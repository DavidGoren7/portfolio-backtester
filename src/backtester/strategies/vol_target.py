"""Volatility-target overlay: scale a base strategy down when it is too risky."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backtester.strategies.base import Strategy, require_history


@dataclass
class VolTarget:
    """Scale base weights w by min(1, target_vol / sqrt(trading_days * w' S w)).

    S is the sample covariance of the trailing `cov_window` daily returns. The
    scale never exceeds 1 (no leverage), and the unused weight sits in cash.
    """

    base: Strategy
    target_vol: float
    cov_window: int
    trading_days: int
    name: str = "vol_target"
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params = {
            **self.base.params,
            "target_vol": self.target_vol,
            "cov_window": self.cov_window,
        }

    @property
    def required_rows(self) -> int:
        return max(self.base.required_rows, self.cov_window + 1)

    def target_weights(self, prices: pd.DataFrame) -> pd.Series:
        require_history(prices, self.required_rows, self.name)
        w = self.base.target_weights(prices)
        returns = prices.iloc[-(self.cov_window + 1) :].pct_change().iloc[1:]
        cov = returns.cov().to_numpy()
        wv = w.reindex(prices.columns).fillna(0.0).to_numpy()
        port_var = float(wv @ cov @ wv)
        if port_var <= 0:
            return w  # all cash or zero-risk holdings: nothing to scale
        scale = min(1.0, self.target_vol / np.sqrt(self.trading_days * port_var))
        return w * scale
