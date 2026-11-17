"""Public pages and sale to cash (MOCKED payments): the approved landing and store pages, the waitlist
sign-up, the practice purchase, refund requests, the signed webhook and the download.

Published pages are served from the approved blob (keyed by SHA-256), never re-rendered: an
unapproved page returns 409.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.errors import error_response
from app.templates import status_page
from proveit import approval, db, metrics, orchestrator
from proveit.commerce import checkout, delivery, refunds, webhooks
from proveit.log import utcnow
from proveit.startup import runs_dir

router = APIRouter()

LANDING = "landing"
STORE = "store"
DEFAULT_PRICE = 39.0
MAX_EMAIL_CHARS = 320
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,255}")
DOWNLOAD_GLOB = "phase3_step*"
DOWNLOAD_FILENAME = "toolkit.zip"
EMPTY_DOWNLOAD_NAME = "README.txt"
EMPTY_DOWNLOAD = "The product files are not built yet."


def _serve(request: Request, run_id: str, kind: str) -> Response:
    """The exact bytes the founder approved, or 409 (known run, not approved) / 404 (unknown run)."""
    published = approval.published_payload(run_id, kind)
    if published is None:
        exists = db.query_one("SELECT id FROM runs WHERE id=?", (run_id,))
        return error_response(request, 409 if exists else 404)
    payload, content_type = published
    return HTMLResponse(payload.decode("utf-8"), media_type=content_type.split(";")[0])


def _require_published(run_id: str, kind: str, detail: str) -> None:
    if approval.published_payload(run_id, kind) is None:
        raise HTTPException(409, detail)


def _order_run_id(order_id: str) -> str:
    order = db.query_one("SELECT run_id FROM orders WHERE id=?", (order_id,))
    if order is None:
        raise HTTPException(404)
    return order["run_id"]


@router.get("/p/{run_id}", response_class=HTMLResponse)
def landing(request: Request, run_id: str) -> Response:
    return _serve(request, run_id, LANDING)


@router.post("/p/{run_id}/signup", response_class=HTMLResponse)
def signup(run_id: str, email: str = Form(..., max_length=MAX_EMAIL_CHARS)) -> HTMLResponse:
    _require_published(run_id, LANDING, "not approved")
    back = {"back": f"/p/{run_id}", "back_label": "Back to the page"}
    if not _EMAIL.fullmatch(email):
        return status_page(422, "That email doesn't look right", "Go back and check the address.", **back)
    # Public hosting is STUBBED: every sign-up is a test sign-up and is excluded from every gate.
    db.execute("INSERT INTO signups (run_id, email, ts, test) VALUES (?,?,?,1)", (run_id, email, utcnow()))
    metrics.increment("signup_recorded")
    return status_page(
        200,
        "You're on the list",
        "Thanks. We stored only your email address and the time. "
        "This page runs locally (public hosting is STUBBED), so this sign-up is marked as a test "
        "and never counts as demand.",
        tone="ok",
        **back,
    )


@router.get("/store/{run_id}", response_class=HTMLResponse)
def store(request: Request, run_id: str) -> Response:
    return _serve(request, run_id, STORE)


@router.post("/store/{run_id}/buy", response_class=HTMLResponse)
def buy(run_id: str) -> HTMLResponse:
    """A MOCKED practice purchase: create the order, run the signed payment webhook, link the download."""
    _require_published(run_id, STORE, "store not approved")
    run = orchestrator.load(run_id)
    price = float(run.state.get("pricing", {}).get("better", DEFAULT_PRICE))
    sale = checkout.purchase(run_id, price)
    order_id, result = sale.order_id, sale.result
    metrics.increment("checkout_completed")
    return status_page(
        200,
        "Practice purchase complete",
        f"This was a MOCKED test purchase of ${price:.2f} (order {order_id}). No money moved and no card "
        "details were asked for. Your download link works for 24 hours.",
        tone="ok",
        back=f"/store/{run_id}",
        back_label="Back to the store",
        actions=[{"href": f"/download/{result['token']}", "label": "Download the files"}],
        refund_order=order_id,
    )


@router.post("/orders/{order_id}/refund-request")
def refund_request(request: Request, order_id: str) -> Response:
    """Open a refund approval for the founder; nothing is refunded until they approve it."""
    run_id = _order_run_id(order_id)
    pending = refunds.request(run_id, order_id)
    metrics.increment("refund_requested")
    if "text/html" in request.headers.get("accept", ""):
        return status_page(
            202,
            "Refund requested",
            "The founder has to approve this refund before anything happens. "
            "ProveIt never refunds money on its own; this is a MOCKED practice refund.",
            back=f"/store/{run_id}",
            back_label="Back to the store",
        )
    return JSONResponse({"approval_id": pending.id, "status": pending.status, "payload_sha256": pending.payload_sha256})


@router.post("/webhooks/mock")
async def webhook(request: Request) -> dict:
    """The MOCKED payment provider's signed events. A malformed or forged event is refused with a 4xx."""
    try:
        event = await request.json()
    except ValueError:
        metrics.increment("webhook_rejected", status=400)
        raise webhooks.BadEvent("body must be JSON") from None
    try:
        return webhooks.handle(event)
    except webhooks.BadEvent as e:
        metrics.increment("webhook_rejected", status=e.status)
        raise


@router.get("/download/{token}")
def download(request: Request, token: str) -> Response:
    try:
        order_id = delivery.check(token)
    except delivery.AccessDenied:
        return error_response(request, 403)
    run_id = _order_run_id(order_id)
    return Response(
        _toolkit_zip(runs_dir() / run_id),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={DOWNLOAD_FILENAME}"},
    )


def _toolkit_zip(run_dir: Path) -> bytes:
    """The run's Phase 3 files as one zip archive, built in memory; a note file when none exist yet."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        files = sorted(f for f in run_dir.glob(DOWNLOAD_GLOB) if f.is_file())
        for f in files:
            archive.write(f, arcname=f.name)
        if not files:
            archive.writestr(EMPTY_DOWNLOAD_NAME, EMPTY_DOWNLOAD)
    return buffer.getvalue()
