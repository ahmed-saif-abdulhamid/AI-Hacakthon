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

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import httpx
from rapidfuzz import fuzz

from sources.base import USER_AGENT, cues, keywords, normalize

from .models import Claim, Hit, Variant

ARCHIVE_WEIGHT = {"hn": 0.5, "stackexchange": 0.5, "github": 0.5, "web": 0.0}
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
    "freelance freelancer freelancers us uk usa world"
)


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
    return Topic(seg, job)


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
    claims, seen = [], set()
    for n, it in enumerate(items, start=start):
        hit = hits.get(it.get("hit_id", ""))
        kind = it.get("kind", "pain")
        claim_text = " ".join(str(it.get("claim_text", "")).split()[:15])
        if hit is None:
            claims.append(
                Claim(
                    id=f"C{n}",
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
            )
            continue
        quote, ids = build_quote(hit, list(it.get("sentence_ids", [])))
        key = (hit.id, tuple(ids))
        if key in seen:
            continue
        seen.add(key)
        claims.append(
            Claim(
                id=f"C{n}",
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
        )
    for i, c in enumerate(claims, start=start):
        c.id = f"C{i}"
    return claims


_SE_URL = re.compile(
    r"https?://(?:(?P<sub>[a-z0-9-]+)\.stackexchange\.com|(?P<so>stackoverflow|superuser|serverfault"
    r"|askubuntu)\.com)/questions/(?P<qid>\d+)"
)


def _fetch_stackexchange(m: re.Match, timeout: float) -> str | None:
    """Stack Exchange web pages sit behind a bot challenge, so re-read the same public post (question and
    answers, current version) through the official API instead of the HTML page."""
    import os

    site = m.group("sub") or m.group("so")
    params = {"site": site, "filter": "withbody"}
    if os.environ.get("SE_KEY"):
        params["key"] = os.environ["SE_KEY"]
    base = "https://api.stackexchange.com/2.3/questions/" + m.group("qid")
    try:
        q = httpx.get(base, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout).json()
        a = httpx.get(base + "/answers", params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout).json()
    except Exception:  # noqa: BLE001
        return None
    bodies = [i.get("title", "") + " " + i.get("body", "") for i in q.get("items", [])]
    bodies += [i.get("body", "") for i in a.get("items", [])]
    return normalize(" ".join(bodies)) if bodies else None


def _fetch(url: str, timeout: float) -> str | None:
    m = _SE_URL.match(url or "")
    if m:
        return _fetch_stackexchange(m, timeout)
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
        return normalize(r.text) if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def quote_on_page(quote: str, page: str, min_chars: int = 40, threshold: int = 95) -> bool:
    if len(quote) < min_chars:
        return quote in page
    return fuzz.partial_ratio(quote, page) >= threshold


def verify_live(
    claims: list[Claim], cap: int = 8, timeout: float = 5.0, min_chars: int = 40, threshold: int = 95, fetcher=None
) -> dict:
    """Re-fetch up to ``cap`` distinct public URLs in parallel and set each claim's status."""
    fetch = fetcher or (lambda u: _fetch(u, timeout))
    # Prioritise claims that could count (on-topic and cue-confirmed come first).
    candidates = [c for c in claims if c.quote and c.url]
    candidates.sort(key=lambda c: (-(c.weight_note == "eligible"), c.id))
    urls = []
    for c in candidates:
        if c.url not in urls:
            urls.append(c.url)
    urls = urls[:cap]
    with ThreadPoolExecutor(max_workers=8) as ex:
        pages = dict(zip(urls, ex.map(fetch, urls), strict=False))
    now = datetime.now(UTC)
    stats = {"checked_urls": len(urls), "reachable": sum(1 for p in pages.values() if p), "verified_live": 0}
    for c in candidates:
        c.fetched_at = now
        page = pages.get(c.url)
        if c.url not in pages:
            c.status = "archived_match"
            c.weight_note = (c.weight_note + "; " if c.weight_note else "") + "not live-checked (verify cap)"
        elif page and quote_on_page(c.quote, page, min_chars, threshold):
            c.status = "verified_live"
            stats["verified_live"] += 1
        else:
            c.status = "archived_match"
            note = "page unreachable" if page is None else "not found on live page"
            c.weight_note = (c.weight_note + "; " if c.weight_note else "") + note + "; archived match"
    return stats


def apply_relevance(claims: list[Claim], variant: Variant, max_age_months: int = 24) -> None:
    """Code relevance check: sets on_topic, cue_matched, weight and label. Pure."""
    topic = topic_keywords(variant)
    for c in claims:
        if not c.quote:
            c.weight, c.label = 0.0, "ASSUMPTION"
            continue
        # On topic: the quote read together with its thread title (a single sentence rarely repeats
        # the segment's words). The pain / payment cue must still be in the quote itself.
        c.keyword_overlap = overlap(c.quote + " " + c.hit_title, topic)
        c.on_topic = is_on_topic(c.quote + " " + c.hit_title, topic)
        base = (
            1.0
            if c.status == "verified_live"
            else ARCHIVE_WEIGHT.get(c.source, 0.0)
            if c.status == "archived_match"
            else 0.0
        )
        c.label = "SOURCED"
        notes = [n for n in c.weight_note.split("; ") if n and n not in ("eligible",)]
        if not c.on_topic:
            c.weight = 0.0
            notes.append("off topic for this variant (code keyword check)")
        elif c.kind in ("pain", "wtp") and (PITCH.search(c.quote) or c.quote.lstrip().startswith(("-", "*", "•"))):
            # Someone selling a tool describes "the problem" to pitch it; a feature bullet is not a person's
            # experience. Neither is a complaint from a would-be customer.
            c.weight = 0.0
            notes.append("product pitch or feature list, not a complaint")
        elif c.kind in ("pain", "wtp") and c.quote.rstrip().endswith("?"):
            c.weight = 0.0
            notes.append("a question, not someone's own experience")
        elif c.kind in CUE_KINDS:
            cue = match_cue(c.kind, c.quote)
            c.cue_matched = cue
            if not cue:
                c.weight = 0.0
                notes.append("label not confirmed by code")
            elif c.kind == "pain" and WEAK_PAIN.fullmatch(cue.strip().lower()) and not FIRST_PERSON.search(c.quote):
                # Words like "manual", "problem" or "overdue" describe a topic; they count as a complaint only
                # when the person is talking about their own experience.
                c.weight = 0.0
                notes.append("general wording, not someone's own complaint")
            else:
                c.weight = base
        elif c.kind == "competitor":
            c.weight = base
        else:
            c.weight = 0.0
            notes.append("context only; never counted by a gate")
        c.weight_note = "; ".join(notes)


def mark_eligible(claims: list[Claim], variant: Variant) -> None:
    """Pre-verification hint so the verify cap is spent on claims that could count."""
    topic = topic_keywords(variant)
    for c in claims:
        if (
            c.quote
            and is_on_topic(c.quote + " " + c.hit_title, topic)
            and (c.kind not in CUE_KINDS or match_cue(c.kind, c.quote))
        ):
            c.weight_note = "eligible"


def is_recent(c: Claim, max_age_months: int) -> bool:
    if c.published_at is None:
        return False
    pub = c.published_at if c.published_at.tzinfo else c.published_at.replace(tzinfo=UTC)
    return pub >= datetime.now(UTC) - timedelta(days=30.44 * max_age_months)


def missed_qualified(
    hits: dict[str, Hit], shown_ids: dict[str, list[int]], claims: list[Claim], variant: Variant
) -> list[str]:
    """Shown sentences that pass code's own on-topic + pain/wtp cue check but were not selected."""
    topic = topic_keywords(variant)
    selected = {(c.hit_id, i) for c in claims for i in c.sentence_ids}
    missed = []
    for hid, ids in shown_ids.items():
        h = hits[hid]
        for i in ids:
            if (hid, i) in selected:
                continue
            s = h.sentences[i - 1]
            # Proxy for "evidence the model should have picked": a person's own experience (first person,
            # declarative, no links or hashtags: product copy talks to "you"), on topic, with a pain cue
            # or a strong payment cue.
            if s.rstrip().endswith("?") or s.lstrip().startswith(("-", "*", "•")) or URLISH.search(s):
                continue
            if not FIRST_PERSON.search(s):
                continue
            if is_on_topic(s, topic) and (match_cue("pain", s) or STRONG_WTP.search(s)):
                missed.append(f"{hid}.S{i}")
    return missed


def _prose(s: str) -> bool:
    """Skip code, tables and ASCII diagrams: keep sentences that are mostly letters."""
    if not 15 <= len(s) <= 500:
        return False
    letters = sum(ch.isalpha() or ch.isspace() for ch in s)
    return letters / len(s) >= 0.8


def select_sentences(hit: Hit, topic: set[str], max_n: int = 6) -> list[int]:
    """Pick up to ``max_n`` sentence IDs to show the model: the most on-topic sentences,
    kept in document order, so long records are not cut off after sentence 6."""
    n = len(hit.sentences)
    usable = [i for i in range(1, n + 1) if _prose(hit.sentences[i - 1])]
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
