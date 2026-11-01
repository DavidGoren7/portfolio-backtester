"""Inverse-volatility weighting."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backtester.strategies.base import require_history

log = logging.getLogger(__name__)


def inverse_vol_weights(returns: pd.DataFrame) -> pd.Series:
    """Weights proportional to 1 / sample std of daily returns, summing to 1.

    If any asset has zero or undefined volatility, 1/vol is meaningless, so
    the function falls back to equal weights and logs it.
    """
    vol = returns.std(ddof=1).to_numpy()
    if not np.isfinite(vol).all() or (vol <= 0).any():
        log.warning("inverse-vol: zero or undefined volatility, using equal weights")
        return pd.Series(1.0 / returns.shape[1], index=returns.columns)
    inv = 1.0 / vol
    return pd.Series(inv / inv.sum(), index=returns.columns)


@dataclass
class InvVol:
    """Weights proportional to 1 / trailing `window`-day volatility, fully invested."""

    window: int
    name: str = "inv_vol"
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params = {"window": self.window}

    @property
    def required_rows(self) -> int:
        return self.window + 1  # window returns need window + 1 prices

    def target_weights(self, prices: pd.DataFrame) -> pd.Series:
        require_history(prices, self.required_rows, self.name)
        returns = prices.iloc[-self.required_rows :].pct_change().iloc[1:]
        return inverse_vol_weights(returns)
