"""Loader validation, gap flagging, alignment, and the synthetic generator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtester.data import (
    DataValidationError,
    align_prices,
    find_gaps,
    load_prices,
    simple_returns,
    validate_series,
)
from backtester.synthetic import generate_prices


def _series(values, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def test_valid_series_passes():
    validate_series("X", _series([1.0, 2.0, 3.0]))


def test_rejects_unsorted_dates():
    s = _series([1.0, 2.0, 3.0])
    s = s.iloc[[1, 0, 2]]
    with pytest.raises(DataValidationError, match="sorted"):
        validate_series("X", s)


def test_rejects_duplicate_dates():
    s = _series([1.0, 2.0, 3.0])
    s.index = pd.DatetimeIndex([s.index[0], s.index[0], s.index[2]])
    with pytest.raises(DataValidationError, match="duplicate"):
        validate_series("X", s)


def test_rejects_nan_price():
    with pytest.raises(DataValidationError, match="missing"):
        validate_series("X", _series([1.0, np.nan, 3.0]))


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_rejects_non_positive_price(bad):
    with pytest.raises(DataValidationError, match="non-positive"):
        validate_series("X", _series([1.0, bad, 3.0]))


def test_flags_long_gaps_only():
    idx = pd.DatetimeIndex(["2020-01-03", "2020-01-06", "2020-01-20", "2020-01-21"])
    gaps = find_gaps("X", idx, max_gap_business_days=5)
    # Fri to Mon is 1 business day (fine); Mon 6th to Mon 20th is 10 (flagged).
    assert len(gaps) == 1
    assert gaps[0].before == pd.Timestamp("2020-01-06")
    assert gaps[0].business_days == 10


def test_align_uses_intersection_without_filling():
    a = _series([1.0, 2.0, 3.0, 4.0])
    b = _series([10.0, 20.0, 30.0, 40.0]).drop(a.index[1])
    prices, report = align_prices({"A": a, "B": b}, max_gap_business_days=5)
    assert len(prices) == 3
    assert a.index[1] not in prices.index
    assert not prices.isna().any().any()
    assert report.common_rows == 3
    assert report.rows == {"A": 4, "B": 3}


def test_load_prices_from_csv(tmp_path):
    for ticker, values in {"A": [1.0, 2.0, 3.0], "B": [5.0, 4.0, 3.0]}.items():
        s = _series(values)
        pd.DataFrame({"date": s.index.strftime("%Y-%m-%d"), "adj_close": s.values}).to_csv(
            tmp_path / f"{ticker}.csv", index=False
        )
    prices, _ = load_prices(tmp_path, ["B", "A"], 5)
    assert list(prices.columns) == ["B", "A"]
    assert prices.shape == (3, 2)


def test_load_prices_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="make data"):
        load_prices(tmp_path, ["SPY"], 5)


def test_simple_returns():
    prices = pd.DataFrame({"A": _series([100.0, 110.0, 99.0])})
    r = simple_returns(prices)
    np.testing.assert_allclose(r["A"].to_numpy(), [0.10, -0.10])


def test_synthetic_is_deterministic_and_valid():
    names = ["A", "B", "C", "D", "E", "F", "G"]
    p1 = generate_prices(500, names, seed=3)
    p2 = generate_prices(500, names, seed=3)
    p3 = generate_prices(500, names, seed=4)
    pd.testing.assert_frame_equal(p1, p2)
    assert not p1.equals(p3)
    assert (p1 > 0).all().all()
    assert list(p1.columns) == names
    for c in names:
        validate_series(c, p1[c])
