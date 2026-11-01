"""Run the whole study: walk-forward, metrics, bootstrap, sensitivity, subperiods.

This module only orchestrates. Each piece of math lives in its own module.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backtester.bootstrap import sharpe_confidence_intervals
from backtester.config import Config
from backtester.data import DataReport
from backtester.metrics import max_drawdown, sharpe, summarize
from backtester.strategies import BENCHMARKS
from backtester.walkforward import WalkForwardResult, folds_frame, rerun_oos, run_walkforward


@dataclass
class StudyResult:
    source: str  # "real" or "demo"
    walkforward: WalkForwardResult
    prices_start: pd.Timestamp
    prices_end: pd.Timestamp
    tickers: list[str]
    oos_net: pd.DataFrame  # strategies as columns
    headline: pd.DataFrame  # strategies x metrics
    sharpe_ci: pd.DataFrame
    diff_ci: pd.DataFrame
    folds: pd.DataFrame
    cost_sensitivity: pd.DataFrame  # strategies x cost levels, net Sharpe
    lag_sensitivity: pd.DataFrame  # strategies x lags, net Sharpe
    subperiods: pd.DataFrame
    data_report: DataReport | None
    config: Config


def subperiod_table(oos_net: pd.DataFrame, windows: dict, min_coverage: float) -> pd.DataFrame:
    """Total return and max drawdown per strategy inside each window, OOS only.

    `oos_coverage` is the share of the window's business days that fall inside
    the out-of-sample period. Numbers are reported only when coverage is at
    least `min_coverage`. A partly covered window would otherwise mislabel
    performance: with real data the OOS period starts around Dec 2008, so a
    "GFC" row would show only the 2009 rebound, not the crash.
    """
    rows = []
    for label, (start, end) in windows.items():
        window_days = pd.bdate_range(start, end)
        covered = oos_net.index[(oos_net.index >= start) & (oos_net.index <= end)]
        coverage = len(covered.intersection(window_days)) / max(len(window_days), 1)
        for name in oos_net.columns:
            r = oos_net.loc[covered, name]
            has = len(r) > 0 and coverage >= min_coverage
            status = "reported" if has else f"not reported: {coverage:.0%} out-of-sample"
            rows.append(
                {
                    "subperiod": label,
                    "start": start.date(),
                    "end": end.date(),
                    "oos_coverage": coverage,
                    "strategy": name,
                    "status": status,
                    "total_return": float((1 + r).prod() - 1) if has else np.nan,
                    "max_drawdown": max_drawdown(r) if has else np.nan,
                }
            )
    return pd.DataFrame(rows)


def run_study(
    prices: pd.DataFrame, cfg: Config, source: str, data_report: DataReport | None = None
) -> StudyResult:
    """Everything the report needs, computed from `prices` and `cfg`."""
    if source not in ("real", "demo"):
        raise ValueError("source must be 'real' or 'demo'")
    ex, st = cfg.execution, cfg.statistics
    wf = run_walkforward(prices, cfg)

    oos_net = pd.DataFrame({name: run.oos.net_returns for name, run in wf.runs.items()})
    headline = pd.DataFrame(
        {
            name: summarize(
                run.oos.net_returns, run.oos.turnover, st.trading_days, ex.cash_rate_annual
            )
            for name, run in wf.runs.items()
        }
    ).T
    headline.index.name = "strategy"

    sharpe_ci, diff_ci = sharpe_confidence_intervals(
        oos_net,
        list(BENCHMARKS),
        st.bootstrap_mean_block,
        st.bootstrap_reps,
        st.seed,
        st.ci_level,
        st.trading_days,
        ex.cash_rate_annual,
    )

    def oos_sharpe(name: str, **kw) -> float:
        res = rerun_oos(prices, wf.runs[name], wf.oos_start, cfg, **kw)
        return sharpe(res.net_returns, st.trading_days, ex.cash_rate_annual)

    cost_sens = pd.DataFrame(
        {
            f"{c:g} bps": {n: oos_sharpe(n, cost_bps=c) for n in wf.runs}
            for c in cfg.sensitivity.cost_bps
        }
    )
    lag_sens = pd.DataFrame(
        {
            f"lag {lag}": {n: oos_sharpe(n, lag_days=lag) for n in wf.runs}
            for lag in cfg.sensitivity.lag_days
        }
    )
    for frame in (cost_sens, lag_sens):
        frame.index.name = "strategy"

    return StudyResult(
        source=source,
        walkforward=wf,
        prices_start=prices.index[0],
        prices_end=prices.index[-1],
        tickers=list(prices.columns),
        oos_net=oos_net,
        headline=headline,
        sharpe_ci=sharpe_ci,
        diff_ci=diff_ci,
        folds=folds_frame(wf),
        cost_sensitivity=cost_sens,
        lag_sensitivity=lag_sens,
        subperiods=subperiod_table(oos_net, cfg.subperiods, st.subperiod_min_coverage),
        data_report=data_report,
        config=cfg,
    )
