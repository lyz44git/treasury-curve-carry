"""Part C (design/forward_plan.md): the forward record, on synthetic data unless the downloads are present."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tcurve import core, evaluate as ev, forward  # noqa: E402

META = {"made_utc": "2026-12-08T13:23:00Z", "code_commit": "abc", "curve_last_date": "2026-12-04",
        "bill_last_date": "2026-12-07", "weight_revision_max": 0.0}


def monthly_series(first="2020-01", last="2027-03", seed=0):
    idx = pd.period_range(first, last, freq="M")
    rng = np.random.default_rng(seed)
    x = pd.Series(rng.normal(0, 1e-4, len(idx)), index=idx)
    y = pd.Series(0.3 * x.to_numpy() + rng.normal(0, 6e-4, len(idx)), index=idx)
    current = pd.DataFrame({"y": y, "x": x, "w_2y": -0.15, "w_5y": 0.2, "w_10y": -0.08}, index=idx)
    return y, x, current


def curve_frame(last_day="2026-12-04"):
    """Business-day Svensson parameters from August 1971 with a little noise; published yields match the formula."""
    dates = pd.bdate_range("1971-08-02", last_day)
    rng = np.random.default_rng(1)
    walk = np.cumsum(rng.normal(0, 0.01, (len(dates), 3)), axis=0)
    frame = pd.DataFrame({"BETA0": 5 + walk[:, 0], "BETA1": -1 + walk[:, 1], "BETA2": 1 + walk[:, 2],
                          "BETA3": 0.0, "TAU1": 2.0, "TAU2": np.nan}, index=dates)
    for n in core.MATURITIES:
        frame[f"SVENY{n:02d}"] = core.yields_at(frame, [n])[n].to_numpy() * 100
    return frame


def test_plan_is_the_recorded_version():
    assert forward.plan_sha256() == forward.PLAN_SHA256


def test_bill_return_uses_the_last_yield_of_the_previous_month():
    cm1 = pd.Series([3.60, 3.65, 3.70], index=pd.to_datetime(["2026-01-29", "2026-01-30", "2026-02-02"]))
    rf = forward.bill_returns(cm1)
    assert list(rf.index) == [pd.Period("2026-02", "M")]                 # February is not finished
    assert rf.iloc[0] == pytest.approx(3.65 / 100 * 28 / 365, abs=1e-15)


def test_an_unfinished_month_has_no_month_end():
    raw = curve_frame(last_day="2026-12-04")
    months = forward.month_ends(raw).index
    assert months[-1] == pd.Period("2026-11", "M") and months[0] == pd.Period("1971-08", "M")


def test_forecast_is_the_part_b_expanding_forecast():
    y, x, _ = monthly_series()
    model, bench = ev.expanding_forecast(y.to_numpy(), x.to_numpy(), first=12)
    for position in (12, 40, len(y) - 1):
        f, b, _, n = forward.forecast_at(y, x, y.index[position])
        assert n == position
        assert f == pytest.approx(model[position], abs=1e-18) and b == pytest.approx(bench[position], abs=1e-18)


def test_forecast_does_not_see_the_month_it_forecasts_or_later():
    y, x, _ = monthly_series()
    t = pd.Period("2026-11", "M")
    before = forward.forecast_at(y, x, t)
    y2 = y.copy()
    y2[y2.index >= t] = 1.0
    assert forward.forecast_at(y2, x, t) == before


def test_record_starts_at_the_first_forward_position_and_scores_once_known():
    y, x, current = monthly_series(last="2026-12")
    y[pd.Period("2026-12", "M")] = np.nan                              # December's return not yet known
    log = forward.update(forward.read_log(ROOT / "missing.csv"), current, y, x, META)
    assert list(log["open_month"]) == ["2026-11", "2026-12"]
    assert log.loc[0, "realized_bp"] == pytest.approx(y[pd.Period("2026-11", "M")] * forward.BP)
    assert np.isnan(log.loc[1, "realized_bp"])
    assert log.loc[0, "history_months"] == len(y[y.index < pd.Period("2026-11", "M")])


def test_written_forecasts_and_scores_are_never_changed():
    y, x, current = monthly_series(last="2026-12")
    y[pd.Period("2026-12", "M")] = np.nan
    first = forward.update(forward.read_log(ROOT / "missing.csv"), current, y, x, META)
    revised_y, revised_x = y * 1.5, x * 0.5                             # a revised curve file
    revised_y[pd.Period("2026-12", "M")] = 2e-4
    later = {**META, "made_utc": "2027-01-12T13:23:00Z", "curve_last_date": "2027-01-08"}
    second = forward.update(first, current, revised_y, revised_x, later)
    keep = forward.FORECAST_FIELDS + ["realized_bp"]
    pd.testing.assert_frame_equal(second.loc[[0], keep], first.loc[[0], keep])
    assert second.loc[1, "forecast_bp"] == first.loc[1, "forecast_bp"]
    assert second.loc[1, "realized_bp"] == pytest.approx(2e-4 * forward.BP)
    assert second.loc[1, "scored_utc"] == later["made_utc"]


def test_record_round_trips_through_csv(tmp_path):
    y, x, current = monthly_series(last="2026-12")
    log = forward.update(forward.read_log(tmp_path / "none.csv"), current, y, x, META)
    log.to_csv(tmp_path / "f.csv", index=False)
    again = forward.read_log(tmp_path / "f.csv")
    assert forward.update(again, current, y, x, META)[forward.COLUMNS].equals(again[forward.COLUMNS])
    assert np.array_equal(again["forecast_bp"].to_numpy(), log["forecast_bp"].to_numpy())


def test_late_forecasts_are_counted_as_late():
    log = pd.DataFrame({"open_month": ["2026-11", "2026-11"],
                        "made_utc": ["2026-12-08T13:00:00Z", "2027-01-05T13:00:00Z"]})
    assert list(forward.on_time(log)) == [True, False]


def test_summary_depends_on_the_record_only():
    y, x, current = monthly_series(last="2026-12")
    log = forward.update(forward.read_log(ROOT / "missing.csv"), current, y, x, META)
    assert forward.summary(log) == forward.summary(log.copy())
    assert forward.PLAN_SHA256 in forward.summary(log)
    assert "No forecast yet" in forward.summary(forward.read_log(ROOT / "missing.csv"))


@pytest.mark.parametrize("damage, message", [
    ("stale_curve", "days before the run"),
    ("stale_bill", "H.15 file ends"),
    ("formula", "Svensson formula"),
    ("missing_column", "lacks columns"),
    ("bill_range", "outside [-1%, 25%]"),
])
def test_validation_rejects_broken_files(damage, message):
    raw = curve_frame()
    cm1 = pd.Series(3.7, index=pd.bdate_range("2026-10-01", "2026-12-07"))
    today = pd.Timestamp("2026-12-08")
    forward.validate(raw, cm1, today)                                   # the undamaged files pass
    if damage == "stale_curve":
        today = pd.Timestamp("2027-01-20")
        cm1 = pd.Series(3.7, index=pd.bdate_range("2026-10-01", "2027-01-19"))
    elif damage == "stale_bill":
        cm1 = cm1.loc[:"2026-11-20"]
    elif damage == "formula":
        raw.loc[raw.index[-1], "SVENY05"] += 0.01
    elif damage == "missing_column":
        raw = raw.drop(columns="SVENY07")
    elif damage == "bill_range":
        cm1.iloc[-1] = 40.0
    with pytest.raises(forward.DataCheckError, match=message.replace("[", r"\[").replace("]", r"\]")):
        forward.validate(raw, cm1, today)


RAW = ROOT / "data" / "raw" / "forward"


@pytest.mark.skipif(not (RAW / "feds200628.csv").exists(), reason="needs scripts/05_forward.py downloads")
def test_pipeline_reproduces_the_published_series():
    raw = core.load_gsw(RAW / "feds200628.csv")
    current = forward.build(raw, forward.bill_returns(forward.load_h15(RAW / "h15_treasury_constant_maturity.csv")))
    archive = forward.load_archive()
    assert forward.weight_revision(archive, current) < 1e-6
    common = archive.index.intersection(current.dropna(subset=["x", "y"]).index)
    assert len(common) >= 300
    assert (current.loc[common, "x"] - archive.loc[common, "carry"]).abs().max() * forward.BP < 0.5
    assert (current.loc[common, "y"] - archive.loc[common, "butterfly_rx"]).abs().max() * forward.BP < 0.5
