"""No look-ahead, checked three ways, plus proof that the checks can fail.

1. Signal level: weights at date d are the same whether the strategy is built
   from the full history or from history truncated at d.
2. Signal level: altering prices strictly after T leaves every weight at or
   before T unchanged.
3. Engine level: altering prices strictly after T leaves every net return up
   to and including T unchanged (signals + engine end to end).

An "oracle" strategy that peeks at future prices must FAIL all three. If it
ever passes, the checks are broken and cannot be trusted.
The checks run over every strategy and parameter set in the config, so a new
strategy is covered automatically.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtester.config import load_config
from backtester.engine import month_end_dates, run_backtest
from backtester.strategies import build_strategy, compute_signals, param_grid, strategy_names

CFG = load_config(Path(__file__).resolve().parents[1] / "configs" / "default.yaml")
N_SAMPLE_DATES = 8
FUTURE_DAYS = 21


class Oracle:
    """Cheats on purpose: buys whichever asset rises most over the next month.

    It is handed the dataset at construction, the way a buggy pipeline might
    leak a full DataFrame into a strategy, and reads beyond the signal date.
    """

    name = "oracle"
    params: dict = {}

    def __init__(self, data: pd.DataFrame):
        self.data = data

    @property
    def required_rows(self) -> int:
        return 1

    def target_weights(self, prices: pd.DataFrame) -> pd.Series:
        today = prices.index[-1]
        future = self.data.loc[today:].iloc[: FUTURE_DAYS + 1]
        w = pd.Series(0.0, index=prices.columns)
        if len(future) < 2:
            return w + 1.0 / len(w)
        w[(future.iloc[-1] / future.iloc[0]).idxmax()] = 1.0
        return w


# Each case is (label, factory). A factory builds a strategy from a dataset;
# honest strategies ignore the dataset, the oracle captures it.
def _cases(cfg=CFG):
    cases = []
    for name in strategy_names(cfg):
        for params in param_grid(cfg, name):
            cases.append(
                (f"{name}[{params}]", lambda _data, n=name, p=params: build_strategy(cfg, n, p))
            )
    return cases


def _signal_dates(prices: pd.DataFrame, warmup: int) -> pd.DatetimeIndex:
    ends = month_end_dates(prices.index)
    return ends[ends >= prices.index[warmup - 1]]


def _sample(dates: pd.DatetimeIndex, k: int = N_SAMPLE_DATES) -> pd.DatetimeIndex:
    pick = np.unique(np.linspace(0, len(dates) - 1, k).round().astype(int))
    return dates[pick]


def _perturb_after(prices: pd.DataFrame, cut: pd.Timestamp, seed: int = 0) -> pd.DataFrame:
    """Replace every price strictly after `cut` with a very different random path."""
    rng = np.random.default_rng(seed)
    out = prices.copy()
    after = out.index > cut
    shocks = rng.normal(0, 0.05, size=(int(after.sum()), out.shape[1]))
    out.loc[after] = out.loc[~after].iloc[-1].to_numpy() * np.exp(np.cumsum(shocks, axis=0))
    return out


def check_truncation(factory, prices: pd.DataFrame, dates: pd.DatetimeIndex) -> None:
    full = compute_signals(factory(prices), prices, dates)
    for d in dates:
        hist = prices.loc[:d]
        trunc = compute_signals(factory(hist), hist, pd.DatetimeIndex([d]))
        np.testing.assert_allclose(full.loc[d].to_numpy(), trunc.iloc[0].to_numpy(), atol=1e-12)


def check_future_perturbation(factory, prices: pd.DataFrame, dates: pd.DatetimeIndex) -> None:
    for i, cut in enumerate(dates):
        altered = _perturb_after(prices, cut, seed=i)
        before = dates[dates <= cut]
        a = compute_signals(factory(prices), prices, before)
        b = compute_signals(factory(altered), altered, before)
        np.testing.assert_allclose(a.to_numpy(), b.to_numpy(), atol=1e-12)


def _pipeline_returns(factory, prices, signal_dates, lag) -> pd.Series:
    signals = compute_signals(factory(prices), prices, signal_dates)
    return run_backtest(prices, signals, lag, 5, 0.0, 252).net_returns


def _mid_month_cuts(prices: pd.DataFrame, signal_dates: pd.DatetimeIndex, k: int) -> list:
    """Cut points between rebalances. Cutting only on rebalance dates can miss a
    strategy that peeks less than a month ahead, because its trades land after
    the cut."""
    pos = prices.index.get_indexer(_sample(signal_dates, k)) + 10
    pos = pos[pos < len(prices) - 1]
    return [*_sample(signal_dates, k), *prices.index[pos]]


def check_engine_causality(factory, prices, signal_dates, cuts, lag=1) -> None:
    base = _pipeline_returns(factory, prices, signal_dates, lag)
    for i, cut in enumerate(cuts):
        altered = _perturb_after(prices, cut, seed=100 + i)
        other = _pipeline_returns(factory, altered, signal_dates, lag)
        np.testing.assert_allclose(
            base.loc[:cut].to_numpy(), other.loc[:cut].to_numpy(), atol=1e-12, rtol=0
        )


CASES = _cases()
IDS = [label for label, _ in CASES]
WARMUP = max(
    build_strategy(CFG, n, p).required_rows for n in strategy_names(CFG) for p in param_grid(CFG, n)
)


@pytest.mark.parametrize(("label", "factory"), CASES, ids=IDS)
def test_signals_equal_on_truncated_history(label, factory, synth_prices):
    dates = _sample(_signal_dates(synth_prices, WARMUP))
    check_truncation(factory, synth_prices, dates)


@pytest.mark.parametrize(("label", "factory"), CASES, ids=IDS)
def test_signals_ignore_future_prices(label, factory, synth_prices):
    dates = _sample(_signal_dates(synth_prices, WARMUP), 4)
    check_future_perturbation(factory, synth_prices, dates)


@pytest.mark.parametrize(("label", "factory"), CASES, ids=IDS)
@pytest.mark.parametrize("lag", [1, 2])
def test_engine_returns_ignore_future_prices(label, factory, lag, synth_prices):
    signal_dates = _signal_dates(synth_prices, WARMUP)
    cuts = _mid_month_cuts(synth_prices, signal_dates, 3)
    check_engine_causality(factory, synth_prices, signal_dates, cuts, lag=lag)


def test_oracle_is_caught_by_truncation_check(synth_prices):
    dates = _sample(_signal_dates(synth_prices, WARMUP))
    with pytest.raises(AssertionError):
        check_truncation(Oracle, synth_prices, dates)


def test_oracle_is_caught_by_perturbation_check(synth_prices):
    dates = _sample(_signal_dates(synth_prices, WARMUP), 4)
    with pytest.raises(AssertionError):
        check_future_perturbation(Oracle, synth_prices, dates)


def test_oracle_is_caught_by_engine_check(synth_prices):
    signal_dates = _signal_dates(synth_prices, WARMUP)
    cuts = _mid_month_cuts(synth_prices, signal_dates, 3)
    with pytest.raises(AssertionError):
        check_engine_causality(Oracle, synth_prices, signal_dates, cuts)


def test_oracle_really_does_better_than_honest_equal_weight(synth_prices):
    """Sanity check that the oracle is a real cheat, not a no-op."""
    signal_dates = _signal_dates(synth_prices, WARMUP)
    oracle = _pipeline_returns(Oracle, synth_prices, signal_dates, lag=1)
    honest = _pipeline_returns(
        lambda _d: build_strategy(CFG, "equal_weight", {}), synth_prices, signal_dates, lag=1
    )
    assert oracle.mean() > honest.mean()
