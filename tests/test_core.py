from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tcurve import core, evaluate as ev  # noqa: E402

HAVE_DATA = (ROOT / "data" / "raw" / "gsw" / "feds200628.csv").exists()


def months(n):
    return pd.period_range("2000-01", periods=n, freq="M")


def test_svensson_limits():
    assert np.isclose(core.svensson(1e-8, 4.0, -1.0, 0.5, 0.3, 1.5, 8.0), 3.0, atol=1e-6)   # beta0 + beta1
    assert np.isclose(core.svensson(1e6, 4.0, -1.0, 0.5, 0.3, 1.5, 8.0), 4.0, atol=1e-4)    # beta0
    flat = core.svensson(np.array([1.0, 5.0, 10.0]), 4.0, 0.0, 0.0, 0.0, 1.5, -999.99)
    assert np.allclose(flat, 4.0)


def test_unchanged_curve_return_equals_carry():
    idx = months(6)
    n = core.MATURITIES
    y_full = pd.DataFrame(np.tile(0.02 + 0.002 * n, (6, 1)), index=idx, columns=n)
    y_short = pd.DataFrame(np.tile(0.02 + 0.002 * (n - core.H), (6, 1)), index=idx, columns=n)
    rf = pd.Series(0.001, index=idx)
    rx, carry = core.returns_and_carry(y_full, y_short, rf)
    assert np.allclose(rx.iloc[:-1], carry.iloc[:-1])
    assert (carry.iloc[0] > 0).all() and rx.iloc[-1].isna().all()


def test_parallel_shift_return():
    idx = months(2)
    n = core.MATURITIES
    y_full = pd.DataFrame([np.full(10, 0.03), np.full(10, 0.04)], index=idx, columns=n)
    rx, _ = core.returns_and_carry(y_full, y_full.copy(), pd.Series(0.0, index=idx))
    assert np.allclose(rx.iloc[0], 0.03 * n - 0.04 * (n - core.H))


def test_carry_uses_only_current_month():
    idx = months(5)
    n = core.MATURITIES
    rng = np.random.default_rng(0)
    y = pd.DataFrame(0.03 + 0.01 * rng.standard_normal((5, 10)), index=idx, columns=n)
    rf = pd.Series(0.002, index=idx)
    _, carry = core.returns_and_carry(y, y, rf)
    later = y.copy()
    later.iloc[3:] += 0.5
    _, carry_later = core.returns_and_carry(later, later, rf.where(rf.index < idx[3], 0.9))
    assert np.allclose(carry.iloc[:3], carry_later.iloc[:3])


def test_butterfly_has_no_level_or_slope_exposure():
    rng = np.random.default_rng(1)
    n = core.MATURITIES
    level, slope, curv = np.ones(10), (n - 5.5) / 4.5, -((n - 5.5) / 4.5) ** 2 + 0.4
    scores = rng.standard_normal((400, 3)) * np.array([0.003, 0.001, 0.0004])
    changes = pd.DataFrame(scores @ np.vstack([level, slope, curv]), columns=n)
    load, share = core.principal_components(changes)
    w = core.butterfly_weights(load)
    idx = [1, 4, 9]
    dur = np.array(core.LEGS) - core.H
    assert np.isclose(w[1] * dur[1], 1.0) and w[0] < 0 and w[2] < 0
    for k in (0, 1):
        assert abs((w * dur) @ load[idx, k]) < 1e-10
    assert abs((w * dur) @ load[idx, 2]) > 1e-3 and share[:3].sum() > 0.999
    assert load[:, 0].sum() > 0 and load[-1, 1] > load[0, 1]


def test_expanding_weights_ignore_the_future():
    rng = np.random.default_rng(2)
    y = pd.DataFrame(0.04 + np.cumsum(0.001 * rng.standard_normal((200, 10)), axis=0), index=months(200),
                     columns=core.MATURITIES)
    later = y.copy()
    later.iloc[150:] += rng.standard_normal((50, 10)) * 0.02
    a, b = core.expanding_butterfly(y, first=120), core.expanding_butterfly(later, first=120)
    assert np.allclose(a.iloc[:29], b.iloc[:29]) and not np.allclose(a.iloc[40:], b.iloc[40:])
    assert a.index[0] == y.index[120]


def test_forecast_uses_only_the_past_and_r2_is_zero_for_the_benchmark():
    rng = np.random.default_rng(3)
    x = rng.standard_normal(300)
    y = 0.5 * x + rng.standard_normal(300)
    model, bench = ev.expanding_forecast(y, x, 100)
    y2 = y.copy()
    y2[200:] += 10
    model2, bench2 = ev.expanding_forecast(y2, x, 100)
    assert np.allclose(model[100:201], model2[100:201]) and np.allclose(bench[100:201], bench2[100:201])
    assert np.isnan(model[:100]).all()
    assert ev.oos_r2(y[100:], bench[100:], bench[100:]) == 0
    assert ev.oos_r2(y[100:], model[100:], bench[100:]) > 0.1
    noise = rng.standard_normal(300)
    restricted, _ = ev.expanding_forecast(-0.5 * x + noise, x, 100, sign_restricted=True)
    _, bench3 = ev.expanding_forecast(-0.5 * x + noise, x, 100)
    assert np.allclose(restricted[100:], bench3[100:])


def test_bootstrap_and_newey_west():
    idx = ev.bootstrap_indices(50, 8, draws=20)
    assert idx.shape == (20, 50) and idx.min() >= 0 and idx.max() < 50
    rng = np.random.default_rng(4)
    x = rng.standard_normal(500)
    out = ev.ols_newey_west(2.0 * x + rng.standard_normal(500), x)
    assert abs(out["slope"] - 2.0) < 0.15 and out["t_nw"] > 10
    assert np.isclose(ev.max_drawdown(np.log([1.1, 0.5, 1.0])), -0.5)


@pytest.mark.skipif(not HAVE_DATA, reason="yield file not downloaded")
def test_formula_reproduces_published_yields():
    raw = core.load_gsw()
    cols = [f"SVENY{n:02d}" for n in core.MATURITIES]
    sub = raw.dropna(subset=core.PARAMS[:3] + ["TAU1"] + cols).iloc[::50]
    rebuilt = np.vstack([core.svensson(core.MATURITIES, *row) for row in sub[core.PARAMS].to_numpy()])
    assert np.abs(rebuilt - sub[cols].to_numpy()).max() < 1e-3
    monthly = core.month_end(raw)
    assert monthly.index.is_unique and monthly.index.is_monotonic_increasing
    rf = core.load_rf()
    assert rf.index[0] == pd.Period("1926-07", "M") and -0.001 < rf.min() and rf.max() < 0.02
