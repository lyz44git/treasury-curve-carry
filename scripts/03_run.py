"""Parts A and B of design/plan.md.

Outputs (reports/):
  part_a_components.csv      loadings and variance shares, full sample
  part_a_stability.csv       expanding-window loadings every five years
  part_a_scenarios.csv       profit or loss of bullet, barbell and butterfly under factor shocks
  part_a_positions.csv       volatility of each position and the share explained by each component
  part_b_primary.csv         out-of-sample R-squared with intervals (primary, blocks, restricted, sub-periods,
                             placebo, level-on-slope reference)
  part_b_insample.csv        in-sample regressions with Newey-West errors
  part_b_strategies.csv      timing rule (before and after the cost scenario) and the carry sort
  part_b_signal.csv          size and persistence of the predictor against the return (descriptive)
  part_b_monthly.csv         monthly series behind the above
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tcurve import core, evaluate as ev  # noqa: E402

OUT = ROOT / "reports"
FIRST_PCA, FIRST_FORECAST = 120, 240          # months from the start of the sample
COST_PER_DURATION = 0.5e-4                    # assumed scenario: 0.5 bp of yield per unit of duration traded
NOTIONAL = 100.0


def build():
    raw = core.load_gsw()
    rf = core.load_rf()
    monthly = core.month_end(raw)
    start = monthly["SVENY10"].first_valid_index()
    monthly = monthly.loc[start:rf.index[-1]]
    y_full = core.yields_at(monthly, core.MATURITIES)
    y_short = core.yields_at(monthly, core.MATURITIES - core.H)
    y_short.columns = y_full.columns
    rx, carry = core.returns_and_carry(y_full, y_short, rf)
    return y_full, rx.iloc[:-1], carry.iloc[:-1]


def part_a(y_full, rx):
    changes = y_full.diff().dropna()
    load, share = core.principal_components(changes)
    names = ["level", "slope", "curvature"]
    comp = pd.DataFrame(load[:, :3], index=core.MATURITIES, columns=names).rename_axis("maturity").reset_index()
    comp = pd.concat([comp, pd.DataFrame([{"maturity": "variance_share", **dict(zip(names, share[:3]))}])])
    comp.to_csv(OUT / "part_a_components.csv", index=False)

    rows = []
    for end in range(FIRST_FORECAST, len(changes) + 1, 60):
        sub, sub_share = core.principal_components(changes.iloc[:end])
        for k, name in enumerate(names):
            rows.append({"window_end": str(changes.index[end - 1]), "component": name,
                         "variance_share": sub_share[k], **{f"m{n}": sub[i, k] for i, n in enumerate(core.MATURITIES)}})
    pd.DataFrame(rows).to_csv(OUT / "part_a_stability.csv", index=False)

    dur = core.MATURITIES - core.H
    d2, d5, d10 = (dur[core.MATURITIES == n][0] for n in core.LEGS)
    w10_bar = NOTIONAL * (d5 - d2) / (d10 - d2)
    positions = {
        "5-year bullet": {5: NOTIONAL},
        "2-10 barbell": {2: NOTIONAL - w10_bar, 10: w10_bar},
        "2-5-10 butterfly": dict(zip(core.LEGS, core.butterfly_weights(load) * NOTIONAL * d5)),
    }
    scores = (changes.to_numpy() - changes.to_numpy().mean(axis=0)) @ load[:, :3]
    shocks = {f"{name} +1 sd": load[:, k] * scores[:, k].std(ddof=1) for k, name in enumerate(names)}
    shocks["parallel +25 bp"] = np.full(len(dur), 0.0025)
    scen, pos_rows = [], []
    aligned = rx.loc[changes.index[0]:]
    score_frame = pd.DataFrame(scores, index=changes.index, columns=names).shift(-1).loc[aligned.index].dropna()
    for label, weights in positions.items():
        w = np.array([weights.get(n, 0.0) for n in core.MATURITIES])
        scen.append({"position": label, **{f"w_{n}y": weights.get(n, 0.0) for n in core.LEGS},
                     **{s: float(-(w * dur) @ dy) for s, dy in shocks.items()}})
        ret = (aligned.loc[score_frame.index].to_numpy() @ w)
        X = np.column_stack([np.ones(len(ret)), score_frame.to_numpy()])
        beta = np.linalg.lstsq(X, ret, rcond=None)[0]
        explained = {name: float(beta[k + 1] ** 2 * score_frame[name].var(ddof=0) / ret.var()) for k, name in enumerate(names)}
        pos_rows.append({"position": label, "monthly_vol": float(ret.std(ddof=1)),
                         "annual_vol": float(ret.std(ddof=1) * np.sqrt(12)), **{f"share_{k}": v for k, v in explained.items()},
                         "share_unexplained": 1 - sum(explained.values())})
    pd.DataFrame(scen).to_csv(OUT / "part_a_scenarios.csv", index=False)
    pd.DataFrame(pos_rows).to_csv(OUT / "part_a_positions.csv", index=False)


def part_b(y_full, rx, carry):
    weights = core.expanding_butterfly(y_full, first=FIRST_PCA).reindex(rx.index).dropna()
    legs = list(core.LEGS)
    target = (weights * rx.loc[weights.index, legs]).sum(axis=1)
    predictor = (weights * carry.loc[weights.index, legs]).sum(axis=1)
    first = FIRST_FORECAST - (len(rx) - len(weights))        # position of the first forecast in this series
    y, x = target.to_numpy(), predictor.to_numpy()
    model, bench = ev.expanding_forecast(y, x, first)
    live = slice(first, None)
    months = weights.index[live]
    rows = []

    def add(label, yy, mm, bb, block=12):
        rows.append({"item": label, "block": block, **ev.r2_interval(yy, mm, bb, block)})

    add("primary", y[live], model[live], bench[live])
    for block in (6, 24):
        add("primary", y[live], model[live], bench[live], block)
    restricted, _ = ev.expanding_forecast(y, x, first, sign_restricted=True)
    add("sign-restricted slope", y[live], restricted[live], bench[live])
    yy, mm, bb = y[live], model[live], bench[live]
    pre = np.array(months <= pd.Period("2008-12", "M"))
    half = np.arange(len(yy)) < len(yy) // 2
    for label, mask in (("through 2008-12", pre), ("after 2008-12", ~pre), ("first half", half), ("second half", ~half)):
        add(label, yy[mask], mm[mask], bb[mask])
    lagged = predictor.shift(12).to_numpy()
    ok = slice(12, None)
    pm, pb = ev.expanding_forecast(y[ok], lagged[ok], first - 12)
    add("placebo: predictor lagged 12 months", y[ok][first - 12:], pm[first - 12:], pb[first - 12:])
    slope = (y_full[10] - y_full[1]).loc[rx.index].to_numpy()
    lm, lb = ev.expanding_forecast(rx[5].to_numpy(), slope, FIRST_FORECAST)
    add("reference: 5-year bullet on 10y-1y slope", rx[5].to_numpy()[FIRST_FORECAST:], lm[FIRST_FORECAST:], lb[FIRST_FORECAST:])
    pd.DataFrame(rows).to_csv(OUT / "part_b_primary.csv", index=False)

    pd.DataFrame([
        {"regression": "butterfly excess return on its carry and roll-down", **ev.ols_newey_west(y, x)},
        {"regression": "5-year excess return on 10y-1y slope", **ev.ols_newey_west(rx[5].to_numpy(), slope)},
    ]).to_csv(OUT / "part_b_insample.csv", index=False)

    side = np.sign(mm - 0.0)
    dur = np.array(legs) - core.H
    holdings = side[:, None] * weights.to_numpy()[live] * dur
    traded = np.abs(np.diff(holdings, axis=0, prepend=np.zeros((1, 3)))).sum(axis=1)
    gross = side * yy
    net = gross - COST_PER_DURATION * traded
    dur_all = core.MATURITIES - core.H
    per_dur = carry.to_numpy() / dur_all
    order = np.argsort(per_dur, axis=1)
    sort_w = np.zeros_like(per_dur)
    np.put_along_axis(sort_w, order[:, -3:], 1.0, axis=1)
    np.put_along_axis(sort_w, order[:, :3], -1.0, axis=1)
    sort_w = sort_w / (3 * dur_all)
    sort_ret = (sort_w * rx.to_numpy()).sum(axis=1)
    strat = []
    for label, series in (("timing rule, before costs", gross), ("timing rule, cost scenario", net),
                          ("butterfly, always long", yy), ("carry sort across 1-10 years", sort_ret)):
        strat.append({"strategy": label, **ev.sharpe_interval(series), "annual_return": series.mean() * 12,
                      "annual_vol": series.std(ddof=1) * np.sqrt(12), "max_drawdown": ev.max_drawdown(series)})
    strat[1]["annual_duration_traded"] = traded.mean() * 12
    strat.append({"strategy": "share of months long", "sharpe": float((side > 0).mean())})
    pd.DataFrame(strat).to_csv(OUT / "part_b_strategies.csv", index=False)

    pd.DataFrame([{"months": len(y), "carry_sd": x.std(ddof=1), "return_sd": y.std(ddof=1),
                   "r2_ceiling_if_carry_were_the_expected_return": x.var(ddof=1) / y.var(ddof=1),
                   "carry_autocorrelation": float(np.corrcoef(x[1:], x[:-1])[0, 1]),
                   "mean_carry_annual": x.mean() * 12, "mean_return_annual": y.mean() * 12}]
                 ).to_csv(OUT / "part_b_signal.csv", index=False)

    monthly = pd.DataFrame({"month": [str(m) for m in weights.index], "butterfly_rx": y, "carry": x,
                            "forecast": model, "benchmark": bench,
                            **{f"w_{n}y": weights[n].to_numpy() for n in legs}})
    monthly["carry_sort_rx"] = pd.Series(sort_ret, index=rx.index).loc[weights.index].to_numpy()
    monthly.to_csv(OUT / "part_b_monthly.csv", index=False)
    print(f"sample {rx.index[0]} to {rx.index[-1]} ({len(rx)} months); butterfly from {weights.index[0]}; "
          f"forecasts {months[0]} to {months[-1]} ({len(months)} months)")


def main():
    OUT.mkdir(exist_ok=True)
    y_full, rx, carry = build()
    part_a(y_full, rx)
    part_b(y_full, rx, carry)


if __name__ == "__main__":
    main()
