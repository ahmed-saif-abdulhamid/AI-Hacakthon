"""Hand-written state machine for the six phases. No agent framework.

The model has no tools: agents return data, and only this module calls functions.
Every run writes to runs/<run_id>/ only; ``promote`` is the only writer of outputs/.

Stages (``advance`` runs until a stage needs the founder):
  phase1 -> gate1 -> phase2 -> [approve publish_landing_page] -> gate2 -> [founder override]
  -> phase3 -> phase4 -> [founder gate 4] -> phase5 -> [approve open_store] -> payment_test
  -> [approve refund] -> refund -> phase6 -> done
"""
from __future__ import annotations

import json
import os
import re
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from agents import analyst, builder, debate, intake, launcher, policy_drafter, pricer, qa, researcher, scorer, scout, strategist
from sources import wikipedia
from sources.github import GitHub
from sources.hn import HackerNews
from sources.searxng import SearXNG
from sources.stackexchange import StackExchange

from . import approval, db, gates, guard, llm, render, verifier, voice
from .log import emit, log_action, utcnow
from .models import Claim, FounderBrief, GateDecision, Hit, SourceCall, Statement, Variant
from .startup import runs_dir

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=select_autoescape(["html", "j2"]))
PHASE_NAMES = {1: "Discover", 2: "Validate", 3: "Build", 4: "Commercial setup",
               5: "Launch (sell, deliver, get paid)", 6: "Operate and learn"}
WAITING = {"await_approval", "await_override", "await_gate4", "await_clarify", "await_founder"}


def runtime() -> dict:
    return yaml.safe_load((ROOT / "config" / "runtime.yaml").read_text(encoding="utf-8"))


# ---- run bookkeeping ------------------------------------------------------------

class Run:
    def __init__(self, row: dict):
        self.id = row["id"]
        self.label = row.get("label")
        self.mode = row.get("mode") or "live"
        self.stage = row.get("stage")
        self.brief_raw = json.loads(row.get("brief_json") or "{}")
        self.state = json.loads(row.get("state_json") or "{}")
        self.sha = row.get("thresholds_sha256") or ""
        self.dir = runs_dir() / self.id
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, stage: str | None = None, outcome: str | None = None, status: str | None = None):
        if stage:
            self.stage = stage
        db.execute("UPDATE runs SET stage=?, state_json=?, outcome=COALESCE(?, outcome), status=COALESCE(?, status)"
                   " WHERE id=?", (self.stage, json.dumps(self.state, default=str), outcome, status, self.id))

    def write(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8", newline="\n")
        emit(self.id, self.state.get("phase", 1), "file", name, path=str(p))
        return p

    @property
    def brief(self) -> FounderBrief:
        return FounderBrief(**self.state["brief"])

    def claims(self) -> list[Claim]:
        return [Claim(**c) for c in self.state.get("claims", [])]

    def ledger(self) -> dict[str, Claim]:
        return {c.id: c for c in self.claims()}

    def variant(self, n: int | None = None) -> Variant:
        n = n or self.state.get("variant_n", 1)
        return Variant(**self.state["variants"][n - 1])

    def next_variant(self) -> int | None:
        """The best-scored angle not researched yet (the pivot target), or None."""
        tried = set(self.state.get("research", {})) | {str(self.state.get("variant_n", 1))}
        ranking = self.state.get("ranking") or []
        excluded = {r["n"] for r in ranking if r.get("excluded")}
        order = [r["n"] for r in sorted(ranking, key=lambda r: -r.get("signal", 0)) if r["n"] not in excluded]
        order += [i for i in range(1, len(self.state.get("variants") or []) + 1) if i not in order and i not in excluded]
        return next((n for n in order if str(n) not in tried), None)


def load(run_id: str) -> Run:
    row = db.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
    if row is None:
        raise KeyError(run_id)
    return Run(row)


def list_runs(limit: int = 30) -> list[dict]:
    return db.query("SELECT id, created_at, label, mode, stage, status, outcome FROM runs ORDER BY created_at DESC LIMIT ?",
                    (limit,))


def say(run: Run, kind: str, **kw) -> None:
    text = voice.line(kind, **kw)
    emit(run.id, run.state.get("phase", 1), "narration", text, event=kind)
    voice.prerender(text)


def progress(run: Run, phase: int, text: str, **data) -> None:
    run.state["phase"] = phase
    emit(run.id, phase, "progress", text, **data)


# ---- start ----------------------------------------------------------------------

def start(brief_text: str, fields: dict | None = None, mode: str = "live", label: str | None = None,
          thresholds: dict | None = None) -> str:
    run_id = datetime.now(timezone.utc).strftime("r%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    th = thresholds or gates.load_thresholds()
    brief_raw = {"text": brief_text, "fields": {k: v for k, v in (fields or {}).items() if v}}
    sha = gates.thresholds_sha256(th, brief_raw)
    db.execute("INSERT INTO runs (id, created_at, label, mode, brief_json, stage, status, thresholds_sha256, state_json)"
               " VALUES (?,?,?,?,?,?,?,?,?)", (run_id, utcnow(), label, mode, json.dumps(brief_raw), "intake",
                                               "running", sha, json.dumps({"thresholds": th, "phase": 1})))
    # First log entry of every run: the pre-registered thresholds and their hash.
    log_action(run_id, "gatekeeper", "preregister_thresholds", model=None, cost=0, thresholds_sha256=sha,
               thresholds=th["gate1_evidence"])
    run = load(run_id)
    (run.dir / "thresholds.json").write_text(json.dumps({"thresholds_sha256": sha, "gates": th, "brief": brief_raw},
                                                        indent=2, ensure_ascii=False), encoding="utf-8")
    say(run, "run_started", sha=sha)
    return run_id


def run_pipeline(brief_text: str, fields: dict | None = None, mode: str = "live", label: str | None = None) -> str:
    run_id = start(brief_text, fields, mode, label)
    advance(run_id)
    return run_id


def advance(run_id: str) -> str:
    """Run stages until one needs the founder, the run stops, or it is done."""
    run = load(run_id)
    steps = {
        "intake": stage_intake, "phase1": stage_phase1, "phase2": stage_phase2, "gate2": stage_gate2,
        "phase3": stage_phase3, "phase4": stage_phase4, "phase5": stage_phase5, "payment_test": stage_payment_test,
        "refund": stage_refund, "phase6": stage_phase6,
    }
    for _ in range(20):
        run = load(run_id)
        if run.stage in ("done", "stopped") or run.stage in WAITING:
            break
        fn = steps.get(run.stage)
        if fn is None:
            break
        try:
            fn(run)
        except llm.LLMError as e:
            busy_waits = run.state.get("busy_waits", 0)
            if ("429" in str(e) or "unreachable" in str(e).lower()) and busy_waits < 3:
                # The free tier is busy: wait visibly and try the same step again, without the founder's help.
                wait = 20 * (busy_waits + 1)
                run.state["busy_waits"] = busy_waits + 1
                run.save()
                log_action(run.id, "orchestrator", "wait_for_busy_model", stage=run.stage, seconds=wait)
                emit(run.id, run.state.get("phase", 1), "progress",
                     f"NVIDIA's free service is busy, so I'm waiting {wait} seconds and trying this step again.")
                time.sleep(wait)
                continue
            run.state.pop("busy_waits", None)
            run.state["error"] = str(e)[:300]
            run.state["error_message"] = friendly_error(str(e))
            log_action(run.id, "orchestrator", "stage_failed", stage=run.stage, error=str(e)[:200])
            emit(run.id, run.state.get("phase", 1), "error", run.state["error_message"])
            run.save(status="error")
            break
        except Exception as e:  # noqa: BLE001
            run.state["error"] = traceback.format_exc()[-800:]
            run.state["error_message"] = ("Something went wrong on our side at this step. Your run is saved; "
                                          "press Try again to pick up where it stopped.")
            log_action(run.id, "orchestrator", "stage_failed", stage=run.stage, error=str(e)[:200])
            emit(run.id, run.state.get("phase", 1), "error", run.state["error_message"])
            run.save(status="error")
            raise
    run = load(run_id)
    usage = llm.usage(run_id)
    run.state["usage"] = usage
    run.save()
    return run.stage


def friendly_error(raw: str) -> str:
    """Plain words for a founder; the raw text stays in the run state and the log."""
    r = raw.lower()
    if "429" in r or "rate" in r:
        return ("The AI service is busy right now, so I paused. Your run is saved: press Try again in "
                "a few seconds and I'll pick up where I stopped.")
    if "api_key" in r or "401" in r or "403" in r:
        return ("The NVIDIA key is missing or not accepted. Add a valid NVIDIA_API_KEY to .env, or set "
                "LLM_PROVIDER=ollama to use the local model, then press Try again.")
    if "unreachable" in r or "timed out" in r or "timeout" in r or "connect" in r:
        return ("I couldn't reach the AI model. With Docker the local model may still be downloading; "
                "otherwise check the connection. Then press Try again; your run is saved.")
    if "invalid json" in r:
        return "The AI gave an answer I couldn't use. Press Try again and I'll ask it once more."
    return "The AI service returned an error. Your run is saved; press Try again to pick up where it stopped."


def retry(run_id: str) -> dict:
    """The founder's Try again button after an error: clear it and continue from the same step."""
    run = load(run_id)
    if run.state.get("error") is None and db.query_one("SELECT status FROM runs WHERE id=?", (run.id,)).get("status") != "error":
        return {"ok": False, "error": "Nothing needs retrying."}
    run.state.pop("error", None)
    run.state.pop("error_message", None)
    log_action(run.id, "founder", "retry_after_error", stage=run.stage)
    run.save(status="running")
    return {"ok": True, "stage": run.stage}


# ---- Phase 1: intake + eligibility ----------------------------------------------------

def stage_intake(run: Run) -> None:
    progress(run, 1, "Intake and eligibility check")
    text = run.brief_raw["text"] + "\n" + "\n".join(f"{k}: {v}" for k, v in run.brief_raw["fields"].items())
    res = guard.check_input(text, scope="brief", use_model=not run.state.get("clarified"), run_id=run.id)
    log_action(run.id, "guard", "check_brief", model=llm.model_name() if res.layer == "model" else None, cost=0,
               verdict=res.verdict, rule=res.rule, layer=res.layer)
    if res.verdict == "clarify" and not run.state.get("clarified"):
        run.state["clarify"] = res.message
        emit(run.id, 1, "clarify", res.message)
        run.save("await_clarify")
        return
    if res.blocked:
        excluded = res.rule if res.verdict == "stop" else None
        dec = GateDecision(run_id=run.id, gate="phase1_eligibility", outcome="stop",
                           reason="excluded_category" if excluded else "guard_refusal", rule_fired=res.rule or "",
                           thresholds_sha256=run.sha, recommendation=res.message, failed_checks=[res.rule or ""])
        run.write("phase1_gate_eligibility.md", eligibility_md(dec, res))
        log_action(run.id, "gatekeeper", "eligibility_gate", outcome="stop", reason=dec.reason, rule_fired=res.rule)
        say(run, "refusal", rule=res.rule, message=res.message) if not excluded else \
            say(run, "gate", outcome="stop", reason="excluded_category")
        run.state["gate1"] = dec.model_dump()
        run.save("stopped", outcome="stop", status="stopped")
        return
    brief = intake.run(run.id, run.brief_raw["text"], run.brief_raw["fields"])
    run.state["brief"] = brief.model_dump()
    run.save("phase1")


def eligibility_md(dec: GateDecision, res) -> str:
    return (f"# Phase 1 gate: eligibility\n\n**Outcome:** {dec.outcome.upper()}\n\n**Reason:** {dec.reason}\n\n"
            f"**Rule fired:** {res.rule} ({res.layer})\n\n**Matched:** `{res.matched or ''}`\n\n"
            f"**Explanation:** {res.message}\n\n**Thresholds SHA-256:** `{dec.thresholds_sha256}`\n")


# ---- Phase 1: discover --------------------------------------------------------------

def gather(run: Run, variant: Variant, caps: dict, limits: dict, broaden: bool = False) -> tuple[list[Hit], list[SourceCall], dict[int, list[Hit]], dict | None]:
    """Call the sources with per-run caps. Returns hits, calls, hits per call index, wiki context."""
    since = int((datetime.now(timezone.utc) - timedelta(days=30.44 * limits["hn_lookback_months"])).timestamp())
    queries = list(variant.pain_queries) or [variant.job_to_be_done]
    if broaden:
        queries = queries[::-1] + [" ".join(variant.segment.split()[:3])]
    timeout = limits["source_timeout_s"]
    jobs: list[tuple] = []
    hn, se, gh, sx = HackerNews(), StackExchange(), GitHub(), SearXNG()
    for q in queries[: caps["hn"]]:
        jobs.append((hn, q, {"since_ts": since, "timeout": timeout, "tags": "comment"}))
    # Stack Exchange full-text search needs short queries: use the 2-3 word job query first.
    from sources.base import stopwords
    def _short(q: str) -> str:                       # 2-3 content words ("clients pay invoices late" -> "clients pay invoices")
        words = [w for w in q.split() if w.lower() not in stopwords() and len(w) > 2]
        return " ".join(words[:3]) or q
    se_queries = [variant.competitor_query] + [_short(q) for q in queries]
    for q in se_queries[: caps["stackexchange"]]:
        jobs.append((se, q, {"site": variant.se_site, "timeout": timeout}))
    for q in [variant.competitor_query][: caps["github"]]:
        jobs.append((gh, q, {"timeout": timeout}))
    searx_on = bool(os.environ.get("SEARXNG_URL", "").strip())
    for q in (queries[: caps["searxng"]] if searx_on else []):
        jobs.append((sx, q, {"language": variant.language, "fetch": max(1, caps["searxng_fetch"] // max(1, caps["searxng"])),
                             "timeout": timeout}))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda j: j[0].search(j[1], **j[2]), jobs))
    wiki = wikipedia.context(variant.segment, variant.language, topic=verifier.topic_keywords(variant))
    hits, calls, by_call, seen = [], [], {}, set()
    for i, (hs, call) in enumerate(results):
        calls.append(call)
        by_call[i] = hs
        log_action(run.id, "researcher", f"search_{call.source}", sources=[h.url for h in hs][:10], model=None,
                   cost=0, query=call.query, ok=call.ok, n_hits=call.n_hits, error=call.error, seconds=call.seconds)
        for h in hs:
            if h.url in seen or not h.sentences:
                continue
            seen.add(h.url)
            hits.append(h)
    if not searx_on:
        log_action(run.id, "researcher", "searxng_not_deployed", model=None, cost=0,
                   note="SEARXNG_URL not set: SearXNG is not deployed for this run and is not queried")
    if wiki:
        log_action(run.id, "researcher", "wikipedia_context", sources=[wiki["url"]], model=None, cost=0)
    return hits, calls, by_call, wiki


def excluded_variant(v: Variant) -> str | None:
    """The Scout's angles get the same excluded-category check as the founder's brief. A word that only
    might mean an excluded category (the ask-the-founder tier) also rules an angle out: nobody confirmed it."""
    res = guard.classify_brief(f"{v.title}. {v.segment}: {v.job_to_be_done}. {'; '.join(v.pain_queries)}; {v.competitor_query}")
    if res.verdict == "stop":
        return (res.category or "excluded").replace("_", " ")
    if res.verdict == "clarify":
        return f"may be excluded ('{res.matched}')"
    return None


def score_alternatives(run: Run, variants: list[Variant], max_age_months: int) -> list[dict]:
    """Rank the eligible angles by recent first-person complaints (code only); fall back to the first."""
    excluded = {v.n: why for v in variants if (why := excluded_variant(v))}
    for n, why in excluded.items():
        log_action(run.id, "guard", "exclude_variant", variant=n, why=why)
    ok = [v for v in variants if v.n not in excluded] or variants[:1]
    try:
        rows = scorer.rank(run.id, run.brief, ok, max_age_months)
    except Exception as e:  # noqa: BLE001 - ranking is advisory; research still runs
        log_action(run.id, "scorer", "score_alternatives_failed", error=str(e)[:160])
        rows = [{"n": v.n, "title": v.title, "chosen": v.n == ok[0].n} for v in ok]
    if rows and "errors" in rows[0] and all(r["errors"] for r in rows):
        for r in rows:
            r["chosen"] = r["n"] == ok[0].n
    rows += [{"n": v.n, "title": v.title, "excluded": excluded[v.n], "chosen": False}
             for v in variants if v.n in excluded and all(r["n"] != v.n for r in rows)]
    return rows


def research_variant(run: Run, variant: Variant, broaden: bool = False) -> dict:
    rt = runtime()
    mode_cfg, limits = rt[run.mode], rt["limits"]
    hits, calls, by_call, wiki = gather(run, variant, mode_cfg["caps"], limits, broaden)
    unavailable = sorted({c.source for c in calls if not c.ok})
    say(run, "sources_done", hits=len(hits), calls=len(calls), unavailable=unavailable)
    topic = verifier.topic_keywords(variant)
    # People describing the problem come first (a pain or payment cue in their own words), then other
    # on-topic posts; GitHub repositories are competitor evidence only, so at most three take a slot.
    def rank(h):
        cue = bool(verifier.match_cue("pain", h.text) or verifier.match_cue("wtp", h.text))
        return (-cue, h.source == "github", -len(verifier.overlap(h.title + " " + h.text, topic)), -(h.engagement or 0))
    ranked = sorted((h for h in hits if verifier.is_on_topic(h.title + " " + h.text, topic, 1)), key=rank)
    shown, n_github = [], 0
    for h in ranked:
        if h.source == "github":
            if n_github >= 3:
                continue
            n_github += 1
        shown.append(h)
        if len(shown) >= limits["max_hits_shown"]:
            break
    start_n = len(run.state.get("hit_counter", [])) + 1
    for i, h in enumerate(shown, start=start_n):
        h.id = f"H{i}"
    run.state.setdefault("hit_counter", []).extend(h.id for h in shown)
    shown_ids = {h.id: verifier.select_sentences(h, topic, limits["max_sentences_per_hit"]) for h in shown}
    hits_by_id = {h.id: h for h in shown}
    model_failure = False
    items: list[dict] = []
    if shown:
        try:
            items = researcher.run(run.id, variant, shown, shown_ids)
        except llm.LLMError:
            model_failure = True
    start_c = len(run.state.get("claims", [])) + 1
    claims = verifier.build_claims(run.id, hits_by_id, items, start=start_c)
    # Two readers: sentences that pass code's own published test (first person, on topic, a pain or payment
    # cue, not a question, link or pitch) but that the model skipped are added by code, then verified like
    # every other claim. A model that under-selects can no longer hide evidence.
    added = []
    if not model_failure:
        for ref in verifier.missed_qualified(hits_by_id, shown_ids, claims, variant):
            hid, sid = ref.split(".S")
            s = hits_by_id[hid].sentences[int(sid) - 1]
            kind = "pain" if verifier.match_cue("pain", s) else "wtp"
            added.append({"hit_id": hid, "sentence_ids": [int(sid)], "kind": kind,
                          "claim_text": "Selected by code: the writer's own " + ("complaint" if kind == "pain" else "payment")})
        if added:
            claims += verifier.build_claims(run.id, hits_by_id, added, start=start_c + len(claims))
            log_action(run.id, "verifier", "add_code_qualified_sentences", model=None, cost=0, n=len(added),
                       refs=[f"{a['hit_id']}.S{a['sentence_ids'][0]}" for a in added])
    verifier.mark_eligible(claims, variant)
    say(run, "verifying")
    stats = verifier.verify_live(claims, cap=mode_cfg["caps"]["verify"], timeout=limits["verify_timeout_s"],
                                 min_chars=limits["min_quote_chars_fuzzy"], threshold=limits["fuzzy_threshold"])
    th = run.state["thresholds"]
    verifier.apply_relevance(claims, variant, th["gate1_evidence"]["max_age_months"])
    log_action(run.id, "verifier", "verify_quotes", sources=sorted({c.url for c in claims if c.url}), model=None,
               cost=0, **stats)
    missed = verifier.missed_qualified(hits_by_id, shown_ids, claims, variant) if not model_failure else []
    cov, cov_rows = gates.coverage(calls, by_call, variant, th["gate1_evidence"]["min_on_topic_hits"])
    metrics = gates.compute_metrics(claims, run.brief, cov, th)
    say(run, "verified", live=stats["verified_live"], archived=metrics["claims_archived"],
        counted=sum(1 for c in claims if c.weight > 0))
    return {"variant_n": variant.n, "claims": [c.model_dump(mode="json") for c in claims],
            "hits": {h.id: {"url": h.url, "source": h.source, "title": h.title, "shown": shown_ids[h.id],
                            "sentences": [h.sentences[i - 1] for i in shown_ids[h.id]]} for h in shown},
            "calls": [c.model_dump() for c in calls], "coverage_rows": cov_rows, "metrics": metrics,
            "missed": missed, "model_failure": model_failure, "wiki": wiki, "verify_stats": stats,
            "unavailable": unavailable}


def stage_phase1(run: Run) -> None:
    progress(run, 1, "Phase 1: Discover")
    say(run, "phase", n=1, name=PHASE_NAMES[1])
    th = run.state["thresholds"]
    if "variants" not in run.state:
        variants = scout.run(run.id, run.brief)
        run.state["variants"] = [v.model_dump() for v in variants]
        progress(run, 1, "Comparing the angles")
        ranking = score_alternatives(run, variants, th["gate1_evidence"]["max_age_months"])
        run.state["ranking"] = ranking
        chosen = next((r["n"] for r in ranking if r.get("chosen")), 1)
        run.state["variant_n"] = chosen
        run.write("phase1_step1_opportunities.md", opportunities_md(run, variants))
        say(run, "variants", title=run.variant(chosen).title)
        run.save()
    rt = runtime()[run.mode]
    variant_n = run.state.get("variant_n", 1)
    repeats = run.state.get("repeats", 0)
    done_key = f"{variant_n}:{repeats}"
    if run.state.get("research_done") == done_key and str(variant_n) in run.state.get("research", {}):
        # A retry after a pause (for example a rate limit at the debate) reuses the search already made,
        # so quotes are never counted twice.
        research = run.state["research"][str(variant_n)]
    else:
        research = research_variant(run, run.variant(variant_n), broaden=repeats > 0)
        run.state.setdefault("claims", []).extend(research.pop("claims"))
        run.state.setdefault("research", {})[str(variant_n)] = research
        run.state["research_done"] = done_key
        run.save()
    if run.mode == "full" and not run.state.get("others_researched"):
        for n in range(1, min(rt["variants_researched"], len(run.state["variants"])) + 1):
            if n == variant_n:
                continue
            other = research_variant(run, run.variant(n))
            run.state["claims"].extend(other.pop("claims"))
            run.state["research"][str(n)] = other
        run.state["others_researched"] = True
    run.write("phase1_step2_claims.json", claims_json(run))
    claims = [c for c in run.claims() if any(c.hit_id == h for h in research["hits"])]
    metrics = research["metrics"]
    # Code decides first; the for-and-against debate only explains, so it never blocks the verdict and is
    # skipped when there is nothing to argue about (the sources could not see the market, or the research failed).
    dec = gates.evaluate_gate1(run.id, metrics, th, run.brief_raw, run.sha, model_failure=research["model_failure"],
                               missed=research["missed"], repeats=repeats, variant_n=variant_n,
                               n_variants=len(run.state["variants"]), next_variant=run.next_variant())
    args = {"advocate": [], "skeptic": []}
    run.state.pop("debate", None)
    if dec.reason not in ("insufficient_evidence", "model_failure", "model_suspect"):
        progress(run, 1, "Weighing the case for and against")
        known = {k: v for k, v in run.state.get("brief", {}).items()
                 if k in ("skills", "budget", "hours_per_week", "target_market", "values") and v and "unspecified" not in str(v)}
        try:
            args = debate.run(run.id, claims, metrics, run.variant(variant_n).title,
                              "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in known.items()))
            run.state["debate"] = {k: [s.model_dump() for s in v] for k, v in args.items()}
            say(run, "debate", advocate=args["advocate"][0].text if args["advocate"] else "",
                skeptic=args["skeptic"][0].text if args["skeptic"] else "")
        except llm.LLMError as e:
            log_action(run.id, "orchestrator", "debate_skipped_model_unavailable", error=str(e)[:160])
    if dec.goalpost_moved:
        log_action(run.id, "gatekeeper", "goalpost_moved", goalpost_moved=True)
    log_action(run.id, "gatekeeper", "evidence_gate", sources=sorted({c.url for c in claims if c.weight > 0}),
               model=None, cost=0, outcome=dec.outcome, reason=dec.reason, rule_fired=dec.rule_fired,
               thresholds_sha256=dec.thresholds_sha256, goalpost_moved=dec.goalpost_moved)
    if dec.outcome == "stop" and run.mode == "live" and len(run.state["variants"]) > 1:
        dec.recommendation += f" (STOP for variant {variant_n}; the other angles were scored but not researched.)"
    run.state["gate1"] = dec.model_dump()
    say(run, "gate", **dec.model_dump())
    prov = render.Provenance()
    run.write("phase1_gate_decision.md", gate1_md(run, dec, claims, args, prov))
    run.write("phase1_step3_market.md", market_md(run, run.variant(variant_n), claims, research.get("wiki")))
    run.write("phase1_step4_interview-kit.md", interview_kit_md(run, run.variant(variant_n), dec))
    prov.write(run.dir)
    emit(run.id, 1, "gate", dec.outcome, gate="gate1_evidence", reason=dec.reason, rule=dec.rule_fired)
    if dec.outcome == "repeat" and dec.reason == "near_miss" and rt["auto_rerun"] and repeats < th["gate1_evidence"]["max_repeats"]:
        run.state["repeats"] = repeats + 1
        run.save("phase1")
        return
    if dec.outcome == "go":
        run.save("phase2", outcome="go")
    elif dec.outcome == "stop":
        run.save("stopped", outcome="stop", status="stopped")
    else:
        run.state["waiting_for"] = "gate1_decision"
        run.save("await_founder", outcome=dec.outcome, status="waiting")


# ---- Phase 1 renderers -------------------------------------------------------------

def opportunities_md(run: Run, variants: list[Variant]) -> str:
    fit, parts = gates.founder_fit(run.brief)
    lines = ["# Phase 1, step 1: Opportunities", "",
             f"**Founder idea:** {run.brief.idea}", "",
             f"**Founder fit (computed in code from the brief, 0-5):** {fit}  ",
             "Components: " + ", ".join(f"{k}={v}" for k, v in parts.items()) + " (unspecified fields count 0.5).", "",
             "| # | Variant | Segment | Job to be done | Pain queries | Competitor query | SE site |",
             "|---|---|---|---|---|---|---|"]
    for v in variants:
        lines.append(f"| {v.n} | {v.title} | {v.segment} | {v.job_to_be_done} | {'; '.join(v.pain_queries)} | "
                     f"{v.competitor_query} | {v.se_site} |")
    lines += ["", "Variants are proposals from the Scout model and are research targets, not market claims.", ""]
    ranking = run.state.get("ranking") or []
    if any("signal" in r for r in ranking):
        g = run.state["thresholds"]["gate1_evidence"]
        lines += ["## Scored against each other (code only, before deep research)", "",
                  f"Each angle's pain queries were run against Hacker News comments from the last {g['max_age_months']} months "
                  f"(https://hn.algolia.com/api/v1/search). Code counted comments that are on topic and read as the "
                  "writer's own complaint (first person, a pain cue, not a product pitch). Fit is the share of the "
                  "angle's segment and job words found in the founder's skills, market and idea.", "",
                  "| # | Variant | Comments checked | On topic | First-person complaints | Founder fit | Signal | Researched first |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in sorted(ranking, key=lambda r: -r.get("signal", -1)):
            if r.get("excluded"):
                lines.append(f"| {r['n']} | {r['title']} | - | - | - | - | - | never: {r['excluded']} |")
                continue
            lines.append(f"| {r['n']} | {r['title']} | {r['comments_checked']} | {r['on_topic']} | {r['complaints']} | "
                         f"{r['fit']} | {r['signal']} | {'**yes**' if r.get('chosen') else 'pivot target'} |")
        lines += ["", "Signal = complaints + 0.25 x on-topic comments + 2 x fit. ASSUMPTION: these weights are a team "
                  "default; the counts only rank the angles and are never counted as evidence at a gate. "
                  "The deep research below (step 2) is what Gate 1 reads.", ""]
    else:
        lines += [f"Variant {run.state.get('variant_n', 1)} is researched first.", ""]
    return "\n".join(lines)


def claims_json(run: Run) -> str:
    data = {"run_id": run.id, "thresholds_sha256": run.sha, "note": (
        "quotes are extracted by code from the source record and re-checked against the public page where "
        "reachable; a claim counts only if code confirms it is on-topic and contains a pain or payment cue."),
        "claims": [], "source_calls": {}}
    for c in run.claims():
        d = c.model_dump(mode="json")
        d.pop("run_id", None)
        data["claims"].append(d)
    for n, r in run.state.get("research", {}).items():
        data["source_calls"][f"variant_{n}"] = r.get("coverage_rows", [])
    return json.dumps(data, indent=2, ensure_ascii=False)


def claim_table(claims: list[Claim]) -> str:
    rows = ["| ID | Kind | Status | Weight | Cue | Quote | Source |", "|---|---|---|---|---|---|---|"]
    for c in sorted(claims, key=lambda c: (-c.weight, c.id)):
        quote = (c.quote or "").replace("|", "/")
        quote = quote[:220] + ("..." if len(quote) > 220 else "")
        label = c.status.upper() if c.weight > 0 else ("ASSUMPTION" if c.label == "ASSUMPTION" else c.status + " (weight 0)")
        rows.append(f"| {c.id} | {c.kind} | {label} | {c.weight} | {c.cue_matched or '-'} | \"{quote}\" "
                    f"{('<br>' + c.weight_note) if c.weight_note else ''} | {c.url or 'ASSUMPTION'} |")
    return "\n".join(rows)


def plain_summary(dec: GateDecision) -> str:
    """One founder-readable sentence at the top of every gate file (the exact figures follow below)."""
    m, g = dec.metrics or {}, dec.thresholds or {}
    pain, need = m.get("sourced_pain"), g.get("min_sourced_pain")
    if dec.outcome == "go":
        return "Enough people describe this problem in their own words, from more than one place. Worth taking further."
    if dec.reason in ("model_failure", "model_suspect"):
        return "The research didn't come back clean, so no verdict was given on the idea. Search again."
    if dec.outcome == "repeat" and dec.reason == "insufficient_evidence":
        return ("The public forums searched can't see this market well enough to call it either way. That is not "
                "proof nobody wants it: the next step is five short conversations (see the interview kit).")
    if dec.outcome == "repeat":
        return "Close to the bar. A wider search could tip it either way."
    if dec.outcome == "pivot":
        return "The problem looks real, but this version of the idea doesn't fit it. Try another angle."
    if pain is not None and need is not None:
        n = int(round(pain))
        found = "no one clearly describing the problem" if n == 0 else f"{n} real complaint{'s' if n != 1 else ''}"
        return (f"People discuss this topic, but ProveIt found {found}, against the {need} it set as the bar before "
                "searching. Recommendation: don't build this as it stands.")
    return dec.recommendation


def gate1_md(run: Run, dec: GateDecision, claims: list[Claim], args: dict, prov: render.Provenance) -> str:
    ledger = run.ledger()
    used: list[str] = []
    g = dec.thresholds
    m = dec.metrics
    rows = [("sourced_pain (weighted)", m.get("sourced_pain"), f">= {g['min_sourced_pain']}"),
            ("distinct_sources", m.get("distinct_sources"), f">= {g['min_distinct_sources']}"),
            ("recent_share (<= {} months)".format(g["max_age_months"]), m.get("recent_share"), f">= {g['min_recent_share']}"),
            ("wtp_signals", m.get("wtp_signals"), f">= {g['min_wtp_signals']}"),
            ("competitors (distinct, verified)", m.get("competitors"), f"in {g['competitor_band']}"),
            ("founder_fit (0-5, code)", m.get("founder_fit"), f">= {g['min_founder_fit']}"),
            ("coverage", m.get("coverage"), f">= {g['min_coverage']}")]
    out = [f"# Phase 1 gate: evidence decision", "",
           f"## Outcome: {dec.outcome.upper()}", "",
           f"> **In plain words:** {plain_summary(dec)}", "",
           f"- **Reason:** {dec.reason}", f"- **Rule fired:** {dec.rule_fired}",
           f"- **Next step:** {dec.next_step or '-'}", f"- **Recommendation:** {dec.recommendation}",
           f"- **Variant researched:** {run.variant().n}. {run.variant().title}",
           f"- **Pre-registered thresholds SHA-256:** `{dec.thresholds_sha256}`",
           f"- **Goalpost moved:** {str(dec.goalpost_moved).lower()}",
           f"- **Founder decision:** {dec.founder_decision}", "",
           "Thresholds are team defaults (ASSUMPTION), registered before any source was called.", "",
           "## Metrics vs thresholds", "", "| Check | Value | Threshold | Pass |", "|---|---|---|---|"]
    for name, val, thr in rows:
        key = name.split(" ")[0]
        key = "competitor_band" if key == "competitors" else key
        out.append(f"| {name} | {val} | {thr} | {'no' if key in dec.failed_checks else 'yes'} |")
    out += ["", f"Claims: {m.get('claims_total', 0)} total, {m.get('claims_verified_live', 0)} verified live, "
            f"{m.get('claims_archived', 0)} archived matches, {m.get('claims_unverified', 0)} unverified.", ""]
    research = run.state.get("research", {}).get(str(run.variant().n), {})
    if research.get("missed"):
        out.append(f"Code-qualified sentences not selected by the model: {', '.join(research['missed'])}.\n")
    if args.get("advocate") or args.get("skeptic"):
        out += ["## Advocate (case for GO)", "",
                render.render_list([Statement(**s) if isinstance(s, dict) else s for s in args["advocate"]], ledger,
                                   used, prov, "phase1_gate_decision.md"), "",
                "## Skeptic (case for STOP)", "",
                render.render_list([Statement(**s) if isinstance(s, dict) else s for s in args["skeptic"]], ledger,
                                   used, prov, "phase1_gate_decision.md"), "",
                "The arguments are model-written and decide nothing; `gates.py` applies the rule precedence.", ""]
    else:
        out += ["## For and against", "",
                "Not written for this verdict: the public sources gave too little to argue about, or the research "
                "did not come back clean. The arguments never decide a checkpoint.", ""]
    out += ["## Source coverage", "", "| Source | Query | OK | Hits | On-topic | Covered |", "|---|---|---|---|---|---|"]
    for r in research.get("coverage_rows", []):
        out.append(f"| {r['source']} | {r['query']} | {r['ok']} | {r['hits']} | {r['on_topic']} | {r['covered']} |"
                   + (f" {r['error'][:60]}" if r.get("error") else ""))
    out += ["", "## Claim ledger (this variant)", "", claim_table(claims), "",
            render.sources_section(used, ledger)]
    return "\n".join(out)


def market_md(run: Run, variant: Variant, claims: list[Claim], wiki: dict | None) -> str:
    comps = [c for c in claims if c.kind == "competitor" and c.weight > 0]
    prices = [c for c in claims if c.kind == "price_point" and c.weight > 0]
    lines = ["# Phase 1, step 3: Market definition", "",
             f"**Segment:** {variant.segment} (from the Scout variant; a research target, not a market claim)", "",
             f"**Job to be done:** {variant.job_to_be_done}", "", "## Alternatives and competitors (verified claims only)", ""]
    lines += [f"- [{c.id}] \"{c.quote}\" ({c.url})" for c in comps] or \
        ["- ASSUMPTION: no verified competitor claim in the ledger for this variant."]
    lines += ["", "## Visible prices", ""]
    lines += [f"- [{c.id}] \"{c.quote}\" ({c.url})" for c in prices] or \
        ["- ASSUMPTION: no verified price point in the ledger for this variant."]
    lines += ["", "## Market size", "", "ASSUMPTION: no source in the ledger states a market size, so no TAM/SAM figure is given.", ""]
    if wiki and verifier.is_on_topic(f"{wiki.get('title', '')} {wiki.get('extract', '')}", verifier.topic_keywords(variant)):
        lines += ["## Context (Wikipedia, context only, never evidence)", "", f"{wiki['extract']}", "", f"Source: {wiki['url']}", ""]
    return "\n".join(lines)


def interview_kit_md(run: Run, variant: Variant, dec: GateDecision) -> str:
    seg, job = variant.segment, variant.job_to_be_done
    qs = [f"Tell me about the last time you had to {job.lower().rstrip('.')}. What happened?",
          "What was the hardest part of that, and why?",
          "What did you do about it? What tools, templates or people did you use?",
          "What did that cost you, in money or time, the last time?",
          "Have you looked for a better way? What did you find, and why did you not keep using it?",
          "When did this last come up, and how often has it come up in the past three months?",
          "Who else is involved when this happens?",
          "Is there anything else about this I should have asked?"]
    lines = ["# Phase 1, step 4: Mom Test interview kit", "",
             f"For: {seg}. Questions are about past behaviour only (no hypotheticals, no pitching).", "",
             "## Questions", ""] + [f"{i}. {q}" for i, q in enumerate(qs, start=1)]
    lines += ["", "## Who to talk to (screener)", "",
              f"- They are one of: {seg}.",
              f"- They had to {job.lower().rstrip('.')} at least once in the past three months.",
              "- They are not a friend or family member (polite answers are not evidence).", "",
              "## How to decide after five conversations", "",
              "- **Strong signal:** 3 or more of 5 describe a recent, specific time it went wrong AND already spend "
              "money or real time on a workaround. Carry on to the waiting-list test.",
              "- **Weak signal:** 1-2 of 5 do. Try another angle (a different segment or job).",
              "- **No signal:** nobody can name a recent instance. Stop here; it saved you the build.",
              "- Ask about the past only. Compliments and \"I would buy that\" don't count.", ""]
    lines += ["## Notes template", "", "| Interviewee profile | Date | Last time it happened | Workaround used | "
              "Money/time spent | Strong signal? |", "|---|---|---|---|---|---|", "| | | | | | |", ""]
    if dec.outcome == "repeat" and dec.reason == "insufficient_evidence" or dec.next_step == "mom_test_interviews":
        market = run.brief.target_market if "unspecified" not in run.brief.target_market else "your target region"
        lines += ["## 5-interview plan (the gate said REPEAT: insufficient evidence)", "",
                  "Profiles to find, not named people:", "",
                  f"1. 2 {seg} in {market} who did this job in the past month; ask in local professional groups.",
                  f"2. 1 {seg} who pays for a tool or service for this job today; find them via the tool's community forum.",
                  f"3. 1 {seg} who stopped doing this job themselves; ask in the {variant.se_site} Stack Exchange community.",
                  f"4. 1 person who hires or works with {seg}; ask in your own network.", "",
                  "Interview-notes analysis is STUBBED; record answers in the notes template.", ""]
    return "\n".join(lines)


# ---- founder decisions ------------------------------------------------------------

def _evidence_choice_open(run: Run) -> bool:
    """After Gate 1 (evidence) and before Gate 2, the founder may search again, try another angle or
    override with a reason. Never after an eligibility STOP (excluded product categories)."""
    g1 = run.state.get("gate1") or {}
    return (run.stage in ("await_founder", "stopped") and g1.get("gate") == "gate1_evidence"
            and not run.state.get("gate2") and not run.state.get("override"))


def allowed_decisions(run: Run) -> list[str]:
    """What the founder can do right now; the console shows exactly these buttons."""
    out = []
    if run.stage == "await_clarify":
        out.append("clarify_ok")
    if _evidence_choice_open(run):
        out += ["repeat", "override"]
        if run.next_variant():
            out.append("pivot")
        if run.stage == "await_founder":
            out.append("stop")
    if run.stage == "await_override":
        out += ["override", "stop"]
    if run.stage == "await_gate4":
        out += ["gate4_approve", "gate4_reject"]
    return out


NOT_ALLOWED = {
    "override": "You can only carry on against the evidence at the first or second checkpoint, and never for "
                "a product type ProveIt can't build.",
    "repeat": "Searching again is only possible right after the first checkpoint.",
    "pivot": "There is no other angle left to try for this idea.",
}


def founder_decide(run_id: str, decision: str, reason: str = "") -> dict:
    """Founder buttons: accept | stop | override | pivot | repeat | clarify_ok | gate4_approve | gate4_reject."""
    run = load(run_id)
    if decision in ("override", "repeat", "pivot") and decision not in allowed_decisions(run):
        log_action(run.id, "orchestrator", "refuse_founder_decision", decision=decision, stage=run.stage)
        return {"ok": False, "error": NOT_ALLOWED[decision]}
    if decision == "clarify_ok" and run.stage == "await_clarify":
        log_action(run.id, "founder", "confirm_digital_product", approved_by="founder")
        run.state["clarified"] = True
        run.save("intake", status="running")
        return {"ok": True, "stage": "intake"}
    if decision == "override":
        if len(reason.strip()) < 8:
            return {"ok": False, "error": "Please write a short reason for carrying on; it is saved with the decision."}
        res = guard.check_input(reason, scope="override", use_model=True, run_id=run.id)
        if guard.UNAVAILABLE in (res.notes or []):          # fail closed: no unchecked override
            return {"ok": False, "error": "I couldn't run the safety check on your reason just now (the AI service "
                                          "is busy). Please press it again in a few seconds."}
        if res.blocked:
            log_action(run.id, "guard", "block_override_reason", rule=res.rule)
            return {"ok": False, "error": res.message, "rule": res.rule}
        gate = "gate2" if run.stage == "await_override" else "gate1"
        log_action(run.id, "founder", "founder_override_against_evidence", approved_by="founder", gate=gate,
                   override_reason=reason)
        run.state["override"] = {"gate": gate, "reason": reason, "at": utcnow()}
        run.state.setdefault("overrides", []).append(gate)
        fname = "phase2_gate_decision.md" if gate == "gate2" else "phase1_gate_decision.md"
        if (run.dir / fname).exists():
            txt = (run.dir / fname).read_text(encoding="utf-8")
            txt = txt.replace("- **Founder decision:** pending",
                              f"- **Founder decision:** overridden against the evidence (logged). Reason: {reason}", 1)
            run.write(fname, txt)
        key = "gate2" if gate == "gate2" else "gate1"
        if key in run.state:
            run.state[key]["founder_decision"] = "overridden"
            run.state[key]["override_reason"] = reason
        say(run, "override")
        run.save("phase3" if gate == "gate2" else "phase2", status="running")
        db.execute("UPDATE runs SET override_reason=? WHERE id=?", (reason, run.id))
        return {"ok": True, "stage": run.stage}
    if decision in ("gate4_approve", "gate4_reject") and run.stage == "await_gate4":
        ok = decision == "gate4_approve"
        log_action(run.id, "founder", "gate4_approve" if ok else "gate4_reject", approved_by="founder" if ok else None)
        dec = GateDecision(run_id=run.id, gate="gate4_commercial", outcome="go" if ok else "stop",
                           reason="founder_approved_pricing_and_policies" if ok else "founder_rejected",
                           thresholds={"founder_approval": True}, thresholds_sha256=run.sha, rule_fired="g4_founder",
                           founder_decision="accepted" if ok else "stopped",
                           recommendation="Founder approved the price and the policy drafts." if ok else
                           "Founder rejected; revise pricing or policies.")
        run.write("phase4_gate_decision.md", simple_gate_md("Phase 4 gate: founder approval of price and policies", dec))
        run.state["gate4"] = dec.model_dump()
        rejects = run.state.setdefault("rejections", {})
        rejects["gate4"] = rejects.get("gate4", 0) + (0 if ok else 1)
        redo = not ok and rejects["gate4"] <= 2
        if redo:
            log_action(run.id, "orchestrator", "redo_phase4_after_founder_rejection")
        run.save("phase5" if ok else ("phase4" if redo else "stopped"),
                 status="running" if ok or redo else "stopped")
        return {"ok": True, "stage": run.stage}
    if decision == "pivot":
        n = run.next_variant()
        if n is None:
            return {"ok": False, "error": "Every angle has already been researched."}
        log_action(run.id, "founder", f"pivot_to_variant_{n}", approved_by="founder")
        old = run.dir / "phase1_gate_decision.md"            # keep the verdict on the angle left behind
        if old.exists():
            old.replace(run.dir / f"phase1_gate_variant-{run.state.get('variant_n', 1)}.md")
        run.state["variant_n"] = n
        run.save("phase1", status="running")
        return {"ok": True, "stage": "phase1"}
    if decision == "repeat":
        log_action(run.id, "founder", "repeat_research", approved_by="founder")
        run.state["repeats"] = run.state.get("repeats", 0) + 1
        run.save("phase1", status="running")
        return {"ok": True, "stage": "phase1"}
    if decision in ("accept", "stop") and run.stage not in ("await_founder", "await_override", "await_clarify"):
        return {"ok": False, "error": "There's nothing to decide at this step."}
    if decision in ("accept", "stop"):
        gate_key = "gate2" if run.stage == "await_override" else "gate1"
        log_action(run.id, "founder", f"accept_{gate_key}_recommendation" if decision == "accept" else "stop_run",
                   approved_by="founder")
        if gate_key in run.state:
            run.state[gate_key]["founder_decision"] = "accepted" if decision == "accept" else "stopped"
        run.save("stopped", status="stopped")
        return {"ok": True, "stage": "stopped"}
    return {"ok": False, "error": "That choice isn't available at this step."}


def simple_gate_md(title: str, dec: GateDecision, extra: str = "") -> str:
    return (f"# {title}\n\n## Outcome: {dec.outcome.upper()}\n\n- **Reason:** {dec.reason}\n"
            f"- **Rule fired:** {dec.rule_fired}\n- **Next step:** {dec.next_step or '-'}\n"
            f"- **Recommendation:** {dec.recommendation}\n- **Founder decision:** {dec.founder_decision}\n"
            f"- **Thresholds SHA-256:** `{dec.thresholds_sha256}`\n\n## Metrics\n\n"
            + ("\n".join(f"- {k}: {v}" for k, v in dec.metrics.items()) or "- none: this gate is the founder's decision")
            + "\n\n## Thresholds\n\n"
            + ("\n".join(f"- {k}: {v}" for k, v in dec.thresholds.items()) or "- none") + "\n\n"
            + (f"## Failed checks\n\n" + "\n".join(f"- {f}" for f in dec.failed_checks) + "\n\n" if dec.failed_checks else "")
            + extra)


# ---- approvals ----------------------------------------------------------------

def request_approval(run: Run, action: str, payload: bytes, content_type: str, note: str) -> None:
    ap = approval.request(run.id, action, payload, note=note, content_type=content_type)
    run.state["pending_approval"] = {"id": ap.id, "action": action, "sha": ap.payload_sha256}
    say(run, "approval_needed", action=action, sha=ap.payload_sha256)
    emit(run.id, run.state.get("phase", 1), "approval", action, approval_id=ap.id, sha=ap.payload_sha256)
    run.save("await_approval", status="waiting")


def on_approval_decided(approval_id: str) -> str | None:
    """Called after the founder clicks approve/reject. Executes the gated action with the stored bytes."""
    ap = approval.load(approval_id)
    if ap is None:
        return None
    try:
        run = load(ap.run_id)
        pending = run.state.get("pending_approval") or {}
    except KeyError:
        run, pending = None, {}
    if pending.get("id") != approval_id:
        # A refund a customer asked for from the store page is not a pipeline step: run it whenever the
        # founder approves it (or just log the rejection), whatever stage the run is at.
        if ap.action == "refund":
            import json as _json

            import refunds
            order_id = _json.loads(approval.blob(ap.payload_sha256)[0]).get("order_id")
            if ap.status == "approved":
                refunds.refund(order_id, approval_id)
                log_action(ap.run_id, "orchestrator", "customer_refund_executed", order_id=order_id,
                           approved_by="founder", test=True)
            else:
                log_action(ap.run_id, "orchestrator", "customer_refund_rejected", order_id=order_id)
        return run.stage if run else None
    payload, _ = approval.blob(ap.payload_sha256)
    run.state.pop("pending_approval", None)
    if ap.status == "rejected":
        redo = {"publish_landing_page": "phase2", "open_store": "phase5"}.get(ap.action)
        rejects = run.state.setdefault("rejections", {})
        rejects[ap.action] = rejects.get(ap.action, 0) + 1
        if redo and rejects[ap.action] <= 2:
            log_action(run.id, "orchestrator", f"regenerate_after_rejected_{ap.action}")
            run.save(redo, status="running")
            return redo
        if ap.action == "refund":
            log_action(run.id, "orchestrator", "refund_not_executed_founder_rejected")
            run.save("phase6", status="running")
            return "phase6"
        log_action(run.id, "orchestrator", f"founder_rejected_{ap.action}")
        run.save("stopped", status="stopped")
        return "stopped"
    say(run, "approved", action=ap.action)
    if ap.action == "publish_landing_page":
        approval.publish_landing_page(payload, approval_id, run_id=run.id)
        run.save("gate2", status="running")
    elif ap.action == "open_store":
        approval.open_store(payload, approval_id, run_id=run.id)
        run.save("payment_test", status="running")
    elif ap.action == "refund":
        run.state["refund_approval"] = approval_id
        run.save("refund", status="running")
    return run.stage


# ---- outward copy guard -------------------------------------------------------------

def guarded(run: Run, artifact: str, gen, to_text, scope: str = "outward"):
    """Generate outward copy, check it (rule set C + model check + market-statement rule),
    regenerate once with the violation named, then flag for the founder."""
    obj = gen("")
    for attempt in range(2):
        text = to_text(obj)
        res = guard.check_output(text, scope, use_model=True, run_id=run.id)
        unsourced = render.factual_flags(text)
        if not res.blocked and not unsourced:
            log_action(run.id, "guard", f"check_{artifact}", model=llm.model_name(), cost=0, verdict="allow",
                       attempt=attempt + 1)
            return obj, None
        issue = res.message if res.blocked else "unsourced market statement: " + "; ".join(unsourced)[:200]
        log_action(run.id, "guard", "guard_block", model=llm.model_name() if res.layer == "model" else None, cost=0,
                   artifact=artifact, rule=res.rule or "unsourced_market_statement", attempt=attempt + 1)
        if attempt == 0:
            obj = gen(issue)
    return obj, issue


# ---- Phase 2: validate ----------------------------------------------------------------

def stage_phase2(run: Run) -> None:
    progress(run, 2, "Phase 2: Validate")
    say(run, "phase", n=2, name=PHASE_NAMES[2])
    variant = run.variant()
    ledger = run.ledger()
    claims = [c for c in run.claims() if c.hit_id in run.state["research"][str(variant.n)]["hits"]]
    cv = strategist.canvas(run.id, run.brief, variant, claims)
    prov = render.Provenance()
    used: list[str] = []
    fname = "phase2_step1_lean-canvas.md"
    out = ["# Phase 2, step 1: Lean Canvas", "", f"Variant: {variant.title}", "",
           "Each statement cites verified claim IDs or is labelled ASSUMPTION by code.", ""]
    for cell in strategist.CELLS:
        out += [f"## {cell.replace('_', ' ').title()}", "", render.render_list(getattr(cv, cell), ledger, used, prov, fname), ""]
    out += ["## Riskiest assumption", "", render.render_list([cv.riskiest_assumption], ledger, used, prov, fname), "",
            "## Experiment", "", render.render_list([cv.experiment], ledger, used, prov, fname), "",
            f"Pre-registered demand target: {run.state['thresholds']['gate2_demand']['waitlist_target']} waitlist "
            f"sign-ups in {run.state['thresholds']['gate2_demand']['window_days']} days (team default, ASSUMPTION).", "",
            render.sources_section(used, ledger)]
    run.write(fname, "\n".join(out))

    def to_text(o):
        return "\n".join([o.headline, o.subheadline] + o.benefits + [f.q + " " + f.a for f in o.faq])
    copy, issue = guarded(run, "landing_copy", lambda fb: strategist.landing(run.id, variant, fb), to_text)
    fields = copy.model_dump()
    for f in fields["faq"]:  # deterministic fix: a question goes in q, its answer in a
        if not f["q"].rstrip().endswith("?") and f["a"].rstrip().endswith("?"):
            f["q"], f["a"] = f["a"], f["q"]
    lab = render.label_unsourced_factual
    fields["headline"], fields["subheadline"] = lab(fields["headline"]), lab(fields["subheadline"])
    fields["benefits"] = [lab(b) for b in fields["benefits"]]
    fields["faq"] = [{"q": f["q"], "a": lab(f["a"])} for f in fields["faq"]]
    if issue:
        # Still blocked after a redraft: code removes the questions and benefits the guard blocks, so the
        # founder is never offered copy that breaks a rule; anything left is flagged for the founder.
        def blocked(text: str) -> bool:
            return guard.check_output(text, "outward").blocked
        kept_faq = [f for f in fields["faq"] if not blocked(f["q"] + " " + f["a"])]
        kept_benefits = [b for b in fields["benefits"] if not blocked(b)]
        dropped = len(fields["faq"]) - len(kept_faq) + len(fields["benefits"]) - len(kept_benefits)
        if dropped:
            fields["faq"], fields["benefits"] = kept_faq, kept_benefits
            log_action(run.id, "guard", "drop_blocked_copy", artifact="landing_copy", dropped=dropped)
        rest = "\n".join([fields["headline"], fields["subheadline"]] + fields["benefits"]
                         + [f["q"] + " " + f["a"] for f in fields["faq"]])
        if blocked(rest):
            log_action(run.id, "guard", "flag_for_founder", artifact="landing_copy", issue=issue[:200])
            run.state["landing_issue"] = issue
    for s in [copy.headline, copy.subheadline] + copy.benefits + [f.a for f in copy.faq]:
        prov.add("phase2_step2_landing-page.html", s)
    html = TEMPLATES.get_template("landing.html.j2").render(run_id=run.id, content_note="shown in the approval console",
                                                           **fields)
    run.write("phase2_step2_landing-page.html", html)
    prov.write(run.dir)
    request_approval(run, "publish_landing_page", html.encode("utf-8"), "text/html; charset=utf-8",
                     "Serve the landing page on localhost at /p/<run> (public hosting STUBBED)")


def stage_gate2(run: Run) -> None:
    progress(run, 2, "Gate 2: demand")
    real = db.query_one("SELECT COUNT(*) n FROM signups WHERE run_id=? AND test=0", (run.id,))["n"]
    test = db.query_one("SELECT COUNT(*) n FROM signups WHERE run_id=? AND test=1", (run.id,))["n"]
    dec = gates.evaluate_gate2(run.id, run.state["thresholds"], run.sha, real, test)
    log_action(run.id, "gatekeeper", "demand_gate", model=None, cost=0, outcome=dec.outcome, reason=dec.reason,
               rule_fired=dec.rule_fired)
    run.state["gate2"] = dec.model_dump()
    say(run, "gate", **dec.model_dump())
    run.write("phase2_gate_decision.md", simple_gate_md(
        "Phase 2 gate: demand", dec,
        "Test sign-ups are excluded from every gate while public hosting is STUBBED. "
        "Continuing past this gate needs a logged founder override; Phases 3-5 are then a preview: "
        "demand not yet proven.\n"))
    emit(run.id, 2, "gate", dec.outcome, gate="gate2_demand", reason=dec.reason)
    if dec.outcome == "go":
        run.save("phase3", status="running")
    else:
        run.save("await_override", status="waiting")


# ---- Phase 3: build -----------------------------------------------------------------

def preview_banner(run: Run) -> str:
    gates_over = run.state.get("overrides", [])
    if not gates_over:
        return ""
    names = " and ".join(g.replace("gate", "Gate ") for g in gates_over)
    return f"> PREVIEW after a founder override against the evidence at {names}: demand not yet proven.\n\n"


def stage_phase3(run: Run) -> None:
    progress(run, 3, "Phase 3: Build")
    say(run, "phase", n=3, name=PHASE_NAMES[3])
    variant = run.variant()
    sp = builder.spec(run.id, variant)
    prov = render.Provenance()
    preview = preview_banner(run)
    spec_md = [f"# Phase 3, step 1: Product spec", "", preview + f"**Title:** {sp.title}", "", f"**Audience:** {sp.audience}",
               "", "## Modules", ""] + [f"{i}. **{m.name}**: {m.purpose}" for i, m in enumerate(sp.modules, start=1)] + \
              ["", "## What the product is not", ""] + [f"- {x}" for x in sp.not_included] + [""]
    text = "\n".join(spec_md)
    prov.add("phase3_step1_product-spec.md", sp.audience)
    run.write("phase3_step1_product-spec.md", render.label_unsourced_factual(text))
    n_mod = min(runtime()[run.mode]["modules"], len(sp.modules))
    feedback = ""
    for attempt in range(2):
        modules, csvs, docs, results, dec = _build_and_test(run, variant, sp, n_mod, prov, preview, feedback)
        if dec.outcome == "go":
            break
        feedback = "Fix these QA failures: " + ", ".join(dec.failed_checks)
        log_action(run.id, "qa", "rebuild_after_failed_tests", failed=dec.failed_checks)
    report = ["# Phase 3 gate: test report", "", f"## Outcome: {dec.outcome.upper()}", "",
              "| Check | Passed | Detail |", "|---|---|---|"] + \
             [f"| {r['name']} | {'yes' if r['passed'] else 'no'} | {r['detail'][:80]} |" for r in results] + \
             ["", f"All checks are deterministic code (no model). Build attempts: {attempt + 1}.", ""]
    run.write("phase3_gate_test-report.md", "\n".join(report))
    prov.write(run.dir)
    run.state["gate3"] = dec.model_dump()
    run.state["product"] = {"title": sp.title, "audience": sp.audience, "modules": [m.title for m in modules]}
    say(run, "gate", **dec.model_dump())
    emit(run.id, 3, "gate", dec.outcome, gate="gate3_tests")
    run.save("phase4" if dec.outcome == "go" else "await_founder", status="running" if dec.outcome == "go" else "waiting")


def _build_and_test(run: Run, variant: Variant, sp, n_mod: int, prov: render.Provenance, preview: str, feedback: str):
    import csv as _csv
    import io as _io
    modules, csvs = [], []
    for i in range(n_mod):
        mod = builder.module(run.id, variant, sp, i, feedback)
        modules.append(mod)
        body = [f"# {mod.title}", "", preview + render.label_unsourced_factual(mod.intro), "", "## Checklist", ""] + \
               [f"- [ ] {render.label_unsourced_factual(s)}" for s in mod.steps] + [""]
        for s in [mod.intro] + mod.steps:
            prov.add(f"phase3_step2_module-{i + 1}.md", s)
        run.write(f"phase3_step2_module-{i + 1}.md", "\n".join(body))
        buf = _io.StringIO()
        w = _csv.writer(buf, lineterminator="\n")
        w.writerow(mod.template_columns)
        for row in mod.template_rows:
            w.writerow((row + [""] * len(mod.template_columns))[: len(mod.template_columns)])
        csvs.append(buf.getvalue())
        run.write(f"phase3_step2_template-{i + 1}.csv", buf.getvalue())
    docs = builder.user_docs(sp, modules)
    run.write("phase3_step3_user-docs.md", preview + docs)
    results = qa.run(sp, modules, csvs, docs, n_mod)
    dec = gates.evaluate_gate3(run.id, results, run.sha)
    log_action(run.id, "qa", "run_product_tests", model=None, cost=0, outcome=dec.outcome,
               passed=dec.metrics["passed"], total=dec.metrics["total"])
    return modules, csvs, docs, results, dec


# ---- Phase 4: commercial setup ------------------------------------------------------------

def stage_phase4(run: Run) -> None:
    progress(run, 4, "Phase 4: Commercial setup")
    say(run, "phase", n=4, name=PHASE_NAMES[4])
    claims = run.claims()
    ledger = run.ledger()
    t = pricer.tiers(claims)
    rationale = pricer.rationale(run.id, claims, t)
    prov = render.Provenance()
    used: list[str] = []
    label = "" if t["basis"] == "verified_price_points" else "ASSUMPTION: "
    pts = ", ".join(f"${v:g} [{cid}]" for v, cid in t["points"]) or "none"
    md = ["# Phase 4, step 1: Pricing", "", preview_banner(run),
          "| Tier | Price (USD, one-time) | Basis |", "|---|---|---|",
          f"| Good | {label}${t['good']:.0f} | {t['basis']} |", f"| Better | {label}${t['better']:.0f} | {t['basis']} |",
          f"| Best | {label}${t['best']:.0f} | {t['basis']} |", "",
          f"Verified price points used: {pts}.", "", t["note"], "",
          "No revenue projections or scenarios are produced.", "", "## Rationale", "",
          render.render_list(rationale, ledger, used, prov, "phase4_step1_pricing.md"), "",
          render.sources_section(used, ledger)]
    run.write("phase4_step1_pricing.md", "\n".join(md))
    run.state["pricing"] = {k: t[k] for k in ("good", "better", "best", "basis", "note")}
    title = run.state.get("product", {}).get("title", run.variant().title)

    def to_text(p):
        return "\n".join(p.terms + p.privacy + p.refunds)
    pol, issue = guarded(run, "policies", lambda fb: policy_drafter.run(run.id, title), to_text, scope="policy")
    for s in pol.terms + pol.privacy + pol.refunds:
        prov.add("phase4_step2_policies.md", s)
    def fix(x: str) -> str:   # no invented contact details: the founder fills in their own
        x = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[founder's support email]", x)
        return render.label_unsourced_factual(x)
    md = ["# Phase 4, step 2: Policy drafts", "", f"**{policy_drafter.STAMP}**", "",
          "## Terms (DRAFT)", ""] + [f"- {fix(x)}" for x in pol.terms] + \
         ["", "## Privacy (DRAFT)", "", "What is stored: an email address and a timestamp for the waitlist; order records "
          "from the MOCKED payment test. No passwords and no card numbers are stored.", ""] + [f"- {fix(x)}" for x in pol.privacy] + \
         ["", "## Refunds (DRAFT)", "", "Refund window: 14 days (ASSUMPTION, team default). Every refund is approved by the founder.",
          ""] + [f"- {fix(x)}" for x in pol.refunds] + [""]
    if issue:
        md.append(f"Flagged for founder review: {issue}\n")
    run.write("phase4_step2_policies.md", "\n".join(md))
    prov.write(run.dir)
    emit(run.id, 4, "founder_gate", "gate4", note="Approve or reject the price and policy drafts")
    say(run, "approval_needed", action="gate 4 price and policy review", sha="")
    run.save("await_gate4", status="waiting")


# ---- Phase 5: launch -------------------------------------------------------------------

def stage_phase5(run: Run) -> None:
    progress(run, 5, "Phase 5: Launch (sell, deliver, get paid)")
    say(run, "phase", n=5, name=PHASE_NAMES[5])
    prod = run.state.get("product", {})
    title, audience, modules = prod.get("title", run.variant().title), prod.get("audience", ""), prod.get("modules", [])

    def store_text(o):
        return "\n".join([o.product_name, o.tagline, o.description, o.who_it_is_for, o.who_it_is_not_for] + o.includes)
    st, issue = guarded(run, "store_copy", lambda fb: launcher.store(run.id, title, audience, modules, fb), store_text)
    fields = st.model_dump()
    if modules:  # the store lists exactly what the buyer downloads
        fields["includes"] = [f"{m} (checklist and CSV template)" for m in modules]
    lab = render.label_unsourced_factual
    for k in ("tagline", "description", "who_it_is_for", "who_it_is_not_for"):
        fields[k] = lab(fields[k])
    fields["includes"] = [lab(x) for x in fields["includes"]]
    if issue:
        log_action(run.id, "guard", "flag_for_founder", artifact="store_copy", issue=issue[:200])
        run.state["store_issue"] = issue
    sprov = render.Provenance()
    for s in [st.tagline, st.description, st.who_it_is_for, st.who_it_is_not_for] + st.includes:
        sprov.add("phase5_step1_store-page.html", s)
    sprov.write(run.dir)
    p = run.state["pricing"]
    if len((run.state.get("product") or {}).get("modules") or []) > 1:
        what = ["Module 1 checklist and template", "All modules and templates",
                "All modules and templates, plus the buyer guide"]
    else:
        what = ["The checklist", "The checklist and the CSV template", "The checklist, the CSV template and the buyer guide"]
    tiers = [{"name": n, "price": p[k], "what": w} for n, k, w in zip(("Good", "Better", "Best"), ("good", "better", "best"), what)]
    note = ("Prices: " + p["basis"] + ". " + p["note"]) if p["basis"] == "verified_price_points" else \
        "ASSUMPTION: " + p["note"]
    html = TEMPLATES.get_template("store.html.j2").render(run_id=run.id, tiers=tiers, pricing_note=note, **fields)
    run.write("phase5_step1_store-page.html", html)

    def post_text(o):
        return o.title + "\n" + o.body
    post, pissue = guarded(run, "launch_post", lambda fb: launcher.post(run.id, title, audience, fb, [f"{m} (a checklist and a CSV template)" for m in modules]), post_text)
    from sources.base import split_sentences
    # What the product contains is stated by code, never by the model (which invents extra parts).
    if modules:
        inside = re.compile(r"\b(includ\w*|contain\w*|comes with|you get|inside|packed with|features?)\b", re.I)
        rest = [x for x in split_sentences(post.body) if not inside.search(x)]
        made = f"It includes {', '.join(modules[:-1]) + ' and ' + modules[-1] if len(modules) > 1 else modules[0]}: " \
               f"{'each part is a' if len(modules) > 1 else 'a'} checklist and a CSV template."
        post.body = " ".join([made] + rest)
    if pissue:   # still blocked after a redraft: code drops the sentences the guard blocks
        sentences = split_sentences(post.body)
        kept = [x for x in sentences if not guard.check_output(x, "outward").blocked]
        if len(kept) < len(sentences):
            log_action(run.id, "guard", "drop_blocked_copy", artifact="launch_post", dropped=len(sentences) - len(kept))
            post.body = " ".join(kept)
            if not guard.check_output(post_text(post), "outward").blocked:
                pissue = None
    prov = render.Provenance()
    prov.add("phase5_step1_launch-post-draft.md", post.body)
    body = render.label_unsourced_factual(post.body)
    run.write("phase5_step1_launch-post-draft.md",
              "# DRAFT - NOT POSTED. For the founder to post under their own name.\n\n"
              + (preview_banner(run)) + f"## {post.title}\n\n{body}\n\n"
              + (f"Flagged for founder review: {pissue}\n\n" if pissue else "")
              + "Posting adapters are STUBBED; publish_post is gated and raises NotEnabled.\n")
    prov.write(run.dir)
    request_approval(run, "open_store", html.encode("utf-8"), "text/html; charset=utf-8",
                     "Open the store page on localhost at /store/<run> (payments MOCKED)")


def stage_payment_test(run: Run) -> None:
    """MOCKED sale to cash: purchase -> webhook -> delivery -> replay -> refund needs approval."""
    import delivery
    import payments
    import refunds
    import webhooks
    progress(run, 5, "Sale to cash (MOCKED)")
    price = float(run.state["pricing"]["better"])
    provider = payments.MockPaymentProvider()
    order_id = provider.create_order(run.id, price)
    event = provider.create_checkout(order_id, price)
    first = webhooks.handle(event)
    replay = webhooks.handle(event)
    token = first.get("token")
    ok_before = delivery.check(token) == order_id
    blocked = False
    try:
        refunds.refund(order_id, None)
    except approval.ApprovalRequired:
        blocked = True
    log = run.state.setdefault("payment_log", [])
    log += [f"1. Simulated test purchase (MOCKED): order `{order_id}`, amount ${price:.2f}, test=true.",
            f"2. `payment.succeeded` event `{event['event_id']}`: fee ${event['fee']:.2f} ({payments.FEE_NOTE}), "
            f"net ${event['net']:.2f}, payout `{event['payout_id']}`.",
            f"3. Webhook handled: delivered={first['delivered']}; download token issued (24 h, HMAC-signed).",
            f"4. Webhook replay of the same event_id: status {replay['status']}, duplicate={replay['duplicate']}, "
            f"delivered={replay['delivered']}. Deliveries for this order: {delivery.delivery_count(order_id)}.",
            f"5. Download before refund: {'200 OK' if ok_before else 'denied'}.",
            f"6. Refund attempted without founder approval: {'blocked (ApprovalRequired)' if blocked else 'NOT BLOCKED'}."]
    say(run, "payment")
    run.state["order"] = {"id": order_id, "token": token, "amount": price}
    ap = refunds.request(run.id, order_id)
    run.state["pending_approval"] = {"id": ap.id, "action": "refund", "sha": ap.payload_sha256}
    log.append(f"7. Refund approval requested: `{ap.id}`, payload SHA-256 `{ap.payload_sha256}`.")
    say(run, "approval_needed", action="refund", sha=ap.payload_sha256)
    emit(run.id, 5, "approval", "refund", approval_id=ap.id, sha=ap.payload_sha256)
    run.save("await_approval", status="waiting")


def stage_refund(run: Run) -> None:
    import delivery
    import reconcile
    import refunds
    o = run.state["order"]
    res = refunds.refund(o["id"], run.state["refund_approval"])
    try:
        delivery.check(o["token"])
        after = "200 OK (NOT REVOKED)"
    except delivery.AccessDenied:
        after = "403 Forbidden (access revoked)"
    csv_text, summary = reconcile.run(run.id)
    run.write("phase5_step3_reconciliation.csv", csv_text)
    log = run.state["payment_log"]
    log += [f"8. Founder approved the refund; refund executed: ${res['refunded']:.2f} (test=true).",
            f"9. Download after refund: {after}.",
            f"10. Reconciliation: {summary['orders']} order(s), {summary['mismatches']} mismatch(es), "
            f"balanced={summary['balanced']}. See the reconciliation file (Phase 5, step 3)."]
    md = ["# Payment and delivery test log (MOCKED)", "",
          "Everything below ran through the in-process MockPaymentProvider. No real or sandbox payment was made, "
          "no card details exist anywhere, and every order is test=true and excluded from every gate.", "",
          f"Run: `{run.id}`", ""] + log + [""]
    run.write("payment_test_log.md", "\n".join(md))
    say(run, "refund_done")
    run.save("phase6", status="running")


def stage_phase6(run: Run) -> None:
    progress(run, 6, "Phase 6: Operate and learn (STUBBED)")
    th = dict(run.state["thresholds"])
    th.setdefault("gate6_operate", gates.load_thresholds()["gate6_operate"])
    one = lambda sql: db.query_one(sql, (run.id,))["n"]  # noqa: E731
    metrics = {
        "real_signups": one("SELECT COUNT(*) n FROM signups WHERE run_id=? AND test=0"),
        "real_orders": one("SELECT COUNT(*) n FROM orders WHERE run_id=? AND test=0"),
        "test_orders": one("SELECT COUNT(*) n FROM orders WHERE run_id=? AND test=1"),
        "real_refunds": one("SELECT COUNT(*) n FROM refunds r JOIN orders o ON o.id=r.order_id WHERE o.run_id=? AND o.test=0"),
        "days_since_launch": 0,
    }
    outcome, reason = analyst.decide(metrics, th)
    run.write("phase6_step1_memo.md", analyst.memo(metrics, th))
    log_action(run.id, "analyst", "operate_and_learn_memo", model=None, cost=0, status="STUBBED")
    read = lambda name: (run.dir / name).read_text(encoding="utf-8") if (run.dir / name).exists() else ""  # noqa: E731
    run.write("phase6_step2_support-answers.md",
              analyst.support_faq(run.state.get("product") or {}, run.state.get("pricing") or {},
                                  read("phase4_step2_policies.md"), read("phase3_step3_user-docs.md")))
    log_action(run.id, "support", "draft_support_answers", model=None, cost=0, sent=False)
    run.write("phase6_step3_metrics.md", analyst.metrics_plan(metrics, th))
    log_action(run.id, "analyst", "metrics_plan", model=None, cost=0)
    run.write("phase6_gate_decision.md", "\n".join([
        "# Phase 6 gate: persevere or pivot", "", f"## Outcome: {outcome.upper()}", "",
        f"- **Reason:** {reason}", "- **Decided by:** code, from real records only (rule in phase6_step3_metrics.md)",
        f"- **Real sign-ups / real orders / test orders (excluded):** {metrics['real_signups']} / "
        f"{metrics['real_orders']} / {metrics['test_orders']}", "- **Status:** STUBBED (no live launch in this demo)", ""]))
    log_action(run.id, "gatekeeper", "operate_gate", model=None, cost=0, outcome=outcome, reason=reason)
    emit(run.id, 6, "gate", outcome, gate="gate6_operate", reason=reason)
    say(run, "done")
    run.save("done", status="done")
