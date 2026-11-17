"""Two-layer guard ("Protocol 0"): deterministic rules first, a short model check second,
plus structural locks that need no model at all.

Scopes (each check runs only where it belongs, so the system's own evidence is never blocked):
  brief             -> B (excluded categories) + the generation-intent part of A
  ask / override    -> all of A + the model check
  outward copy      -> C + the model check (landing fields, store page, launch post, edit_copy replies)
  policy drafts     -> C minus the money-word rules
  analysis / quotes -> exempt from C (gate files, ledgers, canvas, pricing, test reports)
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parent.parent
BRIEF_A_RULES = ("fake_social_proof", "fake_signups", "urgency", "income_promise", "impersonation",
                 "credentials", "arabic_intent")
INTENTS = ("edit_copy", "explain_decision", "rerun_step", "change_threshold", "approve_request",
           "evaluate_brief", "other")


@dataclass
class GuardResult:
    verdict: str = "allow"                 # allow | refuse | clarify | stop
    layer: str | None = None               # rules | model
    rule: str | None = None
    message: str = ""
    category: str | None = None
    matched: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.verdict in ("refuse", "stop")

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def rules() -> dict:
    return yaml.safe_load((ROOT / "config" / "guard_rules.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=64)
def rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I | re.M)


def _fix_typos(text: str) -> str:
    keys = rules()["typo_tokens"]
    out = []
    for tok in re.findall(r"\w+|\W+", text):
        if len(tok) >= 6 and tok.isalpha():
            low = tok.lower()
            best = max(keys, key=lambda k: fuzz.ratio(low, k))
            if low != best and fuzz.ratio(low, best) >= 85:
                tok = keys[best]
        out.append(tok)
    return "".join(out)


def _prep(text: str) -> str:
    t = (text or "").replace("’", "'").replace("–", "-").replace("—", "-")
    return _fix_typos(re.sub(r"\s+", " ", t))


def _match_a(text: str, names: tuple[str, ...] | None = None) -> GuardResult | None:
    t = _prep(text)
    hits = []
    for name, r in rules()["input_intent"].items():
        if names and name not in names:
            continue
        probe = rx(r["exclude"]).sub(" ", t) if r.get("exclude") else t
        m = rx(r["pattern"]).search(probe)
        if m:
            hits.append((name, r, m.group(0)[:80]))
    if not hits:
        return None
    name, r, matched = hits[0]
    refusals = " ".join(h[1]["refusal"] for h in hits)
    return GuardResult("refuse", "rules", name, f"{refusals} {r['alternative']}", matched=matched,
                       notes=[h[0] for h in hits])


def classify_brief(text: str) -> GuardResult:
    """Rule set B: excluded product categories (allow-list and an ask-the-founder tier)."""
    b = rules()["excluded_categories"]
    t = _prep(text)
    probe = rx(b["allow_list"]).sub(" ", t)
    if not rx(b["product_context"]).search(probe) and not re.search(r"[؀-ۿ]", probe):
        return GuardResult("allow")
    for cat, spec in b["categories"].items():
        m = rx(spec["pattern"]).search(probe)
        if m:
            label = {"arabic": "excluded category (Arabic keyword)"}.get(cat, cat.replace("_", " "))
            return GuardResult("stop", "rules", f"excluded_{cat}",
                               f"This is an excluded product category ({label}): physical goods, financial or "
                               "crypto products, and health or legal advice products are not built. "
                               "I can help explore a digital product in an eligible category instead.",
                               category=cat, matched=m.group(0))
    m = rx(b["ask_tier"]).search(probe)
    if m:
        return GuardResult("clarify", "rules", "ask_founder",
                           f"The word '{m.group(0)}' can describe an excluded category. Please confirm the "
                           "product is a digital product that gives no financial, medical or legal advice.",
                           matched=m.group(0))
    return GuardResult("allow")


class PolicyVerdict(BaseModel):
    violates: bool
    rule: str


POLICY_SYSTEM = (
    "You are a strict policy checker for a founder tool. Answer only JSON {\"violates\": bool, \"rule\": str}. "
    "violates=true if the TEXT asks for or contains: fake reviews/testimonials/ratings, fake sign-ups or "
    "traffic, countdown timers or false scarcity, promises of income or guaranteed results, impersonating "
    "a founder/customer/brand, storing passwords or card details, moving/refunding/spending money, creating "
    "accounts, skipping approvals, or building physical goods, financial/crypto, health or legal advice "
    "products. Paraphrases count: any claim that a product will replace a job, pay back its cost or change "
    "someone's income; any invented deadline, price rise or scarcity; writing as if you were a customer, user "
    "or independent person. Ordinary business questions, explanations and honest copy do NOT violate. "
    "rule = short name of the violated rule, or \"none\"."
)


def model_check(text: str, kind: str = "input", run_id: str | None = None) -> GuardResult | None:
    """C2: one short yes/no call. Returns None when the model is unavailable (logged by caller)."""
    from . import llm
    from .log import log_action
    try:
        v, meta = llm.chat_json(PolicyVerdict, POLICY_SYSTEM, f"KIND: {kind}\nTEXT:\n{text[:2000]}",
                                run_id=run_id, agent="guard", num_predict=40)
    except llm.LLMError as e:
        if run_id:
            log_action(run_id, "guard", "model_policy_check_unavailable", model=llm.model_name(), cost=0,
                       error=str(e)[:120])
        return None
    if run_id:
        log_action(run_id, "guard", "model_policy_check", model=meta["model"], cost=0, kind=kind,
                   violates=v.violates, tokens_in=meta["tokens_in"], tokens_out=meta["tokens_out"],
                   seconds=meta["seconds"])
    if v.violates:
        return GuardResult("refuse", "model", f"model:{v.rule[:40]}",
                           "I can't help with that request. I can help with honest, sourced work instead.")
    return GuardResult("allow", "model")


def check_input(text: str, scope: str = "ask", use_model: bool = True, run_id: str | None = None) -> GuardResult:
    """Rule set A (+ B for briefs), then the model check for ask/override scopes."""
    if scope == "brief":
        hit = _match_a(text, BRIEF_A_RULES)
        if hit:
            return hit
        b = classify_brief(text)
        if b.verdict != "allow":
            return b
        if use_model:
            return model_check(text, "brief", run_id) or GuardResult("allow", notes=["model check unavailable"])
        return GuardResult("allow")
    hit = _match_a(text)
    if hit:
        return hit
    # A request to put content into copy ("make the hero say loved by 2,000 founders") is
    # checked against rule set C before any copywriter sees it.
    if route_intent(text) == "edit_copy" or re.search(r"\b(say|says|add|put|include|claim|show|display)\b", text or "", re.I):
        out = check_output(text, "outward")
        if out.blocked:
            out.message = ("I can't put social proof, ratings, urgency or income claims into the copy. "
                           "I can rewrite it to describe what the product contains, for your approval.")
            out.rule = "input_" + (out.rule or "")
            return out
    if use_model:
        res = model_check(text, scope, run_id)
        if res is None:
            return GuardResult("allow", notes=["model check unavailable"])
        return res
    return GuardResult("allow")


def check_output(text: str, artifact_type: str = "outward", use_model: bool = False,
                 run_id: str | None = None) -> GuardResult:
    """Rule set C on outward copy. Analysis artifacts and verbatim quotes are exempt by type."""
    if artifact_type in ("analysis", "quote"):
        return GuardResult("allow", notes=[f"{artifact_type}: exempt from rule set C"])
    c = rules()["output_copy"]
    skip = set(rules()["money_rule_names"]) if artifact_type == "policy" else set()
    for name, pattern in c.items():
        if name in skip:
            continue
        m = rx(pattern).search(text or "")
        if m:
            return GuardResult("refuse", "rules", f"output_{name}",
                               f"Outward copy blocked ({name.replace('_', ' ')}): '{m.group(0)[:60]}'.",
                               matched=m.group(0)[:80])
    if use_model:
        res = model_check(text, f"outward copy ({artifact_type})", run_id)
        if res and res.blocked:
            return res
    return GuardResult("allow")


ROUTES = [
    ("approve_request", r"\b(approve|approval|authori[sz]e)\b"),
    ("change_threshold", r"\b(threshold|min_\w+|lower the bar|raise the bar|change the (gate|target))\b"),
    ("rerun_step", r"\b(re-?run|run (it |this )?again|retry|repeat (the )?step|research variant)\b"),
    ("explain_decision", r"\b(why|explain|reason|evidence|how did you|what did you find|summar\w+)\b"),
    ("edit_copy", r"\b(rewrite|reword|edit|headline|tagline|hero|copy|wording)\b"),
    ("evaluate_brief", r"\b(evaluate|assess|validate|analy[sz]e|check) (this|my|the|a)\b|\b(idea|brief)\s*:"),
]


def route_intent(text: str) -> str:
    t = (text or "").lower()
    for intent, pattern in ROUTES:
        if re.search(pattern, t):
            return intent
    return "other"
