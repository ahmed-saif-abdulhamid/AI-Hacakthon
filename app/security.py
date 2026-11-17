"""HTTP security layer for the console: headers and content policy, same-origin and host
checks (against DNS rebinding and cross-site posts), run-id validation (against path
traversal), the read-only public demo, and per-client rate limits on model-spending routes.

``install(app, not_found)`` registers the middleware in a fixed order.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.settings import API_PREFIX, DEMO

CallNext = Callable[[Request], Awaitable[Response]]
NotFound = Callable[[Request], Response]

RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")  # no dots or slashes, so it cannot leave the runs folder
_RUN_PATH = re.compile(rf"^(?:{re.escape(API_PREFIX)}/runs|/p|/store)/([^/]+)")

ASK = f"{API_PREFIX}/ask"
ASK_STREAM = f"{API_PREFIX}/ask/stream"
ASK_WARM = f"{API_PREFIX}/ask/warm"
START_RUN = f"{API_PREFIX}/runs"
SPEAK = f"{API_PREFIX}/voice/speak"
TRANSCRIBE = f"{API_PREFIX}/voice/transcribe"

DEMO_ALLOWED_POSTS = (ASK, ASK_STREAM, SPEAK)
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
STATE_CHANGING_METHODS = ("POST", "PUT", "PATCH", "DELETE")
# Browser form posts (not JSON) that public pages and the voice recorder make.
FORM_POSTS = re.compile(rf"^/(p/[^/]+/signup|store/[^/]+/buy|orders/[^/]+/refund-request)$|^{re.escape(TRANSCRIBE)}$")

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
PUBLISHED_PREFIXES = ("/p/", "/store/")
API_DOCS_PREFIXES = ("/docs", "/openapi")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"  # versioned static files (?v=...)

ALLOWED_HOSTS = {
    h.strip().lower()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,api,testserver").split(",")
    if h.strip()
}

# Per-client limits on the routes that spend the shared model quota: path -> (requests, window in seconds).
RATE_WINDOW_S = 60
LIMITS = {
    ASK: (20, RATE_WINDOW_S),
    ASK_STREAM: (20, RATE_WINDOW_S),
    ASK_WARM: (8, RATE_WINDOW_S),
    START_RUN: (6, RATE_WINDOW_S),
}
DEMO_READ_ONLY_MESSAGE = (
    "This public demo is read-only. Run ProveIt on your own computer "
    "(docker compose up) to test ideas and make decisions."
)
RATE_LIMITED_MESSAGE = "That's a lot of requests in a short time. Give me a few seconds and try again."

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_hits_lock = threading.Lock()


def _refuse(status: int, error: str, **extra: object) -> JSONResponse:
    return JSONResponse({"ok": False, "error": error, **extra}, status_code=status)


def _host_of(origin: str) -> str:
    return re.sub(r"^https?://", "", origin).split(":")[0].split("/")[0].lower()


async def _security_headers(request: Request, call_next: CallNext) -> Response:
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    path = request.url.path
    if path.startswith(PUBLISHED_PREFIXES):
        response.headers.setdefault("Content-Security-Policy", CSP_PUBLISHED)
    elif not path.startswith(API_DOCS_PREFIXES):
        response.headers.setdefault("Content-Security-Policy", CSP_CONSOLE)
    return response


async def _same_origin_only(request: Request, call_next: CallNext) -> Response:
    """DNS-rebinding and cross-site protection for a local app that can approve things:
    the Host must be this machine, and anything that changes state must come from this origin as JSON."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if not DEMO and "*" not in ALLOWED_HOSTS and host not in ALLOWED_HOSTS:
        return _refuse(400, "unknown host")
    if request.method in STATE_CHANGING_METHODS:
        origin = request.headers.get("origin")
        if origin and origin != "null" and _host_of(origin) not in ALLOWED_HOSTS and not DEMO:
            return _refuse(403, "cross-site request refused")
        content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        has_body = int(request.headers.get("content-length") or 0) > 0
        if not FORM_POSTS.match(request.url.path) and has_body and content_type != "application/json":
            return _refuse(415, "send JSON (Content-Type: application/json)")
    response = await call_next(request)
    if request.url.path.startswith("/static/") and "v=" in request.url.query:
        response.headers["Cache-Control"] = IMMUTABLE_CACHE
    return response


def _valid_run_ids(not_found: NotFound) -> Callable[[Request, CallNext], Awaitable[Response]]:
    async def middleware(request: Request, call_next: CallNext) -> Response:
        """A run id in the path must look like one, so no path can climb out of the runs folder."""
        match = _RUN_PATH.match(request.url.path)
        if match and not RUN_ID.fullmatch(match.group(1)):
            return not_found(request)
        return await call_next(request)

    return middleware


async def _demo_read_only(request: Request, call_next: CallNext) -> Response:
    """In the public demo nothing can start a run, decide a gate, approve, buy or refund."""
    if DEMO and request.method not in SAFE_METHODS and request.url.path not in DEMO_ALLOWED_POSTS:
        return _refuse(403, DEMO_READ_ONLY_MESSAGE)
    return await call_next(request)


async def _rate_limit(request: Request, call_next: CallNext) -> Response:
    limit = LIMITS.get(request.url.path) if request.method == "POST" else None
    if limit:
        max_requests, window_s = limit
        key = (request.client.host if request.client else "?", request.url.path)
        now = time.time()
        with _hits_lock:
            hits = _hits[key]
            while hits and now - hits[0] > window_s:
                hits.popleft()
            if len(hits) >= max_requests:
                retry_after = int(window_s - (now - hits[0])) + 1
                response = _refuse(429, RATE_LIMITED_MESSAGE, retry_after=retry_after)
                response.headers["Retry-After"] = str(retry_after)
                return response
            hits.append(now)
    return await call_next(request)


def install(app: FastAPI, not_found: NotFound) -> None:
    """Register the security middleware, outermost last (Starlette runs the last added first).
    ``not_found(request)`` renders the 404 for an invalid run id (the console's designed page)."""
    for middleware in (
        _security_headers,
        _same_origin_only,
        _valid_run_ids(not_found),
        _demo_read_only,
        _rate_limit,
    ):
        app.middleware("http")(middleware)
