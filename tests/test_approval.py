"""Nothing goes out without a founder approval bound to the exact payload bytes."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from proveit import approval
from proveit.log import export


def test_blocked_without_approval():
    with pytest.raises(approval.ApprovalRequired):
        approval.publish_landing_page(b"<html>x</html>", None, run_id="r1")
    assert export("r1")[-1]["action"] == "blocked_publish_landing_page"


def test_pending_or_rejected_is_not_enough():
    ap = approval.request("r1", "publish_landing_page", b"page")
    with pytest.raises(approval.ApprovalRequired):
        approval.publish_landing_page(b"page", ap.id, run_id="r1")
    approval.decide(ap.id, False)
    with pytest.raises(approval.ApprovalRequired):
        approval.publish_landing_page(b"page", ap.id, run_id="r1")


def test_one_changed_byte_voids_the_approval():
    ap = approval.request("r1", "open_store", b"store v1")
    approval.auto_approve(ap.id)
    with pytest.raises(approval.ApprovalRequired):
        approval.open_store(b"store v2", ap.id, run_id="r1")
    assert approval.open_store(b"store v1", ap.id, run_id="r1") == approval.sha256(b"store v1")
    e = [x for x in export("r1") if x["action"] == "open_store"][0]
    assert e["approved_by"] == "founder"


def test_wrong_action_is_rejected():
    ap = approval.request("r1", "publish_landing_page", b"p")
    approval.auto_approve(ap.id)
    with pytest.raises(approval.ApprovalRequired):
        approval.open_store(b"p", ap.id, run_id="r1")


@pytest.mark.parametrize("fn,action", [(approval.spend, "spend"), (approval.sign, "sign"),
                                       (approval.create_account, "create_account")])
def test_spend_sign_create_account_always_raise(fn, action):
    ap = approval.request("r1", action, b"x")
    approval.auto_approve(ap.id)
    with pytest.raises(approval.NotEnabled):
        fn(b"x", ap.id, run_id="r1")


def test_stubbed_publish_adapters_raise():
    for fn, action in ((approval.publish_post, "publish_post"), (approval.send_email, "send_email")):
        ap = approval.request("r1", action, b"draft")
        approval.auto_approve(ap.id)
        with pytest.raises(approval.NotEnabled):
            fn(b"draft", ap.id, run_id="r1")


def test_auto_approve_only_in_test_env(monkeypatch):
    ap = approval.request("r1", "refund", b"{}")
    monkeypatch.setenv("PROVEIT_ENV", "production")
    with pytest.raises(RuntimeError):
        approval.auto_approve(ap.id)


def test_served_page_is_the_approved_blob_and_unapproved_is_409():
    from app.api import app
    c = TestClient(app)
    assert c.get("/p/r9").status_code == 409
    ap = approval.request("r9", "publish_landing_page", b"<!doctype html><p>approved v1</p>", content_type="text/html")
    approval.auto_approve(ap.id)
    approval.publish_landing_page(b"<!doctype html><p>approved v1</p>", ap.id, run_id="r9")
    # a later template change does not change what is served
    r = c.get("/p/r9")
    assert r.status_code == 200 and "approved v1" in r.text


def test_ui_approval_requires_the_hash_the_founder_saw():
    from app.api import app
    c = TestClient(app)
    ap = approval.request("r8", "publish_landing_page", b"<p>x</p>")
    r = c.post(f"/api/approvals/{ap.id}", json={"approve": True, "payload_sha256": "0" * 64})
    assert r.status_code == 409
    assert approval.load(ap.id).status == "pending"
