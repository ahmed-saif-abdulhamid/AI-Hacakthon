"""FastAPI service (port 8000): the J.A.R.V.I.S. console (both modes), the JSON API, the
approved landing/store pages, the MOCKED webhook/delivery endpoints and the local voice API.

Published pages are served from the approved blob (keyed by SHA-256), never re-rendered:
an unapproved page returns 409.
"""
from __future__ import annotations

import json
import os
import re
from typing import Literal
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

import delivery
import payments
import refunds
import webhooks
from proveit import approval, ask, db, llm, orchestrator, voice
from proveit.log import entries, telemetry, utcnow
from proveit.startup import check_writable, runs_dir

ROOT = Path(__file__).resolve().parent.parent
DEMO = os.environ.get("PROVEIT_DEMO") == "1"   # read-only public demo of the committed runs
app = FastAPI(title="ProveIt - J.A.R.V.I.S. edition", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8501", "http://127.0.0.1:8501",
                                                  "http://localhost:8000", "http://127.0.0.1:8000"],
                   allow_methods=["*"], allow_headers=["*"])
_env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=select_autoescape(["html", "j2"]))
_workers: dict[str, threading.Thread] = {}
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


DEMO_ALLOWED_POSTS = ("/api/ask", "/api/ask/stream", "/api/voice/speak")
RUN_ID = re.compile(r"r\d{8}-\d{6}-[0-9a-f]{4}")
_RUN_PATH = re.compile(r"^/(?:api/runs|p|store)/([^/]+)")


@app.middleware("http")
async def _valid_run_ids(request: Request, call_next):
    """A run id in the path must look like one, so no path can climb out of the runs folder."""
    m = _RUN_PATH.match(request.url.path)
    if m and not RUN_ID.fullmatch(m.group(1)):
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return await call_next(request)



@app.middleware("http")
async def _demo_read_only(request: Request, call_next):
    """In the public demo nothing can start a run, decide a gate, approve, buy or refund."""
    if DEMO and request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path not in DEMO_ALLOWED_POSTS:
        return JSONResponse({"ok": False, "error": "This public demo is read-only. Run the project locally "
                             "(docker compose up) to start runs and make decisions."}, status_code=403)
    return await call_next(request)


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


# ---- console ---------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/hud")


@app.get("/hud", response_class=HTMLResponse)
def hud(mode: Literal["tactical", "hud", "dual"] = "tactical", embed: int = 0, api: str = ""):
    return _env.get_template("hud.html.j2").render(initial_mode=mode, embed=bool(embed), api_base=api,
                                                   status_table=STATUS_TABLE, demo=DEMO)


@app.get("/api/health")
def health():
    return {"ok": True, "startup_problems": check_writable(), "model": llm.status(),
            "tts": voice.tts_status(), "stt": voice.stt_status(), "status_table": STATUS_TABLE}


@app.get("/api/model")
def model_status():
    return llm.status()


# ---- runs -------------------------------------------------------------------

class RunIn(BaseModel):
    brief_text: str = ""
    fields: dict = {}
    mode: str = "live"
    label: str | None = None


@app.post("/api/runs")
def create_run(body: RunIn):
    if not (body.brief_text.strip() or (body.fields or {}).get("idea")):
        raise HTTPException(422, "the idea is required")
    run_id = orchestrator.start(body.brief_text, body.fields, body.mode if body.mode in ("live", "full") else "live",
                                body.label)
    _advance_bg(run_id)
    return {"run_id": run_id}


def _run_title(run_id: str) -> str | None:
    try:
        st = orchestrator.load(run_id).state
    except Exception:  # noqa: BLE001
        return None
    variants = st.get("variants") or []
    if variants:
        return variants[min(len(variants), st.get("variant_n", 1)) - 1].get("title")
    return ((st.get("brief") or {}).get("idea") or "")[:80] or None


@app.get("/api/runs")
def runs():
    return [dict(r, title=_run_title(r["id"])) for r in orchestrator.list_runs()]


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
    return {
        "run_id": run.id, "label": run.label, "mode": run.mode, "stage": run.stage, "phase": s.get("phase", 1),
        "brief": s.get("brief"), "thresholds_sha256": run.sha, "goalpost_moved": bool(current and current != run.sha),
        "thresholds": s.get("thresholds", {}).get("gate1_evidence"), "variants": s.get("variants", []),
        "variant_n": v, "claims": claims, "metrics": research.get("metrics"), "coverage_rows": research.get("coverage_rows"),
        "gate1": s.get("gate1"), "gate2": s.get("gate2"), "gate3": s.get("gate3"), "gate4": s.get("gate4"),
        "debate": s.get("debate"), "override": s.get("override"), "clarify": s.get("clarify"),
        "pending_approval": s.get("pending_approval"), "usage": llm.usage(run.id) or s.get("usage"),
        "error": s.get("error"), "order": {k: s.get("order", {}).get(k) for k in ("id", "amount")} if s.get("order") else None,
        "files": sorted(p.name for p in run.dir.iterdir() if p.is_file()),
        "working": bool(_workers.get(run.id) and _workers[run.id].is_alive()),
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
    _advance_bg(run_id)
    return {"ok": True}


class DecideIn(BaseModel):
    decision: str
    reason: str = ""


@app.post("/api/runs/{run_id}/decide")
def decide(run_id: str, body: DecideIn):
    res = orchestrator.founder_decide(run_id, body.decision, body.reason)
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
    payload_sha256: str


@app.post("/api/approvals/{approval_id}")
def decide_approval(approval_id: str, body: ApproveIn):
    ap = approval.load(approval_id)
    if ap is None:
        raise HTTPException(404)
    if body.payload_sha256 != ap.payload_sha256:
        raise HTTPException(409, "the payload you saw does not match the payload awaiting approval")
    res = approval.decide(approval_id, body.approve, via="ui")
    orchestrator.on_approval_decided(approval_id)
    _advance_bg(res.run_id)
    return res.model_dump(mode="json")


# ---- Ask J.A.R.V.I.S. ------------------------------------------------------------

class AskIn(BaseModel):
    text: str
    run_id: str | None = None
    history: list[dict] = []


@app.post("/api/ask")
def ask_endpoint(body: AskIn):
    res = ask.handle(body.text, body.run_id, history=body.history[-6:])
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
    from fastapi.responses import StreamingResponse
    res = ask.handle(body.text, body.run_id, history=body.history[-6:], stream=True)

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
            for s in ask.converse_stream(ask.strip_wake(body.text), run, body.history[-6:]):
                said.append(s)
                voice.prerender(s)
                yield json.dumps({"type": "sentence", "text": s}) + "\n"
        except llm.LLMError:
            msg = ask.offline_answer(ask.strip_wake(body.text), run)
            said.append(msg)
            yield json.dumps({"type": "sentence", "text": msg}) + "\n"
        yield json.dumps({"type": "done", "text": " ".join(said)}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/ask/warm")
def ask_warm(body: AskIn):
    """Called when a run is opened in the console: caches its context in the local model (no log entry)."""
    if DEMO or not body.run_id:
        return {"ok": False}
    try:
        run = orchestrator.load(body.run_id)
    except KeyError:
        return {"ok": False}
    threading.Thread(target=ask.warm, args=(run,), daemon=True).start()
    return {"ok": True}


@app.get("/api/presets/{name}")
def preset(name: str):
    if name not in ("weak", "strong"):
        raise HTTPException(404)
    return {"text": (ROOT / "briefs" / f"{name}.md").read_text(encoding="utf-8")}


# ---- voice (local only) ------------------------------------------------------------

class SpeakIn(BaseModel):
    text: str


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
    return {"tts": voice.tts_status(), "stt": voice.stt_status()}


# ---- published pages (approved bytes only) ----------------------------------------------

def _serve(run_id: str, kind: str):
    got = approval.published_payload(run_id, kind)
    if got is None:
        return HTMLResponse("<h1>409: not approved</h1><p>This page has no founder approval.</p>", status_code=409)
    payload, ctype = got
    return HTMLResponse(payload.decode("utf-8"), media_type=ctype.split(";")[0])


@app.get("/p/{run_id}", response_class=HTMLResponse)
def landing(run_id: str):
    return _serve(run_id, "landing")


@app.post("/p/{run_id}/signup", response_class=HTMLResponse)
def signup(run_id: str, email: str = Form(...)):
    if approval.published_payload(run_id, "landing") is None:
        raise HTTPException(409, "not approved")
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,255}", email):
        raise HTTPException(422, "invalid email")
    # Public hosting is STUBBED: every sign-up is a test sign-up and is excluded from every gate.
    db.execute("INSERT INTO signups (run_id, email, ts, test) VALUES (?,?,?,1)", (run_id, email, utcnow()))
    return HTMLResponse("<p>Thanks. Stored: your email and a timestamp (test=true; public hosting is STUBBED).</p>")


@app.get("/store/{run_id}", response_class=HTMLResponse)
def store(run_id: str):
    return _serve(run_id, "store")


@app.post("/store/{run_id}/buy", response_class=HTMLResponse)
def buy(run_id: str):
    if approval.published_payload(run_id, "store") is None:
        raise HTTPException(409, "store not approved")
    run = orchestrator.load(run_id)
    price = float(run.state.get("pricing", {}).get("better", 39))
    provider = payments.MockPaymentProvider()
    order_id = provider.create_order(run_id, price)
    res = webhooks.handle(provider.create_checkout(order_id, price))
    return HTMLResponse(f"<p>Simulated test purchase (MOCKED): order {order_id}.</p>"
                        f"<p><a href='/download/{res['token']}'>Download</a> (24 h link)</p>"
                        f"<form method='post' action='/orders/{order_id}/refund-request'>"
                        "<button>Request refund (needs founder approval)</button></form>")


@app.post("/orders/{order_id}/refund-request")
def refund_request(order_id: str):
    o = db.query_one("SELECT run_id FROM orders WHERE id=?", (order_id,))
    if o is None:
        raise HTTPException(404)
    ap = refunds.request(o["run_id"], order_id)
    return {"approval_id": ap.id, "status": ap.status, "payload_sha256": ap.payload_sha256}


@app.post("/webhooks/mock")
async def webhook(request: Request):
    return webhooks.handle(await request.json())


@app.get("/download/{token}")
def download(token: str):
    try:
        order_id = delivery.check(token)
    except delivery.AccessDenied:
        return PlainTextResponse("403: access revoked or invalid", status_code=403)
    o = db.query_one("SELECT run_id FROM orders WHERE id=?", (order_id,))
    files = sorted((runs_dir() / o["run_id"]).glob("phase3_step*"))
    body = "\n\n".join(f"===== {f.name} =====\n{f.read_text(encoding='utf-8')}" for f in files)
    return PlainTextResponse(body or "product files", headers={"Content-Disposition": "attachment; filename=toolkit.txt"})


@app.exception_handler(approval.ApprovalRequired)
def _approval_required(request, exc):
    return JSONResponse({"error": f"founder approval required for {exc}"}, status_code=409)
