"""Group words into utterances and turn kept ids into padded ranges.

The model returns ids and reasons. It never supplies timestamps.
"""

from __future__ import annotations

import json
import os
import re
import time

import requests

UTTERANCE_GAP = 0.5
MERGE_GAP = 1.0
PAD_BEFORE = 0.15
PAD_AFTER = 0.25
# Token-set overlap, or a 4-token phrase contained in order inside a kept line.
NEAR_JACCARD = 0.5
NEAR_MIN_TOKENS = 4

SYSTEM_PROMPT = (
    "These are takes recorded in order for one video. "
    "When a line is repeated, keep the last complete clean take unless an earlier one is clearly better. "
    'Drop false starts, flubs, "let me redo that", off-topic chatter, and filler-only utterances. '
    "Never drop unique content. Return ids only."
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


def pick(utts: list[dict]) -> list[dict]:
    if os.environ.get("BOTCUT_FAKE") == "1":
        return [{"id": u["id"], "reason": "fake"} for u in utts]
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")
    body = {
        "model": model_name(),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_message(utts)},
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


def model_name() -> str:
    return os.environ.get("BOTCUT_LLM_MODEL") or "grok-4.3"


def llm_url() -> str:
    base = os.environ.get("BOTCUT_LLM_BASE_URL") or "https://api.x.ai/v1"
    return base.rstrip("/") + "/chat/completions"


def _utt(uid: int, clip: int, start: float, end: float, text: str) -> dict:
    return {"id": uid, "clip": clip, "start": start, "end": end, "text": text}


def _user_message(utts: list[dict]) -> str:
    return "\n".join(
        f"[{u['id']}] (clip {u['clip']}, {u['start']:.2f}-{u['end']:.2f}) {u['text']}" for u in utts
    )


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
