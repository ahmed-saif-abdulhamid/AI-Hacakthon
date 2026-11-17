"""Intake agent: founder brief -> FounderBrief. Labelled briefs are parsed by code; free
text goes to the model. Missing fields become "ASSUMPTION: unspecified"."""

from __future__ import annotations

import re

from pydantic import BaseModel

from proveit import llm
from proveit.log import log_action
from proveit.models import UNSPECIFIED, FounderBrief

LABELS = {
    "idea": r"(starting )?idea",
    "skills": r"(founder'?s? )?skills?",
    "budget": r"budget",
    "hours_per_week": r"(available )?(time|hours?)( ?(/|per) ?week)?",
    "target_market": r"target( market)?|market|region",
    "values": r"(core )?values",
}
MAX_BRIEF_CHARS = 3000  # what the model sees of a free-text brief
ARABIC_SCRIPT = re.compile(r"[؀-ۿ]")
ARABIC_MARKETS = r"\b(egypt|cairo|alexandria|saudi|riyadh|jeddah|uae|dubai|abu dhabi|jordan|morocco|algeria|tunisia|kuwait|qatar|oman|bahrain|lebanon|iraq|arab\w*|mena)\b"


class IntakeOut(BaseModel):
    idea: str
    skills: str
    budget: str
    hours_per_week: str
    target_market: str
    values: str
    language: str


def parse_brief(text: str) -> dict:
    """Parse 'Label: value' lines (plain or markdown) into brief fields."""
    out = {}
    for line in (text or "").splitlines():
        line = re.sub(r"^[\s>*\-#]+", "", line).replace("**", "").strip()
        m = re.match(r"([A-Za-z' /]+?)\s*[:\-–]\s+(.+)$", line)
        if not m:
            continue
        label, value = m.group(1).strip().lower(), m.group(2).strip()
        for field, pattern in LABELS.items():
            if field not in out and re.fullmatch(pattern, label):
                out[field] = value
                break
    return out


def detect_language(brief: dict, text: str) -> str:
    """ "ar" for a brief in Arabic script or aimed at an Arab market, otherwise "en"."""
    if ARABIC_SCRIPT.search(text or ""):
        return "ar"
    if re.search(ARABIC_MARKETS, brief.get("target_market", "") or "", re.I) and re.search(
        r"\barab", (brief.get("target_market", "") + " " + text).lower()
    ):
        return "ar"
    return "en"


def run(run_id: str, text: str, fields: dict | None = None) -> FounderBrief:
    """The brief from labelled lines and form fields by code; free text without an idea line goes to the model."""
    parsed = parse_brief(text)
    for k, v in (fields or {}).items():
        if v and str(v).strip():
            parsed[k] = str(v).strip()
    if parsed.get("idea"):
        brief = {k: parsed.get(k) or UNSPECIFIED for k in LABELS}
        brief["language"] = detect_language(brief, text)
        log_action(
            run_id,
            "intake",
            "parse_brief",
            model=None,
            cost=0,
            fields_unspecified=[k for k, v in brief.items() if v == UNSPECIFIED],
        )
        return FounderBrief(**brief)
    out = llm.agent_call(
        run_id, "intake", "structure_brief", IntakeOut, f"BRIEF:\n{text[:MAX_BRIEF_CHARS]}", num_predict=300
    )
    data = out.model_dump()
    for k in LABELS:
        v = (data.get(k) or "").strip()
        data[k] = v if v and "unspecified" not in v.lower() else UNSPECIFIED
    data["language"] = data.get("language") if data.get("language") in ("en", "ar") else detect_language(data, text)
    return FounderBrief(**data)
