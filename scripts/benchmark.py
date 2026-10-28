"""Usage: uv run python scripts/benchmark.py problem n_mreps n_post solvers [overrides_json]

Solvers are comma-separated; settings follow a colon, joined by "+", for example
"CRNLS,CRNLS12:patience_fraction=0.5+sample_growth=3".

Reports the area under the normalized optimality-gap curve (the competition
metric, lower is better): gap(b) = (f* - f(x_b)) / (f* - f(x0)), where f* is the
best post-replicated value found by any solver on any macroreplication.
"""
import json, os, sys
import numpy as np
from joblib import Parallel, delayed
from mrg32k3a.mrg32k3a import MRG32k3a
from simopt.experiment.run_solver import _run_mrep
from simopt.models.dualsourcing import DualSourcingMinCost
from simopt.models.example import Example2Problem
from simopt.models.hotel import HotelRevenue
from simopt.problem import Solution
from simopt_competition_26 import DASTRODF, DemoSolver
from simopt_competition_26.crnls import CRNLS
from simopt_competition_26.crnls12 import CRNLS12
from simopt_competition_26.teleops import TeleopsProblem

PROBLEMS = {"teleops": TeleopsProblem, "dualsourcing": DualSourcingMinCost,
            "hotel": HotelRevenue, "example2": Example2Problem}
from simopt.solvers.randomsearch import RandomSearch
SOLVERS = {"RNDSRCH": RandomSearch, "DASTRODF": DASTRODF, "DemoSolver": DemoSolver, "CRNLS": CRNLS, "CRNLS12": CRNLS12}
pname, n_mreps, n_post = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
names = sys.argv[4].split(",")
over = json.loads(sys.argv[5]) if len(sys.argv) > 5 else {}

def make_problem():
    return PROBLEMS[pname](fixed_factors=over.get("problem") or None,
                           model_fixed_factors=over.get("model") or None)

def make_solver(spec):
    name, _, params = spec.partition(":")
    factors = {}
    for item in filter(None, params.split("+")):
        key, value = item.split("=")
        factors[key] = json.loads(value)
    return SOLVERS[name](fixed_factors=factors)

def run(name, mrep):
    df, t = _run_mrep(make_solver(name), make_problem(), mrep)
    return name, mrep, [(int(b), tuple(int(v) for v in s)) for b, s in zip(df["budget"], df["solution"])], t

def true_val(x):
    p = make_problem()
    s = Solution(x, [MRG32k3a(s_ss_sss_index=[0, i, 0]) for i in range(p.model.n_rngs)])
    p.simulate(s, n_post)
    return float(np.mean(s.objectives[:, 0])) * p.minmax[0]  # higher is better

jobs = Parallel(n_jobs=-1)(delayed(run)(n, m) for n in names for m in range(n_mreps))
x0 = tuple(int(v) for v in make_problem().factors["initial_solution"])
xs = sorted({x for _, _, h, _ in jobs for _, x in h} | {x0})
vals = dict(zip(xs, Parallel(n_jobs=-1)(delayed(true_val)(x) for x in xs)))
B = make_problem().factors["budget"]
grid = np.arange(0, B + 1)
f0, fstar = vals[x0], max(vals.values())
print(f"[{pname} {json.dumps(over)}] budget={B} f(x0)={f0:.4f} f*={fstar:.4f}")
curves_out = {}
for name in names:
    gaps, finals, times, gap_curves = [], [], [], []
    for n, m, h, t in jobs:
        if n != name: continue
        bud = np.array([b for b, _ in h]); v = np.array([vals[x] for _, x in h])
        curve = v[np.searchsorted(bud, grid, side="right") - 1]
        gap = (fstar - curve) / (fstar - f0) if fstar > f0 else np.zeros_like(curve)
        gaps.append(gap.mean()); finals.append(curve[-1]); times.append(t); gap_curves.append(gap)
    se = lambda a: np.std(a, ddof=1) / np.sqrt(len(a))
    print(f"  {name:30s} normGapArea={np.mean(gaps):.3f}±{se(gaps):.3f} "
          f"final={np.mean(finals):.4f}±{se(finals):.4f} time={np.mean(times):.0f}s", flush=True)
    curves_out[name] = np.array(gap_curves)
    if os.environ.get("BENCH_DETAIL"):
        g = np.mean(gap_curves, axis=0)
        marks = [b for b in (25, 50, 100, 200, 400, 700) if b < B] + [B]
        print("      mean gap at budget " + " ".join(f"{b}:{g[b]:.3f}" for b in marks))
        print("      gap area per macroreplication " + " ".join(f"{a:.3f}" for a in gaps))
if os.environ.get("BENCH_CURVES"):
    np.savez(os.environ["BENCH_CURVES"], **curves_out)
