"""Shared fixtures. Everything here is synthetic and offline."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "default.yaml"


@pytest.fixture
def raw_config() -> dict:
    """A fresh, mutable copy of the default YAML as a dict."""
    return copy.deepcopy(yaml.safe_load(DEFAULT_CONFIG.read_text()))


@pytest.fixture
def default_config_path() -> Path:
    return DEFAULT_CONFIG


@pytest.fixture
def cfg(default_config_path):
    from backtester.config import load_config

    return load_config(default_config_path)


@pytest.fixture(scope="session")
def synth_prices():
    """About 3 years of seeded synthetic prices for the default 7 tickers."""
    from backtester.synthetic import generate_prices

    names = ["SPY", "EFA", "EEM", "AGG", "TLT", "GLD", "VNQ"]
    return generate_prices(800, names, seed=11)


def shrink_config(raw: dict) -> dict:
    """Make the default config small and fast for tests (same structure)."""
    raw["walkforward"]["min_train_months"] = 6
    raw["walkforward"]["test_months"] = 3
    raw["statistics"]["bootstrap_reps"] = 200
    s = raw["strategies"]
    s["trend_sma"]["grid"]["window"] = [20, 40]
    s["xs_momentum"]["grid"] = {"lookback": [21, 42], "top_k": [2]}
    s["xs_momentum"]["fixed"] = {"skip": 5}
    s["inv_vol"]["grid"]["window"] = [20]
    s["min_variance"]["grid"]["window"] = [40]
    for name in ("trend_sma_vt", "xs_momentum_vt"):
        s[name]["overlay"]["cov_window"] = 20
        s[name]["overlay"]["grid"]["target_vol"] = [0.08]
    raw["demo"]["n_days"] = 700
    return raw


@pytest.fixture
def small_cfg(raw_config):
    from backtester.config import parse_config

    return parse_config(shrink_config(raw_config))


@pytest.fixture
def small_raw_config(raw_config) -> dict:
    return shrink_config(raw_config)
