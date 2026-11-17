"""Pipeline smoke tests with the FAKE LLM (tests only) and recorded source fixtures.
They run the real orchestrator, verifier, gates, render, guard and approval code."""

from __future__ import annotations

import json
import re

from proveit import approval, orchestrator, render
from proveit.log import export

STRONG = (orchestrator.ROOT / "briefs" / "strong.md").read_text(encoding="utf-8")
WEAK = (orchestrator.ROOT / "tests" / "fixtures" / "weak_brief.md").read_text(
    encoding="utf-8"
)  # matches weak_hits.json


def approve_pending(run_id: str) -> None:
    pend = approval.list_approvals(run_id, "pending")
    assert len(pend) == 1
    approval.auto_approve(pend[0].id)
    orchestrator.on_approval_decided(pend[0].id)


def test_weak_brief_stops(fake_llm, offline_sources):
    offline_sources("weak_hits.json")
    rid = orchestrator.run_pipeline(WEAK, label="weak")
    run = orchestrator.load(rid)
    assert run.stage == "stopped"
    g = run.state["gate1"]
    assert g["outcome"] == "stop" and g["rule_fired"] == "rule_3"
    assert g["metrics"]["coverage"] >= 0.5 and g["metrics"]["sourced_pain"] < 3
    text = (run.dir / "phase1_gate_decision.md").read_text(encoding="utf-8")
    assert "## Outcome: STOP" in text
    log = export(rid)
    assert log[0]["action"] == "preregister_thresholds"
    assert all(k in e for e in log for k in ("action", "sources", "model", "cost", "approved_by"))


def test_excluded_category_stops_at_eligibility(fake_llm, offline_sources):
    offline_sources("weak_hits.json")
    rid = orchestrator.run_pipeline("Idea: sell CBD gummies online")
    run = orchestrator.load(rid)
    assert run.stage == "stopped"
    assert (run.dir / "phase1_gate_eligibility.md").exists()
    assert run.state["gate1"]["reason"] == "excluded_category"


def test_strong_brief_full_flow_with_approvals(fake_llm, offline_sources):
    offline_sources("strong_hits.json")
    rid = orchestrator.run_pipeline(STRONG, label="strong")
    run = orchestrator.load(rid)
    assert run.state["gate1"]["outcome"] == "go", run.state["gate1"]
    assert run.stage == "await_approval"  # landing page waits for the founder
    assert approval.published_payload(rid, "landing") is None
    approve_pending(rid)
    orchestrator.advance(rid)
    run = orchestrator.load(rid)
    assert run.state["gate2"]["outcome"] == "repeat" and run.state["gate2"]["reason"] == "insufficient_evidence"
    assert run.stage == "await_override"
    assert orchestrator.founder_decide(rid, "override", "Preview the build for the demo; demand not yet proven")["ok"]
    orchestrator.advance(rid)
    run = orchestrator.load(rid)
    assert run.stage == "await_gate4", run.state.get("error")
    orchestrator.founder_decide(rid, "gate4_approve")
    orchestrator.advance(rid)
    assert orchestrator.load(rid).stage == "await_approval"  # open_store
    approve_pending(rid)
    orchestrator.advance(rid)
    assert orchestrator.load(rid).stage == "await_approval"  # refund
    approve_pending(rid)
    orchestrator.advance(rid)
    run = orchestrator.load(rid)
    assert run.stage == "done", run.state.get("error")
    names = {p.name for p in run.dir.iterdir()}
    for f in (
        "phase1_step1_opportunities.md",
        "phase1_step2_claims.json",
        "phase1_step3_market.md",
        "phase1_step4_interview-kit.md",
        "phase1_gate_decision.md",
        "phase2_step1_lean-canvas.md",
        "phase2_step2_landing-page.html",
        "phase2_gate_decision.md",
        "phase3_step1_product-spec.md",
        "phase3_step2_module-1.md",
        "phase3_step2_template-1.csv",
        "phase3_step3_user-docs.md",
        "phase3_gate_test-report.md",
        "phase4_step1_pricing.md",
        "phase4_step2_policies.md",
        "phase4_gate_decision.md",
        "phase5_step1_store-page.html",
        "phase5_step1_launch-post-draft.md",
        "phase5_step3_reconciliation.csv",
        "payment_test_log.md",
        "phase6_step1_memo.md",
    ):
        assert f in names, f
    pay = (run.dir / "payment_test_log.md").read_text(encoding="utf-8")
    assert "403 Forbidden" in pay and "blocked (ApprovalRequired)" in pay and "duplicate=True" in pay
    store = (run.dir / "phase5_step1_store-page.html").read_text(encoding="utf-8")
    assert "No reviews yet" in store and "MOCKED" in store
    log = export(rid)
    approved = [e for e in log if e["approved_by"] == "founder"]
    assert {e["action"] for e in approved} >= {
        "approve_publish_landing_page",
        "publish_landing_page",
        "open_store",
        "refund",
        "founder_override_against_evidence",
    }
    outcomes = {e.get("outcome") for e in log if "outcome" in e}
    assert outcomes <= {"go", "repeat", "pivot", "stop"}


def test_statement_artifacts_sourced(fake_llm, offline_sources):
    """Every bullet in Statement artifacts has a [C..] footnote or an ASSUMPTION: prefix."""
    offline_sources("strong_hits.json")
    rid = orchestrator.run_pipeline(STRONG)
    approve_pending(rid)
    orchestrator.advance(rid)
    run = orchestrator.load(rid)
    for name in ("phase2_step1_lean-canvas.md", "phase1_gate_decision.md"):
        text = (run.dir / name).read_text(encoding="utf-8")
        section = text.split("### Sources")[0]
        bullets = [
            ln
            for ln in section.splitlines()
            if ln.startswith("- ") and not ln.startswith("- **") and not ln.startswith("- [")
        ]
        for b in bullets:
            assert re.search(r"\[C\d+\]", b) or b[2:].startswith("ASSUMPTION:"), (name, b)


def test_no_unsourced_market_claims_in_prose(fake_llm, offline_sources):
    """Spans the model wrote (provenance.json) are never shown as unlabelled market claims."""
    offline_sources("strong_hits.json")
    rid = orchestrator.run_pipeline(STRONG)
    run = orchestrator.load(rid)
    prov = json.loads((run.dir / "provenance.json").read_text(encoding="utf-8"))
    for fname, spans in prov.items():
        body = (run.dir / fname).read_text(encoding="utf-8") if (run.dir / fname).exists() else ""
        for span in spans:
            for flagged in render.factual_flags(span):
                idx = body.find(flagged)
                assert (
                    idx == -1
                    or body[max(0, idx - 12) : idx].endswith("ASSUMPTION: ")
                    or re.search(r"\[C\d+\]", body[idx : idx + len(flagged) + 12])
                ), (fname, flagged)


def test_qa_rejects_evaluation_words_in_product_files():
    from types import SimpleNamespace

    from agents import qa

    m = SimpleNamespace(title="Module", intro="Use this checklist for each new client.", steps=["Send the intake form"])
    spec = SimpleNamespace(title="Kit", audience="designers", not_included=["Client risk-" + "sco" + "ring features"])
    res = {r["name"]: r for r in qa.run(spec, [m], [], "", 1)}
    assert not res["no_evaluation_words"]["passed"] and "sco" + "ring" in res["no_evaluation_words"]["detail"]
