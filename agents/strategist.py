"""Strategist: Lean Canvas + riskiest assumption + experiment, and landing-page copy fields.
Every canvas cell is a list of Statements; render.py cites or labels each one."""

from __future__ import annotations

from pydantic import BaseModel, Field

from proveit import llm
from proveit.models import Claim, FounderBrief, Statement, Variant

from .debate import claims_table

CELLS = (
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


class CanvasOut(BaseModel):
    problem: list[Statement] = Field(min_length=1, max_length=2)
    customer_segments: list[Statement] = Field(min_length=1, max_length=2)
    unique_value_proposition: list[Statement] = Field(min_length=1, max_length=2)
    solution: list[Statement] = Field(min_length=1, max_length=2)
    channels: list[Statement] = Field(min_length=1, max_length=2)
    revenue_streams: list[Statement] = Field(min_length=1, max_length=2)
    cost_structure: list[Statement] = Field(min_length=1, max_length=2)
    key_metrics: list[Statement] = Field(min_length=1, max_length=2)
    unfair_advantage: list[Statement] = Field(min_length=1, max_length=2)
    riskiest_assumption: Statement
    experiment: Statement


class FAQ(BaseModel):
    q: str
    a: str


class LandingOut(BaseModel):
    headline: str
    subheadline: str
    benefits: list[str] = Field(min_length=3, max_length=3)
    faq: list[FAQ] = Field(min_length=1, max_length=3)


def canvas(run_id: str, brief: FounderBrief, variant: Variant, claims: list[Claim]) -> CanvasOut:
    counted = [c for c in claims if c.weight > 0]
    user = (
        f"MODE: canvas\nVARIANT: {variant.title}\nSEGMENT: {variant.segment}\nJOB: {variant.job_to_be_done}\n"
        f"FOUNDER SKILLS: {brief.skills}\nBUDGET: {brief.budget}\nCLAIMS:\n{claims_table(counted, 12)}"
    )
    return llm.agent_call(
        run_id,
        "strategist",
        "lean_canvas",
        CanvasOut,
        user,
        num_predict=1100,
        sources=sorted({c.url for c in counted if c.url}),
    )


def landing(run_id: str, variant: Variant, feedback: str = "") -> LandingOut:
    user = f"MODE: landing\nPRODUCT: {variant.title}\nFOR: {variant.segment}\nJOB: {variant.job_to_be_done}\n" + (
        f"PREVIOUS DRAFT WAS BLOCKED: {feedback}. Remove that content.\n" if feedback else ""
    )
    return llm.agent_call(run_id, "strategist", "landing_copy", LandingOut, user, num_predict=450)
