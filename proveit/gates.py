"""Gatekeeper: pure, deterministic code. LLMs argue; this module decides.

Gate 1 rule precedence (first match wins):
  0 researcher output invalid / model_suspect      -> REPEAT (model_failure | model_suspect)
  1 excluded category                              -> STOP
  2 coverage < min_coverage                        -> REPEAT (insufficient_evidence, mom_test_interviews)
  3 sourced_pain < 3 with coverage OK              -> STOP
  4 all checks pass                                -> GO
  5 pain OK, competitors out of band or fit low    -> PIVOT (research_variant_<n>)
  6 every failed check >= 60% of target, repeats < max -> REPEAT (broaden queries)
  7 otherwise                                      -> STOP
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from sources.base import keywords

from .models import Claim, FounderBrief, GateDecision, SourceCall, UNSPECIFIED, Variant
from .verifier import is_on_topic, is_recent, topic_keywords

ROOT = Path(__file__).resolve().parent.parent
OUTCOMES = ("go", "repeat", "pivot", "stop")


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def load_thresholds(path: Path | None = None) -> dict:
    return yaml.safe_load((path or ROOT / "config" / "gates.yaml").read_text(encoding="utf-8"))


def thresholds_sha256(thresholds: dict, brief: dict) -> str:
    return hashlib.sha256(canonical_json({"gates": thresholds, "brief": brief}).encode()).hexdigest()


# ---- metrics (computed in code) ------------------------------------------------

def _num(text: str) -> float | None:
    import re
    m = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(m.group(0)) if m else None


def founder_fit(brief: FounderBrief) -> tuple[float, dict]:
    """0-5 from the brief. Each component: 1 met, 0.5 unspecified (neutral), 0 not met."""
    parts = {}
    idea_kw = keywords(brief.idea)
    if brief.skills == UNSPECIFIED:
        parts["skills_match_idea"] = 0.5
    else:
        parts["skills_match_idea"] = 1.0 if keywords(brief.skills) & idea_kw or len(keywords(brief.skills)) >= 3 else 0.0
    hours = _num(brief.hours_per_week) if brief.hours_per_week != UNSPECIFIED else None
    parts["hours_per_week_ge_5"] = 0.5 if hours is None else (1.0 if hours >= 5 else 0.0)
    parts["budget_stated"] = 0.5 if brief.budget == UNSPECIFIED else 1.0
    parts["target_market_stated"] = 0.5 if brief.target_market == UNSPECIFIED else 1.0
    parts["values_stated"] = 0.5 if brief.values == UNSPECIFIED else 1.0
    return round(sum(parts.values()), 2), parts


def coverage(calls: list[SourceCall], hits_by_call: dict[int, list], variant: Variant, min_hits: int = 3) -> tuple[float, list[dict]]:
    """Share of pain-capable calls (HN, SE, SearXNG) returning >= ``min_hits`` on-topic hits."""
    topic = topic_keywords(variant)
    rows = []
    for i, call in enumerate(calls):
        if not call.pain_capable:
            continue
        on_topic = sum(1 for h in hits_by_call.get(i, []) if is_on_topic(h.title + " " + h.text, topic))
        call.n_on_topic = on_topic
        rows.append({"source": call.source, "query": call.query, "ok": call.ok, "hits": call.n_hits,
                     "on_topic": on_topic, "covered": on_topic >= min_hits, "error": call.error})
    if not rows:
        return 0.0, rows
    return round(sum(r["covered"] for r in rows) / len(rows), 2), rows


def _one_per_comment(claims: list) -> list:
    """Several sentences from the same comment are one person's complaint: count it once (highest weight)."""
    best: dict = {}
    for c in claims:
        key = c.hit_id or c.url or c.id
        if key not in best or c.weight > best[key].weight:
            best[key] = c
    return list(best.values())


def compute_metrics(claims: list[Claim], brief: FounderBrief, cov: float, th: dict) -> dict:
    g = th["gate1_evidence"]
    counted = [c for c in claims if c.weight > 0]
    pain = _one_per_comment([c for c in counted if c.kind == "pain"])
    recent = [c for c in pain if is_recent(c, g["max_age_months"])]
    fit, fit_parts = founder_fit(brief)
    return {
        "sourced_pain": round(sum(c.weight for c in pain), 2),
        "pain_claims_counted": len(pain),
        "distinct_sources": len({c.source for c in counted if c.kind in ("pain", "wtp", "price_point")}),
        "recent_share": round(len(recent) / len(pain), 2) if pain else 0.0,
        "wtp_signals": sum(1 for c in counted if c.kind in ("wtp", "price_point")),
        "competitors": len({c.url for c in counted if c.kind == "competitor"}),
        "founder_fit": fit,
        "founder_fit_parts": fit_parts,
        "coverage": cov,
        "claims_total": len(claims),
        "claims_on_topic": sum(1 for c in claims if c.on_topic),
        "claims_verified_live": sum(1 for c in claims if c.status == "verified_live"),
        "claims_archived": sum(1 for c in claims if c.status == "archived_match"),
        "claims_unverified": sum(1 for c in claims if c.status == "unverified"),
    }


# ---- gate 1 ---------------------------------------------------------------------

def _checks(m: dict, g: dict) -> dict[str, tuple[bool, float]]:
    """check -> (passed, fraction of target reached)."""
    lo, hi = g["competitor_band"]
    def frac(v, t):
        return 1.0 if t == 0 else min(1.0, v / t)
    comp_ok = lo <= m["competitors"] <= hi
    return {
        "sourced_pain": (m["sourced_pain"] >= g["min_sourced_pain"], frac(m["sourced_pain"], g["min_sourced_pain"])),
        "distinct_sources": (m["distinct_sources"] >= g["min_distinct_sources"],
                             frac(m["distinct_sources"], g["min_distinct_sources"])),
        "recent_share": (m["recent_share"] >= g["min_recent_share"], frac(m["recent_share"], g["min_recent_share"])),
        "wtp_signals": (m["wtp_signals"] >= g["min_wtp_signals"], frac(m["wtp_signals"], g["min_wtp_signals"])),
        "competitor_band": (comp_ok, 1.0 if comp_ok else (frac(m["competitors"], lo) if m["competitors"] < lo else hi / m["competitors"])),
        "founder_fit": (m["founder_fit"] >= g["min_founder_fit"], frac(m["founder_fit"], g["min_founder_fit"])),
        "coverage": (m["coverage"] >= g["min_coverage"], frac(m["coverage"], g["min_coverage"])),
    }


def evaluate_gate1(run_id: str, metrics: dict, thresholds: dict, brief: dict, registered_sha: str, *,
                   model_failure: bool = False, missed: list[str] | None = None, excluded: str | None = None,
                   repeats: int = 0, variant_n: int = 1, n_variants: int = 3) -> GateDecision:
    g = thresholds["gate1_evidence"]
    current_sha = thresholds_sha256(thresholds, brief)
    moved = current_sha != registered_sha
    missed = missed or []
    checks = _checks(metrics, g) if metrics else {}
    failed = [k for k, (ok, _) in checks.items() if not ok]
    base = dict(run_id=run_id, gate="gate1_evidence", metrics=metrics, thresholds=g,
                thresholds_sha256=registered_sha, goalpost_moved=moved, failed_checks=failed)

    if model_failure or len(missed) >= g["model_suspect_missed"]:
        reason = "model_failure" if model_failure else "model_suspect"
        return GateDecision(**base, outcome="repeat", reason=reason, next_step="rerun_research",
                            rule_fired="rule_0",
                            recommendation=("The research model returned invalid output after a retry. "
                                            if model_failure else
                                            f"{len(missed)} sentences pass code's own on-topic and cue check but "
                                            "were not selected by the model. ")
                            + "A broken model must never look like a weak idea, so this is a REPEAT.")
    if excluded:
        return GateDecision(**base, outcome="stop", reason="excluded_category", rule_fired="rule_1",
                            recommendation=f"Excluded product category ({excluded}). Not eligible.")
    if metrics["coverage"] < g["min_coverage"]:
        return GateDecision(**base, outcome="repeat", reason="insufficient_evidence",
                            next_step="mom_test_interviews", rule_fired="rule_2",
                            recommendation=("Our public sources cannot see this market well enough "
                                            f"(coverage {metrics['coverage']} < {g['min_coverage']}). "
                                            "This is not evidence of absence. Run 5 Mom Test interviews."))
    if metrics["sourced_pain"] < 3:
        return GateDecision(**base, outcome="stop", reason="weak_pain_evidence", rule_fired="rule_3",
                            recommendation=(f"The topic is discussed (coverage {metrics['coverage']}), but "
                                            f"verified pain signals are {metrics['sourced_pain']}, below 3 and "
                                            f"far below the pre-registered {g['min_sourced_pain']}. "
                                            "Recommend: do not build this."))
    if not failed:
        return GateDecision(**base, outcome="go", reason="all_checks_pass", next_step="phase2_validate",
                            rule_fired="rule_4", recommendation="Every pre-registered check passed.")
    pain_ok = checks["sourced_pain"][0] and checks["distinct_sources"][0]
    if pain_ok and set(failed) <= {"competitor_band", "founder_fit"} and variant_n < n_variants:
        return GateDecision(**base, outcome="pivot", reason="pain_ok_" + "_and_".join(failed),
                            next_step=f"research_variant_{variant_n + 1}", rule_fired="rule_5",
                            recommendation="Pain is real, but " + ", ".join(failed)
                            + f" failed. Pivot: research variant {variant_n + 1}.")
    if all(checks[k][1] >= g["near_miss_ratio"] for k in failed) and repeats < g["max_repeats"]:
        return GateDecision(**base, outcome="repeat", reason="near_miss", next_step="broaden_queries",
                            rule_fired="rule_6",
                            recommendation="Close to target on " + ", ".join(failed)
                            + ". Repeat with broader queries.")
    return GateDecision(**base, outcome="stop", reason="checks_failed", rule_fired="rule_7",
                        recommendation="Failed: " + ", ".join(failed) + ". Recommend: stop.")


# ---- gates 2 and 3 --------------------------------------------------------------

def evaluate_gate2(run_id: str, thresholds: dict, registered_sha: str, real_signups: int,
                   test_signups: int, visits: int = 0) -> GateDecision:
    g = thresholds["gate2_demand"]
    metrics = {"real_signups": real_signups, "test_signups_excluded": test_signups, "visits": visits,
               "public_hosting": "STUBBED"}
    base = dict(run_id=run_id, gate="gate2_demand", metrics=metrics, thresholds=g,
                thresholds_sha256=registered_sha)
    if real_signups >= g["waitlist_target"]:
        return GateDecision(**base, outcome="go", reason="waitlist_target_met", rule_fired="g2_target",
                            recommendation="Waitlist target met.")
    if real_signups == 0:
        return GateDecision(**base, outcome="repeat", reason="insufficient_evidence",
                            next_step="share_landing_page_publicly", failed_checks=["waitlist_target"],
                            rule_fired="g2_no_real_traffic",
                            recommendation=(f"0 real sign-ups against a target of {g['waitlist_target']} in "
                                            f"{g['window_days']} days. Public hosting is STUBBED and test "
                                            "sign-ups are excluded, so demand is not yet proven. Continuing "
                                            "needs a logged founder override."))
    share = real_signups / g["waitlist_target"]
    outcome = "pivot" if share >= 0.3 else "stop"
    return GateDecision(**base, outcome=outcome, reason="waitlist_target_missed", failed_checks=["waitlist_target"],
                        rule_fired="g2_missed",
                        recommendation=f"{real_signups} of {g['waitlist_target']} sign-ups. Recommend {outcome}.")


def evaluate_gate3(run_id: str, results: list[dict], registered_sha: str = "") -> GateDecision:
    failed = [r["name"] for r in results if r.get("required", True) and not r["passed"]]
    return GateDecision(run_id=run_id, gate="gate3_tests", outcome="go" if not failed else "repeat",
                        reason="all_required_pass" if not failed else "tests_failed",
                        next_step=None if not failed else "fix_and_rebuild",
                        metrics={"passed": sum(r["passed"] for r in results), "total": len(results)},
                        thresholds={"all_required_pass": True}, thresholds_sha256=registered_sha,
                        failed_checks=failed, rule_fired="g3_tests",
                        recommendation="All required QA checks pass." if not failed else
                        "Failed QA checks: " + ", ".join(failed))
