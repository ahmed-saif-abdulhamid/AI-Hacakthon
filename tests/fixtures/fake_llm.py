"""FAKE LLM for CI smoke tests ONLY. Every real run uses the open-weight model.

It answers each agent deterministically from the prompt it receives, so the tests
exercise the real orchestrator, verifier, gates, render and approval code.
"""

from __future__ import annotations

import json
import re

PAIN = re.compile(r"tedious|waste|nightmare|hate|manual|frustrat|wish", re.I)
WTP = re.compile(r"paid|\$\d", re.I)


def _variants(user: str) -> list[dict]:
    weak = "wallpaper" in user.lower()
    if weak:
        base = {
            "title": "Motivational lock screen wallpapers",
            "segment": "smartphone users who like motivational quotes",
            "job_to_be_done": "decorate phone lock screen wallpapers with motivational quotes",
            "pain_queries": ["motivational quote wallpapers", "lock screen quotes", "phone wallpaper quotes"],
            "competitor_query": "quote wallpaper",
            "se_site": "android",
            "language": "en",
        }
    else:
        base = {
            "title": "Client onboarding toolkit",
            "segment": "freelance web designers",
            "job_to_be_done": "onboard new clients and collect project content",
            "pain_queries": ["client onboarding process", "chasing clients for content", "client intake form"],
            "competitor_query": "client onboarding",
            "se_site": "freelancing",
            "language": "en",
        }
    v2 = dict(base, title=base["title"] + " (agencies)", segment="small design agencies")
    v3 = dict(base, title=base["title"] + " (course)", job_to_be_done="learn a repeatable process")
    return [base, v2, v3]


def _researcher(user: str) -> dict:
    claims, hit = [], None
    for line in user.splitlines():
        m = re.match(r"^(H\d+) \[", line)
        if m:
            hit = m.group(1)
            continue
        m = re.match(r"^\s+S(\d+): (.*)$", line)
        if m and hit:
            sid, text = int(m.group(1)), m.group(2)
            if re.search(r"per month|cost \$", text):
                kind = "price_point"
            elif WTP.search(text):
                kind = "wtp"
            elif PAIN.search(text):
                kind = "pain"
            elif re.search(r"Dubsado|HoneyBook|tools? that", text):
                kind = "competitor"
            else:
                continue
            claims.append({"hit_id": hit, "sentence_ids": [sid], "kind": kind, "claim_text": text[:60]})
    return {"claims": claims}


def _claim_lines(user: str) -> list[tuple[str, float, str]]:
    out = []
    for m in re.finditer(r"^(C\d+) kind=\S+ weight=([\d.]+) status=\S+ quote=\"(.*)\"$", user, re.M):
        out.append((m.group(1), float(m.group(2)), m.group(3)))
    return out


def _statements(user: str, n: int = 2) -> list[dict]:
    lines = [c for c in _claim_lines(user) if c[1] > 0][:n]
    sts = [{"text": " ".join(q.split()[:14]), "claim_ids": [cid]} for cid, _, q in lines]
    sts.append({"text": "Interviews are still needed to confirm demand.", "claim_ids": []})
    return sts[:3]


def backend(system: str, user: str, schema: dict, agent: str) -> str:
    if agent == "guard":
        return json.dumps({"violates": False, "rule": "none"})
    if agent == "intake":
        return json.dumps(
            {
                "idea": "test idea",
                "skills": "ASSUMPTION: unspecified",
                "budget": "ASSUMPTION: unspecified",
                "hours_per_week": "ASSUMPTION: unspecified",
                "target_market": "ASSUMPTION: unspecified",
                "values": "ASSUMPTION: unspecified",
                "language": "en",
            }
        )
    if agent == "scout":
        return json.dumps({"variants": _variants(user)})
    if agent == "researcher":
        return json.dumps(_researcher(user))
    if agent in ("advocate", "skeptic"):
        return json.dumps({"statements": _statements(user)})
    if agent == "strategist" and "MODE: canvas" in user:
        sts = _statements(user, 1)
        cell = sts[:1]
        data = {
            k: cell
            for k in (
                "problem",
                "customer_segments",
                "unique_value_proposition",
                "solution",
                "channels",
                "revenue_streams",
                "cost_structure",
                "key_metrics",
                "unfair_advantage",
            )
        }
        data["channels"] = [{"text": "Share the toolkit in freelance design communities.", "claim_ids": []}]
        data["riskiest_assumption"] = {
            "text": "Designers will pay for a toolkit instead of free templates.",
            "claim_ids": [],
        }
        data["experiment"] = {"text": "Run a waitlist landing page for 14 days.", "claim_ids": []}
        return json.dumps(data)
    if agent == "strategist":
        return json.dumps(
            {
                "headline": "Onboard clients without the chaos",
                "subheadline": "Checklists and templates for your next client.",
                "benefits": [
                    "An intake questionnaire you can copy",
                    "A content-collection checklist",
                    "A kickoff template",
                ],
                "faq": [{"q": "What format is it?", "a": "Markdown and CSV files."}],
            }
        )
    if agent == "builder" and "MODE: spec" in user:
        return json.dumps(
            {
                "title": "Client Onboarding Toolkit",
                "audience": "Freelance web designers.",
                "modules": [
                    {"name": "Intake", "purpose": "Collect project details"},
                    {"name": "Content", "purpose": "Collect content"},
                ],
                "not_included": ["Legal contracts", "Payment processing", "Project management software"],
            }
        )
    if agent == "builder":
        return json.dumps(
            {
                "title": "Client intake",
                "intro": "Use this checklist for each new client. It keeps the first week organised and calm for you and the client.",
                "steps": [
                    "Send the welcome email",
                    "Share the intake questionnaire",
                    "Schedule the kickoff call",
                    "Collect logins securely",
                    "Confirm the content deadline",
                    "Create the project folder",
                    "Review the brief with the client",
                    "Record decisions in the tracker",
                ],
                "template_columns": ["Client", "Item", "Owner", "Due", "Status"],
                "template_rows": [["Client name", "Logo files", "Client", "Day 3", "Open"]],
            }
        )
    if agent == "pricer":
        return json.dumps({"rationale": [{"text": "Prices sit near the verified price points.", "claim_ids": []}]})
    if agent == "policy_drafter":
        return json.dumps(
            {
                "terms": ["You may use the files in your own client work.", "You may not resell the files."],
                "privacy": ["We store your email and a timestamp.", "We never store card numbers."],
                "refunds": ["Ask for a refund within 14 days by email.", "The founder reviews every refund."],
            }
        )
    if agent == "launcher" and "MODE: store" in user:
        return json.dumps(
            {
                "product_name": "Client Onboarding Toolkit",
                "tagline": "Checklists and templates for new clients",
                "description": "A set of checklists and templates for onboarding web design clients.",
                "includes": ["Intake questionnaire", "Content checklist"],
                "who_it_is_for": "Freelance web designers.",
                "who_it_is_not_for": "Large agencies with a project management team.",
            }
        )
    if agent == "launcher":
        return json.dumps(
            {
                "title": "I built a client onboarding toolkit",
                "body": "I made the checklists I use with my own clients into a toolkit. Feedback welcome.",
            }
        )
    if agent == "assistant":
        return "Gate 1 stopped this run. The weighted pain signals were below the threshold. Ask me about the quotes."
    raise AssertionError(f"fake LLM has no answer for agent {agent}")
