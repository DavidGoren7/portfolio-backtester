"""Stationary bootstrap: determinism, pairing, ordering, lengths."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtester.bootstrap import (
    bootstrap_sharpes,
    sharpe_confidence_intervals,
    stationary_bootstrap_indices,
)
from backtester.study import subperiod_table


@pytest.fixture
def returns():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2015-01-01", periods=500)
    return pd.DataFrame(
        {
            "equal_weight": rng.normal(0.0003, 0.01, 500),
            "sixty_forty": rng.normal(0.0002, 0.007, 500),
            "strat": rng.normal(0.0005, 0.012, 500),
        },
        index=idx,
    )


def test_same_seed_same_output(returns):
    a = bootstrap_sharpes(returns, 20, 300, seed=1, trading_days=252)
    b = bootstrap_sharpes(returns, 20, 300, seed=1, trading_days=252)
    c = bootstrap_sharpes(returns, 20, 300, seed=2, trading_days=252)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(c)


def test_resampled_length_and_range():
    idx = stationary_bootstrap_indices(137, 20, 50, np.random.default_rng(0))
    assert idx.shape == (50, 137)
    assert idx.min() >= 0 and idx.max() < 137


def test_mean_block_length_is_about_right():
    idx = stationary_bootstrap_indices(2000, 20, 200, np.random.default_rng(3))
    breaks = (np.diff(idx, axis=1) != 1) & ~((idx[:, :-1] == 1999) & (idx[:, 1:] == 0))
    mean_len = idx.size / (breaks.sum() + idx.shape[0])
    assert 17 < mean_len < 23


def test_paired_resampling_uses_identical_indices(returns):
    # A copy of a series must have a Sharpe difference of exactly zero on every
    # resample. That only happens if both use the same day indices.
    df = returns[["strat"]].assign(copy=returns["strat"])
    boot = bootstrap_sharpes(df, 20, 200, seed=4, trading_days=252)
    assert (boot["strat"] - boot["copy"]).abs().max() == 0.0


def test_intervals_are_ordered(returns):
    ci, diff = sharpe_confidence_intervals(
        returns, ["equal_weight", "sixty_forty"], 20, 400, 7, 0.95, 252
    )
    assert (ci["ci_low"] < ci["ci_high"]).all()
    assert (diff["ci_low"] < diff["ci_high"]).all()
    assert set(diff.index.get_level_values("versus")) == {"equal_weight", "sixty_forty"}
    assert ("equal_weight", "equal_weight") not in diff.index
    assert diff["share_above_zero"].between(0, 1).all()


def test_wider_level_gives_wider_interval(returns):
    narrow, _ = sharpe_confidence_intervals(returns, [], 20, 400, 7, 0.80, 252)
    wide, _ = sharpe_confidence_intervals(returns, [], 20, 400, 7, 0.99, 252)
    assert (wide["ci_high"] - wide["ci_low"] > narrow["ci_high"] - narrow["ci_low"]).all()


def test_subperiods_report_coverage_and_skip_uncovered(returns):
    windows = {
        "before": (pd.Timestamp("2010-01-01"), pd.Timestamp("2010-12-31")),
        "inside": (pd.Timestamp("2015-03-01"), pd.Timestamp("2015-06-30")),
    }
    table = subperiod_table(returns, windows)
    before = table[table["subperiod"] == "before"]
    assert (before["oos_coverage"] == 0).all()
    assert before["total_return"].isna().all()
    inside = table[(table["subperiod"] == "inside") & (table["strategy"] == "strat")].iloc[0]
    r = returns.loc["2015-03-01":"2015-06-30", "strat"]
    assert inside["total_return"] == pytest.approx((1 + r).prod() - 1)
    assert inside["oos_coverage"] == pytest.approx(1.0)
