"""The numbers quoted in the README, checked against the files in reports/."""
from pathlib import Path

import pandas as pd

REP = Path(__file__).resolve().parents[1] / "reports"


def close(value, quoted, tol):
    return abs(value - quoted) <= tol


def test_part_a_numbers():
    comp = pd.read_csv(REP / "part_a_components.csv").set_index("maturity")
    share = comp.loc["variance_share"]
    assert close(share.level, 0.917, 5e-4) and close(share.slope, 0.073, 5e-4) and close(share.curvature, 0.009, 5e-4)
    assert close(share.sum(), 0.999, 5e-4)
    for m, lev, slo, cur in (("2", 0.36, -0.37, 0.16), ("5", 0.32, 0.11, 0.28), ("10", 0.27, 0.34, -0.41)):
        row = comp.loc[m]
        assert close(row.level, lev, 5e-3) and close(row.slope, slo, 5e-3) and close(row.curvature, cur, 5e-3)
    stab = pd.read_csv(REP / "part_a_stability.csv")
    lev = stab[stab.component == "level"]
    assert len(lev) == 8 and 0.295 <= lev.m5.min() and lev.m5.max() <= 0.325
    first = stab[stab.window_end == "1991-08"].set_index("component").variance_share
    assert close(first.level, 0.937, 5e-4) and close(first.slope, 0.055, 5e-4) and close(first.curvature, 0.006, 5e-4)
    scen = pd.read_csv(REP / "part_a_scenarios.csv").set_index("position")
    quoted = {"5-year bullet": (-1.69, -0.16, -0.15, -1.23), "2-10 barbell": (-1.56, -0.26, 0.15, -1.23),
              "2-5-10 butterfly": (0.0, 0.0, -0.27, 0.06)}
    for pos, vals in quoted.items():
        got = scen.loc[pos, ["level +1 sd", "slope +1 sd", "curvature +1 sd", "parallel +25 bp"]]
        assert all(close(g, q, 5e-3) for g, q in zip(got, vals)), pos
    assert close(scen.loc["2-5-10 butterfly", "w_2y"], -91.6, 0.05) and close(scen.loc["2-5-10 butterfly", "w_10y"], -34.4, 0.05)
    assert close(scen.loc["2-10 barbell", "w_2y"], 62.5, 0.05)
    pos = pd.read_csv(REP / "part_a_positions.csv").set_index("position")
    assert close(pos.loc["5-year bullet", "annual_vol"], 6.0, 0.05) and close(pos.loc["2-10 barbell", "annual_vol"], 5.6, 0.05)
    assert close(pos.loc["2-5-10 butterfly", "annual_vol"], 1.1, 0.05)
    assert close(pos.loc["5-year bullet", "share_level"], 0.97, 5e-3)
    assert close(pos.loc["2-5-10 butterfly", "share_curvature"], 0.74, 5e-3)
    assert close(pos.loc["2-5-10 butterfly", "share_unexplained"], 0.26, 5e-3)


def test_part_b_numbers():
    prim = pd.read_csv(REP / "part_b_primary.csv")
    quoted = {("primary", 12): (-2.6, -5.6, 0.6, 421), ("primary", 6): (-2.6, -6.4, 1.4, 421),
              ("primary", 24): (-2.6, -4.9, -0.2, 421), ("sign-restricted slope", 12): (-2.6, -5.6, 0.6, 421),
              ("through 2008-12", 12): (-2.3, -7.0, 2.6, 209), ("after 2008-12", 12): (-3.0, -6.7, 0.2, 212),
              ("placebo: predictor lagged 12 months", 12): (-1.4, -3.2, -0.0, 421),
              ("reference: 5-year bullet on 10y-1y slope", 12): (1.5, -0.9, 3.7, 421)}
    for (item, block), (r2, lo, hi, n) in quoted.items():
        row = prim[(prim.item == item) & (prim.block == block)].iloc[0]
        assert close(row.oos_r2 * 100, r2, 0.051) and close(row.ci_low * 100, lo, 0.051) and close(row.ci_high * 100, hi, 0.051)
        assert row.months == n
    ins = pd.read_csv(REP / "part_b_insample.csv")
    assert close(ins.slope[0], 0.40, 5e-3) and close(ins.t_nw[0], 1.0, 0.05) and close(ins.r2[0], 0.002, 5e-4)
    assert ins.months[0] == 541 and close(ins.t_nw[1], 2.6, 0.05)
    strat = pd.read_csv(REP / "part_b_strategies.csv").set_index("strategy")
    quoted = {"timing rule, before costs": (0.21, -0.01, 0.42), "timing rule, cost scenario": (0.12, -0.12, 0.34),
              "butterfly, always long": (0.15, -0.09, 0.39), "carry sort across 1-10 years": (0.04, -0.29, 0.42)}
    for name, (s, lo, hi) in quoted.items():
        row = strat.loc[name]
        assert close(row.sharpe, s, 6e-3) and close(row.ci_low, lo, 6e-3) and close(row.ci_high, hi, 6e-3), name
    assert strat.loc["carry sort across 1-10 years", "months"] == 661
    sig = pd.read_csv(REP / "part_b_signal.csv").iloc[0]
    assert close(sig.carry_sd * 1e4, 0.7, 0.05) and close(sig.return_sd * 1e4, 6.2, 0.05)
    assert close(sig.r2_ceiling_if_carry_were_the_expected_return, 0.013, 5e-4) and close(sig.carry_autocorrelation, 0.88, 5e-3)
    monthly = pd.read_csv(REP / "part_b_monthly.csv").iloc[120:]
    gain = ((monthly.butterfly_rx - monthly.benchmark) ** 2 - (monthly.butterfly_rx - monthly.forecast) ** 2).cumsum()
    years = pd.PeriodIndex(monthly.month, freq="M").year
    above = monthly.month[(gain >= 0).to_numpy() & (years >= 1993)]
    assert list(above) == ["2008-09"]
