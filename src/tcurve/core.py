"""Curve evaluation, bond returns, carry, factors and the butterfly (design/plan.md)."""
from pathlib import Path
import io
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
H = 1.0 / 12.0                      # holding period in years
MATURITIES = np.arange(1, 11)       # years
LEGS = (2, 5, 10)                   # butterfly legs: short 2, long 5, short 10
PARAMS = ["BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2"]


# ---------------------------------------------------------------- data

def load_gsw(path=None):
    """Daily Svensson parameters and published zero yields (percent, continuously compounded)."""
    path = Path(path or ROOT / "data" / "raw" / "gsw" / "feds200628.csv")
    lines = path.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Date,"))
    frame = pd.read_csv(io.StringIO("\n".join(lines[start:])), parse_dates=["Date"], na_values=["NA"])
    return frame.set_index("Date").sort_index()


def load_rf(path=None):
    """One-month bill return by month (decimal, simple), from the Kenneth French monthly factor file."""
    path = Path(path or ROOT / "data" / "raw" / "french" / "F-F_Research_Data_Factors_CSV.zip")
    with zipfile.ZipFile(path) as archive:
        text = archive.read(archive.namelist()[0]).decode("latin1").splitlines()
    rows = {}
    started = False
    for line in text:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 5 and parts[0].isdigit() and len(parts[0]) == 6:
            rows[pd.Period(parts[0], "M")] = float(parts[4]) / 100.0
            started = True
        elif started:
            break                                       # the annual block follows the monthly block
    return pd.Series(rows, name="rf").sort_index()


def month_end(frame):
    """Last row of each calendar month that has all six parameters, indexed by month."""
    ok = frame.dropna(subset=PARAMS[:3] + ["TAU1"])
    out = ok.groupby(ok.index.to_period("M")).tail(1)
    out = out.set_index(out.index.to_period("M"))
    return out


# ---------------------------------------------------------------- curve

def svensson(n, beta0, beta1, beta2, beta3, tau1, tau2):
    """Zero-coupon yield at maturity n (years) from Svensson parameters; Nelson-Siegel when beta3 is 0."""
    n = np.asarray(n, dtype=float)
    x1 = n / tau1
    f1 = (1 - np.exp(-x1)) / x1
    y = beta0 + beta1 * f1 + beta2 * (f1 - np.exp(-x1))
    if beta3 != 0 and np.isfinite(tau2) and tau2 > 0:
        x2 = n / tau2
        y = y + beta3 * ((1 - np.exp(-x2)) / x2 - np.exp(-x2))
    return y


def yields_at(month_frame, maturities):
    """Months x maturities table of zero yields in decimals, evaluated from the parameters."""
    values = np.vstack([svensson(maturities, *row) for row in month_frame[PARAMS].to_numpy()])
    return pd.DataFrame(values / 100.0, index=month_frame.index, columns=list(maturities))


# ---------------------------------------------------------------- returns

def returns_and_carry(y_full, y_short, rf):
    """One-month log excess return of each zero and its carry and roll-down.

    y_full[t, n]  yield at maturity n at month-end t; y_short[t, n] yield at maturity n - H at month-end t.
    rf[t]         simple bill return over month t.
    Returns (rx, carry), both indexed by the month-end t at which the position is opened:
      rx[t, n]    = -(n - H) y_short[t+1, n] + n y_full[t, n] - log(1 + rf[t+1])
      carry[t, n] = -(n - H) y_short[t, n]   + n y_full[t, n] - log(1 + rf[t])
    The carry uses the bill return of the month just ended, which is always known at t.
    """
    n = np.asarray(y_full.columns, dtype=float)
    log_rf = np.log1p(rf.reindex(y_full.index))
    start_price = y_full.to_numpy() * n
    rx = -(n - H) * y_short.shift(-1).to_numpy() + start_price - log_rf.shift(-1).to_numpy()[:, None]
    carry = -(n - H) * y_short.to_numpy() + start_price - log_rf.to_numpy()[:, None]
    frame = lambda v: pd.DataFrame(v, index=y_full.index, columns=y_full.columns)  # noqa: E731
    return frame(rx), frame(carry)


# ---------------------------------------------------------------- factors

def principal_components(changes):
    """Loadings (maturities x k), with signs fixed, and variance shares of the yield changes."""
    x = changes.to_numpy() - changes.to_numpy().mean(axis=0)
    _, s, vt = np.linalg.svd(x, full_matrices=False)
    load = vt.T.copy()
    if load[:, 0].sum() < 0:
        load[:, 0] *= -1                                # level: all yields up
    if load[-1, 1] - load[0, 1] < 0:
        load[:, 1] *= -1                                # slope: long end up relative to short end
    mid = len(load) // 2
    if load[mid, 2] - (load[0, 2] + load[-1, 2]) / 2 < 0:
        load[:, 2] *= -1                                # curvature: belly up relative to the wings
    return load, s ** 2 / (s ** 2).sum()


def butterfly_weights(load, maturities=MATURITIES, legs=LEGS):
    """Notional weights on the three legs: 5-year leg of one unit of duration, no exposure to PC1 and PC2.

    The first-order return to a yield change dy is -sum_n w_n (n - H) dy_n, so the exposure to component k
    is -sum_n w_n (n - H) load[n, k].
    """
    idx = [int(np.flatnonzero(np.asarray(maturities) == leg)[0]) for leg in legs]
    dur = np.array(legs, dtype=float) - H
    w_mid = 1.0 / dur[1]
    a = np.array([[dur[0] * load[idx[0], k], dur[2] * load[idx[2], k]] for k in (0, 1)])
    b = np.array([-w_mid * dur[1] * load[idx[1], k] for k in (0, 1)])
    w_short, w_long = np.linalg.solve(a, b)
    return np.array([w_short, w_mid, w_long])


def expanding_butterfly(y_full, first=120):
    """Weights at each month-end from the components of yield changes observed up to that month."""
    changes = y_full.diff().dropna()
    rows = {}
    for i in range(first, len(changes) + 1):
        load, _ = principal_components(changes.iloc[:i])
        rows[changes.index[i - 1]] = butterfly_weights(load, y_full.columns)
    return pd.DataFrame.from_dict(rows, orient="index", columns=list(LEGS))
