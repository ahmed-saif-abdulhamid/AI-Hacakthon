"""Voice: local text-to-speech and speech-to-text, with a browser fallback when neither is installed."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from proveit import voice

router = APIRouter(prefix="/voice", tags=["voice"])

DEFAULT_AUDIO_SUFFIX = ".webm"
BROWSER_TTS = "browser speechSynthesis"
BROWSER_STT = "browser SpeechRecognition"


class SpeakIn(BaseModel):
    text: str = Field(max_length=1200)


def _unavailable(error: voice.VoiceUnavailable, fallback: str) -> JSONResponse:
    return JSONResponse({"error": str(error), "fallback": fallback}, status_code=503)


@router.post("/speak")
def speak(body: SpeakIn) -> Response:
    try:
        path = voice.synthesize(body.text)
    except voice.VoiceUnavailable as e:
        return _unavailable(e, BROWSER_TTS)
    return FileResponse(path, media_type="audio/wav")


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> Response:
    data = await audio.read()
    suffix = Path(audio.filename or "").suffix or DEFAULT_AUDIO_SUFFIX
    try:
        text = voice.transcribe(data, suffix=suffix)
    except voice.VoiceUnavailable as e:
        return _unavailable(e, BROWSER_STT)
    return JSONResponse({"text": text})


@router.get("/status")
def voice_status() -> dict:
    return {"tts": voice.tts_status(), "stt": voice.stt_status(), "assistant": voice.assistant_name()}
