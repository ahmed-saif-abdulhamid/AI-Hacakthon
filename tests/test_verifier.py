"""Quotes are cut by code from sentence IDs, re-checked live, and weighted by code."""
from __future__ import annotations

from datetime import datetime, timezone

from proveit import verifier
from proveit.models import Hit, Variant
from sources.base import normalize, split_sentences

V = Variant(n=1, title="t", segment="freelance web designers", job_to_be_done="onboard new clients and collect content")
TEXT = ("Onboarding new clients is tedious for freelance web designers. I use email. "
        "Collecting content from clients is a nightmare. Unrelated: I wish my compiler was faster.")


def make_hit():
    return Hit(id="H1", source="hn", url="https://news.ycombinator.com/item?id=1", text=TEXT,
               sentences=split_sentences(TEXT), published_at=datetime.now(timezone.utc))


def test_normalize_html_and_quotes():
    assert normalize("<p>It&#x27;s “broken”</p>  <i>now</i>") == "It's \"broken\" now"


def test_quote_built_by_code_is_verbatim_and_contiguous():
    h = make_hit()
    q, ids = verifier.build_quote(h, [1, 3])
    assert ids == [1] and q == h.sentences[0]
    q, ids = verifier.build_quote(h, [2, 3])
    assert q == h.sentences[1] + " " + h.sentences[2] and q in TEXT


def test_invalid_ids_give_unverified_assumption():
    claims = verifier.build_claims("r", {"H1": make_hit()}, [{"hit_id": "H9", "sentence_ids": [1], "kind": "pain",
                                                              "claim_text": "x"}])
    assert claims[0].status == "unverified" and claims[0].label == "ASSUMPTION" and claims[0].weight == 0


def test_live_and_archived_status_and_relevance():
    h = make_hit()
    items = [{"hit_id": "H1", "sentence_ids": [1], "kind": "pain", "claim_text": "a"},
             {"hit_id": "H1", "sentence_ids": [3], "kind": "pain", "claim_text": "b"},
             {"hit_id": "H1", "sentence_ids": [4], "kind": "pain", "claim_text": "off topic"},
             {"hit_id": "H1", "sentence_ids": [2], "kind": "pain", "claim_text": "no cue"}]
    claims = verifier.build_claims("r", {"H1": h}, items)
    page = normalize(h.sentences[0])          # live page holds only the first sentence
    verifier.verify_live(claims, fetcher=lambda u: page)
    verifier.apply_relevance(claims, V)
    c1, c2, c3, c4 = claims
    assert (c1.status, c1.weight, c1.cue_matched) == ("verified_live", 1.0, "tedious")
    assert (c2.status, c2.weight) == ("archived_match", 0.5)
    assert c3.weight == 0 and "off topic" in c3.weight_note
    assert c4.weight == 0


def test_unreachable_web_page_gets_zero_weight():
    h = make_hit().model_copy(update={"source": "web"})
    claims = verifier.build_claims("r", {"H1": h}, [{"hit_id": "H1", "sentence_ids": [1], "kind": "pain", "claim_text": "a"}])
    verifier.verify_live(claims, fetcher=lambda u: None)
    verifier.apply_relevance(claims, V)
    assert claims[0].status == "archived_match" and claims[0].weight == 0.0


def test_model_suspect_counts_missed_qualified_sentences():
    h = make_hit()
    missed = verifier.missed_qualified({"H1": h}, {"H1": [1, 2, 3, 4]}, [], V)
    assert missed == ["H1.S1", "H1.S3"]
