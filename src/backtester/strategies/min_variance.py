"""Long-only minimum variance with a Ledoit-Wolf shrunk covariance."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

from backtester.strategies.base import require_history
from backtester.strategies.inv_vol import inverse_vol_weights

log = logging.getLogger(__name__)

# Tolerances for accepting a solver answer. These check feasibility only; they
# do not change the optimization problem.
_SUM_TOL = 1e-6
_BOUND_TOL = 1e-8


def solve_min_variance(cov: np.ndarray) -> np.ndarray | None:
    """Minimize w' S w subject to sum(w) = 1 and 0 <= w <= 1, with SLSQP.

    Returns None if the solver fails or returns an infeasible point.

    Daily covariances are around 1e-5, below SLSQP's default stopping
    tolerance, so an unscaled problem "converges" at the starting point. We
    divide S by its average diagonal first. Scaling the objective by a positive
    constant does not change the minimizer.
    """
    n = cov.shape[0]
    scale = float(np.mean(np.diag(cov)))
    if not np.isfinite(scale) or scale <= 0:
        return None
    cov = cov / scale
    x0 = np.full(n, 1.0 / n)
    res = minimize(
        lambda w: float(w @ cov @ w),
        x0,
        jac=lambda w: 2.0 * cov @ w,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
    )
    w = np.asarray(res.x, dtype=float)
    feasible = np.isfinite(w).all() and abs(w.sum() - 1.0) < _SUM_TOL and (w >= -_BOUND_TOL).all()
    if not res.success or not feasible:
        return None
    w = np.clip(w, 0.0, None)
    return w / w.sum()


@dataclass
class MinVariance:
    """Long-only minimum-variance weights from trailing `window` daily returns.

    Covariance is Ledoit-Wolf shrunk (sample covariance pulled toward a scaled
    identity), which keeps the estimate well conditioned. If SLSQP fails, the
    strategy falls back to inverse-volatility weights on the same window and
    records the date in `fallback_dates`.
    """

    window: int
    name: str = "min_variance"
    params: dict[str, Any] = field(default_factory=dict)
    fallback_dates: list[pd.Timestamp] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.params = {"window": self.window}

    @property
    def required_rows(self) -> int:
        return self.window + 1

    def target_weights(self, prices: pd.DataFrame) -> pd.Series:
        require_history(prices, self.required_rows, self.name)
        returns = prices.iloc[-self.required_rows :].pct_change().iloc[1:]
        cov = LedoitWolf().fit(returns.to_numpy()).covariance_
        w = solve_min_variance(cov)
        if w is None:
            log.warning("min_variance: solver failed on %s, using inverse-vol", prices.index[-1])
            self.fallback_dates.append(prices.index[-1])
            return inverse_vol_weights(returns)
        return pd.Series(w, index=prices.columns)
