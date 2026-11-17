"""Service status: health check, model status and alerting counters."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from app.presenters import STATUS_TABLE
from app.settings import COMMIT, VERSION
from proveit import llm, metrics, voice
from proveit.startup import check_writable

router = APIRouter(tags=["system"])

# Model states in which the service counts as healthy (the demo runs without a model).
HEALTHY_MODEL_STATES = ("ready", "busy", "not attached in this demo")
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4"


@router.get("/health")
def health() -> JSONResponse:
    problems = check_writable()
    model = llm.status()
    ok = not problems and model.get("state") in HEALTHY_MODEL_STATES
    body = {
        "ok": ok,
        "version": VERSION,
        "commit": COMMIT,
        "startup_problems": problems,
        "model": model,
        "tts": voice.tts_status(),
        "stt": voice.stt_status(),
        "status_table": STATUS_TABLE,
    }
    return JSONResponse(body, status_code=200 if ok else 503)


@router.get("/model")
def model_status() -> dict:
    return llm.status()


@router.get("/metrics")
def prometheus_metrics() -> PlainTextResponse:
    """Business counters in the Prometheus text format (they reset when the process restarts)."""
    return PlainTextResponse(metrics.render_prometheus(), media_type=PROMETHEUS_CONTENT_TYPE)
