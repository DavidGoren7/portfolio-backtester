"""Walk-forward folds, selection without leakage, and complete records."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtester.metrics import sharpe
from backtester.synthetic import generate_prices
from backtester.walkforward import (
    folds_frame,
    make_folds,
    rerun_oos,
    run_walkforward,
    signal_dates,
)


@pytest.fixture(scope="module")
def prices():
    names = ["SPY", "EFA", "EEM", "AGG", "TLT", "GLD", "VNQ"]
    return generate_prices(700, names, seed=5)


@pytest.fixture
def result(small_cfg, prices):
    return run_walkforward(prices, small_cfg)


def test_make_folds_expanding_and_non_overlapping():
    dates = pd.date_range("2010-01-31", periods=30, freq="ME")
    folds = make_folds(dates, pd.Timestamp("2012-08-15"), min_train_months=12, test_months=6)
    assert [f.train_end for f in folds] == [dates[12], dates[18], dates[24]]
    for a, b in zip(folds, folds[1:], strict=False):
        assert a.train_start == b.train_start  # expanding: same start
        assert a.test_end == b.train_end  # test blocks tile without gaps or overlap
        assert a.train_end < a.test_end
    assert folds[-1].test_end == pd.Timestamp("2012-08-15")


def test_make_folds_needs_enough_history():
    dates = pd.date_range("2010-01-31", periods=6, freq="ME")
    with pytest.raises(ValueError, match="min_train_months"):
        make_folds(dates, dates[-1], min_train_months=6, test_months=3)


def test_train_and_test_windows_never_overlap(result):
    for run in result.runs.values():
        for rec in run.folds:
            assert rec.train_end < rec.test_end
            # The test block begins strictly after the training block ends.
            block = run.oos.net_returns.loc[
                (run.oos.net_returns.index > rec.train_end)
                & (run.oos.net_returns.index <= rec.test_end)
            ]
            assert block.index.min() > rec.train_end


def test_oos_series_starts_after_first_training_window(result):
    for run in result.runs.values():
        assert run.oos.net_returns.index[0] > result.oos_start
        assert run.signals.index.min() >= result.oos_start


def test_records_are_complete(result, small_cfg):
    frame = folds_frame(result)
    n_folds = len(result.folds)
    assert n_folds >= 3
    assert len(frame) == n_folds * len(result.runs)
    assert not frame[["params", "train_end", "test_end"]].isna().any().any()
    assert np.isfinite(frame["oos_sharpe"]).any()
    expected_configs = sum(run.n_configs for run in result.runs.values())
    assert result.n_configs == expected_configs
    assert result.n_evaluations == expected_configs * n_folds


def test_chosen_params_ignore_test_period_prices(small_cfg, prices):
    base = run_walkforward(prices, small_cfg)
    fold = base.folds[1]
    altered = prices.copy()
    after = altered.index > fold.train_end
    rng = np.random.default_rng(9)
    altered.loc[after] *= np.exp(np.cumsum(rng.normal(0, 0.05, (int(after.sum()), 7)), axis=0))
    other = run_walkforward(altered, small_cfg)
    for name in base.runs:
        # The stitched OOS returns up to the cut are untouched too.
        a = base.runs[name].oos.net_returns.loc[: fold.train_end]
        b = other.runs[name].oos.net_returns.loc[: fold.train_end]
        np.testing.assert_allclose(a.to_numpy(), b.to_numpy(), atol=1e-12)
        for j in range(fold.index + 1):
            assert base.runs[name].folds[j].params == other.runs[name].folds[j].params, name
            assert base.runs[name].folds[j].is_sharpe == pytest.approx(
                other.runs[name].folds[j].is_sharpe
            )


def test_selection_picks_highest_training_sharpe(small_cfg, prices, result):
    """Recompute fold 0's choice for trend_sma by brute force."""
    from backtester.engine import run_backtest
    from backtester.strategies import build_strategy, compute_signals, param_grid

    ex, st = small_cfg.execution, small_cfg.statistics
    dates = signal_dates(prices, result.warmup_rows)
    fold = result.folds[0]
    scores = {}
    for params in param_grid(small_cfg, "trend_sma"):
        sig = compute_signals(build_strategy(small_cfg, "trend_sma", params), prices, dates)
        res = run_backtest(
            prices.loc[result.first_signal :],
            sig,
            ex.lag_days,
            ex.cost_bps,
            ex.cash_rate_annual,
            st.trading_days,
        )
        scores[params["window"]] = sharpe(res.net_returns.loc[: fold.train_end], st.trading_days)
    best = max(scores, key=lambda k: scores[k])
    assert result.runs["trend_sma"].folds[0].params["window"] == best


def test_benchmarks_share_the_oos_dates(result):
    idx = result.runs["equal_weight"].oos.net_returns.index
    for run in result.runs.values():
        assert run.oos.net_returns.index.equals(idx)


def test_rerun_with_same_frictions_reproduces_oos(result, small_cfg, prices):
    run = result.runs["xs_momentum"]
    again = rerun_oos(prices, run, result.oos_start, small_cfg)
    pd.testing.assert_series_equal(again.net_returns, run.oos.net_returns)
    pricier = rerun_oos(prices, run, result.oos_start, small_cfg, cost_bps=25)
    assert pricier.net_returns.sum() < run.oos.net_returns.sum()
