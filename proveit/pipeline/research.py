"""Phase 1 research: query the public sources, pick the evidence worth reading, have the model
select quotes, then verify every quote by code.

The model only proposes which sentences are evidence; code chooses what it sees, adds the qualifying
sentences it skipped, re-fetches each quote live and computes every metric the gate reads.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agents import researcher, scorer
from sources import wikipedia
from sources.base import stopwords
from sources.github import GitHub
from sources.hn import HackerNews
from sources.searxng import SearXNG
from sources.stackexchange import StackExchange

from .. import gates, guard, llm, verifier
from ..log import log_action
from ..models import Claim, Hit, SourceCall, Variant
from .run import Run, runtime

SOURCE_WORKERS = 8
DAYS_PER_MONTH = 30.44
MAX_GITHUB_HITS_SHOWN = 3  # repositories are competitor evidence, not people describing the problem
SHORT_QUERY_WORDS = 3
MIN_CONTENT_WORD_LEN = 3


@dataclass
class Gathered:
    hits: list[Hit]
    calls: list[SourceCall]
    hits_by_call: dict[int, list[Hit]]
    wiki: dict | None


# ---- source fan-out ---------------------------------------------------------------


def _short_query(query: str) -> str:
    """Stack Exchange full-text search needs 2-3 content words ("clients pay invoices late" -> "clients pay invoices")."""
    words = [w for w in query.split() if w.lower() not in stopwords() and len(w) >= MIN_CONTENT_WORD_LEN]
    return " ".join(words[:SHORT_QUERY_WORDS]) or query


def _searxng_deployed() -> bool:
    return bool(os.environ.get("SEARXNG_URL", "").strip())


def _source_jobs(variant: Variant, caps: dict, limits: dict, broaden: bool) -> list[tuple]:
    """(source, query, kwargs) for every call this run may make, within the per-run caps."""
    since = int((datetime.now(UTC) - timedelta(days=DAYS_PER_MONTH * limits["hn_lookback_months"])).timestamp())
    timeout = limits["source_timeout_s"]
    queries = list(variant.pain_queries) or [variant.job_to_be_done]
    if broaden:
        queries = queries[::-1] + [" ".join(variant.segment.split()[:SHORT_QUERY_WORDS])]
    hn, stackexchange, github, searxng = HackerNews(), StackExchange(), GitHub(), SearXNG()

    jobs: list[tuple] = [
        (hn, q, {"since_ts": since, "timeout": timeout, "tags": "comment"}) for q in queries[: caps["hn"]]
    ]
    se_queries = [variant.competitor_query] + [_short_query(q) for q in queries]
    jobs += [
        (stackexchange, q, {"site": variant.se_site, "timeout": timeout}) for q in se_queries[: caps["stackexchange"]]
    ]
    jobs += [(github, q, {"timeout": timeout}) for q in [variant.competitor_query][: caps["github"]]]
    if _searxng_deployed():
        fetch = max(1, caps["searxng_fetch"] // max(1, caps["searxng"]))
        jobs += [
            (searxng, q, {"language": variant.language, "fetch": fetch, "timeout": timeout})
            for q in queries[: caps["searxng"]]
        ]
    return jobs


def gather(run: Run, variant: Variant, caps: dict, limits: dict, broaden: bool = False) -> Gathered:
    """Call the sources in parallel with per-run caps and log every call."""
    jobs = _source_jobs(variant, caps, limits, broaden)
    with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as pool:
        results = list(pool.map(lambda job: job[0].search(job[1], **job[2]), jobs))
    wiki = wikipedia.context(variant.segment, variant.language, topic=verifier.topic_keywords(variant))

    hits, calls, by_call, seen = [], [], {}, set()
    for i, (call_hits, call) in enumerate(results):
        calls.append(call)
        by_call[i] = call_hits
        _log_source_call(run, call, call_hits)
        for hit in call_hits:
            if hit.url not in seen and hit.sentences:
                seen.add(hit.url)
                hits.append(hit)
    if not _searxng_deployed():
        log_action(
            run.id,
            "researcher",
            "searxng_not_deployed",
            model=None,
            cost=0,
            note="SEARXNG_URL not set: SearXNG is not deployed for this run and is not queried",
        )
    if wiki:
        log_action(run.id, "researcher", "wikipedia_context", sources=[wiki["url"]], model=None, cost=0)
    return Gathered(hits, calls, by_call, wiki)


def _log_source_call(run: Run, call: SourceCall, hits: list[Hit]) -> None:
    log_action(
        run.id,
        "researcher",
        f"search_{call.source}",
        sources=[h.url for h in hits][:10],
        model=None,
        cost=0,
        query=call.query,
        ok=call.ok,
        n_hits=call.n_hits,
        error=call.error,
        seconds=call.seconds,
    )


# ---- choosing the angle -------------------------------------------------------------


def excluded_variant(variant: Variant) -> str | None:
    """The Scout's angles get the same excluded-category check as the founder's brief. A word that only
    might mean an excluded category (the ask-the-founder tier) also rules an angle out: nobody confirmed it."""
    res = guard.classify_brief(
        f"{variant.title}. {variant.segment}: {variant.job_to_be_done}. "
        f"{'; '.join(variant.pain_queries)}; {variant.competitor_query}"
    )
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
    eligible = [v for v in variants if v.n not in excluded] or variants[:1]
    try:
        rows = scorer.rank(run.id, run.brief, eligible, max_age_months)
    except Exception as e:  # noqa: BLE001 - ranking is advisory; research still runs on the first angle
        log_action(run.id, "scorer", "score_alternatives_failed", error=str(e)[:160])
        rows = [{"n": v.n, "title": v.title, "chosen": v.n == eligible[0].n} for v in eligible]
    if rows and "errors" in rows[0] and all(r["errors"] for r in rows):
        for row in rows:
            row["chosen"] = row["n"] == eligible[0].n
    rows += [
        {"n": v.n, "title": v.title, "excluded": excluded[v.n], "chosen": False}
        for v in variants
        if v.n in excluded and all(r["n"] != v.n for r in rows)
    ]
    return rows


# ---- one variant's evidence ---------------------------------------------------------


def _hits_to_show(hits: list[Hit], topic: set[str], max_shown: int) -> list[Hit]:
    """People describing the problem first (a pain or payment cue in their own words), then other on-topic
    posts. GitHub repositories are competitor evidence only, so a few at most take a slot."""

    def priority(h: Hit) -> tuple:
        has_cue = bool(verifier.match_cue("pain", h.text) or verifier.match_cue("wtp", h.text))
        topic_overlap = len(verifier.overlap(h.title + " " + h.text, topic))
        return (-has_cue, h.source == "github", -topic_overlap, -(h.engagement or 0))

    on_topic = sorted((h for h in hits if verifier.is_on_topic(h.title + " " + h.text, topic, 1)), key=priority)
    shown, n_github = [], 0
    for hit in on_topic:
        if hit.source == "github":
            if n_github >= MAX_GITHUB_HITS_SHOWN:
                continue
            n_github += 1
        shown.append(hit)
        if len(shown) >= max_shown:
            break
    return shown


def _number_hits(run: Run, shown: list[Hit]) -> None:
    """Hit ids (H1, H2, ...) are unique across every research round of a run."""
    counter = run.state.setdefault("hit_counter", [])
    for i, hit in enumerate(shown, start=len(counter) + 1):
        hit.id = f"H{i}"
    counter.extend(h.id for h in shown)


def _code_qualified_claims(
    run: Run, variant: Variant, hits_by_id: dict[str, Hit], shown_ids: dict, claims: list[Claim], start: int
) -> list[Claim]:
    """Two readers: sentences that pass code's own published test (first person, on topic, a pain or payment
    cue, not a question, link or pitch) but that the model skipped are added by code, then verified like
    every other claim. A model that under-selects can no longer hide evidence."""
    added = []
    for ref in verifier.missed_qualified(hits_by_id, shown_ids, claims, variant):
        hit_id, sentence_n = ref.split(".S")
        sentence = hits_by_id[hit_id].sentences[int(sentence_n) - 1]
        kind = "pain" if verifier.match_cue("pain", sentence) else "wtp"
        added.append(
            {
                "hit_id": hit_id,
                "sentence_ids": [int(sentence_n)],
                "kind": kind,
                "claim_text": "Selected by code: the writer's own " + ("complaint" if kind == "pain" else "payment"),
            }
        )
    if not added:
        return []
    log_action(
        run.id,
        "verifier",
        "add_code_qualified_sentences",
        model=None,
        cost=0,
        n=len(added),
        refs=[f"{a['hit_id']}.S{a['sentence_ids'][0]}" for a in added],
    )
    return verifier.build_claims(run.id, hits_by_id, added, start=start)


def research_variant(run: Run, variant: Variant, broaden: bool = False) -> dict:
    """Search, select, verify and measure the evidence for one variant. Returns the research record
    stored under ``run.state["research"][n]`` (its ``claims`` are moved into the run's ledger)."""
    config = runtime()
    caps, limits = config[run.mode]["caps"], config["limits"]
    found = gather(run, variant, caps, limits, broaden)
    unavailable = sorted({c.source for c in found.calls if not c.ok})
    run.say("sources_done", hits=len(found.hits), calls=len(found.calls), unavailable=unavailable)
    topic = verifier.topic_keywords(variant)

    shown = _hits_to_show(found.hits, topic, limits["max_hits_shown"])
    _number_hits(run, shown)
    shown_ids = {h.id: verifier.select_sentences(h, topic, limits["max_sentences_per_hit"]) for h in shown}
    hits_by_id = {h.id: h for h in shown}

    model_failure = False
    items: list[dict] = []
    if shown:
        try:
            items = researcher.run(run.id, variant, shown, shown_ids)
        except llm.LLMError:
            model_failure = True
    start = len(run.state.get("claims", [])) + 1
    claims = verifier.build_claims(run.id, hits_by_id, items, start=start)
    if not model_failure:
        claims += _code_qualified_claims(run, variant, hits_by_id, shown_ids, claims, start + len(claims))

    verifier.mark_eligible(claims, variant)
    run.say("verifying")
    stats = verifier.verify_live(
        claims,
        cap=caps["verify"],
        timeout=limits["verify_timeout_s"],
        min_chars=limits["min_quote_chars_fuzzy"],
        threshold=limits["fuzzy_threshold"],
        hits_by_id=hits_by_id,
    )
    evidence_thresholds = run.thresholds["gate1_evidence"]
    verifier.apply_relevance(claims, variant, evidence_thresholds["max_age_months"])
    log_action(
        run.id,
        "verifier",
        "verify_quotes",
        sources=sorted({c.url for c in claims if c.url}),
        model=None,
        cost=0,
        **stats,
    )
    missed = [] if model_failure else verifier.missed_qualified(hits_by_id, shown_ids, claims, variant)
    coverage, coverage_rows = gates.coverage(
        found.calls, found.hits_by_call, variant, evidence_thresholds["min_on_topic_hits"]
    )
    metrics = gates.compute_metrics(claims, run.brief, coverage, run.thresholds)
    run.say(
        "verified",
        live=stats["verified_live"],
        archived=metrics["claims_archived"],
        counted=sum(1 for c in claims if c.weight > 0),
    )
    return {
        "variant_n": variant.n,
        "claims": [c.model_dump(mode="json") for c in claims],
        "hits": {
            h.id: {
                "url": h.url,
                "source": h.source,
                "title": h.title,
                "shown": shown_ids[h.id],
                "sentences": [h.sentences[i - 1] for i in shown_ids[h.id]],
            }
            for h in shown
        },
        "calls": [c.model_dump() for c in found.calls],
        "coverage_rows": coverage_rows,
        "metrics": metrics,
        "missed": missed,
        "model_failure": model_failure,
        "wiki": found.wiki,
        "verify_stats": stats,
        "unavailable": unavailable,
    }
