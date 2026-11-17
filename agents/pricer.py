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
DEFAULT_TIERS = (19.0, 39.0, 79.0)


class PricingOut(BaseModel):
    rationale: list[Statement] = Field(min_length=1, max_length=3)


def price_points(claims: list[Claim]) -> list[tuple[float, str]]:
    pts, seen = [], set()
    for c in claims:
        if c.weight > 0 and c.kind in ("price_point", "wtp") and c.quote:
            for m in PRICE.finditer(c.quote):
                v = float(m.group(1))
                if 1 <= v <= 2000 and (c.url, v) not in seen:   # one source sentence counts once
                    seen.add((c.url, v))
                    pts.append((v, c.id))
    return pts


def tiers(claims: list[Claim]) -> dict:
    pts = price_points(claims)
    if len(pts) < 2:
        return {"basis": "ASSUMPTION", "points": pts, "good": DEFAULT_TIERS[0], "better": DEFAULT_TIERS[1],
                "best": DEFAULT_TIERS[2],
                "note": f"Only {len(pts)} verified price point(s); tiers are an illustrative ASSUMPTION."}
    vals = sorted(v for v, _ in pts)
    q = statistics.quantiles(vals, n=4) if len(vals) >= 3 else [vals[0], statistics.median(vals), vals[-1]]
    r = lambda x: float(max(5, round(x)))  # noqa: E731
    return {"basis": "verified_price_points", "points": pts, "good": r(q[0]), "better": r(q[1]),
            "best": r(q[2]), "median": statistics.median(vals),
            "note": "Tiers at the lower quartile, median and upper quartile of verified price points."}


def rationale(run_id: str, claims: list[Claim], t: dict) -> list[Statement]:
    rel = [c for c in claims if c.kind in ("price_point", "competitor", "wtp") and c.weight > 0]
    user = (f"TIERS: good={t['good']} better={t['better']} best={t['best']} basis={t['basis']}\n"
            f"CLAIMS:\n{claims_table(rel, 10)}")
    return llm.agent_call(run_id, "pricer", "pricing_rationale", PricingOut, user, num_predict=260,
                          sources=sorted({c.url for c in rel if c.url})).rationale
