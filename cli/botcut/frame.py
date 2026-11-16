"""Where the speaker is in the picture, for punch-ins and the vertical short.

The model is shown one still of a shot and returns the face as fractions of
the picture. Nothing here can stop a cut: with no answer, the frame is held on
the middle, a little above center, where a talking head sits.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from botcut.llm import ask

# Punched-in pieces show this much of the frame, around the speaker.
PUNCH_IN = 1.12
# Below this height an enlarged picture starts to look soft, so it is left alone.
PUNCH_MIN_HEIGHT = 1080
DEFAULT_FOCUS = (0.5, 0.38)

FACE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "face",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["found", "x", "y", "w", "h"],
            "properties": {
                "found": {"type": "boolean"},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "w": {"type": "number"},
                "h": {"type": "number"},
            },
        },
    },
}

FACE_PROMPT = (
    "This is one frame of a video of a person talking. Return the box around the speaker's face "
    "as fractions of the picture, from 0 to 1: x and y are its top-left corner, measured from the "
    "left and from the top, and w and h are its width and height. If more than one face shows, "
    "return the one most clearly speaking to the camera. Set found to false, with zeros, when no "
    "face is in the picture."
)

FAKE_FACE = {"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3}


def parse_face(payload) -> dict | None:
    """A box that lies inside the picture, or None."""
    if not isinstance(payload, dict) or payload.get("found") is not True:
        return None
    try:
        x, y, w, h = (float(payload[key]) for key in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= x < 1 and 0 <= y < 1 and 0.02 <= w <= 1 and 0.02 <= h <= 1):
        return None
    if x + w > 1.001 or y + h > 1.001:
        return None
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def ask_face(still: str) -> dict | None:
    if os.environ.get("BOTCUT_FAKE") == "1":
        return dict(FAKE_FACE)
    key = os.environ.get("XAI_API_KEY")
    if not key or not os.path.isfile(still):
        return None
    from botcut.pick import _jpeg_data_url

    try:
        return ask(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": FACE_PROMPT},
                        {"type": "image_url", "image_url": {"url": _jpeg_data_url(still)}},
                    ],
                }
            ],
            FACE_SCHEMA,
            what="a face",
            parse=parse_face,
            read_timeout=60,
        )
    except SystemExit:
        # Framing is a nicety. A cut is never lost for want of it.
        return None


def find_faces(work: str, clips: list[dict], is_spoken) -> None:
    """Note where the speaker is in each spoken shot, once. `is_spoken(clip)` picks the shots."""
    from concurrent.futures import ThreadPoolExecutor

    from botcut.media import grab_still

    stills = os.path.join(work, "stills")
    os.makedirs(stills, exist_ok=True)

    def look(numbered: tuple[int, dict]) -> None:
        index, clip = numbered
        if not is_spoken(clip):
            return
        cache = os.path.join(work, f"{index}-{Path(clip['path']).stem}.face.json")
        try:
            face = parse_face({"found": True, **json.loads(Path(cache).read_text())["face"]})
            known = True
        except (OSError, ValueError, KeyError, TypeError):
            face, known = None, os.path.isfile(cache)
        if not known:
            still = os.path.join(stills, f"face-{index}.jpg")
            # A third of the way in, past the moment of sitting down.
            at = max(0.0, float(clip.get("duration") or 0) / 3)
            face = ask_face(still) if grab_still(clip["path"], at, still) else None
            Path(cache).write_text(json.dumps({"face": face}) + "\n")
        if face:
            clip["face"] = face

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(look, enumerate(clips)))


def focus(clip: dict) -> tuple[float, float]:
    """The point to hold in frame: the middle of the face, or where a talking head usually is."""
    face = parse_face({"found": True, **face}) if isinstance(face := clip.get("face"), dict) else None
    if not face:
        return DEFAULT_FOCUS
    return face["x"] + face["w"] / 2, face["y"] + face["h"] / 2


def can_punch_in(clip: dict) -> bool:
    try:
        return int(clip.get("height") or 0) >= PUNCH_MIN_HEIGHT and int(clip.get("width") or 0) > 0
    except (TypeError, ValueError):
        return False


def punch_crop(clip: dict) -> str:
    """The crop that shows 1/PUNCH_IN of the frame around the speaker, kept inside the picture."""
    width, height = int(clip["width"]), int(clip["height"])
    crop_w = int(width / PUNCH_IN) // 2 * 2
    crop_h = int(height / PUNCH_IN) // 2 * 2
    cx, cy = focus(clip)
    left = min(max(0, round(cx * width - crop_w / 2)), width - crop_w)
    top = min(max(0, round(cy * height - crop_h / 2)), height - crop_h)
    return f"crop={crop_w}:{crop_h}:{left}:{top}"


def punched(segments: list[dict], clips: list[dict], is_plain) -> list[bool]:
    """Which segments are shown punched in.

    A cut inside one shot is a jump: the same framing, a different moment.
    Alternating wide and tight across each one makes it read as a change of
    shot. A cut to another shot is already a change, so it starts wide.
    `is_plain(clip)` is true for a shot that may be punched in.
    """
    states: list[bool] = []
    for index, seg in enumerate(segments):
        clip = clips[int(seg["clip"])]
        jump = index > 0 and int(segments[index - 1]["clip"]) == int(seg["clip"])
        states.append(jump and is_plain(clip) and can_punch_in(clip) and not states[index - 1])
    return states


def vertical_left(width: int, height: int, cx: float) -> int:
    """The left edge of a 9:16 crop of a wide frame, centered on cx and kept inside the picture."""
    crop_w = int(height * 9 / 16) // 2 * 2
    return min(max(0, round(cx * width - crop_w / 2)), max(0, width - crop_w))
