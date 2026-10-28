CRN Priority Local Search (CRNLS)
=================================

See the :mod:`simopt_competition_26.crnls` module for API details.

Description
-----------

CRNLS is a local search for integer-ordered simulation optimization problems
with box constraints. It is built around one observation: when solutions are
simulated with common random numbers (CRN), replication *i* of every solution
uses the same random inputs. Comparing a candidate with the incumbent on the
same replication indices therefore measures the noise of the *difference*,
which is usually far smaller than the noise of either estimate. On the
tele-operator problem, for example, the standard deviation of a single
replication of the objective is about 0.007, while the paired difference
between neighboring schedules has a standard deviation of about 0.001-0.005,
against true differences of about 0.005-0.01. A single paired replication is
then usually enough to rank two neighbors, so CRNLS starts with one
replication per solution and spends the budget on exploring rather than on
averaging.

The search proceeds as follows.

1. **Start.** Simulate the initial solution. Then simulate a few random
   solutions from the problem's random-solution generator and move to the best
   of them if it beats the initial solution. Then try two *diagonal* moves
   that change every coordinate by one step together, up and then down; if
   one improves, the combined jumps of step 4 continue in that direction. This
   costs a handful of replications and protects against a poor starting point.
2. **Prioritized single moves.** A single move changes one coordinate up or
   down by that coordinate's current step size, shortened if needed so that it
   stops at a bound. The solver remembers the improvement each move showed the
   last time it was tried. Untried moves are tried first, in random order;
   after that, moves are tried in order of their last observed improvement.
   A move counts as *checked* only if it was evaluated against the current
   incumbent.
3. **Acceptance and step adaptation.** A candidate replaces the incumbent if
   its mean over the incumbent's first *n* replications is better (paired
   comparison). After a successful move, that coordinate's step doubles and
   the move stays at the top of the queue, so the search accelerates along
   improving directions. After a move that does not improve the objective, a
   step larger than one is halved and retried.
4. **Combined jumps.** After a successful single move, CRNLS applies every
   direction that improved on its last trial *at once*, with steps that double
   after each successful jump. A failed jump doubles the number of successful
   single moves required before the next jump (up to 64), so jumps cost little
   when coordinates interact.
5. **Random block moves on flat regions.** If at least half of the recent
   failed single moves left the objective exactly unchanged, single moves
   carry little information. CRNLS then also tries random moves on several
   coordinates at once, with steps of one to eight times the current step, and
   follows a successful block move with a combined jump.
6. **Two-coordinate trades.** When no single move improves the incumbent,
   CRNLS tries up to ``pair_moves`` combinations of one "up" move and one
   "down" move on different coordinates, chosen from the moves whose
   last observed effects were the least bad. This captures substitutions
   (for example, moving a shift from one hour to another).
7. **Sample-size growth.** When neither single moves nor trades improve the
   incumbent, the incumbent is a local optimum for the current sample size
   *n*. CRNLS multiplies *n* by ``sample_growth``, adds replications to the
   incumbent, and re-checks every move with the larger paired sample. Early
   decisions are therefore cheap, and later decisions are robust to the
   scenario-specific overfitting that a small fixed sample would cause. The
   sample size never decreases; the run ends when the budget cannot cover the
   next sample, or if a full re-check uses no new replications.

Every accepted solution is recorded with ``ctx.log``, so the progress curve
reflects each improvement as soon as it is found.

Modifications & Implementation
------------------------------

**_initialize**: Converts bounds to integers, sets the initial step of each
coordinate (one for unbounded coordinates, ``initial_step_fraction`` of the
range for bounded ones), and creates the move-score memory.

**_solution**: Returns the cached solution for a vector, adding replications
until it has at least *n*. Solutions are cached so that revisited points reuse
their replications.

**_try**: Evaluates a move with *n* replications and computes the paired
improvement over the incumbent's first *n* replications; accepts and logs the
candidate if it improves.

**_next_key**: Selects the untried or most promising single move that has not
been checked against the current incumbent.

**_jump**: Repeats combined multi-coordinate moves while they improve, then
backs off.

**_block**: Tries one random multi-coordinate move in flat regions.

**_pair_moves**: Builds the two-coordinate trades tried at a local optimum.

**solve**: Runs the random start and the diagonal probe, then the main loop of single moves, trades
and sample-size growth until the budget is exhausted.

The solver uses only the problem's dimension, bounds,
``check_deterministic_constraints`` and ``get_random_solution``, so it applies
to any single-objective, box-constrained, integer-ordered SimOpt problem.

Scope
-----

* objective_type: single
* constraint_type: box
* variable_type: discrete
* gradient_observations: not available

Solver Factors
--------------

* crn_across_solns: Use CRN across solutions?
    * Default: True
* initial_sample_size: Replications per solution in the first stage, integer > 0.
    * Default: 1
* sample_growth: Sample-size multiplier at each local optimum, > 1.
    * Default: 2.0
* initial_step_fraction: Initial step as a fraction of each finite coordinate range, in [0, 1]. Unbounded coordinates start with a step of 1.
    * Default: 0.05
* initial_random_samples: Random solutions compared with the initial solution before searching, integer >= 0.
    * Default: 3
* pair_moves: Two-coordinate moves tried at a local optimum before growing the sample, integer >= 0.
    * Default: 24

References
----------

This solver was developed for the 2026 SimOpt Solver Competition. It draws on
standard ideas from the simulation optimization literature: common random
numbers for paired comparisons, adaptive step sizes in pattern search, and
increasing sample sizes in the spirit of retrospective approximation.
