PY ?= python
WEAK ?=
STRONG ?=

.PHONY: up test test-llm run-weak run-strong promote evals

up:
	docker compose up

test:
	$(PY) -m pytest

test-llm:
	$(PY) -m pytest -m llm

run-weak:
	$(PY) -m proveit run briefs/weak.md --mode live --label weak

run-strong:
	$(PY) -m proveit run briefs/strong.md --mode live --label strong

# Copies the two committed runs into outputs/ and the decision log to the repo root.
# Usage: make promote WEAK=<run_id> STRONG=<run_id>
promote:
	$(PY) -m proveit promote --weak $(WEAK) --strong $(STRONG)
	cp runs/promoted/decision_log.json decision_log.json

evals:
	$(PY) -m evals.run_evals
