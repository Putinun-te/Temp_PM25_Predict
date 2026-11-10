PYTHON ?= .venv/bin/python

.PHONY: install test backfill

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

backfill:
	$(PYTHON) -m pm25 backfill
