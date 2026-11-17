"""Pydantic data models shared by every agent, gate and renderer."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ClaimKind = Literal["pain", "wtp", "competitor", "price_point", "market_size", "trend"]
SourceName = Literal["hn", "stackexchange", "github", "web", "founder", "assumption"]
Outcome = Literal["go", "repeat", "pivot", "stop"]
GatedAction = Literal[
    "publish_landing_page",
    "open_store",
    "publish_post",
    "send_email",
    "refund",
    "spend",
    "sign",
    "create_account",
]
UNSPECIFIED = "ASSUMPTION: unspecified"


class FounderBrief(BaseModel):
    idea: str
    skills: str = UNSPECIFIED
    budget: str = UNSPECIFIED
    hours_per_week: str = UNSPECIFIED
    target_market: str = UNSPECIFIED
    values: str = UNSPECIFIED
    language: str = "en"


class Variant(BaseModel):
    n: int
    title: str
    segment: str
    job_to_be_done: str
    pain_queries: list[str] = Field(default_factory=list)
    competitor_query: str = ""
    se_site: str = "softwareengineering"
    language: str = "en"


class Hit(BaseModel):
    id: str  # H1..Hn, unique within a run
    source: SourceName
    url: str
    title: str = ""
    text: str = ""  # normalised record text
    sentences: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    engagement: int | None = None
    query: str = ""


class SourceCall(BaseModel):
    source: str
    query: str
    url: str
    ok: bool
    n_hits: int = 0
    n_on_topic: int = 0
    seconds: float = 0.0
    error: str | None = None
    pain_capable: bool = False


class Claim(BaseModel):
    id: str
    run_id: str
    kind: ClaimKind
    claim_text: str  # <= 15 words, never used by a gate
    quote: str | None  # built by code only
    url: str | None
    source: SourceName
    hit_id: str | None = None
    hit_title: str = ""  # title of the thread the quote comes from (topic context)
    sentence_ids: list[int] = Field(default_factory=list)
    fetched_at: datetime | None = None
    published_at: datetime | None = None
    engagement: int | None = None
    status: Literal["verified_live", "archived_match", "unverified"] = "unverified"
    weight: float = 0.0  # 1.0 / 0.5 / 0; 0 if the code cue disagrees
    cue_matched: str | None = None
    on_topic: bool = False
    keyword_overlap: list[str] = Field(default_factory=list)
    weight_note: str = ""
    label: Literal["SOURCED", "ASSUMPTION"] = "ASSUMPTION"


class Statement(BaseModel):
    text: str
    claim_ids: list[str] = Field(default_factory=list)


class GateDecision(BaseModel):
    run_id: str
    gate: str
    outcome: Outcome
    reason: str
    next_step: str | None = None
    metrics: dict = Field(default_factory=dict)
    thresholds: dict = Field(default_factory=dict)
    thresholds_sha256: str = ""
    goalpost_moved: bool = False
    failed_checks: list[str] = Field(default_factory=list)
    rule_fired: str = ""
    recommendation: str = ""
    founder_decision: Literal["pending", "accepted", "overridden", "stopped"] = "pending"
    override_reason: str | None = None


class Approval(BaseModel):
    id: str
    run_id: str
    action: GatedAction
    payload_sha256: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    decided_by: Literal["founder"] | None = None
    decided_at: datetime | None = None
    created_at: datetime | None = None
    note: str = ""
