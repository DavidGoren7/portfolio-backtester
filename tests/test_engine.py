"""Execution engine: lag, drift, costs, constraints, cash."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtester.engine import month_end_dates, run_backtest
from backtester.synthetic import generate_prices

TD = 252


def _prices(cols: dict[str, list[float]]) -> pd.DataFrame:
    n = len(next(iter(cols.values())))
    idx = pd.bdate_range("2021-01-04", periods=n)
    return pd.DataFrame(cols, index=idx, dtype=float)


def _signal(prices: pd.DataFrame, date_pos: int, weights: dict[str, float]) -> pd.DataFrame:
    row = {c: weights.get(c, 0.0) for c in prices.columns}
    return pd.DataFrame([row], index=[prices.index[date_pos]])


def test_single_asset_zero_cost_tracks_asset_after_execution():
    prices = _prices({"A": [100, 101, 99, 103, 104, 102]})
    sig = _signal(prices, 1, {"A": 1.0})  # signal day 1, executes day 2 (lag 1)
    res = run_backtest(prices, sig, lag_days=1, cost_bps=0, cash_rate_annual=0, trading_days=TD)
    asset = prices["A"].pct_change()
    # Before and on the execution day the portfolio is in cash.
    assert (res.net_returns.loc[: prices.index[2]] == 0).all()
    # After execution it earns exactly the asset's return.
    np.testing.assert_allclose(res.net_returns.iloc[2:], asset.iloc[3:], atol=1e-15)


def test_lag_two_executes_one_day_later():
    prices = _prices({"A": [100, 101, 99, 103, 104, 102]})
    sig = _signal(prices, 1, {"A": 1.0})
    res = run_backtest(prices, sig, lag_days=2, cost_bps=0, cash_rate_annual=0, trading_days=TD)
    assert res.turnover.index[0] == prices.index[3]
    assert res.net_returns.loc[prices.index[3]] == 0


def test_weights_drift_analytically_between_rebalances():
    prices = _prices({"A": [100, 110, 121, 133.1], "B": [100, 100, 90, 81]})
    sig = _signal(prices, 0, {"A": 0.5, "B": 0.5})  # executes at close of day 1
    res = run_backtest(prices, sig, lag_days=1, cost_bps=0, cash_rate_annual=0, trading_days=TD)
    for t in (2, 3):
        ga = prices["A"].iloc[t] / prices["A"].iloc[1]
        gb = prices["B"].iloc[t] / prices["B"].iloc[1]
        expected_a = 0.5 * ga / (0.5 * ga + 0.5 * gb)
        assert res.weights["A"].iloc[t] == pytest.approx(expected_a, abs=1e-12)
        assert res.weights["B"].iloc[t] == pytest.approx(1 - expected_a, abs=1e-12)
    # No implicit rebalancing: one execution only.
    assert len(res.turnover) == 1


def test_cash_to_full_position_costs_exactly_cost_bps():
    prices = _prices({"A": [100, 100, 100, 100]})
    sig = _signal(prices, 0, {"A": 1.0})
    res = run_backtest(prices, sig, lag_days=1, cost_bps=5, cash_rate_annual=0, trading_days=TD)
    assert res.costs.iloc[0] == pytest.approx(5 / 10_000)
    assert res.turnover.iloc[0] == pytest.approx(1.0)
    assert res.net_returns.iloc[0] == pytest.approx(-5 / 10_000)
    assert res.gross_returns.iloc[0] == 0


def test_rebalance_cost_uses_drifted_weights():
    prices = _prices({"A": [100, 100, 200, 200, 200], "B": [100, 100, 100, 100, 100]})
    sig = pd.DataFrame(
        [{"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}], index=[prices.index[0], prices.index[2]]
    )
    res = run_backtest(prices, sig, lag_days=1, cost_bps=10, cash_rate_annual=0, trading_days=TD)
    # After A doubles, drifted weights are 2/3 and 1/3, so trading back to 50/50
    # moves 1/6 + 1/6 = 1/3 of the portfolio.
    assert res.turnover.iloc[1] == pytest.approx(1 / 3)
    assert res.costs.iloc[1] == pytest.approx(10 / 10_000 / 3)


def test_constraints_hold_on_synthetic_run():
    prices = generate_prices(600, list("ABCDE"), seed=1)
    dates = month_end_dates(prices.index)
    rng = np.random.default_rng(0)
    raw = rng.random((len(dates), 5))
    raw = raw / raw.sum(axis=1, keepdims=True) * rng.uniform(0.3, 1.0, (len(dates), 1))
    sig = pd.DataFrame(raw, index=dates, columns=prices.columns)
    res = run_backtest(prices, sig, lag_days=1, cost_bps=5, cash_rate_annual=0.02, trading_days=TD)
    w = res.weights.to_numpy()
    assert (w >= -1e-9).all()
    assert (w.sum(axis=1) <= 1 + 1e-9).all()


@pytest.mark.parametrize(
    "bad", [{"A": -0.1, "B": 0.5}, {"A": 0.7, "B": 0.6}, {"A": np.nan, "B": 0.5}]
)
def test_invalid_targets_rejected(bad):
    prices = _prices({"A": [1, 2, 3], "B": [1, 2, 3]})
    with pytest.raises(ValueError):
        run_backtest(prices, _signal(prices, 0, bad), 1, 0, 0, TD)


def test_lag_zero_rejected():
    prices = _prices({"A": [1, 2, 3]})
    with pytest.raises(ValueError, match="look-ahead"):
        run_backtest(prices, _signal(prices, 0, {"A": 1}), 0, 0, 0, TD)


def test_cash_earns_configured_rate():
    prices = _prices({"A": [100, 120, 80, 100, 90]})
    empty = pd.DataFrame(columns=prices.columns, dtype=float)
    res = run_backtest(
        prices, empty, lag_days=1, cost_bps=5, cash_rate_annual=0.05, trading_days=TD
    )
    daily = 1.05 ** (1 / TD) - 1
    np.testing.assert_allclose(res.net_returns.to_numpy(), daily, rtol=1e-9)


def test_partial_investment_mixes_cash_and_asset():
    prices = _prices({"A": [100, 100, 110, 121]})
    sig = _signal(prices, 0, {"A": 0.5})
    res = run_backtest(prices, sig, lag_days=1, cost_bps=0, cash_rate_annual=0, trading_days=TD)
    # Day 2: half in A (+10%), half in cash, so +5%.
    assert res.net_returns.iloc[1] == pytest.approx(0.05)


def test_signals_past_end_are_dropped():
    prices = _prices({"A": [100, 101, 102]})
    sig = _signal(prices, 2, {"A": 1.0})
    res = run_backtest(prices, sig, 1, 0, 0, TD)
    assert res.turnover.empty
    assert (res.net_returns == 0).all()


def test_month_end_dates_excludes_incomplete_last_month():
    idx = pd.bdate_range("2021-01-25", "2021-03-10")
    ends = month_end_dates(idx)
    assert list(ends) == [pd.Timestamp("2021-01-29"), pd.Timestamp("2021-02-26")]
