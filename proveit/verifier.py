"""Verifier: builds quotes from sentence IDs (code only), re-checks them against the live
public page, and runs the deterministic relevance + cue check.

Statuses and weights:
  verified_live   quote found on the live public page               1.0
  archived_match  verbatim from the API record, not confirmed live  0.5 (HN / SE / GitHub), 0 (web)
  unverified      quote could not be built                          0   (label ASSUMPTION)
A claim keeps its weight only if code confirms it is on topic (at least two specific stemmed
keywords shared with the variant's segment + job, at least one about the job, generic business
words excluded) and, for pain / wtp / price claims, contains a matching cue.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import httpx
from rapidfuzz import fuzz

from sources.base import NETWORK_ERRORS, USER_AGENT, cues, keywords, normalize

from .models import Claim, Hit, Variant

ARCHIVE_WEIGHT = {"hn": 0.5, "stackexchange": 0.5, "github": 0.5, "web": 0.0}
LIVE_WEIGHT = 1.0
MAX_CLAIM_WORDS = 15
# Live check: how many pages at once, and how closely a quote must match the page text.
FETCH_WORKERS = 8
DEFAULT_VERIFY_CAP = 8
DEFAULT_FETCH_TIMEOUT_SECONDS = 5.0
FUZZY_MIN_CHARS = 40  # shorter quotes must appear verbatim
FUZZY_THRESHOLD = 95
DAYS_PER_MONTH = 30.44
# A shown sentence must be prose: this many characters, and mostly letters (not code, tables or diagrams).
PROSE_MIN_CHARS, PROSE_MAX_CHARS = 15, 500
PROSE_MIN_LETTER_SHARE = 0.8
LIST_BULLETS = ("-", "*", "•")
SE_API = "https://api.stackexchange.com/2.3/questions/"
# Unauthenticated Stack Exchange API calls are throttled (HTTP 429): space them out across threads.
SE_MIN_INTERVAL_SECONDS = 0.35
# When a live page cannot be read, these sources' API text (fetched earlier in the same run) is used.
API_TEXT_SOURCES = ("stackexchange", "hn")

CUE_KINDS = {"pain": "pain", "wtp": "wtp", "price_point": "price_point"}
FIRST_PERSON = re.compile(r"\b(i|i'm|i've|i'd|me|my|we|we're|we've|our|us)\b", re.I)
PITCH = re.compile(
    r"\b(i|we)('ve| have)? (built|made|created|launched|am building|'m building|are building|'re building)\b"
    r"|\bthe idea came from\b|\bi hear from\b|\b(my|our) (app|tool|product|startup|saas)\b"
    r"|\b(sign up|try it|check it out|join (the|our) waitlist|show hn|launch hn)\b",
    re.I,
)
WEAK_PAIN = re.compile(r"manual(ly)?|problems?|overdue|unpaid|wish|pain|expensive|costly|difficult")
URLISH = re.compile(r"https?://|www\.|#\w")
STRONG_WTP = re.compile(r"\b(paid|would pay|pay for|paying for|bought)\b|[$€£]\s?\d", re.I)


@lru_cache(maxsize=8)
def cue_regex(kind: str) -> re.Pattern:
    c = cues()[kind]
    return re.compile(f"(?:{c['en']})|(?:{c['ar']})", re.I)


def match_cue(kind: str, text: str) -> str | None:
    if kind not in CUE_KINDS:
        return None
    m = cue_regex(CUE_KINDS[kind]).search(text or "")
    return m.group(0) if m else None


# Words that appear in almost any business text: they must not make a comment "on topic" by themselves.
GENERIC = keywords(
    "small new client clients customer customers business businesses people person user users team teams "
    "company companies owner owners form forms track tracking record records online simple easy tool tools "
    "app apps software digital template templates kit pack guide guides checklist checklists work working "
    "time day week month year help manage management process system service services product products "
    "free first need needs want get make use using local independent professional professionals "
    "us uk usa world"
)

# Domain expansion: when the job or segment is about getting paid, people describe it with sibling
# words ("paid", "owes me", "late") that do not share a stem with "payments" or "invoice".
# Each entry: trigger stems -> sibling stems added to the job keywords.
TOPIC_EXPANSIONS: list[tuple[frozenset[str], set[str]]] = [
    (
        frozenset({"payment", "invoic", "deposit", "mileston", "overdu", "overdue"}),
        keywords(
            "pay paid unpaid paying owe owes owed bill billing late delay delayed deposit deposits "
            "milestone milestones invoice invoices"
        ),
    ),
]


class Topic(set):
    """The variant's keywords, split into who (segment) and what (job to be done)."""

    def __init__(self, segment: set[str], job: set[str]):
        super().__init__(segment | job)
        self.segment, self.job = segment, job


def topic_keywords(variant: Variant) -> Topic:
    seg = keywords(variant.segment) - GENERIC
    job = keywords(variant.job_to_be_done) - GENERIC
    if not seg:  # a segment made only of generic words: fall back to its words
        seg = keywords(variant.segment)
    if not job:
        job = keywords(variant.job_to_be_done)
    for triggers, siblings in TOPIC_EXPANSIONS:
        if (seg | job) & triggers:
            job = job | (siblings - GENERIC)
    return Topic(seg, job)


def topic_context(c: Claim, variant: Variant) -> str:
    """Text read for the on-topic check: the quote, its thread title and, for a Stack Exchange post on
    the variant's own community, that community's name (e.g. "freelancing")."""
    context = (c.quote or "") + " " + c.hit_title
    if c.source == "stackexchange" and variant.se_site and f"//{variant.se_site}." in (c.url or ""):
        context += " " + variant.se_site
    return context


def overlap(text: str, topic: set[str]) -> list[str]:
    return sorted(keywords(text) & topic)


def is_on_topic(text: str, topic: set[str], need: int = 2) -> bool:
    """On topic = at least ``need`` specific (non-generic) topic words, at least one of them about the
    job to be done, so a comment that only shares words like "small", "clients" or "forms" never counts."""
    words = keywords(text)
    if isinstance(topic, Topic):
        shared = words & topic
        return len(shared) >= need and bool(shared & topic.job)
    return len(words & topic) >= need


# ---- building claims from sentence IDs ----------------------------------------------


def contiguous_run(ids: list[int]) -> list[int]:
    """Longest run of consecutive IDs (a non-contiguous join would not be verbatim)."""
    ids = sorted(set(ids))
    best, cur = [], []
    for i in ids:
        cur = cur + [i] if cur and i == cur[-1] + 1 else [i]
        if len(cur) > len(best):
            best = cur
    return best


def build_quote(hit: Hit, sentence_ids: list[int]) -> tuple[str | None, list[int]]:
    run = [i for i in contiguous_run(sentence_ids) if 1 <= i <= len(hit.sentences)]
    if not run:
        return None, []
    return " ".join(hit.sentences[i - 1] for i in run), run


def build_claims(run_id: str, hits: dict[str, Hit], items: list[dict], start: int = 1) -> list[Claim]:
    """Claims from the researcher's (hit ID, sentence IDs) items. Code builds every quote; duplicates
    (same hit and sentences) are dropped and the rest are numbered C<start>, C<start+1>, ..."""
    claims, seen = [], set()
    for it in items:
        hit = hits.get(it.get("hit_id", ""))
        kind = it.get("kind", "pain")
        claim_text = " ".join(str(it.get("claim_text", "")).split()[:MAX_CLAIM_WORDS])
        if hit is None:
            claims.append(_unbuilt_claim(run_id, kind, claim_text))
            continue
        quote, ids = build_quote(hit, list(it.get("sentence_ids", [])))
        if (hit.id, tuple(ids)) in seen:
            continue
        seen.add((hit.id, tuple(ids)))
        claims.append(_hit_claim(run_id, kind, claim_text, hit, quote, ids))
    for i, c in enumerate(claims, start=start):
        c.id = f"C{i}"
    return claims


def _unbuilt_claim(run_id: str, kind: str, claim_text: str) -> Claim:
    """A claim whose hit ID does not exist: kept visible as an ASSUMPTION with no weight."""
    return Claim(
        id="",
        run_id=run_id,
        kind=kind,
        claim_text=claim_text,
        quote=None,
        url=None,
        source="assumption",
        status="unverified",
        weight=0.0,
        weight_note="hit id not found; quote could not be built",
    )


def _hit_claim(run_id: str, kind: str, claim_text: str, hit: Hit, quote: str | None, ids: list[int]) -> Claim:
    return Claim(
        id="",
        run_id=run_id,
        kind=kind,
        claim_text=claim_text,
        quote=quote,
        url=hit.url,
        source=hit.source,
        hit_id=hit.id,
        hit_title=hit.title,
        sentence_ids=ids,
        published_at=hit.published_at,
        engagement=hit.engagement,
        status="archived_match" if quote else "unverified",
        label="SOURCED" if quote else "ASSUMPTION",
        weight_note="" if quote else "sentence ids invalid; quote could not be built",
    )


# ---- live re-check -------------------------------------------------------------------

_SE_URL = re.compile(
    r"https?://(?:(?P<sub>[a-z0-9-]+)\.stackexchange\.com|(?P<so>stackoverflow|superuser|serverfault"
    r"|askubuntu)\.com)/questions/(?P<qid>\d+)"
)


_se_lock = threading.Lock()
_se_last_call = [0.0]


def _se_get(url: str, params: dict, headers: dict, timeout: float) -> dict | None:
    """One paced Stack Exchange API GET; None unless the API answered 200 with JSON."""
    with _se_lock:
        wait = _se_last_call[0] + SE_MIN_INTERVAL_SECONDS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _se_last_call[0] = time.monotonic()
    r = httpx.get(url, params=params, headers=headers, timeout=timeout)
    return r.json() if r.status_code == httpx.codes.OK else None


def _fetch_stackexchange(m: re.Match, timeout: float) -> str | None:
    """Stack Exchange web pages sit behind a bot challenge, so re-read the same public post (question and
    answers, current version) through the official API instead of the HTML page."""
    params = {"site": m.group("sub") or m.group("so"), "filter": "withbody"}
    if os.environ.get("SE_KEY"):
        params["key"] = os.environ["SE_KEY"]
    base = SE_API + m.group("qid")
    headers = {"User-Agent": USER_AGENT}
    try:
        q = _se_get(base, params, headers, timeout)
        a = _se_get(base + "/answers", params, headers, timeout) if q is not None else None
    except (*NETWORK_ERRORS, ValueError):
        return None
    if q is None or a is None:  # throttled (429) or any other error: the page could not be read
        return None
    bodies = [i.get("title", "") + " " + i.get("body", "") for i in q.get("items", [])]
    bodies += [i.get("body", "") for i in a.get("items", [])]
    return normalize(" ".join(bodies)) if bodies else None


def _fetch(url: str, timeout: float) -> str | None:
    """The normalised text of a public page, or None when it cannot be read."""
    m = _SE_URL.match(url or "")
    if m:
        return _fetch_stackexchange(m, timeout)
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
    except NETWORK_ERRORS:
        return None
    return normalize(r.text) if r.status_code == httpx.codes.OK else None


def quote_on_page(quote: str, page: str, min_chars: int = FUZZY_MIN_CHARS, threshold: int = FUZZY_THRESHOLD) -> bool:
    if len(quote) < min_chars:
        return quote in page
    return fuzz.partial_ratio(quote, page) >= threshold


def _add_note(c: Claim, note: str) -> None:
    c.weight_note = (c.weight_note + "; " if c.weight_note else "") + note


def verify_live(
    claims: list[Claim],
    cap: int = DEFAULT_VERIFY_CAP,
    timeout: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    min_chars: int = FUZZY_MIN_CHARS,
    threshold: int = FUZZY_THRESHOLD,
    fetcher: Callable[[str], str | None] | None = None,
    hits_by_id: dict[str, Hit] | None = None,
) -> dict:
    """Re-fetch up to ``cap`` distinct public URLs in parallel and set each claim's status.

    When a Stack Exchange or HN page cannot be read (throttled or down), the quote is checked against
    that hit's API text from ``hits_by_id``, fetched earlier in the same run; such claims are counted
    under ``verified_from_api_text`` and noted on the claim."""
    fetch = fetcher or (lambda u: _fetch(u, timeout))
    # Prioritise claims that could count (on-topic and cue-confirmed come first).
    candidates = [c for c in claims if c.quote and c.url]
    candidates.sort(key=lambda c: (-(c.weight_note == "eligible"), c.id))
    urls = list(dict.fromkeys(c.url for c in candidates))[:cap]
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as ex:
        pages = dict(zip(urls, ex.map(fetch, urls), strict=False))
    now = datetime.now(UTC)
    stats = {
        "checked_urls": len(urls),
        "reachable": sum(1 for p in pages.values() if p),
        "verified_live": 0,
        "verified_from_api_text": 0,
    }
    for c in candidates:
        c.fetched_at = now
        page = pages.get(c.url)
        if c.url not in pages:
            c.status = "archived_match"
            _add_note(c, "not live-checked (verify cap)")
        elif page and quote_on_page(c.quote, page, min_chars, threshold):
            c.status = "verified_live"
            stats["verified_live"] += 1
        elif page is None and _api_text_match(c, hits_by_id, min_chars, threshold):
            c.status = "verified_live"
            stats["verified_from_api_text"] += 1
            _add_note(c, "live page unreachable; verified against API text fetched this run")
        else:
            c.status = "archived_match"
            _add_note(c, ("page unreachable" if page is None else "not found on live page") + "; archived match")
    return stats


def _api_text_match(c: Claim, hits_by_id: dict[str, Hit] | None, min_chars: int, threshold: int) -> bool:
    hit = (hits_by_id or {}).get(c.hit_id or "")
    if hit is None or hit.source not in API_TEXT_SOURCES or hit.url != c.url or not hit.text:
        return False
    return quote_on_page(c.quote, normalize(hit.text), min_chars, threshold)


# ---- relevance and weight --------------------------------------------------------------


def _base_weight(c: Claim) -> float:
    if c.status == "verified_live":
        return LIVE_WEIGHT
    if c.status == "archived_match":
        return ARCHIVE_WEIGHT.get(c.source, 0.0)
    return 0.0


def _weigh(c: Claim) -> tuple[float, str | None]:
    """(weight, reason it is zero) for a claim with a quote whose ``on_topic`` is already set."""
    if not c.on_topic:
        return 0.0, "off topic for this variant (code keyword check)"
    if c.kind in ("pain", "wtp"):
        # Someone selling a tool describes "the problem" to pitch it; a feature bullet is not a person's
        # experience, and a question is not someone's own complaint.
        if PITCH.search(c.quote) or c.quote.lstrip().startswith(LIST_BULLETS):
            return 0.0, "product pitch or feature list, not a complaint"
        if c.quote.rstrip().endswith("?"):
            return 0.0, "a question, not someone's own experience"
    if c.kind in CUE_KINDS:
        c.cue_matched = match_cue(c.kind, c.quote)
        if not c.cue_matched:
            return 0.0, "label not confirmed by code"
        if c.kind == "pain" and WEAK_PAIN.fullmatch(c.cue_matched.strip().lower()) and not FIRST_PERSON.search(c.quote):
            # Words like "manual", "problem" or "overdue" describe a topic; they count as a complaint only
            # when the person is talking about their own experience.
            return 0.0, "general wording, not someone's own complaint"
        return _base_weight(c), None
    if c.kind == "competitor":
        return _base_weight(c), None
    return 0.0, "context only; never counted by a gate"


def apply_relevance(claims: list[Claim], variant: Variant, max_age_months: int = 24) -> None:
    """Code relevance check: sets on_topic, cue_matched, weight and label. Pure.

    ``max_age_months`` is not used here: recency is counted by the gate (``gates.compute_metrics``).
    """
    topic = topic_keywords(variant)
    for c in claims:
        if not c.quote:
            c.weight, c.label = 0.0, "ASSUMPTION"
            continue
        # On topic: the quote read together with its thread title (a single sentence rarely repeats
        # the segment's words). The pain / payment cue must still be in the quote itself.
        context = topic_context(c, variant)
        c.keyword_overlap = overlap(context, topic)
        c.on_topic = is_on_topic(context, topic)
        c.label = "SOURCED"
        c.weight, reason = _weigh(c)
        notes = [n for n in c.weight_note.split("; ") if n and n != "eligible"]
        c.weight_note = "; ".join(notes + ([reason] if reason else []))


def mark_eligible(claims: list[Claim], variant: Variant) -> None:
    """Pre-verification hint so the verify cap is spent on claims that could count."""
    topic = topic_keywords(variant)
    for c in claims:
        if (
            c.quote
            and is_on_topic(topic_context(c, variant), topic)
            and (c.kind not in CUE_KINDS or match_cue(c.kind, c.quote))
        ):
            c.weight_note = "eligible"


def is_recent(c: Claim, max_age_months: int) -> bool:
    if c.published_at is None:
        return False
    pub = c.published_at if c.published_at.tzinfo else c.published_at.replace(tzinfo=UTC)
    return pub >= datetime.now(UTC) - timedelta(days=DAYS_PER_MONTH * max_age_months)


def missed_qualified(
    hits: dict[str, Hit], shown_ids: dict[str, list[int]], claims: list[Claim], variant: Variant
) -> list[str]:
    """Shown sentences that pass code's own on-topic + pain/wtp cue check but were not selected."""
    topic = topic_keywords(variant)
    selected = {(c.hit_id, i) for c in claims for i in c.sentence_ids}
    return [
        f"{hid}.S{i}"
        for hid, ids in shown_ids.items()
        for i in ids
        if (hid, i) not in selected and _qualifies(hits[hid].sentences[i - 1], topic)
    ]


def _qualifies(s: str, topic: set[str]) -> bool:
    """Proxy for "evidence the model should have picked": a person's own experience (first person,
    declarative, no links or hashtags: product copy talks to "you"), on topic, with a pain cue or a
    strong payment cue."""
    if s.rstrip().endswith("?") or s.lstrip().startswith(LIST_BULLETS) or URLISH.search(s):
        return False
    if not FIRST_PERSON.search(s):
        return False
    return is_on_topic(s, topic) and bool(match_cue("pain", s) or STRONG_WTP.search(s))


def _prose(s: str) -> bool:
    """Skip code, tables and ASCII diagrams: keep sentences that are mostly letters."""
    if not PROSE_MIN_CHARS <= len(s) <= PROSE_MAX_CHARS:
        return False
    letters = sum(ch.isalpha() or ch.isspace() for ch in s)
    return letters / len(s) >= PROSE_MIN_LETTER_SHARE


def select_sentences(hit: Hit, topic: set[str], max_n: int = 6) -> list[int]:
    """Pick up to ``max_n`` sentence IDs to show the model: the most on-topic sentences,
    kept in document order, so long records are not cut off after sentence 6."""
    usable = [i for i in range(1, len(hit.sentences) + 1) if _prose(hit.sentences[i - 1])]
    if len(usable) <= max_n:
        return usable
    ranked = sorted(
        usable,
        key=lambda i: (
            -len(keywords(hit.sentences[i - 1]) & topic),
            -(1 if match_cue("pain", hit.sentences[i - 1]) else 0),
            i,
        ),
    )
    return sorted(ranked[:max_n])
