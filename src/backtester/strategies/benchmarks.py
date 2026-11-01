"""Benchmarks: equal weight and 60/40. Neither is tuned."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backtester.strategies.base import require_history


@dataclass
class EqualWeight:
    """1/N in every asset, rebalanced monthly."""

    name: str = "equal_weight"
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def required_rows(self) -> int:
        return 1

    def target_weights(self, prices: pd.DataFrame) -> pd.Series:
        require_history(prices, self.required_rows, self.name)
        n = prices.shape[1]
        return pd.Series(1.0 / n, index=prices.columns)


@dataclass
class SixtyForty:
    """A fixed equity/bond mix, 60/40 by default, rebalanced monthly."""

    equity: str
    bond: str
    equity_weight: float
    name: str = "sixty_forty"
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def required_rows(self) -> int:
        return 1

    def target_weights(self, prices: pd.DataFrame) -> pd.Series:
        require_history(prices, self.required_rows, self.name)
        w = pd.Series(0.0, index=prices.columns)
        w[self.equity] = self.equity_weight
        w[self.bond] = 1.0 - self.equity_weight
        return w
