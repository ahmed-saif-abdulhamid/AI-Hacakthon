"""The assistant: answer a question (whole or streamed sentence by sentence), pre-warm a run, load a preset brief."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.background import run_workers
from app.cache import TtlCache
from app.settings import BRIEFS_DIR, DEMO
from proveit import ask, llm, orchestrator, voice
from proveit.orchestrator import Run

router = APIRouter(tags=["assistant"])

HISTORY_TURNS = 6  # recent turns sent to the model with each question
WARM_TTL_S = 300  # a run warmed this recently is not warmed again (it saves the shared model quota)
MAX_WARMED_RUNS = 256
NDJSON = "application/x-ndjson"
PRESETS = ("weak", "strong")

_warmed: TtlCache[bool] = TtlCache(WARM_TTL_S, MAX_WARMED_RUNS)


class AskIn(BaseModel):
    text: str = Field(max_length=2000)
    run_id: str | None = Field(None, max_length=64)
    history: list[dict] = Field(default_factory=list, max_length=20)
    screen: list[str] = Field(default_factory=list, max_length=20)


def _load_or_none(run_id: str | None) -> Run | None:
    if not run_id:
        return None
    try:
        return orchestrator.load(run_id)
    except KeyError:
        return None


def _act_on(answer: dict) -> None:
    """Pre-render the spoken answer and start any run the assistant opened."""
    voice.prerender(answer.get("spoken", ""))
    if answer.get("start_run"):
        run_workers.advance(answer["start_run"])


def _line(kind: str, **fields: object) -> str:
    return json.dumps({"type": kind, **fields}) + "\n"


@router.post("/ask")
def ask_endpoint(body: AskIn) -> dict:
    answer = ask.handle(body.text, body.run_id, history=body.history[-HISTORY_TURNS:], screen=body.screen)
    _act_on(answer)
    return answer


@router.post("/ask/stream")
def ask_stream(body: AskIn) -> StreamingResponse:
    """NDJSON: one "meta" line, then one "sentence" line per spoken sentence, then "done".

    Sentences are spoken as they arrive, so the first words play about a second after the
    model starts instead of after the whole answer.
    """
    history = body.history[-HISTORY_TURNS:]
    answer = ask.handle(body.text, body.run_id, history=history, stream=True, screen=body.screen)

    def fixed_answer() -> Iterator[str]:
        _act_on(answer)
        spoken = answer.get("spoken", "")
        yield _line("meta", **answer)
        yield _line("sentence", text=spoken)
        yield _line("done", text=spoken)

    def conversation() -> Iterator[str]:
        yield _line("meta", intent=answer["intent"], detail=answer.get("text", ""))
        run = _load_or_none(body.run_id)
        question = ask.strip_wake(body.text)
        said = []
        try:
            for sentence in ask.converse_stream(question, run, history, screen=body.screen):
                said.append(sentence)
                voice.prerender(sentence)
                yield _line("sentence", text=sentence)
        except llm.LLMError:
            fallback = ask.offline_answer(question, run)
            said.append(fallback)
            yield _line("sentence", text=fallback)
        yield _line("done", text=" ".join(said))

    return StreamingResponse(conversation() if answer.get("converse") else fixed_answer(), media_type=NDJSON)


@router.post("/ask/warm")
def ask_warm(body: AskIn) -> dict:
    """Called when a run is opened in the console: pre-reads its context so the first answer is quick."""
    run = None if DEMO else _load_or_none(body.run_id)
    if run is None or not _warmed.add(run.id, True):
        return {"ok": False}
    threading.Thread(target=ask.warm, args=(run,), daemon=True, name=f"warm-{run.id}").start()
    return {"ok": True}


@router.get("/presets/{name}")
def preset(name: str) -> dict:
    if name not in PRESETS:
        raise HTTPException(404)
    return {"text": (BRIEFS_DIR / f"{name}.md").read_text(encoding="utf-8")}
