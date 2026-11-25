"""xAI speech-to-text. The API key stays in the Authorization header."""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import time
from pathlib import Path

from botcut.net import post

STT_URL = "https://api.x.ai/v1/stt"
STT_MODEL = "grok-voice-transcribe-2.0"
STT_FIELDS = ("model", "language", "filler_words", "file")
# xAI takes this many words to lean toward, each this long at most.
KEY_TERMS_MAX = 100
KEY_TERM_CHARS = 50

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9&+-]*")


def names_path() -> Path:
    """The person's own list of names and product words, one a line, kept across movies."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "botcut" / "names.txt"


def _listed_names() -> list[str]:
    try:
        rows = names_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    names = (" ".join(row.split()) for row in rows)
    return [name for name in names if name and not name.startswith("#")]


def _is_name(word: str, opens: bool) -> bool:
    """A capital that is not just the start of a sentence: Lynn, MCP, VirtualPBX, 3CX."""
    if word == "I" or not any(letter.isalpha() for letter in word):
        return False
    if any(letter.isupper() for letter in word[1:]):
        return True
    return word[0].isupper() and not opens


def names_in(sentence: str) -> list[str]:
    """The names in a sentence. Names side by side are one name: "Lynn Baker"."""
    found: list[str] = []
    # Where the last name ended, or -1 when the word before this one was not a name.
    name_end = -1
    text = str(sentence or "")
    for match in _WORD.finditer(text):
        lead = text[: match.start()].rstrip()
        opens = not lead or lead[-1] in ".!?:"
        word = match.group(0)
        if not _is_name(word, opens):
            name_end = -1
            continue
        if name_end >= 0 and text[name_end : match.start()].isspace():
            found[-1] = f"{found[-1]} {word}"
        else:
            found.append(word)
        name_end = match.end()
    return found


def key_terms(intent: str = "") -> list[str]:
    """Words to lean the transcript toward: the kept list first, then names in the movie sentence."""
    terms: list[str] = []
    seen: set[str] = set()
    for name in [*_listed_names(), *names_in(intent)]:
        if len(name) > KEY_TERM_CHARS or name.lower() in seen:
            continue
        seen.add(name.lower())
        terms.append(name)
        if len(terms) == KEY_TERMS_MAX:
            break
    return terms


def terms_mark(terms: list[str] | tuple[str, ...]) -> str:
    """A short mark for a list of key terms, so a transcript made with another list is not reused."""
    if not terms:
        return ""
    return "+" + hashlib.sha1("\n".join(terms).encode("utf-8")).hexdigest()[:6]


def fixture_path() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "words_retake.json"


def transcribe_fake() -> dict:
    data = json.loads(fixture_path().read_text())
    return {"duration": float(data["duration"]), "words": [_word(w) for w in data["words"]]}


def transcribe_xai(flac: str, terms: list[str] | tuple[str, ...] = ()) -> dict:
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
                # Options go before the file. xAI may not read one that comes after it.
                *(("keyterm", (None, term)) for term in terms),
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


@functools.lru_cache(maxsize=1)
def _whisper_model(model: str, device: str = "cpu", compute_type: str = "int8"):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit("Install local STT: uv sync --extra local") from exc
    return WhisperModel(model, device=device, compute_type=compute_type)


def transcribe_local(
    flac: str, model: str, stem: str, terms: list[str] | tuple[str, ...] = ()
) -> dict:
    started = time.perf_counter()
    whisper = _whisper_model(model, "cpu", "int8")
    segments, info = whisper.transcribe(
        flac,
        language="en",
        word_timestamps=True,
        vad_filter=True,
        hotwords=", ".join(terms) or None,
    )
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
