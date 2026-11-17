## What this changes

## Why

## Checklist
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] `python -m pytest` passes, with a test for the change
- [ ] `python -m evals.run_evals --rules` passes when guard rules or prompts change
- [ ] Anything mocked or stubbed is labelled `MOCKED` or `STUBBED` in the README table and the UI
- [ ] Nothing is published, sent, spent or signed without `@gated(action)`
- [ ] Gate thresholds in `config/gates.yaml` were not tuned after seeing a run's data
- [ ] No keys, `.env` contents or personal data in the diff
