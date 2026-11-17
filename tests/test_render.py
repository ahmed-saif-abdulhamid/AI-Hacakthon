"""Statement-level citation enforcement."""
from __future__ import annotations

from proveit import render
from proveit.models import Claim, Statement


def claim(cid, quote, weight=1.0):
    return Claim(id=cid, run_id="r", kind="pain", claim_text="x", quote=quote, url=f"https://e.x/{cid}",
                 source="hn", status="verified_live", weight=weight, label="SOURCED")


LEDGER = {"C1": claim("C1", "Onboarding new web design clients is tedious and slow."),
          "C3": claim("C3", "The client onboarding market for design tools is growing."),
          "C9": claim("C9", "Chasing clients for content wastes hours.", weight=0.0)}


def test_number_not_in_quote_drops_citation():
    used = []
    out = render.render_statement(Statement(text="The client onboarding market for design tools is $4B [C3]",
                                            claim_ids=["C3"]), LEDGER, used)
    assert out.startswith("ASSUMPTION:") and used == []


def test_supported_statement_gets_footnote():
    used = []
    out = render.render_statement(Statement(text="Onboarding web design clients is tedious", claim_ids=["C1"]), LEDGER, used)
    assert out.endswith("[C1]") and used == ["C1"]


def test_unknown_and_zero_weight_ids_dropped():
    used = []
    out = render.render_statement(Statement(text="Chasing clients for content wastes hours", claim_ids=["C9", "C77"]),
                                  LEDGER, used)
    assert out.startswith("ASSUMPTION:")


def test_unrelated_citation_dropped():
    used = []
    out = render.render_statement(Statement(text="Pricing should be simple", claim_ids=["C1"]), LEDGER, used)
    assert out.startswith("ASSUMPTION:")


def test_sources_section_lists_urls():
    s = render.sources_section(["C1"], LEDGER)
    assert "https://e.x/C1" in s and "### Sources" in s


def test_factual_detector_scope():
    assert render.factual_flags("Most freelance designers lose 5 hours per week.")
    assert render.factual_flags("70% of customers churn.")
    assert not render.factual_flags("Block 2 hours every week for client calls.")
    assert render.label_unsourced_factual("Most founders struggle. Send the email.").startswith("ASSUMPTION: Most")
