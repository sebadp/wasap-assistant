.PHONY: dev test lint format typecheck check

VENV := .venv/bin/

dev:
	python3 -m venv .venv
	$(VENV)pip install -e ".[dev]"
	$(VENV)pre-commit install
	@echo "Done! Run: source .venv/bin/activate"

test:
	$(VENV)pytest tests/ -v

lint:
	$(VENV)ruff check app tests

format:
	$(VENV)ruff format app tests

typecheck:
	$(VENV)mypy app

check: lint typecheck test
