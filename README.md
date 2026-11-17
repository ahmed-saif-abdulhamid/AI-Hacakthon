# J.A.R.V.I.S. by ProveIt

**Meet J.A.R.V.I.S., the AI venture team that tells you whether anyone wants your product before you build it.** Talk to it, type to it, or hand it a founder brief: a team of agents researches real public complaints, decides each gate by rule, and only acts when you approve. It runs entirely on a local open-weight model with one command, `docker compose up`.

**The problem:** first-time founders spend months building digital products nobody asked for, and most AI business tools make it worse: they write a confident business plan, promise income and never say "don't". **The user:** a solo founder or small team with an idea, a few hours a week and a small budget. **What ProveIt does:** a team of AI agents takes the founder's brief (idea, skills, budget, time, market, values) through six phases, from Discover to Operate and learn. Between phases, code-decided gates say **go, repeat, pivot or stop**, against a bar hashed before any searching starts. Nothing is published, sent or refunded without the founder approving the exact bytes.

| It is | It is not |
|---|---|
| A six-phase pipeline whose gates are decided by code, with quotes cut by code from public posts and re-checked on their source page | A business-plan generator, an income promise, or an autopilot that posts, sells or moves money |
| Free and local: an open-weight model (Qwen3 4B Instruct) runs on your computer through Ollama; no key, no account | A paid API wrapper |
| Honest about what is MOCKED or STUBBED, in this README and on screen | A demo that hides its mocks |

**What the committed runs show** ([outputs/](outputs/), [decision_log.json](decision_log.json)):

1. **It says "don't launch this".** A weak idea (an ebook of inspirational quotes) gets **STOP** in about a minute: too few people complain about the problem in public ([outputs/phase1_gate_decision-weak.md](outputs/phase1_gate_decision-weak.md)).
2. **It compares angles and pivots on evidence.** For a stronger idea (a late-payment toolkit for freelancers) the Scout proposed three angles; code counted recent first-person complaints on Hacker News for each, ruled one out as too close to legal advice (contract templates), and researched the strongest first ([outputs/phase1_step1_opportunities-strong.md](outputs/phase1_step1_opportunities-strong.md)). Gate 1 said **STOP** (1 counted complaint against a bar of 6: [outputs/phase1_gate_variant-1-strong.md](outputs/phase1_gate_variant-1-strong.md)); the founder pivoted to the next-best angle, which got **REPEAT**: the public forums can't see that market, so the next step is a Mom Test interview kit ([outputs/phase1_gate_decision-strong.md](outputs/phase1_gate_decision-strong.md)).
3. **The founder stays in charge, and it stays on the record.** The founder carried on against the evidence with a logged reason, so phases 2-6 ran as a labelled preview: Lean Canvas, landing page (the founder rejected two drafts until the guard-blocked contract wording was gone), a tested MVP toolkit, pricing and draft policies, store page, a MOCKED sale with automatic delivery and an approved refund that revoked access, then support-answer drafts, a metrics plan and a persevere-or-pivot gate decided by code (**REPEAT**: no real buyers yet).
4. **Known flaw in this run:** its launch-post draft (never posted) lists parts that were not built. The fix (code now writes what the product contains) landed after the run; see `proveit/orchestrator.py` `stage_phase5`.

## Quickstart

```bash
docker compose up
```

Then open **http://localhost:8000** and say hello to J.A.R.V.I.S. (type, or hold the talk button). **No key, no account, no paid service:** the first start downloads the local open-weight model (`qwen3:4b-instruct-2507-q4_K_M` through Ollama, about 2.5 GB, once) into a Docker volume, and the two committed runs load straight away, so every verdict, quote, gate file and approval is readable while the model downloads. Then press **Test a new idea**. A developer view with raw details runs on http://localhost:8501.

Without Docker: `pip install -r requirements.txt`, run [Ollama](https://ollama.com) with `ollama pull qwen3:4b-instruct-2507-q4_K_M` (or set `LLM_PROVIDER=nvidia` and a free `NVIDIA_API_KEY` in `.env`), then `uvicorn app.api:app` (console) or `python -m proveit run briefs/weak.md` (command line). Tests: `python -m pytest`.

## What works and what is mocked

| Step | Status | Notes |
|---|---|---|
| Local model through Ollama (default with Docker) | **Working** | Phase 1 run end to end on `qwen3:4b-instruct-2507-q4_K_M` (5 model calls, ~110 s on a 4 GB laptop GPU); the committed demo runs used the optional hosted NVIDIA model |
| Intake + eligibility check (step 0) | **Working** | Excluded categories stop before any search; the founder cannot override them |
| 1.1 Find opportunities (Core) | **Working** | Scout proposes 3 angles; each passes the excluded-category check; code ranks them by recent first-person complaints and researches the strongest; PIVOT goes to the next-best |
| 1.2 Evidence ledger | **Working** | Quotes cut by code, re-checked on the source page, relevance and complaint cues checked by code; sentences the model skipped but code qualifies are added and verified too |
| 1.3 Market definition | **Working** | Unsourced numbers are labelled ASSUMPTION |
| 1.4 Mom Test interview kit | **Working** | Questions, screener and a decision rule; interview-notes analysis is **STUBBED** |
| Gate 1: evidence | **Working** | Code decides go / repeat / pivot / stop against a bar hashed before searching |
| 2.1 Lean Canvas + riskiest assumption (Core) | **Working** | Each cell cites claim IDs or is ASSUMPTION |
| 2.2 Landing page + waitlist | **Working** | Served on localhost after approval |
| Public hosting of the landing page | **STUBBED** | Every sign-up is stored with test=true and excluded from gates |
| Gate 2: demand | **Working** (always REPEAT while hosting is STUBBED) | Counts real sign-ups only, so it cannot pass with test traffic; continuing needs a logged founder override |
| 3.1 Build MVP toolkit (Core) | **Working** | Spec, 1 module (3 in full mode), CSV templates, buyer docs |
| Gate 3: tests | **Working** | Deterministic QA |
| 4.1 Pricing (Core) | **Working** | From verified price points, otherwise ASSUMPTION |
| 4.2 Policy drafts (Core) | **Working** | Stamped "DRAFT - not legal advice" |
| Gate 4 | **Working** | Founder approve / reject |
| 5.1 Store page + launch post draft (Core) | **Working** | localhost only; posts are never sent |
| 5.2 Payment -> delivery -> refund (Core) | **MOCKED** | In-process mock provider with signed webhooks; no real or sandbox payments, no card fields |
| 5.3 Reconciliation | **MOCKED** | Matches mock orders, payments, fees, payouts |
| Posting to external platforms / email | **STUBBED** | Adapters are gated and raise NotEnabled |
| 6.1 Persevere-or-pivot memo + Gate 6 | **Working** on real records (none exist yet, so **STUBBED** in the demo) | Code rule over pre-registered bars (`gate6_operate`); test orders never count |
| 6.2 Support answers | **Working** (drafts only) | Built by code from the run's approved files; sending is **STUBBED** |
| 6.3 Metrics plan | **Working** | Each metric's source and pre-registered bar |
| Reddit source | **STUBBED** | Self-serve API access is restricted |
| Console and optional spoken assistant (J.A.R.V.I.S.) | **Working** | Piper voice on this computer when installed, browser voice otherwise |

- **Who acted as founder:** for the committed runs, the operator of the build machine pressed every approval and gave both override reasons through the command line; the log records `approved_by: "founder"` for those actions.
- **Later phases after an override are a preview:** Gate 2 cannot pass without real traffic, so a run reaches phases 3-5 only through a logged `founder_override_against_evidence`. Every later file says "PREVIEW after a founder override", and so does the console.
- **Run-to-run variation, measured:** across six runs of the weak brief the gate said STOP twice and "look again" (the sources can't see the market) four times; never GO. The Scout's search phrasing varies between calls even at temperature 0. Every attempt and calibration change is in [docs/calibration.md](docs/calibration.md); the 10-idea calibration set is in [evals/gate_backtest.md](evals/gate_backtest.md).

## Architecture

Eleven agents work through six phases, but only plain Python code calls tools, cuts quotes, decides checkpoints and executes approved actions; the model points at sentence IDs, summarises and argues. The bar each checkpoint uses is hashed with the brief before any source is called, so a moved goalpost is detected and shown. Quotes are cut by code from the source record and re-checked against the public page (through the official API for Stack Exchange); a quote counts only if code confirms it is on topic and is a person's own complaint or payment (not a question, a vendor pitch or a feature list), and one comment counts once. Every publish, store opening and refund is wrapped in `@gated(action)` and bound to the SHA-256 of the exact bytes the founder saw. Details, diagrams and the gate rules are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

- **Default model (local):** `qwen3:4b-instruct-2507-q4_K_M` (Qwen3 4B Instruct 2507, 4-bit, open weights, Apache-2.0; no reasoning block, so answers come straight away) served by Ollama `0.40.10` inside Docker. `docker compose up` downloads it into the `ollama-models` volume on first start; nothing leaves the computer except the public searches. Change it with `OLLAMA_MODEL` (for example `qwen3:8b` on a machine with more memory). Ollama uses an NVIDIA GPU when Docker exposes one, otherwise the CPU (slower: on a 4 GB laptop GPU a Phase 1 verdict took about 2 minutes, 5 model calls).
- **Optional hosted model:** `nvidia/nemotron-3-ultra-550b-a55b` (NVIDIA Nemotron 3 Ultra, open weights under OpenMDW-1.1) on NVIDIA's OpenAI-compatible free developer tier: set `LLM_PROVIDER=nvidia` and a free key from build.nvidia.com (no card). The committed runs used this provider. It is rate-limited (about 40 requests a minute); ProveIt paces itself to 30 (`LLM_RPM`), backs off on HTTP 429 and retries the same step before showing **Try again**, reusing the search already made.
- **Structured output:** every agent call sends its JSON schema as `response_format`, at temperature 0; invalid JSON is retried once and then turned into a REPEAT ("the research didn't come back clean"), never into a weak-idea verdict.
- **Privacy:** with the default local model, ideas, quotes and questions stay on your computer (with `LLM_PROVIDER=nvidia` they go to NVIDIA's API); searches go to Hacker News, Stack Exchange, GitHub, Wikipedia and (in Docker) a self-hosted SearXNG. Runs and decisions stay on your computer. Details are in the console under **Privacy**.
- **Optional free keys** (`SE_KEY`, `GITHUB_TOKEN`) only raise public search rate limits.
- **Voice:** Piper text-to-speech (`requirements-voice.txt`, British voice `en_GB-alan-medium`) runs on your computer when installed; otherwise the browser's own voice. Speech recognition is the browser's. No paid speech API.

## Cost per run

**About $0.00 per run**: the default model runs locally (electricity only); the committed runs used NVIDIA's free developer tier, also $0.00. Measured from the committed [decision_log.json](decision_log.json):

| Run | Model | Model calls | Tokens (in + out) | Model time | Cost |
|---|---|---|---|---|---|
| Weak brief, Phase 1 to STOP | Nemotron 3 Ultra | 7 | 7,465 + 495 = ~8k | ~71 s | $0.00 |
| Strong brief: 2 angles researched, all six phases (preview after override) | Nemotron 3 Ultra | 46 | 31,420 + 6,755 = ~38k | ~8.5 min | $0.00 |

Model time includes ProveIt's own pacing for the free tier's rate limit. The strong run's 46 calls include a pivot (a second research pass) and the redrafts after the founder's rejections. A Phase 1 verdict typically arrives in 30-90 seconds of wall-clock time.

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
