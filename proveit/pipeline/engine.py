"""The run loop: execute stages until one needs the founder, the run stops, or it is done.

The model has no tools: agents return data, and only this code calls functions. A transient model
error (rate limit, busy or unreachable service) is waited out a few times in the open; any other error
pauses the run with a plain-words message, and the founder's Try again button continues from that stage.
"""

from __future__ import annotations

import json
import time
import traceback
from collections.abc import Callable

from .. import gates, llm, metrics
from ..log import emit, log_action
from . import run as runs
from .run import FINISHED, WAITING, Run, Stage, Status
from .stages.build import stage_phase3
from .stages.commercial import stage_phase4
from .stages.discover import stage_phase1
from .stages.intake import stage_intake
from .stages.launch import stage_phase5
from .stages.operate import stage_phase6
from .stages.sale_to_cash import stage_payment_test, stage_refund
from .stages.validate import stage_gate2, stage_phase2

STAGES: dict[str, Callable[[Run], None]] = {
    Stage.INTAKE: stage_intake,
    Stage.PHASE1: stage_phase1,
    Stage.PHASE2: stage_phase2,
    Stage.GATE2: stage_gate2,
    Stage.PHASE3: stage_phase3,
    Stage.PHASE4: stage_phase4,
    Stage.PHASE5: stage_phase5,
    Stage.PAYMENT_TEST: stage_payment_test,
    Stage.REFUND: stage_refund,
    Stage.PHASE6: stage_phase6,
}
MAX_STEPS_PER_ADVANCE = 20  # a safety stop; a full run needs about a dozen steps
MAX_BUSY_WAITS = 3
BUSY_WAIT_STEP_S = 20  # waits grow linearly: 20 s, 40 s, 60 s
ERROR_STATE_CHARS, ERROR_LOG_CHARS, TRACEBACK_CHARS = 300, 200, 800
INTERNAL_ERROR_MESSAGE = (
    "Something went wrong on our side at this step. Your run is saved; press Try again to pick up where it stopped."
)


def start(
    brief_text: str,
    fields: dict | None = None,
    mode: str = "live",
    label: str | None = None,
    thresholds: dict | None = None,
) -> str:
    """Create a run with its thresholds pre-registered: hashed and logged before any research."""
    thresholds = thresholds or gates.load_thresholds()
    brief_raw = {"text": brief_text, "fields": {k: v for k, v in (fields or {}).items() if v}}
    sha = gates.thresholds_sha256(thresholds, brief_raw)
    run = runs.create(brief_raw, mode, label, thresholds, sha)
    log_action(
        run.id,
        "gatekeeper",
        "preregister_thresholds",
        model=None,
        cost=0,
        thresholds_sha256=sha,
        thresholds=thresholds["gate1_evidence"],
    )
    (run.dir / "thresholds.json").write_text(
        json.dumps({"thresholds_sha256": sha, "gates": thresholds, "brief": brief_raw}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    run.say("run_started", sha=sha)
    return run.id


def run_pipeline(brief_text: str, fields: dict | None = None, mode: str = "live", label: str | None = None) -> str:
    run_id = start(brief_text, fields, mode, label)
    advance(run_id)
    return run_id


def advance(run_id: str) -> str:
    """Run stages until one needs the founder, the run stops, or it is done. Returns the stage reached."""
    for _ in range(MAX_STEPS_PER_ADVANCE):
        run = runs.load(run_id)
        step = STAGES.get(run.stage)
        if run.stage in FINISHED or run.stage in WAITING or step is None:
            break
        try:
            step(run)
        except llm.LLMError as e:
            if _is_transient(e) and _wait_out_busy_model(run):
                continue
            _pause_on_error(run, str(e), friendly_error(str(e)))
            break
        except Exception as e:
            _pause_on_error(run, str(e), INTERNAL_ERROR_MESSAGE, detail=traceback.format_exc()[-TRACEBACK_CHARS:])
            raise
    run = runs.load(run_id)
    run.state["usage"] = llm.usage(run_id)
    run.save()
    return run.stage


def _is_transient(error: llm.LLMError) -> bool:
    message = str(error).lower()
    return "429" in message or "unreachable" in message


def _wait_out_busy_model(run: Run) -> bool:
    """The free tier is busy: wait visibly and let the loop try the same step again, without the
    founder's help. Returns False once the waits are used up."""
    busy_waits = run.state.get("busy_waits", 0)
    if busy_waits >= MAX_BUSY_WAITS:
        return False
    wait_s = BUSY_WAIT_STEP_S * (busy_waits + 1)
    run.state["busy_waits"] = busy_waits + 1
    run.save()
    log_action(run.id, "orchestrator", "wait_for_busy_model", stage=run.stage, seconds=wait_s)
    emit(
        run.id,
        run.phase,
        "progress",
        f"NVIDIA's free service is busy, so I'm waiting {wait_s} seconds and trying this step again.",
    )
    time.sleep(wait_s)
    return True


def _pause_on_error(run: Run, error: str, message: str, detail: str | None = None) -> None:
    """Keep the run at its stage with status ``error``; the founder sees ``message``, the log keeps ``error``."""
    run.state.pop("busy_waits", None)
    run.state["error"] = detail or error[:ERROR_STATE_CHARS]
    run.state["error_message"] = message
    log_action(run.id, "orchestrator", "stage_failed", stage=run.stage, error=error[:ERROR_LOG_CHARS])
    metrics.increment("stage_failed", stage=run.stage)
    emit(run.id, run.phase, "error", message)
    run.save(status=Status.ERROR)


def friendly_error(raw: str) -> str:
    """Plain words for a founder; the raw text stays in the run state and the log."""
    r = raw.lower()
    if "429" in r or "rate" in r:
        return (
            "The AI service is busy right now, so I paused. Your run is saved: press Try again in "
            "a few seconds and I'll pick up where I stopped."
        )
    if "api_key" in r or "401" in r or "403" in r:
        return (
            "The NVIDIA key is missing or not accepted. Add a valid NVIDIA_API_KEY to .env, or set "
            "LLM_PROVIDER=ollama to use the local model, then press Try again."
        )
    if "unreachable" in r or "timed out" in r or "timeout" in r or "connect" in r:
        return (
            "I couldn't reach the AI model. With Docker the local model may still be downloading; "
            "otherwise check the connection. Then press Try again; your run is saved."
        )
    if "invalid json" in r:
        return "The AI gave an answer I couldn't use. Press Try again and I'll ask it once more."
    return "The AI service returned an error. Your run is saved; press Try again to pick up where it stopped."


def retry(run_id: str) -> dict:
    """The founder's Try again button after an error: clear it and continue from the same step."""
    run = runs.load(run_id)
    if run.state.get("error") is None and run.status != Status.ERROR:
        return {"ok": False, "error": "Nothing needs retrying."}
    run.state.pop("error", None)
    run.state.pop("error_message", None)
    log_action(run.id, "founder", "retry_after_error", stage=run.stage)
    run.save(status=Status.RUNNING)
    return {"ok": True, "stage": run.stage}
