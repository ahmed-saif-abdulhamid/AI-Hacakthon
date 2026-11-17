"""Shared source plumbing: one normalize() for API records and pages, the pysbd
sentence splitter, stemmed keywords, a response cache, circuit-broken JSON fetching
and the Source interface.

Add a new source by subclassing ``Source`` and implementing ``search``.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import httpx
import pysbd
import snowballstemmer
import yaml
from bs4 import BeautifulSoup

from proveit import metrics
from proveit.models import Hit, SourceCall

from . import circuit
from .circuit import CircuitOpenError

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
CACHE_TTL_SECONDS = 6 * 3600
DEFAULT_TIMEOUT_SECONDS = 8.0
MAX_HIT_CHARS = 12000
MAX_ERROR_CHARS = 160
MIN_KEYWORD_LENGTH = 3
USER_AGENT = "ProveIt/0.1 (open-source founder research agent; https://github.com/)"
# A page or API that could not be read: transport failures, HTTP error statuses, malformed URLs.
NETWORK_ERRORS = (httpx.HTTPError, httpx.InvalidURL)
# Everything a source search can fail with: the above, a body that is not JSON, or an open breaker.
FETCH_ERRORS = (*NETWORK_ERRORS, ValueError, CircuitOpenError)

_QUOTES = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "′": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "″": '"',
    " ": " ",
    "–": "-",
    "—": "-",
    "…": "...",
}


def normalize(text: str | None) -> str:
    """BeautifulSoup get_text(" ") -> html.unescape -> straight quotes -> collapsed whitespace."""
    if not text:
        return ""
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        for t in soup(["script", "style", "noscript"]):
            t.decompose()
        text = soup.get_text(" ")
    text = html.unescape(text)
    for k, v in _QUOTES.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=4)
def _segmenter(lang: str) -> pysbd.Segmenter:
    try:
        return pysbd.Segmenter(language=lang, clean=False)
    except ValueError:  # unsupported language: fall back to English rules
        return pysbd.Segmenter(language="en", clean=False)


def split_sentences(text: str, lang: str = "en") -> list[str]:
    """Sentences of ``text`` (Arabic or English rules), stripped, without one-character fragments."""
    seg = _segmenter("ar" if lang == "ar" else "en")
    return [s.strip() for s in seg.segment(text) if s and len(s.strip()) > 1]


@lru_cache(maxsize=1)
def cues() -> dict:
    """Cue patterns and stopwords from ``config/cues.yaml``."""
    return yaml.safe_load((ROOT / "config" / "cues.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def stopwords() -> frozenset[str]:
    """Words ignored when building short queries and keywords."""
    return frozenset(cues()["stopwords"].split())


_stemmer = snowballstemmer.stemmer("english")
_WORD = re.compile(r"[a-z؀-ۿ][a-z0-9؀-ۿ'-]+")


def keywords(text: str) -> set[str]:
    """Lower-cased, stemmed, stop-word-free content keywords."""
    words = [w.strip("'-") for w in _WORD.findall((text or "").lower())]
    words = [w for w in words if len(w) >= MIN_KEYWORD_LENGTH and w not in stopwords()]
    return {_stemmer.stemWord(w) for w in words}


def _cache_path(key: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(key.encode()).hexdigest() + ".json")


def cache_get(key: str) -> object | None:
    """A cached source response younger than the cache lifetime, or None."""
    p = _cache_path(key)
    if not p.exists() or time.time() - p.stat().st_mtime >= CACHE_TTL_SECONDS:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def cache_put(key: str, value: object) -> None:
    """Cache a source response (skipped in tests)."""
    if os.environ.get("PROVEIT_ENV") == "test":
        return
    p = _cache_path(key)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value), encoding="utf-8")
    except OSError as e:  # the cache is an optimisation; a read-only disk only makes runs slower
        logger.warning("could not write the source cache %s: %s", p, e)


def get_json(
    url: str,
    source: str,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> object:
    """GET a JSON API through ``source``'s circuit breaker, with a 6-hour response cache.

    Raises one of ``FETCH_ERRORS``; ``CircuitOpenError`` means no request was made.
    """
    key = url + json.dumps(params or {}, sort_keys=True)
    cached = cache_get(key)
    if cached is not None:
        return cached
    data = _fetch_json(
        url, source, params, {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}, timeout
    )
    cache_put(key, data)
    return data


def _fetch_json(url: str, source: str, params: dict | None, headers: dict, timeout: float) -> object:
    breaker = circuit.breaker(source)
    if not breaker.allow():
        metrics.increment("source_circuit_open", source=source)
        raise CircuitOpenError()
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        data = r.json()
    except (*NETWORK_ERRORS, ValueError) as e:
        breaker.record_failure()
        metrics.increment("source_call_failed", source=source)
        logger.warning("%s call failed: %s", source, e)
        raise
    breaker.record_success()
    return data


def ts_to_dt(ts: float | int | None) -> datetime | None:
    """A UTC datetime from a Unix timestamp, or None."""
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=UTC)


class Source:
    """Interface for an evidence source. ``pain_capable`` sources count toward coverage."""

    name = "base"
    pain_capable = False

    def search(self, query: str, **kw) -> tuple[list[Hit], SourceCall]:
        """Search this source for a query; every adapter implements it."""
        raise NotImplementedError

    def _get_json(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> object:
        return get_json(url, self.name, params=params, headers=headers, timeout=timeout)

    def _call(
        self, query: str, url: str, t0: float, hits: list[Hit] | None = None, error: str | None = None
    ) -> SourceCall:
        return SourceCall(
            source=self.name,
            query=query,
            url=url,
            ok=error is None,
            n_hits=len(hits or []),
            seconds=round(time.time() - t0, 2),
            error=error,
            pain_capable=self.pain_capable,
        )

    def _failed(self, query: str, url: str, t0: float, error: Exception, prefix: str = "") -> SourceCall:
        """The record of a search that returned nothing because the source could not be read."""
        return self._call(query, url, t0, error=(prefix + str(error))[:MAX_ERROR_CHARS])


def make_hit(
    source: str,
    url: str,
    raw_text: str,
    title: str = "",
    published_at: datetime | None = None,
    engagement: int | None = None,
    query: str = "",
    lang: str = "en",
) -> Hit:
    """A Hit with normalised text, split into sentences."""
    text = normalize(raw_text)[:MAX_HIT_CHARS]
    return Hit(
        id="",
        source=source,
        url=url,
        title=normalize(title),
        text=text,
        sentences=split_sentences(text, lang),
        published_at=published_at,
        engagement=engagement,
        query=query,
    )
