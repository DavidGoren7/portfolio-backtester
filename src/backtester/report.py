"""Write tables, figures, report.md, and the README results block.

Outputs go to `reports/<source>/`. Demo outputs are labeled DEMO everywhere
(file banner, figure titles, report heading). Only a study whose source is
"real" can write the README results block; anything else is refused.
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtester.metrics import drawdown_series, rolling_sharpe  # noqa: E402
from backtester.strategies import BENCHMARKS, param_grid  # noqa: E402
from backtester.study import StudyResult  # noqa: E402

RESULTS_START = "<!-- RESULTS:START -->"
RESULTS_END = "<!-- RESULTS:END -->"
NOT_RUN = "NOT RUN ON REAL DATA"
DEMO_BANNER = (
    "DEMO: every number here comes from SYNTHETIC data. It says nothing about real markets."
)

PERCENT_METRICS = {"cagr", "ann_vol", "max_drawdown", "turnover", "best_month", "worst_month"}
METRIC_LABELS = {
    "cagr": "CAGR",
    "ann_vol": "Vol",
    "sharpe": "Sharpe",
    "sortino": "Sortino",
    "max_drawdown": "Max DD",
    "calmar": "Calmar",
    "turnover": "Turnover/yr",
    "best_month": "Best month",
    "worst_month": "Worst month",
    "skew": "Skew",
    "excess_kurtosis": "Excess kurt.",
}
# Benchmarks in neutral tones, strategies in distinct colors, fixed per name.
_PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b"]
_BENCH_COLORS = {"equal_weight": "#555555", "sixty_forty": "#aaaaaa"}
CASH_COLOR = "#e6e6e6"
ROLLING_WINDOW_DAYS = 252
FIG_SIZE = (10, 4.5)
FIG_DPI = 120


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt(value, pct: bool = False) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    if isinstance(value, (int, float, np.floating)):
        return f"{value:.1%}" if pct else f"{value:.2f}"
    return str(value)


def markdown_table(
    frame: pd.DataFrame, pct_cols: set[str] = frozenset(), index: bool = True
) -> str:
    """Render a DataFrame as a GitHub markdown table (no extra dependencies)."""
    df = frame.reset_index() if index else frame
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    lines = [header, sep]
    for _, row in df.iterrows():
        cells = [_fmt(row[c], pct=c in pct_cols) for c in df.columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def strategy_colors(names: list[str]) -> dict[str, str]:
    colors, i = {}, 0
    for n in names:
        if n in _BENCH_COLORS:
            colors[n] = _BENCH_COLORS[n]
        else:
            colors[n] = _PALETTE[i % len(_PALETTE)]
            i += 1
    return colors


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def headline_display(study: StudyResult) -> pd.DataFrame:
    return study.headline.rename(columns=METRIC_LABELS)


def tables(study: StudyResult) -> dict[str, tuple[pd.DataFrame, set[str], bool]]:
    """name -> (frame, percent columns, write index)."""
    pct_labels = {METRIC_LABELS[m] for m in PERCENT_METRICS}
    out = {
        "headline_metrics": (headline_display(study), pct_labels, True),
        "sharpe_ci": (study.sharpe_ci, set(), True),
        "sharpe_diff_ci": (study.diff_ci, {"share_above_zero"}, True),
        "fold_parameters": (study.folds, set(), False),
        "cost_sensitivity": (study.cost_sensitivity, set(), True),
        "lag_sensitivity": (study.lag_sensitivity, set(), True),
        "subperiods": (study.subperiods, {"oos_coverage", "total_return", "max_drawdown"}, False),
    }
    if study.data_report is not None:
        dr = study.data_report
        frame = pd.DataFrame(
            {
                "first_date": {t: d.date() for t, d in dr.start.items()},
                "last_date": {t: d.date() for t, d in dr.end.items()},
                "rows": dr.rows,
            }
        )
        frame.index.name = "ticker"
        out["data_summary"] = (frame, set(), True)
    return out


def write_tables(study: StudyResult, out_dir: Path) -> list[Path]:
    tdir = out_dir / "tables"
    tdir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (frame, pct, index) in tables(study).items():
        csv = tdir / f"{name}.csv"
        frame.to_csv(csv, index=index)
        md = tdir / f"{name}.md"
        banner = f"> {DEMO_BANNER}\n\n" if study.source == "demo" else ""
        md.write_text(banner + markdown_table(frame, pct, index) + "\n")
        written += [csv, md]
    return written


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _title(study: StudyResult, text: str) -> str:
    return f"DEMO (synthetic data): {text}" if study.source == "demo" else text


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=FIG_DPI)
    plt.close(fig)
    return path


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)


def _legend(ax) -> None:
    """Legend outside the plot area on the right, so it never hides data."""
    ax.legend(fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0))


def _line_kwargs(name: str, colors: dict[str, str]) -> dict:
    bench = name in BENCHMARKS
    return {"color": colors[name], "lw": 1.6 if bench else 1.2, "ls": "--" if bench else "-"}


def fig_equity(study: StudyResult, colors, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    equity = (1 + study.oos_net).cumprod()
    for name in equity.columns:
        ax.plot(equity.index, equity[name], label=name, **_line_kwargs(name, colors))
    ax.set_yscale("log")
    ax.set_ylabel("Growth of 1 (log scale)")
    ax.set_title(_title(study, "Out-of-sample equity, net of costs"))
    _legend(ax)
    _style(ax)
    return _save(fig, path)


def fig_drawdowns(study: StudyResult, colors, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    for name in study.oos_net.columns:
        dd = drawdown_series(study.oos_net[name])
        ax.plot(dd.index, dd * 100, label=name, **_line_kwargs(name, colors))
    ax.set_ylabel("Drawdown (%)")
    ax.set_title(_title(study, "Drawdown from running peak"))
    _legend(ax)
    _style(ax)
    return _save(fig, path)


def fig_rolling_sharpe(study: StudyResult, colors, path: Path) -> Path:
    st, ex = study.config.statistics, study.config.execution
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    for name in study.oos_net.columns:
        rs = rolling_sharpe(
            study.oos_net[name], ROLLING_WINDOW_DAYS, st.trading_days, ex.cash_rate_annual
        )
        ax.plot(rs.index, rs, label=name, **_line_kwargs(name, colors))
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Sharpe, trailing 252 days")
    ax.set_title(_title(study, "Rolling one-year Sharpe ratio"))
    _legend(ax)
    _style(ax)
    return _save(fig, path)


def fig_weights(study: StudyResult, name: str, path: Path) -> Path:
    w = study.walkforward.runs[name].oos.weights
    w = w.assign(cash=(1 - w.sum(axis=1)).clip(lower=0))
    asset_colors = [plt.get_cmap("tab10")(i) for i in range(w.shape[1] - 1)]
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.stackplot(
        w.index, w.T.to_numpy(), labels=w.columns, colors=[*asset_colors, CASH_COLOR], alpha=0.9
    )
    ax.set_ylim(0, 1)
    ax.set_ylabel("Weight")
    ax.set_title(_title(study, f"Daily weights after drift: {name}"))
    _legend(ax)
    _style(ax)
    return _save(fig, path)


def fig_param_stability(study: StudyResult, colors, path: Path) -> Path:
    tuned = [n for n in study.walkforward.runs if n not in BENCHMARKS]
    fig, axes = plt.subplots(len(tuned), 1, figsize=(9, 1.3 * len(tuned) + 1), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, name in zip(axes, tuned, strict=True):
        folds = study.folds[study.folds["strategy"] == name]
        grid = param_grid(study.config, name)
        varying = [k for k in grid[0] if len({str(g[k]) for g in grid}) > 1]
        chosen = [r.params for r in study.walkforward.runs[name].folds]
        short = [", ".join(f"{k}={p[k]}" for k in varying) or "-" for p in chosen]
        order = [", ".join(f"{k}={g[k]}" for k in varying) or "-" for g in grid]
        labels = [lab for lab in dict.fromkeys(order) if lab in short]
        codes = [labels.index(lab) for lab in short]
        ax.step(folds["fold"], codes, where="mid", color=colors[name])
        ax.scatter(folds["fold"], codes, color=colors[name], s=12)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=7)
        ax.set_title(name, fontsize=9, loc="left")
        _style(ax)
    axes[-1].set_xlabel("Fold")
    fig.suptitle(_title(study, "Chosen parameters by fold (only parameters that vary)"))
    return _save(fig, path)


def fig_is_vs_oos(study: StudyResult, colors, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    tuned = study.folds[~study.folds["strategy"].isin(BENCHMARKS)]
    for name, grp in tuned.groupby("strategy", sort=False):
        ax.scatter(grp["is_sharpe"], grp["oos_sharpe"], label=name, color=colors[name], s=18)
    vals = tuned[["is_sharpe", "oos_sharpe"]].to_numpy(dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals):
        lo, hi = float(vals.min()), float(vals.max())
        ax.plot([lo, hi], [lo, hi], color="black", lw=0.8, ls=":")
    ax.axhline(0, color="grey", lw=0.6)
    ax.set_xlabel("In-sample Sharpe (chosen parameters)")
    ax.set_ylabel("Out-of-sample Sharpe (next block)")
    ax.set_title(_title(study, "In-sample vs out-of-sample, per fold"))
    _legend(ax)
    _style(ax)
    return _save(fig, path)


def fig_sharpe_vs_cost(study: StudyResult, colors, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    costs = list(study.config.sensitivity.cost_bps)
    for name, row in study.cost_sensitivity.iterrows():
        ax.plot(costs, row.to_numpy(), marker="o", label=name, **_line_kwargs(name, colors))
    ax.set_xlabel("Cost (bps of traded notional)")
    ax.set_ylabel("Out-of-sample Sharpe")
    ax.set_title(_title(study, "Sharpe ratio versus transaction cost"))
    _legend(ax)
    _style(ax)
    return _save(fig, path)


def weight_figure_strategies(study: StudyResult) -> list[str]:
    preferred = ["min_variance", "xs_momentum_vt"]
    names = [n for n in preferred if n in study.walkforward.runs]
    tuned = [n for n in study.walkforward.runs if n not in BENCHMARKS and n not in names]
    return (names + tuned)[:2]


def write_figures(study: StudyResult, out_dir: Path) -> list[Path]:
    fdir = out_dir / "figures"
    fdir.mkdir(parents=True, exist_ok=True)
    colors = strategy_colors(list(study.walkforward.runs))
    paths = [
        fig_equity(study, colors, fdir / "equity.png"),
        fig_drawdowns(study, colors, fdir / "drawdowns.png"),
        fig_rolling_sharpe(study, colors, fdir / "rolling_sharpe.png"),
        fig_param_stability(study, colors, fdir / "param_stability.png"),
        fig_is_vs_oos(study, colors, fdir / "is_vs_oos.png"),
        fig_sharpe_vs_cost(study, colors, fdir / "sharpe_vs_cost.png"),
    ]
    for name in weight_figure_strategies(study):
        paths.append(fig_weights(study, name, fdir / f"weights_{name}.png"))
    return paths


# ---------------------------------------------------------------------------
# report.md and the README block
# ---------------------------------------------------------------------------


def _period_line(study: StudyResult) -> str:
    oos = study.oos_net.index
    wf = study.walkforward
    return (
        f"Prices {study.prices_start.date()} to {study.prices_end.date()}. "
        f"Out-of-sample {oos[0].date()} to {oos[-1].date()} ({len(oos)} trading days, "
        f"{len(wf.folds)} folds). {wf.n_configs} strategy-parameter combinations were tried, "
        f"{wf.n_evaluations} fold evaluations in total."
    )


def _setup_line(study: StudyResult) -> str:
    ex = study.config.execution
    return (
        f"Net of {ex.cost_bps:g} bps per unit traded, lag {ex.lag_days} day(s), "
        f"cash at {ex.cash_rate_annual:.1%} a year, monthly rebalancing. "
        f"Sharpe intervals: {study.config.statistics.ci_level:.0%} stationary bootstrap, "
        f"{study.config.statistics.bootstrap_reps} resamples."
    )


def results_block(study: StudyResult) -> str:
    """The README key-results text. Generated from a real-data study only."""
    if study.source != "real":
        raise ValueError("the README results block may only come from real data")
    ci = study.sharpe_ci
    head = study.headline[["cagr", "ann_vol", "sharpe", "max_drawdown", "turnover"]]
    head = head.rename(columns=METRIC_LABELS)
    head[f"Sharpe {study.config.statistics.ci_level:.0%} CI"] = [
        f"[{ci.loc[n, 'ci_low']:.2f}, {ci.loc[n, 'ci_high']:.2f}]" for n in head.index
    ]
    pct = {METRIC_LABELS[m] for m in ("cagr", "ann_vol", "max_drawdown", "turnover")}
    lines = [
        f"*Generated by `make report` from `reports/real/`. {_period_line(study)}*",
        "",
        f"*{_setup_line(study)}*",
        "",
        markdown_table(head, pct),
        "",
        "Full tables and figures: [reports/real/report.md](reports/real/report.md).",
    ]
    return "\n".join(lines)


def update_readme(readme: Path, block: str) -> None:
    """Replace the text between the RESULTS markers, keeping the markers."""
    text = readme.read_text()
    pattern = re.compile(re.escape(RESULTS_START) + r".*?" + re.escape(RESULTS_END), re.DOTALL)
    if not pattern.search(text):
        raise ValueError(f"{readme} has no {RESULTS_START} ... {RESULTS_END} markers")
    new = pattern.sub(lambda _m: f"{RESULTS_START}\n{block}\n{RESULTS_END}", text)
    readme.write_text(new)


def write_report_md(study: StudyResult, out_dir: Path, figures: list[Path]) -> Path:
    tbl = tables(study)
    parts = []
    if study.source == "demo":
        parts += [f"# DEMO report (synthetic data)\n\n> {DEMO_BANNER}\n"]
    else:
        parts += ["# Study report (real data)\n"]
    parts += [_period_line(study), "", _setup_line(study), ""]
    wf = study.walkforward
    fallbacks = {n: r.solver_fallbacks for n, r in wf.runs.items() if r.solver_fallbacks}
    if fallbacks:
        parts += [f"Min-variance solver fell back to inverse volatility: {fallbacks}.", ""]

    def section(title: str, key: str, note: str = "") -> None:
        frame, pct, index = tbl[key]
        parts.extend([f"## {title}", ""])
        if note:
            parts.extend([note, ""])
        parts.extend([markdown_table(frame, pct, index), ""])

    section("Headline metrics (out-of-sample, net)", "headline_metrics")
    section("Sharpe ratio confidence intervals", "sharpe_ci")
    section(
        "Sharpe difference versus benchmarks (paired bootstrap)",
        "sharpe_diff_ci",
        "An interval that contains 0 means the data cannot distinguish the strategy from "
        "the benchmark at this confidence level.",
    )
    section("Cost sensitivity (out-of-sample Sharpe)", "cost_sensitivity")
    section("Execution lag sensitivity (out-of-sample Sharpe)", "lag_sensitivity")
    section(
        "Subperiods (out-of-sample only)",
        "subperiods",
        "oos_coverage is the share of the window inside the out-of-sample period. "
        "Windows before it have no numbers on purpose.",
    )
    section("Chosen parameters per fold", "fold_parameters")
    if "data_summary" in tbl:
        section("Data coverage", "data_summary")
    parts += [
        "## Multiple testing",
        "",
        f"{wf.n_configs} strategy-parameter combinations were evaluated. The best of many "
        "tries looks better than it is by chance alone. The Deflated Sharpe Ratio is not "
        "implemented, so this bias is acknowledged but not corrected.",
        "",
        "## Figures",
        "",
    ]
    for p in figures:
        parts.append(f"![{p.stem}](figures/{p.name})\n")
    parts += ["", "Educational project, not investment advice."]
    path = out_dir / "report.md"
    path.write_text("\n".join(parts) + "\n")
    return path


def write_report(study: StudyResult, out_dir: Path, readme: Path | None = None) -> dict:
    """Write every output. Updates `readme` only for a real-data study."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if study.source == "demo":
        (out_dir / "DEMO_README.txt").write_text(DEMO_BANNER + "\n")
    table_paths = write_tables(study, out_dir)
    figure_paths = write_figures(study, out_dir)
    report_path = write_report_md(study, out_dir, figure_paths)
    if readme is not None:
        if study.source != "real":
            raise ValueError("refusing to write demo results into the README")
        update_readme(readme, results_block(study))
    return {"tables": table_paths, "figures": figure_paths, "report": report_path}
