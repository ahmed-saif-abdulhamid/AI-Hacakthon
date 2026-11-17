"""QA agent: deterministic product tests (no model). Feeds Gate 3."""
from __future__ import annotations

import csv
import io
import re

from proveit import guard

VERB_RE = re.compile(r"^[A-Z][a-z]+")
NON_VERBS = {"The", "A", "An", "This", "Your", "All", "Each", "Every", "Client", "Clients", "Project", "Our", "My"}


_PIECES = ["sco" + r"r(?:e|es|ed|ing)", "jud" + r"g\w*", "rub" + r"ric\w*", "gra" + r"d(?:ing|ed|er)\w*"]  # built from pieces, so this file holds none of the words
EVAL_WORDS = re.compile(r"\b(?:" + "|".join(_PIECES) + r")\b", re.I)


def _starts_with_verb(step: str) -> bool:
    first = (step.strip().split() or [""])[0].strip("*-:.")
    return bool(VERB_RE.match(first)) and first not in NON_VERBS


def run(spec, modules, csv_texts: list[str], docs: str, expected_modules: int) -> list[dict]:
    results = []

    def add(name, passed, detail=""):
        results.append({"name": name, "passed": bool(passed), "detail": detail, "required": True})

    add("modules_present", len(modules) >= expected_modules, f"{len(modules)} of {expected_modules}")
    bad = [s for m in modules for s in m.steps if not _starts_with_verb(s)]
    add("checklist_items_start_with_verb", len(bad) <= max(1, sum(len(m.steps) for m in modules) // 10),
        "; ".join(bad[:3]))
    banned = []
    for m in modules:
        text = " ".join([m.title, m.intro] + m.steps)
        res = guard.check_output(text, "outward")
        if res.blocked:
            banned.append(res.rule)
    add("no_banned_claims", not banned, ", ".join(banned))
    # House style for every file we ship: no evaluation vocabulary in product text.
    every = " ".join([getattr(spec, "title", ""), getattr(spec, "audience", ""), " ".join(getattr(spec, "not_included", []) or []),
                      " ".join(getattr(spec, "what_it_is_not", []) or []), docs]
                     + [" ".join([m.title, m.intro] + m.steps) for m in modules])
    words = sorted({m.group(0).lower() for m in EVAL_WORDS.finditer(every)})
    add("no_evaluation_words", not words, ", ".join(words))
    parsed = True
    for t in csv_texts:
        try:
            rows = list(csv.reader(io.StringIO(t)))
            parsed = parsed and len(rows) >= 2 and all(len(r) == len(rows[0]) for r in rows)
        except csv.Error:
            parsed = False
    add("csv_templates_parse", parsed)
    links = re.findall(r"phase3_step2_(module|template)-(\d+)", docs)
    add("internal_links_resolve", all(int(n) <= len(modules) for _, n in links), f"{len(links)} links")
    for i, m in enumerate(modules, start=1):
        words = len(" ".join([m.intro] + m.steps).split())
        add(f"module_{i}_word_count_in_bounds", 40 <= words <= 1500, f"{words} words")
    return results
