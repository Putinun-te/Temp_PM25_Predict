PYTHON ?= .venv/bin/python

.PHONY: install test backfill train predict publish pipeline

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

backfill:
	$(PYTHON) -m pm25 backfill

train:
	$(PYTHON) -m pm25 train

predict:
	$(PYTHON) -m pm25 predict

publish:
	$(PYTHON) -m pm25 publish

pipeline: backfill train predict
