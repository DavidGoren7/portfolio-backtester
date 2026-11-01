"""Execution engine: turn target weights at signal dates into daily returns.

Semantics (see SPEC.md, "Execution semantics"):

1. Signals are target weights decided at the close of a signal date.
2. A signal on trading day i is executed at the close of trading day i + lag_days,
   using that day's adjusted close. Signals that would execute after the last
   available date are dropped.
3. Between executions holdings drift with realized returns. Nothing is
   rebalanced implicitly.
4. On an execution day the portfolio trades from its drifted weights to the
   target. Traded notional is sum_i |target_i - drifted_i| (a fraction of
   portfolio value). The cost cost_bps / 10000 * traded is deducted from
   portfolio value on that day.
5. Weights are long-only and sum to at most 1. The remainder is cash, which
   compounds daily at (1 + cash_rate_annual) ** (1 / trading_days) - 1.

The portfolio starts at value 1, entirely in cash, at the close of the first
date in `prices`. Returns are reported from the second date onward.

The loop runs once per execution segment, not once per day: inside a segment
holdings simply scale with price relatives, which is vectorized.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

WEIGHT_TOL = 1e-9
BPS = 10_000.0


@dataclass
class BacktestResult:
    """Everything the engine produces.

    gross_returns: daily returns of the holdings before transaction costs.
    net_returns: daily returns after costs. (1 + net) = (1 + gross) * (1 - cost)
        on execution days and net = gross otherwise.
    weights: end-of-day asset weights after drift and any trade (cash is
        1 - row sum).
    turnover: traded notional per execution, as a fraction of portfolio value
        (two-way: buying 0.3 and selling 0.3 counts 0.6).
    costs: cost per execution as a fraction of portfolio value.
    """

    gross_returns: pd.Series
    net_returns: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    costs: pd.Series


def month_end_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last trading day of each complete month in `index`.

    A date counts as a month end only if the next available date falls in a
    different month. The final date in the index is never a month end, because
    we cannot tell whether its month is complete.
    """
    if len(index) < 2:
        return pd.DatetimeIndex([], name=index.name)
    periods = index.to_period("M")
    is_end = np.asarray(periods[:-1] != periods[1:])
    return pd.DatetimeIndex(index[:-1][is_end], name=index.name)


def validate_weights(weights: pd.DataFrame) -> None:
    """Raise ValueError unless every row is long-only and sums to at most 1."""
    values = weights.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("target weights contain NaN or inf")
    if (values < -WEIGHT_TOL).any():
        raise ValueError("target weights must be non-negative (long-only)")
    if (values.sum(axis=1) > 1 + WEIGHT_TOL).any():
        raise ValueError("target weights must sum to at most 1")


def run_backtest(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    lag_days: int,
    cost_bps: float,
    cash_rate_annual: float,
    trading_days: int,
) -> BacktestResult:
    """Simulate a long-only portfolio that trades toward `signals` with a lag.

    Args:
        prices: adjusted closes, dates x assets, strictly positive.
        signals: target weights, indexed by signal dates that must appear in
            `prices.index`; columns must equal `prices.columns`.
        lag_days: trading days between signal and execution. Must be >= 1.
        cost_bps: cost in basis points of traded notional.
        cash_rate_annual: annual rate earned by uninvested cash.
        trading_days: trading days per year, used to convert the cash rate.
    """
    if lag_days < 1:
        raise ValueError("lag_days must be >= 1; same-close execution is look-ahead")
    if list(signals.columns) != list(prices.columns):
        raise ValueError("signal columns must match price columns")
    if not signals.index.isin(prices.index).all():
        raise ValueError("every signal date must be a trading date in prices")
    validate_weights(signals)

    dates = prices.index
    n, k = prices.shape
    px = prices.to_numpy(dtype=float)
    cash_growth = (1.0 + cash_rate_annual) ** (1.0 / trading_days)
    cost_rate = cost_bps / BPS

    # Map each signal to its execution day; drop those past the end of data.
    sig_pos = dates.get_indexer(signals.index)
    exec_pos = sig_pos + lag_days
    keep = exec_pos < n
    exec_pos = exec_pos[keep]
    targets = signals.to_numpy(dtype=float)[keep]
    if len(exec_pos) and (np.diff(exec_pos) <= 0).any():
        raise ValueError("signals must be strictly increasing in time")

    gross = np.zeros(n)
    net = np.zeros(n)
    weights = np.zeros((n, k))
    turnover = np.zeros(len(exec_pos))
    costs = np.zeros(len(exec_pos))

    holdings = np.zeros(k)  # value held in each asset at the last close processed
    cash = 1.0
    last = 0  # index of the last close processed

    # Each segment covers days (last, end]; executions happen at the segment end.
    boundaries = [*exec_pos.tolist(), n - 1]
    for seg, end in enumerate(boundaries):
        if end > last:
            days = np.arange(last + 1, end + 1)
            rel = px[days] / px[last]  # price relative to the segment start close
            asset_val = holdings * rel  # (len(days), k)
            cash_val = cash * cash_growth ** (days - last)
            value = asset_val.sum(axis=1) + cash_val
            prev_value = np.concatenate([[holdings.sum() + cash], value[:-1]])
            gross[days] = value / prev_value - 1.0
            net[days] = gross[days]
            weights[days] = asset_val / value[:, None]
            holdings = asset_val[-1]
            cash = cash_val[-1]
            last = end
        if seg < len(exec_pos):
            value = holdings.sum() + cash
            drifted = holdings / value
            target = targets[seg]
            traded = np.abs(target - drifted).sum()
            cost = cost_rate * traded
            value_after = value * (1.0 - cost)
            holdings = target * value_after
            cash = value_after - holdings.sum()
            turnover[seg] = traded
            costs[seg] = cost
            net[end] = (1.0 + gross[end]) * (1.0 - cost) - 1.0
            weights[end] = target

    exec_dates = dates[exec_pos]
    return BacktestResult(
        gross_returns=pd.Series(gross[1:], index=dates[1:], name="gross"),
        net_returns=pd.Series(net[1:], index=dates[1:], name="net"),
        weights=pd.DataFrame(weights, index=dates, columns=prices.columns),
        turnover=pd.Series(turnover, index=exec_dates, name="turnover"),
        costs=pd.Series(costs, index=exec_dates, name="cost"),
    )
