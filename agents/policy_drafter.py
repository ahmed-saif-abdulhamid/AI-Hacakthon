"""Policy drafter: terms, privacy and refund DRAFTS, never legal advice."""

from __future__ import annotations

from pydantic import BaseModel, Field

from proveit import llm

STAMP = "DRAFT - not legal advice; review with a qualified professional."


class PoliciesOut(BaseModel):
    terms: list[str] = Field(min_length=2, max_length=6)
    privacy: list[str] = Field(min_length=2, max_length=5)
    refunds: list[str] = Field(min_length=2, max_length=4)


def run(run_id: str, product_title: str) -> PoliciesOut:
    return llm.agent_call(
        run_id,
        "policy_drafter",
        "draft_policies",
        PoliciesOut,
        f"PRODUCT: {product_title} (a downloadable digital toolkit)",
        num_predict=600,
    )
