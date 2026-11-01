# Methods

The math behind every number in the reports. Notation: r_t is a daily simple return, n is the number of days, D = 252 trading days per year, and rf is the daily cash rate, rf = (1 + cash_rate_annual)^(1/D) - 1.

## Data

Daily adjusted closes p_t (splits and dividends adjusted), so r_t = p_t / p_(t-1) - 1 is a total return. Tickers are aligned on the dates they all share. Nothing is forward-filled. Gaps longer than 5 business days are reported.

## Execution

Let w_t be the end-of-day asset weights and c_t the cash weight, with w >= 0 and sum(w) + c = 1.

1. A signal is computed at the close of month-end day s from prices up to and including s.
2. It executes at the close of day s + L, where L is the lag (default 1).
3. Between executions holdings drift. If h_i is the value held in asset i at the close of day a, then at a later close t, h_i(t) = h_i(a) * p_i(t) / p_i(a), and cash grows by (1 + rf) per day.
4. At an execution, with drifted weights d and target weights w*, traded notional is T = sum_i |w*_i - d_i| and the cost is k = (cost_bps / 10000) * T. Portfolio value V becomes V(1 - k), and the new holdings are w* times that value.

Gross daily return is the change in value from the holdings. Net daily return is (1 + gross)(1 - k) - 1 on execution days and equals gross otherwise.

## Strategies

All are long-only, rebalanced at month ends, and see only prices up to the signal date.

- **Equal weight:** w_i = 1/N.
- **60/40:** 60% SPY, 40% AGG.
- **Trend (SMA window m):** hold asset i with weight 1/N if p_i(s) > mean of its last m closes; otherwise that 1/N stays in cash.
- **Cross-sectional momentum (lookback L, skip k, top K):** score_i = p_i(s - k) / p_i(s - k - L) - 1, counted in trading days. Hold the K highest scores at 1/K each.
- **Inverse volatility (window m):** w_i proportional to 1 / sigma_i, where sigma_i is the sample standard deviation of the last m daily returns.
- **Minimum variance (window m):** minimize w' S w subject to sum(w) = 1, 0 <= w_i <= 1. S is the Ledoit-Wolf shrunk covariance of the last m daily returns: a weighted average of the sample covariance and a scaled identity, with the weight chosen to minimize expected estimation error. Solved with SLSQP after dividing S by its average diagonal (a positive rescaling that leaves the answer unchanged). If the solver fails, inverse-volatility weights are used.
- **Vol-target overlay (target tau, window 60):** w_scaled = w * min(1, tau / sqrt(D * w' S w)), with S the sample covariance of the last 60 daily returns. The scale never exceeds 1, so there is no leverage.

## Walk-forward selection

Let B_0 < B_1 < ... be month ends, with B_0 = 36 month ends after the first common signal date and B_(j+1) = B_j + 12 month ends. Fold j trains on returns in (start, B_j] and tests on (B_j, B_(j+1)]. In each fold, every parameter set is scored by its net Sharpe on training returns, and the best is used for the signals dated in [B_j, B_(j+1)). The out-of-sample series is one engine run over (B_0, end] driven by those stitched signals.

## Metrics (net returns)

- **CAGR:** (prod_t (1 + r_t))^(D/n) - 1.
- **Annualized volatility:** std(r, ddof = 1) * sqrt(D).
- **Sharpe:** mean(r - rf) / std(r - rf, ddof = 1) * sqrt(D). Undefined (NaN) if the standard deviation is zero.
- **Sortino:** mean(r) / DD * sqrt(D), with downside deviation DD = sqrt((1/n) sum_t min(r_t, 0)^2), threshold 0.
- **Max drawdown:** with equity E_t = prod_(u <= t)(1 + r_u) and E_0 = 1, the minimum over t of E_t / max_(u <= t) E_u - 1.
- **Calmar:** CAGR / |max drawdown|.
- **Annual one-way turnover:** 0.5 * sum over executions of T, divided by the number of years n / D. The 0.5 counts a full swap of the portfolio once.
- **Best and worst month:** extremes of calendar-month compounded returns.
- **Skew and excess kurtosis:** bias-corrected sample estimators of daily returns. Excess kurtosis is 0 for a normal distribution.

## Stationary bootstrap

Politis and Romano (1994). Each resample is a sequence of n day indices. The first is uniform on {0, ..., n - 1}. Each later index starts a new block with probability p = 1/20 (a uniform random day), and otherwise continues the block (previous index + 1, wrapping around). Block lengths are therefore geometric with mean 20 days, which keeps the short-term dependence of daily returns, such as volatility clustering.

For each of 5000 resamples (fixed seed), the Sharpe ratio of every strategy is computed on the same indices. The 95% interval is the 2.5th to 97.5th percentile. For a strategy A and benchmark B, the paired difference Sharpe_A - Sharpe_B is computed on each resample, so both are measured on the same resampled market days.

"Share above zero" is the fraction of resamples where the difference is positive. It is a description of the bootstrap distribution, not a p-value.

Limits: percentile intervals can under-cover in small samples; the mean block length of 20 days is a judgment call; and the bootstrap cannot fix the fact that the sample contains only a few market regimes.

## Sensitivity and subperiods

Cost sensitivity reruns each strategy's stitched out-of-sample signals at 0, 2, 5, 10, and 25 bps. Lag sensitivity reruns them at lags 1 and 2. The per-fold parameter choices stay fixed (they were selected at 5 bps and lag 1), so these tables show how fragile the realized strategy is, not what re-tuning would do.

Subperiods report total return and max drawdown over out-of-sample days inside each window, plus the share of the window that is out-of-sample. A window is reported only if at least 90% of it is out-of-sample (`subperiod_min_coverage`); otherwise it would show the wrong part of a crisis.

Per-fold out-of-sample Sharpe ratios use the days earned by that fold's own holdings: (exec(B_j), exec(B_(j+1))], where exec(B) is the execution date of the signal at B.

## Multiple testing

The study tries 40 strategy-parameter combinations (including the two benchmarks). The best result among many tries is biased upward even if nothing works. The Deflated Sharpe Ratio (Bailey and Lopez de Prado, 2014) would correct for this, but it is not implemented, so the bias is acknowledged and not corrected. Walk-forward selection reduces the problem for each strategy family, but the choice of which families to show is still made by a human with hindsight.
