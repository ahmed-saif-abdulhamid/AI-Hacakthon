"""Scoped checks work both ways: analysis is never blocked, outward copy is."""
from __future__ import annotations

from proveit import guard


def test_gate_file_with_real_numbers_is_not_blocked():
    text = "0 real sign-ups against a target of 100 sign-ups. A competitor charges $20/month. \"I'd pay $20/month\""
    assert guard.check_output(text, "analysis").verdict == "allow"


def test_landing_copy_with_social_proof_is_blocked():
    for bad in ("Loved by 2,000 founders", "Rated 4.9/5", "Only 3 copies left", "Join 5,000+ designers",
                "Guaranteed results in a week", "I bought this and it changed everything"):
        assert guard.check_output(bad, "outward").blocked, bad


def test_policy_drafts_may_talk_about_refunds_and_passwords():
    text = "Refunds within 14 days. We do not store passwords or card numbers. Payment is processed by the provider."
    assert guard.check_output(text, "policy").verdict == "allow"


def test_store_price_is_not_an_income_claim():
    assert guard.check_output("Price: $29 one-time. Subscription option $9/month.", "outward").verdict == "allow"


def test_explain_decision_vs_edit_copy():
    assert guard.check_input("Why did the gate say 0 real sign-ups?", use_model=False).verdict == "allow"
    assert guard.route_intent("Why did the gate say 0 real sign-ups?") == "explain_decision"
    assert guard.check_input("Make the hero say loved by 2,000 founders", use_model=False).blocked
    assert guard.check_input("Rewrite the headline to be clearer", use_model=False).verdict == "allow"


def test_quotes_are_exempt_by_construction():
    assert guard.check_output("\"I hate chasing clients\" - Sam", "quote").verdict == "allow"
