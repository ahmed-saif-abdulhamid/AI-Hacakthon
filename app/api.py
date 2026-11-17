"""FastAPI service (port 8000): the ProveIt console, the JSON API, the approved landing and store
pages, the MOCKED webhook/delivery endpoints and the voice API.

Published pages are served from the approved blob (keyed by SHA-256), never re-rendered: an
unapproved page returns 409. Browsers get designed error pages; API clients get JSON errors.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse,
                               Response, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

import delivery
import payments
import refunds
import webhooks
from proveit import approval, ask, db, llm, orchestrator, voice
from proveit.log import entries, telemetry, utcnow
from proveit.startup import check_writable, runs_dir

ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.2.0"
DEMO = os.environ.get("PROVEIT_DEMO") == "1"   # read-only public demo of the committed runs
app = FastAPI(title="ProveIt", version=VERSION, docs_url=None if DEMO else "/docs", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8501", "http://127.0.0.1:8501",
                                                  "http://localhost:8000", "http://127.0.0.1:8000"],
                   allow_methods=["*"], allow_headers=["*"])
_env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=select_autoescape(["html", "j2"]))
_workers: dict[str, threading.Thread] = {}
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

STATUS_TABLE = [
    ("Intake + eligibility check", "Working"), ("1.1 Find opportunities", "Working"),
    ("1.2 Evidence ledger", "Working"), ("1.3 Market definition", "Working"),
    ("1.4 Mom Test interview kit", "Working"), ("Gate 1: evidence", "Working"),
    ("2.1 Lean Canvas", "Working"), ("2.2 Landing page + waitlist", "Working"),
    ("Public hosting", "STUBBED"), ("Gate 2: demand", "Working"), ("3.1 Build MVP toolkit", "Working"),
    ("Gate 3: tests", "Working"), ("4.1 Pricing", "Working"), ("4.2 Policy drafts", "Working"),
    ("Gate 4", "Working"), ("5.1 Store page + launch post draft", "Working"),
    ("5.2 Payment -> delivery -> refund", "MOCKED"), ("5.3 Reconciliation", "MOCKED"),
    ("Posting to external platforms", "STUBBED"), ("6 Operate and learn", "STUBBED"),
    ("Reddit source", "STUBBED"),
]


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              timeout=3).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


COMMIT = _commit()

# ---- middleware -------------------------------------------------------------------------

DEMO_ALLOWED_POSTS = ("/api/ask", "/api/ask/stream", "/api/voice/speak")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")   # no dots or slashes, so it cannot leave the runs folder
_RUN_PATH = re.compile(r"^/(?:api/runs|p|store)/([^/]+)")

# Script may only come from this origin; published landing/store pages run no script at all.
CSP_CONSOLE = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
               "font-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
               "frame-src 'self'; frame-ancestors 'self' http://localhost:8501 http://127.0.0.1:8501; "
               "base-uri 'none'; form-action 'self'; object-src 'none'")
CSP_PUBLISHED = ("default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
                 "form-action 'self'; frame-ancestors 'self'; base-uri 'none'")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


@app.middleware("http")
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


@app.middleware("http")
async def _valid_run_ids(request: Request, call_next):
    """A run id in the path must look like one, so no path can climb out of the runs folder."""
    m = _RUN_PATH.match(request.url.path)
    if m and not RUN_ID.fullmatch(m.group(1)):
        return _error_response(request, 404)
    return await call_next(request)


@app.middleware("http")
async def _demo_read_only(request: Request, call_next):
    """In the public demo nothing can start a run, decide a gate, approve, buy or refund."""
    if DEMO and request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path not in DEMO_ALLOWED_POSTS:
        return JSONResponse({"ok": False, "error": "This public demo is read-only. Run ProveIt on your own computer "
                             "(docker compose up) to test ideas and make decisions."}, status_code=403)
    return await call_next(request)


# Simple per-client rate limits on the routes that spend the shared model quota.
LIMITS = {"/api/ask": (20, 60), "/api/ask/stream": (20, 60), "/api/ask/warm": (8, 60), "/api/runs": (6, 60)}
_hits: dict[tuple, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


@app.middleware("http")
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
                return JSONResponse({"ok": False, "error": "That's a lot of requests in a short time. Give me a few "
                                     "seconds and try again.", "retry_after": retry}, status_code=429,
                                    headers={"Retry-After": str(retry)})
            q.append(now)
    return await call_next(request)


app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.on_event("startup")
def _warm_voice() -> None:
    if not DEMO:
        voice.warm_up()


def _advance_bg(run_id: str) -> None:
    t = _workers.get(run_id)
    if t and t.is_alive():
        return
    t = threading.Thread(target=orchestrator.advance, args=(run_id,), daemon=True)
    _workers[run_id] = t
    t.start()


# ---- error pages -----------------------------------------------------------------------

PAGES = {
    400: ("That request didn't make sense", "Something in the link or form was not what ProveIt expected."),
    401: ("That request wasn't signed", "ProveIt only accepts events it created itself."),
    403: ("This link no longer works", "Download links expire after 24 hours, or as soon as a refund is approved."),
    404: ("Page not found", "The address may be mistyped, or the run may have been removed."),
    409: ("Not published", "The founder has not approved this page, so ProveIt does not show it."),
    422: ("That didn't look right", "Something in the link or form was not what ProveIt expected."),
    429: ("Slow down a little", "Too many requests in a short time. Wait a few seconds and try again."),
    500: ("Something went wrong on our side", "Your runs are saved. Go back and try again; if it keeps happening, "
                                              "restart ProveIt."),
}


def _wants_json(request: Request) -> bool:
    p = request.url.path
    return p.startswith(("/api/", "/webhooks/", "/orders/")) or "text/html" not in request.headers.get("accept", "")


def _render_page(status: int, title: str, body: str, back: str = "/hud", back_label: str = "Back to ProveIt",
                 tone: str = "plain") -> HTMLResponse:
    html = _env.get_template("status.html.j2").render(status=status, title=title, body=body, back=back,
                                                      back_label=back_label, tone=tone)
    return HTMLResponse(html, status_code=status)


def _error_response(request: Request, status: int, detail: str | None = None):
    if _wants_json(request):
        return JSONResponse({"ok": False, "error": detail or PAGES.get(status, ("Error",))[0]}, status_code=status)
    title, body = PAGES.get(status, PAGES[500])
    return _render_page(status, title, body)


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    return _error_response(request, exc.status_code, exc.detail if isinstance(exc.detail, str) else None)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    if _wants_json(request):
        return JSONResponse({"ok": False, "error": "invalid request", "detail": exc.errors()[:3]}, status_code=422)
    return _error_response(request, 422)


@app.exception_handler(webhooks.BadEvent)
async def _bad_event(request: Request, exc: webhooks.BadEvent):
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=exc.status)


@app.exception_handler(approval.ApprovalRequired)
async def _approval_required(request: Request, exc: approval.ApprovalRequired):
    return JSONResponse({"error": f"founder approval required for {exc}"}, status_code=409)


@app.exception_handler(Exception)
async def _unexpected(request: Request, exc: Exception):
    return _error_response(request, 500)


# ---- console ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/hud")


@app.get("/hud", response_class=HTMLResponse)
def hud(mode: Literal["tactical", "hud", "dual"] = "tactical", embed: int = 0, api: str = ""):
    return _env.get_template("hud.html.j2").render(
        initial_mode=mode, embed=bool(embed), api_base=api, status_table=STATUS_TABLE, demo=DEMO,
        assistant=voice.assistant_name(), version=VERSION, commit=COMMIT, model=llm.model_name())


FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" '
           'fill="#3A35C9"/><path d="M18 33.5l9 9L46 22" fill="none" stroke="#fff" stroke-width="7" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>')


@app.get("/favicon.svg", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(FAVICON, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return JSONResponse({"name": "ProveIt", "short_name": "ProveIt", "start_url": "/hud", "display": "standalone",
                         "background_color": "#EDF0F3", "theme_color": "#3A35C9",
                         "description": "Find out if anyone wants your product idea before you build it.",
                         "icons": [{"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml"}]},
                        media_type="application/manifest+json")


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /api/\nDisallow: /download/\nDisallow: /hud\nDisallow: /p/\n"
                             "Disallow: /store/\n")


@app.get("/api/health")
def health():
    problems = check_writable()
    model = llm.status()
    ok = not problems and model.get("state") in ("ready", "busy", "not attached in this demo")
    body = {"ok": ok, "version": VERSION, "commit": COMMIT, "startup_problems": problems, "model": model,
            "tts": voice.tts_status(), "stt": voice.stt_status(), "status_table": STATUS_TABLE}
    return JSONResponse(body, status_code=200 if ok else 503)


@app.get("/api/model")
def model_status():
    return llm.status()


# ---- runs -------------------------------------------------------------------------------

MAX_IDEA = 2000


class RunIn(BaseModel):
    brief_text: str = Field("", max_length=8000)
    fields: dict = {}
    mode: str = "live"
    label: str | None = Field(None, max_length=40)


_recent_starts: dict[str, tuple[float, str]] = {}


@app.post("/api/runs")
def create_run(body: RunIn):
    fields = {k: str(v)[:MAX_IDEA if k == "idea" else 300] for k, v in (body.fields or {}).items()
              if k in ("idea", "skills", "budget", "hours_per_week", "target_market", "values", "founder_name") and v}
    if not (body.brief_text.strip() or fields.get("idea", "").strip()):
        raise HTTPException(422, "the idea is required")
    # A double click must not start the same run twice.
    key = (body.brief_text.strip() + "|" + json.dumps(fields, sort_keys=True)).lower()
    prev = _recent_starts.get(key)
    if prev and time.time() - prev[0] < 15:
        return {"run_id": prev[1], "duplicate": True}
    run_id = orchestrator.start(body.brief_text, fields, body.mode if body.mode in ("live", "full") else "live",
                                body.label)
    _recent_starts[key] = (time.time(), run_id)
    _advance_bg(run_id)
    return {"run_id": run_id}


def _idea_text(run) -> str:
    b = run.state.get("brief") or {}
    raw = run.brief_raw or {}
    return str(b.get("idea") or raw.get("fields", {}).get("idea") or raw.get("text", "")).strip()


def _run_title(run_id: str) -> str | None:
    try:
        run = orchestrator.load(run_id)
    except Exception:  # noqa: BLE001
        return None
    variants = run.state.get("variants") or []
    if variants:
        return variants[min(len(variants), run.state.get("variant_n", 1)) - 1].get("title")
    idea = re.sub(r"(?i)^idea\s*:\s*", "", _idea_text(run)).split("\n")[0]
    return idea[:80] or None


@app.get("/api/runs")
def runs():
    return [dict(r, title=_run_title(r["id"])) for r in orchestrator.list_runs(60)]


def run_view(run_id: str) -> dict:
    try:
        run = orchestrator.load(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run")
    s = run.state
    v = s.get("variant_n", 1)
    research = s.get("research", {}).get(str(v), {})
    claims = [c for c in s.get("claims", []) if c.get("hit_id") in research.get("hits", {})] if research else s.get("claims", [])
    from proveit import gates as g
    current = g.thresholds_sha256(s.get("thresholds", {}), run.brief_raw) if s.get("thresholds") else ""
    row = db.query_one("SELECT status FROM runs WHERE id=?", (run.id,)) or {}
    narr = db.query("SELECT text FROM telemetry WHERE run_id=? AND kind IN ('narration','progress') "
                    "ORDER BY seq DESC LIMIT 1", (run.id,))
    return {
        "run_id": run.id, "label": run.label, "mode": run.mode, "stage": run.stage, "phase": s.get("phase", 1),
        "idea": re.sub(r"(?i)^idea\s*:\s*", "", _idea_text(run)), "title": _run_title(run.id),
        "brief": s.get("brief"), "thresholds_sha256": run.sha, "goalpost_moved": bool(current and current != run.sha),
        "thresholds": s.get("thresholds", {}).get("gate1_evidence"), "variants": s.get("variants", []),
        "variant_n": v, "claims": claims, "metrics": research.get("metrics"), "coverage_rows": research.get("coverage_rows"),
        "gate1": s.get("gate1"), "gate2": s.get("gate2"), "gate3": s.get("gate3"), "gate4": s.get("gate4"),
        "debate": s.get("debate"), "override": s.get("override"), "clarify": s.get("clarify"),
        "pending_approval": s.get("pending_approval"), "usage": llm.usage(run.id) or s.get("usage"),
        "error": s.get("error"), "error_message": s.get("error_message"),
        "order": {k: s.get("order", {}).get(k) for k in ("id", "amount")} if s.get("order") else None,
        "files": sorted(p.name for p in run.dir.iterdir() if p.is_file()),
        "working": bool(_workers.get(run.id) and _workers[run.id].is_alive()),
        "actions": [] if DEMO else orchestrator.allowed_decisions(run),
        "status": row.get("status"), "latest": narr[0]["text"] if narr else "",
        "created_at": (db.query_one("SELECT created_at FROM runs WHERE id=?", (run.id,)) or {}).get("created_at"),
    }


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return run_view(run_id)


@app.get("/api/runs/{run_id}/telemetry")
def get_telemetry(run_id: str, since: int = 0):
    return telemetry(run_id, since)


@app.get("/api/runs/{run_id}/log")
def get_log(run_id: str):
    out = entries(run_id)
    for e in out:
        e.pop("_seq", None)
    return out


@app.get("/api/runs/{run_id}/files/{name}")
def get_file(run_id: str, name: str):
    if not RUN_ID.fullmatch(run_id) or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", name) or ".." in name:
        raise HTTPException(404, "no such file")
    base = (runs_dir() / run_id).resolve()
    p = (base / name).resolve()
    if base not in p.parents or not p.is_file():          # never serve anything outside the run's folder
        raise HTTPException(404, "no such file")
    return PlainTextResponse(p.read_text(encoding="utf-8"))


@app.post("/api/runs/{run_id}/continue")
def continue_run(run_id: str):
    """Try again after an error (the run keeps its stage, so it picks up where it stopped)."""
    try:
        res = orchestrator.retry(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run")
    if res.get("ok"):
        _advance_bg(run_id)
    return res


class DecideIn(BaseModel):
    decision: str = Field(max_length=40)
    reason: str = Field("", max_length=1000)


@app.post("/api/runs/{run_id}/decide")
def decide(run_id: str, body: DecideIn):
    try:
        res = orchestrator.founder_decide(run_id, body.decision, body.reason)
    except KeyError:
        raise HTTPException(404, "unknown run")
    if res.get("ok"):
        _advance_bg(run_id)
    return res


# ---- approvals (the hash-locked buttons) ---------------------------------------------

@app.get("/api/approvals")
def list_approvals(run: str | None = None, status: str | None = None):
    return [a.model_dump(mode="json") for a in approval.list_approvals(run, status)]


@app.get("/api/approvals/{approval_id}/payload")
def approval_payload(approval_id: str):
    ap = approval.load(approval_id)
    if ap is None:
        raise HTTPException(404)
    payload, ctype = approval.blob(ap.payload_sha256)
    return PlainTextResponse(payload.decode("utf-8", "replace"), headers={"X-Payload-SHA256": ap.payload_sha256})


class ApproveIn(BaseModel):
    approve: bool
    payload_sha256: str = Field(max_length=64)


@app.post("/api/approvals/{approval_id}")
def decide_approval(approval_id: str, body: ApproveIn):
    ap = approval.load(approval_id)
    if ap is None:
        raise HTTPException(404)
    if ap.status != "pending":
        raise HTTPException(409, "this approval was already decided")
    if body.payload_sha256 != ap.payload_sha256:
        raise HTTPException(409, "the payload you saw does not match the payload awaiting approval")
    res = approval.decide(approval_id, body.approve, via="ui")
    orchestrator.on_approval_decided(approval_id)
    _advance_bg(res.run_id)
    return res.model_dump(mode="json")


# ---- Ask the assistant -------------------------------------------------------------------

class AskIn(BaseModel):
    text: str = Field(max_length=2000)
    run_id: str | None = Field(None, max_length=64)
    history: list[dict] = Field(default_factory=list, max_length=20)
    screen: list[str] = Field(default_factory=list, max_length=20)


@app.post("/api/ask")
def ask_endpoint(body: AskIn):
    res = ask.handle(body.text, body.run_id, history=body.history[-6:], screen=body.screen)
    voice.prerender(res.get("spoken", ""))
    if res.get("start_run"):
        _advance_bg(res["start_run"])
    return res


@app.post("/api/ask/stream")
def ask_stream(body: AskIn):
    """NDJSON: one "meta" line, then one "sentence" line per spoken sentence, then "done".

    Sentences are spoken as they arrive, so the first words play about a second after the
    model starts instead of after the whole answer.
    """
    res = ask.handle(body.text, body.run_id, history=body.history[-6:], stream=True, screen=body.screen)

    def gen():
        if not res.get("converse"):
            voice.prerender(res.get("spoken", ""))
            if res.get("start_run"):
                _advance_bg(res["start_run"])
            yield json.dumps({"type": "meta", **res}) + "\n"
            yield json.dumps({"type": "sentence", "text": res.get("spoken", "")}) + "\n"
            yield json.dumps({"type": "done", "text": res.get("spoken", "")}) + "\n"
            return
        yield json.dumps({"type": "meta", "intent": res["intent"], "detail": res.get("text", "")}) + "\n"
        run = None
        if body.run_id:
            try:
                run = orchestrator.load(body.run_id)
            except KeyError:
                run = None
        said = []
        try:
            for s in ask.converse_stream(ask.strip_wake(body.text), run, body.history[-6:], screen=body.screen):
                said.append(s)
                voice.prerender(s)
                yield json.dumps({"type": "sentence", "text": s}) + "\n"
        except llm.LLMError:
            msg = ask.offline_answer(ask.strip_wake(body.text), run)
            said.append(msg)
            yield json.dumps({"type": "sentence", "text": msg}) + "\n"
        yield json.dumps({"type": "done", "text": " ".join(said)}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


_warmed: dict[str, float] = {}


@app.post("/api/ask/warm")
def ask_warm(body: AskIn):
    """Called when a run is opened in the console: pre-reads its context so the first answer is quick.
    Skipped if the same run was warmed in the last five minutes (it saves the shared model quota)."""
    if DEMO or not body.run_id or time.time() - _warmed.get(body.run_id, 0) < 300:
        return {"ok": False}
    try:
        run = orchestrator.load(body.run_id)
    except KeyError:
        return {"ok": False}
    _warmed[body.run_id] = time.time()
    threading.Thread(target=ask.warm, args=(run,), daemon=True).start()
    return {"ok": True}


@app.get("/api/presets/{name}")
def preset(name: str):
    if name not in ("weak", "strong"):
        raise HTTPException(404)
    return {"text": (ROOT / "briefs" / f"{name}.md").read_text(encoding="utf-8")}


# ---- voice -----------------------------------------------------------------------------

class SpeakIn(BaseModel):
    text: str = Field(max_length=1200)


@app.post("/api/voice/speak")
def speak(body: SpeakIn):
    try:
        path = voice.synthesize(body.text)
    except voice.VoiceUnavailable as e:
        return JSONResponse({"error": str(e), "fallback": "browser speechSynthesis"}, status_code=503)
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/voice/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    data = await audio.read()
    try:
        text = voice.transcribe(data, suffix=Path(audio.filename or "a.webm").suffix or ".webm")
    except voice.VoiceUnavailable as e:
        return JSONResponse({"error": str(e), "fallback": "browser SpeechRecognition"}, status_code=503)
    return {"text": text}


@app.get("/api/voice/status")
def voice_status():
    return {"tts": voice.tts_status(), "stt": voice.stt_status(), "assistant": voice.assistant_name()}


# ---- published pages (approved bytes only) ----------------------------------------------

def _serve(request: Request, run_id: str, kind: str):
    got = approval.published_payload(run_id, kind)
    if got is None:
        exists = db.query_one("SELECT id FROM runs WHERE id=?", (run_id,))
        return _error_response(request, 409 if exists else 404)
    payload, ctype = got
    return HTMLResponse(payload.decode("utf-8"), media_type=ctype.split(";")[0])


@app.get("/p/{run_id}", response_class=HTMLResponse)
def landing(request: Request, run_id: str):
    return _serve(request, run_id, "landing")


@app.post("/p/{run_id}/signup", response_class=HTMLResponse)
def signup(request: Request, run_id: str, email: str = Form(..., max_length=320)):
    if approval.published_payload(run_id, "landing") is None:
        raise HTTPException(409, "not approved")
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,255}", email):
        return _render_page(422, "That email doesn't look right", "Go back and check the address.",
                            back=f"/p/{run_id}", back_label="Back to the page")
    # Public hosting is STUBBED: every sign-up is a test sign-up and is excluded from every gate.
    db.execute("INSERT INTO signups (run_id, email, ts, test) VALUES (?,?,?,1)", (run_id, email, utcnow()))
    return _render_page(200, "You're on the list", "Thanks. We stored only your email address and the time. "
                        "This page runs locally (public hosting is STUBBED), so this sign-up is marked as a test "
                        "and never counts as demand.", back=f"/p/{run_id}", back_label="Back to the page", tone="ok")


@app.get("/store/{run_id}", response_class=HTMLResponse)
def store(request: Request, run_id: str):
    return _serve(request, run_id, "store")


@app.post("/store/{run_id}/buy", response_class=HTMLResponse)
def buy(request: Request, run_id: str):
    if approval.published_payload(run_id, "store") is None:
        raise HTTPException(409, "store not approved")
    run = orchestrator.load(run_id)
    price = float(run.state.get("pricing", {}).get("better", 39))
    provider = payments.MockPaymentProvider()
    order_id = provider.create_order(run_id, price)
    res = webhooks.handle(provider.create_checkout(order_id, price))
    html = _env.get_template("status.html.j2").render(
        status=200, tone="ok", title="Practice purchase complete",
        body=f"This was a MOCKED test purchase of ${price:.2f} (order {order_id}). No money moved and no card "
             "details were asked for. Your download link works for 24 hours.",
        back=f"/store/{run_id}", back_label="Back to the store",
        actions=[{"href": f"/download/{res['token']}", "label": "Download the files"}],
        refund_order=order_id)
    return HTMLResponse(html)


@app.post("/orders/{order_id}/refund-request")
def refund_request(request: Request, order_id: str):
    o = db.query_one("SELECT run_id FROM orders WHERE id=?", (order_id,))
    if o is None:
        raise HTTPException(404)
    ap = refunds.request(o["run_id"], order_id)
    if "text/html" in request.headers.get("accept", ""):
        return _render_page(202, "Refund requested", "The founder has to approve this refund before anything happens. "
                            "ProveIt never refunds money on its own; this is a MOCKED practice refund.",
                            back=f"/store/{o['run_id']}", back_label="Back to the store")
    return {"approval_id": ap.id, "status": ap.status, "payload_sha256": ap.payload_sha256}


@app.post("/webhooks/mock")
async def webhook(request: Request):
    try:
        event = await request.json()
    except ValueError:
        raise webhooks.BadEvent("body must be JSON")
    return webhooks.handle(event)


@app.get("/download/{token}")
def download(request: Request, token: str):
    try:
        order_id = delivery.check(token)
    except delivery.AccessDenied:
        return _error_response(request, 403)
    o = db.query_one("SELECT run_id FROM orders WHERE id=?", (order_id,))
    files = sorted((runs_dir() / o["run_id"]).glob("phase3_step*"))
    body = "\n\n".join(f"===== {f.name} =====\n{f.read_text(encoding='utf-8')}" for f in files)
    return PlainTextResponse(body or "product files", headers={"Content-Disposition": "attachment; filename=toolkit.txt"})
