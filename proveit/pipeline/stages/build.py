"""Phase 3 (Build) and Gate 3 (tests).

The Builder writes a product spec, checklist modules and CSV templates; deterministic QA checks decide
the gate. A failed build is rebuilt once with the failing checks named.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents import builder, qa

from ... import gates, render
from ...log import emit, log_action
from ...models import GateDecision, Variant
from ...reports import module_md, preview_banner, product_spec_md, template_csv, test_report_md
from ..run import PHASE_NAMES, Run, Stage, Status, runtime

BUILD_ATTEMPTS = 2


@dataclass
class Build:
    modules: list
    decision: GateDecision
    results: list[dict]


def _build_and_test(run: Run, variant: Variant, spec, n_modules: int, prov: render.Provenance, feedback: str) -> Build:
    preview = preview_banner(run)
    modules, csvs = [], []
    for i in range(n_modules):
        module = builder.module(run.id, variant, spec, i, feedback)
        modules.append(module)
        for statement in [module.intro] + module.steps:
            prov.add(f"phase3_step2_module-{i + 1}.md", statement)
        run.write(f"phase3_step2_module-{i + 1}.md", module_md(module, preview))
        csvs.append(template_csv(module))
        run.write(f"phase3_step2_template-{i + 1}.csv", csvs[-1])
    docs = builder.user_docs(spec, modules)
    run.write("phase3_step3_user-docs.md", preview + docs)
    results = qa.run(spec, modules, csvs, docs, n_modules)
    dec = gates.evaluate_gate3(run.id, results, run.sha)
    log_action(
        run.id,
        "qa",
        "run_product_tests",
        model=None,
        cost=0,
        outcome=dec.outcome,
        passed=dec.metrics["passed"],
        total=dec.metrics["total"],
    )
    return Build(modules, dec, results)


def stage_phase3(run: Run) -> None:
    run.progress(3, "Phase 3: Build")
    run.say("phase", n=3, name=PHASE_NAMES[3])
    variant = run.variant()
    spec = builder.spec(run.id, variant)
    prov = render.Provenance()
    prov.add("phase3_step1_product-spec.md", spec.audience)
    run.write("phase3_step1_product-spec.md", product_spec_md(spec, preview_banner(run)))

    n_modules = min(runtime()[run.mode]["modules"], len(spec.modules))
    feedback = ""
    for attempt in range(1, BUILD_ATTEMPTS + 1):
        build = _build_and_test(run, variant, spec, n_modules, prov, feedback)
        if build.decision.outcome == "go" or attempt == BUILD_ATTEMPTS:
            break
        feedback = "Fix these QA failures: " + ", ".join(build.decision.failed_checks)
        log_action(run.id, "qa", "rebuild_after_failed_tests", failed=build.decision.failed_checks)

    dec = build.decision
    run.write("phase3_gate_test-report.md", test_report_md(dec, build.results, attempt))
    prov.write(run.dir)
    run.state["gate3"] = dec.model_dump()
    run.state["product"] = {"title": spec.title, "audience": spec.audience, "modules": [m.title for m in build.modules]}
    run.say("gate", **dec.model_dump())
    emit(run.id, 3, "gate", dec.outcome, gate="gate3_tests")
    if dec.outcome == "go":
        run.save(Stage.PHASE4, status=Status.RUNNING)
    else:
        run.save(Stage.AWAIT_FOUNDER, status=Status.WAITING)
