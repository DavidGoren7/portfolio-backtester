"""Load and validate the study configuration (configs/default.yaml).

Every tunable number in the study lives in the YAML file. This module turns it
into frozen dataclasses and fails loudly on unknown keys, missing keys, or bad
values, so a typo can never silently fall back to a default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

# Parameter names each tunable base strategy accepts, and whether each must be
# a positive integer (a window in trading days or a count of assets).
BASE_STRATEGY_PARAMS: dict[str, set[str]] = {
    "trend_sma": {"window"},
    "xs_momentum": {"lookback", "top_k", "skip"},
    "inv_vol": {"window"},
    "min_variance": {"window"},
}
INTEGER_PARAMS = {"window", "lookback", "top_k"}
NON_NEGATIVE_INTEGER_PARAMS = {"skip"}


class ConfigError(ValueError):
    """Raised when the configuration file is malformed."""


@dataclass(frozen=True)
class DataConfig:
    dir: str
    tickers: tuple[str, ...]
    max_gap_business_days: int


@dataclass(frozen=True)
class ExecutionConfig:
    rebalance: str
    lag_days: int
    cost_bps: float
    cash_rate_annual: float


@dataclass(frozen=True)
class WalkForwardConfig:
    scheme: str
    min_train_months: int
    test_months: int
    selection_metric: str


@dataclass(frozen=True)
class StatisticsConfig:
    trading_days: int
    bootstrap_reps: int
    bootstrap_mean_block: float
    ci_level: float
    seed: int


@dataclass(frozen=True)
class SensitivityConfig:
    cost_bps: tuple[float, ...]
    lag_days: tuple[int, ...]


@dataclass(frozen=True)
class SixtyFortyConfig:
    equity: str
    bond: str
    equity_weight: float


@dataclass(frozen=True)
class OverlayConfig:
    cov_window: int
    grid: dict[str, tuple[float, ...]]


@dataclass(frozen=True)
class StrategyConfig:
    """One tunable strategy family.

    For a plain strategy, `base` is None and `grid`/`fixed` hold its parameters.
    For a vol-target overlay, `base` names the strategy it wraps (whose grid and
    fixed values are reused) and `overlay` holds the overlay settings.
    """

    name: str
    grid: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    fixed: dict[str, Any] = field(default_factory=dict)
    base: str | None = None
    overlay: OverlayConfig | None = None

    @property
    def kind(self) -> str:
        """The underlying strategy type (the base name for overlays)."""
        return self.base if self.base is not None else self.name


@dataclass(frozen=True)
class DemoConfig:
    n_days: int
    n_assets: int
    seed: int


@dataclass(frozen=True)
class Config:
    data: DataConfig
    execution: ExecutionConfig
    walkforward: WalkForwardConfig
    statistics: StatisticsConfig
    sensitivity: SensitivityConfig
    subperiods: dict[str, tuple[pd.Timestamp, pd.Timestamp]]
    equal_weight: bool
    sixty_forty: SixtyFortyConfig
    strategies: dict[str, StrategyConfig]
    demo: DemoConfig

    def param_grid(self, name: str) -> list[dict[str, Any]]:
        """Every parameter combination for strategy family `name`.

        For an overlay the combinations are base grid x overlay grid, and each
        dict carries the overlay keys (`target_vol`, `cov_window`) alongside the
        base parameters.
        """
        spec = self.strategies[name]
        if spec.base is None:
            return _expand(spec.grid, spec.fixed)
        base = self.strategies[spec.base]
        assert spec.overlay is not None
        overlay_fixed = {"cov_window": spec.overlay.cov_window}
        combos = []
        for base_params in _expand(base.grid, base.fixed):
            for overlay_params in _expand(spec.overlay.grid, overlay_fixed):
                combos.append({**base_params, **overlay_params})
        return combos


def _expand(grid: dict[str, tuple[Any, ...]], fixed: dict[str, Any]) -> list[dict[str, Any]]:
    keys = list(grid)
    combos = []
    for values in product(*(grid[k] for k in keys)):
        combos.append({**dict(zip(keys, values, strict=True)), **fixed})
    return combos or [dict(fixed)]


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _require_keys(section: str, raw: Any, required: set[str], optional: set[str] = frozenset()):
    if not isinstance(raw, dict):
        raise ConfigError(f"{section}: expected a mapping, got {type(raw).__name__}")
    unknown = set(raw) - required - set(optional)
    if unknown:
        raise ConfigError(f"{section}: unknown key(s) {sorted(unknown)}")
    missing = required - set(raw)
    if missing:
        raise ConfigError(f"{section}: missing key(s) {sorted(missing)}")


def _pos_int(section: str, value: Any, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{section}: expected an integer, got {value!r}")
    if value < 0 or (value == 0 and not allow_zero):
        raise ConfigError(f"{section}: must be {'>= 0' if allow_zero else '> 0'}, got {value}")
    return value


def _number(section: str, value: Any, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{section}: expected a number, got {value!r}")
    if lo is not None and value < lo:
        raise ConfigError(f"{section}: must be >= {lo}, got {value}")
    if hi is not None and value > hi:
        raise ConfigError(f"{section}: must be <= {hi}, got {value}")
    return float(value)


def _list(section: str, value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{section}: expected a non-empty list, got {value!r}")
    return value


def _param_value(section: str, key: str, value: Any) -> Any:
    if key in INTEGER_PARAMS:
        return _pos_int(section, value)
    if key in NON_NEGATIVE_INTEGER_PARAMS:
        return _pos_int(section, value, allow_zero=True)
    raise ConfigError(f"{section}: unknown parameter {key!r}")


def _parse_strategy(name: str, raw: Any, n_tickers: int) -> StrategyConfig:
    section = f"strategies.{name}"
    if isinstance(raw, dict) and "base" in raw:
        _require_keys(section, raw, {"base", "overlay"})
        base = raw["base"]
        if base not in BASE_STRATEGY_PARAMS:
            raise ConfigError(f"{section}.base: unknown base strategy {base!r}")
        ov = raw["overlay"]
        _require_keys(f"{section}.overlay", ov, {"cov_window", "grid"})
        cov_window = _pos_int(f"{section}.overlay.cov_window", ov["cov_window"])
        if cov_window < 2:
            raise ConfigError(f"{section}.overlay.cov_window: need at least 2 days")
        _require_keys(f"{section}.overlay.grid", ov["grid"], {"target_vol"})
        vols = tuple(
            _number(f"{section}.overlay.grid.target_vol", v, lo=1e-6, hi=5.0)
            for v in _list(f"{section}.overlay.grid.target_vol", ov["grid"]["target_vol"])
        )
        return StrategyConfig(
            name=name,
            base=base,
            overlay=OverlayConfig(cov_window=cov_window, grid={"target_vol": vols}),
        )

    if name not in BASE_STRATEGY_PARAMS:
        raise ConfigError(f"{section}: unknown strategy {name!r}")
    _require_keys(section, raw, {"grid"}, {"fixed"})
    allowed = BASE_STRATEGY_PARAMS[name]
    grid: dict[str, tuple[Any, ...]] = {}
    for key, values in raw["grid"].items():
        if key not in allowed:
            raise ConfigError(f"{section}.grid: unknown parameter {key!r}")
        grid[key] = tuple(
            _param_value(f"{section}.grid.{key}", key, v) for v in _list(f"{section}.grid", values)
        )
    fixed: dict[str, Any] = {}
    for key, value in (raw.get("fixed") or {}).items():
        if key not in allowed:
            raise ConfigError(f"{section}.fixed: unknown parameter {key!r}")
        fixed[key] = _param_value(f"{section}.fixed.{key}", key, value)
    overlap = set(grid) & set(fixed)
    if overlap:
        raise ConfigError(f"{section}: {sorted(overlap)} appear in both grid and fixed")
    missing = allowed - set(grid) - set(fixed)
    if missing:
        raise ConfigError(f"{section}: missing parameter(s) {sorted(missing)}")
    for k in grid.get("top_k", ()):
        if k > n_tickers:
            raise ConfigError(f"{section}.grid.top_k: {k} exceeds the {n_tickers} tickers")
    return StrategyConfig(name=name, grid=grid, fixed=fixed)


def parse_config(raw: dict[str, Any]) -> Config:
    """Validate a raw YAML mapping and return a Config."""
    top = {
        "data",
        "execution",
        "walkforward",
        "statistics",
        "sensitivity",
        "subperiods",
        "benchmarks",
        "strategies",
        "demo",
    }
    _require_keys("config", raw, top)

    d = raw["data"]
    _require_keys("data", d, {"dir", "tickers", "max_gap_business_days"})
    tickers = tuple(str(t) for t in _list("data.tickers", d["tickers"]))
    if len(set(tickers)) != len(tickers):
        raise ConfigError("data.tickers: duplicate tickers")
    data = DataConfig(
        dir=str(d["dir"]),
        tickers=tickers,
        max_gap_business_days=_pos_int("data.max_gap_business_days", d["max_gap_business_days"]),
    )

    e = raw["execution"]
    _require_keys("execution", e, {"rebalance", "lag_days", "cost_bps", "cash_rate_annual"})
    if e["rebalance"] != "month_end":
        raise ConfigError("execution.rebalance: only 'month_end' is supported")
    execution = ExecutionConfig(
        rebalance="month_end",
        lag_days=_pos_int("execution.lag_days", e["lag_days"]),  # lag 0 is look-ahead
        cost_bps=_number("execution.cost_bps", e["cost_bps"], lo=0, hi=1000),
        cash_rate_annual=_number("execution.cash_rate_annual", e["cash_rate_annual"], -0.1, 0.5),
    )

    w = raw["walkforward"]
    _require_keys(
        "walkforward", w, {"scheme", "min_train_months", "test_months", "selection_metric"}
    )
    if w["scheme"] != "expanding":
        raise ConfigError("walkforward.scheme: only 'expanding' is supported")
    if w["selection_metric"] != "sharpe_net":
        raise ConfigError("walkforward.selection_metric: only 'sharpe_net' is supported")
    walkforward = WalkForwardConfig(
        scheme="expanding",
        min_train_months=_pos_int("walkforward.min_train_months", w["min_train_months"]),
        test_months=_pos_int("walkforward.test_months", w["test_months"]),
        selection_metric="sharpe_net",
    )

    s = raw["statistics"]
    _require_keys(
        "statistics",
        s,
        {"trading_days", "bootstrap_reps", "bootstrap_mean_block", "ci_level", "seed"},
    )
    statistics = StatisticsConfig(
        trading_days=_pos_int("statistics.trading_days", s["trading_days"]),
        bootstrap_reps=_pos_int("statistics.bootstrap_reps", s["bootstrap_reps"]),
        bootstrap_mean_block=_number(
            "statistics.bootstrap_mean_block", s["bootstrap_mean_block"], 1
        ),
        ci_level=_number("statistics.ci_level", s["ci_level"], 0.5, 0.999),
        seed=_pos_int("statistics.seed", s["seed"], allow_zero=True),
    )

    sens = raw["sensitivity"]
    _require_keys("sensitivity", sens, {"cost_bps", "lag_days"})
    lags = tuple(
        _pos_int("sensitivity.lag_days", v) for v in _list("sensitivity.lag_days", sens["lag_days"])
    )
    sensitivity = SensitivityConfig(
        cost_bps=tuple(
            _number("sensitivity.cost_bps", v, 0, 1000)
            for v in _list("sensitivity.cost_bps", sens["cost_bps"])
        ),
        lag_days=lags,
    )

    subperiods = {}
    if not isinstance(raw["subperiods"], dict):
        raise ConfigError("subperiods: expected a mapping")
    for name, window in raw["subperiods"].items():
        if not isinstance(window, list) or len(window) != 2:
            raise ConfigError(f"subperiods.{name}: expected [start, end]")
        try:
            start, end = pd.Timestamp(window[0]), pd.Timestamp(window[1])
        except (ValueError, TypeError) as exc:
            raise ConfigError(f"subperiods.{name}: bad date ({exc})") from exc
        if end <= start:
            raise ConfigError(f"subperiods.{name}: end must be after start")
        subperiods[str(name)] = (start, end)

    b = raw["benchmarks"]
    _require_keys("benchmarks", b, {"equal_weight", "sixty_forty"})
    if b["equal_weight"] not in ({}, None):
        raise ConfigError("benchmarks.equal_weight: takes no parameters")
    sf = b["sixty_forty"]
    _require_keys("benchmarks.sixty_forty", sf, {"equity", "bond", "equity_weight"})
    for key in ("equity", "bond"):
        if sf[key] not in tickers:
            raise ConfigError(f"benchmarks.sixty_forty.{key}: {sf[key]!r} is not in data.tickers")
    sixty_forty = SixtyFortyConfig(
        equity=sf["equity"],
        bond=sf["bond"],
        equity_weight=_number("benchmarks.sixty_forty.equity_weight", sf["equity_weight"], 0, 1),
    )

    if not isinstance(raw["strategies"], dict) or not raw["strategies"]:
        raise ConfigError("strategies: expected a non-empty mapping")
    reserved = {"equal_weight", "sixty_forty"}
    strategies: dict[str, StrategyConfig] = {}
    for name, spec in raw["strategies"].items():
        if name in reserved:
            raise ConfigError(f"strategies.{name}: name is reserved for a benchmark")
        strategies[name] = _parse_strategy(name, spec, len(tickers))
    for spec in strategies.values():
        if spec.base is not None and spec.base not in strategies:
            raise ConfigError(f"strategies.{spec.name}.base: {spec.base!r} has no grid configured")

    dm = raw["demo"]
    _require_keys("demo", dm, {"n_days", "n_assets", "seed"})
    demo = DemoConfig(
        n_days=_pos_int("demo.n_days", dm["n_days"]),
        n_assets=_pos_int("demo.n_assets", dm["n_assets"]),
        seed=_pos_int("demo.seed", dm["seed"], allow_zero=True),
    )
    if demo.n_assets != len(tickers):
        raise ConfigError("demo.n_assets: must equal the number of data.tickers")

    return Config(
        data=data,
        execution=execution,
        walkforward=walkforward,
        statistics=statistics,
        sensitivity=sensitivity,
        subperiods=subperiods,
        equal_weight=True,
        sixty_forty=sixty_forty,
        strategies=strategies,
        demo=demo,
    )


def load_config(path: str | Path) -> Config:
    """Read and validate a YAML config file."""
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return parse_config(raw)
