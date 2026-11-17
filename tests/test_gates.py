"""Each gate rule in precedence order, pre-registration and goalpost detection."""
from __future__ import annotations

import pytest

from proveit import gates
from proveit.models import FounderBrief

TH = gates.load_thresholds()
BRIEF = {"text": "Idea: test", "fields": {}}
SHA = gates.thresholds_sha256(TH, BRIEF)


def metrics(**over):
    m = {"sourced_pain": 8.0, "distinct_sources": 2, "recent_share": 0.8, "wtp_signals": 2, "competitors": 3,
         "founder_fit": 4.0, "coverage": 0.8}
    m.update(over)
    return m


def ev(m, **kw):
    return gates.evaluate_gate1("r1", m, TH, BRIEF, SHA, **kw)


def test_rule0_model_failure_and_suspect():
    assert ev(metrics(), model_failure=True).reason == "model_failure"
    d = ev(metrics(sourced_pain=0), missed=["H1.S1", "H1.S2", "H2.S1"])
    assert (d.outcome, d.reason, d.rule_fired) == ("repeat", "model_suspect", "rule_0")


def test_rule1_excluded():
    d = ev(metrics(), excluded="excluded_health")
    assert (d.outcome, d.rule_fired) == ("stop", "rule_1")


def test_rule2_low_coverage_is_repeat_never_stop():
    d = ev(metrics(coverage=0.2, sourced_pain=0))
    assert (d.outcome, d.reason, d.next_step) == ("repeat", "insufficient_evidence", "mom_test_interviews")


def test_rule3_discussed_but_no_pain_is_stop():
    d = ev(metrics(sourced_pain=2.5))
    assert (d.outcome, d.rule_fired) == ("stop", "rule_3")


def test_rule4_go():
    d = ev(metrics())
    assert (d.outcome, d.rule_fired, d.failed_checks) == ("go", "rule_4", [])


def test_rule5_pivot_on_competitors_or_fit():
    d = ev(metrics(competitors=40))
    assert (d.outcome, d.rule_fired, d.next_step) == ("pivot", "rule_5", "research_variant_2")
    assert ev(metrics(founder_fit=1.5)).outcome == "pivot"


def test_rule6_near_miss_repeat_and_rule7_stop():
    assert ev(metrics(sourced_pain=4.5)).rule_fired == "rule_6"
    assert ev(metrics(sourced_pain=4.5), repeats=2).rule_fired == "rule_7"
    assert ev(metrics(sourced_pain=3.2, wtp_signals=0, distinct_sources=1)).outcome == "stop"


def test_only_canonical_outcomes():
    for m in (metrics(), metrics(coverage=0), metrics(sourced_pain=0), metrics(competitors=99)):
        assert ev(m).outcome in ("go", "repeat", "pivot", "stop")


def test_preregistration_hash_and_goalpost_moved():
    assert ev(metrics()).goalpost_moved is False
    moved = {**TH, "gate1_evidence": {**TH["gate1_evidence"], "min_sourced_pain": 2}}
    d = gates.evaluate_gate1("r1", metrics(), moved, BRIEF, SHA)
    assert d.goalpost_moved is True


def test_live_and_full_same_outcome():
    """The gate takes no mode argument: identical evidence gives identical answers."""
    import yaml
    rt = yaml.safe_load((gates.ROOT / "config" / "runtime.yaml").read_text())
    assert rt["live"]["auto_rerun"] is False
    for m in (metrics(), metrics(sourced_pain=2), metrics(coverage=0.1)):
        assert ev(m).model_dump() == ev(m).model_dump()


def test_founder_fit_unspecified_is_neutral():
    fit, parts = gates.founder_fit(FounderBrief(idea="client onboarding kit"))
    assert fit == 2.5 and set(parts.values()) == {0.5}


def test_gate2_zero_real_signups_is_repeat():
    d = gates.evaluate_gate2("r", TH, SHA, real_signups=0, test_signups=12)
    assert (d.outcome, d.reason) == ("repeat", "insufficient_evidence")
    assert gates.evaluate_gate2("r", TH, SHA, 12, 0).outcome == "stop"


@pytest.mark.parametrize("passed,outcome", [(True, "go"), (False, "repeat")])
def test_gate3(passed, outcome):
    assert gates.evaluate_gate3("r", [{"name": "x", "passed": passed}]).outcome == outcome
