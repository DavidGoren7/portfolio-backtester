"""The Strategy protocol and the helper that turns a strategy into signals.

A strategy maps a price history to target weights. The history it receives
always ends at the signal date: `compute_signals` slices `prices.loc[:date]`
before calling it, so a strategy cannot see the future through its input.
The causality tests check this end to end.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class Strategy(Protocol):
    """Anything with a name, parameters, a history requirement, and target_weights."""

    name: str
    params: dict[str, Any]

    @property
    def required_rows(self) -> int:
        """Number of trailing price rows (including the signal date) required."""
        ...

    def target_weights(self, prices: pd.DataFrame) -> pd.Series:
        """Long-only weights summing to at most 1, indexed by `prices.columns`.

        `prices` holds history up to and including the signal date (its last row).
        """
        ...


class InsufficientHistoryError(ValueError):
    """Raised when a strategy is asked for weights before its warm-up ends."""


def require_history(prices: pd.DataFrame, rows: int, who: str) -> None:
    if len(prices) < rows:
        raise InsufficientHistoryError(f"{who}: needs {rows} rows of history, got {len(prices)}")


def param_label(params: dict[str, Any]) -> str:
    """Stable, readable label for a parameter set, e.g. 'lookback=63,skip=21,top_k=2'."""
    if not params:
        return "-"
    return ",".join(f"{k}={params[k]}" for k in sorted(params))


def compute_signals(
    strategy: Strategy, prices: pd.DataFrame, signal_dates: pd.DatetimeIndex
) -> pd.DataFrame:
    """Target weights at each signal date, computed from history up to that date only."""
    rows = []
    for date in signal_dates:
        w = strategy.target_weights(prices.loc[:date])
        rows.append(w.reindex(prices.columns).fillna(0.0).to_numpy(dtype=float))
    return pd.DataFrame(rows, index=signal_dates, columns=prices.columns, dtype=float)
