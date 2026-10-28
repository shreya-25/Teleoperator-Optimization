"""Usage: uv run python scripts/plot_progress.py curves_dir out.png

Draws mean normalized optimality-gap curves (with a +/- 1 standard error band)
from the .npz files written by benchmark.py with BENCH_CURVES set.
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

PANELS = [
    ("teleops", "Driver scheduling (TELEOPS-1)", "DASTRODF"),
    ("hotel", "Hotel revenue (HOTEL-1)", "DASTRODF"),
    ("dualsourcing", "Dual sourcing (DUALSOURCING-1)", "DemoSolver"),
    ("example2", "Example (EXAMPLE-2)", "DASTRODF"),
]
COLORS = {"CRNLS": "#2a78d6", "baseline": "#eb6834"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"

src, out = Path(sys.argv[1]), sys.argv[2]
fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), facecolor="#fcfcfb")
for ax, (key, title, base) in zip(axes.flat, PANELS):
    data = np.load(src / f"{key}.npz")
    ax.set_facecolor("#fcfcfb")
    for name, color in (("CRNLS", COLORS["CRNLS"]), (base, COLORS["baseline"])):
        curves = data[name]
        mean = curves.mean(axis=0)
        se = curves.std(axis=0, ddof=1) / np.sqrt(len(curves))
        budget = np.arange(len(mean))
        ax.fill_between(budget, mean - se, mean + se, color=color, alpha=0.18, lw=0)
        ax.plot(budget, mean, color=color, lw=2,
                label=f"{name} (score {mean.mean():.3f})")
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.set_ylim(0, 1.02)
    ax.set_xlim(0, len(mean) - 1)
    ax.set_xlabel("Simulation runs used", color=MUTED, fontsize=9)
    ax.set_ylabel("Gap (share of improvement missing)", color=MUTED, fontsize=9)
    ax.grid(color=GRID, lw=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
fig.suptitle("Progress curves: mean gap over the budget (lower is better; score = average gap)",
             color=INK, fontsize=12, x=0.01, ha="left")
fig.tight_layout()
fig.savefig(out, dpi=200, facecolor=fig.get_facecolor())
