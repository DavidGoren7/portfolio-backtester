"""Trend following on each asset's simple moving average."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backtester.strategies.base import require_history


@dataclass
class TrendSMA:
    """Hold an asset if its last price is above its `window`-day simple moving average.

    Each held asset gets 1/N (N = number of assets in the universe), so when
    only some assets are in an uptrend the rest of the portfolio sits in cash.
    The SMA includes the signal-date close.
    """

    window: int
    name: str = "trend_sma"
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params = {"window": self.window}

    @property
    def required_rows(self) -> int:
        return self.window

    def target_weights(self, prices: pd.DataFrame) -> pd.Series:
        require_history(prices, self.required_rows, self.name)
        recent = prices.iloc[-self.window :]
        held = recent.iloc[-1] > recent.mean()
        return held.astype(float) / prices.shape[1]
