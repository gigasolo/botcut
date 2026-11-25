"""Where the speaker is in the picture, for punch-ins and the vertical short.

The model is shown one still of a shot and returns the face as fractions of
the picture. Nothing here can stop a cut: with no answer, the frame is held on
the middle, a little above center, where a talking head sits.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from botcut.llm import ask

# Punched-in pieces show this much of the frame, around the speaker.
PUNCH_IN = 1.08
# Below this height an enlarged picture starts to look soft, so it is left alone.
PUNCH_MIN_HEIGHT = 1080
# The ways a spoken shot can be zoomed. Off is the default.
# Three editorial auto-framing intensities (subtle, medium, bold) plus legacy aliases.
ZOOMS = ("off", "subtle", "medium", "bold", "auto", "cuts", "push", "lines")
AUTO_ZOOMS = ("subtle", "medium", "bold", "auto")
# Auto: default (medium) tight framing — subtle "invisible B-cam" jump-cut mask.
TIGHT = 1.10
# Auto: a wide stretch has to run this long before it is worth a slow push.
PUSH_STRETCH = 8.0
# A face found this far from the moment being framed says nothing about it.
FACE_REACH = 20.0
# On cuts: a framing is held this long before it may change.
ZOOM_HOLD = 4.0
# Auto framing: ignore tiny micro-trims so small pause cuts don't cause unnecessary zoom hops.
SMALL_JUMP_GAP = 0.45
# Slow push: this much closer every second, up to this much.
PUSH_RATE = 0.003
PUSH_MAX = 1.05
# Key lines: a named line shows this much of the frame less, with this lead and tail.
CLOSE_IN = 1.10

ZOOM_PROFILES: dict[str, dict[str, float]] = {
    "subtle": {
        "tight": 1.06,
        "push_rate": 0.002,
        "push_max": 1.03,
        "hold": 8.0,
        "push_stretch": 10.0,
    },
    "medium": {
        "tight": 1.10,
        "push_rate": 0.003,
        "push_max": 1.05,
        "hold": 6.0,
        "push_stretch": 8.0,
    },
    "bold": {
        "tight": 1.15,
        "push_rate": 0.0045,
        "push_max": 1.07,
        "hold": 4.5,
        "push_stretch": 7.0,
    },
}


def zoom_profile(zoom: str) -> dict[str, float]:
    """Return the framing profile for subtle, medium (or legacy auto), or bold."""
    key = "medium" if zoom == "auto" else zoom
    return dict(ZOOM_PROFILES.get(key, ZOOM_PROFILES["medium"]))
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


def _ask_face(still: str) -> tuple[bool, dict | None]:
    if os.environ.get("BOTCUT_FAKE") == "1":
        return True, dict(FAKE_FACE)
    key = os.environ.get("XAI_API_KEY")
    if not key or not os.path.isfile(still):
        return False, None
    from botcut.pick import _jpeg_data_url

    try:
        face = ask(
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
        return True, face
    except SystemExit:
        # Framing is a nicety. A cut is never lost for want of it.
        return False, None


def ask_face(still: str) -> dict | None:
    return _ask_face(still)[1]


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
        face = None
        known = False
        try:
            stored = json.loads(Path(cache).read_text())
            if isinstance(stored, dict) and "face" in stored:
                raw = stored["face"]
                if raw is None:
                    known = True
                elif isinstance(raw, dict):
                    face = parse_face({"found": True, **raw})
                    known = True
        except (OSError, ValueError, KeyError, TypeError):
            known = False
        if not known:
            still = os.path.join(stills, f"face-{index}.jpg")
            # A third of the way in, past the moment of sitting down.
            at = max(0.0, float(clip.get("duration") or 0) / 3)
            if grab_still(clip["path"], at, still):
                ok, face = _ask_face(still)
                if ok:
                    Path(cache).write_text(json.dumps({"face": face}) + "\n")
        if face:
            clip["face"] = face

    pool = ThreadPoolExecutor(max_workers=4)
    try:
        list(pool.map(look, enumerate(clips)))
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)


def focus(clip: dict, at: float | None = None) -> tuple[float, float]:
    """The point to hold in frame: the middle of the face, or where a talking head usually is.

    `at` is the moment of the shot being framed. When faces were found along
    the shot, the nearest one in time is used, so a speaker who has moved is
    still the middle of the picture.
    """
    seen = clip.get("faces") or []
    if at is not None and seen:
        when, cx, cy = min(seen, key=lambda row: abs(float(row[0]) - at))
        if abs(float(when) - at) <= FACE_REACH:
            return float(cx), float(cy)
    face = parse_face({"found": True, **face}) if isinstance(face := clip.get("face"), dict) else None
    if not face:
        return DEFAULT_FOCUS
    return face["x"] + face["w"] / 2, face["y"] + face["h"] / 2


_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "face_detection_yunet_2023mar.onnx")
_DETECTOR = threading.local()


def find_face(still: str) -> dict | None:
    """The largest face in a still, as fractions of the picture, found on this machine. None when there is none."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    try:
        import cv2
    except ImportError:
        return None
    if not os.path.isfile(_MODEL) or not os.path.isfile(still):
        return None
    image = cv2.imread(still)
    if image is None:
        return None
    height, width = image.shape[:2]
    try:
        detector = getattr(_DETECTOR, "yunet", None)
        if detector is None:
            detector = cv2.FaceDetectorYN.create(_MODEL, "", (width, height), 0.7, 0.3, 20)
            _DETECTOR.yunet = detector
        else:
            detector.setInputSize((width, height))
        _count, faces = detector.detect(image)
    except cv2.error:
        return None
    if faces is None or not len(faces):
        return None
    x, y, w, h = (float(value) for value in max(faces, key=lambda face: face[2] * face[3])[:4])
    x, y = max(0.0, x), max(0.0, y)
    w, h = min(w, width - x), min(h, height - y)
    return parse_face({"found": True, "x": x / width, "y": y / height, "w": w / width, "h": h / height})


def faces_along(
    work: str, clips: list[dict], lines: list[dict] | None, angles: list[dict] | None = None
) -> None:
    """Note on each spoken shot (and second camera) where the speaker's face is at each line.

    The stills the cut already took of every line are looked at here, on this
    machine, and what is found is kept in work/faces.json. A still that
    shows no face adds nothing.
    """
    from concurrent.futures import ThreadPoolExecutor

    if os.environ.get("BOTCUT_FAKE") == "1":
        return
    cache = os.path.join(work, "faces.json")
    try:
        known = json.loads(Path(cache).read_text())
    except (OSError, ValueError):
        known = {}
    if not isinstance(known, dict):
        known = {}
    changed = False
    entries: list[tuple[str, int, float, str, float]] = []
    misses: list[tuple[str, str, float]] = []
    by_id: dict[int, dict] = {}
    for line in lines or []:
        try:
            uid, clip = int(line["id"]), int(line["clip"])
            middle = (float(line["start"]) + float(line["end"])) / 2
        except (KeyError, TypeError, ValueError):
            continue
        by_id[uid] = line
        still = os.path.join(work, "stills", f"{uid}.jpg")
        if not os.path.isfile(still):
            continue
        stamp = os.path.getmtime(still)
        key = str(uid)
        entries.append((key, clip, middle, still, stamp))
        row = known.get(key)
        if not isinstance(row, dict) or row.get("stamp") != stamp:
            misses.append((key, still, stamp))
    # Also detect faces on second-camera stills so portrait crops center the speaker on Cam B.
    for run in angles or []:
        if not isinstance(run, dict):
            continue
        try:
            cam = int(run["clip"])
            uid = int(run["line"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= cam < len(clips)) or uid not in by_id:
            continue
        still = os.path.join(work, "stills", f"angle-{cam}-{uid}.jpg")
        if not os.path.isfile(still):
            continue
        line = by_id[uid]
        from botcut.angles import angle_time

        at = angle_time(clips[cam], (float(line["start"]) + float(line["end"])) / 2)
        stamp = os.path.getmtime(still)
        key = f"angle-{cam}-{uid}"
        entries.append((key, cam, at, still, stamp))
        row = known.get(key)
        if not isinstance(row, dict) or row.get("stamp") != stamp:
            misses.append((key, still, stamp))
    if misses:
        if len(misses) == 1:
            key, still, stamp = misses[0]
            known[key] = {"stamp": stamp, "face": find_face(still)}
        else:
            pool = ThreadPoolExecutor(max_workers=min(4, len(misses)))
            try:
                found_faces = list(pool.map(lambda item: find_face(item[1]), misses))
            except BaseException:
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            else:
                pool.shutdown(wait=True)
            for (key, _still, stamp), found in zip(misses, found_faces):
                known[key] = {"stamp": stamp, "face": found}
        changed = True
    seen: dict[int, list] = {}
    for key, clip, middle, _still, _stamp in entries:
        row = known.get(key)
        face = parse_face({"found": True, **row["face"]}) if isinstance(row, dict) and isinstance(row.get("face"), dict) else None
        if face:
            seen.setdefault(clip, []).append(
                [round(middle, 2), round(face["x"] + face["w"] / 2, 4), round(face["y"] + face["h"] / 2, 4)]
            )
    if changed:
        try:
            Path(cache).write_text(json.dumps(known) + "\n")
        except OSError:
            pass
    for index, clip in enumerate(clips):
        if seen.get(index):
            clip["faces"] = sorted(seen[index])


def can_punch_in(clip: dict) -> bool:
    try:
        return int(clip.get("height") or 0) >= PUNCH_MIN_HEIGHT and int(clip.get("width") or 0) > 0
    except (TypeError, ValueError):
        return False


def punch_crop(clip: dict, amount: float = PUNCH_IN, at: float | None = None) -> str:
    """Eye-line-locked crop showing 1/amount of the frame, keeping the speaker's eyes on the same coordinate."""
    width, height = int(clip["width"]), int(clip["height"])
    crop_w = round(width / amount) // 2 * 2
    crop_h = round(height / amount) // 2 * 2
    cx, cy = focus(clip, at)
    # Anchor zoom on (cx, cy) so the speaker's eye-line stays fixed across wide -> tight cuts.
    left = min(max(0, round(cx * (width - crop_w))), width - crop_w)
    top = min(max(0, round(cy * (height - crop_h))), height - crop_h)
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


def push_filter(
    clip: dict,
    started: float = 0.0,
    at: float | None = None,
    *,
    rate: float = PUSH_RATE,
    max_zoom: float = PUSH_MAX,
) -> str:
    """A slow, even move in toward the speaker, `rate` a second up to `max_zoom`.

    `started` is how many seconds the push has already run when this piece
    begins. The picture is resampled between pixels on every frame, so the move
    does not step the way a crop that grows by whole pixels does.
    """
    cx, cy = focus(clip, at)
    fps = float(clip.get("fps") or 0) or 30.0
    zoom = f"min(1+{rate:g}*(on/{fps:g}+{max(0.0, started):.3f}),{max_zoom:g})"
    left = f"W*{cx:.4f}*(1-1/({zoom}))"
    top = f"H*{cy:.4f}*(1-1/({zoom}))"
    right = f"{left}+W/({zoom})"
    bottom = f"{top}+H/({zoom})"
    return (
        f"perspective=x0='{left}':y0='{top}':x1='{right}':y1='{top}'"
        f":x2='{left}':y2='{bottom}':x3='{right}':y3='{bottom}'"
        ":sense=source:eval=frame:interpolation=cubic"
    )


def stretch_lengths(segments: list[dict], lines: list[dict] | None = None) -> list[float]:
    """For each segment, how long the unbroken stretch of speech it belongs to runs.

    A cut inside a line does not break a stretch. A join between lines does.
    """
    lengths = [max(0.0, float(seg["end"]) - float(seg["start"])) for seg in segments]
    totals = list(lengths)
    first = 0
    for index in range(1, len(segments) + 1):
        if index < len(segments) and inside_a_line(segments[index - 1], segments[index], lines):
            continue
        whole = sum(lengths[first:index])
        for inner in range(first, index):
            totals[inner] = whole
        first = index
    return totals


class AutoFraming:
    """Decide, piece by piece as the movie plays, whether the speaker is shown wide or tight.

    Wide and tight are the two set-ups of a one-camera shoot. The picture
    goes from one to the other at a jump cut, once the framing has been
    held, so the jump reads as a change of shot; a line that carries the
    point is tight; and anything that is already a change of picture, a new
    shot, B-roll, another camera, comes back wide.
    """

    def __init__(self, hold: float = ZOOM_HOLD) -> None:
        self.tight = False
        self.held = 0.0
        self.clip: int | None = None
        self.hold = float(hold)

    def other_picture(self) -> None:
        """B-roll, a card, or another camera played. The speaker comes back wide."""
        self.clip = None

    def frame(
        self,
        clip: int,
        length: float,
        *,
        close: bool,
        runs_on: bool,
        same_footage: bool,
        gap: float = 0.0,
    ) -> bool:
        """True when this piece of the speaker plays tight.

        `close` is a line named to be shown close, `runs_on` a cut inside a
        line, `same_footage` a piece that follows the one before it in the
        file with nothing taken out, and `gap` is how many seconds of source
        footage were cut between the previous piece and this one.
        """
        fresh = self.clip != clip
        tiny_trim = 0.0 < gap < SMALL_JUMP_GAP
        if close:
            tight = True
        elif fresh or same_footage:
            tight = False
        elif runs_on or tiny_trim or self.held < self.hold:
            tight = self.tight
        else:
            tight = not self.tight
        self.held = length if fresh or tight != self.tight else self.held + length
        self.tight, self.clip = tight, clip
        return tight


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


def portrait_crop(clip: dict, target_w: int, target_h: int, at: float | None = None) -> str:
    """A face-centered vertical crop for fitting a wide clip into a taller target (e.g. 9:16 or split-screen).

    Returns empty string when the clip is already as tall as (or taller than) the target aspect.
    """
    try:
        src_w, src_h = int(clip.get("width") or 0), int(clip.get("height") or 0)
        rot = abs(int(round(float(clip.get("rotate") or 0)))) % 180
    except (TypeError, ValueError):
        return ""
    if rot == 90:
        src_w, src_h = src_h, src_w
    if src_w <= 0 or src_h <= 0 or target_w <= 0 or target_h <= 0:
        return ""
    if (src_w / src_h) <= (target_w / target_h) + 1e-3:
        return ""
    crop_w = max(2, min(src_w, (int(src_h * target_w / target_h) // 2) * 2))
    cx, _cy = focus(clip, at)
    left = min(max(0, round(cx * src_w - crop_w / 2)), max(0, src_w - crop_w))
    return f"crop={crop_w}:{src_h}:{left}:0"
