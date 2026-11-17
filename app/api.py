"""FastAPI service (port 8000): the ProveIt console, the versioned JSON API, the approved landing
and store pages, the MOCKED payment, webhook and delivery endpoints, and the voice API.

This module only assembles the app: middleware, routers and error handlers. The routes live
in ``app/routes/``; every JSON route is mounted under ``settings.API_PREFIX``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app import errors, security
from app.routes import approvals, assistant, console, runs, storefront, system
from app.routes import voice as voice_routes
from app.settings import API_PREFIX, DEMO, STATIC_DIR, VERSION
from proveit import seed, voice

logger = logging.getLogger(__name__)

# The developer view (Streamlit, port 8501) embeds the console and calls the API from its own origin.
CORS_ORIGINS = ["http://localhost:8501", "http://127.0.0.1:8501", "http://localhost:8000", "http://127.0.0.1:8000"]
GZIP_MIN_BYTES = 1024
JSON_ROUTERS = (system.router, runs.router, approvals.router, assistant.router, voice_routes.router)


def _load_committed_runs() -> None:
    """Load the committed example runs, so a fresh install never opens on an empty console."""
    try:
        loaded = seed.load()
    except Exception:  # a broken seed must never stop the console
        logger.exception("could not load the committed runs")
        return
    if loaded:
        logger.info("loaded the committed runs %s", ", ".join(loaded))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if os.environ.get("PROVEIT_ENV") != "test":
        _load_committed_runs()
    if not DEMO:
        voice.warm_up()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="ProveIt", version=VERSION, docs_url=None if DEMO else "/docs", redoc_url=None, lifespan=lifespan
    )
    application.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
    security.install(application, not_found=errors.not_found)
    application.add_middleware(GZipMiddleware, minimum_size=GZIP_MIN_BYTES)
    errors.install(application)

    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    application.include_router(console.router)
    application.include_router(storefront.router)
    for router in JSON_ROUTERS:
        application.include_router(router, prefix=API_PREFIX)
    return application


app = create_app()
