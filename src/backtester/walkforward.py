"""Expanding-window walk-forward parameter selection and out-of-sample stitching.

Timeline (all dates are month-end rebalance dates unless stated):

    first_signal          B_0                 B_1                 B_2 ...
    |---- training 0 -----|---- test 0 -------|---- test 1 -------|
    |---------- training 1 -------------------|
    |---------- training 2 ---------------------------------------|

* `first_signal` is the first month end at which every configured strategy has
  enough history (the longest warm-up across all strategies and grids). All
  strategies start there, in cash, so training windows are identical.
* B_0 is `min_train_months` month ends after `first_signal`; each later
  boundary adds `test_months`.
* Fold j trains on returns in (first_signal, B_j] and tests on (B_j, B_{j+1}].
  The last fold tests up to the end of the data, so it may be shorter.
* In fold j, every parameter set is scored by net Sharpe on its training
  returns. The winner drives the signals dated in [B_j, B_{j+1}). The signal at
  B_j uses only data up to B_j's close, and it executes after B_j, inside the
  test block.
* The headline out-of-sample (OOS) series is ONE engine run over (B_0, end]
  using those stitched signals. Holdings carry over between folds, so the cost
  of switching parameters is paid, not ignored.

Training scores come from one full-history run per parameter set. This is not
a leak: the engine and strategies are causal (see tests/test_causality.py), so
returns up to B_j from a full-history run are identical to a run that stops at
B_j. tests/test_walkforward.py checks this by perturbing test-period prices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backtester.config import Config
from backtester.engine import BacktestResult, month_end_dates, run_backtest
from backtester.metrics import sharpe
from backtester.strategies import (
    build_strategy,
    compute_signals,
    max_required_rows,
    param_grid,
    param_label,
    strategy_names,
)


@dataclass(frozen=True)
class Fold:
    index: int
    train_start: pd.Timestamp  # exclusive: first training return is the day after
    train_end: pd.Timestamp  # inclusive (B_j)
    test_end: pd.Timestamp  # inclusive


@dataclass
class FoldRecord:
    fold: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_end: pd.Timestamp
    params: dict[str, Any]
    params_label: str
    is_sharpe: float
    oos_sharpe: float


@dataclass
class StrategyRun:
    """Walk-forward output for one strategy family."""

    name: str
    folds: list[FoldRecord]
    signals: pd.DataFrame  # stitched signals, dated from B_0 onward
    oos: BacktestResult  # one engine run over (B_0, end]
    n_configs: int
    solver_fallbacks: int = 0


@dataclass
class WalkForwardResult:
    runs: dict[str, StrategyRun]
    first_signal: pd.Timestamp
    oos_start: pd.Timestamp  # B_0; OOS returns start the next trading day
    folds: list[Fold]
    n_configs: int  # distinct strategy-parameter combinations tried
    n_evaluations: int  # combinations x folds (each scored once per fold)
    warmup_rows: int
    extra: dict[str, Any] = field(default_factory=dict)


def signal_dates(prices: pd.DataFrame, warmup_rows: int) -> pd.DatetimeIndex:
    """Month ends at which every strategy has `warmup_rows` of history."""
    if len(prices) < warmup_rows:
        raise ValueError(f"need at least {warmup_rows} rows of prices, got {len(prices)}")
    ends = month_end_dates(prices.index)
    return ends[ends >= prices.index[warmup_rows - 1]]


def make_folds(
    dates: pd.DatetimeIndex, last_date: pd.Timestamp, min_train_months: int, test_months: int
) -> list[Fold]:
    """Expanding folds over month-end `dates`. See the module docstring."""
    if len(dates) <= min_train_months:
        raise ValueError(
            f"only {len(dates)} usable month ends; need more than min_train_months="
            f"{min_train_months} to form a test block"
        )
    first = dates[0]
    bounds = list(dates[min_train_months::test_months])
    folds = []
    for j, b in enumerate(bounds):
        test_end = bounds[j + 1] if j + 1 < len(bounds) else last_date
        if test_end <= b:
            continue
        folds.append(Fold(index=len(folds), train_start=first, train_end=b, test_end=test_end))
    return folds


def _select(scores: list[float]) -> int:
    """Index of the highest score; NaN counts as worst; ties go to the first."""
    arr = np.array([s if np.isfinite(s) else -np.inf for s in scores])
    return int(np.argmax(arr))


def execution_date(index: pd.DatetimeIndex, signal_date: pd.Timestamp, lag: int) -> pd.Timestamp:
    """The close at which a signal dated `signal_date` trades (capped at the last date)."""
    pos = min(index.get_loc(signal_date) + lag, len(index) - 1)
    return index[pos]


def fold_block(net: pd.Series, index: pd.DatetimeIndex, rec: FoldRecord, lag: int) -> pd.Series:
    """Returns earned by fold `rec`'s holdings.

    Fold j's holdings are bought at the close of exec(B_j) = B_j + lag days and
    held until the close of exec(B_j+1), so its market returns are the days in
    (exec(B_j), exec(B_j+1)]. Using (B_j, B_j+1] instead would credit the first
    `lag` days of each block to the previous fold's holdings. The cost of
    switching into fold j+1 is charged on exec(B_j+1), the last day here.
    """
    start = execution_date(index, rec.train_end, lag)
    is_last = rec.test_end == index[-1]
    end = index[-1] if is_last else execution_date(index, rec.test_end, lag)
    return net.loc[(net.index > start) & (net.index <= end)]


def run_walkforward(prices: pd.DataFrame, cfg: Config) -> WalkForwardResult:
    """Run the full walk-forward study for every configured strategy."""
    ex, st, wf = cfg.execution, cfg.statistics, cfg.walkforward
    warmup = max_required_rows(cfg)
    dates = signal_dates(prices, warmup)
    folds = make_folds(dates, prices.index[-1], wf.min_train_months, wf.test_months)
    first_signal = dates[0]
    oos_start = folds[0].train_end
    sim_prices = prices.loc[first_signal:]
    oos_prices = prices.loc[oos_start:]

    def backtest(px: pd.DataFrame, signals: pd.DataFrame) -> BacktestResult:
        return run_backtest(
            px, signals, ex.lag_days, ex.cost_bps, ex.cash_rate_annual, st.trading_days
        )

    runs: dict[str, StrategyRun] = {}
    n_configs = 0
    for name in strategy_names(cfg):
        grid = param_grid(cfg, name)
        n_configs += len(grid)
        all_signals, all_net, fallbacks = [], [], 0
        for params in grid:
            strat = build_strategy(cfg, name, params)
            sig = compute_signals(strat, prices, dates)
            fallbacks += len(getattr(strat, "fallback_dates", []))
            all_signals.append(sig)
            all_net.append(backtest(sim_prices, sig).net_returns)

        records, pieces = [], []
        for fold in folds:
            scores = [
                sharpe(net.loc[: fold.train_end], st.trading_days, ex.cash_rate_annual)
                for net in all_net
            ]
            best = _select(scores)
            in_block = (dates >= fold.train_end) & (dates < fold.test_end)
            if fold.index == len(folds) - 1:
                in_block = dates >= fold.train_end
            pieces.append(all_signals[best].loc[dates[in_block]])
            records.append(
                FoldRecord(
                    fold=fold.index,
                    train_start=fold.train_start,
                    train_end=fold.train_end,
                    test_end=fold.test_end,
                    params=grid[best],
                    params_label=param_label(grid[best]),
                    is_sharpe=scores[best],
                    oos_sharpe=float("nan"),
                )
            )
        stitched = pd.concat(pieces)
        oos = backtest(oos_prices, stitched)
        for rec in records:
            block = fold_block(oos.net_returns, oos_prices.index, rec, ex.lag_days)
            rec.oos_sharpe = sharpe(block, st.trading_days, ex.cash_rate_annual)
        runs[name] = StrategyRun(
            name=name,
            folds=records,
            signals=stitched,
            oos=oos,
            n_configs=len(grid),
            solver_fallbacks=fallbacks,
        )

    return WalkForwardResult(
        runs=runs,
        first_signal=first_signal,
        oos_start=oos_start,
        folds=folds,
        n_configs=n_configs,
        n_evaluations=n_configs * len(folds),
        warmup_rows=warmup,
    )


def rerun_oos(
    prices: pd.DataFrame,
    run: StrategyRun,
    oos_start: pd.Timestamp,
    cfg: Config,
    cost_bps: float | None = None,
    lag_days: int | None = None,
) -> BacktestResult:
    """Re-run a strategy's stitched OOS signals with a different cost or lag.

    Per-fold parameters stay fixed; only the frictions change.
    """
    ex = cfg.execution
    return run_backtest(
        prices.loc[oos_start:],
        run.signals,
        ex.lag_days if lag_days is None else lag_days,
        ex.cost_bps if cost_bps is None else cost_bps,
        ex.cash_rate_annual,
        cfg.statistics.trading_days,
    )


def folds_frame(result: WalkForwardResult) -> pd.DataFrame:
    """Per-fold records for every strategy, one row per (strategy, fold)."""
    rows = []
    for name, run in result.runs.items():
        for r in run.folds:
            rows.append(
                {
                    "strategy": name,
                    "fold": r.fold,
                    "train_end": r.train_end.date(),
                    "test_end": r.test_end.date(),
                    "params": r.params_label,
                    "is_sharpe": r.is_sharpe,
                    "oos_sharpe": r.oos_sharpe,
                }
            )
    return pd.DataFrame(rows)
