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
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from rapidfuzz import fuzz

from . import llm
from .log import log_action

ROOT = Path(__file__).resolve().parent.parent
BRIEF_A_RULES = (
    "fake_social_proof",
    "fake_signups",
    "urgency",
    "income_promise",
    "impersonation",
    "credentials",
    "arabic_intent",
    "bypass",
)
UNAVAILABLE = "model_check_unavailable"

# Typo correction: tokens this long are fuzzy-matched against the rule words at this similarity.
TYPO_MIN_TOKEN_LENGTH = 6
TYPO_MIN_SIMILARITY = 85
# The model check sees at most this much text and answers in a few tokens.
MODEL_CHECK_MAX_CHARS = 2000
MODEL_CHECK_TOKENS = 40
# A brief whose model check could not run is checked once more after this pause, then the founder is asked.
MODEL_CHECK_RETRY_DELAY_SECONDS = 3
MAX_MATCH_CHARS = 80

# The model check names its rule in free text; map it to the same friendly refusal the rules use.
MODEL_RULE_KEYS = [
    (r"review|testimon|rating|endorse|quote", "fake_social_proof"),
    (r"sign-?up|traffic|follower|user|subscriber", "fake_signups"),
    (r"urgen|scarc|countdown|timer|deadline|limited", "urgency"),
    (r"income|earn|profit|result|guarant|forecast|revenue", "income_promise"),
    (r"imperson|pose|posing|voice|brand|pretend|as a customer|as the founder", "impersonation"),
    (r"password|card|credential|cvv|bank", "credentials"),
    (r"refund|spend|charge|transfer|money|pay", "money_action"),
    (r"account", "account_creation"),
    (r"approv|skip|bypass|jailbreak|ignore", "bypass"),
]
MODEL_CATEGORY_KEYS = [
    (r"physical|goods|merch|inventory", "physical_goods"),
    (r"financ|crypto|invest|trading|stock|loan|insurance", "financial_crypto"),
    (r"health|medic|supplement|diet|therap|diagnos", "health_advice"),
    (r"legal|law|immigration|tax", "legal_advice"),
]
# How each excluded category is named in a refusal: singular for a rule hit on one brief, plural for the model's.
CATEGORY_LABELS = {
    "arabic": "an excluded category",
    "physical_goods": "physical goods",
    "financial_crypto": "a financial or crypto product",
    "health_advice": "a health advice product",
    "legal_advice": "a legal advice product",
}
MODEL_CATEGORY_LABELS = {
    "physical_goods": "physical goods",
    "financial_crypto": "financial or crypto products",
    "health_advice": "health advice products",
    "legal_advice": "legal advice products",
}
COPY_REQUEST = re.compile(r"\b(say|says|add|put|include|claim|show|display)\b", re.I)


@dataclass
class GuardResult:
    verdict: str = "allow"  # allow | refuse | clarify | stop
    layer: str | None = None  # rules | model
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
        if len(tok) >= TYPO_MIN_TOKEN_LENGTH and tok.isalpha():
            low = tok.lower()
            best = max(keys, key=lambda k: fuzz.ratio(low, k))
            if low != best and fuzz.ratio(low, best) >= TYPO_MIN_SIMILARITY:
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
            hits.append((name, r, m.group(0)[:MAX_MATCH_CHARS]))
    if not hits:
        return None
    name, r, matched = hits[0]
    refusals = " ".join(h[1]["refusal"] for h in hits)
    return GuardResult(
        "refuse", "rules", name, f"{refusals} {r['alternative']}", matched=matched, notes=[h[0] for h in hits]
    )


def classify_brief(text: str) -> GuardResult:
    """Rule set B: excluded product categories (allow-list and an ask-the-founder tier)."""
    b = rules()["excluded_categories"]
    probe = rx(b["allow_list"]).sub(" ", _prep(text))
    if not rx(b["product_context"]).search(probe) and not re.search(r"[؀-ۿ]", probe):
        return GuardResult("allow")
    for cat, spec in b["categories"].items():
        m = rx(spec["pattern"]).search(probe)
        if m:
            label = CATEGORY_LABELS.get(cat, cat.replace("_", " "))
            return GuardResult(
                "stop",
                "rules",
                f"excluded_{cat}",
                f"This looks like {label}, which ProveIt can't help build. It works on digital "
                "products such as templates, guides, checklists or small tools that give no "
                "financial, medical or legal advice.",
                category=cat,
                matched=m.group(0),
            )
    m = rx(b["ask_tier"]).search(probe)
    if m:
        return GuardResult(
            "clarify",
            "rules",
            "ask_founder",
            f"The word '{m.group(0)}' can describe an excluded category. Please confirm the "
            "product is a digital product that gives no financial, medical or legal advice.",
            matched=m.group(0),
        )
    return GuardResult("allow")


class PolicyVerdict(BaseModel):
    violates: bool
    rule: str


POLICY_SYSTEM = (
    'You are a strict policy checker for a founder tool. Answer only JSON {"violates": bool, "rule": str}. '
    "violates=true if the TEXT asks for or contains: fake reviews/testimonials/ratings, fake sign-ups or "
    "traffic, countdown timers or false scarcity, promises of income or guaranteed results, impersonating "
    "a founder/customer/brand, storing passwords or card details, moving/refunding/spending money, creating "
    "accounts, skipping approvals, or building physical goods, financial/crypto, health or legal advice "
    "products. Paraphrases count: any claim that a product will replace a job, pay back its cost or change "
    "someone's income; any invented deadline, price rise or scarcity; writing as if you were a customer, user "
    "or independent person. Ordinary business questions, explanations and honest copy do NOT violate. "
    'rule = short name of the violated rule, or "none".'
)


def model_check(text: str, kind: str = "input", run_id: str | None = None, quick: bool = False) -> GuardResult | None:
    """C2: one short yes/no call. Returns None when the model is unavailable (logged by caller)."""
    try:
        v, meta = llm.chat_json(
            PolicyVerdict,
            POLICY_SYSTEM,
            f"KIND: {kind}\nTEXT:\n{text[:MODEL_CHECK_MAX_CHARS]}",
            run_id=run_id,
            agent="guard",
            num_predict=MODEL_CHECK_TOKENS,
            quick=quick,
        )
    except llm.LLMError as e:
        if run_id:
            log_action(
                run_id, "guard", "model_policy_check_unavailable", model=llm.model_name(), cost=0, error=str(e)[:120]
            )
        return None
    if run_id:
        log_action(
            run_id,
            "guard",
            "model_policy_check",
            model=meta["model"],
            cost=0,
            kind=kind,
            violates=v.violates,
            tokens_in=meta["tokens_in"],
            tokens_out=meta["tokens_out"],
            seconds=meta["seconds"],
        )
    if v.violates:
        return model_refusal(v.rule, kind)
    return GuardResult("allow", "model")


def model_refusal(rule: str, kind: str = "input") -> GuardResult:
    """Turn the model's free-text rule name into the same specific, friendly refusal the rules give."""
    low = (rule or "").lower()
    for pat, cat in MODEL_CATEGORY_KEYS:
        if re.search(pat, low):
            msg = (
                f"This looks like {MODEL_CATEGORY_LABELS[cat]}, which ProveIt can't help build. It works on digital "
                "products such as templates, guides and checklists that give no financial, medical or legal advice."
            )
            return GuardResult("stop" if kind == "brief" else "refuse", "model", f"excluded_{cat}", msg, category=cat)
    for pat, key in MODEL_RULE_KEYS:
        if re.search(pat, low):
            r = rules()["input_intent"][key]
            return GuardResult("refuse", "model", key, f"{r['refusal']} {r['alternative']}", notes=[key])
    return GuardResult(
        "refuse",
        "model",
        f"model:{low[:40]}",
        "I can't help with that one, because it could mislead people or skip your approval. "
        "I can help with honest, sourced work instead.",
    )


def check_input(text: str, scope: str = "ask", use_model: bool = True, run_id: str | None = None) -> GuardResult:
    """Rule set A (+ B for briefs), then the model check for ask/override scopes."""
    if scope == "brief":
        return _check_brief(text, use_model, run_id)
    return _check_request(text, scope, use_model, run_id)


def _check_brief(text: str, use_model: bool, run_id: str | None) -> GuardResult:
    """A founder brief: the generation-intent rules, excluded categories, then the model (fail closed)."""
    hit = _match_a(text, BRIEF_A_RULES)
    if hit:
        return hit
    b = classify_brief(text)
    if b.verdict != "allow":
        return b
    if not use_model:
        return GuardResult("allow")
    res = model_check(text, "brief", run_id)
    if res is None:  # fail closed: one retry, then ask the founder
        time.sleep(MODEL_CHECK_RETRY_DELAY_SECONDS)
        res = model_check(text, "brief", run_id)
    if res is None:
        return GuardResult(
            "clarify",
            "model",
            UNAVAILABLE,
            "I couldn't run my safety check just now because the AI service is busy. Please "
            "confirm this is a digital product that gives no financial, medical or legal "
            "advice, and I'll carry on.",
        )
    return res


def _check_request(text: str, scope: str, use_model: bool, run_id: str | None) -> GuardResult:
    """An ask or override message: every A rule, outward-copy rules for copy requests, then the model."""
    hit = _match_a(text)
    if hit:
        return hit
    # A request to put content into copy ("make the hero say loved by 2,000 founders") is
    # checked against rule set C before any copywriter sees it.
    if route_intent(text) == "edit_copy" or COPY_REQUEST.search(text or ""):
        out = check_output(text, "outward")
        if out.blocked:
            out.message = (
                "I can't put social proof, ratings, urgency or income claims into the copy. "
                "I can rewrite it to describe what the product contains, for your approval."
            )
            out.rule = "input_" + (out.rule or "")
            return out
    if not use_model:
        return GuardResult("allow")
    res = model_check(text, scope, run_id)
    if res is None:
        # Fail closed for generation: the caller answers only from recorded data (no model writing).
        return GuardResult("allow", notes=[UNAVAILABLE])
    return res


def check_output(
    text: str, artifact_type: str = "outward", use_model: bool = False, run_id: str | None = None
) -> GuardResult:
    """Rule set C on outward copy. Analysis artifacts and verbatim quotes are exempt by type."""
    if artifact_type in ("analysis", "quote"):
        return GuardResult("allow", notes=[f"{artifact_type}: exempt from rule set C"])
    skip = set(rules()["money_rule_names"]) if artifact_type == "policy" else set()
    for name, pattern in rules()["output_copy"].items():
        if name in skip:
            continue
        m = rx(pattern).search(text or "")
        if m:
            return GuardResult(
                "refuse",
                "rules",
                f"output_{name}",
                f"Outward copy blocked ({name.replace('_', ' ')}): '{m.group(0)[:60]}'.",
                matched=m.group(0)[:MAX_MATCH_CHARS],
            )
    if use_model:
        res = model_check(text, f"outward copy ({artifact_type})", run_id)
        if res and res.blocked:
            return res
    return GuardResult("allow")


ROUTES = [
    # Commands only: questions such as "what did I approve?" or "what is the threshold?" go to the model.
    (
        "approve_request",
        r"^\s*(please\s+)?(approve|authori[sz]e)\b|\b(can|could|would) you\s+(please\s+)?(approve|authori[sz]e)\b"
        r"|\b(go ahead and|just|please)\s+(approve|authori[sz]e)\b|\bapprove (it|this|that|the|my|our)\b(?!.*\?\s*$)",
    ),
    (
        "change_threshold",
        r"\b(lower|raise|reduce|change|move|relax|loosen|drop|tweak|adjust)\b\W+(\w+\W+){0,3}?"
        r"(bar|threshold|target|rules?)\b|\bcount (it|this) as a pass\b"
        r"|\b(treat|count|consider|call)\b\W+(\w+\W+){0,4}?as\W+(\w+\W+){0,2}?(go|a pass|enough|six|6)\b",
    ),
    ("rerun_step", r"\b(re-?run|run (it |this )?again|retry|repeat (the )?step|research variant)\b"),
    ("explain_decision", r"\b(why|explain|reason|evidence|how did you|what did you find|summar\w+)\b"),
    ("edit_copy", r"\b(rewrite|reword|edit|headline|tagline|hero|copy|wording)\b"),
    (
        "evaluate_brief",
        r"\b(evaluate|assess|validate|analy[sz]e|check|test) (this|my|a|the|an|new) "
        r"(new |business |product |startup )?(idea|brief|concept)\b|\b(idea|brief)\s*:",
    ),
]


def route_intent(text: str) -> str:
    """The first route whose pattern matches (see ROUTES), or "other"."""
    t = (text or "").lower()
    for intent, pattern in ROUTES:
        if re.search(pattern, t):
            return intent
    return "other"
