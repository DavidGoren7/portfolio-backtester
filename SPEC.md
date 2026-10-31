# Portfolio Backtester (walk-forward, cost-aware)

## Goal
Build a small, rigorous backtesting library and study that compares simple long-only multi-asset strategies on liquid ETFs. It uses walk-forward parameter selection, realistic frictions (execution lag, transaction costs, weight drift), and statistical honesty (bootstrap confidence intervals, an explicit multiple-testing caveat). The methodology matters as much as the results.

## Audience
Hiring managers and recruiters in wealth management, capital markets, and risk analytics, data science, software developers. The README should read like a short research note by a careful junior quant, not a tutorial.

## Non-goals
Live trading, shorting, leverage above 1x, derivatives, intraday data, machine-learning price prediction, a web UI, and any claim that a strategy will make money.

## Data
- Default universe: SPY, EFA, EEM, AGG, TLT, GLD, VNQ. Daily adjusted close (splits and dividends adjusted, so returns are total returns). The common history starts around Nov 2004.
- Real data is fetched by the owner with `scripts/fetch_data.py` into `data/raw/<TICKER>.csv` with columns `date,adj_close`. It is gitignored because data vendor terms restrict redistribution.
- The loader (`data.py`) validates: dates sorted and unique, `adj_close` positive and non-null, gaps longer than 5 business days flagged, and common-history start and end reported per ticker. It aligns tickers on the intersection of dates and never forward-fills across gaps longer than 5 business days.
- Cash earns a constant annual rate from config (default 0%). This is a documented simplification.
- `synthetic.py` generates seeded, correlated price series with different drifts and volatilities and a built-in crash regime. It exists for tests and for `make demo`. Output from it is always labeled DEMO.
- Biases to state plainly in the README: the universe was chosen with hindsight (these ETFs exist and are liquid today), the sample is only about 20 years, and cash earns 0%.

## Library design
Package `src/backtester/`:
- `config.py`: load and validate `configs/default.yaml` into dataclasses. Fail loudly on unknown keys or bad values.
- `data.py`: load, validate, and align prices. Helpers for simple returns.
- `synthetic.py`: deterministic price generator.
- `engine.py`: the execution engine (see Execution semantics).
- `strategies/`: `base.py` (a Strategy protocol with `name`, `params`, and `target_weights(prices) -> pd.Series` that sees only prices up to and including the signal date), plus the strategies below.
- `metrics.py`: performance statistics.
- `bootstrap.py`: stationary bootstrap and confidence intervals.
- `walkforward.py`: expanding-window parameter selection and out-of-sample stitching.
- `report.py`: tables, figures, markdown report, and README results block.
- `cli.py` and `__main__.py`: commands `demo`, `run`, `report`.

### Execution semantics (the part that must be exactly right)
1. Rebalance dates are the last trading day of each month. The signal for a rebalance is computed from data up to and including that date's close.
2. Trades execute at the close of the trading day `lag_days` after the signal date (default 1). The trade uses that day's adjusted close.
3. Between rebalances, holdings drift with realized asset returns. There is no implicit daily rebalancing back to target weights.
4. At each rebalance, trade size per asset is the absolute difference between target weight and drifted weight. Cost is `cost_bps / 10000` times total traded notional (sum of absolute weight changes), deducted from portfolio value on the execution day.
5. Weights are long-only and sum to at most 1. Any remainder is cash earning `cash_rate_annual`.
6. The engine returns a result object with gross daily returns, net daily returns, daily post-drift weights, per-rebalance turnover, and per-rebalance cost.

### Strategies
All are long-only and monthly rebalanced. Each has a parameter grid in `configs/default.yaml`.
- `equal_weight`: 1/N across all assets. Benchmark, no tuning.
- `sixty_forty`: 60% SPY and 40% AGG. Benchmark, no tuning.
- `trend_sma(window)`: an asset is held if its price is above its simple moving average of `window` days. Held assets share weight 1/N each, so the rest sits in cash.
- `xs_momentum(lookback, top_k, skip)`: rank assets by total return from `t - lookback - skip` to `t - skip` (skip defaults to 21 days to avoid short-term reversal). Hold the top `top_k` equally.
- `inv_vol(window)`: weights proportional to 1 / trailing volatility, summing to 1.
- `min_variance(window)`: long-only minimum-variance weights summing to 1, using a Ledoit-Wolf shrunk covariance of trailing daily returns, solved with scipy SLSQP. Handle solver failure by falling back to inverse-volatility weights and logging it.
- `vol_target` overlay: scales a base strategy's weights by `min(1, target_vol / sqrt(252 * w' S w))`, where S is the trailing `cov_window`-day covariance. The leftover goes to cash. Applied to `trend_sma` and `xs_momentum` to create `trend_sma_vt` and `xs_momentum_vt`.

## Walk-forward protocol
- Expanding training window. The first training window is `min_train_months` (36). Each test block is `test_months` (12) long. Slide forward until data ends.
- For each tunable strategy and each fold, evaluate every parameter combination on the training window only, with costs, and pick the one with the highest net Sharpe. Apply it to the next test block unchanged.
- Strategies need warm-up history. Training metrics start only once all signals are defined. Benchmarks are evaluated over the same out-of-sample dates as the tuned strategies.
- Stitch test blocks into one out-of-sample return series per strategy. Headline results use only these.
- Record per fold: chosen parameters, in-sample Sharpe, and out-of-sample Sharpe.
- Record the total number of strategy-parameter trials evaluated. It feeds the multiple-testing caveat.

## Statistics
- Metrics on net returns: CAGR, annualized volatility, Sharpe (excess of the cash rate, annualized with sqrt(252)), Sortino (downside deviation, threshold 0), max drawdown, Calmar, annual one-way turnover (0.5 times sum of absolute weight changes per year), best and worst month, skew, excess kurtosis. Define each in `docs/METHODS.md`.
- Stationary bootstrap (Politis and Romano, 1994), mean block length 20 days, 5000 resamples, fixed seed. Report 95% percentile confidence intervals for each strategy's Sharpe and for the paired Sharpe difference versus `equal_weight` and versus `sixty_forty`, using the same resampled indices for both series.
- Stretch (do it only after everything else passes): the Deflated Sharpe Ratio (Bailey and Lopez de Prado, 2014), using the recorded number of trials. If implemented, describe its assumptions and limits in `docs/METHODS.md`. If not, say in the README that the multiple-testing issue is acknowledged but not corrected.
- Sensitivity: rerun the stitched out-of-sample series with per-fold parameters held fixed at the cost levels `[0, 2, 5, 10, 25]` bps, and at execution lag 1 and 2 days. Never report lag 0.
- Subperiods (out-of-sample only): the three windows in config (GFC, COVID, 2022). Report total return and max drawdown per strategy.

## Outputs
Written by `report.py` to `reports/<source>/` where source is `real` or `demo`:
- `tables/`: headline metrics, bootstrap confidence intervals, per-fold chosen parameters, cost sensitivity, lag sensitivity, subperiods (CSV and markdown).
- `figures/`: log equity curves with benchmarks, drawdowns, rolling 252-day Sharpe, weights over time for two strategies, chosen-parameter stability across folds, in-sample versus out-of-sample Sharpe by strategy, and Sharpe versus cost. Clean labels, readable at README width, consistent colors per strategy, no chartjunk.
- `report.md`: the above stitched into a readable note.
- Only `reports/real/` may feed the README results block, between the markers `<!-- RESULTS:START -->` and `<!-- RESULTS:END -->`. If no real data was used, that block says "NOT RUN ON REAL DATA" and nothing else.

## Tests (all offline, all synthetic)
Put these in `tests/`. Names are suggestions; coverage of the behaviors is required.
1. `test_data.py`: loader rejects unsorted dates, duplicate dates, NaN prices, and non-positive prices; flags long gaps.
2. `test_engine.py`:
   - One asset at weight 1, zero cost: net return equals the asset's return after the first execution.
   - Drift: two assets with no rebalance between dates; weights equal the analytic drifted weights.
   - Cost: moving from 100% cash to 100% one asset costs exactly `cost_bps` of portfolio value.
   - Constraints: weights are non-negative and sum to at most 1 within 1e-9.
   - Cash earns the configured rate.
3. `test_causality.py` (critical):
   - For every strategy, for a sample of dates, weights computed from the full price history equal weights computed from history truncated at that date.
   - Engine-level: changing prices strictly after date T must not change net returns up to and including T.
   - A deliberately cheating "oracle" strategy that peeks at future prices must FAIL the causality check. This proves the test can catch look-ahead.
4. `test_metrics.py`: hand-computed expected values on small series, including a drawdown example and constant-return edge cases.
5. `test_bootstrap.py`: same seed gives identical output; paired resampling uses identical indices; interval bounds are ordered; resampled series length matches input.
6. `test_walkforward.py`: train and test windows never overlap; chosen parameters are unchanged if test-period prices are perturbed; per-fold records are complete.
7. `test_strategies.py`: weights are long-only and sum to at most 1; `inv_vol` returns equal weights when volatilities are equal; `trend_sma` is fully invested on a steadily rising series and in cash on a steadily falling one; `xs_momentum` picks the known top performers; `min_variance` falls back correctly when the solver fails.
8. `test_config.py`: unknown keys and invalid values are rejected.
9. `test_cli_smoke.py`: `demo` on a tiny synthetic config finishes and writes expected files.

## Milestones
Each ends with `make check` passing and a commit.
1. M1 Config, data loader, synthetic generator. Check: `pytest tests/test_config.py tests/test_data.py`.
2. M2 Execution engine with lag, drift, costs, cash. Check: `pytest tests/test_engine.py`.
3. M3 Metrics. Check: `pytest tests/test_metrics.py`.
4. M4 Strategy base and all strategies including the overlay. Check: `pytest tests/test_strategies.py`.
5. M5 Causality tests across all strategies and the engine, including the oracle. Check: `pytest tests/test_causality.py`.
6. M6 Walk-forward selection and stitching. Check: `pytest tests/test_walkforward.py`.
7. M7 Bootstrap confidence intervals, sensitivity analyses, subperiods. Stretch: Deflated Sharpe. Check: `pytest tests/test_bootstrap.py`.
8. M8 CLI and end-to-end demo on synthetic data. Check: `make demo` completes and `pytest tests/test_cli_smoke.py` passes.
9. M9 Report generator: tables, figures, report.md, README results-block updater. Check: `make demo` writes all outputs under `reports/demo/`.
10. M10 Real-data run if `data/raw/` contains the seven CSVs, otherwise log the gap and skip. Never fake it.
11. M11 Documentation: README, `docs/METHODS.md` (the math, written clearly), `docs/WALKTHROUGH.md` (design walkthrough and the questions an interviewer would ask, each with a short answer pointing to code), CI workflow check, `ruff` clean.
12. M12 Final review (below).

## Final review
Start a fresh subagent with no memory of the implementation. Give it SPEC.md and the diff. Ask it to report only correctness gaps: look-ahead, cost accounting, weight drift, leakage in walk-forward selection, wrong metric definitions, and any place results could be overstated. Fix real findings and add a regression test for each. Ignore style preferences. Log the review and its outcome in DECISIONS.md.

## Done when
From a fresh clone with no network and no data:
- `make install && make check` passes.
- `make demo` writes the full set of outputs to `reports/demo/`, labeled DEMO.

With real data in `data/raw/`:
- `make run && make report` writes `reports/real/` and fills the README results block from code.

README must contain: one-paragraph summary; a generated key-results block; method summary; how to run in three commands; the design decisions that matter most; limitations (the biases listed under Data, the multiple-testing caveat, lag and cost assumptions, no taxes, no market impact); the sentence "Educational project, not investment advice."; and the line "Built by David Goren and Claude Code" 
