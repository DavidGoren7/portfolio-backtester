"""Cross-sectional momentum: hold the recent winners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backtester.strategies.base import require_history


@dataclass
class XSMomentum:
    """Rank assets by total return from t - lookback - skip to t - skip; hold the top_k.

    `skip` leaves out the most recent days, where returns tend to reverse.
    The top_k assets get 1/top_k each, so the portfolio is fully invested.
    Ties are broken by column order, so results are deterministic.
    """

    lookback: int
    top_k: int
    skip: int
    name: str = "xs_momentum"
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.params = {"lookback": self.lookback, "top_k": self.top_k, "skip": self.skip}

    @property
    def required_rows(self) -> int:
        return self.lookback + self.skip + 1

    def target_weights(self, prices: pd.DataFrame) -> pd.Series:
        require_history(prices, self.required_rows, self.name)
        end = prices.iloc[-1 - self.skip]
        start = prices.iloc[-1 - self.skip - self.lookback]
        past_return = (end / start - 1.0).to_numpy()
        order = np.argsort(-past_return, kind="stable")[: self.top_k]
        w = np.zeros(prices.shape[1])
        w[order] = 1.0 / self.top_k
        return pd.Series(w, index=prices.columns)
