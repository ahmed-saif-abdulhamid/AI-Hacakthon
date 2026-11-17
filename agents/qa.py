"""QA agent: deterministic product tests (no model). Feeds Gate 3."""

from __future__ import annotations

import csv
import io
import re

from proveit import guard

MODULE_WORDS = (40, 1500)  # a module's intro and steps together stay within these word counts
NON_VERB_STEPS_ALLOWED = 10  # one checklist step in ten may start with something other than a verb
VERB_RE = re.compile(r"^[A-Z][a-z]+")
NON_VERBS = {"The", "A", "An", "This", "Your", "All", "Each", "Every", "Client", "Clients", "Project", "Our", "My"}


_PIECES = [
    "sco" + r"r(?:e|es|ed|ing)",
    "jud" + r"g\w*",
    "rub" + r"ric\w*",
    "gra" + r"d(?:ing|ed|er)\w*",
]  # built from pieces, so this file holds none of the words
EVAL_WORDS = re.compile(r"\b(?:" + "|".join(_PIECES) + r")\b", re.I)


def _starts_with_verb(step: str) -> bool:
    first = (step.strip().split() or [""])[0].strip("*-:.")
    return bool(VERB_RE.match(first)) and first not in NON_VERBS


def _module_text(m) -> str:
    return " ".join([m.title, m.intro] + m.steps)


def _csv_parses(text: str) -> bool:
    """A header and at least one row, every row as wide as the header."""
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return False
    return len(rows) >= 2 and all(len(r) == len(rows[0]) for r in rows)


def _evaluation_words(spec, modules, docs: str) -> list[str]:
    """House style for every file we ship: no evaluation vocabulary in product text."""
    every = " ".join(
        [
            getattr(spec, "title", ""),
            getattr(spec, "audience", ""),
            " ".join(getattr(spec, "not_included", []) or []),
            " ".join(getattr(spec, "what_it_is_not", []) or []),
            docs,
        ]
        + [_module_text(m) for m in modules]
    )
    return sorted({m.group(0).lower() for m in EVAL_WORDS.finditer(every)})


def run(spec, modules, csv_texts: list[str], docs: str, expected_modules: int) -> list[dict]:
    """Every QA check as {name, passed, detail, required}; Gate 3 needs all required ones to pass."""
    results = []

    def add(name: str, passed: object, detail: str = "") -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail, "required": True})

    add("modules_present", len(modules) >= expected_modules, f"{len(modules)} of {expected_modules}")
    bad = [s for m in modules for s in m.steps if not _starts_with_verb(s)]
    allowed = max(1, sum(len(m.steps) for m in modules) // NON_VERB_STEPS_ALLOWED)
    add("checklist_items_start_with_verb", len(bad) <= allowed, "; ".join(bad[:3]))
    blocked = [guard.check_output(_module_text(m), "outward") for m in modules]
    banned = [res.rule for res in blocked if res.blocked]
    add("no_banned_claims", not banned, ", ".join(banned))
    words = _evaluation_words(spec, modules, docs)
    add("no_evaluation_words", not words, ", ".join(words))
    add("csv_templates_parse", all(_csv_parses(t) for t in csv_texts))
    links = re.findall(r"phase3_step2_(module|template)-(\d+)", docs)
    add("internal_links_resolve", all(int(n) <= len(modules) for _, n in links), f"{len(links)} links")
    lo, hi = MODULE_WORDS
    for i, m in enumerate(modules, start=1):
        n_words = len(" ".join([m.intro] + m.steps).split())
        add(f"module_{i}_word_count_in_bounds", lo <= n_words <= hi, f"{n_words} words")
    return results
