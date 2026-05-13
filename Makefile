# We're using Make as a command runner, so always make (avoids need for .PHONY)
MAKEFLAGS += --always-make

help:  # Display help
	@echo "Usage: make [target] [ARGS='additional args']\n\nTargets:"
	@awk -F'#' '/^[a-z0-9-]+:/ { sub(":.*", "", $$1); print " ", $$1, "#", $$2 }' Makefile | column -t -s '#'

all: format lint unit  # Run all quick, local commands

# Please keep the list below in alphabetical order.

format:  # Format the Python code
	uv run ruff format
	uv run ruff check --fix --unsafe-fixes

lint:  # Perform linting and static type checks
	uv run ruff check
	uv run ruff format --diff
	uv run ty check

unit:  # Run unit tests, eg: make unit ARGS='tests/unit/test_config.py'
	uv run pytest tests/unit -vv --cov=dashcraft $(ARGS)
