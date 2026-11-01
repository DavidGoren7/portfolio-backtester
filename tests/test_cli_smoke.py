"""End to end: `demo` on a tiny synthetic config writes every expected file."""

from __future__ import annotations

import pickle

import pytest
import yaml

from backtester.cli import main
from backtester.config import parse_config
from backtester.report import NOT_RUN, RESULTS_END, RESULTS_START, write_report
from backtester.study import run_study
from backtester.synthetic import generate_prices

EXPECTED_TABLES = [
    "headline_metrics",
    "sharpe_ci",
    "sharpe_diff_ci",
    "fold_parameters",
    "cost_sensitivity",
    "lag_sensitivity",
    "subperiods",
]
EXPECTED_FIGURES = [
    "equity",
    "drawdowns",
    "rolling_sharpe",
    "param_stability",
    "is_vs_oos",
    "sharpe_vs_cost",
]


@pytest.fixture
def tiny_config(tmp_path, small_raw_config):
    path = tmp_path / "tiny.yaml"
    path.write_text(yaml.safe_dump(small_raw_config))
    return path


def test_demo_writes_expected_files(tmp_path, tiny_config):
    out = tmp_path / "demo"
    assert main(["demo", "--config", str(tiny_config), "--out", str(out)]) == 0
    for name in EXPECTED_TABLES:
        assert (out / "tables" / f"{name}.csv").exists()
        md = (out / "tables" / f"{name}.md").read_text()
        assert md.startswith("> DEMO")
    for name in EXPECTED_FIGURES:
        assert (out / "figures" / f"{name}.png").stat().st_size > 0
    assert len(list((out / "figures").glob("weights_*.png"))) == 2
    report = (out / "report.md").read_text()
    assert report.startswith("# DEMO report (synthetic data)")
    assert (out / "DEMO_README.txt").exists()


def test_run_without_data_says_not_run(tmp_path, tiny_config, small_raw_config, capsys):
    small_raw_config["data"]["dir"] = str(tmp_path / "empty")
    cfg_path = tmp_path / "nodata.yaml"
    cfg_path.write_text(yaml.safe_dump(small_raw_config))
    code = main(["run", "--config", str(cfg_path), "--out", str(tmp_path / "real")])
    assert code == 1
    assert "NOT RUN ON REAL DATA" in capsys.readouterr().err


def test_report_without_study_fails_cleanly(tmp_path):
    assert main(["report", "--out", str(tmp_path / "none"), "--readme", ""]) == 1


def test_demo_study_can_never_write_the_readme(tmp_path, small_raw_config):
    cfg = parse_config(small_raw_config)
    prices = generate_prices(cfg.demo.n_days, cfg.data.tickers, cfg.demo.seed)
    study = run_study(prices, cfg, source="demo")
    readme = tmp_path / "README.md"
    readme.write_text(f"x\n{RESULTS_START}\n{NOT_RUN}\n{RESULTS_END}\n")
    with pytest.raises(ValueError, match="README"):
        write_report(study, tmp_path / "out", readme=readme)
    assert NOT_RUN in readme.read_text()


def test_run_then_report_fills_readme_from_code(tmp_path, small_raw_config):
    """Full real-data path, using synthetic CSVs as stand-in files.

    Labeled 'real' here only to exercise the plumbing in a temp folder; the
    repository README is never touched by tests.
    """
    cfg = parse_config(small_raw_config)
    prices = generate_prices(cfg.demo.n_days, cfg.data.tickers, cfg.demo.seed)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for t in cfg.data.tickers:
        prices[[t]].rename(columns={t: "adj_close"}).to_csv(raw_dir / f"{t}.csv")
    small_raw_config["data"]["dir"] = str(raw_dir)
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(yaml.safe_dump(small_raw_config))
    out = tmp_path / "real"
    assert main(["run", "--config", str(cfg_path), "--out", str(out)]) == 0
    with open(out / "study.pkl", "rb") as fh:
        assert pickle.load(fh).source == "real"
    readme = tmp_path / "README.md"
    readme.write_text(f"Intro\n\n{RESULTS_START}\n{NOT_RUN}\n{RESULTS_END}\n\nOutro\n")
    assert main(["report", "--out", str(out), "--readme", str(readme)]) == 0
    text = readme.read_text()
    assert NOT_RUN not in text
    assert text.startswith("Intro") and text.rstrip().endswith("Outro")
    assert "| strategy |" in text
