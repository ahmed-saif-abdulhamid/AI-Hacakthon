"""Phase 2 (Validate) and Gate 2 (demand).

The Strategist drafts a Lean Canvas and landing-page copy; the copy passes the outward guard and the
page is published only after the founder approves its exact bytes. Gate 2 counts real sign-ups only.
"""

from __future__ import annotations

import re

from agents import strategist

from ... import db, gates, guard, render
from ...log import emit, log_action
from ...reports.common import simple_gate_md
from ...reports.validate import GATE2_NOTE, lean_canvas_md
from ...templates import render_page
from ..approvals import request_approval
from ..copy_guard import drop_blocked, flag_for_founder, guarded, is_blocked
from ..run import PHASE_NAMES, Run, Stage, Status, log_gate

LANDING_FILE = "phase2_step2_landing-page.html"
LEGAL_RULE = "legal_documents"
# Non-legal operational wording for each kind of legal-document phrase the guard's rule matches.
LEGAL_REWRITES: tuple[tuple[str, str], ...] = (
    (r"\bdeposit agreement(s?)\b", r"deposit checklist\1"),
    (r"\b(?:contract|agreement)s? template(s?)\b", r"payment-terms checklist\1"),
    (
        r"\btemplates? for (?:your |my |client |deposit |service )?(?:own )?(?:contracts?|agreements?)\b",
        "payment-terms checklists",
    ),
    (r"\bfor (my|your) (?:own )?contracts\b", r"for \1 payment schedules"),
    (r"\benforce payment terms\b", "follow up on payment schedules"),
)
LEGAL_FALLBACK = (r"\b(?:contract|agreement)(s?)\b", r"payment schedule\1")


def _landing_text(copy) -> str:
    return "\n".join([copy.headline, copy.subheadline] + copy.benefits + [f.q + " " + f.a for f in copy.faq])


def _landing_fields(copy) -> dict:
    """Template fields with deterministic fixes: each question in ``q`` and its answer in ``a``, and every
    unsourced factual statement labelled."""
    fields = copy.model_dump()
    for faq in fields["faq"]:
        if not faq["q"].rstrip().endswith("?") and faq["a"].rstrip().endswith("?"):
            faq["q"], faq["a"] = faq["a"], faq["q"]
    label = render.label_unsourced_factual
    fields["headline"], fields["subheadline"] = label(fields["headline"]), label(fields["subheadline"])
    fields["benefits"] = [label(b) for b in fields["benefits"]]
    fields["faq"] = [{"q": f["q"], "a": label(f["a"])} for f in fields["faq"]]
    return fields


def _remove_blocked_copy(run: Run, fields: dict, issue: str) -> None:
    """Still blocked after a redraft: code removes the questions and benefits the guard blocks, so the
    founder is never offered copy that breaks a rule; anything left is flagged for the founder."""
    fields["faq"] = drop_blocked(run, "landing_copy", fields["faq"], lambda f: f["q"] + " " + f["a"])
    fields["benefits"] = drop_blocked(run, "landing_copy", fields["benefits"])
    remaining = "\n".join(
        [fields["headline"], fields["subheadline"]]
        + fields["benefits"]
        + [f["q"] + " " + f["a"] for f in fields["faq"]]
    )
    if is_blocked(remaining):
        flag_for_founder(run, "landing_copy", "landing_issue", issue)


def _rewrite_legal_text(text: str) -> str:
    """Replace legal-document phrases with operational ones; any match left gets the plain fallback."""
    for pattern, repl in LEGAL_REWRITES:
        text = re.sub(pattern, _keep_case(repl), text, flags=re.I)
    if guard.rx(guard.rules()["output_copy"][LEGAL_RULE]).search(text):
        pattern, repl = LEGAL_FALLBACK
        text = re.sub(pattern, _keep_case(repl), text, flags=re.I)
    return text


def _keep_case(repl: str):
    """A replacement that keeps the capital letter of a phrase that starts a sentence."""

    def sub(match: re.Match) -> str:
        out = match.expand(repl)
        return out[:1].upper() + out[1:] if match.group(0)[:1].isupper() else out

    return sub


def rewrite_legal_terms(run_id: str, canvas) -> list[str]:
    """Analysis artifacts skip the outward copy guard, so the canvas is checked here against the legal
    documents rule and every matching statement is rewritten in place. Returns the rewritten originals."""
    legal = guard.rx(guard.rules()["output_copy"][LEGAL_RULE])
    changed = []
    for name in strategist.CELLS + ("riskiest_assumption", "experiment"):
        cell = getattr(canvas, name, None)
        for statement in cell if isinstance(cell, list) else [cell] if cell is not None else []:
            if legal.search(statement.text):
                changed.append(statement.text)
                statement.text = _rewrite_legal_text(statement.text)
    if changed:
        log_action(run_id, "guard", "rewrite_legal_terms", model=None, cost=0, rule=LEGAL_RULE, count=len(changed))
    return changed


def stage_phase2(run: Run) -> None:
    run.progress(2, "Phase 2: Validate")
    run.say("phase", n=2, name=PHASE_NAMES[2])
    variant = run.variant()
    canvas = strategist.canvas(run.id, run.brief, variant, run.variant_claims())
    rewrite_legal_terms(run.id, canvas)
    prov = render.Provenance()
    run.write("phase2_step1_lean-canvas.md", lean_canvas_md(run, variant, canvas, strategist.CELLS, prov))

    copy, issue = guarded(
        run, "landing_copy", lambda feedback: strategist.landing(run.id, variant, feedback), _landing_text
    )
    fields = _landing_fields(copy)
    if issue:
        _remove_blocked_copy(run, fields, issue)
    for statement in [copy.headline, copy.subheadline] + copy.benefits + [f.a for f in copy.faq]:
        prov.add(LANDING_FILE, statement)
    html = render_page("landing.html.j2", run_id=run.id, content_note="shown in the approval console", **fields)
    run.write(LANDING_FILE, html)
    prov.write(run.dir)
    request_approval(
        run,
        "publish_landing_page",
        html.encode("utf-8"),
        "text/html; charset=utf-8",
        "Serve the landing page on localhost at /p/<run> (public hosting STUBBED)",
    )


def _count_signups(run_id: str, test: bool) -> int:
    return db.query_one("SELECT COUNT(*) n FROM signups WHERE run_id=? AND test=?", (run_id, int(test)))["n"]


def stage_gate2(run: Run) -> None:
    run.progress(2, "Gate 2: demand")
    dec = gates.evaluate_gate2(
        run.id, run.thresholds, run.sha, _count_signups(run.id, test=False), _count_signups(run.id, test=True)
    )
    log_gate(run, "demand_gate", dec)
    run.state["gate2"] = dec.model_dump()
    run.say("gate", **dec.model_dump())
    run.write("phase2_gate_decision.md", simple_gate_md("Phase 2 gate: demand", dec, GATE2_NOTE))
    emit(run.id, 2, "gate", dec.outcome, gate="gate2_demand", reason=dec.reason)
    if dec.outcome == "go":
        run.save(Stage.PHASE3, status=Status.RUNNING)
    else:
        run.save(Stage.AWAIT_OVERRIDE, status=Status.WAITING)
