"""Group words into utterances and turn kept ids into padded ranges.

The model returns ids and reasons. It never supplies timestamps.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path

import requests

UTTERANCE_GAP = 0.5
MERGE_GAP = 1.0
PAD_BEFORE = 0.25
PAD_AFTER = 0.40
# Token-set overlap, or a 4-token phrase contained in order inside a kept line.
NEAR_JACCARD = 0.5
NEAR_MIN_TOKENS = 4

DEFAULT_INTENT = (
    "Keep each moment in order. Drop flubs and true retakes. Keep a beat that appears only once."
)

RETAKE_PROMPT = (
    "These are takes recorded in order for one video. "
    "When a line is repeated, keep the last complete clean take unless an earlier one is clearly better. "
    'Drop false starts, flubs, "let me redo that", off-topic chatter, and filler-only utterances. '
    "Never drop unique content. Return ids only."
)

STORY_PROMPT = (
    "These clips are one movie, in order. "
    "Drop false starts, flubs, and filler-only lines. "
    "When the same line is a retake, keep the last clean one. "
    "Keep a beat that appears only once. "
    "Do not drop a clip that has its own content. "
    "Return ids only."
)

KEEP_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "keep",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["keep"],
            "properties": {
                "keep": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "reason"],
                        "properties": {
                            "id": {"type": "integer"},
                            "reason": {"type": "string"},
                        },
                    },
                }
            },
        },
    },
}

RETRY_STATUS = {429, 503}
RETRY_DELAYS = (1.0, 2.0, 4.0)


def utterances(words_by_clip: list[list[dict]]) -> list[dict]:
    found = []
    next_id = 0
    for clip, words in enumerate(words_by_clip):
        current = None
        for word in words:
            text = str(word["text"]).strip()
            start = float(word["start"])
            end = float(word["end"])
            if not text:
                continue
            if current is None:
                current = _utt(next_id, clip, start, end, text)
                next_id += 1
                continue
            if start - current["end"] > UTTERANCE_GAP:
                found.append(current)
                current = _utt(next_id, clip, start, end, text)
                next_id += 1
            else:
                current["end"] = end
                current["text"] = f"{current['text']} {text}"
        if current is not None:
            found.append(current)
    return found


def pick(utts: list[dict], intent: str = "") -> list[dict]:
    if os.environ.get("BOTCUT_FAKE") == "1":
        return [{"id": u["id"], "reason": "fake"} for u in utts]
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")
    body = {
        **chat_fields(),
        "messages": [
            {"role": "system", "content": system_prompt(intent)},
            {"role": "user", "content": user_content(utts)},
        ],
        "response_format": KEEP_SCHEMA,
    }
    url = llm_url()
    for attempt in range(len(RETRY_DELAYS) + 1):
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=120,
        )
        if response.status_code in RETRY_STATUS and attempt < len(RETRY_DELAYS):
            time.sleep(RETRY_DELAYS[attempt])
            continue
        if response.status_code != 200:
            raise SystemExit(f"LLM HTTP {response.status_code}: {_safe_body(response.text, key)}")
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return [{"id": int(item["id"]), "reason": str(item["reason"])} for item in parsed["keep"]]
    raise SystemExit("LLM request failed")


def segments(utts: list[dict], keep: list[dict], durations: list[float]) -> tuple[list[dict], list[int]]:
    by_id = {u["id"]: u for u in utts}
    chosen = []
    unknown = []
    for item in keep:
        uid = int(item["id"])
        utt = by_id.get(uid)
        if utt is None:
            unknown.append(uid)
            continue
        chosen.append({**utt, "reason": str(item["reason"])})
    chosen.sort(key=lambda utt: (utt["clip"], utt["start"], utt["id"]))
    # Merge on the unpadded gap. The later utterance's reason wins.
    merged: list[dict] = []
    for utt in chosen:
        if merged and merged[-1]["clip"] == utt["clip"] and utt["start"] - merged[-1]["end"] < MERGE_GAP:
            merged[-1]["end"] = max(merged[-1]["end"], utt["end"])
            merged[-1]["reason"] = utt["reason"]
        else:
            merged.append(
                {
                    "clip": utt["clip"],
                    "start": utt["start"],
                    "end": utt["end"],
                    "reason": utt["reason"],
                }
            )
    padded = []
    for seg in merged:
        dur = durations[seg["clip"]]
        start = max(0.0, seg["start"] - PAD_BEFORE)
        end = min(dur, seg["end"] + PAD_AFTER)
        if end <= start:
            continue
        padded.append({"clip": seg["clip"], "start": start, "end": end, "reason": seg["reason"]})
    collapsed: list[dict] = []
    for seg in padded:
        if collapsed and collapsed[-1]["clip"] == seg["clip"] and seg["start"] <= collapsed[-1]["end"]:
            collapsed[-1]["end"] = max(collapsed[-1]["end"], seg["end"])
            collapsed[-1]["reason"] = seg["reason"]
        else:
            collapsed.append(dict(seg))
    return collapsed, unknown


def snap(segments: list[dict], silences_by_clip: list[list[tuple[float, float]]]) -> list[dict]:
    snapped = []
    for seg in segments:
        sils = _silences_for(silences_by_clip, seg["clip"])
        start, end = float(seg["start"]), float(seg["end"])
        for silence_start, silence_end in sils:
            if silence_start <= start < silence_end:
                start = silence_end - 0.10
                break
        for silence_start, silence_end in sils:
            if silence_start < end <= silence_end:
                end = silence_start + 0.15
                break
        if end - start < 0.3:
            snapped.append(dict(seg))
        else:
            snapped.append({**seg, "start": max(0.0, start), "end": end})
    return snapped


def tighten(
    segments: list[dict],
    silences_by_clip: list[list[tuple[float, float]]],
    max_pause: float,
) -> list[dict]:
    tightened = []
    for seg in segments:
        pieces = [dict(seg)]
        for silence_start, silence_end in _silences_for(silences_by_clip, seg["clip"]):
            if silence_end - silence_start <= max_pause:
                continue
            nxt = []
            for piece in pieces:
                if silence_start >= piece["start"] and silence_end <= piece["end"]:
                    left_end = silence_start + 0.15
                    right_start = silence_end - 0.15
                    if left_end - piece["start"] > 0:
                        nxt.append({**piece, "end": left_end})
                    if piece["end"] - right_start > 0:
                        nxt.append({**piece, "start": right_start})
                else:
                    nxt.append(piece)
            pieces = nxt
        tightened.extend(pieces)
    return tightened


def _silences_for(silences_by_clip: list[list[tuple[float, float]]], clip: int):
    if clip < 0 or clip >= len(silences_by_clip):
        return []
    return silences_by_clip[clip]


def dropped_utterances(utts: list[dict], keep: list[dict]) -> list[dict]:
    by_id = {u["id"]: u for u in utts}
    kept = {int(item["id"]) for item in keep if int(item["id"]) in by_id}
    return [u for u in utts if u["id"] not in kept]


def kept_utterances(utts: list[dict], keep: list[dict]) -> list[dict]:
    by_id = {u["id"]: u for u in utts}
    return [by_id[int(item["id"])] for item in keep if int(item["id"]) in by_id]


def unique_warnings(dropped: list[dict], kept: list[dict]) -> list[str]:
    lines = []
    for utt in dropped:
        if any(near_duplicate(utt["text"], other["text"]) for other in kept):
            continue
        lines.append(f"unique? id {utt['id']}: {utt['text']}")
    return lines


def unknown_warnings(ids: list[int]) -> list[str]:
    return [f"unknown id {uid}" for uid in ids]


def near_duplicate(left: str, right: str) -> bool:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return False
    if _jaccard(a, b) >= NEAR_JACCARD:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= NEAR_MIN_TOKENS and _in_order(short, long)


def system_prompt(intent: str = "") -> str:
    """Story prompt by default. A line about repeated takes keeps the retake prompt.

    The default sentence mentions retakes as something to drop, so that wording
    stays on the story prompt.
    """
    line = intent.strip() or DEFAULT_INTENT
    if _retake_job(line):
        return f"{RETAKE_PROMPT}\nThe movie is: {line}"
    return f"{STORY_PROMPT}\nThe movie is: {line}"


def _retake_job(intent: str) -> bool:
    text = intent.lower()
    if text == DEFAULT_INTENT.lower():
        return False
    return "repeated take" in text or "retake" in text


def decision_lines(utts: list[dict], keep: list[dict]) -> list[dict]:
    reasons = {int(item["id"]): str(item["reason"]) for item in keep}
    kept = kept_utterances(utts, keep)
    dropped = dropped_utterances(utts, keep)
    drop_reason = {}
    for utt in dropped:
        if any(near_duplicate(utt["text"], other["text"]) for other in kept):
            drop_reason[int(utt["id"])] = "retake"
        else:
            drop_reason[int(utt["id"])] = "unique?"
    rows = []
    for utt in utts:
        uid = int(utt["id"])
        kept_reason = reasons.get(uid)
        row = {
            "id": uid,
            "clip": int(utt["clip"]),
            "start": float(utt["start"]),
            "end": float(utt["end"]),
            "text": str(utt["text"]),
            "keep": kept_reason is not None,
            "reason": kept_reason if kept_reason is not None else drop_reason.get(uid, "dropped"),
        }
        still = str(utt.get("still") or "")
        if still and os.path.isfile(still):
            row["still"] = os.path.abspath(still)
        rows.append(row)
    return rows


def model_name() -> str:
    return os.environ.get("BOTCUT_LLM_MODEL") or "grok-4.7"


def reasoning_effort(model: str) -> str | None:
    """Low effort for Grok 4.5 and newer. Older chat models omit the field."""
    name = model.split("/")[-1]
    if not name.startswith("grok-4."):
        return None
    minor = name.removeprefix("grok-4.").split("-", 1)[0]
    if minor.isdigit() and int(minor) >= 5:
        return "low"
    return None


def chat_fields(model: str | None = None) -> dict:
    chosen = model_name() if model is None else model
    fields: dict = {"model": chosen}
    effort = reasoning_effort(chosen)
    if effort:
        fields["reasoning_effort"] = effort
    return fields


def llm_url() -> str:
    base = os.environ.get("BOTCUT_LLM_BASE_URL") or "https://api.x.ai/v1"
    return base.rstrip("/") + "/chat/completions"


def _utt(uid: int, clip: int, start: float, end: float, text: str) -> dict:
    return {"id": uid, "clip": clip, "start": start, "end": end, "text": text}


# A long interview can have more stills than one request should carry.
MAX_STILLS = 40


def _user_message(utts: list[dict]) -> str:
    return "\n".join(
        f"[{u['id']}] (clip {u['clip']}, {u['start']:.2f}-{u['end']:.2f}) {u['text']}" for u in utts
    )


def user_content(utts: list[dict]) -> str | list[dict]:
    """Text when no still exists. Otherwise the lines, then one JPEG per shown line."""
    ready = [u for u in utts if u.get("still") and os.path.isfile(str(u["still"]))]
    if not ready:
        return _user_message(utts)
    if len(ready) > MAX_STILLS:
        step = len(ready) / MAX_STILLS
        ready = [ready[int(i * step)] for i in range(MAX_STILLS)]
    parts: list[dict] = [
        {
            "type": "text",
            "text": (
                "A still from the middle of a line follows that line when one exists. "
                "Drop a blurred, dark, or unusable picture. Keep a clean look. "
                "Return ids and reasons only. A reason may mention the picture.\n\n"
                + _user_message(utts)
            ),
        }
    ]
    for utt in ready:
        parts.append({"type": "text", "text": f"Still for [{int(utt['id'])}]"})
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": _jpeg_data_url(str(utt["still"]))},
            }
        )
    return parts


def _jpeg_data_url(path: str) -> str:
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return "data:image/jpeg;base64," + encoded


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _jaccard(a: list[str], b: list[str]) -> float:
    left, right = set(a), set(b)
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _in_order(short: list[str], long: list[str]) -> bool:
    index = 0
    for token in long:
        if index < len(short) and token == short[index]:
            index += 1
    return index == len(short)


def _safe_body(text: str, key: str) -> str:
    return text.replace(key, "[redacted]")[:300]
