# Portfolio Backtester: working rules

Read SPEC.md before doing anything. It is the source of truth. Do not edit it.

## Stack
- Python 3.10+, src layout (`src/backtester/`), tests in `tests/`.
- Runtime dependencies are limited to: numpy, pandas, scipy, scikit-learn, matplotlib, pyyaml.
- Dev dependencies: pytest, pytest-cov, ruff. Optional data extra: yfinance (used only by `scripts/fetch_data.py`).
- Do not add a dependency without recording why in DECISIONS.md.
- Tests must never import yfinance and must never need network access or files in `data/raw/`. CI installs only `.[dev]`.

## Commands
- `make install` installs the package in editable mode with dev and data extras.
- `make check` runs ruff and pytest. Run it after every milestone.
- `make cov` shows test coverage.
- `make demo` runs the full pipeline on synthetic data into `reports/demo/`.
- `make data` fetches real prices (owner runs this locally). `make run` and `make report` use real prices from `data/raw/`.

## Non-negotiables
- No look-ahead. A signal at date t may only use data up to and including t. The causality tests enforce this. Never weaken, skip, or delete them to make a build pass. If one fails, fix the code.
- Never invent data or results. Synthetic data is for tests and the demo only. It must never appear in README results, `reports/real/`, or any claim about real markets.
- If `data/raw/` has no real prices, finish everything else, write "NOT RUN ON REAL DATA" in the README results block, and record it in DECISIONS.md. Do not try to work around a blocked network.
- Every number in the README and reports is produced by code. Never type a result by hand.
- No secrets, API keys, or personal data in the repo.
- Never commit raw price data. `data/raw/` is gitignored. Derived outputs under `reports/real/` may be committed.
- Do not describe any strategy as profitable, predictive, or investable. State what was measured and the limits.
- Do not use em dashes in any file you write.

## Workflow
- Work milestone by milestone as listed in SPEC.md. After each one: `make check`, fix failures, commit.
- Write the test with or before the code. A milestone without tests is not done.
- Commit messages: imperative, one line, naming the milestone, for example "M2: add execution engine with drift and costs".
- Record every non-obvious choice in DECISIONS.md: what, why, alternatives considered. The owner is a second-year math student who must explain each choice in an interview, so write it for that reader.
- Prefer simple, readable code over clever code. Type hints on public functions. Docstrings state assumptions and units. Small modules. No notebooks as deliverables.
- No magic numbers in code. Parameters come from `configs/default.yaml` via `config.py`.
- When something is ambiguous, pick the simplest honest option, log it in DECISIONS.md, and continue. Do not stop to ask.
- Keep the full demo run under about two minutes on a laptop. Vectorize across assets and loop only over rebalance dates.

## Definition of done
See "Done when" and "Final review" in SPEC.md.
