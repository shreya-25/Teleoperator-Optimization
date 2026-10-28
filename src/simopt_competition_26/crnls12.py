"""CRNLS 1.2: CRN-paired priority local search."""

from __future__ import annotations

import math
from collections import deque
from typing import Annotated, ClassVar

import numpy as np
from pydantic import Field
from simopt.base import (
    ConstraintType,
    Context,
    ObjectiveType,
    Problem,
    Solution,
    Solver,
    SolverConfig,
    VariableType,
)

Move = tuple[tuple[int, int], ...]


class CRNLS12Config(SolverConfig):
    """Configuration for CRNLS 1.2."""

    initial_sample_size: Annotated[
        int, Field(default=1, gt=0, description="replications per solution in the first stage")
    ]
    sample_growth: Annotated[
        float,
        Field(default=2.0, gt=1.0, description="sample-size multiplier at each local optimum"),
    ]
    initial_step_fraction: Annotated[
        float,
        Field(
            default=0.05,
            ge=0.0,
            le=1.0,
            description="initial step as a fraction of each finite coordinate range",
        ),
    ]
    initial_random_samples: Annotated[
        int,
        Field(
            default=3,
            ge=0,
            description="random solutions compared with the initial solution before searching",
        ),
    ]
    hot_after_sweep: Annotated[
        bool,
        Field(
            default=True,
            description="retry a just-successful move only after every move has been tried once",
        ),
    ]
    pair_moves: Annotated[
        int,
        Field(
            default=24,
            ge=0,
            description="two-coordinate moves tried at a local optimum before growing the sample",
        ),
    ]


class CRNLS12(Solver):
    """Priority local search using paired common-random-number comparisons.

    Every candidate is compared with the incumbent on the same replication
    indices, so with CRN the comparison noise is the noise of the difference,
    not of each estimate. Moves are prioritized by the improvement they showed
    the last time they were tried; step sizes grow along improving directions
    and the sample size grows each time a local optimum is certified. Improving
    directions are also combined into multi-coordinate jumps, and random block
    moves probe regions where single moves leave the objective unchanged.
    """

    name: str = "CRNLS12"
    config_class: ClassVar[type[SolverConfig]] = CRNLS12Config
    class_name_abbr: ClassVar[str] = "CRNLS12"
    class_name: ClassVar[str] = "CRN Priority Local Search 1.2"
    objective_type: ClassVar[ObjectiveType] = ObjectiveType.SINGLE
    constraint_type: ClassVar[ConstraintType] = ConstraintType.BOX
    variable_type: ClassVar[VariableType] = VariableType.DISCRETE
    gradient_needed: ClassVar[bool] = False

    def _initialize(self, problem: Problem, ctx: Context) -> None:
        self.problem = problem
        self.ctx = ctx
        self.rng = self.rng_list[1]
        self.cache: dict[tuple[int, ...], Solution] = {}
        self.lower = [-math.inf if math.isinf(b) else math.ceil(b) for b in problem.lower_bounds]
        self.upper = [math.inf if math.isinf(b) else math.floor(b) for b in problem.upper_bounds]
        fraction = self.factors["initial_step_fraction"]
        self.max_step = []
        self.step = []
        for lo, hi in zip(self.lower, self.upper, strict=True):
            span = hi - lo
            if math.isinf(span):
                self.max_step.append(2**20)
                self.step.append(1)
            else:
                self.max_step.append(max(1, int(span)))
                self.step.append(max(1, round(fraction * span)))
        # Last observed improvement for each (coordinate, direction) and the
        # incumbent version it was observed at.
        self.score: dict[tuple[int, int], float] = {}
        self.scored_at: dict[tuple[int, int], int] = {}
        self.version = 0
        # The move that just succeeded is retried first; steps double only
        # after consecutive successes in the same direction.
        self.hot: tuple[int, int] | None = None
        self.streak: dict[tuple[int, int], int] = {}
        # Successful single moves required before the next combined jump.
        self.jump_wait = 1
        self.successes_since_jump = 0
        # Whether each recent failed single move left the objective unchanged.
        self.recent_flat: deque[bool] = deque(maxlen=20)

    def _solution(self, x: tuple[int, ...], n: int) -> Solution:
        solution = self.cache.get(x)
        if solution is None:
            solution = self.ctx.evaluate(x, 0)
            self.cache[x] = solution
        if solution.n_reps < n:
            self.ctx.evaluate(solution, n - solution.n_reps)
        return solution

    def _mean(self, solution: Solution, n: int) -> float:
        # Context.evaluate normalizes every objective to minimization.
        return float(np.mean(solution.objectives[:n, 0]))

    def _feasible(self, x: tuple[int, ...]) -> bool:
        return all(
            lo <= v <= hi for v, lo, hi in zip(x, self.lower, self.upper, strict=True)
        ) and self.problem.check_deterministic_constraints(x)

    def _apply(self, move: Move) -> tuple[int, ...] | None:
        x = list(self.incumbent.x)
        for idx, delta in move:
            x[idx] += delta
        candidate = tuple(x)
        return candidate if self._feasible(candidate) else None

    def _try(self, move: Move) -> float | None:
        """Evaluate a move with paired replications; return its improvement."""
        candidate = self._apply(move)
        if candidate is None or all(delta == 0 for _, delta in move):
            return None
        solution = self._solution(candidate, self.n)
        improvement = self._mean(self.incumbent, self.n) - self._mean(solution, self.n)
        if improvement > 0:
            self.incumbent = solution
            self.version += 1
            self.ctx.log(solution)
        return improvement

    def _clipped(self, idx: int, delta: int) -> int:
        """Shorten a step so it stops at the bound instead of crossing it."""
        value = self.incumbent.x[idx]
        return int(min(max(value + delta, self.lower[idx]), self.upper[idx]) - value)

    def _single_move(self, key: tuple[int, int]) -> Move:
        idx, sign = key
        return ((idx, self._clipped(idx, sign * self.step[idx])),)

    def _jump_move(self) -> Move:
        """Apply every direction that improved last time it was tried, all at once."""
        best: dict[int, tuple[float, int]] = {}
        for (idx, sign), score in self.score.items():
            if score > 0 and score > best.get(idx, (0.0, 0))[0]:
                best[idx] = (score, sign)
        move = tuple(
            (idx, delta)
            for idx, (_, sign) in best.items()
            if (delta := self._clipped(idx, sign * self.step[idx])) != 0
        )
        return move if len(move) >= 2 else ()

    def _block(self) -> None:
        """Try one random move on several coordinates; keep its parts on success."""
        dim = self.problem.dim
        if dim < 2:
            return
        size = self.rng.randint(2, max(2, dim // 3))
        move = []
        for idx in self.rng.sample(range(dim), size):
            up, down = self.score.get((idx, 1), 0.0), self.score.get((idx, -1), 0.0)
            sign = (1 if up > down else -1) if up != down else self.rng.choice((1, -1))
            delta = self._clipped(idx, sign * self.step[idx] * 2 ** self.rng.randint(0, 3))
            if delta != 0:
                move.append((idx, delta))
        improvement = self._try(tuple(move))
        if improvement is None or improvement <= 0:
            return
        for idx, delta in move:
            sign = 1 if delta > 0 else -1
            self.score[(idx, sign)] = improvement / len(move)
            self.score[(idx, -sign)] = -improvement / len(move)
            self.step[idx] = min(self.max_step[idx], max(self.step[idx], abs(delta)))
        self._jump()

    def _jump(self) -> None:
        """Repeat combined jumps while they improve; back off after a failure."""
        while self.ctx.budget.remaining > 0:
            move = self._jump_move()
            if not move:
                return
            improvement = self._try(move)
            if improvement is None or improvement <= 0:
                self.jump_wait = min(2 * self.jump_wait, 64)
                return
            self.jump_wait = 1
            for idx, _ in move:
                self.step[idx] = min(self.max_step[idx], 2 * self.step[idx])

    def _next_key(self) -> tuple[int, int] | None:
        """Pick the untried or most promising single move at the current incumbent."""
        best_key = None
        best_rank = (-math.inf, -math.inf)
        for key in self.keys:
            if self.scored_at.get(key) == self.version:
                continue
            move = self._single_move(key)
            if move[0][1] == 0 or self._apply(move) is None:
                continue
            rank = (self.score.get(key, math.inf), self.rng.random())
            if rank > best_rank:
                best_rank = rank
                best_key = key
        if math.isinf(best_rank[0]) and self.factors["hot_after_sweep"]:
            # Finish the first sweep over untried moves before exploiting.
            return best_key
        if self.hot is not None and self.scored_at.get(self.hot) != self.version:
            move = self._single_move(self.hot)
            if move[0][1] != 0 and self._apply(move) is not None:
                return self.hot
        self.hot = None
        return best_key

    def _pair_moves(self) -> list[Move]:
        """Combine the least-bad up and down moves on different coordinates."""
        ups = sorted(
            (k for k in self.keys if k[1] > 0 and k in self.score), key=lambda k: -self.score[k]
        )
        downs = sorted(
            (k for k in self.keys if k[1] < 0 and k in self.score), key=lambda k: -self.score[k]
        )
        limit = max(1, math.isqrt(self.factors["pair_moves"]) + 2)
        pairs = [
            (self.score[u] + self.score[d], u, d)
            for u in ups[:limit]
            for d in downs[:limit]
            if u[0] != d[0]
        ]
        pairs.sort(key=lambda item: -item[0])
        return [
            self._single_move(u) + self._single_move(d)
            for _, u, d in pairs[: self.factors["pair_moves"]]
        ]

    def solve(self, problem: Problem, ctx: Context) -> None:
        self._initialize(problem, ctx)
        self.n = self.factors["initial_sample_size"]
        self.keys = [(idx, sign) for idx in range(problem.dim) for sign in (1, -1)]
        x0 = tuple(int(v) for v in problem.factors["initial_solution"])
        self.incumbent = self._solution(x0, self.n)
        ctx.log(self.incumbent)

        # A poor starting point can be far worse than a typical solution.
        for _ in range(self.factors["initial_random_samples"]):
            x = tuple(int(v) for v in problem.get_random_solution(self.rng_list[2]))
            if x in self.cache or not self._feasible(x):
                continue
            solution = self._solution(x, self.n)
            if self._mean(solution, self.n) < self._mean(self.incumbent, self.n):
                self.incumbent = solution
                ctx.log(solution)

        # Probe moving every coordinate together; a success seeds combined jumps.
        for sign in (1, -1):
            move = tuple(
                (idx, delta)
                for idx in range(problem.dim)
                if (delta := self._clipped(idx, sign * self.step[idx])) != 0
            )
            improvement = self._try(move) if len(move) >= 2 else None
            if improvement is not None and improvement > 0:
                for idx, _ in move:
                    self.score[(idx, sign)] = improvement / len(move)
                    self.score[(idx, -sign)] = -improvement / len(move)
                    self.step[idx] = min(self.max_step[idx], 2 * self.step[idx])
                self._jump()
                break

        budget_at_optimum = -1
        while ctx.budget.remaining > 0:
            key = self._next_key()
            if key is not None:
                idx, sign = key
                improvement = self._try(self._single_move(key))
                if improvement is None:
                    self.scored_at[key] = self.version
                    continue
                if improvement > 0:
                    # Keep the direction on top and lengthen its stride.
                    self.score[key] = improvement
                    self.score[(idx, -sign)] = -improvement
                    self.scored_at[(idx, -sign)] = self.version
                    self.streak[key] = self.streak.get(key, 0) + 1
                    if self.streak[key] >= 2:
                        self.step[idx] = min(self.max_step[idx], 2 * self.step[idx])
                    self.hot = key
                    self.successes_since_jump += 1
                    if self.successes_since_jump >= self.jump_wait:
                        self.successes_since_jump = 0
                        self._jump()
                    continue
                self.score[key] = improvement
                self.scored_at[key] = self.version
                self.streak[key] = 0
                self.recent_flat.append(improvement == 0)
                if self.step[idx] > 1:
                    # Retry a shorter step in this direction before giving up.
                    self.step[idx] = max(1, self.step[idx] // 2)
                    self.scored_at.pop(key, None)
                    self.scored_at.pop((idx, -sign), None)
                if improvement == 0 and 2 * sum(self.recent_flat) >= len(self.recent_flat):
                    # Flat region: single moves carry little signal, so
                    # probe several coordinates at once.
                    self._block()
                continue

            # Every single move fails: try two-coordinate trades.
            version = self.version
            for move in self._pair_moves():
                improvement = self._try(move)
                if improvement is not None and improvement > 0:
                    break
            if self.version != version:
                continue

            # Local optimum for this sample: grow the sample and re-certify.
            if ctx.budget.used == budget_at_optimum:
                # Re-certifying cost nothing, so nothing new can be learned.
                return
            budget_at_optimum = ctx.budget.used
            self.n = max(self.n + 1, math.ceil(self.n * self.factors["sample_growth"]))
            # Raises BudgetExhaustedError, ending the run, if the budget is too small.
            self._solution(self.incumbent.x, self.n)
            self.version += 1
