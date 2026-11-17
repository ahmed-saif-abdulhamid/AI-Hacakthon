"""Analyst and support (Phase 6: operate and learn). Code only, from real records.

- ``support_faq``: draft answers to the questions buyers ask most, built only from facts the
  run already approved (user docs, price, policies, delivery). Drafts for the founder:
  nothing is sent (email sending is STUBBED and gated).
- ``metrics_plan``: what is tracked, where it is read from, and the pre-registered bar.
- ``decide``: persevere / pivot / stop / not enough data, by rule, from real records only.
  MOCKED test orders and test sign-ups never count.
- ``memo``: the persevere-or-pivot memo with that decision.
"""
from __future__ import annotations

STATUS = "STUBBED"   # no live product, so every real-record count is 0 in the demo


def support_faq(product: dict, pricing: dict, policies_md: str, docs_md: str) -> str:
    title = product.get("title", "the toolkit")
    modules = product.get("modules", [])
    tiers = [f"${pricing[k]:.0f}" for k in ("good", "better", "best") if isinstance(pricing.get(k), (int, float))]
    refund = next((ln.strip("- ").strip() for ln in policies_md.splitlines() if "Refund window" in ln), None)
    not_do = []
    if "does not do" in docs_md:
        tail = docs_md.split("does not do", 1)[1].split("\n## ", 1)[0]
        not_do = [ln[2:].strip() for ln in tail.splitlines() if ln.startswith("- ")]
    qa = [
        ("What do I get?",
         f"{title} contains {len(modules)} parts: " + "; ".join(modules) + ". Each part has a checklist and a CSV template.",
         "phase3_step3_user-docs.md"),
        ("How do I receive it?",
         "Right after payment you get a download link. The link is signed and expires after 24 hours; "
         "if it expires, reply with your order number and the founder sends a new one.",
         "payment_test_log.md (delivery is MOCKED in this demo)"),
        ("What does it cost?",
         ("Three options: " + ", ".join(tiers) + ". The price is shown on the store page before you pay.") if tiers
         else "The price is shown on the store page before you pay.",
         "phase4_step1_pricing.md"),
        ("Can I get a refund?",
         (refund + ". " if refund else "") + "Send your order number; the founder reviews and approves every refund, "
         "and your download link stops working once it is refunded.",
         "phase4_step2_policies.md"),
    ]
    if not_do:
        qa.append(("Does it do X for me automatically?",
                   "No. It does not include: " + "; ".join(not_do) + ".", "phase3_step3_user-docs.md"))
    qa.append(("Who answers support?",
               "The founder, by email. Replies are drafted here and sent only after the founder approves them.",
               "phase4_step2_policies.md"))
    lines = ["# Phase 6, step 2: Support answers (drafts)", "",
             "Drafted by code only from files this run already produced and the founder approved. "
             "**Nothing is sent:** email sending is STUBBED, and every reply needs the founder's approval.", "",
             "| Question | Draft answer | Built from |", "|---|---|---|"]
    lines += [f"| {q} | {a} | {src} |" for q, a, src in qa]
    return "\n".join(lines) + "\n"


def _rows(m: dict, th: dict) -> list[tuple]:
    g2, g6 = th["gate2_demand"], th["gate6_operate"]
    orders = m.get("real_orders", 0)
    rate = (m.get("real_refunds", 0) / orders) if orders else None
    visits = m.get("real_visits", 0)
    conv = (m.get("real_signups", 0) / visits) if visits else None
    return [
        ("Real waitlist sign-ups", m.get("real_signups", 0), f">= {g2['waitlist_target']} in {g2['window_days']} days",
         "signups table, test=false", "gates.yaml gate2_demand"),
        ("Landing-page conversion", "n/a" if conv is None else f"{conv:.0%}",
         f">= {g2['min_conversion']:.0%} after {g2['min_visits_for_rate']} visits", "visits and signups, test=false",
         "gates.yaml gate2_demand"),
        ("Real orders", orders, f">= {g6['min_real_orders']} in {g6['window_days']} days", "orders table, test=false",
         "gates.yaml gate6_operate (ASSUMPTION)"),
        ("Refund rate", "n/a" if rate is None else f"{rate:.0%}", f"<= {g6['max_refund_rate']:.0%}",
         "refunds joined to real orders", "gates.yaml gate6_operate (ASSUMPTION)"),
        ("Test orders (never counted)", m.get("test_orders", 0), "-", "MOCKED payment test", "-"),
    ]


def metrics_plan(m: dict, th: dict) -> str:
    lines = ["# Phase 6, step 3: Metrics plan", "",
             "What the analyst reads after launch, where each number comes from, and the bar it is held to. "
             "Every bar is in config/gates.yaml, hashed with the brief before the run started.", "",
             "| Metric | Now | Bar | Read from | Bar set in |", "|---|---|---|---|---|"]
    lines += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in _rows(m, th)]
    g6 = th["gate6_operate"]
    lines += ["", "## Decision rule (code, first match wins)", "",
              f"1. Fewer than {g6['window_days']} days since launch, or no real orders and sign-ups under target: "
              "**not enough data** (REPEAT: keep collecting, change nothing).",
              f"2. Real orders >= {g6['min_real_orders']} and refund rate <= {g6['max_refund_rate']:.0%}: **persevere** (GO).",
              "3. Real orders >= the bar but refund rate above it: **pivot** the product (the buyers came, the "
              "product did not keep them); return to Phase 3.",
              f"4. After the window, real sign-ups under {g6['stop_below_share']:.0%} of the waitlist target and "
              "no real orders: **stop**.", ""]
    return "\n".join(lines)


def decide(m: dict, th: dict) -> tuple[str, str]:
    """(outcome, reason) with outcome in go / repeat / pivot / stop."""
    g2, g6 = th["gate2_demand"], th["gate6_operate"]
    orders, days = m.get("real_orders", 0), m.get("days_since_launch", 0)
    rate = (m.get("real_refunds", 0) / orders) if orders else 0.0
    if orders >= g6["min_real_orders"]:
        if rate <= g6["max_refund_rate"]:
            return "go", "persevere: real orders and refund rate meet the bar"
        return "pivot", "pivot the product: buyers came but the refund rate is above the bar"
    if days >= g6["window_days"] and m.get("real_signups", 0) < g6["stop_below_share"] * g2["waitlist_target"]:
        return "stop", "stop: after the window, real demand is far under the pre-registered target"
    return "repeat", "not enough data: no live launch yet, so there are no real sign-ups or orders"


def memo(metrics: dict, thresholds: dict) -> str:
    outcome, reason = decide(metrics, thresholds)
    lines = ["# Phase 6, step 1: Persevere-or-pivot memo (STUBBED: no live launch)", "",
             "Real records only. MOCKED test orders and test sign-ups are excluded.", "",
             "| Metric | Now | Bar |", "|---|---|---|"]
    lines += [f"| {a} | {b} | {c} |" for a, b, c, *_ in _rows(metrics, thresholds)]
    lines += ["", f"## Outcome: {outcome.upper()}", "", f"**{reason[0].upper() + reason[1:]}.**", "",
              "The rule that decided this is in phase6_step3_metrics.md. Nothing here is a forecast."]
    if outcome == "repeat":
        lines.append("With no real buyers yet, the honest answer is to keep collecting and change nothing.")
    lines.append("")
    return "\n".join(lines)
