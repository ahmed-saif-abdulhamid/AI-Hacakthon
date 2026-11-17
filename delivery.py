"""Automatic delivery: a paid order gets a signed, 24-hour download token
(itsdangerous URLSafeTimedSerializer). A refund revokes it; the download then returns 403."""
from __future__ import annotations

import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from proveit import db
from proveit.log import log_action, utcnow

MAX_AGE_S = 24 * 3600


class AccessDenied(Exception):
    """Maps to HTTP 403."""


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(os.environ.get("SECRET_KEY", "dev-only-change-me"), salt="proveit-download")


def grant(order_id: str) -> str:
    token = _serializer().dumps({"order_id": order_id})
    db.execute("INSERT OR REPLACE INTO deliveries (order_id, token, issued_at, revoked) VALUES (?,?,?,0)",
               (order_id, token, utcnow()))
    order = db.query_one("SELECT run_id FROM orders WHERE id=?", (order_id,))
    log_action(order["run_id"] if order else None, "delivery", "grant_download", order_id=order_id, test=True)
    return token


def check(token: str) -> str:
    """Return the order id for a valid, unrevoked token, else raise AccessDenied (403)."""
    try:
        data = _serializer().loads(token, max_age=MAX_AGE_S)
    except (BadSignature, SignatureExpired) as e:
        raise AccessDenied(str(e)) from e
    row = db.query_one("SELECT revoked FROM deliveries WHERE order_id=? AND token=?", (data["order_id"], token))
    if row is None or row["revoked"]:
        raise AccessDenied("access revoked")
    return data["order_id"]


def revoke(order_id: str) -> None:
    db.execute("UPDATE deliveries SET revoked=1 WHERE order_id=?", (order_id,))
    order = db.query_one("SELECT run_id FROM orders WHERE id=?", (order_id,))
    log_action(order["run_id"] if order else None, "delivery", "revoke_download", order_id=order_id)


def delivery_count(order_id: str) -> int:
    return len(db.query("SELECT order_id FROM deliveries WHERE order_id=?", (order_id,)))
