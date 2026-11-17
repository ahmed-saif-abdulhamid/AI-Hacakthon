"""Phase 6 (Operate and learn, STUBBED): a memo, support-answer drafts and a metrics plan, and the
persevere-or-pivot gate decided by code from real records only (test orders never count)."""

from __future__ import annotations

from agents import analyst

from ... import db, gates
from ...log import emit, log_action
from ...reports import operate_gate_md
from ..run import Run, Stage, Status

METRIC_QUERIES = {
    "real_signups": "SELECT COUNT(*) n FROM signups WHERE run_id=? AND test=0",
    "real_orders": "SELECT COUNT(*) n FROM orders WHERE run_id=? AND test=0",
    "test_orders": "SELECT COUNT(*) n FROM orders WHERE run_id=? AND test=1",
    "real_refunds": "SELECT COUNT(*) n FROM refunds r JOIN orders o ON o.id=r.order_id WHERE o.run_id=? AND o.test=0",
}


def _real_metrics(run_id: str) -> dict:
    metrics = {name: db.query_one(sql, (run_id,))["n"] for name, sql in METRIC_QUERIES.items()}
    metrics["days_since_launch"] = 0  # no live launch in this demo
    return metrics


def stage_phase6(run: Run) -> None:
    run.progress(6, "Phase 6: Operate and learn (STUBBED)")
    thresholds = dict(run.thresholds)
    thresholds.setdefault("gate6_operate", gates.load_thresholds()["gate6_operate"])  # runs from before Gate 6
    metrics = _real_metrics(run.id)
    outcome, reason = analyst.decide(metrics, thresholds)

    run.write("phase6_step1_memo.md", analyst.memo(metrics, thresholds))
    log_action(run.id, "analyst", "operate_and_learn_memo", model=None, cost=0, status="STUBBED")
    run.write(
        "phase6_step2_support-answers.md",
        analyst.support_faq(
            run.state.get("product") or {},
            run.state.get("pricing") or {},
            run.read("phase4_step2_policies.md"),
            run.read("phase3_step3_user-docs.md"),
        ),
    )
    log_action(run.id, "support", "draft_support_answers", model=None, cost=0, sent=False)
    run.write("phase6_step3_metrics.md", analyst.metrics_plan(metrics, thresholds))
    log_action(run.id, "analyst", "metrics_plan", model=None, cost=0)

    run.write("phase6_gate_decision.md", operate_gate_md(outcome, reason, metrics))
    log_action(run.id, "gatekeeper", "operate_gate", model=None, cost=0, outcome=outcome, reason=reason)
    emit(run.id, 6, "gate", outcome, gate="gate6_operate", reason=reason)
    run.say("done")
    run.save(Stage.DONE, status=Status.DONE)
