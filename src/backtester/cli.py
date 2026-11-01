"""Command line: `python -m backtester {demo,run,report}`.

demo    synthetic prices -> full study -> reports/demo/ (labeled DEMO)
run     real prices from data/raw/ -> study saved to reports/real/study.pkl
report  reports/real/study.pkl -> tables, figures, report.md, README block
"""

from __future__ import annotations

import argparse
import logging
import pickle
import sys
import time
from pathlib import Path

from backtester.config import load_config
from backtester.data import load_prices
from backtester.report import write_report
from backtester.study import StudyResult, run_study
from backtester.synthetic import generate_prices

DEFAULT_CONFIG = "configs/default.yaml"
STUDY_FILE = "study.pkl"


def cmd_demo(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    start = time.perf_counter()
    prices = generate_prices(cfg.demo.n_days, cfg.data.tickers, cfg.demo.seed)
    study = run_study(prices, cfg, source="demo")
    out = write_report(study, Path(args.out))
    print(
        f"DEMO (synthetic data) written to {args.out}: {len(out['tables'])} table files, "
        f"{len(out['figures'])} figures, {out['report']}"
    )
    print(f"Done in {time.perf_counter() - start:.1f}s")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    try:
        prices, report = load_prices(cfg.data.dir, cfg.data.tickers, cfg.data.max_gap_business_days)
    except FileNotFoundError as exc:
        print(f"NOT RUN ON REAL DATA: {exc}", file=sys.stderr)
        return 1
    for gap in report.gaps:
        logging.warning(
            "gap in %s: %s to %s (%d business days)",
            gap.ticker,
            gap.before.date(),
            gap.after.date(),
            gap.business_days,
        )
    study = run_study(prices, cfg, source="real", data_report=report)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / STUDY_FILE, "wb") as fh:
        pickle.dump(study, fh)
    print(f"Study on real data saved to {out / STUDY_FILE}. Next: make report")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    path = Path(args.out) / STUDY_FILE
    if not path.exists():
        print(
            f"No study at {path}. Run `make run` first (needs data in data/raw/).", file=sys.stderr
        )
        return 1
    with open(path, "rb") as fh:  # a file this program wrote itself
        study: StudyResult = pickle.load(fh)
    readme = Path(args.readme) if args.readme else None
    out = write_report(study, Path(args.out), readme=readme)
    print(f"Report written to {out['report']}")
    if readme is not None:
        print(f"README results block updated in {readme}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backtester", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, out in (
        ("demo", cmd_demo, "reports/demo"),
        ("run", cmd_run, "reports/real"),
        ("report", cmd_report, "reports/real"),
    ):
        p = sub.add_parser(name)
        p.add_argument("--config", default=DEFAULT_CONFIG)
        p.add_argument("--out", default=out)
        if name == "report":
            p.add_argument(
                "--readme", default="README.md", help="README to update; pass '' to skip"
            )
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    return args.func(args)
