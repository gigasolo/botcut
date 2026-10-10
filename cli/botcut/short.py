"""Cut one vertical highlight from the rough cut."""

from __future__ import annotations

import json
import os

from botcut.captions import subtitles_filter
from botcut.net import post
from botcut.pick import chat_fields, llm_url

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
        **chat_fields(),
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
    response = post(
        llm_url(),
        key=key,
        label="LLM",
        read_timeout=120,
        send=lambda: {
            "headers": {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            "json": body,
        },
    )
    try:
        parsed = json.loads(response.json()["choices"][0]["message"]["content"])
        return {
            "start_id": int(parsed["start_id"]),
            "end_id": int(parsed["end_id"]),
            "title": str(parsed["title"]).strip(),
        }
    except (ValueError, KeyError, TypeError, IndexError):
        raise SystemExit("LLM response was not a highlight")


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


def short_args(
    start: float,
    duration: float,
    width: int,
    height: int,
    srt_name: str = "short.srt",
    encoder: str = "x264",
    device: str | None = None,
) -> list[str]:
    if encoder not in ("x264", "vaapi"):
        raise SystemExit(f"Unknown encoder {encoder}")
    if encoder == "vaapi" and not device:
        raise SystemExit("VA-API encode needs a device")
    filters = []
    if needs_crop(width, height):
        filters.append("crop=ih*9/16:ih")
    filters.append("scale=1080:1920")
    filters.append(subtitles_filter(srt_name))
    video_filter = ",".join(filters)
    if encoder == "vaapi":
        # No crop_vaapi in this ffmpeg. Download, crop, draw, then upload.
        video_filter = f"hwdownload,format=nv12,{video_filter},format=nv12,hwupload"
        return [
            "-y",
            "-init_hw_device",
            f"vaapi=va:{device}",
            "-filter_hw_device",
            "va",
            "-hwaccel",
            "vaapi",
            "-hwaccel_device",
            str(device),
            "-hwaccel_output_format",
            "vaapi",
            "-ss",
            f"{start:.3f}",
            "-i",
            "rough_cut.mp4",
            "-t",
            f"{duration:.3f}",
            "-vf",
            video_filter,
            "-c:v",
            "h264_vaapi",
            "-qp",
            "20",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            "short.mp4",
        ]
    return [
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        "rough_cut.mp4",
        "-t",
        f"{duration:.3f}",
        "-vf",
        video_filter,
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
