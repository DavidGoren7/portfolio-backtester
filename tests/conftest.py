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
