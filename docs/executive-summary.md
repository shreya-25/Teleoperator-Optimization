# SimOpt 2026 Competition: Our Solver, CRNLS

## Executive summary

We built a new search method, **CRNLS**, for the SimOpt 2026 competition. The competition asks teams to write a program that finds good decisions for problems we can only test by running a computer simulation, under a strict limit on how many simulations we may run.

On every problem we tested, CRNLS beats the baseline method supplied by the organizers:

- On the main competition problem (scheduling remote drivers), CRNLS leaves **about half as much improvement unfound** as the baseline, and it ends with a better schedule.
- It is the clear winner on three other, unrelated test problems as well, which shows it isn't tuned to a single case.
- On one of those problems the baseline **crashes on 8 out of 10 runs**. CRNLS has never crashed.

---

## Problem statement

### The competition

Many real decisions, like how many staff to schedule or how much stock to order, are too complex to solve with a formula. Instead, people build a **simulation**: a computer model that plays out a day (or a week) many times with random events and reports how well a given plan did.

Each simulation run is noisy, because it depends on chance, and it takes time. The competition gives every method the same fixed number of runs (the **budget**). The goal is to find the best plan possible within that budget, and to find it **quickly**.

### How entries are scored

The judges track how good each method's best plan is at every point while it uses up its budget. They measure the **gap**: how much of the possible improvement is still missing.

- A gap of 100% means no progress beyond the starting plan.
- A gap of 0% means the best known plan has been reached.

The score is the **average gap across the whole run**. Lower is better. A method that improves fast early on scores much better than one that only gets there at the end.

Entries are judged on hidden versions of the main problem and on other problems the teams haven't seen. A method that only works on one problem will lose.

### The main problem: scheduling remote drivers

Self-driving cars and trucks sometimes get stuck and call a center where a human driver takes over remotely. The center must decide **how many drivers start a shift at each hour of the day**, for three kinds of driver: car-only, truck-only, and flexible (either).

That is 72 numbers to choose (24 hours × 3 driver types). The trade-off is:

- **More drivers** means more calls are answered immediately.
- **More drivers** also means higher wages, including night and overtime rates.

The score for a schedule combines both: the share of calls answered immediately, minus a penalty for daily staffing cost.

### The other test problems

To make sure our method works in general, we also tested it on three standard problems from the SimOpt library:

| Problem | What is being decided |
|---|---|
| **Hotel** | How many rooms to make available at each price for each length of stay (56 numbers), to maximize revenue |
| **Dual sourcing** | How much stock to order from a cheap slow supplier and a costly fast supplier (2 numbers), to minimize total cost |
| **Example** | A simple puzzle with a known correct answer (4 numbers), used as a sanity check |

The method is never told what problem it is solving. It only proposes a plan and gets back a noisy score.

---

## Baseline model summary: DASTRODF

The organizers supplied **DASTRODF** as the method to beat. In plain terms:

1. It looks at the plans it has tried so far and builds a rough "map" of which changes seem to help.
2. It uses the map to suggest 24 new plans and tests the 2 most promising ones.
3. If a new plan seems better, it moves there and widens its search area. If not, it narrows the area.

**Methodology (technical overview).** 

The DASTRODF algorithm uses a simulation-based, derivative-free trust-region optimization approach to find the best combination of discrete (integer) decision variables while minimizing the objective function. The algorithm begins with an initial solution and evaluates its performance through multiple simulation replications to account for randomness. It then builds a local quadratic surrogate model using previously evaluated solutions to approximate how changes in decision variables affect the objective value. Based on this model, the algorithm generates a pool of candidate solutions using a combination of greedy search, individual variable adjustments, and random exploration. These candidates are ranked according to their predicted performance, and the most promising ones are evaluated using the actual simulation. The algorithm compares the new solutions with the current best solution (incumbent) and performs additional simulation replications when the results are too close to confidently distinguish. If a candidate produces a lower estimated objective value, it replaces the current best solution. The algorithm also dynamically adjusts its trust-region radius based on the agreement between predicted and actual improvements, expanding the search when predictions are successful and shrinking it when improvements are poor or unsuccessful. To avoid becoming trapped in a local optimum, it introduces larger exploratory moves after repeated unsuccessful iterations. This process continues until the simulation budget is exhausted or the algorithm stops making progress, ultimately returning the best solution identified during the search.

## In Simple Terms

The algorithm starts with one solution, learns from previous simulation results, predicts which new solutions might be better, tests the most promising ones, and gradually improves its decisions while managing the limited simulation budget.

## Additional Information 

- **Local model.** Around the current best solution (the *incumbent*), it fits a cheap surrogate model of the objective: a *separable quadratic* (a constant, plus a linear and a squared term for each variable, with no interaction terms). The fit uses weighted ridge regression on up to 64 previously simulated nearby points, giving more weight to points that are closer and have more replications.
- **Candidate generation.** In each iteration it generates a pool of 24 candidate solutions inside the trust region, a box of a given radius around the incumbent:
  - a greedy candidate built from the model's best step in each variable,
  - single-variable moves,
  - random perturbations,
  - occasional completely random solutions, early on or after repeated failures.
- **Selection and comparison.** It ranks the candidates by predicted value, simulates the top 2 with 2 replications each, and compares the best of them to the incumbent using sample means and standard errors. If the difference is within the noise, it adds replications to both, up to 6.
- **Radius update.** It computes the ratio of actual to predicted improvement. A good ratio means the model is trusted, so the step is accepted and the radius doubles. A poor ratio or a failure halves the radius.
- **Unbounded variables.** These are confined to the starting value ± 5.

**Weaknesses we found:**

- **The map is often wrong early on.** With 72 numbers and little data, the guesses are poor, so it wastes runs at the start, which is exactly when the score counts most.
- **It is fooled by luck.** It compares plans that were tested under different random conditions, so a plan can look better just because it had an easy day.
- **It crashes** on the dual-sourcing problem (8 of 10 runs), because of a bug in how it handles choices with no upper limit.

---

## Our model summary: CRNLS

CRNLS stands for "Common Random Numbers Local Search."

**Methodology (technical overview).** 

The CRNLS algorithm uses a **simulation-based, derivative-free, priority-driven local search approach** to identify an effective combination of discrete (integer) decision variables while minimizing the objective function. The algorithm begins with an initial solution and evaluates several randomly generated alternatives to select a promising starting point. It then explores neighboring solutions by increasing or decreasing individual decision variables, comparing their performance through simulation replications using **Common Random Numbers (CRN)** to reduce comparison noise when common random streams are provided. Based on the observed improvements, the algorithm assigns priority scores to different search directions, favoring previously successful moves and increasing their step sizes to accelerate the search. It also combines promising directions into multi-variable jumps and introduces random block moves to explore regions where individual variable changes produce little or no improvement. When a move fails to improve the objective value, the algorithm reduces its step size to investigate smaller adjustments. If no improvement is found through the available single-variable moves and selected two-variable combinations, the algorithm treats the current solution as a potential local optimum and **increases the number of simulation replications** to obtain more reliable performance estimates before continuing the search. Newly evaluated solutions are compared with the current best solution (incumbent), and any candidate producing a lower estimated objective value replaces it. This iterative process continues until the simulation budget is exhausted or no further progress can be made, ultimately identifying the best solution encountered during the search.

**In simple terms:** The algorithm starts with a solution, tests small changes to individual variables, remembers which directions improve performance, makes larger or combined moves when successful, and uses additional simulations when progress slows to gradually find better solutions within a limited simulation budget.

**Additional Information**

CRNLS is an *adaptive coordinate (pattern) search* on the integer lattice, built around *common random numbers* (CRN). It uses no surrogate model; every decision is based on direct, paired simulation comparisons.

- **Paired comparisons with CRN.** Replication *i* of every solution uses the same random-number streams, meaning the same call arrivals and service times. A candidate is compared to the incumbent on the *same* first *n* replications, and is accepted if its paired mean is better. Because both solutions face identical randomness, most of the noise cancels in the difference, so small sample sizes still give reliable comparisons.
- **Sample-size schedule.** The search starts with *n* = 1 replication per solution. When a full sweep of the neighborhood finds no improvement (a local optimum at the current *n*), *n* is doubled, the incumbent is topped up to *n* replications, and the search continues. Effort grows only once the easy improvements are exhausted, and an optimum found by luck is re-checked with more data.
- **Prioritized moves with adaptive steps.**
  - Each move is "variable *j*, direction ±". Every move has a priority equal to the improvement it produced the last time it was tried, and untried moves come first.
  - Each move has its own step size, which doubles after success and halves after failure, and is clipped to the variable's bounds.
- **Acceleration.** After successes, CRNLS tries a *combined jump*: it applies all recently successful moves at once and keeps repeating while the result improves. Failed jumps are tried less often (exponential back-off).
- **Escaping stagnation.**
  - When single moves fail, it tries *two-variable trades* (+1 on one variable, −1 on another), such as moving a driver from one hour to another.
  - In flat regions, where many moves change nothing, it tries random *block moves* that shift several variables at once.
- **Initialization.** Besides the given starting solution, it evaluates 3 random solutions and a "diagonal probe" (all variables moved up or down together), then starts from the best.
- **Safeguards.**
  - The sample size never decreases.
  - The search stops cleanly when a re-check costs no new budget.
  - It works with unbounded variables without any artificial box.

It rests on three ideas.

### 1. Fair comparisons

When CRNLS compares two plans, it tests both under **exactly the same random conditions**: the same calls arriving at the same times. Any difference in score then comes from the plans themselves, not from luck. One test per plan is often enough to tell which is better, so CRNLS can try many more plans with the same budget.

### 2. Keep doing what works

CRNLS changes one number at a time, for example "add one flexible driver at 8 am."

- It remembers which changes helped and tries those first.
- When a change keeps helping, it takes **bigger steps** in that direction. When it stops helping, it takes smaller steps.
- After a run of successes, it tries **making all the good changes at once**, which often saves many runs.

### 3. Don't get stuck

- When single changes stop helping, it tries **trading** between two numbers, such as moving a driver from one hour to another.
- When nothing seems to make a difference, it tries a few random **group changes** to escape flat areas.
- When it believes it has found the best plan nearby, it **tests more carefully** to make sure it wasn't luck, and keeps going if it was.

### How we built it

We improved CRNLS in eight rounds, testing each version against the baseline and recording every change and result in [results-log.md](results-log.md). We also tested ideas that didn't help and removed them. A refined version, CRNLS 1.2, performs the same within measurement noise.

---

## Results

### What is being optimized

**The main objective function (driver scheduling).** For each proposed schedule, the simulation plays out nine days of calls (one warm-up day, seven measured days and one buffer day) and returns a single score:

```
score = immediate_service_fraction − 0.00005 × staff_cost        (higher is better)
```

- **immediate_service_fraction** is the share of measured calls that reached a driver right away, with no waiting. It runs from 0 to 1.
- **staff_cost** is the average daily wage bill in dollars, including the late-night rate (1.2×) and overtime (1.5×).
- **0.00005** is the *objective weight*. It converts dollars into score points, so every $1,000 a day of wages costs 0.05.

The 72 decision variables are the number of drivers starting a shift at each hour (24 hours) for each driver type (car-only, flexible, truck-only). Each must be a whole number of at least zero. Adding drivers raises the service fraction but also the cost, so the best schedule balances the two.

Because every run has random call arrivals and driving times, the score of a schedule is **noisy**. The true objective is its *average* over many runs, which the solver can only estimate by running the simulation. The judges have said they may also test other versions of this score, such as different weights or waiting-time-based objectives, so a solver must not rely on this exact formula.

**How the same solver handles different problems.** CRNLS never sees the formula of any problem. Each problem is a **black box**:

1. The solver proposes a plan: a list of whole numbers.
2. The problem runs its own simulation and returns a noisy score for each replication.
3. The SimOpt framework turns every problem into a *minimization*: scores to be maximized (driver score, hotel revenue) have their sign flipped. The solver therefore always does the same thing: make the number smaller.

From each problem the solver only reads:
- the number of variables (72, 56, 2 or 4),
- each variable's lower and upper bound, which may be unlimited,
- the starting plan,
- the simulation budget (1,000 runs, or 100 for the hotel).

| Problem | Objective computed inside the simulation | Goal | Variables | Limits | Budget |
|---|---|---|---|---|---|
| Driver scheduling | service fraction − 0.00005 × daily wage cost | maximize | 72 shift-start counts | ≥ 0, no upper limit | 1,000 |
| Hotel | total room revenue | maximize | 56 booking limits | 0 to 100 | 100 |
| Dual sourcing | ordering + holding + shortage cost per day | minimize | 2 order-up-to levels | ≥ 0, no upper limit | 1,000 |
| Example | squared distance from (1, 2, 3, 4), plus noise | minimize | 4 integers | −4 to 4 | 1,000 |

This is why the method carries over to the hidden test problems. Its rules (paired comparisons, adaptive step sizes, jumps, trades) depend only on proposing plans and comparing scores, not on what the plan means. For example:
- Step sizes grow automatically when a variable has a wide range, like the hotel's 0–100 booking limits.
- The step sizes stay unrestricted when a variable has no upper limit, like dual sourcing.

### Scores

Every number below is an **average over repeated runs**, 6 to 12 per problem.

**Gap** is how much of the possible improvement was still missing, averaged over the whole run. **This is the competition score: lower is better.**

| Problem | Our gap (CRNLS) | Baseline gap | Our final result | Baseline final result |
|---|---|---|---|---|
| Driver scheduling, standard | **12.6%** | 27.7% (DASTRODF) | **0.796** | 0.781 |
| Driver scheduling, high demand | **9.2%** | 21.2% (DASTRODF) | **0.754** | 0.738 |
| Driver scheduling, cost matters more | **15.0%** | 31.3% (DASTRODF) | **0.633** | 0.605 |
| Driver scheduling, service matters more | **6.8%** | 17.1% (DASTRODF) | **0.905** | 0.899 |
| Hotel (revenue, only 100 runs allowed) | **2.8%** | 8.6% (DASTRODF) | **$52,841** | $51,949 |
| Example (known answer) | **0.6%** | 1.7% (DASTRODF) | **Exact answer every run** | Missed on some runs |
| Dual sourcing (cost) | **1.0%** | 35.5% (DemoSolver)\* | **$3,195.45** | $3,195.62 |

\* DASTRODF crashes on 8 of 10 runs of this problem, so the comparison uses the organizers' simpler demo method.

### How to read the columns

- **Gap** (our gap, baseline gap) is how much of the possible improvement was still missing, averaged over the whole search from the first simulation run to the last. It measures **how fast** a method finds good plans. This is the competition score, and **lower is better**.
- **Final result** is the quality of the last plan the method chose after using its whole budget. To avoid lucky results, that plan was re-tested on fresh simulation runs. It measures **where the method ended up**, in the problem's own units.

### What each result means

**Driver scheduling, standard.** This is the competition problem with its default settings. The score is the share of calls answered right away minus 0.00005 × the daily wage bill, and higher is better. The starting schedule scores 0.643 and the best schedule we have found scores about 0.80.
- CRNLS ends at **0.796**, capturing about **96%** of the possible improvement. The baseline ends at 0.781, about 87%.
- Averaged over the whole search, CRNLS was missing **12.6%** of the improvement and the baseline 27.7%. CRNLS finds good schedules much sooner: after only 100 of the 1,000 runs, it has already closed about three-quarters of the gap.

**Driver scheduling, high demand.** Same problem, with about 50% more calls (18 car and 10 truck calls per hour instead of 12 and 7). This checks that the method still works when the center is busier and needs more drivers.
- CRNLS ends at **0.754** and the baseline at 0.738. Scores are lower than in the standard case because the extra calls need more paid drivers.
- CRNLS's gap is **9.2%** against 21.2%, less than half the baseline's.

**Driver scheduling, cost matters more.** The wage penalty is doubled (0.0001 per dollar instead of 0.00005). This is the kind of change the judges warn they may make to the score. The best plan now uses fewer drivers.
- CRNLS ends at **0.633** and the baseline at 0.605. Scores are lower overall because each dollar of wages costs twice as much.
- CRNLS's gap is **15.0%** against 31.3%. This is the hardest of the four versions for both methods, and CRNLS still halves the baseline's gap.

**Driver scheduling, service matters more.** The wage penalty is reduced (0.00002 per dollar), so answering calls right away matters most. The best plan now uses more drivers.
- CRNLS ends at **0.905** and the baseline at 0.899. Scores are higher because wages cost less in score points.
- CRNLS's gap is **6.8%** against 17.1%.

**Hotel.** A standard SimOpt problem: choose how many rooms to sell at each price and length of stay (56 numbers) to maximize revenue. Only **100** simulation runs are allowed, a tenth of the driver problem's budget, so speed is everything. The starting plan sells no rooms ($0) and the best known plan earns about $53,053.
- CRNLS ends at **$52,841**, about **99.6%** of the best. The baseline ends at $51,949, about 97.9%.
- CRNLS's gap is **2.8%** against 8.6%: it reaches high revenue within its first few runs.

**Example.** A simple test puzzle with a known correct answer, (1, 2, 3, 4). The score is how far the plan is from that answer, plus random noise, and lower is better. It checks that the method can find an exact answer through noise.
- CRNLS found the **exact correct answer in every run**. The baseline found it in most runs but stopped one step away in about one run in ten.
- CRNLS's gap is **0.6%** against 1.7%.

**Dual sourcing.** A standard SimOpt inventory problem: choose stock levels for a cheap, slow supplier and a costly, fast supplier (2 numbers) to minimize the total daily cost of ordering, storage and shortages. Lower is better. The starting plan costs about $3,302 a day and the best known costs about $3,195.
- CRNLS ends at **$3,195.45**, essentially the best. The demo method ends at $3,195.62, almost as good.
- The gap shows the real difference: **1.0%** for CRNLS against 35.5% for the demo method. Both reach about the same cost, but CRNLS gets there almost immediately, while the demo method spends 10 simulation runs on every plan it tries and arrives much later.
- The official baseline, DASTRODF, **crashes on 8 of 10 runs** of this problem, so it has no result. This problem has no upper limit on the choices, which DASTRODF doesn't handle correctly.

**Overall.** CRNLS has the lower gap on every problem, usually by half or more, and the better or equal final result on every problem. It completed every test run without errors.

### Limits

- The results come from our own test runs. The judges will use hidden problems, so final scores will differ.
- The best known values are the best found by any method in our tests, not proven optimal answers.
- In the driver problem, the last 1–2% of improvement is hard to separate from random noise, so we don't expect large further gains there.

---

## Conclusion

### Starting point: the baseline

The organizers supplied DASTRODF as the reference solver. It is a model-based trust-region method: it fits a quadratic approximation of the objective from previously simulated solutions, uses it to choose candidate solutions, and compares them to the incumbent using independent sample means. In our evaluation it showed three limitations:

1. **Slow early progress.** In high dimensions (72 variables), the fitted model is unreliable until many solutions have been simulated, so much of the early budget is spent on poor candidates. The competition metric weights early performance heavily.
2. **Noisy comparisons.** Candidates and the incumbent are simulated under different random conditions, so differences in performance are hidden by simulation noise and several replications are needed per comparison.
3. **Lack of robustness.** It artificially restricts variables that have no upper limit and fails with an error on 8 of 10 runs of the dual-sourcing problem.

### Our improvement: CRNLS

We developed CRNLS (Common Random Numbers Local Search), which addresses each limitation directly:

1. **Paired comparisons with common random numbers** replace independent comparisons. Every solution is evaluated under identical random conditions, so most of the noise cancels and a single replication is usually enough to rank two solutions. This allows many more solutions to be evaluated within the same budget.
2. **Direct, adaptive search** replaces the fitted model. Moves are ranked by their past success, step sizes grow and shrink with experience, and successful moves are combined into larger jumps. The search therefore makes rapid progress from the first replications instead of waiting for a model to become accurate.
3. **Sample sizes that grow only when needed.** Additional replications are spent only when a solution appears locally optimal, which guards against accepting solutions that looked good by chance.
4. **Robust handling of problem structure.** Variables with no upper limit, wide ranges and flat regions are handled without artificial restrictions, and the solver has safeguards against endless loops.

The method was developed over eight tested versions. Every change and its measured effect is recorded in [results-log.md](results-log.md).

### Results: the improvement achieved

The table below summarizes the improvement over the baseline. The **gap reduction** is the relative decrease in the competition metric (the average optimality gap), where higher means a larger improvement.

| Problem | Baseline gap | CRNLS gap | Gap reduction | Final result: baseline → CRNLS |
|---|---|---|---|---|
| Driver scheduling, standard | 27.7% | 12.6% | **55%** | 0.781 → **0.796** |
| Driver scheduling, high demand | 21.2% | 9.2% | **57%** | 0.738 → **0.754** |
| Driver scheduling, cost matters more | 31.3% | 15.0% | **52%** | 0.605 → **0.633** |
| Driver scheduling, service matters more | 17.1% | 6.8% | **60%** | 0.899 → **0.905** |
| Hotel | 8.6% | 2.8% | **67%** | $51,949 → **$52,841** |
| Example | 1.7% | 0.6% | **65%** | missed on some runs → **exact answer every run** |
| Dual sourcing | 35.5%\* | 1.0% | **97%** | $3,195.62 → **$3,195.45** |

\* DASTRODF fails on this problem, so the comparison uses the organizers' DemoSolver.

The results support four conclusions:

1. **CRNLS more than halves the competition metric on the main problem.** Across all four versions of driver scheduling, the average optimality gap falls by 52–60% compared with the baseline. The improvement holds whether demand is higher or the score weights cost or service differently, which indicates it isn't tied to one specific objective.
2. **CRNLS reaches better final solutions.** On standard driver scheduling it captures about 96% of the possible improvement over the starting schedule, against about 87% for the baseline. It is also better at the end of the budget on every other problem.
3. **The improvement generalizes.** On three unrelated problems (hotel revenue management, inventory ordering and a test function), CRNLS reduces the gap by 65–97%, without any problem-specific tuning. This is the most important property for a competition judged on hidden problems.
4. **CRNLS is more reliable.** It completed every test run, including the problem on which the baseline fails.

Overall, replacing model-based search with noise-cancelling paired comparisons and adaptive local search produces a solver that is **faster, more accurate and more robust** than the supplied baseline. Further refinements (CRNLS 1.2) gave no measurable additional gain, which suggests the current method is close to the best this approach can achieve on the main problem.