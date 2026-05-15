.PHONY: install test lint run clean all

install:
	pip install -e ".[dev]"

test:
	pytest -v --tb=short

test-cov:
	pytest -v --cov=ocean_curator --cov-report=term-missing

lint:
	ruff check ocean_curator/ tests/

run:
	rm -rf output/
	python -m ocean_curator -c config.yaml run-all

samples:
	python sample_data/generate_samples.py

clean:
	rm -rf output/ dist/ build/ *.egg-info .pytest_cache
	find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

all: install test run
