"""Scaffold check: the package imports and the default config parses as YAML."""

from pathlib import Path

import yaml

import backtester


def test_package_imports():
    assert backtester.__version__


def test_default_config_is_valid_yaml():
    path = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    cfg = yaml.safe_load(path.read_text())
    assert cfg["execution"]["lag_days"] >= 1
    assert len(cfg["data"]["tickers"]) == 7
