"""Every generated sentence is sourced or labelled, enforced in code.

Agents return ``list[Statement]``. This module:
* drops claim IDs that are unknown or have weight 0;
* keeps a citation only if the statement shares >= 2 content keywords with the cited quote
  and every number in the statement appears in at least one cited quote;
* renders cited statements with [C1][C3] footnotes and a Sources list, and everything
  else as ``ASSUMPTION: <text>``;
* records the spans the model wrote in runs/<id>/provenance.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sources.base import keywords

from .models import Claim, Statement

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
SCALE = {"k": "000", "thousand": "000", "m": "000000", "million": "000000", "b": "000000000", "billion": "000000000"}
MARKET_STATEMENT = re.compile(r"\d|%|\b(most|many|every|hours|per week|struggl\w*|lose|losing)\b", re.I)
FACTUAL = re.compile(
    r"(\d[\d,.]*\s*%?|\b(most|majority|many|millions|thousands|every)\b)(\W+\w+){0,6}?\W+"
    r"(market|industry|users|people|customers|founders|businesses|freelancers|designers|% of)\b"
    r"|\b(market|industry|users|people|customers|founders|businesses)\b(\W+\w+){0,4}?\W+(\d[\d,.]*\s*%)"
    r"|\b(save|saves|saving|lose|loses|losing|waste|wastes|wasting|cut|cuts)\b(\W+\w+){0,3}?\W+\d[\d,.]*\s*(hours?|days?|%|percent)",
    re.I,
)


def _numbers(text: str) -> set[str]:
    out = set()
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(k|m|b|thousand|million|billion)?\b", text or "", re.I):
        n = m.group(1).replace(",", "")
        out.add(n)
        if m.group(2):
            whole = n.split(".")[0]
            out.add(whole + SCALE[m.group(2).lower()])
    return out


def citation_supports(statement: str, quote: str) -> bool:
    """The quote must share at least 2 content words, and at least 30% of the statement's, with it.
    Two shared topic words ("invoice", "overdue") are not enough to back a longer claim."""
    words = keywords(statement)
    shared = words & keywords(quote)
    return len(shared) >= max(2, -(-3 * len(words) // 10))


def validate(st: Statement, ledger: dict[str, Claim]) -> tuple[list[str], list[str]]:
    """Return (valid claim ids, notes)."""
    notes, valid = [], []
    for cid in st.claim_ids:
        c = ledger.get(cid)
        if c is None:
            notes.append(f"{cid}: unknown id dropped")
        elif c.weight <= 0 or not c.quote:
            notes.append(f"{cid}: zero-weight claim dropped")
        elif not citation_supports(st.text, c.quote):
            notes.append(f"{cid}: quote does not support this statement")
        else:
            valid.append(cid)
    nums = _numbers(st.text)
    if valid and nums:
        quote_nums = set().union(*(_numbers(ledger[c].quote) for c in valid))
        if not nums <= quote_nums:
            notes.append("number not found in any cited quote; citations dropped")
            valid = []
    return valid, notes


class Provenance:
    """Collects the spans the model wrote, per output file."""

    def __init__(self):
        self.spans: dict[str, list[str]] = {}

    def add(self, file: str, text: str) -> None:
        """Record a statement written into an output file."""
        self.spans.setdefault(file, []).append(text)

    def write(self, run_dir: Path) -> None:
        """Merge the recorded statements into the run's ``provenance.json``."""
        p = run_dir / "provenance.json"
        old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        for k, v in self.spans.items():
            old[k] = v
        p.write_text(json.dumps(old, indent=2, ensure_ascii=False), encoding="utf-8")


def render_statement(st: Statement, ledger: dict[str, Claim], used: list[str]) -> str:
    """One statement with its supporting citations, or labelled ASSUMPTION when none supports it."""
    valid, _ = validate(st, ledger)
    text = st.text.strip()
    if text.upper().startswith("ASSUMPTION:"):
        text = text.split(":", 1)[1].strip()
    if not valid:
        return f"ASSUMPTION: {text}"
    for c in valid:
        if c not in used:
            used.append(c)
    return text + "".join(f"[{c}]" for c in valid)


def render_list(
    statements: list[Statement],
    ledger: dict[str, Claim],
    used: list[str],
    prov: Provenance | None = None,
    file: str = "",
    bullet: str = "- ",
) -> str:
    """Statements as a Markdown list, each recorded in the provenance file."""
    lines = []
    for st in statements:
        if prov is not None:
            prov.add(file, st.text)
        lines.append(bullet + render_statement(st, ledger, used))
    return "\n".join(lines)


def sources_section(used: list[str], ledger: dict[str, Claim]) -> str:
    """The Sources section for the claims cited in one output file."""
    if not used:
        return "### Sources\n\nNo statement in this file carries a verified citation; every claim above is labelled ASSUMPTION.\n"
    rows = ["### Sources", ""]
    for cid in used:
        c = ledger[cid]
        rows.append(f"- [{cid}] {c.url} ({c.status}, weight {c.weight})")
    return "\n".join(rows) + "\n"


def needs_citation(text: str) -> bool:
    """Outward copy: a factual or market statement (digit, %, quantifier) must carry claim ids."""
    return bool(MARKET_STATEMENT.search(text or ""))


def factual_flags(text: str) -> list[str]:
    """Sentences combining a number/quantifier with a market or population word."""
    flagged = []
    for sent in re.split(r"(?<=[.!?])\s+", text or ""):
        if sent.strip().upper().startswith("ASSUMPTION:"):
            continue
        if FACTUAL.search(sent):
            flagged.append(sent.strip())
    return flagged


def label_unsourced_factual(text: str) -> str:
    """Prefix every flagged factual sentence with ASSUMPTION: (used after one regeneration)."""
    out = text
    for s in factual_flags(text):
        out = out.replace(s, "ASSUMPTION: " + s, 1)
    return out
