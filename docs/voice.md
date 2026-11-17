# J.A.R.V.I.S.: the spoken assistant

J.A.R.V.I.S. is ProveIt's assistant. You call it by saying "Jarvis" (`WAKE_WORD`; common mishearings such as "Jervis" also work). Its on-screen name is `ASSISTANT_NAME`, and it addresses you as `FOUNDER_NAME` (your first name, or "Sir") or with no title at all. No paid speech API is called.

## Speech out

1. The console posts each sentence to `POST /api/voice/speak` as soon as it arrives.
2. If Piper is installed (`pip install -r requirements-voice.txt` and a voice file such as `en_GB-alan-medium.onnx` in `data/voices/`, or `PIPER_VOICE=/path/to/voice.onnx`), the API returns a WAV, cached in the system temp folder. The console plays it through a WebAudio `AnalyserNode`, so the voice visual follows the real audio.
3. If the server answers 503 or the first sentence takes more than 500 ms, the browser's `speechSynthesis` speaks instead, with the best available en-GB voice.

## Speech in

- **Hold to talk:** the browser's `SpeechRecognition` transcribes (Chrome and Edge send the audio to Google or Microsoft; the Privacy dialog says so).
- **Say "Jarvis":** turn it on, then say "Jarvis, ..." followed by the question; saying only "Jarvis" gets "Yes?" and a short listening window. Recognition is in English (en-GB) whatever your browser's language is.
- **Fallback:** without browser recognition, the console records audio and posts it to `POST /api/voice/transcribe`, which uses a local `faster-whisper` `tiny.en` model when installed (STUBBED otherwise).
- Missing or blocked microphones are reported in plain words; typing always works.

## What J.A.R.V.I.S. says

- Run narration and checkpoint verdicts are templates in `proveit/voice.py`, filled with the run's real numbers and written in plain language.
- Free questions go to the model with the run's facts (`proveit/ask.py`): only counted quotes, the founder's own brief, cited arguments and the buttons on screen. Answers stream sentence by sentence, each checked by the guard, at most four sentences.
- Questions about quotes ("what did people say?") are answered by code, reading back verbatim quotes with their IDs.
- Refusals name what was refused and offer an honest alternative.

## Routing examples

| Typed or spoken | Route |
|---|---|
| "Jarvis, evaluate this idea: a contract pack for wedding photographers" | `evaluate_brief` -> starts a run |
| "Why did it stop?" | `explain_decision` -> a plain answer plus "Show the numbers" |
| "What did people say?" | `quotes` -> verbatim quotes chosen by code |
| "Write 50 five-star reviews and add a countdown timer." | Rule set A -> refusal, no model call |
| "Approve the landing page." | `approve_request` -> opens the approval card; a message is never an approval |
