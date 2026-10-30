"""Cover a spoken line with a clip that has no kept speech.

The model returns clip and line ids. The render computes the window.
"""

from __future__ import annotations

import json
import os

from botcut.card import is_card
from botcut.net import post
from botcut.pick import _jpeg_data_url, chat_fields, llm_url

COVER_MAX = 4.0

COVER_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "covers",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["covers"],
            "properties": {
                "covers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["clip", "line"],
                        "properties": {
                            "clip": {"type": "integer"},
                            "line": {"type": "integer"},
                        },
                    },
                }
            },
        },
    },
}

COVER_SYSTEM = (
    "Cover one spoken line with a clip's picture. "
    "Return clip indexes and line ids only. "
    "Do not return times, paths, or a new picture. "
    "A clip covers at most one line. A line takes at most one clip. "
    "Leave a line uncovered when no clip fits."
)


def broll_still_at(duration: float) -> float:
    # Line stills stop 0.05s early. A one-second B-roll frame does not.
    if duration >= 1.0:
        return 1.0
    if duration <= 0:
        return 0.0
    return duration / 2.0


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def candidate_indexes(clips: list[dict], lines: list[dict]) -> list[int]:
    """Non-card clips with no kept line. A clip whose speech was all dropped still counts."""
    taken: set[int] = set()
    for line in lines or []:
        if not isinstance(line, dict) or not line.get("keep"):
            continue
        try:
            taken.add(int(line["clip"]))
        except (KeyError, TypeError, ValueError):
            continue
    found = []
    for index, clip in enumerate(clips or []):
        path = str(clip.get("path") or "") if isinstance(clip, dict) else ""
        if is_card(path) or index in taken:
            continue
        found.append(index)
    return found


def spoken_kept(lines: list[dict]) -> list[dict]:
    found = []
    for line in lines or []:
        if not isinstance(line, dict) or not line.get("keep"):
            continue
        if str(line.get("reason") or "") == "card":
            continue
        try:
            int(line["id"])
        except (KeyError, TypeError, ValueError):
            continue
        found.append(line)
    return found


def accept_covers(claims, *, candidates, kept_ids, speech) -> list[dict]:
    """First valid claim wins. A stored cover is only the clip index and the line id."""
    allowed = set(candidates)
    kept = set(kept_ids)
    talking = set(speech)
    used_clips: set[int] = set()
    used_lines: set[int] = set()
    accepted = []
    if not isinstance(claims, list):
        return []
    for item in claims:
        if not isinstance(item, dict):
            continue
        clip = _as_int(item.get("clip"))
        line = _as_int(item.get("line"))
        if clip is None or line is None:
            continue
        if clip not in allowed or clip in talking or line not in kept:
            continue
        if clip in used_clips or line in used_lines:
            continue
        used_clips.add(clip)
        used_lines.add(line)
        accepted.append({"clip": clip, "line": line})
    return accepted


def fake_claims(candidates: list[int], kept: list[dict]) -> list[dict]:
    """Tray order onto the earliest kept spoken line that is not already covered."""
    ordered = sorted(
        kept,
        key=lambda line: (
            int(line.get("clip") or 0),
            float(line.get("start") or 0),
            int(line["id"]),
        ),
    )
    return [
        {"clip": int(clip), "line": int(line["id"])} for clip, line in zip(candidates, ordered)
    ]


def cover_user_content(clips: list[dict], candidates: list[int], kept: list[dict], stills: dict):
    """Durations and words. No paths and no timestamps."""
    body = [
        "Clips with no kept line. A cover uses that clip's picture from its start. "
        "A still, when one exists, is that clip. Return clip and line ids only."
    ]
    for index in candidates:
        dur = 0.0
        try:
            dur = float(clips[index].get("duration") or 0)
        except (TypeError, ValueError, KeyError):
            dur = 0.0
        body.append(f"clip {index}, {dur:.1f}s")
    body.append("")
    body.append("Spoken lines:")
    for line in kept:
        body.append(f"[{int(line['id'])}] {line.get('text') or ''}")
    text = "\n".join(body)
    ready = [index for index in candidates if stills.get(index) and os.path.isfile(str(stills[index]))]
    if not ready:
        return text
    parts: list[dict] = [{"type": "text", "text": text}]
    for index in ready:
        parts.append({"type": "text", "text": f"Still for clip {index}"})
        parts.append(
            {"type": "image_url", "image_url": {"url": _jpeg_data_url(str(stills[index]))}}
        )
    return parts


def _ask(clips: list[dict], candidates: list[int], kept: list[dict], still_dir: str) -> list:
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")
    from botcut.media import grab_still

    os.makedirs(still_dir, exist_ok=True)
    stills: dict[int, str] = {}
    for index in candidates:
        clip = clips[index]
        try:
            dur = float(clip.get("duration") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        dest = os.path.join(still_dir, f"broll-{index}.jpg")
        # A missed frame still sends the clip. The cut does not stop.
        if grab_still(str(clip.get("path") or ""), broll_still_at(dur), dest):
            stills[index] = dest
    body = {
        **chat_fields(),
        "messages": [
            {"role": "system", "content": COVER_SYSTEM},
            {"role": "user", "content": cover_user_content(clips, candidates, kept, stills)},
        ],
        "response_format": COVER_SCHEMA,
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
        payload = json.loads(response.json()["choices"][0]["message"]["content"])
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        raise SystemExit("LLM response was not a cover list")
    if not isinstance(payload, dict) or not isinstance(payload.get("covers"), list):
        raise SystemExit("LLM response was not a cover list")
    return payload["covers"]


def choose_covers(clips: list[dict], lines: list[dict], still_dir: str) -> list[dict]:
    candidates = candidate_indexes(clips, lines)
    kept = spoken_kept(lines)
    if not candidates or not kept:
        return []
    kept_ids = [int(line["id"]) for line in kept]
    speech = []
    for line in kept:
        try:
            speech.append(int(line["clip"]))
        except (KeyError, TypeError, ValueError):
            continue
    if os.environ.get("BOTCUT_FAKE") == "1":
        claims = fake_claims(candidates, kept)
    else:
        claims = _ask(clips, candidates, kept, still_dir)
    return accept_covers(claims, candidates=candidates, kept_ids=kept_ids, speech=speech)


def kept_covers(covers, lines: list[dict]) -> list[dict]:
    """Drop a cover whose line is no longer kept. Do not add one."""
    alive: set[int] = set()
    for line in lines or []:
        if not isinstance(line, dict) or not line.get("keep"):
            continue
        try:
            alive.add(int(line["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    found = []
    for item in covers or []:
        if not isinstance(item, dict):
            continue
        clip = _as_int(item.get("clip"))
        line = _as_int(item.get("line"))
        if clip is None or line is None or line not in alive:
            continue
        found.append({"clip": clip, "line": line})
    return found


def cover_windows(covers, lines, segments, durations) -> list[dict]:
    """Picture on that line, clipped to the spoken segment. Times are not stored."""
    by_id: dict[int, dict] = {}
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        uid = _as_int(line.get("id"))
        if uid is None:
            continue
        by_id[uid] = line
    raw = []
    for order, item in enumerate(covers or []):
        if not isinstance(item, dict):
            continue
        clip = _as_int(item.get("clip"))
        line_id = _as_int(item.get("line"))
        if clip is None or line_id is None:
            continue
        line = by_id.get(line_id)
        if not line or not line.get("keep") or str(line.get("reason") or "") == "card":
            continue
        try:
            spoken = int(line["clip"])
            line_start = float(line["start"])
            line_end = float(line["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if clip == spoken or clip < 0 or clip >= len(durations):
            continue
        try:
            broll_dur = float(durations[clip] or 0)
        except (TypeError, ValueError):
            continue
        if broll_dur <= 0:
            continue
        chosen = None
        for index, seg in enumerate(segments or []):
            try:
                if int(seg["clip"]) != spoken:
                    continue
                seg_start = float(seg["start"])
                seg_end = float(seg["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if line_end > seg_start and line_start < seg_end:
                chosen = (index, seg_start, seg_end)
                break
        if chosen is None:
            continue
        index, seg_start, seg_end = chosen
        window_start = max(seg_start, line_start)
        # End on the line. A handle can only shorten that, not leave the line playing under B-roll.
        span = min(seg_end, line_end) - window_start
        length = min(broll_dur, span, COVER_MAX)
        if length <= 0.001:
            continue
        raw.append((index, window_start, window_start + length, clip, order))
    by_seg: dict[int, list] = {}
    for item in raw:
        by_seg.setdefault(item[0], []).append(item)
    windows = []
    for index in sorted(by_seg):
        items = sorted(by_seg[index], key=lambda item: (item[1], item[4]))
        cursor = None
        for _index, start, end, clip, _order in items:
            # Stay inside this line. Overlap only shrinks the later window, and none is left if it cannot.
            if cursor is not None and start < cursor:
                start = cursor
            if end - start <= 0.001:
                continue
            windows.append({"segment": index, "start": start, "end": end, "clip": clip})
            cursor = end
    return windows
