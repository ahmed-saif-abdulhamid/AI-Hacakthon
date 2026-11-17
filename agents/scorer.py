"""Scorer: compares the Scout's angles before any deep research. Code only, no model.

For each variant it runs its pain queries against Hacker News comments from the evidence
window, and counts the comments that code reads as on-topic, first-person complaints (the
same relevance and cue checks the verifier uses). The founder-fit share comes from the
brief. The highest signal is researched first; the rest stay as pivot targets. These counts
rank angles against each other; they are never counted as evidence at a gate.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from proveit.log import log_action
from proveit.models import FounderBrief, Hit, Variant
from proveit.verifier import FIRST_PERSON, PITCH, is_on_topic, match_cue, topic_keywords
from sources.base import keywords
from sources.hn import API, HackerNews

PER_QUERY = 20
QUERIES_PER_VARIANT = 3
PAUSE_BETWEEN_QUERIES_SECONDS = 0.2  # stay polite to the free Algolia API
DAYS_PER_MONTH = 30
# signal = complaints + weights x (on-topic comments, founder fit): complaints count most.
ON_TOPIC_WEIGHT = 0.25
FIT_WEIGHT = 2


def _fit(brief: FounderBrief, v: Variant) -> float:
    """Share of the variant's segment and job words that also appear in the founder's skills and market."""
    want = keywords(f"{v.segment} {v.job_to_be_done}")
    have = keywords(f"{brief.skills} {brief.target_market} {brief.idea}")
    return round(len(want & have) / len(want), 2) if want else 0.0


def _is_complaint(h: Hit) -> bool:
    """A first-person comment with a pain cue that is not someone pitching their own product."""
    return bool(match_cue("pain", h.text) and FIRST_PERSON.search(h.text) and not PITCH.search(h.text))


def _score_variant(hn: HackerNews, brief: FounderBrief, v: Variant, since: int) -> dict:
    topic, seen, on_topic, complaints, errors = topic_keywords(v), set(), 0, 0, 0
    for q in v.pain_queries[:QUERIES_PER_VARIANT]:
        hits, call = hn.search(q, since_ts=since, per_page=PER_QUERY, tags="comment")
        errors += 0 if call.ok else 1
        for h in hits:
            if h.url in seen:
                continue
            seen.add(h.url)
            if is_on_topic(f"{h.title} {h.text}", topic):
                on_topic += 1
                complaints += _is_complaint(h)
        time.sleep(PAUSE_BETWEEN_QUERIES_SECONDS)
    fit = _fit(brief, v)
    return {
        "n": v.n,
        "title": v.title,
        "comments_checked": len(seen),
        "on_topic": on_topic,
        "complaints": complaints,
        "fit": fit,
        "errors": errors,
        "signal": round(complaints + ON_TOPIC_WEIGHT * on_topic + FIT_WEIGHT * fit, 2),
    }


def rank(run_id: str, brief: FounderBrief, variants: list[Variant], max_age_months: int = 24) -> list[dict]:
    """One row per variant with its signal; the strongest is marked ``chosen`` and logged."""
    since = int((datetime.now(UTC) - timedelta(days=DAYS_PER_MONTH * max_age_months)).timestamp())
    hn = HackerNews()
    rows = [_score_variant(hn, brief, v, since) for v in variants]
    best = max(rows, key=lambda r: (r["signal"], -r["n"]))
    for r in rows:
        r["chosen"] = r is best
    log_action(
        run_id,
        "scorer",
        "score_alternatives",
        sources=[API],
        model=None,
        cost=0,
        ranking=[{k: r[k] for k in ("n", "signal", "complaints", "on_topic", "fit")} for r in rows],
        chosen=best["n"],
    )
    return rows
