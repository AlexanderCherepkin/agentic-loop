.PHONY: test coverage journey format lint

PYTHON ?= python

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest -m core --no-cov

coverage:
	$(PYTHON) -m pytest --cov --cov-report=html --cov-report=term

journey:
	$(PYTHON) -m runtime.journey.cli --workspace .

format:
	$(PYTHON) -m black .

lint:
	$(PYTHON) -m ruff check .
