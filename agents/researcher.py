"""Researcher agent: sees numbered sentences, returns only IDs. Code builds every quote."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from proveit import llm
from proveit.models import Hit, Variant


class ExtractedClaim(BaseModel):
    hit_id: str
    sentence_ids: list[int] = Field(min_length=1, max_length=3)
    kind: Literal["pain", "wtp", "competitor", "price_point", "market_size", "trend"]
    claim_text: str


class ResearcherOut(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list, max_length=20)


def numbered_block(hits: list[Hit], shown_ids: dict[str, list[int]]) -> str:
    lines = []
    for h in hits:
        date = h.published_at.date().isoformat() if h.published_at else "undated"
        lines.append(f"{h.id} [{h.source}, {date}] {h.title[:80]}")
        for i in shown_ids[h.id]:
            lines.append(f"  S{i}: {h.sentences[i - 1][:400]}")
    return "\n".join(lines)


BATCH = 7  # threads per call (a 4B model needed 4; the hosted 550B model handles 7 reliably)


def run(run_id: str, variant: Variant, hits: list[Hit], shown_ids: dict[str, list[int]]) -> list[dict]:
    items: list[dict] = []
    for i in range(0, len(hits), BATCH):
        items += _run_batch(run_id, variant, hits[i : i + BATCH], shown_ids)
    return items


def _run_batch(run_id: str, variant: Variant, hits: list[Hit], shown_ids: dict[str, list[int]]) -> list[dict]:
    user = (
        f"VARIANT: {variant.title}\nSEGMENT: {variant.segment}\nJOB TO BE DONE: {variant.job_to_be_done}\n\n"
        f"NUMBERED SENTENCES:\n{numbered_block(hits, shown_ids)}\n\n"
        "Return the claims as JSON. Use only the hit IDs and sentence numbers shown above."
    )
    out = llm.agent_call(
        run_id, "researcher", "extract_claims", ResearcherOut, user, num_predict=1200, sources=[h.url for h in hits]
    )
    allowed = {h.id: set(shown_ids[h.id]) for h in hits}
    items = []
    for c in out.claims:
        ids = [i for i in c.sentence_ids if i in allowed.get(c.hit_id, set())]
        if ids:
            items.append({"hit_id": c.hit_id, "sentence_ids": ids, "kind": c.kind, "claim_text": c.claim_text})
    return items
