"""Pricer: code computes tiers from verified price points; the model only writes a
cited rationale. With fewer than 2 verified price points every price is ASSUMPTION."""

from __future__ import annotations

import re
import statistics

from pydantic import BaseModel, Field

from proveit import llm
from proveit.models import Claim, Statement

from .debate import claims_table

PRICE = re.compile(r"[$€£]\s?(\d{1,5}(?:\.\d{1,2})?)")
PRICE_WORDING = re.compile(r"per month|/mo\b|/month|one.time", re.I)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
DEFAULT_TIERS = (19.0, 39.0, 79.0)
MIN_PRICE_POINTS = 2  # fewer verified price points than this: every tier is an ASSUMPTION
PLAUSIBLE_PRICE = (1, 2000)  # dollar amounts outside this range are not a product price
MIN_TIER_PRICE = 5
MAX_COMPETITORS_IN_RATIONALE = 3
RATIONALE_CLAIMS = 10


class PricingOut(BaseModel):
    rationale: list[Statement] = Field(min_length=1, max_length=3)


def price_points(claims: list[Claim]) -> list[tuple[float, str]]:
    """(price, claim ID) for every distinct dollar amount in counted price and payment quotes."""
    lo, hi = PLAUSIBLE_PRICE
    pts, seen = [], set()
    for c in claims:
        if c.weight > 0 and c.kind in ("price_point", "wtp") and c.quote:
            for m in PRICE.finditer(c.quote):
                v = float(m.group(1))
                if lo <= v <= hi and (c.url, v) not in seen:  # one source sentence counts once
                    seen.add((c.url, v))
                    pts.append((v, c.id))
    return pts


def _tier_price(x: float) -> float:
    return float(max(MIN_TIER_PRICE, round(x)))


def tiers(claims: list[Claim]) -> dict:
    """Good / better / best prices: quartiles of verified price points, or illustrative defaults."""
    pts = price_points(claims)
    if len(pts) < MIN_PRICE_POINTS:
        return {
            "basis": "ASSUMPTION",
            "points": pts,
            "good": DEFAULT_TIERS[0],
            "better": DEFAULT_TIERS[1],
            "best": DEFAULT_TIERS[2],
            "note": ("No verified price point was found" if not pts else "Only one verified price point was found")
            + "; the tiers are an illustrative ASSUMPTION.",
        }
    vals = sorted(v for v, _ in pts)
    q = statistics.quantiles(vals, n=4) if len(vals) >= 3 else [vals[0], statistics.median(vals), vals[-1]]
    return {
        "basis": "verified_price_points",
        "points": pts,
        "good": _tier_price(q[0]),
        "better": _tier_price(q[1]),
        "best": _tier_price(q[2]),
        "median": statistics.median(vals),
        "note": "Tiers at the lower quartile, median and upper quartile of verified price points.",
    }


def _price_sentence(c: Claim) -> Claim:
    """Only the sentence that states the price (a long quote about a tool's tech stack is not a price)."""
    parts = SENTENCE_BREAK.split(c.quote or "")
    hit = next((p for p in parts if PRICE.search(p) or PRICE_WORDING.search(p)), None)
    return c.model_copy(update={"quote": hit}) if hit else c


def rationale(run_id: str, claims: list[Claim], t: dict) -> list[Statement]:
    """The model's cited explanation of the tiers code computed (it never sets a price)."""
    rel = [_price_sentence(c) for c in claims if c.kind in ("price_point", "wtp") and c.weight > 0]
    rel += [c for c in claims if c.kind == "competitor" and c.weight > 0][:MAX_COMPETITORS_IN_RATIONALE]
    user = (
        f"TIERS: good={t['good']} better={t['better']} best={t['best']} basis={t['basis']}\n"
        f"CLAIMS:\n{claims_table(rel, RATIONALE_CLAIMS)}"
    )
    return llm.agent_call(
        run_id,
        "pricer",
        "pricing_rationale",
        PricingOut,
        user,
        num_predict=260,
        sources=sorted({c.url for c in rel if c.url}),
    ).rationale
