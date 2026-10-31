"""Download daily adjusted closes into data/raw/<TICKER>.csv.

Run this on your own computer (it needs internet):

    python scripts/fetch_data.py
    python scripts/fetch_data.py --tickers SPY AGG --start 2004-01-01

Each CSV has two columns: date, adj_close. Prices are split and dividend
adjusted, so returns computed from them are total returns.

The data is for personal research. Do not commit it or redistribute it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DEFAULT_TICKERS = ["SPY", "EFA", "EEM", "AGG", "TLT", "GLD", "VNQ"]
DEFAULT_START = "2004-01-01"


def to_adj_close_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn a yfinance download (auto_adjust=True) into a date, adj_close frame."""
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or "Close" not in df.columns:
        raise ValueError("download returned no 'Close' column")
    out = df[["Close"]].rename(columns={"Close": "adj_close"}).dropna()
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out.index.name = "date"
    return out.sort_index()


def fetch(tickers: list[str], start: str, end: str | None, out_dir: Path) -> None:
    import yfinance as yf  # imported here so tests and CI never need it

    out_dir.mkdir(parents=True, exist_ok=True)
    for ticker in tickers:
        raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        try:
            frame = to_adj_close_frame(raw)
        except ValueError as exc:
            raise SystemExit(
                f"{ticker}: {exc}. Check your internet connection or the ticker."
            ) from exc
        frame.to_csv(out_dir / f"{ticker}.csv")
        print(f"{ticker}: {len(frame)} rows, {frame.index[0].date()} to {frame.index[-1].date()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=None)
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    fetch(args.tickers, args.start, args.end, args.out)


if __name__ == "__main__":
    main()
