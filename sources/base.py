"""Shared source plumbing: one normalize() for API records and pages, the pysbd
sentence splitter, stemmed keywords, a response cache and the Source interface.

Add a new source by subclassing ``Source`` and implementing ``search``.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import httpx
import pysbd
import snowballstemmer
import yaml
from bs4 import BeautifulSoup

from proveit.models import Hit, SourceCall

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "ProveIt/0.1 (open-source founder research agent; https://github.com/)"
_QUOTES = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
           "“": '"', "”": '"', "„": '"', "″": '"', " ": " ",
           "–": "-", "—": "-", "…": "..."}


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
    except Exception:  # noqa: BLE001 - unsupported language falls back to English rules
        return pysbd.Segmenter(language="en", clean=False)


def split_sentences(text: str, lang: str = "en") -> list[str]:
    seg = _segmenter("ar" if lang == "ar" else "en")
    return [s.strip() for s in seg.segment(text) if s and len(s.strip()) > 1]


@lru_cache(maxsize=1)
def cues() -> dict:
    return yaml.safe_load((ROOT / "config" / "cues.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def stopwords() -> frozenset[str]:
    return frozenset(cues()["stopwords"].split())


_stemmer = snowballstemmer.stemmer("english")
_WORD = re.compile(r"[a-z؀-ۿ][a-z0-9؀-ۿ'-]+")


def keywords(text: str) -> set[str]:
    """Lower-cased, stemmed, stop-word-free content keywords."""
    words = [w.strip("'-") for w in _WORD.findall((text or "").lower())]
    words = [w for w in words if len(w) > 2 and w not in stopwords()]
    return {_stemmer.stemWord(w) for w in words}


def cache_get(key: str) -> object | None:
    p = ROOT / "data" / "cache" / (hashlib.sha256(key.encode()).hexdigest() + ".json")
    if p.exists() and time.time() - p.stat().st_mtime < 6 * 3600:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def cache_put(key: str, value: object) -> None:
    if os.environ.get("PROVEIT_ENV") == "test":
        return
    p = ROOT / "data" / "cache" / (hashlib.sha256(key.encode()).hexdigest() + ".json")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value), encoding="utf-8")
    except OSError:
        pass


def get_json(url: str, params: dict | None = None, headers: dict | None = None,
             timeout: float = 8.0) -> object:
    key = url + json.dumps(params or {}, sort_keys=True)
    cached = cache_get(key)
    if cached is not None:
        return cached
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    h.update(headers or {})
    r = httpx.get(url, params=params, headers=h, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    data = r.json()
    cache_put(key, data)
    return data


def ts_to_dt(ts: float | int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


class Source:
    """Interface for an evidence source. ``pain_capable`` sources count toward coverage."""
    name = "base"
    pain_capable = False

    def search(self, query: str, **kw) -> tuple[list[Hit], SourceCall]:
        raise NotImplementedError

    def _call(self, query: str, url: str, t0: float, hits: list[Hit] | None = None,
              error: str | None = None) -> SourceCall:
        return SourceCall(source=self.name, query=query, url=url, ok=error is None,
                          n_hits=len(hits or []), seconds=round(time.time() - t0, 2), error=error,
                          pain_capable=self.pain_capable)


def make_hit(source: str, url: str, raw_text: str, title: str = "", published_at=None,
             engagement=None, query: str = "", lang: str = "en") -> Hit:
    text = normalize(raw_text)[:12000]
    return Hit(id="", source=source, url=url, title=normalize(title), text=text,
               sentences=split_sentences(text, lang), published_at=published_at,
               engagement=engagement, query=query)
