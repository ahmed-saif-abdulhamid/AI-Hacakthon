"""The console page and the files a browser asks for alongside it."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response

from app.presenters import STATUS_TABLE
from app.settings import API_PREFIX, COMMIT, DEMO, VERSION
from app.templates import CONSOLE_PATH, HUD_TEMPLATE, render
from proveit import llm, voice

router = APIRouter()

BRAND_COLOR = "#3A35C9"
BACKGROUND_COLOR = "#EDF0F3"
ICON_CACHE_CONTROL = "public, max-age=86400"
FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" '
    f'fill="{BRAND_COLOR}"/><path d="M18 33.5l9 9L46 22" fill="none" stroke="#fff" stroke-width="7" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
MANIFEST = {
    "name": "ProveIt",
    "short_name": "ProveIt",
    "start_url": CONSOLE_PATH,
    "display": "standalone",
    "background_color": BACKGROUND_COLOR,
    "theme_color": BRAND_COLOR,
    "description": "Find out if anyone wants your product idea before you build it.",
    "icons": [{"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml"}],
}
ROBOTS_DISALLOW = ("/api/", "/download/", "/hud", "/p/", "/store/")
ROBOTS_TXT = "User-agent: *\n" + "".join(f"Disallow: {path}\n" for path in ROBOTS_DISALLOW)

ConsoleMode = Literal["tactical", "hud", "dual"]


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(CONSOLE_PATH)


@router.api_route(CONSOLE_PATH, methods=["GET", "HEAD"], response_class=HTMLResponse)
def hud(mode: ConsoleMode = "tactical", embed: int = 0, api: str = "") -> str:
    """The console. ``api`` is the API's origin when the page is embedded from another port."""
    return render(
        HUD_TEMPLATE,
        initial_mode=mode,
        embed=bool(embed),
        api_base=api,
        api_prefix=API_PREFIX,
        status_table=STATUS_TABLE,
        demo=DEMO,
        assistant=voice.assistant_name(),
        wake=voice.wake_word(),
        wake_re=voice.wake_pattern(),
        version=VERSION,
        commit=COMMIT,
        model=llm.model_name(),
    )


@router.get("/favicon.svg", include_in_schema=False)
@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(FAVICON_SVG, media_type="image/svg+xml", headers={"Cache-Control": ICON_CACHE_CONTROL})


@router.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> JSONResponse:
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


@router.get("/robots.txt", include_in_schema=False)
def robots() -> PlainTextResponse:
    return PlainTextResponse(ROBOTS_TXT)
