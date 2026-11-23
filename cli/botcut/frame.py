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
# The ways a spoken shot can be zoomed. Off is the default.
ZOOMS = ("off", "cuts", "push", "lines")
# On cuts: a framing is held this long before it may change.
ZOOM_HOLD = 4.0
# Slow push: this much closer every second, up to this much.
PUSH_RATE = 0.005
PUSH_MAX = 1.08
# Key lines: a named line shows this much of the frame less, with this lead and tail.
CLOSE_IN = 1.15
CLOSE_LEAD = 0.25
CLOSE_TAIL = 0.40
CLOSE_PIECE_MIN = 0.5
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


def punch_crop(clip: dict, amount: float = PUNCH_IN) -> str:
    """The crop that shows 1/amount of the frame around the speaker, kept inside the picture."""
    width, height = int(clip["width"]), int(clip["height"])
    crop_w = int(width / amount) // 2 * 2
    crop_h = int(height / amount) // 2 * 2
    cx, cy = focus(clip)
    left = min(max(0, round(cx * width - crop_w / 2)), width - crop_w)
    top = min(max(0, round(cy * height - crop_h / 2)), height - crop_h)
    return f"crop={crop_w}:{crop_h}:{left}:{top}"


def _span(row: dict) -> tuple[int, float, float] | None:
    try:
        return int(row["clip"]), float(row["start"]), float(row["end"])
    except (KeyError, TypeError, ValueError):
        return None


def inside_a_line(before: dict, after: dict, lines: list[dict] | None) -> bool:
    """True when the join between two pieces is a cut inside one line, such as an "um" taken out.

    The viewer hears one sentence go on across it, so it is not a place to change the framing.
    """
    left, right = _span(before), _span(after)
    if left is None or right is None or left[0] != right[0]:
        return False
    for line in lines or []:
        if not isinstance(line, dict) or not line.get("keep"):
            continue
        span = _span(line)
        if not span or span[0] != left[0]:
            continue
        if span[1] < left[2] and right[1] < span[2]:
            return True
        # A word cut at the very start or end of a line sits on the line's own edge.
        for cut in line.get("cuts") or []:
            try:
                taken = cut.get("cut") and abs(float(cut["start"]) - left[2]) <= 0.06
                if taken and abs(float(cut["end"]) - right[1]) <= 0.06:
                    return True
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
    return False


def punched(segments: list[dict], clips: list[dict], is_plain, lines: list[dict] | None = None) -> list[bool]:
    """Which segments are shown punched in, for the zoom on cuts.

    A cut inside one shot is a jump: the same framing, a different moment.
    Going from wide to tight across it makes it read as a change of shot. The
    framing changes only at a join between two lines, never at a cut inside a
    line, and only once it has been held for ZOOM_HOLD seconds, so it does not
    flicker. A cut to another shot is already a change, so it starts wide.
    `is_plain(clip)` is true for a shot that may be punched in.
    """
    states: list[bool] = []
    held = 0.0
    for index, seg in enumerate(segments):
        clip = clips[int(seg["clip"])]
        length = max(0.0, float(seg["end"]) - float(seg["start"]))
        before = segments[index - 1] if index else None
        if before is None or int(before["clip"]) != int(seg["clip"]):
            states.append(False)
            held = length
        elif inside_a_line(before, seg, lines) or held < ZOOM_HOLD:
            states.append(states[-1])
            held += length
        else:
            states.append(not states[-1] and is_plain(clip) and can_punch_in(clip))
            held = length
    return states


def push_starts(segments: list[dict], lines: list[dict] | None = None) -> list[float]:
    """How long the slow push has been running when each segment starts.

    The push starts wide at every join between lines and at every new shot.
    Across a cut inside a line it carries on from where it was.
    """
    starts: list[float] = []
    for index, seg in enumerate(segments):
        before = segments[index - 1] if index else None
        if before is not None and inside_a_line(before, seg, lines):
            starts.append(starts[-1] + max(0.0, float(before["end"]) - float(before["start"])))
        else:
            starts.append(0.0)
    return starts


def push_filter(clip: dict, started: float = 0.0) -> str:
    """A slow, even move in toward the speaker, PUSH_RATE a second up to PUSH_MAX.

    `started` is how many seconds the push has already run when this piece
    begins. The picture is resampled between pixels on every frame, so the move
    does not step the way a crop that grows by whole pixels does.
    """
    cx, cy = focus(clip)
    fps = float(clip.get("fps") or 0) or 30.0
    zoom = f"min(1+{PUSH_RATE:g}*(on/{fps:g}+{max(0.0, started):.3f}),{PUSH_MAX:g})"
    left = f"W*{cx:.4f}*(1-1/({zoom}))"
    top = f"H*{cy:.4f}*(1-1/({zoom}))"
    right = f"{left}+W/({zoom})"
    bottom = f"{top}+H/({zoom})"
    return (
        f"perspective=x0='{left}':y0='{top}':x1='{right}':y1='{top}'"
        f":x2='{left}':y2='{bottom}':x3='{right}':y3='{bottom}'"
        ":sense=source:eval=frame:interpolation=cubic"
    )


def close_ids(close: object, lines: list[dict] | None) -> list[int]:
    """The ids of the kept spoken lines named to be shown close, in the order given."""
    kept = set()
    for line in lines or []:
        if not isinstance(line, dict) or not line.get("keep") or str(line.get("reason") or "") == "card":
            continue
        try:
            kept.add(int(line["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    found: list[int] = []
    for value in close if isinstance(close, list) else []:
        if isinstance(value, bool) or not isinstance(value, int) or value not in kept or value in found:
            continue
        found.append(value)
    return found


def close_spans(lines: list[dict] | None, close: object) -> dict[int, list[tuple[float, float]]]:
    """Per shot, the stretches that play close: each named line, out to the middle of the air around it."""
    wanted = set(close_ids(close, lines))
    rows = [(line, _span(line)) for line in lines or [] if isinstance(line, dict)]
    rows = [(line, span) for line, span in rows if span is not None and "id" in line]
    spans: dict[int, list[tuple[float, float]]] = {}
    for line, (clip, start, end) in rows:
        if int(line["id"]) not in wanted:
            continue
        low, high = start - CLOSE_LEAD, end + CLOSE_TAIL
        for other, (other_clip, other_start, other_end) in rows:
            if other is line or other_clip != clip:
                continue
            if other_end <= start:
                low = max(low, (other_end + start) / 2)
            elif other_start >= end:
                high = min(high, (end + other_start) / 2)
        spans.setdefault(clip, []).append((low, high))
    return {clip: sorted(found) for clip, found in spans.items()}


def split_close(piece: dict, spans: list[tuple[float, float]]) -> list[dict]:
    """One piece of a spoken shot as the parts that play wide and the parts that play close.

    The close parts carry `tight`. A part too short to read as a change of
    framing is not split off.
    """
    start, end = float(piece["start"]), float(piece["end"])
    marks = [start]
    for low, high in spans:
        for edge in (low, high):
            if edge - marks[-1] >= CLOSE_PIECE_MIN and end - edge >= CLOSE_PIECE_MIN:
                marks.append(edge)
    marks.append(end)
    parts = []
    for left, right in zip(marks, marks[1:]):
        middle = (left + right) / 2
        part = {**piece, "start": left, "end": right}
        if any(low <= middle <= high for low, high in spans):
            part["tight"] = True
        if parts and bool(parts[-1].get("tight")) == bool(part.get("tight")):
            parts[-1]["end"] = right
        else:
            parts.append(part)
    return parts


def vertical_left(width: int, height: int, cx: float) -> int:
    """The left edge of a 9:16 crop of a wide frame, centered on cx and kept inside the picture."""
    crop_w = int(height * 9 / 16) // 2 * 2
    return min(max(0, round(cx * width - crop_w / 2)), max(0, width - crop_w))
