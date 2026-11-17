# ProveIt

**Find out if anyone wants it before you build it.** ProveIt is an open-source team of AI agents that tests a founder's product idea against what real people say in public, stops them when the evidence is thin, and never publishes, sends or refunds anything without the founder's hash-locked approval. Verity, its spoken assistant, explains every verdict in plain words.

| It is | It is not |
|---|---|
| A six-phase pipeline whose checkpoints are decided by code, with quotes cut by code from public posts and re-checked on their source page | A business-plan generator, an income promise, or an autopilot that posts, sells or moves money |
| Free: open-weight NVIDIA Nemotron on NVIDIA's free hosted tier (a free key, no card) | A paid API wrapper |
| Honest about what is MOCKED or STUBBED, in this README and on screen | A demo that hides its mocks |

**Two committed runs show it working** ([outputs/](outputs/), [decision_log.json](decision_log.json)): a weak idea (an ebook of inspirational quotes) gets **STOP** in about a minute; a stronger idea (a late-payment toolkit for freelancers) also gets **STOP**, and the founder then carries on against the evidence with a logged reason, so phases 2-6 run as a clearly labelled preview through to a MOCKED sale, delivery and refund.

## Quickstart

```bash
docker compose up
```

Before the first start, copy `.env.example` to `.env` and set `NVIDIA_API_KEY` (a free key from [build.nvidia.com](https://build.nvidia.com): open any model page and choose **Get API Key**). Then open **http://localhost:8000**, press **Test a new idea** (or try one of the two examples in that dialog), and ask Verity "why?" in the bar at the bottom. A developer view with raw details runs on http://localhost:8501.

Without Docker: `pip install -r requirements.txt`, put `NVIDIA_API_KEY` in `.env`, then `uvicorn app.api:app` (console) or `python -m proveit run briefs/weak.md` (command line). Tests: `python -m pytest`.

## What works and what is mocked

| Step | Status | Notes |
|---|---|---|
| Intake + eligibility check (step 0) | **Working** | Excluded categories stop before any search; the founder cannot override them |
| 1.1 Find opportunities (Core) | **Working** | Scout proposes 3 angles; live mode researches the first |
| 1.2 Evidence ledger | **Working** | Quotes cut by code, re-checked on the source page, relevance and complaint cues checked by code |
| 1.3 Market definition | **Working** | Unsourced numbers are labelled ASSUMPTION |
| 1.4 Mom Test interview kit | **Working** | Questions, screener and a decision rule; interview-notes analysis is **STUBBED** |
| Gate 1: evidence | **Working** | Code decides go / repeat / pivot / stop against a bar hashed before searching |
| 2.1 Lean Canvas + riskiest assumption (Core) | **Working** | Each cell cites claim IDs or is ASSUMPTION |
| 2.2 Landing page + waitlist | **Working** | Served on localhost after approval |
| Public hosting of the landing page | **STUBBED** | Every sign-up is stored with test=true and excluded from gates |
| Gate 2: demand | **Working** | Real sign-ups only (0 while hosting is STUBBED) -> repeat; continuing needs a logged founder override |
| 3.1 Build MVP toolkit (Core) | **Working** | Spec, 1 module (3 in full mode), CSV templates, buyer docs |
| Gate 3: tests | **Working** | Deterministic QA |
| 4.1 Pricing (Core) | **Working** | From verified price points, otherwise ASSUMPTION |
| 4.2 Policy drafts (Core) | **Working** | Stamped "DRAFT - not legal advice" |
| Gate 4 | **Working** | Founder approve / reject |
| 5.1 Store page + launch post draft (Core) | **Working** | localhost only; posts are never sent |
| 5.2 Payment -> delivery -> refund (Core) | **MOCKED** | In-process mock provider with signed webhooks; no real or sandbox payments, no card fields |
| 5.3 Reconciliation | **MOCKED** | Matches mock orders, payments, fees, payouts |
| Posting to external platforms / email | **STUBBED** | Adapters are gated and raise NotEnabled |
| 6 Operate and learn | **STUBBED** | Memo from real metrics only ("not enough data") |
| Reddit source | **STUBBED** | Self-serve API access is restricted |
| Console, Verity assistant, voice | **Working** | Piper voice on this computer when installed, browser voice otherwise |

- **Who acted as founder:** for the committed runs, the operator of the build machine pressed every approval and gave both override reasons through the command line; the log records `approved_by: "founder"` for those actions.
- **Later phases after an override are a preview:** Gate 2 cannot pass without real traffic, so a run reaches phases 3-5 only through a logged `founder_override_against_evidence`. Every later file says "PREVIEW after a founder override", and so does the console.
- **Run-to-run variation, measured:** the weak brief gave STOP in 2 of 4 runs and "look again" (sources can't see the market) in the other 2; never GO. Every attempt and calibration change is in [docs/calibration.md](docs/calibration.md); the 10-idea calibration set is in [evals/gate_backtest.md](evals/gate_backtest.md).

## Architecture

Eleven agents work through six phases, but only plain Python code calls tools, cuts quotes, decides checkpoints and executes approved actions; the model points at sentence IDs, summarises and argues. The bar each checkpoint uses is hashed with the brief before any source is called, so a moved goalpost is detected and shown. Quotes are cut by code from the source record and re-checked against the public page (through the official API for Stack Exchange); a quote counts only if code confirms it is on topic and contains a complaint or payment cue, and one comment counts once. Every publish, store opening and refund is wrapped in `@gated(action)` and bound to the SHA-256 of the exact bytes the founder saw. Details, diagrams and the gate rules are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

- **Model:** `nvidia/nemotron-3-ultra-550b-a55b` (NVIDIA Nemotron 3 Ultra, open weights on Hugging Face under the OpenMDW-1.1 licence), with thinking switched off for speed, called through NVIDIA's OpenAI-compatible API at `https://integrate.api.nvidia.com/v1`. Change it with `NVIDIA_MODEL`; `NVIDIA_BASE_URL` points the same client at any OpenAI-compatible server, including a self-hosted one.
- **How to run without paying:** a free developer key from build.nvidia.com (no card) in `.env`. The free tier is rate-limited (about 40 requests a minute per account); ProveIt paces itself to 30 a minute (`LLM_RPM`) and backs off on HTTP 429, so a run waits instead of failing.
- **Structured output:** every agent call sends its JSON schema as `response_format`, at temperature 0; invalid JSON is retried once and then turned into a REPEAT ("the research didn't come back clean"), never into a weak-idea verdict.
- **Privacy:** ideas, quotes and questions are sent to NVIDIA's API; searches go to Hacker News, Stack Exchange, GitHub, Wikipedia and (in Docker) a self-hosted SearXNG. Runs and decisions stay on your computer. Details are in the console under **Privacy**.
- **Optional free keys** (`SE_KEY`, `GITHUB_TOKEN`) only raise public search rate limits.
- **Voice:** Piper text-to-speech (`requirements-voice.txt`, British voice `en_GB-alan-medium`) runs on your computer when installed; otherwise the browser's own voice. Speech recognition is the browser's. No paid speech API.

## Cost per run

**About $0.00 per run** (NVIDIA's free developer tier, no card). Measured from the committed [decision_log.json](decision_log.json):

| Run | Model | Model calls | Tokens (in + out) | Model time | Cost |
|---|---|---|---|---|---|
| Weak brief, Phase 1 to STOP | Nemotron 3 Ultra | 7 | 7,465 + 495 = ~8k | ~71 s | $0.00 |
| Strong brief, all six phases (preview after override) | Nemotron 3 Ultra | 29 | 29,594 + 6,112 = ~36k | ~7 min | $0.00 |

Model time includes ProveIt's own pacing for the free tier's rate limit. A Phase 1 verdict typically arrives in 30-90 seconds of wall-clock time.

## What our system will NOT do

- Promise income or success, or project revenue.
- Write reviews, testimonials, ratings, sign-ups, counters or countdown timers (the templates have no slots for them).
- Pose as the founder, a customer or another brand, or invent the founder's experience.
- Hold, move or refund money by itself; refunds need the founder's approval of the exact refund payload.
- Create accounts, or store passwords or card numbers (no card field exists anywhere).
- Publish, send, spend or sign anything without approval; `spend`, `sign` and `create_account` always raise, even when approved.
- Let a founder override an excluded category, or treat a chat message as an approval.
- Hide core features behind a paywall.
- Build excluded products: physical goods, financial or crypto products, health or legal advice products.
- Use synthetic customer interviews as evidence.

Guard numbers are measured on our own eval sets (see [evals/results.md](evals/results.md)), not a general safety claim.

## How the project stays alive after the hackathon

- **Maintainers:** the founding team keeps a monthly release with a public changelog; maintainership is open to regular contributors after three merged pull requests.
- **Roadmap (dated):** December 2026: interview-notes import, Product Hunt and IndieHackers sources, SearXNG on by default. January 2027: published calibration set grown to 50 ideas with outcomes. February 2027: a micro-tool product format and opt-in publishing adapters that stay approval-gated. v1.0: a community-hosted instance with no paywall on core features. ([docs/roadmap.md](docs/roadmap.md))
- **Why open beats closed here:** the verdict is only worth trusting if anyone can read the rules that produced it, re-run them and see every quote's source. Comparison with closed tools: [docs/positioning.md](docs/positioning.md).
- **Community:** Apache-2.0, [CONTRIBUTING.md](CONTRIBUTING.md), a source plugin interface (`sources/base.py`) and good first issues (a Reddit adapter once access allows, a Product Hunt adapter, an Arabic prompt pack).
- **Funding:** core features stay free. Options under consideration (ASSUMPTION: none confirmed): GitHub Sponsors, incubators sponsoring a hosted instance for their cohorts, and open-source grants.
