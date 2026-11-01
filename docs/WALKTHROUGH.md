# Design walkthrough

A tour of the code in the order data flows through it, then the questions an interviewer is likely to ask, each with a short answer and where to look.

## How a run flows

1. **Config** (`src/backtester/config.py`). `configs/default.yaml` becomes frozen dataclasses. Unknown keys, missing keys, and bad values fail loudly. Lag 0 cannot be configured.
2. **Data** (`data.py`). One CSV per ticker. Each series must have sorted, unique dates and positive prices. Tickers are joined on their common dates without forward-filling; long gaps are reported.
3. **Strategies** (`strategies/`). Each strategy is a small class with `params`, `required_rows`, and `target_weights(prices)`. `compute_signals` hands each strategy `prices.loc[:date]`, so a strategy only ever sees history up to the signal date.
4. **Engine** (`engine.py`). Signals execute `lag_days` later at that day's close. Holdings drift between trades. Costs are charged on traded notional. The loop runs once per trade; each segment between trades is one array operation.
5. **Walk-forward** (`walkforward.py`). Every parameter set is run once over the whole sample. For each fold, the set with the best training Sharpe drives the next 12 months of signals. The stitched signals go through the engine once to make the out-of-sample series.
6. **Statistics** (`metrics.py`, `bootstrap.py`, `study.py`). Headline metrics, stationary bootstrap intervals, cost and lag sensitivity, crisis subperiods.
7. **Report** (`report.py`, `cli.py`). Tables, figures, `report.md`, and the README block (real data only).

## Questions an interviewer might ask

**How do you know there is no look-ahead bias?**
Three automated checks run on every strategy and parameter set in the config: weights from truncated history equal weights from full history; scrambling all prices after a date leaves earlier weights unchanged; and scrambling prices after a date leaves all earlier portfolio returns unchanged. A deliberately cheating "oracle" strategy must fail all three, which proves the checks can catch a leak. See `tests/test_causality.py`.

**Why trade one day after the signal?**
The signal uses the closing price of day t. You cannot also trade at that same close, because you only know it once it has printed. Trading at the next close is the simplest realistic option. Lag 2 is in the sensitivity table. See `engine.py` and DECISIONS.md.

**Why let weights drift instead of rebalancing daily?**
Daily rebalancing to fixed targets is trading you are not paying for. Drift is what a real portfolio does between monthly trades. `tests/test_engine.py::test_weights_drift_analytically_between_rebalances` checks drifted weights against the formula.

**How are transaction costs modeled, and what is missing?**
A fixed number of basis points times the sum of absolute weight changes. It ignores bid-ask spreads that widen in crises, market impact, and taxes. The cost sensitivity table shows how much each strategy depends on the cost assumption.

**What is walk-forward selection, and why not just pick the best parameters?**
Picking the best parameters on the full sample uses the future to choose. Walk-forward picks them using only data before each test year, then applies them unchanged. Only the out-of-sample years count in the headline numbers. See `walkforward.py`.

**Isn't scoring folds from one full-history run a leak?**
No, because the engine and strategies are causal: returns up to the fold boundary are the same whether or not later data exists. `test_chosen_params_ignore_test_period_prices` replaces all later prices with noise and checks the choices do not change.

**What happens when the chosen parameters change between folds?**
The portfolio carries its holdings into the new fold and trades to the new target, paying the cost. The out-of-sample series is one continuous engine run, not glued-together pieces.

**Why the stationary bootstrap instead of a normal standard error?**
Daily returns are not independent: volatility clusters, and returns have fat tails. The usual Sharpe standard error assumes independent normal returns. Resampling blocks of days keeps some of that dependence. Mean block length is 20 days. See `bootstrap.py` and `docs/METHODS.md`.

**What does a paired bootstrap give you?**
Strategies and benchmarks are resampled on the same days, so the interval for the Sharpe difference accounts for the fact that they move together. Two separate intervals that overlap do not tell you whether the difference is meaningful; the paired one does.

**Did you try many things and only show the best?**
40 combinations of strategy and parameters were tried, and the count is printed in every report. The Deflated Sharpe Ratio is not implemented, so the bias from trying many things is acknowledged but not corrected. The universe of ETFs was also chosen with hindsight.

**Why Ledoit-Wolf for minimum variance?**
With 7 assets and 126 to 252 days, the sample covariance is noisy, and the optimizer puts large weights where the noise makes risk look low. Shrinking toward a scaled identity reduces that error. `sklearn.covariance.LedoitWolf` picks the shrinkage amount from the data.

**Did you find any bugs while building this?**
Two, both caught by tests. SLSQP stopped at its starting point because daily covariances are tiny, so min-variance silently returned equal weights; rescaling the covariance fixed it, and a closed-form two-asset test guards it. And the first version of the engine-level look-ahead check only cut prices on rebalance dates, which let a one-month-ahead oracle slip through; cutting mid-month too fixed it. Both are in DECISIONS.md.

**What would you add next?**
A T-bill series for the cash rate, the Deflated Sharpe Ratio, a Canadian ETF universe with currency handling, and spread-based costs that widen in volatile markets.

**Is any of this strategy profitable?**
That is not something this project claims. It measures what these rules would have done, after costs, on about 20 years of one hand-picked universe, with intervals that are wide. Educational project, not investment advice.
