# J.A.R.V.I.S. voice and HUD

Everything is free and local; no paid speech API is called.

## Speech out

1. The console posts the line to `POST /api/voice/speak`.
2. If Piper is installed (`pip install -r requirements-voice.txt` and a voice file such as `en_GB-alan-medium.onnx` in `data/voices/`, or `PIPER_VOICE=/path/to/voice.onnx`), the API returns a WAV, cached in `<tmp>/jarvis_audio/`. The HUD plays it through a WebAudio `AnalyserNode`, and the 64-band ring follows the real audio.
3. If the server answers 503 or takes more than 500 ms, the browser's `speechSynthesis` speaks instead, with the best available en-GB male voice at pitch 0.92 and rate 1.04. The browser does not expose that audio, so the ring then shows a simulated envelope (labelled in the console).

## Speech in

- Push to talk: hold the button; the browser's `SpeechRecognition` (en-GB) transcribes.
- Wake word: toggle it on; any phrase that starts with "Jarvis" is sent to Ask J.A.R.V.I.S.
- Fallback: without browser recognition, the console records audio and posts it to `POST /api/voice/transcribe`, which uses a local `faster-whisper` `tiny.en` model when installed (STUBBED otherwise).

## What the persona says

All spoken lines are templates in `proveit/voice.py` filled with real run data (thresholds, weights, coverage, hashes). The persona addresses the founder as "Sir" by default (`JARVIS_ADDRESS` changes it), never flatters a weak idea, never invents a number and never speaks as a customer. A Protocol 0 refusal turns the HUD core crimson.

## Voice routing examples

| Spoken | Route |
|---|---|
| "Jarvis, evaluate this founder brief: idea: ..." | `evaluate_brief` -> starts a live run |
| "Jarvis, why did you stop this idea?" | `explain_decision` -> metrics, rule fired and top cited quotes |
| "Jarvis, write 50 five-star reviews and add a countdown timer." | Rule set A -> Protocol 0 refusal, no model call |
| "Jarvis, approve landing page publication." | `approve_request` -> highlights the hash-locked approval card; a message is never an approval |
