"""Stationary bootstrap (Politis and Romano, 1994) confidence intervals.

Daily returns are not independent: volatility clusters. Resampling single days
(the iid bootstrap) destroys that structure and gives intervals that are too
narrow. The stationary bootstrap resamples blocks of consecutive days whose
lengths are random with a geometric distribution (mean `mean_block`), wrapping
around the end of the sample. It keeps short-range dependence while still
producing a stationary resampled series.

Paired comparisons use the SAME resampled day indices for every strategy, so
the interval for "Sharpe(A) - Sharpe(B)" reflects that A and B were measured
over the same market days.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pandas as pd

from backtester.metrics import daily_rate, sharpe

# Resamples are processed in batches to bound memory (batch x n_days x n_series
# floats). Changing it changes the random stream, so it is fixed here.
BATCH_SIZE = 250


def stationary_bootstrap_indices(
    n: int, mean_block: float, n_reps: int, rng: np.random.Generator
) -> np.ndarray:
    """Return an (n_reps, n) array of resampled day indices.

    Day 0 of each resample is uniform. Each later day starts a new block with
    probability p = 1 / mean_block (jump to a uniform random day), otherwise it
    continues the current block (previous index + 1, wrapping to 0).
    """
    if n < 1 or n_reps < 1:
        raise ValueError("need n >= 1 and n_reps >= 1")
    if mean_block < 1:
        raise ValueError("mean_block must be >= 1")
    p = 1.0 / mean_block
    idx = np.empty((n_reps, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, n_reps)
    for t in range(1, n):
        jump = rng.random(n_reps) < p
        fresh = rng.integers(0, n, n_reps)
        idx[:, t] = np.where(jump, fresh, (idx[:, t - 1] + 1) % n)
    return idx


def _batches(n: int, mean_block: float, n_reps: int, seed: int) -> Iterator[np.ndarray]:
    rng = np.random.default_rng(seed)
    done = 0
    while done < n_reps:
        size = min(BATCH_SIZE, n_reps - done)
        yield stationary_bootstrap_indices(n, mean_block, size, rng)
        done += size


def _sharpe_rows(sample: np.ndarray, rf_daily: float, trading_days: int) -> np.ndarray:
    """Sharpe per (resample, series) for an array shaped (reps, n_days, n_series)."""
    excess = sample - rf_daily
    sd = excess.std(axis=1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = excess.mean(axis=1) / sd * np.sqrt(trading_days)
    return np.where(sd > 1e-15, out, np.nan)


def bootstrap_sharpes(
    returns: pd.DataFrame,
    mean_block: float,
    n_reps: int,
    seed: int,
    trading_days: int,
    cash_rate_annual: float = 0.0,
) -> pd.DataFrame:
    """Sharpe ratio of every column on each paired resample: (n_reps, n_columns)."""
    values = returns.to_numpy(dtype=float)
    if np.isnan(values).any():
        raise ValueError("returns must be aligned and NaN-free")
    rf = daily_rate(cash_rate_annual, trading_days)
    out = [
        _sharpe_rows(values[idx], rf, trading_days)
        for idx in _batches(len(values), mean_block, n_reps, seed)
    ]
    return pd.DataFrame(np.vstack(out), columns=returns.columns)


def percentile_interval(samples: np.ndarray, ci_level: float) -> tuple[float, float]:
    """Equal-tailed percentile interval, ignoring NaN resamples."""
    alpha = (1.0 - ci_level) / 2.0
    lo, hi = np.nanquantile(samples, [alpha, 1.0 - alpha])
    return float(lo), float(hi)


def sharpe_confidence_intervals(
    returns: pd.DataFrame,
    benchmarks: list[str],
    mean_block: float,
    n_reps: int,
    seed: int,
    ci_level: float,
    trading_days: int,
    cash_rate_annual: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Bootstrap intervals for each Sharpe and for paired differences vs benchmarks.

    Returns (sharpe_ci, diff_ci). `sharpe_ci` has one row per strategy with the
    point estimate and interval. `diff_ci` has one row per (strategy,
    benchmark) pair with the point difference, interval, and the share of
    resamples where the difference is above zero.
    """
    boot = bootstrap_sharpes(returns, mean_block, n_reps, seed, trading_days, cash_rate_annual)
    point = {c: sharpe(returns[c], trading_days, cash_rate_annual) for c in returns.columns}
    rows = []
    for c in returns.columns:
        lo, hi = percentile_interval(boot[c].to_numpy(), ci_level)
        rows.append({"strategy": c, "sharpe": point[c], "ci_low": lo, "ci_high": hi})
    sharpe_ci = pd.DataFrame(rows).set_index("strategy")

    diff_rows = []
    for c in returns.columns:
        for b in benchmarks:
            if c == b:
                continue
            d = (boot[c] - boot[b]).to_numpy()
            lo, hi = percentile_interval(d, ci_level)
            diff_rows.append(
                {
                    "strategy": c,
                    "versus": b,
                    "sharpe_diff": point[c] - point[b],
                    "ci_low": lo,
                    "ci_high": hi,
                    "share_above_zero": float(np.nanmean(d > 0)),
                }
            )
    columns = ["strategy", "versus", "sharpe_diff", "ci_low", "ci_high", "share_above_zero"]
    diff_ci = pd.DataFrame(diff_rows, columns=columns).set_index(["strategy", "versus"])
    return sharpe_ci, diff_ci
