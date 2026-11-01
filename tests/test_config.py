"""Config loading rejects unknown keys and invalid values."""

from __future__ import annotations

import pytest

from backtester.config import ConfigError, load_config, parse_config


def test_default_config_loads(default_config_path):
    cfg = load_config(default_config_path)
    assert cfg.execution.lag_days == 1
    assert cfg.data.tickers[0] == "SPY"
    assert len(cfg.param_grid("xs_momentum")) == 8
    # Overlay grid is base grid x overlay grid, with the overlay keys attached.
    vt = cfg.param_grid("trend_sma_vt")
    assert len(vt) == 6
    assert {"window", "target_vol", "cov_window"} <= set(vt[0])


@pytest.mark.parametrize(
    "path",
    [
        ("execution", "lag_dayz"),
        ("statistics", "unexpected"),
        (None, "extra_section"),
        ("strategies", "trend_sma", "grid", "windw"),
    ],
)
def test_unknown_keys_rejected(raw_config, path):
    node = raw_config
    for key in path[:-1]:
        if key is not None:
            node = node[key]
    node[path[-1]] = 1
    with pytest.raises(ConfigError, match="unknown"):
        parse_config(raw_config)


def test_missing_key_rejected(raw_config):
    del raw_config["execution"]["cost_bps"]
    with pytest.raises(ConfigError, match="missing"):
        parse_config(raw_config)


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("execution", "lag_days", 0),  # same-close trading is look-ahead
        ("execution", "lag_days", -1),
        ("execution", "cost_bps", -5),
        ("execution", "cost_bps", "five"),
        ("execution", "rebalance", "weekly"),
        ("statistics", "bootstrap_reps", 0),
        ("statistics", "ci_level", 1.5),
        ("walkforward", "scheme", "rolling"),
        ("walkforward", "test_months", 0),
        ("demo", "n_assets", 3),
    ],
)
def test_invalid_values_rejected(raw_config, section, key, value):
    raw_config[section][key] = value
    with pytest.raises(ConfigError):
        parse_config(raw_config)


def test_bad_strategy_values_rejected(raw_config):
    raw_config["strategies"]["xs_momentum"]["grid"]["top_k"] = [2, 99]
    with pytest.raises(ConfigError, match="top_k"):
        parse_config(raw_config)


def test_bad_overlay_base_rejected(raw_config):
    raw_config["strategies"]["trend_sma_vt"]["base"] = "not_a_strategy"
    with pytest.raises(ConfigError):
        parse_config(raw_config)


def test_sixty_forty_ticker_must_exist(raw_config):
    raw_config["benchmarks"]["sixty_forty"]["bond"] = "BND"
    with pytest.raises(ConfigError, match="sixty_forty"):
        parse_config(raw_config)


def test_bad_subperiod_rejected(raw_config):
    raw_config["subperiods"]["gfc"] = ["2009-01-01", "2008-01-01"]
    with pytest.raises(ConfigError, match="subperiods"):
        parse_config(raw_config)
