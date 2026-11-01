"""Deterministic synthetic prices for tests and `make demo`.

The generator is a multivariate normal model of daily log returns with a
built-in crash regime. It is NOT a model of real markets and its output must
always be labeled DEMO. The asset profiles below are rough, made-up stand-ins
for "stocks", "bonds", "gold", and so on, chosen only so that strategies behave
differently from each other.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Annual drift and volatility per asset profile. Profiles are reused in order
# if more assets are requested than profiles exist. Groups drive correlation.
_PROFILES = (
    # (annual_drift, annual_vol, group)
    (0.08, 0.17, "equity"),
    (0.06, 0.19, "equity"),
    (0.07, 0.25, "equity"),
    (0.03, 0.05, "bond"),
    (0.035, 0.13, "bond"),
    (0.04, 0.16, "gold"),
    (0.07, 0.24, "equity"),
)
_SAME_GROUP_CORR = 0.75
_EQUITY_BOND_CORR = -0.2
_OTHER_CORR = 0.1
# Crash regime: placed at a fixed fraction of the sample, as a fraction of its length.
_CRASH_START_FRAC = 0.35
_CRASH_LENGTH_FRAC = 0.04
_CRASH_EQUITY_DRIFT = -0.9  # annualized, during the crash only
_CRASH_BOND_DRIFT = 0.10
_CRASH_VOL_MULT = 2.5
_DEMO_START = "2005-01-03"
_DAYS_PER_YEAR = 252


def _correlation(groups: list[str]) -> np.ndarray:
    n = len(groups)
    corr = np.eye(n)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if groups[i] == groups[j]:
                corr[i, j] = _SAME_GROUP_CORR
            elif {groups[i], groups[j]} == {"equity", "bond"}:
                corr[i, j] = _EQUITY_BOND_CORR
            else:
                corr[i, j] = _OTHER_CORR
    # Make sure the matrix is positive definite before Cholesky.
    eigvals = np.linalg.eigvalsh(corr)
    if eigvals.min() <= 0:
        corr += np.eye(n) * (abs(eigvals.min()) + 1e-6)
        d = np.sqrt(np.diag(corr))
        corr = corr / np.outer(d, d)
    return corr


def generate_prices(n_days: int, names: tuple[str, ...] | list[str], seed: int) -> pd.DataFrame:
    """Return `n_days` business days of positive prices starting at 100.

    Same `seed` gives the same output on every machine (numpy PCG64).
    """
    names = tuple(names)
    n = len(names)
    profiles = [_PROFILES[i % len(_PROFILES)] for i in range(n)]
    drift = np.array([p[0] for p in profiles]) / _DAYS_PER_YEAR
    vol = np.array([p[1] for p in profiles]) / np.sqrt(_DAYS_PER_YEAR)
    groups = [p[2] for p in profiles]
    chol = np.linalg.cholesky(_correlation(groups))

    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_days, n)) @ chol.T

    mu = np.tile(drift, (n_days, 1))
    sigma = np.tile(vol, (n_days, 1))
    c0 = int(n_days * _CRASH_START_FRAC)
    c1 = c0 + max(1, int(n_days * _CRASH_LENGTH_FRAC))
    is_equity = np.array([g == "equity" for g in groups])
    is_bond = np.array([g == "bond" for g in groups])
    mu[c0:c1, is_equity] = _CRASH_EQUITY_DRIFT / _DAYS_PER_YEAR
    mu[c0:c1, is_bond] = _CRASH_BOND_DRIFT / _DAYS_PER_YEAR
    sigma[c0:c1, is_equity] *= _CRASH_VOL_MULT

    log_ret = mu - 0.5 * sigma**2 + sigma * z
    log_ret[0] = 0.0
    prices = 100.0 * np.exp(np.cumsum(log_ret, axis=0))
    index = pd.bdate_range(_DEMO_START, periods=n_days, name="date")
    return pd.DataFrame(prices, index=index, columns=list(names))
