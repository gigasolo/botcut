"""Cut one vertical highlight from the rough cut."""

from __future__ import annotations

import json
import os
import time

import requests

from botcut.captions import subtitles_filter
from botcut.pick import RETRY_DELAYS, RETRY_STATUS, _safe_body, llm_url, model_name

HIGHLIGHT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "highlight",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["start_id", "end_id", "title"],
            "properties": {
                "start_id": {"type": "integer"},
                "end_id": {"type": "integer"},
                "title": {"type": "string"},
            },
        },
    },
}


def pick_highlight(utts: list[dict]) -> dict:
    if os.environ.get("BOTCUT_FAKE") == "1":
        ids = [int(utt["id"]) for utt in utts]
        if not ids:
            raise SystemExit("No utterances to highlight")
        chosen = ids[:3]
        return {"start_id": chosen[0], "end_id": chosen[-1], "title": "Fake highlight"}
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")
    body = {
        "model": model_name(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Choose one contiguous highlight from these kept takes. "
                    "Return a start id, an end id, and a title. Never return timestamps."
                ),
            },
            {"role": "user", "content": _user_message(utts)},
        ],
        "response_format": HIGHLIGHT_SCHEMA,
    }
    for attempt in range(len(RETRY_DELAYS) + 1):
        response = requests.post(
            llm_url(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=120,
        )
        if response.status_code in RETRY_STATUS and attempt < len(RETRY_DELAYS):
            time.sleep(RETRY_DELAYS[attempt])
            continue
        if response.status_code != 200:
            raise SystemExit(f"LLM HTTP {response.status_code}: {_safe_body(response.text, key)}")
        parsed = json.loads(response.json()["choices"][0]["message"]["content"])
        return {
            "start_id": int(parsed["start_id"]),
            "end_id": int(parsed["end_id"]),
            "title": str(parsed["title"]).strip(),
        }
    raise SystemExit("LLM request failed")


def kept_on_cut(utts: list[dict], segments: list[dict]) -> list[dict]:
    kept = []
    for utt in utts:
        for seg in segments:
            if int(seg["clip"]) != int(utt["clip"]):
                continue
            if float(utt["start"]) < float(seg["end"]) and float(utt["end"]) > float(seg["start"]):
                kept.append(utt)
                break
    return kept


def highlight_span(
    segments: list[dict],
    words_by_clip: list[list[dict]],
    utts: list[dict],
    start_id: int,
    end_id: int,
) -> tuple[float, float]:
    lo, hi = sorted((int(start_id), int(end_id)))
    chosen = [utt for utt in utts if lo <= int(utt["id"]) <= hi]
    if not chosen:
        raise SystemExit(f"Highlight ids {lo}..{hi} match no utterances")
    spans: list[tuple[float, float]] = []
    timeline = 0.0
    for seg in segments:
        seg_start = float(seg["start"])
        seg_end = float(seg["end"])
        length = max(0.0, seg_end - seg_start)
        clip = int(seg["clip"])
        words = words_by_clip[clip] if 0 <= clip < len(words_by_clip) else []
        overlapping = [
            utt
            for utt in chosen
            if int(utt["clip"]) == clip
            and float(utt["start"]) < seg_end
            and float(utt["end"]) > seg_start
        ]
        for word in words:
            wstart = float(word["start"])
            if not (seg_start <= wstart < seg_end):
                continue
            if not any(float(utt["start"]) <= wstart < float(utt["end"]) for utt in overlapping):
                continue
            mapped_start = timeline + (wstart - seg_start)
            mapped_end = min(timeline + length, timeline + (float(word["end"]) - seg_start))
            if mapped_end < mapped_start:
                mapped_end = mapped_start
            spans.append((mapped_start, mapped_end))
        timeline += length
    if not spans:
        raise SystemExit(f"Highlight ids {lo}..{hi} have no words on the rough cut")
    return spans[0][0], spans[-1][1]


def needs_crop(width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        raise SystemExit("Rough cut has no video size")
    # Already 9:16 or taller: scale only. Wider frames get a center crop.
    return (height / width) < (16 / 9)


def short_args(start: float, duration: float, width: int, height: int, srt_name: str = "short.srt") -> list[str]:
    filters = []
    if needs_crop(width, height):
        filters.append("crop=ih*9/16:ih")
    filters.append("scale=1080:1920")
    filters.append(subtitles_filter(srt_name))
    return [
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        "rough_cut.mp4",
        "-t",
        f"{duration:.3f}",
        "-vf",
        ",".join(filters),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        "short.mp4",
    ]


def _user_message(utts: list[dict]) -> str:
    lines = [
        "Pick one contiguous id range of about 30 to 60 seconds and a title of at most 60 characters.",
        "If nothing fits that length, still return the best contiguous range.",
        "",
    ]
    for utt in utts:
        lines.append(f"[{utt['id']}] ({utt['start']:.2f}-{utt['end']:.2f}) {utt['text']}")
    return "\n".join(lines)
