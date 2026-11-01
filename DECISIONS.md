# Decisions log

Every non-obvious choice goes here: what, why, and what else was considered. The owner uses this file to prepare for interviews, so write for a second-year math student.

Format for new entries:

```
## <short title>
- Decision:
- Why:
- Alternatives considered:
- Where in the code:
```

## Seeded by the planning stage (already decided)

## Universe of seven ETFs
- Decision: SPY, EFA, EEM, AGG, TLT, GLD, VNQ.
- Why: liquid, long history (common start near Nov 2004), covers equities, bonds, gold, real estate, so the 2008 crash, 2020, and 2022 all fall in the sample.
- Alternatives considered: adding XIU.TO for a Canadian angle (needs currency handling, left as an extension); longer-history index data (licensing and splicing issues).
- Known weakness: chosen with hindsight, so survivorship bias is possible.

## One-day execution lag
- Decision: signal on close of day t, trade at close of day t + 1.
- Why: removes the most common look-ahead error (trading on the same close that produced the signal).
- Alternatives considered: next-day open (needs open prices); same-day close (look-ahead, rejected).

## Weights drift between rebalances
- Decision: holdings drift with returns; only rebalance dates trade.
- Why: a constant-mix backtest quietly rebalances every day and overstates turnover-free performance.
- Alternatives considered: daily rebalancing to target (simpler, less honest).

## Costs as basis points of traded notional
- Decision: default 5 bps per unit of traded notional, with sensitivity at 0, 2, 5, 10, 25 bps.
- Why: simple and transparent; the sensitivity table shows how fragile each strategy is.
- Alternatives considered: spread and impact models (too many unverifiable assumptions).

## Expanding walk-forward, 36 months minimum, 12-month test blocks
- Decision: tune on all history before each test block, then apply the choice unchanged.
- Why: mimics what an investor could have done; headline numbers are out-of-sample only.
- Alternatives considered: rolling window (discards early data), k-fold (leaks time order).

## Selection metric is net Sharpe
- Decision: choose parameters by in-sample Sharpe after costs.
- Why: standard and costs-aware.
- Alternatives considered: Calmar or CAGR (more sensitive to a single bad episode).

## Cash earns 0%
- Decision: constant annual cash rate in config, default 0.
- Why: avoids importing a rate series with its own data issues. It slightly understates cash-heavy strategies in high-rate periods.
- Alternatives considered: T-bill series (extra data dependency).

## Stationary bootstrap for confidence intervals
- Decision: Politis and Romano stationary bootstrap, mean block 20 days, 5000 resamples, paired for differences.
- Why: daily returns are autocorrelated in volatility; blocks preserve some dependence.
- Alternatives considered: iid bootstrap (too optimistic), analytic Sharpe standard error (assumes iid normal).

## Raw data is not committed
- Decision: `data/raw/` is gitignored.
- Why: data vendor terms restrict redistribution, and it keeps the repo small.
- Consequence: the overnight cloud run builds and tests everything on synthetic data; the owner runs the real-data study locally.

## Entries added during implementation
(Claude Code: append below this line.)

## Strategies all start on the same date
- Decision: every strategy and benchmark starts trading at the first month end where the strategy with the longest warm-up has enough history (274 trading days with the default grids, set by 12-month momentum plus the 21-day skip).
- Why: training windows, out-of-sample dates, and benchmark dates are then identical for every strategy, so comparisons are like for like. "Training metrics start only once all signals are defined" is satisfied for the slowest strategy, so it holds for all.
- Alternatives considered: a separate start per strategy (more data for fast strategies, but Sharpe ratios over different periods are not comparable).
- Where in the code: `strategies.max_required_rows`, `walkforward.signal_dates`.

## Month ends exclude the final, possibly incomplete month
- Decision: a date is a month end only if the next trading date is in a new month. The last date in the data is never a rebalance date.
- Why: if the data stops on the 14th, the 14th is not the end of the month. Treating it as one would add a rebalance that a real investor would not have made.
- Alternatives considered: a business-day calendar (needs exchange holiday data, an extra dependency).
- Where in the code: `engine.month_end_dates`.

## The portfolio starts in cash
- Decision: each engine run starts at value 1, all cash, at the close of its first date. The first trade happens at the first signal plus the lag. The out-of-sample run also starts in cash at the first test boundary.
- Why: it is the simplest honest starting state and it is the same for every strategy, benchmarks included. The cost of the first purchase is paid, like a real investor would.
- Cost of the choice: one day (two with lag 2) of cash at the start of the out-of-sample period, which is negligible over about 15 years.
- Where in the code: `engine.run_backtest`, `walkforward.run_walkforward`.

## How costs hit the portfolio
- Decision: on an execution day, cost = cost_bps / 10000 * sum |target - drifted|. Portfolio value is multiplied by (1 - cost), then the target weights are applied to what is left.
- Why: matches the spec's "cost deducted from portfolio value", and makes the identity (1 + net) = (1 + gross) * (1 - cost) exact, which the tests check.
- Alternatives considered: paying the cost from cash only (fails when the target is fully invested).
- Where in the code: `engine.run_backtest`.

## Gross returns and recorded weights
- Decision: gross returns are the returns of the holdings before costs; net returns subtract costs. The recorded daily weights are end-of-day weights after drift and after any trade that day.
- Why: gross minus net then isolates exactly what frictions cost. End-of-day weights are what the portfolio actually holds overnight.
- Where in the code: `engine.BacktestResult`.

## The engine loops over trades, not days
- Decision: between two executions, every holding just scales with its price relative to the segment start. The engine computes a whole segment with one array operation and loops only over execution dates.
- Why: CLAUDE.md asks to loop only over rebalance dates. A daily loop gives the same numbers but is slower and hides the math.
- Where in the code: `engine.run_backtest`.

## Training scores come from one full-history run per parameter set
- Decision: each parameter set is run once over the whole sample. Fold j scores it on returns up to B_j only.
- Why: the engine and strategies are causal, so returns up to B_j from a full run equal those from a run that stops at B_j. Running once is about 12 times faster than once per fold.
- Proof it does not leak: `tests/test_walkforward.py::test_chosen_params_ignore_test_period_prices` replaces all prices after B_j with a random path and checks every choice up to fold j is identical.
- Where in the code: `walkforward.run_walkforward`.

## The out-of-sample series is one engine run with stitched signals
- Decision: the chosen parameters for fold j produce the signals dated in [B_j, B_j+1). All folds' signals are joined and run through the engine once.
- Why: holdings carry over from one fold to the next, so when the chosen parameters change, the trade and its cost appear in the results. Gluing together separate per-parameter return series would silently skip those switching costs.
- Alternatives considered: concatenating each fold's returns from the per-parameter runs (simpler, slightly flattering).
- Where in the code: `walkforward.run_walkforward`.

## Which fold owns a boundary signal
- Decision: the signal dated exactly B_j uses fold j's parameters.
- Why: fold j was chosen with returns through B_j's close, and the signal at B_j is also computed at that close. Both use the same information, and the trade executes after B_j, inside the test block.
- Where in the code: `walkforward.run_walkforward` (`in_block`).

## Partial last test block
- Decision: the last fold tests from its boundary to the last date in the data, even if that is shorter than 12 months.
- Why: dropping it would throw away the most recent data. Per-fold Sharpe for a short block is noisy, which the fold table makes visible.

## Selection ties and undefined scores
- Decision: the highest training Sharpe wins; NaN counts as the worst; ties go to the first parameter set in the grid.
- Why: deterministic and conservative. A zero-volatility series (for example, all cash) has an undefined Sharpe and should never win.
- Where in the code: `walkforward._select`.

## Counting trials for the multiple-testing caveat
- Decision: report both the number of distinct strategy-parameter combinations (40 with the default config, including the two benchmarks) and the number of fold evaluations (combinations x folds).
- Why: distinct combinations are the "how many things did we try" number that multiple-testing corrections use. Evaluations show how much selection happened.
- Where in the code: `WalkForwardResult.n_configs`, `n_evaluations`.

## Min-variance: rescale the covariance before solving
- Decision: divide the covariance matrix by its average diagonal before SLSQP.
- Why: found by a test. Daily covariances are around 1e-5, below SLSQP's default stopping tolerance, so the solver "converged" at the equal-weight starting point and reported success. Scaling the objective by a positive constant does not change the minimizer. A regression test checks a two-asset case against the closed-form answer w1 = (s2^2 - rho s1 s2) / (s1^2 + s2^2 - 2 rho s1 s2).
- Alternatives considered: tightening `ftol` (works, but depends on the data's scale).
- Where in the code: `strategies/min_variance.py`.

## Solver failure and zero volatility
- Decision: if SLSQP fails or returns an infeasible point, min-variance uses inverse-volatility weights on the same window and records the date. If an asset has zero volatility, inverse-volatility uses equal weights.
- Why: both are documented, simple, long-only fallbacks. The report prints the number of fallbacks so they are not hidden.

## Vol-target overlay uses the sample covariance
- Decision: the overlay's S is the plain sample covariance of the last `cov_window` (60) days.
- Why: the spec says "trailing covariance" for the overlay and names Ledoit-Wolf only for min-variance. With 7 assets and 60 days the sample estimate is well defined.

## Momentum details
- Decision: lookback and skip count trading days (rows), not calendar days. Ties in past return go to the earlier column. The top_k assets are held even if all have negative past returns.
- Why: the spec says "hold the top_k equally". Adding an absolute-momentum filter would be a different strategy.

## Metric definitions
- Decision: Sharpe uses excess returns over the daily cash rate and the sample standard deviation (ddof 1). Sortino uses the raw mean over the downside deviation sqrt(mean(min(r, 0)^2)) with threshold 0, as the spec says. Skew and excess kurtosis use pandas' bias-corrected sample estimators. Ratios with a zero denominator are NaN, never a large fake number.
- Why: standard definitions, written out in docs/METHODS.md.

## Bootstrap implementation
- Decision: one set of resampled day indices per resample is applied to every strategy at once. Resamples run in batches of 250 to bound memory. The interval is the equal-tailed percentile interval. The report also gives the share of resamples where the Sharpe difference is above zero.
- Why: using the same indices for all strategies makes every pairwise difference paired, as the spec requires, and costs nothing extra. The percentile interval is simple to explain. The "share above zero" is easier to read than an interval but is not a p-value, and the docs say so.
- Alternatives considered: BCa intervals (better coverage in theory, harder to explain).

## Subperiods are out-of-sample only, with a coverage column
- Decision: each crisis window reports total return and max drawdown using out-of-sample days only, plus the share of the window that is out-of-sample. Windows before the out-of-sample start show no numbers.
- Why: with real data the out-of-sample period starts around the end of 2008, so the GFC window is only partly covered. Filling the gap with in-sample numbers would mix tuned and untuned results.

## Deflated Sharpe Ratio not implemented
- Decision: skipped the stretch goal. The README and report say the multiple-testing problem is acknowledged but not corrected.
- Why: doing it properly needs the variance of Sharpe ratios across all trials and assumptions about how independent the trials are. A half-correct version would be worse than an honest caveat.

## Synthetic data uses the real ticker names
- Decision: the demo generator names its 7 series SPY, EFA, and so on, with made-up drifts, volatilities, correlations, and a crash.
- Why: the 60/40 benchmark is defined by ticker (SPY and AGG), so the demo needs those names to run the same code path as the real study. Every demo output says DEMO in its title, banner, or folder, and a test proves a demo study can never write the README results block.
- Alternatives considered: names like SYN1 with a special-case 60/40 (more code paths, less tested).
- Where in the code: `synthetic.py`, `report.py`.

## run and report are separate steps
- Decision: `make run` saves the study to `reports/real/study.pkl`; `make report` loads it and writes tables, figures, report.md, and the README block.
- Why: the spec lists them as two commands. Re-rendering a report does not need the study re-run. Pickle files are gitignored, and the program only loads a pickle it wrote itself.

## Config is strict
- Decision: unknown or missing keys and bad values raise an error. lag_days must be at least 1, the momentum skip must be in the config (not a code default), and demo.n_assets must equal the number of tickers.
- Why: a typo should never silently change the study. Lag 0 is look-ahead, so it is impossible to configure.

## Causality tests check three ways, at mid-month cuts too
- Decision: the engine-level check perturbs prices after cut points that include mid-month days, not only rebalance dates.
- Why: found while writing the tests. With cuts only on rebalance dates, an oracle that peeks one month ahead was NOT caught, because its trades landed after the cut. With mid-month cuts it fails, as it must. The oracle tests now guard against this weakness coming back.
- Where in the code: `tests/test_causality.py`.

## M10 skipped: no real data in this environment
- Decision: the build environment has no market data (and should not try to download any), so M10 was skipped. The README results block says NOT RUN ON REAL DATA.
- Next step for the owner: `make data && make run && make report` on your own computer.
