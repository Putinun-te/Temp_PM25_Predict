PYTHON ?= .venv/bin/python

.PHONY: install test backfill train predict report publish pipeline

install:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt
	$(PYTHON) -m pip install -e . --no-deps

test:
	$(PYTHON) -m pytest

backfill:
	$(PYTHON) -m pm25 backfill

train:
	$(PYTHON) -m pm25 train

predict:
	$(PYTHON) -m pm25 predict

report:
	$(PYTHON) -m pm25 report

publish:
	$(PYTHON) -m pm25 publish

pipeline: backfill train predict report
