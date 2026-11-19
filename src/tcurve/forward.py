"""Part C: a forward record of the Part B carry forecast (design/forward_plan.md).

Each run uses the curve and bill-rate files as published on the day of the run. The Part B series
(reports/part_b_monthly.csv, positions opened up to ARCHIVE_LAST) is used as published; positions opened
later are computed from the current files. A forecast, once written to the record, is never changed; the
realized return is added once the following month is complete.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import io

import numpy as np
import pandas as pd

from . import core, evaluate as ev

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "reports" / "part_b_monthly.csv"
PLAN = ROOT / "design" / "forward_plan.md"
PLAN_SHA256 = "c22aaa6a47346c8ed12762f341d08eefa165da5bb97f756ef5fe1333470965b8"
ARCHIVE_LAST = pd.Period("2026-08", "M")         # last position of the published Part B series
FIRST_FORWARD = pd.Period("2026-11", "M")        # first position opened after the plan was committed
FIRST_PCA = 120                                  # as in Part B
BILL_SERIES = "RIFLGFCM01_N.B"                   # H.15: 1-month Treasury constant maturity, investment basis
LEGS = list(core.LEGS)
BP = 1e4
INTERVAL_FROM = 24                               # scored months before an interval is reported
CURVE_MAX_AGE, BILL_MAX_AGE = 21, 10             # days

FORECAST_FIELDS = ["open_month", "made_utc", "code_commit", "curve_last_date", "bill_last_date",
                   "w_2y", "w_5y", "w_10y", "carry_bp", "forecast_bp", "benchmark_bp", "slope",
                   "history_months", "weight_revision_max"]
SCORE_FIELDS = ["realized_bp", "scored_utc", "curve_last_date_at_scoring"]
COLUMNS = FORECAST_FIELDS + SCORE_FIELDS


class DataCheckError(RuntimeError):
    """A downloaded file failed a check of design/forward_plan.md; the run stops and nothing is written."""


# ---------------------------------------------------------------- inputs

URLS = {
    "feds200628.csv": "https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv",
    "h15_treasury_constant_maturity.csv": (
        "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15&series=bf17364827e38702b42a58cf8eaa3f78"
        "&lastobs=&from=&to=&filetype=csv&label=include&layout=seriescolumn"),
}


def download(directory, attempts=3, wait=30) -> dict:
    """Fetch today's curve and H.15 files into `directory` (git-ignored); returns their paths by name."""
    import time
    import urllib.request
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, url in URLS.items():
        request = urllib.request.Request(url, headers={"User-Agent": "research-download"})
        for attempt in range(1, attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    (directory / name).write_bytes(response.read())
                break
            except OSError as error:
                if attempt == attempts:
                    raise DataCheckError(f"download of {name} failed: {error}") from error
                time.sleep(wait)
        paths[name] = directory / name
    return paths


def load_h15(path) -> pd.Series:
    """Daily 1-month constant-maturity yield (percent) from the Federal Reserve H.15 download."""
    lines = Path(path).read_text().splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith('"Time Period"'))
    except StopIteration:
        raise DataCheckError("H.15 file has no data header") from None
    frame = pd.read_csv(io.StringIO("\n".join(lines[start:])), na_values=["ND", "NC", "NA"])
    if BILL_SERIES not in frame.columns:
        raise DataCheckError(f"H.15 file has no column {BILL_SERIES}")
    series = pd.Series(pd.to_numeric(frame[BILL_SERIES], errors="coerce").to_numpy(),
                       index=pd.to_datetime(frame["Time Period"]), name="cm1")
    return series.dropna().sort_index()


def finished_months(index: pd.DatetimeIndex) -> pd.PeriodIndex:
    """Months that the file has passed: a month counts only when the file contains a later date."""
    months = index.to_period("M").unique()
    return months[[m.end_time < index.max() for m in months]]


def bill_returns(cm1: pd.Series) -> pd.Series:
    """Simple bill return over each month m: the 1-month yield on the last day of month m - 1 with data,
    times the days in m over 365. Only months m - 1 that the file has passed are used."""
    last = cm1.groupby(cm1.index.to_period("M")).last()
    last = last[last.index.isin(finished_months(cm1.index))]
    months = last.index + 1
    days = np.array([m.days_in_month for m in months], dtype=float)
    return pd.Series(last.to_numpy() / 100.0 * days / 365.0, index=months, name="rf")


def month_ends(raw: pd.DataFrame) -> pd.DataFrame:
    """Part B month-end curves, restricted to months the curve file has passed, from the first 10-year yield."""
    monthly = core.month_end(raw)
    monthly = monthly[monthly.index.isin(finished_months(raw.index))]
    return monthly.loc[monthly["SVENY10"].first_valid_index():]


# ---------------------------------------------------------------- checks

def validate(raw: pd.DataFrame, cm1: pd.Series, today: pd.Timestamp) -> dict:
    """Checks of design/forward_plan.md. Raises DataCheckError listing every failure; returns facts on success."""
    problems = []
    published = [f"SVENY{n:02d}" for n in core.MATURITIES]
    missing = [c for c in core.PARAMS + published if c not in raw.columns]
    if missing:
        raise DataCheckError(f"curve file lacks columns {missing}")
    curve_age = (today - raw.index.max()).days
    if curve_age > CURVE_MAX_AGE:
        problems.append(f"curve file ends {raw.index.max().date()}, {curve_age} days before the run")
    monthly = month_ends(raw)
    expected = pd.period_range(monthly.index[0], monthly.index[-1], freq="M")
    if len(monthly) != len(expected):
        problems.append(f"{len(expected) - len(monthly)} month-ends without a full set of parameters")
    yields = core.yields_at(monthly, core.MATURITIES).to_numpy()
    if not np.isfinite(yields).all() or yields.min() <= -0.05 or yields.max() >= 0.25:
        problems.append("month-end yields outside (-5%, 25%) or not finite")
    recent = raw.dropna(subset=core.PARAMS[:3] + ["TAU1"] + published).iloc[-250:]
    gap = np.abs(core.yields_at(recent, core.MATURITIES).to_numpy() * 100 - recent[published].to_numpy()).max()
    if not gap <= 0.001:
        problems.append(f"Svensson formula misses the published yields by {gap:.5f} percentage points")
    if cm1.empty:
        problems.append("H.15 file has no 1-month yields")
    else:
        bill_age = (today - cm1.index.max()).days
        if bill_age > BILL_MAX_AGE:
            problems.append(f"H.15 file ends {cm1.index.max().date()}, {bill_age} days before the run")
        if cm1.min() < -1 or cm1.max() > 25:
            problems.append("1-month yields outside [-1%, 25%]")
    if problems:
        raise DataCheckError("; ".join(problems))
    return {"curve_last_date": str(raw.index.max().date()), "bill_last_date": str(cm1.index.max().date()),
            "formula_gap_pp": float(gap)}


# ---------------------------------------------------------------- series

def build(raw: pd.DataFrame, rf: pd.Series) -> pd.DataFrame:
    """Butterfly weights, carry (x) and next-month excess return (y) by opening month, from the current files."""
    monthly = month_ends(raw)
    y_full = core.yields_at(monthly, core.MATURITIES)
    y_short = core.yields_at(monthly, core.MATURITIES - core.H)
    y_short.columns = y_full.columns
    rx, carry = core.returns_and_carry(y_full, y_short, rf)
    weights = core.expanding_butterfly(y_full, first=FIRST_PCA).reindex(rx.index)
    return pd.DataFrame({"y": (weights * rx[LEGS]).sum(axis=1, min_count=3),
                         "x": (weights * carry[LEGS]).sum(axis=1, min_count=3),
                         **{f"w_{n}y": weights[n] for n in LEGS}}).dropna(subset=[f"w_{n}y" for n in LEGS])


def load_archive(path=ARCHIVE) -> pd.DataFrame:
    archive = pd.read_csv(path, float_precision="round_trip")
    archive.index = pd.PeriodIndex(archive.pop("month"), freq="M")
    return archive


def series(archive: pd.DataFrame, current: pd.DataFrame):
    """(y, x): the published series up to ARCHIVE_LAST, then the current files."""
    if archive.index[-1] != ARCHIVE_LAST:
        raise ValueError(f"published series ends {archive.index[-1]}, expected {ARCHIVE_LAST}")
    later = current.loc[current.index > ARCHIVE_LAST]
    y = pd.concat([archive["butterfly_rx"], later["y"]])
    x = pd.concat([archive["carry"], later["x"]])
    if not (y.index == pd.period_range(y.index[0], y.index[-1], freq="M")).all():
        raise ValueError("months are not contiguous")
    return y, x


def weight_revision(archive: pd.DataFrame, current: pd.DataFrame) -> float:
    """Largest change in the published butterfly weights when recomputed from the current curve file."""
    common = archive.index.intersection(current.index)
    cols = [f"w_{n}y" for n in LEGS]
    return float(np.abs(archive.loc[common, cols].to_numpy() - current.loc[common, cols].to_numpy()).max())


# ---------------------------------------------------------------- forecast and record

def forecast_at(y: pd.Series, x: pd.Series, t: pd.Period):
    """Part B forecast for the position opened at t: OLS of y on x over all earlier openings, applied to x[t].

    Same arithmetic as evaluate.expanding_forecast; returns (forecast, benchmark, slope, months used).
    """
    past = y.index < t
    ys, xs = y[past].to_numpy(float), x[past].to_numpy(float)
    if not (np.isfinite(ys).all() and np.isfinite(xs).all() and np.isfinite(x[t])):
        raise ValueError(f"history before {t} is incomplete")
    bench = ys.mean()
    slope = np.cov(xs, ys, ddof=0)[0, 1] / xs.var()
    return bench + slope * (x[t] - xs.mean()), bench, slope, len(ys)


def read_log(path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    log = pd.read_csv(path, dtype={"open_month": str, "code_commit": str}, float_precision="round_trip")
    return log[COLUMNS]


def update(log: pd.DataFrame, current: pd.DataFrame, y: pd.Series, x: pd.Series, meta: dict) -> pd.DataFrame:
    """Append a forecast for every new position from FIRST_FORWARD on; add realized returns once known.

    meta: made_utc, code_commit, curve_last_date, bill_last_date, weight_revision_max. Fields already in the
    record are never changed.
    """
    logged = set(log["open_month"].astype(str))
    rows = []
    for t in x.index:
        if t < FIRST_FORWARD or str(t) in logged or not np.isfinite(x[t]):
            continue
        f, b, slope, months = forecast_at(y, x, t)
        rows.append({"open_month": str(t), "made_utc": meta["made_utc"], "code_commit": meta["code_commit"],
                     "curve_last_date": meta["curve_last_date"], "bill_last_date": meta["bill_last_date"],
                     **{f"w_{n}y": current.at[t, f"w_{n}y"] for n in LEGS},
                     "carry_bp": x[t] * BP, "forecast_bp": f * BP, "benchmark_bp": b * BP, "slope": slope,
                     "history_months": months, "weight_revision_max": meta["weight_revision_max"]})
    if rows:
        new = pd.DataFrame(rows, columns=COLUMNS)
        out = new if log.empty else pd.concat([log, new], ignore_index=True)
    else:
        out = log.copy()
    out = out.astype({"realized_bp": float, "scored_utc": object, "curve_last_date_at_scoring": object})
    for i in out.index:
        t = pd.Period(out.at[i, "open_month"], "M")
        if pd.isna(out.at[i, "realized_bp"]) and t in y.index and np.isfinite(y[t]):
            out.at[i, "realized_bp"] = y[t] * BP
            out.at[i, "scored_utc"] = meta["made_utc"]
            out.at[i, "curve_last_date_at_scoring"] = meta["curve_last_date"]
    return out.sort_values("open_month", kind="stable").reset_index(drop=True)


def plan_sha256(path=PLAN) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def on_time(log: pd.DataFrame) -> np.ndarray:
    """Whether each forecast was written before the month it forecasts had ended."""
    made = pd.to_datetime(log["made_utc"], utc=True)
    ends = [(pd.Period(m, "M") + 1).end_time.tz_localize("UTC") for m in log["open_month"]]
    return np.array([a < b for a, b in zip(made, ends)], dtype=bool)


def summary(log: pd.DataFrame) -> str:
    """forward/summary.md, written from the record alone so that it changes only when the record does."""
    lines = ["# Forward record", "",
             "Written by `scripts/05_forward.py` (scheduled in `.github/workflows/forward.yml`). Rule, data and "
             f"checks: [`design/forward_plan.md`](../design/forward_plan.md), SHA-256 `{PLAN_SHA256}`. "
             "Returns are per unit of 5-year duration, in basis points.", ""]
    if log.empty:
        lines += ["No forecast yet. The first is for the position opened at the end of November 2026; it is "
                  "written once the curve for that date is published.", ""]
        return "\n".join(lines)
    scored = log.dropna(subset=["realized_bp"])
    timely = on_time(log)
    lines += ["| Positions logged | Logged before the forecast month ended | Scored | Forward R² against the mean |",
              "|---|---|---|---|"]
    if len(scored):
        y, f, b = (scored[c].to_numpy(float) for c in ("realized_bp", "forecast_bp", "benchmark_bp"))
        r2 = f"{ev.oos_r2(y, f, b):+.1%}"
        if len(scored) >= INTERVAL_FROM:
            ci = ev.r2_interval(y, f, b, block=12)
            r2 += f" (95% CI {ci['ci_low']:+.1%} to {ci['ci_high']:+.1%})"
    else:
        r2 = "none scored yet"
    lines += [f"| {len(log)} | {int(timely.sum())} | {len(scored)} | {r2} |", "",
              "| Opened | Forecast written (UTC) | Carry | Forecast | Mean | Realized |", "|---|---|---|---|---|---|"]
    for _, row in log.iloc[::-1].head(24).iterrows():
        realized = "" if pd.isna(row.realized_bp) else f"{row.realized_bp:+.2f}"
        lines.append(f"| {row.open_month} | {str(row.made_utc)[:16].replace('T', ' ')} | {row.carry_bp:+.2f} | "
                     f"{row.forecast_bp:+.2f} | {row.benchmark_bp:+.2f} | {realized} |")
    lines += ["", f"No conclusion is drawn before 60 scored months (plan, section 5); no interval is shown before "
              f"{INTERVAL_FROM}.", ""]
    return "\n".join(lines)
