.PHONY: all install lint format test scan check clean

all: check

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .
	shellcheck scripts/*.sh

format:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest -v
	bats tests/*.bats
	python3 scripts/validate-notebook.py notebooks/colab_ollama.ipynb

scan:
	bash scripts/scan-public-tree.sh --test
	bash scripts/scan-public-tree.sh

check: lint test scan
	@if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
		git diff --check; \
	fi
	@echo "All repository validation checks PASSED."

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info /tmp/bridge_state
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
