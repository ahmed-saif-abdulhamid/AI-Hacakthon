"""Error responses: browsers get a designed page, API and webhook clients get JSON.

``install(app)`` registers the exception handlers.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.templates import status_page
from proveit import approval, metrics
from proveit.commerce import webhooks

logger = logging.getLogger(__name__)

# Paths whose callers are programs, so they always get JSON errors.
JSON_PATH_PREFIXES = ("/api/", "/webhooks/", "/orders/")
MAX_VALIDATION_ERRORS = 3

PAGES: dict[int, tuple[str, str]] = {
    400: ("That request didn't make sense", "Something in the link or form was not what ProveIt expected."),
    401: ("That request wasn't signed", "ProveIt only accepts events it created itself."),
    403: ("This link no longer works", "Download links expire after 24 hours, or as soon as a refund is approved."),
    404: ("Page not found", "The address may be mistyped, or the run may have been removed."),
    409: ("Not published", "The founder has not approved this page, so ProveIt does not show it."),
    422: ("That didn't look right", "Something in the link or form was not what ProveIt expected."),
    429: ("Slow down a little", "Too many requests in a short time. Wait a few seconds and try again."),
    500: (
        "Something went wrong on our side",
        "Your runs are saved. Go back and try again; if it keeps happening, restart ProveIt.",
    ),
}


def wants_json(request: Request) -> bool:
    if request.url.path.startswith(JSON_PATH_PREFIXES):
        return True
    return "text/html" not in request.headers.get("accept", "")


def error_response(request: Request, status: int, detail: str | None = None) -> Response:
    if wants_json(request):
        title = PAGES.get(status, ("Error",))[0]
        return JSONResponse({"ok": False, "error": detail or title}, status_code=status)
    title, body = PAGES.get(status, PAGES[500])
    return status_page(status, title, body)


def not_found(request: Request) -> Response:
    return error_response(request, 404)


async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
    return error_response(request, exc.status_code, exc.detail if isinstance(exc.detail, str) else None)


async def _validation_error(request: Request, exc: RequestValidationError) -> Response:
    if wants_json(request):
        return JSONResponse(
            {"ok": False, "error": "invalid request", "detail": exc.errors()[:MAX_VALIDATION_ERRORS]},
            status_code=422,
        )
    return error_response(request, 422)


async def _bad_event(request: Request, exc: webhooks.BadEvent) -> Response:
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=exc.status)


async def _approval_required(request: Request, exc: approval.ApprovalRequired) -> Response:
    return JSONResponse({"error": f"founder approval required for {exc}"}, status_code=409)


async def _unexpected(request: Request, exc: Exception) -> Response:
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    metrics.increment("http_errors", status=500)
    return error_response(request, 500)


def install(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(webhooks.BadEvent, _bad_event)
    app.add_exception_handler(approval.ApprovalRequired, _approval_required)
    app.add_exception_handler(Exception, _unexpected)
