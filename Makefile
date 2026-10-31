.PHONY: install lint test check cov data demo run report clean

PY ?= python

install:
	$(PY) -m pip install -e ".[dev,data]"

lint:
	ruff check .

test:
	pytest

check: lint test

cov:
	pytest --cov=backtester --cov-report=term-missing

data:
	$(PY) scripts/fetch_data.py

demo:
	$(PY) -m backtester demo

run:
	$(PY) -m backtester run --config configs/default.yaml

report:
	$(PY) -m backtester report --config configs/default.yaml

clean:
	rm -rf build dist .pytest_cache .ruff_cache .coverage htmlcov src/*.egg-info
