# ProveIt · J.A.R.V.I.S. edition

Proof before product: an open-source team of AI agents that tests a founder's idea against real public evidence, says **stop** when the evidence is weak, and never publishes, sends or refunds anything without the founder's hash-bound approval. J.A.R.V.I.S. (*Just A Rather Very Intelligent Strategist*) is its voice and console.

| It is | It is not |
|---|---|
| A six-phase pipeline with code-decided gates, a claim ledger of quotes cut by code from public sources, and founder approvals bound to SHA-256 | A business-plan generator, an income promise, or an autopilot that posts, sells or moves money |
| Free: a local open-weight model via Ollama, no keys | A paid API wrapper |
| Honest about what is MOCKED or STUBBED | A demo that hides its mocks |

## Quickstart

```bash
docker compose up
```

Then open **http://localhost:8501** (Streamlit: Tactical Writing mode, Holographic Voice HUD and Dual-Sync) or **http://localhost:8000/hud** (the J.A.R.V.I.S. console full screen, best for voice). The first start downloads about 3-4 GB (model and images). Load the weak or strong brief and press **RUN PIPELINE**, or type "Jarvis, why did you stop this idea?" in the Ask bar.

Without Docker: `pip install -r requirements.txt`, `ollama pull qwen3:4b-instruct-2507-q4_K_M`, then `python -m proveit run briefs/weak.md` (CLI) or `uvicorn app.api:app` and `streamlit run app/ui.py`.

## What works and what is mocked

| Step | Status | Notes |
|---|---|---|
| Intake + eligibility check (step 0) | **Working** | Excluded categories give STOP with an explanation |
| 1.1 Find opportunities (Core) | **Working** | Scout proposes 3 variants; live mode researches variant 1 |
| 1.2 Evidence ledger | **Working** | Quotes cut by code, live re-check, code relevance check |
| 1.3 Market definition | **Working** | Unsourced numbers are labelled ASSUMPTION |
| 1.4 Mom Test interview kit | **Working** | Interview-notes analyser is **STUBBED** |
| Gate 1: evidence | **Working** | Code decides go / repeat / pivot / stop |
| 2.1 Lean Canvas + riskiest assumption (Core) | **Working** | Each cell cites claim IDs or is ASSUMPTION |
| 2.2 Landing page + waitlist | **Working** | Served on localhost after approval |
| Public hosting of the landing page | **STUBBED** | Every sign-up is stored with test=true and excluded from gates |
| Gate 2: demand | **Working** | Real sign-ups only (0 while hosting is STUBBED) -> repeat; continuing needs a logged founder override |
| 3.1 Build MVP toolkit (Core) | **Working** | Spec, 1 module (3 in full mode), CSV template, buyer docs |
| Gate 3: tests | **Working** | Deterministic QA |
| 4.1 Pricing (Core) | **Working** | From verified price points, otherwise ASSUMPTION |
| 4.2 Policy drafts (Core) | **Working** | Stamped "DRAFT - not legal advice" |
| Gate 4 | **Working** | Founder approve / reject |
| 5.1 Store page + launch post draft (Core) | **Working** | localhost only; posts are never sent |
| 5.2 Payment -> delivery -> refund (Core) | **MOCKED** | In-process mock provider; no real or sandbox payments, no card fields |
| 5.3 Reconciliation | **MOCKED** | Matches mock orders, payments, fees, payouts |
| Posting to external platforms / email | **STUBBED** | Adapters are gated and raise NotEnabled |
| 6 Operate and learn | **STUBBED** | Memo from real metrics only ("not enough data") |
| Reddit source | **STUBBED** | Self-serve API access is restricted |
| J.A.R.V.I.S. console, HUD, Ask bar, browser voice | **Working** | Local Piper voice when installed, browser en-GB voice otherwise |

- **Who acted as founder:** for the committed demo runs, the operator of the build machine issued every approval and the Gate 2 override through the CLI (`python -m proveit approvals approve <id>`, `python -m proveit decide <run> override`). The log shows `approved_by: "founder"` for those actions.
- **Phases after an override are a preview:** Gate 2 cannot pass without real traffic, so any run reaches Phases 3-5 only through `founder_override_against_evidence` (reason required, guard-checked, logged). Every later file says "PREVIEW after a founder override against the evidence ...: demand not yet proven", and the UI shows the same banner.
- **Privacy:** search queries derived from the brief go to Hacker News, Stack Exchange, GitHub and SearXNG's engines. Don't put confidential details in the brief.
- **CI:** the smoke tests use a fake LLM fixture that lives only in `tests/`. Every real run uses the open-weight model.
- **Committed runs:** both were produced with `python -m proveit` on a Windows laptop (Ollama 0.40.16, the pinned model, a 4 GB GPU) because Docker was not available on that machine; `docker compose up` itself was not exercised there. SearXNG was not deployed for these runs (`SEARXNG_URL` unset), which the log records as `searxng_not_deployed`; evidence came from Hacker News, Stack Exchange, GitHub and Wikipedia. The weak brief (motivational lock-screen wallpapers) ends in **STOP** (rule 3). The strong brief (a late-payment follow-up toolkit for freelancers) also ends in **STOP** at Gate 1 (3.0 weighted pain signals against a threshold of 6), so its Phases 2-6 exist only as a preview after logged founder overrides at Gate 1 and Gate 2. An earlier strong brief (client onboarding) stopped too; the history and every calibration change are in [docs/calibration.md](docs/calibration.md). No threshold was changed.

## Architecture

Eleven agents work through six phases, but only plain Python code calls tools, cuts quotes, decides gates and executes approved actions; the model only points at sentence IDs, summarises and argues. Thresholds and the brief are hashed before any source is called, so a moved goalpost is logged and shown in red. Quotes are extracted by code from the source record and re-checked against the public page where reachable; a claim counts only if code confirms it is on-topic and contains a pain or payment cue. Every publish, store opening and refund is wrapped in `@gated(action)` and bound to the SHA-256 of the exact bytes the founder saw. Details, diagrams and the gate rules are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

- **Model:** `qwen3:4b-instruct-2507-q4_K_M` (Qwen3 4B Instruct 2507, open weights, non-thinking) served by **Ollama**. The same tag is used in `docker-compose.yml`, `.env.example` and this README.
- **No keys and no paid service are required.** Optional free keys (`SE_KEY`, `GITHUB_TOKEN`) only raise public rate limits.
- **Bigger model on a GPU:** `MODEL=qwen3:8b docker compose up`, or `MODEL=gpt-oss:20b` with enough memory.
- **Native GPU / Apple Metal:** Docker on a Mac has no GPU access, so run Ollama on the host and point the stack at it: `SKIP_PULL=1 LLM_BASE_URL=http://host.docker.internal:11434 docker compose up`.
- **Search:** a self-hosted SearXNG container (no account). Wikipedia is used for context only.
- **Voice:** local Piper text-to-speech (`requirements-voice.txt`, British voice `en_GB-alan-medium`) and the browser's built-in speech recognition and en-GB voice as fallback. No paid speech API.

## Cost per run

**About $0.00 per run** (local `qwen3:4b-instruct-2507-q4_K_M` via Ollama; no paid API, no keys). Measured on the committed runs (see `decision_log.json`):

| Run | Model calls | Tokens (in + out) | Model time | Cost |
|---|---|---|---|---|
| Weak brief, live mode, Phase 1 to STOP | 7 | 5,435 + 1,573 = ~7k | ~2.7 min | $0.00 |
| Strong brief, full mode, all six phases (preview) | 44 | 28,629 + 13,207 = ~42k | ~21.5 min | $0.00 |

Times are on a 4 GB laptop GPU; electricity is the only cost.

## What our system will NOT do

- Promise income or success, or project revenue.
- Write reviews, testimonials, ratings, sign-ups, counters or countdown timers (the templates have no slots for them).
- Pose as the founder, a customer or another brand.
- Hold, move or refund money by itself; refunds need the founder's approval of the exact refund payload.
- Create accounts, or store passwords or card numbers (no card field exists anywhere).
- Publish, send, spend or sign anything without approval; `spend`, `sign` and `create_account` always raise, even when approved.
- Hide core features behind a paywall.
- Build excluded products: physical goods, financial or crypto products, health or legal advice products.
- Use synthetic customer interviews as evidence.

Guard numbers are measured on our own eval sets (see [evals/results.md](evals/results.md)), not a general safety claim.

## How the project stays alive after the hackathon

- **Maintainers:** the founding team, with a monthly release and a public changelog.
- **Roadmap:** v0.2 interview-notes import and more sources; v0.3 a micro-tool product format; v0.4 opt-in publishing adapters, still approval-gated; v1.0 a community-hosted instance with no paywall on core features.
- **Community:** Apache-2.0, [CONTRIBUTING.md](CONTRIBUTING.md), a source plugin interface (`sources/base.py`) and good first issues (a Reddit adapter once access allows, a Product Hunt adapter, an Arabic prompt pack).
- **Funding:** GitHub Sponsors and university incubator support (ASSUMPTION: availability not checked). Core features stay free.
