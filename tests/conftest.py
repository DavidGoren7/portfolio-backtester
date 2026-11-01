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
