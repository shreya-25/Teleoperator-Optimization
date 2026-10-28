# CRNLS development log: changes and results

This log records every change made to the CRNLS solver
([src/simopt_competition_26/crnls.py](../src/simopt_competition_26/crnls.py)),
in order, with the benchmark results measured after each change.

## How results are measured

There are two kinds of run.

- **Official experiment:** `uv run simopt-competition-26`. It runs 10
  macroreplications (independent repeat runs) per solver with 20
  post-replications and draws `plot.png`.
- **Benchmark harness:** [scripts/benchmark.py](../scripts/benchmark.py). It
  runs a chosen problem with chosen solvers and reports:
  - **Gap area:** the area under the normalized optimality-gap curve. This is
    the competition's scoring metric, and **lower is better**. At each budget
    point, gap = (f\* − f(current solution)) / (f\* − f(x0)), where f\* is the
    best post-replicated value any solver found in that test. 1 means the
    solver is still at the start, and 0 means it is at the best known
    solution. Averaging over the budget rewards being fast as well as
    accurate.
  - **Final:** the post-replicated objective of the last recommended solution.
    For minimization problems the harness reports the negated objective, so
    **higher is always better**.
  - **±:** the standard error over macroreplications.

Gap areas can be compared only within one test, because each test has its own
f\*.

### Test problems

| Name | What it is | Dimensions | Bounds | Budget |
|---|---|---|---|---|
| Teleops, default | Competition problem TELEOPS-1 | 72 | ≥ 0, unbounded above | 1000 |
| Teleops, high demand | `car_calls_per_hour` 18, `truck_calls_per_hour` 10 | 72 | same | 1000 |
| Teleops, cost-heavy | `objective_weight` 0.0001 | 72 | same | 1000 |
| Teleops, service-heavy | `objective_weight` 0.00002 | 72 | same | 1000 |
| HOTEL-1 | SimOpt hotel booking limits | 56 | 0–100 | **100** |
| EXAMPLE-2 | SimOpt noisy quadratic, optimum (1, 2, 3, 4) | 4 | −4 to 4 | 1000 |
| DUALSOURCING-1 | SimOpt dual-sourcing inventory | 2 | ≥ 0, unbounded above | 1000 |

---

## Version 0: baselines (before CRNLS)

Official experiment on default teleops, 10 macroreplications:

| Solver | Value at budget 100 | Final value |
|---|---|---|
| DASTRODF | ~0.70 | ~0.781 |
| DemoSolver | ~0.69 | ~0.735 |
| RandomSearch | ~0.66 | ~0.727 |

**Finding:** with common random numbers (CRN), the paired difference between
neighboring teleops schedules has a standard deviation of about 0.001–0.005.
A single replication has a standard deviation of about 0.007, and one-driver
changes are worth about 0.005–0.01. So one paired replication is usually
enough to rank two neighbors. CRNLS is built on this.

## Version 1: first CRNLS

**What it does:**
- Single-coordinate moves, compared with the incumbent on matched replication
  indices, starting with 1 replication per solution.
- A memory of each move's last improvement, used to prioritize; untried moves
  go first.
- Steps double after a success and halve after a failure.
- Two-coordinate trades when no single move helps.
- The sample size doubles at each local optimum.

**Benchmark, default teleops, 6 macroreplications** (mean curve height,
higher is better):

| Solver | Mean curve | Final | At 100 | At 250 | At 500 |
|---|---|---|---|---|---|
| **CRNLS** | **0.7783 ± 0.0010** | **0.7933 ± 0.0009** | **0.7623** | **0.7723** | **0.7882** |
| DASTRODF | 0.7577 ± 0.0034 | 0.7812 ± 0.0040 | 0.7016 | 0.7522 | 0.7717 |

**Official experiment, 10 macroreplications** (`plot.png`, October 17): CRNLS
was at about 0.76 after budget 100 against DASTRODF's 0.70, and finished at
about 0.793 against 0.781, with a much narrower confidence band.

**Robustness suite** (gap area, lower is better):

| Problem | CRNLS | DASTRODF | CRNLS final | DASTRODF final |
|---|---|---|---|---|
| Teleops, high demand | **0.108 ± 0.008** | 0.203 ± 0.033 | **0.7512** | 0.7383 |
| Teleops, cost-heavy | **0.169 ± 0.009** | 0.317 ± 0.034 | **0.6316** | 0.6050 |
| Teleops, service-heavy | **0.076 ± 0.005** | 0.166 ± 0.023 | **0.9050** | 0.8989 |
| EXAMPLE-2 | **0.006 ± 0.000** | 0.017 ± 0.003 | **0.1696** | 0.0696 |
| HOTEL-1 | 0.883 ± 0.004 | **0.086 ± 0.006** | 9,567 | **51,949** |
| DUALSOURCING-1 | not measured | **crashed** | — | — |

**Problems found:**
1. HOTEL-1 starts at all zeros, has 56 variables and allows only 100
   replications. One coordinate at a time cannot cover it.
2. DASTRODF crashes on DUALSOURCING-1 (see the baseline note below).

## Version 2: combined jumps and bound clipping

**What changed:**
- After a successful single move, CRNLS tries applying every direction that
  improved last time **at once**, doubling the steps after each successful
  jump. A failed jump doubles the number of successes required before the
  next one, up to 64.
- A step that would cross a bound is shortened to stop at the bound instead
  of being discarded as infeasible.

| Problem | CRNLS | DASTRODF |
|---|---|---|
| HOTEL-1 | 0.744 ± 0.018 (was 0.883) | **0.086** |
| EXAMPLE-2 | **0.007 ± 0.001** | 0.017 |

**Finding:** a trace showed most single +5 moves on HOTEL-1 change the
objective by exactly 0. Meanwhile DASTRODF's early random global solutions
land near 35,000–40,000 immediately.

## Version 3: random starting samples

**What changed:** before searching, simulate 3 random solutions from the
problem's own generator, and move to the best one if it beats the initial
solution. On teleops this costs 3 of 1000 replications.

| Problem | CRNLS | DASTRODF |
|---|---|---|
| HOTEL-1 | 0.301 ± 0.008 (was 0.744) | **0.086** |
| EXAMPLE-2 | **0.008 ± 0.001** | 0.017 |

## Version 4: random block moves on flat regions

**What changed:** when at least half of the last 20 failed single moves left
the objective exactly unchanged, CRNLS also tries random moves on several
coordinates at once, with steps of 1–8 times the current step. Flat results
temporarily stopped halving the step. On teleops, results are almost never
exactly flat, so this does not trigger there.

| Problem | CRNLS | DASTRODF |
|---|---|---|
| HOTEL-1 | 0.273 ± 0.010 | **0.086** |
| EXAMPLE-2 | **0.009 ± 0.001** | 0.017 |

## Version 5: follow successful block moves with jumps

**What changed:** a successful block move now triggers the doubling jump, so
the search keeps pushing in that direction.

| Problem | CRNLS | DASTRODF | CRNLS final | DASTRODF final |
|---|---|---|---|---|
| HOTEL-1 | 0.249 ± 0.009 | **0.086 ± 0.006** | 41,708 | **51,949** |
| EXAMPLE-2 | **0.009 ± 0.001** | 0.017 ± 0.003 | **0.1696** | 0.0696 |
| Teleops, default | **0.124 ± 0.020** | 0.277 ± 0.024 | **0.7957 ± 0.0014** | 0.7812 ± 0.0044 |
| Teleops, cost-heavy | **0.148 ± 0.033** | 0.313 ± 0.034 | **0.6326 ± 0.0028** | 0.6050 ± 0.0067 |

**Finding:** HOTEL-1's best solution is every limit at 100 (53,053). The
objective rises with the limits overall, but single small changes often show
no effect.

## Version 6: infinite-loop fix (critical)

**Problem:** a single CRNLS run on DUALSOURCING-1 never finished. The cause:
at a local optimum, the sample size `n` was capped at the remaining budget,
which could make it *smaller*. Every neighbor was already cached with that
many replications, so re-checking them cost zero budget, nothing improved,
and the loop ran forever. Any problem could hit this late in a run.

**What changed:**
- `n` never decreases. When the budget cannot cover a larger sample, SimOpt's
  `BudgetExhaustedError` ends the run cleanly.
- As a safety net, the solver stops if a full re-check at a local optimum used
  no budget.

**Verification:** one DUALSOURCING-1 run now takes 3 seconds and uses 94–99%
of the budget across 4 macroreplications. HOTEL-1 and EXAMPLE-2 results are
unchanged.

| Problem | CRNLS | DemoSolver | RandomSearch |
|---|---|---|---|
| DUALSOURCING-1 (10 macroreplications) | **0.011 ± 0.001** | 0.355 ± 0.010 | 0.694 ± 0.014 |

## Version 7: diagonal probe

**What changed:** right after the random start, CRNLS tries two moves that
change **every** coordinate together, one step up and one step down. If one
improves, all coordinates get a positive score in that direction and the
doubling jump takes over. On teleops both probes fail, so they cost 2
replications.

| Problem | CRNLS | DASTRODF | CRNLS final | DASTRODF final |
|---|---|---|---|---|
| HOTEL-1 | **0.029 ± 0.002** | 0.086 ± 0.006 | **52,794** | 51,949 |
| EXAMPLE-2 | 0.055 ± 0.023 (**regression**) | **0.017 ± 0.003** | −1.33 | 0.0696 |
| DUALSOURCING-1 | **0.010 ± 0.001** | crashes | — | — |

**Problem found:** on EXAMPLE-2 CRNLS got stuck at (1, 4, 3, 4). A jump had
grown coordinate 1's step to 4, and stepping 4 → 0 is exactly as good as
staying, because both are 2 away from the target. Since version 4, an exact
tie no longer halved the step, so the step never shrank back to 2.

## Version 8: halve the step on ties again (current version)

**What changed:** any failed single move, tied or worse, halves a step larger
than 1, as in version 1. The diagonal probe now handles the flat starts that
version 4's tie rule was aimed at.

| Problem | Runs | CRNLS | Baseline | CRNLS final | Baseline final |
|---|---|---|---|---|---|
| HOTEL-1 | 10 | **0.028 ± 0.002** | DASTRODF 0.086 ± 0.006 | **52,841 ± 97** | 51,949 ± 365 |
| EXAMPLE-2 | 10 | **0.006 ± 0.000** | DASTRODF 0.017 ± 0.003 | **0.1696** (optimum, every run) | 0.0696 ± 0.1000 |
| DUALSOURCING-1 | 10 | **0.010 ± 0.001** | DemoSolver 0.355 ± 0.010 | **−3195.45** | −3195.62 |
| Teleops, default | 6 | **0.126 ± 0.020** | DASTRODF 0.277 ± 0.024 | **0.7957 ± 0.0014** | 0.7812 ± 0.0044 |
| Teleops, high demand | 6 | **0.092 ± 0.011** | DASTRODF 0.212 ± 0.033 | **0.7541 ± 0.0008** | 0.7383 ± 0.0084 |
| Teleops, cost-heavy | 6 | **0.150 ± 0.033** | DASTRODF 0.313 ± 0.034 | **0.6326 ± 0.0028** | 0.6050 ± 0.0067 |
| Teleops, service-heavy | 6 | **0.068 ± 0.017** | DASTRODF 0.171 ± 0.023 | **0.9047 ± 0.0007** | 0.8989 ± 0.0009 |

---

## Baseline note: DASTRODF crashes on DUALSOURCING-1

DASTRODF raised `ValueError: empty range in randrange(...)` on **8 of 10**
DUALSOURCING-1 macroreplications. The error comes from `_sample_step` in
[dastrodf.py](../src/simopt_competition_26/dastrodf.py). DASTRODF boxes
unbounded variables to x0 ± 5 (`unbounded_search_radius`), but its random
"shake" solutions can land outside that box. Once the incumbent is outside,
the allowed step range is empty (its low end is above its high end), and
`randint` raises. This is a bug in the provided baseline and has not been
changed. DemoSolver and RandomSearch are the comparison on that problem.

## Summary of the current version against DASTRODF

| Problem | Winner | Margin in gap area |
|---|---|---|
| Teleops (all four settings) | CRNLS | about half the gap area (see version 8) |
| HOTEL-1 | CRNLS | 0.028 vs 0.086 |
| EXAMPLE-2 | CRNLS | 0.006 vs 0.017 |
| DUALSOURCING-1 | CRNLS | DASTRODF crashes on 8 of 10 runs |

---

# CRNLS 1.2 experiments

CRNLS 1.2 is a separate solver,
[src/simopt_competition_26/crnls12.py](../src/simopt_competition_26/crnls12.py),
class `CRNLS12`. `crnls.py` (version 8 above) is unchanged.

**Where a default-teleops run spends its budget (CRNLS v8, one run):**

| Sample size n | Budget | Moves tried | Improvements |
|---|---|---|---|
| 1 | 664 | 705 | 33 |
| 2 | 270 | 166 | 2 |
| 4 | 56 | 18 | 2 |

**Mean gap by budget (CRNLS v8, 6 runs):** 25: 0.553, 50: 0.476, 100: 0.239,
200: 0.148, 400: 0.107, 700: 0.052, 1000: 0.037. About 40% of the gap area
comes from the first 100 replications.

**Trace of the first 160 replications:** every improvement came from a
single-coordinate move. Every combined jump failed (−0.07 to −0.62), costing
about 5 replications.

## Experiment 1: patience (rejected)

Treat a point as a local optimum after a run of consecutive failed re-checks
(a fraction of 2 × dimension), to skip re-checking moves that were already
bad. Default teleops, 6 runs:

| Variant | Gap area | Final |
|---|---|---|
| **CRNLS v8** | **0.126 ± 0.020** | **0.7957** |
| Patience 0.125 | 0.178 ± 0.033 | 0.7811 |
| Patience 0.25 | 0.163 ± 0.033 | 0.7831 |
| Patience 0.5 | 0.161 ± 0.031 | 0.7836 |

**Finding:** the full re-checks at n = 1 find real improvements. Leaving the
cheap n = 1 phase early hurts. The code was removed.

## Experiment 2: setting changes (no effect)

Default teleops, 6 runs:

| Variant | Gap area | Final |
|---|---|---|
| CRNLS v8 | 0.126 ± 0.020 | 0.7957 |
| `sample_growth` = 1.5 | 0.126 ± 0.020 | 0.7959 |
| `sample_growth` = 4 | 0.126 ± 0.020 | 0.7962 |
| `initial_sample_size` = 2 | 0.179 ± 0.031 (worse) | 0.7941 |
| `pair_moves` = 48 | 0.126 ± 0.020 | 0.7961 |

**Finding:** the score is decided in the n = 1 phase. Later settings barely
matter, and starting with 2 replications per candidate is clearly worse.

## Experiment 3: hot moves (kept in 1.2)

After a successful single move, retry the same move next at the **same** step.
Double the step only after **two consecutive** successes in that direction
(v8 doubled after every success). The setting `hot_after_sweep` (default
true) waits until every move has been tried once before retrying hot moves.

**6 runs, hot always:** 0.122 ± 0.018 against CRNLS 0.131 ± 0.020. Slower
before budget 50, better from budget 100 on.

**12 runs, default teleops:**

| Version | Gap area | Worst run | Final | Gap at 100 | Gap at 400 | Gap at 1000 |
|---|---|---|---|---|---|---|
| CRNLS v8 | 0.121 ± 0.015 | 0.219 | **0.7952** | 0.217 | 0.098 | **0.040** |
| **1.2, hot after sweep (default)** | 0.118 ± 0.012 | 0.182 | 0.7951 | **0.205** | 0.078 | **0.040** |
| 1.2, hot always | **0.116 ± 0.007** | **0.160** | 0.7933 | 0.207 | **0.076** | 0.052 |

**Small problems, 1.2 default, 10 runs:** HOTEL-1 0.028 ± 0.002, EXAMPLE-2
0.006 ± 0.000, DUALSOURCING-1 0.011 ± 0.001. These are unchanged from v8.

**Finding:** the differences between the three versions are within noise.
"Hot always" is the most consistent but ends at a worse schedule. The 1.2
default ties v8 on average, is slightly better mid-run, and has a better
worst case.

## Conclusion so far

CRNLS appears close to the limit of its design on teleops. Tuning changes
move the gap area by less than its uncertainty. A larger gain would need a
new source of information, such as learning which coordinates improve
together, which risks overfitting to teleops.
