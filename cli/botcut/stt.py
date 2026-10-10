"""xAI speech-to-text. The API key stays in the Authorization header."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from botcut.net import post

STT_URL = "https://api.x.ai/v1/stt"
STT_MODEL = "grok-voice-transcribe-2.0"
STT_FIELDS = ("model", "language", "filler_words", "file")


def fixture_path() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "words_retake.json"


def transcribe_fake() -> dict:
    data = json.loads(fixture_path().read_text())
    return {"duration": float(data["duration"]), "words": [_word(w) for w in data["words"]]}


def transcribe_xai(flac: str) -> dict:
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")

    def send() -> dict:
        handle = open(flac, "rb")
        return {
            "headers": {"Authorization": f"Bearer {key}"},
            "files": [
                ("model", (None, STT_MODEL)),
                ("language", (None, "en")),
                ("filler_words", (None, "true")),
                ("file", (os.path.basename(flac), handle, "audio/flac")),
            ],
        }

    response = post(STT_URL, key=key, label="STT", read_timeout=300, send=send)
    try:
        data = response.json()
        return {
            "duration": float(data.get("duration") or 0),
            "words": [_word(w) for w in data.get("words") or []],
        }
    except (ValueError, KeyError, TypeError):
        raise SystemExit("STT response was not a transcript")


def transcribe_local(flac: str, model: str, stem: str) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit("Install local STT: uv sync --extra local") from exc
    started = time.perf_counter()
    whisper = WhisperModel(model, device="cpu", compute_type="int8")
    segments, info = whisper.transcribe(flac, language="en", word_timestamps=True, vad_filter=True)
    words = []
    for segment in segments:
        for word in segment.words or []:
            text = str(word.word).strip()
            if text:
                words.append({"text": text, "start": float(word.start), "end": float(word.end)})
    wall = max(time.perf_counter() - started, 1e-6)
    duration = float(getattr(info, "duration", 0) or 0)
    if duration <= 0 and words:
        duration = words[-1]["end"]
    print(f"local STT {stem}: {duration:.1f}s in {wall:.1f}s ({duration / wall:.1f}x realtime)")
    return {"duration": duration, "words": words}


def _word(word: dict) -> dict:
    return {"text": str(word["text"]), "start": float(word["start"]), "end": float(word["end"])}
