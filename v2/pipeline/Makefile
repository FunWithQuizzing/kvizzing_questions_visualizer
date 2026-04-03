# KVizzing v2 Pipeline — run from v2/pipeline/

PYTHON := python3

.PHONY: backfill incremental export test test-verbose

## Run pipeline on all unprocessed dates (first run)
backfill:
	$(PYTHON) pipeline.py backfill

## Run pipeline on new dates only (daily use)
incremental:
	$(PYTHON) pipeline.py incremental

## Re-export JSON from questions.db without re-running the pipeline
export:
	$(PYTHON) pipeline.py export

## Run all pipeline + schema tests (run from v2/pipeline/)
test:
	cd .. && $(PYTHON) -m pytest pipeline/tests/ schema/test_schema.py -q

## Run tests with verbose output
test-verbose:
	cd .. && $(PYTHON) -m pytest pipeline/tests/ schema/test_schema.py -v
