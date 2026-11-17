"""Out-of-sample forecasts, bootstrap intervals and regression statistics (design/plan.md)."""
import numpy as np
import pandas as pd

PER_YEAR = 12
DRAWS = 2000


def expanding_forecast(y, x, first, sign_restricted=False):
    """Forecast y[t] from x[t] with OLS on observations before t, and the expanding-mean benchmark.

    y and x are aligned arrays; the forecast for position t uses positions 0..t-1 only. Forecasts start at
    position `first`. With sign_restricted, a negative slope is replaced by the benchmark forecast.
    """
    y, x = np.asarray(y, float), np.asarray(x, float)
    model = np.full(len(y), np.nan)
    bench = np.full(len(y), np.nan)
    for t in range(first, len(y)):
        xs, ys = x[:t], y[:t]
        bench[t] = ys.mean()
        slope = np.cov(xs, ys, ddof=0)[0, 1] / xs.var()
        model[t] = bench[t] if (sign_restricted and slope < 0) else ys.mean() + slope * (x[t] - xs.mean())
    return model, bench


def oos_r2(y, model, bench):
    return 1.0 - np.sum((y - model) ** 2) / np.sum((y - bench) ** 2)


def bootstrap_indices(n, block, draws=DRAWS, seed=0):
    """Stationary bootstrap (Politis and Romano): rows of resampled positions with mean block length `block`."""
    rng = np.random.default_rng(seed)
    idx = np.empty((draws, n), dtype=int)
    for path in idx:
        path[0] = rng.integers(n)
        restart = rng.random(n) < 1.0 / block
        jump = rng.integers(n, size=n)
        for i in range(1, n):
            path[i] = jump[i] if restart[i] else (path[i - 1] + 1) % n
    return idx


def r2_interval(y, model, bench, block=12):
    """Point estimate and 95% interval of the out-of-sample R-squared from paired squared errors."""
    e_model, e_bench = (y - model) ** 2, (y - bench) ** 2
    idx = bootstrap_indices(len(y), block)
    draws = 1.0 - e_model[idx].sum(axis=1) / e_bench[idx].sum(axis=1)
    lo, hi = np.quantile(draws, [0.025, 0.975])
    return {"oos_r2": oos_r2(y, model, bench), "ci_low": lo, "ci_high": hi, "months": len(y),
            "share_above_zero": float((draws > 0).mean())}


def sharpe(r):
    r = np.asarray(r, float)
    return np.sqrt(PER_YEAR) * r.mean() / r.std(ddof=1)


def sharpe_interval(r, block=12):
    r = np.asarray(r, float)
    paths = r[bootstrap_indices(len(r), block)]
    draws = np.sqrt(PER_YEAR) * paths.mean(axis=1) / paths.std(axis=1, ddof=1)
    lo, hi = np.quantile(draws[np.isfinite(draws)], [0.025, 0.975])
    return {"sharpe": sharpe(r), "ci_low": lo, "ci_high": hi, "months": len(r)}


def max_drawdown(r):
    wealth = np.exp(np.cumsum(np.asarray(r, float)))
    return float((wealth / np.maximum.accumulate(wealth) - 1).min())


def ols_newey_west(y, x, lags=12):
    """Slope, Newey-West t-statistic and R-squared of y on a constant and x."""
    y, x = np.asarray(y, float), np.asarray(x, float)
    X = np.column_stack([np.ones(len(y)), x])
    beta = np.linalg.solve(X.T @ X, X.T @ y)
    u = y - X @ beta
    xu = X * u[:, None]
    s = xu.T @ xu
    for lag in range(1, lags + 1):
        g = xu[lag:].T @ xu[:-lag]
        s += (1 - lag / (lags + 1)) * (g + g.T)
    bread = np.linalg.inv(X.T @ X)
    cov = bread @ s @ bread
    return {"slope": beta[1], "t_nw": beta[1] / np.sqrt(cov[1, 1]),
            "r2": 1 - u.var() / y.var(), "months": len(y)}
