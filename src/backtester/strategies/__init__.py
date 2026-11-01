"""Strategy registry: build strategy objects from the config.

Adding a strategy: write a class implementing the Strategy protocol, register
its constructor in `_BUILDERS`, add its parameter names to
`config.BASE_STRATEGY_PARAMS`, and give it a grid in configs/default.yaml.
The causality tests pick it up automatically from the config.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backtester.config import Config
from backtester.strategies.base import Strategy, compute_signals, param_label
from backtester.strategies.benchmarks import EqualWeight, SixtyForty
from backtester.strategies.inv_vol import InvVol
from backtester.strategies.min_variance import MinVariance
from backtester.strategies.momentum import XSMomentum
from backtester.strategies.trend import TrendSMA
from backtester.strategies.vol_target import VolTarget

BENCHMARKS = ("equal_weight", "sixty_forty")

_BUILDERS: dict[str, Callable[..., Strategy]] = {
    "trend_sma": lambda p: TrendSMA(window=p["window"]),
    "xs_momentum": lambda p: XSMomentum(lookback=p["lookback"], top_k=p["top_k"], skip=p["skip"]),
    "inv_vol": lambda p: InvVol(window=p["window"]),
    "min_variance": lambda p: MinVariance(window=p["window"]),
}

_OVERLAY_KEYS = {"target_vol", "cov_window"}


def strategy_names(cfg: Config) -> list[str]:
    """Benchmarks first, then the configured strategies in file order."""
    return [*BENCHMARKS, *cfg.strategies]


def param_grid(cfg: Config, name: str) -> list[dict[str, Any]]:
    """Every parameter set to try for `name` (a single empty set for benchmarks)."""
    if name in BENCHMARKS:
        return [{}]
    return cfg.param_grid(name)


def build_strategy(cfg: Config, name: str, params: dict[str, Any]) -> Strategy:
    """Construct strategy `name` with `params`."""
    if name == "equal_weight":
        return EqualWeight()
    if name == "sixty_forty":
        sf = cfg.sixty_forty
        return SixtyForty(equity=sf.equity, bond=sf.bond, equity_weight=sf.equity_weight)
    spec = cfg.strategies[name]
    if spec.base is None:
        strat = _BUILDERS[spec.kind](params)
        strat.name = name
        return strat
    base_params = {k: v for k, v in params.items() if k not in _OVERLAY_KEYS}
    base = _BUILDERS[spec.kind](base_params)
    return VolTarget(
        base=base,
        target_vol=params["target_vol"],
        cov_window=params["cov_window"],
        trading_days=cfg.statistics.trading_days,
        name=name,
    )


def max_required_rows(cfg: Config) -> int:
    """The longest warm-up any configured strategy and parameter set needs."""
    return max(
        build_strategy(cfg, name, params).required_rows
        for name in strategy_names(cfg)
        for params in param_grid(cfg, name)
    )


__all__ = [
    "BENCHMARKS",
    "Strategy",
    "build_strategy",
    "compute_signals",
    "max_required_rows",
    "param_grid",
    "param_label",
    "strategy_names",
]
