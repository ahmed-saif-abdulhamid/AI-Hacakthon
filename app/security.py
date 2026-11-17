"""HTTP security layer for the console: headers and content policy, same-origin and host
checks (against DNS rebinding and cross-site posts), run-id validation (against path
traversal), the read-only public demo, and per-client rate limits on model-spending routes.

``install(app)`` registers the middleware in a fixed order.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

DEMO = os.environ.get("PROVEIT_DEMO") == "1"  # read-only public demo of the committed runs

DEMO_ALLOWED_POSTS = ("/api/ask", "/api/ask/stream", "/api/voice/speak")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")  # no dots or slashes, so it cannot leave the runs folder
_RUN_PATH = re.compile(r"^/(?:api/runs|p|store)/([^/]+)")

# Script may only come from this origin; published landing/store pages run no script at all.
CSP_CONSOLE = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
    "frame-src 'self'; frame-ancestors 'self' http://localhost:8501 http://127.0.0.1:8501; "
    "base-uri 'none'; form-action 'self'; object-src 'none'"
)
CSP_PUBLISHED = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
    "form-action 'self'; frame-ancestors 'self'; base-uri 'none'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    path = request.url.path
    if path.startswith(("/p/", "/store/")):
        resp.headers.setdefault("Content-Security-Policy", CSP_PUBLISHED)
    elif not path.startswith("/docs") and not path.startswith("/openapi"):
        resp.headers.setdefault("Content-Security-Policy", CSP_CONSOLE)
    return resp


ALLOWED_HOSTS = {
    h.strip().lower()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,api,testserver").split(",")
    if h.strip()
}
FORM_POSTS = re.compile(r"^/(p/[^/]+/signup|store/[^/]+/buy|orders/[^/]+/refund-request|api/voice/transcribe)$")


async def _same_origin_only(request: Request, call_next):
    """DNS-rebinding and cross-site protection for a local app that can approve things:
    the Host must be this machine, and anything that changes state must come from this origin as JSON."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if not DEMO and "*" not in ALLOWED_HOSTS and host not in ALLOWED_HOSTS:
        return JSONResponse({"ok": False, "error": "unknown host"}, status_code=400)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin and origin != "null":
            ohost = re.sub(r"^https?://", "", origin).split(":")[0].split("/")[0].lower()
            if ohost not in ALLOWED_HOSTS and not DEMO:
                return JSONResponse({"ok": False, "error": "cross-site request refused"}, status_code=403)
        ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        if (
            not FORM_POSTS.match(request.url.path)
            and int(request.headers.get("content-length") or 0) > 0
            and ctype != "application/json"
        ):
            return JSONResponse({"ok": False, "error": "send JSON (Content-Type: application/json)"}, status_code=415)
    resp = await call_next(request)
    if request.url.path.startswith("/static/") and "v=" in request.url.query:
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


async def _valid_run_ids(request: Request, call_next):
    """A run id in the path must look like one, so no path can climb out of the runs folder."""
    m = _RUN_PATH.match(request.url.path)
    if m and not RUN_ID.fullmatch(m.group(1)):
        return _not_found(request)
    return await call_next(request)


async def _demo_read_only(request: Request, call_next):
    """In the public demo nothing can start a run, decide a gate, approve, buy or refund."""
    if DEMO and request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path not in DEMO_ALLOWED_POSTS:
        return JSONResponse(
            {
                "ok": False,
                "error": "This public demo is read-only. Run ProveIt on your own computer "
                "(docker compose up) to test ideas and make decisions.",
            },
            status_code=403,
        )
    return await call_next(request)


# Simple per-client rate limits on the routes that spend the shared model quota.
LIMITS = {"/api/ask": (20, 60), "/api/ask/stream": (20, 60), "/api/ask/warm": (8, 60), "/api/runs": (6, 60)}
_hits: dict[tuple, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


async def _rate_limit(request: Request, call_next):
    lim = LIMITS.get(request.url.path) if request.method == "POST" else None
    if lim:
        n, window = lim
        key = (request.client.host if request.client else "?", request.url.path)
        now = time.time()
        with _hits_lock:
            q = _hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= n:
                retry = int(window - (now - q[0])) + 1
                return JSONResponse(
                    {
                        "ok": False,
                        "error": "That's a lot of requests in a short time. Give me a few " "seconds and try again.",
                        "retry_after": retry,
                    },
                    status_code=429,
                    headers={"Retry-After": str(retry)},
                )
            q.append(now)
    return await call_next(request)


def _not_found(request: Request):
    return PlainTextResponse("Not found", status_code=404)


def install(app: FastAPI, not_found=None) -> None:
    """Register the security middleware, outermost last (Starlette runs the last added first).
    ``not_found(request)`` renders the 404 for an invalid run id (the console's designed page)."""
    global _not_found
    if not_found is not None:
        _not_found = not_found
    for middleware in (
        _security_headers,
        _same_origin_only,
        _valid_run_ids,
        _demo_read_only,
        _rate_limit,
    ):
        app.middleware("http")(middleware)
