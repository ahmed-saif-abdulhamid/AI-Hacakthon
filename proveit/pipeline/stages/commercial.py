"""Phase 4 (Commercial setup): Good/Better/Best pricing from verified price points, and policy drafts.

Gate 4 is the founder's: the run waits until the founder approves or rejects the price and the policies.
"""

from __future__ import annotations

from agents import policy_drafter, pricer

from ... import render
from ...log import emit
from ...reports import policies_md, pricing_md
from ..copy_guard import guarded
from ..run import PHASE_NAMES, Run, Stage, Status

PRICING_FIELDS = ("good", "better", "best", "basis", "note")


def _write_pricing(run: Run, prov: render.Provenance) -> None:
    claims = run.claims()
    tiers = pricer.tiers(claims)
    rationale = pricer.rationale(run.id, claims, tiers)
    run.write("phase4_step1_pricing.md", pricing_md(run, tiers, rationale, prov))
    run.state["pricing"] = {k: tiers[k] for k in PRICING_FIELDS}


def _policies_text(policies) -> str:
    return "\n".join(policies.terms + policies.privacy + policies.refunds)


def _write_policies(run: Run, prov: render.Provenance) -> None:
    title = run.state.get("product", {}).get("title", run.variant().title)
    policies, issue = guarded(
        run, "policies", lambda _feedback: policy_drafter.run(run.id, title), _policies_text, scope="policy"
    )
    for statement in policies.terms + policies.privacy + policies.refunds:
        prov.add("phase4_step2_policies.md", statement)
    run.write("phase4_step2_policies.md", policies_md(policies, policy_drafter.STAMP, issue))


def stage_phase4(run: Run) -> None:
    run.progress(4, "Phase 4: Commercial setup")
    run.say("phase", n=4, name=PHASE_NAMES[4])
    prov = render.Provenance()
    _write_pricing(run, prov)
    _write_policies(run, prov)
    prov.write(run.dir)
    emit(run.id, 4, "founder_gate", "gate4", note="Approve or reject the price and policy drafts")
    run.say("approval_needed", action="gate 4 price and policy review", sha="")
    run.save(Stage.AWAIT_GATE4, status=Status.WAITING)
