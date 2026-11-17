"""Figure 1 of the README: the three factors, what they do to three positions, and the forecast test.

Usage: python figures/make_figure1.py   (writes figures/figure1.png)
Inputs: reports/part_a_components.csv, part_a_scenarios.csv, part_b_primary.csv, part_b_monthly.csv
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
INK, AXIS, GREY, SHADE = "#111111", "#333333", "#6e6e6e", "#f8f5f1"
FACTOR = {"level": "#0072B2", "slope": "#D55E00", "curvature": "#009E73"}
POSITION = {"5-year bullet": "#0072B2", "2-10 barbell": "#56B4E9", "2-5-10 butterfly": "#009E73"}
FIRST = 120                                              # position of the first forecast in the butterfly series


def label(ax, letter, text, x=-0.16):
    ax.text(x, 1.06, letter, transform=ax.transAxes, fontsize=8, fontweight="bold", va="baseline")
    ax.text(x + 0.06, 1.06, text, transform=ax.transAxes, fontsize=7.5, va="baseline")


def main():
    plt.rcParams.update({
        "font.family": ["Arial", "Helvetica Neue", "DejaVu Sans"], "font.size": 7, "axes.labelsize": 7,
        "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "text.color": INK, "axes.labelcolor": INK,
        "axes.edgecolor": AXIS, "xtick.color": AXIS, "ytick.color": AXIS, "axes.linewidth": 0.5,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.major.size": 2.2, "ytick.major.size": 2.2,
        "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "white",
        "savefig.facecolor": "white"})
    comp = pd.read_csv(REP / "part_a_components.csv")
    share = comp[comp.maturity == "variance_share"].iloc[0]
    load = comp[comp.maturity != "variance_share"].astype(float)
    scen = pd.read_csv(REP / "part_a_scenarios.csv").set_index("position")
    prim = pd.read_csv(REP / "part_b_primary.csv")
    monthly = pd.read_csv(REP / "part_b_monthly.csv").iloc[FIRST:]

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), gridspec_kw={"wspace": 0.62, "hspace": 0.55})
    a, b, c, d = axes.ravel()

    for name, col in FACTOR.items():
        a.plot(load.maturity, load[name], "-o", color=col, lw=1.2, ms=3.2, mfc="white", mew=1.0)
        a.text(10.3, load[name].iloc[-1], f"{name.capitalize()} ({float(share[name]):.1%})", va="center", fontsize=6.5)
    a.axhline(0, color=AXIS, lw=0.5)
    a.set_xticks(range(1, 11)); a.set_xlim(0.6, 14.2); a.spines["bottom"].set_bounds(1, 10)
    a.set_xlabel("Maturity (years)", x=0.36); a.set_ylabel("Loading on the monthly yield change")
    label(a, "a", "Three factors, and their share of variance")

    shocks = ["level +1 sd", "slope +1 sd", "curvature +1 sd"]
    for i, (pos, col) in enumerate(POSITION.items()):
        ys = np.arange(len(shocks)) + (i - 1) * 0.25
        b.barh(ys, scen.loc[pos, shocks], height=0.21, color=col, lw=0)
        for yv, v in zip(ys, scen.loc[pos, shocks]):
            b.text(v - 0.04 if v < 0 else v + 0.04, yv, ("0.00" if abs(v) < 0.005 else f"{v:+.2f}".replace("-", "\u2212")), va="center", ha="right" if v < 0 else "left",
                   fontsize=6)
        b.plot([], [], "s", color=col, ms=4, label=pos)
    b.axvline(0, color=AXIS, lw=0.5)
    b.set_yticks(range(len(shocks))); b.set_yticklabels(["Level", "Slope", "Curvature"]); b.invert_yaxis()
    b.tick_params(axis="y", length=0); b.spines["left"].set_visible(False)
    b.set_xlim(-2.15, 0.75)
    b.set_xlabel("Profit or loss per 100 of 5-year notional,\none-standard-deviation monthly move")
    b.legend(frameon=False, fontsize=6.3, loc="lower left", handletextpad=0.2, borderaxespad=0.0,
             bbox_to_anchor=(0.0, 0.0))
    label(b, "b", "What each factor does to three positions", x=-0.22)

    gain = np.cumsum((monthly.butterfly_rx - monthly.benchmark) ** 2 - (monthly.butterfly_rx - monthly.forecast) ** 2)
    total = np.sum((monthly.butterfly_rx - monthly.benchmark) ** 2)
    x = pd.PeriodIndex(monthly.month, freq="M").to_timestamp()
    c.fill_between(x, 0, gain / total * 100, where=gain <= 0, color=SHADE, lw=0, interpolate=True)
    c.plot(x, gain / total * 100, color=FACTOR["curvature"], lw=1.1)
    c.axhline(0, color=AXIS, lw=0.5)
    c.set_ylabel("Cumulative gain over the historical mean\n(% of its squared error)")
    c.text(0.03, 0.06, "below zero: the carry forecast\nis worse than the mean", transform=c.transAxes, fontsize=6.3,
           color=GREY, va="bottom")
    label(c, "c", "Butterfly: forecast from carry and roll-down", x=-0.22)

    items = [("primary", "Butterfly, all months"), ("through 2008-12", "  through 2008"),
             ("after 2008-12", "  after 2008"), ("placebo: predictor lagged 12 months", "Placebo: carry lagged 12 m"),
             ("reference: 5-year bullet on 10y-1y slope", "Reference: 5-year on slope")]
    main_rows = prim[prim.block == 12].set_index("item")
    d.axvspan(-8, 0, color=SHADE, lw=0, zorder=0)
    for i, (key, lab) in enumerate(items):
        r = main_rows.loc[key] * 1
        col = FACTOR["level"] if key.startswith("reference") else (GREY if key.startswith("placebo") else FACTOR["curvature"])
        d.plot([r.ci_low * 100, r.ci_high * 100], [i, i], color=col, lw=1.3, solid_capstyle="round")
        d.plot(r.oos_r2 * 100, i, "o", ms=4, color=col, mfc="white" if i in (1, 2) else col, mew=1.0)
    d.axvline(0, color=AXIS, lw=0.5)
    d.set_yticks(range(len(items))); d.set_yticklabels([lab for _, lab in items]); d.invert_yaxis()
    d.tick_params(axis="y", length=0); d.spines["left"].set_visible(False)
    d.set_xlim(-8, 5); d.set_xlabel("Out-of-sample R² (%), 95% interval")
    label(d, "d", "Out-of-sample test of the carry forecast", x=-0.5)

    fig.savefig(ROOT / "figures" / "figure1.png", dpi=300, bbox_inches="tight")


if __name__ == "__main__":
    main()
