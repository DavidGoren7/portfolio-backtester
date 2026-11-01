"""Strategy behavior on hand-built and synthetic price histories."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtester.strategies import build_strategy, param_grid, strategy_names
from backtester.strategies import min_variance as mv_module
from backtester.strategies.base import InsufficientHistoryError
from backtester.strategies.inv_vol import InvVol
from backtester.strategies.min_variance import MinVariance
from backtester.strategies.momentum import XSMomentum
from backtester.strategies.trend import TrendSMA
from backtester.strategies.vol_target import VolTarget


def _frame(cols: dict[str, np.ndarray]) -> pd.DataFrame:
    n = len(next(iter(cols.values())))
    return pd.DataFrame(cols, index=pd.bdate_range("2020-01-01", periods=n))


def test_all_configured_strategies_are_long_only_and_capped(cfg, synth_prices):
    for name in strategy_names(cfg):
        for params in param_grid(cfg, name):
            strat = build_strategy(cfg, name, params)
            for end in (400, 600, 799):
                w = strat.target_weights(synth_prices.iloc[: end + 1])
                assert (w >= -1e-12).all(), (name, params)
                assert w.sum() <= 1 + 1e-9, (name, params)
                assert list(w.index) == list(synth_prices.columns)


def test_benchmarks(cfg, synth_prices):
    ew = build_strategy(cfg, "equal_weight", {}).target_weights(synth_prices)
    np.testing.assert_allclose(ew.to_numpy(), 1 / 7)
    sf = build_strategy(cfg, "sixty_forty", {}).target_weights(synth_prices)
    assert sf["SPY"] == pytest.approx(0.6)
    assert sf["AGG"] == pytest.approx(0.4)
    assert sf.sum() == pytest.approx(1.0)


def test_inv_vol_equal_vols_gives_equal_weights():
    # Same return path scaled differently has identical volatility.
    rng = np.random.default_rng(0)
    path = 100 * np.cumprod(1 + rng.normal(0, 0.01, 80))
    prices = _frame({"A": path, "B": 2 * path, "C": 3 * path})
    w = InvVol(window=60).target_weights(prices)
    np.testing.assert_allclose(w.to_numpy(), 1 / 3)


def test_inv_vol_prefers_low_vol():
    rng = np.random.default_rng(1)
    shocks = rng.normal(0, 0.01, 80)
    prices = _frame(
        {"calm": 100 * np.cumprod(1 + shocks), "wild": 100 * np.cumprod(1 + 3 * shocks)}
    )
    w = InvVol(window=60).target_weights(prices)
    assert w["calm"] == pytest.approx(0.75)
    assert w.sum() == pytest.approx(1.0)


def test_trend_sma_rising_fully_invested_falling_in_cash():
    n = 250
    up = np.linspace(100, 200, n)
    down = np.linspace(200, 100, n)
    w_up = TrendSMA(window=200).target_weights(_frame({"A": up, "B": up * 1.5}))
    w_down = TrendSMA(window=200).target_weights(_frame({"A": down, "B": down * 1.5}))
    assert w_up.sum() == pytest.approx(1.0)
    assert w_down.sum() == 0.0
    mixed = TrendSMA(window=200).target_weights(_frame({"A": up, "B": down}))
    assert mixed["A"] == pytest.approx(0.5) and mixed["B"] == 0.0


def test_xs_momentum_picks_known_winners():
    n = 300
    t = np.arange(n)
    prices = _frame(
        {
            "best": 100 * 1.003**t,
            "worst": 100 * 0.999**t,
            "second": 100 * 1.002**t,
            "third": 100 * 1.001**t,
        }
    )
    w = XSMomentum(lookback=126, top_k=2, skip=21).target_weights(prices)
    assert set(w[w > 0].index) == {"best", "second"}
    assert w["best"] == pytest.approx(0.5)


def test_xs_momentum_skip_ignores_recent_days():
    # "late" jumps only in the final 10 days, inside the skip window.
    n = 300
    base = np.full(n, 100.0)
    late = base.copy()
    late[-10:] = 300.0
    steady = 100 * 1.001 ** np.arange(n)
    prices = _frame({"late": late, "steady": steady})
    w = XSMomentum(lookback=126, top_k=1, skip=21).target_weights(prices)
    assert w["steady"] == 1.0


def test_min_variance_sums_to_one_and_prefers_low_vol(synth_prices):
    w = MinVariance(window=252).target_weights(synth_prices)
    assert w.sum() == pytest.approx(1.0)
    assert (w >= 0).all()
    # The calm bond (AGG) should carry the largest weight.
    assert w.idxmax() == "AGG"


def test_min_variance_falls_back_when_solver_fails(monkeypatch, synth_prices):
    class Failed:
        success = False
        x = np.full(7, np.nan)

    monkeypatch.setattr(mv_module, "minimize", lambda *a, **k: Failed())
    strat = MinVariance(window=126)
    w = strat.target_weights(synth_prices)
    expected = InvVol(window=126).target_weights(synth_prices)
    pd.testing.assert_series_equal(w, expected, check_names=False)
    assert strat.fallback_dates == [synth_prices.index[-1]]


def test_vol_target_scales_down_but_never_levers(synth_prices):
    base = TrendSMA(window=100)
    tiny = VolTarget(base=base, target_vol=0.001, cov_window=60, trading_days=252)
    huge = VolTarget(base=base, target_vol=5.0, cov_window=60, trading_days=252)
    raw = base.target_weights(synth_prices)
    assert tiny.target_weights(synth_prices).sum() < raw.sum()
    pd.testing.assert_series_equal(huge.target_weights(synth_prices), raw)


def test_vol_target_hits_target_when_binding(synth_prices):
    base = XSMomentum(lookback=63, top_k=2, skip=21)
    vt = VolTarget(base=base, target_vol=0.05, cov_window=60, trading_days=252)
    w = vt.target_weights(synth_prices).to_numpy()
    cov = synth_prices.iloc[-61:].pct_change().iloc[1:].cov().to_numpy()
    assert np.sqrt(252 * w @ cov @ w) == pytest.approx(0.05)


def test_insufficient_history_raises(synth_prices):
    with pytest.raises(InsufficientHistoryError):
        TrendSMA(window=200).target_weights(synth_prices.iloc[:50])


def test_min_variance_matches_two_asset_closed_form():
    # Regression: SLSQP used to stop at the equal-weight start on tiny daily
    # covariances. For two assets the long-only optimum is known in closed form.
    from backtester.strategies.min_variance import solve_min_variance

    s1, s2, rho = 0.01, 0.003, 0.2  # daily vols
    cov = np.array([[s1**2, rho * s1 * s2], [rho * s1 * s2, s2**2]])
    w1 = (s2**2 - rho * s1 * s2) / (s1**2 + s2**2 - 2 * rho * s1 * s2)
    np.testing.assert_allclose(solve_min_variance(cov), [w1, 1 - w1], atol=1e-5)
