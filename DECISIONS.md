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
