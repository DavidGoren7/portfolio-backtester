"""Load, validate, and align daily adjusted-close prices.

Each ticker lives in `<dir>/<TICKER>.csv` with columns `date,adj_close`.
Adjusted closes include splits and dividends, so simple returns computed from
them are total returns.

Alignment uses the intersection of dates across tickers. Nothing is ever
forward-filled: a date missing for any ticker is dropped for all of them.
Gaps longer than `max_gap_business_days` are reported, not filled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


class DataValidationError(ValueError):
    """Raised when a price series breaks one of the loader's rules."""


@dataclass(frozen=True)
class Gap:
    """A stretch with no prices longer than the allowed number of business days."""

    ticker: str
    before: pd.Timestamp
    after: pd.Timestamp
    business_days: int


@dataclass
class DataReport:
    """What the loader found, for the report and for the log."""

    start: dict[str, pd.Timestamp] = field(default_factory=dict)
    end: dict[str, pd.Timestamp] = field(default_factory=dict)
    rows: dict[str, int] = field(default_factory=dict)
    gaps: list[Gap] = field(default_factory=list)
    common_start: pd.Timestamp | None = None
    common_end: pd.Timestamp | None = None
    common_rows: int = 0


def validate_series(ticker: str, series: pd.Series) -> None:
    """Check one ticker's price series. Raises DataValidationError on failure.

    Rules: the index is a sorted, unique DatetimeIndex, and every price is a
    finite number strictly greater than zero.
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        raise DataValidationError(f"{ticker}: index must be dates")
    if series.index.has_duplicates:
        dup = series.index[series.index.duplicated()][0].date()
        raise DataValidationError(f"{ticker}: duplicate date {dup}")
    if not series.index.is_monotonic_increasing:
        raise DataValidationError(f"{ticker}: dates are not sorted ascending")
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any():
        bad = values.index[values.isna()][0].date()
        raise DataValidationError(f"{ticker}: missing or non-numeric price on {bad}")
    if not np.isfinite(values.to_numpy()).all():
        raise DataValidationError(f"{ticker}: non-finite price")
    if (values <= 0).any():
        bad = values.index[values <= 0][0].date()
        raise DataValidationError(f"{ticker}: non-positive price on {bad}")


def find_gaps(ticker: str, index: pd.DatetimeIndex, max_gap_business_days: int) -> list[Gap]:
    """Return gaps where consecutive dates are more than `max_gap_business_days` apart.

    The gap size counts business days strictly between the two dates plus one,
    so consecutive weekdays have a gap of 1 and Friday to Monday also has 1.
    """
    if len(index) < 2:
        return []
    dates = index.values.astype("datetime64[D]")
    days = np.busday_count(dates[:-1], dates[1:])
    gaps = []
    for i in np.flatnonzero(days > max_gap_business_days):
        gaps.append(Gap(ticker, index[i], index[i + 1], int(days[i])))
    return gaps


def read_ticker_csv(path: Path) -> pd.Series:
    """Read one `date,adj_close` CSV into a float Series indexed by date."""
    frame = pd.read_csv(path)
    missing = {"date", "adj_close"} - set(frame.columns)
    if missing:
        raise DataValidationError(f"{path.name}: missing column(s) {sorted(missing)}")
    index = pd.DatetimeIndex(pd.to_datetime(frame["date"]), name="date")
    return pd.Series(frame["adj_close"].to_numpy(), index=index, name=path.stem)


def align_prices(
    series: dict[str, pd.Series], max_gap_business_days: int
) -> tuple[pd.DataFrame, DataReport]:
    """Validate each series and align them on the intersection of their dates."""
    report = DataReport()
    for ticker, s in series.items():
        validate_series(ticker, s)
        report.start[ticker] = s.index[0]
        report.end[ticker] = s.index[-1]
        report.rows[ticker] = len(s)
        report.gaps.extend(find_gaps(ticker, s.index, max_gap_business_days))
    prices = pd.concat({t: s.astype(float) for t, s in series.items()}, axis=1, join="inner")
    prices.index.name = "date"
    if prices.empty:
        raise DataValidationError("tickers share no common dates")
    # Gaps can also appear in the aligned frame (one ticker missing a week).
    report.gaps.extend(find_gaps("ALIGNED", prices.index, max_gap_business_days))
    report.common_start = prices.index[0]
    report.common_end = prices.index[-1]
    report.common_rows = len(prices)
    return prices, report


def load_prices(
    data_dir: str | Path, tickers: tuple[str, ...] | list[str], max_gap_business_days: int
) -> tuple[pd.DataFrame, DataReport]:
    """Load every ticker from `data_dir`, validate, and align. Columns follow `tickers`."""
    data_dir = Path(data_dir)
    missing = [t for t in tickers if not (data_dir / f"{t}.csv").exists()]
    if missing:
        raise FileNotFoundError(
            f"No price file for {missing} in {data_dir}. "
            "Run `make data` on a machine with internet."
        )
    series = {t: read_ticker_csv(data_dir / f"{t}.csv") for t in tickers}
    prices, report = align_prices(series, max_gap_business_days)
    return prices[list(tickers)], report


def simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily simple returns p_t / p_{t-1} - 1. The first row is dropped."""
    return prices.pct_change().iloc[1:]
