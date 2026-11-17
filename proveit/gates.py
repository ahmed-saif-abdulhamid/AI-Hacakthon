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
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from sources.base import keywords

from .models import UNSPECIFIED, Claim, FounderBrief, GateDecision, SourceCall, Variant
from .verifier import is_on_topic, is_recent, topic_keywords

ROOT = Path(__file__).resolve().parent.parent
OUTCOMES = ("go", "repeat", "pivot", "stop")
WEAK_PAIN_FLOOR = 3  # rule 3: below this many weighted pain signals the idea stops, whatever the threshold
PIVOT_CHECKS = {"competitor_band", "founder_fit"}  # rule 5: failures a different angle can fix
GATE2_PIVOT_SHARE = 0.3  # gate 2: at least this share of the waitlist target is a pivot, below it a stop
MIN_WEEKLY_HOURS = 5


def canonical_json(obj) -> str:
    """Deterministic JSON (sorted keys, no spaces), so equal data always hashes the same."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def load_thresholds(path: Path | None = None) -> dict:
    """The gate thresholds from ``config/gates.yaml`` (or the given path)."""
    return yaml.safe_load((path or ROOT / "config" / "gates.yaml").read_text(encoding="utf-8"))


def thresholds_sha256(thresholds: dict, brief: dict) -> str:
    """The pre-registration hash of the thresholds and the brief, logged before any search."""
    return hashlib.sha256(canonical_json({"gates": thresholds, "brief": brief}).encode()).hexdigest()


# ---- metrics (computed in code) ------------------------------------------------


def _num(text: str) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(m.group(0)) if m else None


def founder_fit(brief: FounderBrief) -> tuple[float, dict]:
    """0-5 from the brief. Each component: 1 met, 0.5 unspecified (neutral), 0 not met."""
    parts = {}
    idea_kw = keywords(brief.idea)
    if brief.skills == UNSPECIFIED:
        parts["skills_match_idea"] = 0.5
    else:
        parts["skills_match_idea"] = (
            1.0 if keywords(brief.skills) & idea_kw or len(keywords(brief.skills)) >= 3 else 0.0
        )
    hours = _num(brief.hours_per_week) if brief.hours_per_week != UNSPECIFIED else None
    parts["hours_per_week_ge_5"] = 0.5 if hours is None else (1.0 if hours >= MIN_WEEKLY_HOURS else 0.0)
    parts["budget_stated"] = 0.5 if brief.budget == UNSPECIFIED else 1.0
    parts["target_market_stated"] = 0.5 if brief.target_market == UNSPECIFIED else 1.0
    parts["values_stated"] = 0.5 if brief.values == UNSPECIFIED else 1.0
    return round(sum(parts.values()), 2), parts


def coverage(
    calls: list[SourceCall], hits_by_call: dict[int, list], variant: Variant, min_hits: int = 3
) -> tuple[float, list[dict]]:
    """Share of pain-capable calls (HN, SE, SearXNG) returning >= ``min_hits`` on-topic hits."""
    topic = topic_keywords(variant)
    rows = []
    for i, call in enumerate(calls):
        if not call.pain_capable:
            continue
        on_topic = sum(1 for h in hits_by_call.get(i, []) if is_on_topic(h.title + " " + h.text, topic))
        call.n_on_topic = on_topic
        rows.append(
            {
                "source": call.source,
                "query": call.query,
                "ok": call.ok,
                "hits": call.n_hits,
                "on_topic": on_topic,
                "covered": on_topic >= min_hits,
                "error": call.error,
            }
        )
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
    """Gate 1 metrics computed by code from the counted claims, the brief and the source coverage."""
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
        """Share of the target reached, capped at 1."""
        return 1.0 if t == 0 else min(1.0, v / t)

    comp_ok = lo <= m["competitors"] <= hi
    return {
        "sourced_pain": (m["sourced_pain"] >= g["min_sourced_pain"], frac(m["sourced_pain"], g["min_sourced_pain"])),
        "distinct_sources": (
            m["distinct_sources"] >= g["min_distinct_sources"],
            frac(m["distinct_sources"], g["min_distinct_sources"]),
        ),
        "recent_share": (m["recent_share"] >= g["min_recent_share"], frac(m["recent_share"], g["min_recent_share"])),
        "wtp_signals": (m["wtp_signals"] >= g["min_wtp_signals"], frac(m["wtp_signals"], g["min_wtp_signals"])),
        "competitor_band": (
            comp_ok,
            1.0 if comp_ok else (frac(m["competitors"], lo) if m["competitors"] < lo else hi / m["competitors"]),
        ),
        "founder_fit": (m["founder_fit"] >= g["min_founder_fit"], frac(m["founder_fit"], g["min_founder_fit"])),
        "coverage": (m["coverage"] >= g["min_coverage"], frac(m["coverage"], g["min_coverage"])),
    }


def evaluate_gate1(
    run_id: str,
    metrics: dict,
    thresholds: dict,
    brief: dict,
    registered_sha: str,
    *,
    model_failure: bool = False,
    missed: list[str] | None = None,
    excluded: str | None = None,
    repeats: int = 0,
    variant_n: int = 1,
    n_variants: int = 3,
    next_variant: int | None = 0,
) -> GateDecision:
    """Apply the Gate 1 rules in precedence order (see the module docstring); the first that fires decides."""
    if next_variant == 0:  # not given: simply the next number
        next_variant = variant_n + 1 if variant_n < n_variants else None
    g = thresholds["gate1_evidence"]
    checks = _checks(metrics, g) if metrics else {}
    failed = [k for k, (ok, _) in checks.items() if not ok]
    inputs = _Gate1Inputs(metrics, g, checks, failed, missed or [], model_failure, excluded, repeats, next_variant)
    decision = next((d for rule in GATE1_RULES if (d := rule(inputs))), None) or _rule7_stop(inputs)
    return GateDecision(
        run_id=run_id,
        gate="gate1_evidence",
        metrics=metrics,
        thresholds=g,
        thresholds_sha256=registered_sha,
        goalpost_moved=thresholds_sha256(thresholds, brief) != registered_sha,
        failed_checks=failed,
        **decision,
    )


@dataclass(frozen=True)
class _Gate1Inputs:
    metrics: dict
    thresholds: dict
    checks: dict[str, tuple[bool, float]]
    failed: list[str]
    missed: list[str]
    model_failure: bool
    excluded: str | None
    repeats: int
    next_variant: int | None


def _rule0_model(i: _Gate1Inputs) -> dict | None:
    """A broken or suspect researcher output must never look like a weak idea."""
    if not i.model_failure and len(i.missed) < i.thresholds["model_suspect_missed"]:
        return None
    cause = (
        "The research model returned invalid output after a retry. "
        if i.model_failure
        else f"{len(i.missed)} sentences pass code's own on-topic and cue check but were not selected by the model. "
    )
    return {
        "outcome": "repeat",
        "reason": "model_failure" if i.model_failure else "model_suspect",
        "next_step": "rerun_research",
        "rule_fired": "rule_0",
        "recommendation": cause + "A broken model must never look like a weak idea, so this is a REPEAT.",
    }


def _rule1_excluded(i: _Gate1Inputs) -> dict | None:
    if not i.excluded:
        return None
    return {
        "outcome": "stop",
        "reason": "excluded_category",
        "rule_fired": "rule_1",
        "recommendation": f"Excluded product category ({i.excluded}). Not eligible.",
    }


def _rule2_low_coverage(i: _Gate1Inputs) -> dict | None:
    """Sources that cannot see the market are not evidence of absence."""
    cov, need = i.metrics["coverage"], i.thresholds["min_coverage"]
    if cov >= need:
        return None
    return {
        "outcome": "repeat",
        "reason": "insufficient_evidence",
        "next_step": "mom_test_interviews",
        "rule_fired": "rule_2",
        "recommendation": (
            f"Our public sources cannot see this market well enough (coverage {cov} < {need}). "
            "This is not evidence of absence. Run 5 Mom Test interviews."
        ),
    }


def _rule3_weak_pain(i: _Gate1Inputs) -> dict | None:
    pain = i.metrics["sourced_pain"]
    if pain >= WEAK_PAIN_FLOOR:
        return None
    return {
        "outcome": "stop",
        "reason": "weak_pain_evidence",
        "rule_fired": "rule_3",
        "recommendation": (
            f"The topic is discussed (coverage {i.metrics['coverage']}), but verified pain signals are {pain}, "
            f"below {WEAK_PAIN_FLOOR} and far below the pre-registered {i.thresholds['min_sourced_pain']}. "
            "Recommend: do not build this."
        ),
    }


def _rule4_all_pass(i: _Gate1Inputs) -> dict | None:
    if i.failed:
        return None
    return {
        "outcome": "go",
        "reason": "all_checks_pass",
        "next_step": "phase2_validate",
        "rule_fired": "rule_4",
        "recommendation": "Every pre-registered check passed.",
    }


def _rule5_pivot(i: _Gate1Inputs) -> dict | None:
    """Real pain, but the market or the founder does not fit this angle: research the next variant."""
    pain_ok = i.checks["sourced_pain"][0] and i.checks["distinct_sources"][0]
    if not (pain_ok and set(i.failed) <= PIVOT_CHECKS and i.next_variant):
        return None
    return {
        "outcome": "pivot",
        "reason": "pain_ok_" + "_and_".join(i.failed),
        "next_step": f"research_variant_{i.next_variant}",
        "rule_fired": "rule_5",
        "recommendation": f"Pain is real, but {', '.join(i.failed)} failed. Pivot: research variant {i.next_variant}.",
    }


def _rule6_near_miss(i: _Gate1Inputs) -> dict | None:
    near = all(i.checks[k][1] >= i.thresholds["near_miss_ratio"] for k in i.failed)
    if not (near and i.repeats < i.thresholds["max_repeats"]):
        return None
    return {
        "outcome": "repeat",
        "reason": "near_miss",
        "next_step": "broaden_queries",
        "rule_fired": "rule_6",
        "recommendation": "Close to target on " + ", ".join(i.failed) + ". Repeat with broader queries.",
    }


def _rule7_stop(i: _Gate1Inputs) -> dict:
    return {
        "outcome": "stop",
        "reason": "checks_failed",
        "rule_fired": "rule_7",
        "recommendation": "Failed: " + ", ".join(i.failed) + ". Recommend: stop.",
    }


GATE1_RULES = (
    _rule0_model,
    _rule1_excluded,
    _rule2_low_coverage,
    _rule3_weak_pain,
    _rule4_all_pass,
    _rule5_pivot,
    _rule6_near_miss,
)


# ---- gates 2 and 3 --------------------------------------------------------------


def evaluate_gate2(
    run_id: str, thresholds: dict, registered_sha: str, real_signups: int, test_signups: int, visits: int = 0
) -> GateDecision:
    """Gate 2 (demand): real sign-ups against the pre-registered target; test sign-ups never count."""
    g = thresholds["gate2_demand"]
    metrics = {
        "real_signups": real_signups,
        "test_signups_excluded": test_signups,
        "visits": visits,
        "public_hosting": "STUBBED",
    }
    base = dict(run_id=run_id, gate="gate2_demand", metrics=metrics, thresholds=g, thresholds_sha256=registered_sha)
    if real_signups >= g["waitlist_target"]:
        return GateDecision(
            **base,
            outcome="go",
            reason="waitlist_target_met",
            rule_fired="g2_target",
            recommendation="Waitlist target met.",
        )
    if real_signups == 0:
        return GateDecision(
            **base,
            outcome="repeat",
            reason="insufficient_evidence",
            next_step="share_landing_page_publicly",
            failed_checks=["waitlist_target"],
            rule_fired="g2_no_real_traffic",
            recommendation=(
                f"0 real sign-ups against a target of {g['waitlist_target']} in "
                f"{g['window_days']} days. Public hosting is STUBBED and test "
                "sign-ups are excluded, so demand is not yet proven. Continuing "
                "needs a logged founder override."
            ),
        )
    share = real_signups / g["waitlist_target"]
    outcome = "pivot" if share >= GATE2_PIVOT_SHARE else "stop"
    return GateDecision(
        **base,
        outcome=outcome,
        reason="waitlist_target_missed",
        failed_checks=["waitlist_target"],
        rule_fired="g2_missed",
        recommendation=f"{real_signups} of {g['waitlist_target']} sign-ups. Recommend {outcome}.",
    )


def evaluate_gate3(run_id: str, results: list[dict], registered_sha: str = "") -> GateDecision:
    """Gate 3 (tests): GO only when every required QA check passed."""
    failed = [r["name"] for r in results if r.get("required", True) and not r["passed"]]
    return GateDecision(
        run_id=run_id,
        gate="gate3_tests",
        outcome="go" if not failed else "repeat",
        reason="all_required_pass" if not failed else "tests_failed",
        next_step=None if not failed else "fix_and_rebuild",
        metrics={"passed": sum(r["passed"] for r in results), "total": len(results)},
        thresholds={"all_required_pass": True},
        thresholds_sha256=registered_sha,
        failed_checks=failed,
        rule_fired="g3_tests",
        recommendation="All required QA checks pass." if not failed else "Failed QA checks: " + ", ".join(failed),
    )
