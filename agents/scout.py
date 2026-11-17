"""Scout agent: 3 researchable variants (segment, job, pain-phrased queries, SE site, language)."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from proveit import llm
from proveit.models import FounderBrief, Variant

SE_SITES = {"stackoverflow", "superuser", "webapps", "workplace", "freelancing", "ux", "graphicdesign",
            "softwareengineering", "pm", "academia", "writers", "webmasters", "softwarerecs", "photo",
            "english", "interpersonal"}


class VariantOut(BaseModel):
    title: str
    segment: str
    job_to_be_done: str
    pain_queries: list[str] = Field(min_length=1, max_length=4)
    competitor_query: str
    se_site: str
    language: str


class ScoutOut(BaseModel):
    variants: list[VariantOut] = Field(min_length=1, max_length=3)


def _clean_query(q: str) -> str:
    q = re.sub(r"[\"'()\[\]]", " ", q or "")
    return " ".join(q.lower().split()[:4])


def run(run_id: str, brief: FounderBrief) -> list[Variant]:
    user = (f"IDEA: {brief.idea}\nFOUNDER SKILLS: {brief.skills}\nTARGET MARKET: {brief.target_market}\n"
            f"VALUES: {brief.values}\nLANGUAGE: {brief.language}\nReturn exactly 3 variants.")
    out = llm.agent_call(run_id, "scout", "find_opportunities", ScoutOut, user, num_predict=700)
    variants = []
    for n, v in enumerate(out.variants[:3], start=1):
        site = v.se_site.strip().lower().replace(".stackexchange.com", "")
        variants.append(Variant(
            n=n, title=v.title.strip(), segment=v.segment.strip(), job_to_be_done=v.job_to_be_done.strip(),
            pain_queries=[q for q in (_clean_query(x) for x in v.pain_queries) if q][:3],
            competitor_query=_clean_query(v.competitor_query) or _clean_query(v.job_to_be_done),
            se_site=site if site in SE_SITES else "softwareengineering",
            language=v.language if v.language in ("en", "ar") else brief.language))
    return variants
