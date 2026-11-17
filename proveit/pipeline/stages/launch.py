"""Phase 5, step 1 (Launch): the store page and a launch-post draft.

The store opens only after the founder approves its exact bytes. The launch post is a draft for the
founder to post under their own name; posting adapters are STUBBED.
"""

from __future__ import annotations

import re

from agents import launcher
from sources.base import split_sentences

from ... import render
from ...reports.launch import launch_post_md
from ...templates import render_page
from ..approvals import request_approval
from ..copy_guard import drop_blocked, flag_for_founder, guarded, is_blocked
from ..run import PHASE_NAMES, Run

STORE_FILE = "phase5_step1_store-page.html"
POST_FILE = "phase5_step1_launch-post-draft.md"
TIER_NAMES = (("Good", "good"), ("Better", "better"), ("Best", "best"))
WHAT_EACH_TIER_GETS = {
    "several_modules": (
        "Module 1 checklist and template",
        "All modules and templates",
        "All modules and templates, plus the buyer guide",
    ),
    "one_module": (
        "The checklist",
        "The checklist and the CSV template",
        "The checklist, the CSV template and the buyer guide",
    ),
}
# A sentence describing what the product contains; code states that itself.
CONTENTS_CLAIM = re.compile(r"\b(includ\w*|contain\w*|comes with|you get|inside|packed with|features?)\b", re.I)


def _store_text(copy) -> str:
    return "\n".join(
        [copy.product_name, copy.tagline, copy.description, copy.who_it_is_for, copy.who_it_is_not_for] + copy.includes
    )


def _store_fields(copy, modules: list[str]) -> dict:
    fields = copy.model_dump()
    if modules:  # the store lists exactly what the buyer downloads
        fields["includes"] = [f"{m} (checklist and CSV template)" for m in modules]
    label = render.label_unsourced_factual
    for key in ("tagline", "description", "who_it_is_for", "who_it_is_not_for"):
        fields[key] = label(fields[key])
    fields["includes"] = [label(x) for x in fields["includes"]]
    return fields


def _tiers(pricing: dict, n_modules: int) -> list[dict]:
    what = WHAT_EACH_TIER_GETS["several_modules" if n_modules > 1 else "one_module"]
    return [{"name": name, "price": pricing[key], "what": w} for (name, key), w in zip(TIER_NAMES, what, strict=True)]


def _pricing_note(pricing: dict) -> str:
    if pricing["basis"] == "verified_price_points":
        return "Prices: " + pricing["basis"] + ". " + pricing["note"]
    return "ASSUMPTION: " + pricing["note"]


def _write_store_page(run: Run, title: str, audience: str, modules: list[str]) -> str:
    copy, issue = guarded(
        run, "store_copy", lambda feedback: launcher.store(run.id, title, audience, modules, feedback), _store_text
    )
    if issue:
        flag_for_founder(run, "store_copy", "store_issue", issue)
    prov = render.Provenance()
    for statement in [copy.tagline, copy.description, copy.who_it_is_for, copy.who_it_is_not_for] + copy.includes:
        prov.add(STORE_FILE, statement)
    prov.write(run.dir)
    pricing = run.state["pricing"]
    html = render_page(
        "store.html.j2",
        run_id=run.id,
        tiers=_tiers(pricing, len(modules)),
        pricing_note=_pricing_note(pricing),
        **_store_fields(copy, modules),
    )
    run.write(STORE_FILE, html)
    return html


def _contents_sentence(modules: list[str]) -> str:
    names = ", ".join(modules[:-1]) + " and " + modules[-1] if len(modules) > 1 else modules[0]
    each = "each part is a" if len(modules) > 1 else "a"
    return f"It includes {names}: {each} checklist and a CSV template."


def _post_text(post) -> str:
    return post.title + "\n" + post.body


def _write_launch_post(run: Run, title: str, audience: str, modules: list[str]) -> None:
    post, issue = guarded(
        run,
        "launch_post",
        lambda feedback: launcher.post(
            run.id, title, audience, feedback, [f"{m} (a checklist and a CSV template)" for m in modules]
        ),
        _post_text,
    )
    # What the product contains is stated by code, never by the model (which invents extra parts).
    if modules:
        rest = [s for s in split_sentences(post.body) if not CONTENTS_CLAIM.search(s)]
        post.body = " ".join([_contents_sentence(modules)] + rest)
    if issue:  # still blocked after a redraft: code drops the sentences the guard blocks
        sentences = split_sentences(post.body)
        kept = drop_blocked(run, "launch_post", sentences)
        if len(kept) < len(sentences):
            post.body = " ".join(kept)
            if not is_blocked(_post_text(post)):
                issue = None
    prov = render.Provenance()
    prov.add(POST_FILE, post.body)
    run.write(POST_FILE, launch_post_md(run, post.title, post.body, issue))
    prov.write(run.dir)


def stage_phase5(run: Run) -> None:
    run.progress(5, "Phase 5: Launch (sell, deliver, get paid)")
    run.say("phase", n=5, name=PHASE_NAMES[5])
    product = run.state.get("product", {})
    title = product.get("title", run.variant().title)
    audience, modules = product.get("audience", ""), product.get("modules", [])
    html = _write_store_page(run, title, audience, modules)
    _write_launch_post(run, title, audience, modules)
    request_approval(
        run,
        "open_store",
        html.encode("utf-8"),
        "text/html; charset=utf-8",
        "Open the store page on localhost at /store/<run> (payments MOCKED)",
    )
