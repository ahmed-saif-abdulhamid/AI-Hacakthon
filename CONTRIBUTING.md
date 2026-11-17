# Contributing to ProveIt

Thanks for helping. ProveIt is Apache-2.0 and every core feature stays free.

## Setup

```bash
docker compose up            # or, without Docker:
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env         # local Ollama model by default; or LLM_PROVIDER=nvidia with a free NVIDIA_API_KEY
python -m pytest
```

## Ground rules for every change

- Nothing may be published, sent, spent or signed without `@gated(action)` in `proveit/approval.py`.
- Market claims must come from `proveit/verifier.py` (quotes cut by code) or be labelled `ASSUMPTION`.
- Gate thresholds live in `config/gates.yaml` and are pre-registered; never tune them after seeing a run's data.
- Label anything mocked or stubbed `MOCKED` or `STUBBED`, in the README table and in the UI.
- Trick prompts that test our own guardrails belong in `tests/` or `evals/` only.

## Good first issues

- A Reddit adapter in `sources/reddit.py` (currently STUBBED) once API access allows.
- A Product Hunt source adapter (subclass `sources.base.Source`).
- An Arabic prompt pack and more Arabic cue words in `config/cues.yaml`.
- An HTML micro-tool product format for the Builder.

## Pull requests

Keep them small, add a test, and run `ruff check .`, `ruff format --check .`, `python -m pytest` and `python -m evals.run_evals --rules` before opening one. The pull-request template lists the full checklist; every function stays under a cyclomatic complexity of 10 (ruff enforces it). Security problems go through [SECURITY.md](SECURITY.md); notable changes go in [CHANGELOG.md](CHANGELOG.md).
