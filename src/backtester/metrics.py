"""Performance statistics on daily returns. Definitions are in docs/METHODS.md.

All functions take a Series of daily simple returns (net of costs unless the
caller passes something else). Annualization uses `trading_days` (252 by
default in the config). Statistics that are undefined, such as a Sharpe ratio
of a series with zero volatility, are returned as NaN instead of a fake number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

METRIC_ORDER = [
    "cagr",
    "ann_vol",
    "sharpe",
    "sortino",
    "max_drawdown",
    "calmar",
    "turnover",
    "best_month",
    "worst_month",
    "skew",
    "excess_kurtosis",
]


def daily_rate(annual_rate: float, trading_days: int) -> float:
    """Convert an annual rate into the equivalent compounded daily rate."""
    return (1.0 + annual_rate) ** (1.0 / trading_days) - 1.0


def cagr(returns: pd.Series, trading_days: int) -> float:
    """Compound annual growth rate: (prod(1 + r)) ** (trading_days / n) - 1."""
    n = len(returns)
    if n == 0:
        return float("nan")
    growth = float(np.prod(1.0 + returns.to_numpy()))
    if growth <= 0:
        return -1.0
    return growth ** (trading_days / n) - 1.0


def ann_vol(returns: pd.Series, trading_days: int) -> float:
    """Sample standard deviation of daily returns times sqrt(trading_days)."""
    if len(returns) < 2:
        return float("nan")
    return float(returns.std(ddof=1)) * np.sqrt(trading_days)


def sharpe(returns: pd.Series, trading_days: int, cash_rate_annual: float = 0.0) -> float:
    """Annualized Sharpe ratio of returns in excess of the cash rate.

    mean(r - rf) / std(r - rf) * sqrt(trading_days), with rf the daily cash
    rate. NaN if there are fewer than two observations or zero volatility.
    """
    if len(returns) < 2:
        return float("nan")
    excess = returns.to_numpy() - daily_rate(cash_rate_annual, trading_days)
    sd = excess.std(ddof=1)
    if not np.isfinite(sd) or sd < 1e-15:
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(trading_days))


def sortino(returns: pd.Series, trading_days: int) -> float:
    """Annualized Sortino ratio with a threshold of 0.

    mean(r) / downside_deviation * sqrt(trading_days), where the downside
    deviation is sqrt(mean(min(r, 0) ** 2)) over all days. NaN when there are
    no negative days.
    """
    if len(returns) == 0:
        return float("nan")
    r = returns.to_numpy()
    dd = np.sqrt(np.mean(np.minimum(r, 0.0) ** 2))
    if dd < 1e-15:
        return float("nan")
    return float(r.mean() / dd * np.sqrt(trading_days))


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Drawdown from the running peak of the equity curve, starting at 1."""
    equity = (1.0 + returns).cumprod()
    peak = np.maximum.accumulate(np.concatenate([[1.0], equity.to_numpy()]))[1:]
    return pd.Series(equity.to_numpy() / peak - 1.0, index=returns.index, name="drawdown")


def max_drawdown(returns: pd.Series) -> float:
    """Largest peak-to-trough fall, as a negative number (0 if never below a peak)."""
    if len(returns) == 0:
        return float("nan")
    return float(drawdown_series(returns).min())


def calmar(returns: pd.Series, trading_days: int) -> float:
    """CAGR divided by the absolute max drawdown. NaN when there is no drawdown."""
    mdd = max_drawdown(returns)
    if not np.isfinite(mdd) or mdd > -1e-15:
        return float("nan")
    return cagr(returns, trading_days) / abs(mdd)


def annual_turnover(turnover: pd.Series, n_days: int, trading_days: int) -> float:
    """Annual one-way turnover: 0.5 * sum of traded notional / years.

    `turnover` is the engine's two-way traded notional per rebalance, so 0.5
    converts it to one-way (a 100% swap of the portfolio counts once).
    """
    if n_days == 0:
        return float("nan")
    return 0.5 * float(turnover.sum()) / (n_days / trading_days)


def monthly_returns(returns: pd.Series) -> pd.Series:
    """Compound daily returns into calendar-month returns."""
    if len(returns) == 0:
        return pd.Series(dtype=float)
    months = returns.index.to_period("M")
    return (1.0 + returns).groupby(months).prod() - 1.0


def summarize(
    returns: pd.Series,
    turnover: pd.Series,
    trading_days: int,
    cash_rate_annual: float = 0.0,
) -> pd.Series:
    """All headline metrics for one return series, in METRIC_ORDER."""
    monthly = monthly_returns(returns)
    values = {
        "cagr": cagr(returns, trading_days),
        "ann_vol": ann_vol(returns, trading_days),
        "sharpe": sharpe(returns, trading_days, cash_rate_annual),
        "sortino": sortino(returns, trading_days),
        "max_drawdown": max_drawdown(returns),
        "calmar": calmar(returns, trading_days),
        "turnover": annual_turnover(turnover, len(returns), trading_days),
        "best_month": float(monthly.max()) if len(monthly) else float("nan"),
        "worst_month": float(monthly.min()) if len(monthly) else float("nan"),
        "skew": float(returns.skew()) if len(returns) > 2 else float("nan"),
        "excess_kurtosis": float(returns.kurt()) if len(returns) > 3 else float("nan"),
    }
    return pd.Series(values)[METRIC_ORDER]


def rolling_sharpe(
    returns: pd.Series, window: int, trading_days: int, cash_rate_annual: float = 0.0
) -> pd.Series:
    """Sharpe ratio over a trailing window of `window` days (NaN until full)."""
    excess = returns - daily_rate(cash_rate_annual, trading_days)
    mean = excess.rolling(window).mean()
    sd = excess.rolling(window).std(ddof=1)
    out = mean / sd * np.sqrt(trading_days)
    return out.where(sd > 1e-15)
