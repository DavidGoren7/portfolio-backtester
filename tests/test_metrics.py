"""Metrics against hand-computed values on tiny series."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backtester import metrics as m

TD = 252


def _s(values, start="2021-01-04"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_cagr_two_days_doubling():
    # (1.1 * 1.1) over 2 days -> 1.21 ** (252 / 2) - 1
    r = _s([0.1, 0.1])
    assert m.cagr(r, TD) == pytest.approx(1.21**126 - 1)


def test_ann_vol_and_sharpe_by_hand():
    r = _s([0.01, -0.01, 0.02, 0.0])
    mean = 0.005
    sd = math.sqrt(((0.005) ** 2 + (0.015) ** 2 + (0.015) ** 2 + (0.005) ** 2) / 3)
    assert m.ann_vol(r, TD) == pytest.approx(sd * math.sqrt(TD))
    assert m.sharpe(r, TD) == pytest.approx(mean / sd * math.sqrt(TD))


def test_sharpe_subtracts_cash_rate():
    r = _s([0.01, -0.01, 0.02, 0.0])
    rf = 1.02 ** (1 / TD) - 1
    sd = r.std(ddof=1)
    assert m.sharpe(r, TD, 0.02) == pytest.approx((0.005 - rf) / sd * math.sqrt(TD))


def test_sortino_by_hand():
    r = _s([0.02, -0.01, 0.03, -0.02])
    dd = math.sqrt((0.01**2 + 0.02**2) / 4)
    assert m.sortino(r, TD) == pytest.approx(0.005 / dd * math.sqrt(TD))


def test_max_drawdown_example():
    # Equity: 1.1, 0.88, 0.968, 1.2584 -> peak 1.1, trough 0.88 -> -20%
    r = _s([0.10, -0.20, 0.10, 0.30])
    assert m.max_drawdown(r) == pytest.approx(-0.20)
    dd = m.drawdown_series(r)
    assert dd.iloc[-1] == 0.0


def test_drawdown_counts_loss_from_initial_capital():
    r = _s([-0.1, -0.1])
    assert m.max_drawdown(r) == pytest.approx(0.9 * 0.9 - 1)


def test_calmar():
    r = _s([0.10, -0.20, 0.10, 0.30])
    assert m.calmar(r, TD) == pytest.approx(m.cagr(r, TD) / 0.20)


def test_constant_return_edge_cases():
    r = _s([0.001] * 30)
    assert math.isnan(m.sharpe(r, TD))  # zero volatility
    assert math.isnan(m.sortino(r, TD))  # no down days
    assert m.max_drawdown(r) == 0.0
    assert math.isnan(m.calmar(r, TD))
    assert m.ann_vol(r, TD) == pytest.approx(0.0, abs=1e-15)
    assert m.cagr(r, TD) == pytest.approx(1.001**TD - 1)


def test_zero_returns():
    r = _s([0.0] * 10)
    assert m.cagr(r, TD) == 0.0
    assert math.isnan(m.sharpe(r, TD))


def test_annual_turnover_one_way():
    # Two full swaps (traded notional 2.0 each, two-way) over one year -> 2.0 one-way.
    t = pd.Series([2.0, 2.0])
    assert m.annual_turnover(t, n_days=TD, trading_days=TD) == pytest.approx(2.0)


def test_monthly_best_and_worst():
    idx = pd.DatetimeIndex(["2021-01-04", "2021-01-05", "2021-02-01", "2021-02-02"])
    r = pd.Series([0.1, 0.1, -0.05, 0.0], index=idx)
    monthly = m.monthly_returns(r)
    assert monthly.iloc[0] == pytest.approx(0.21)
    assert monthly.iloc[1] == pytest.approx(-0.05)
    s = m.summarize(r, pd.Series(dtype=float), TD)
    assert s["best_month"] == pytest.approx(0.21)
    assert s["worst_month"] == pytest.approx(-0.05)


def test_summarize_has_all_metrics_in_order():
    r = _s(np.random.default_rng(0).normal(0.0005, 0.01, 300))
    s = m.summarize(r, pd.Series([0.5, 0.5]), TD)
    assert list(s.index) == m.METRIC_ORDER
    assert s["excess_kurtosis"] == pytest.approx(r.kurt())
    assert s["skew"] == pytest.approx(r.skew())


def test_rolling_sharpe_matches_point_sharpe():
    r = _s(np.random.default_rng(1).normal(0.0005, 0.01, 100))
    roll = m.rolling_sharpe(r, 50, TD)
    assert roll.iloc[:49].isna().all()
    assert roll.iloc[-1] == pytest.approx(m.sharpe(r.iloc[-50:], TD))
