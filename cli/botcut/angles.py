"""Cut between cameras that filmed the same take.

A second camera is not B-roll. B-roll is other footage laid over the voice.
A second camera is the same moment from somewhere else: it is lined up with
the first by its sound, it is never transcribed and never heard, and the
picture goes to it and back at the joins between lines.

Where to switch is decided here by rule, the way an editor does it without
thinking: a jump cut is the best place, because the change of view hides it;
then the start of a new beat; then a line that carries the point; and
otherwise when one view has simply been on a long time. A view is held a few
seconds before it changes, and it never changes inside a line.
"""

from __future__ import annotations

import os

from botcut.card import is_card

# Seconds a view is held before it may change, and how long before it should, by how busy the cutting is.
PACES = {"calm": (6.0, 30.0), "normal": (4.0, 18.0), "busy": (2.5, 10.0)}
VIEWS = ("wide", "close", "side")
# The shortest stretch of another camera worth showing.
WINDOW_MIN = 0.2

HIDES = "hides a cut"
BEAT = "a new beat"
KEY = "a line that matters"
LONG = "a change of view"
MAIN = "back to the main view"
ENDS = "the other camera stops"
WIDE = "the wide view"


def is_angle(clip: object) -> bool:
    """True for another camera on a take that an earlier shot in the list filmed."""
    if not isinstance(clip, dict) or str(clip.get("role") or "") != "angle":
        return False
    return not is_card(str(clip.get("path") or "")) and _whole(clip.get("of")) is not None


def _whole(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _number(value: object, fallback: float = 0.0) -> float:
    try:
        found = float(value)
    except (TypeError, ValueError):
        return fallback
    return found if found == found else fallback


def groups(clips: list[dict]) -> dict[int, list[int]]:
    """Each shot that has other cameras on it, with those cameras in list order."""
    found: dict[int, list[int]] = {}
    for index, clip in enumerate(clips or []):
        if not is_angle(clip):
            continue
        main = int(clip["of"])
        if 0 <= main < len(clips) and main != index and not is_angle(clips[main]):
            found.setdefault(main, []).append(index)
    return found


def angle_time(clip: dict, at: float) -> float:
    """Where a moment of the main shot is in this camera's own file."""
    return at + _number(clip.get("offset")) + _number(clip.get("drift")) * at


def has_picture(clip: dict, start: float, end: float) -> bool:
    """True when this camera was running for the whole of a stretch of the main shot."""
    return angle_time(clip, start) >= 0 and angle_time(clip, end) <= _number(clip.get("duration"))


def read_cameras(value: object, clips: list[dict] | None = None) -> dict:
    """How the person asked for the cameras to be cut: {pace, favor, stay, off}."""
    raw = value if isinstance(value, dict) else {}
    pace = str(raw.get("pace") or "normal")
    favor = _whole(raw.get("favor"))
    if favor is not None and clips is not None and not 0 <= favor < len(clips):
        favor = None
    stay = sorted({uid for uid in (_whole(item) for item in raw.get("stay") or []) if uid is not None})
    return {
        "pace": pace if pace in PACES else "normal",
        "favor": favor if favor is not None and favor >= 0 else None,
        "stay": stay,
        "off": bool(raw.get("off")),
    }


def write_cameras(cameras: dict) -> dict:
    """The same, with what is at its default left out. Empty when nothing was asked for."""
    out: dict = {}
    if cameras.get("pace") in PACES and cameras["pace"] != "normal":
        out["pace"] = cameras["pace"]
    if cameras.get("favor") is not None:
        out["favor"] = int(cameras["favor"])
    if cameras.get("stay"):
        out["stay"] = sorted(int(uid) for uid in cameras["stay"])
    if cameras.get("off"):
        out["off"] = True
    return out


def _span(row: dict) -> tuple[int, float, float] | None:
    try:
        return int(row["clip"]), float(row["start"]), float(row["end"])
    except (KeyError, TypeError, ValueError):
        return None


def _spoken_kept(lines: list[dict]) -> list[dict]:
    return [
        line
        for line in lines or []
        if isinstance(line, dict)
        and line.get("keep")
        and str(line.get("reason") or "") != "card"
        and _whole(line.get("id")) is not None
        and _span(line) is not None
    ]


def _first_piece(line: dict, segments: list[dict]) -> int | None:
    clip, start, end = _span(line)
    for index, seg in enumerate(segments or []):
        span = _span(seg)
        if span and span[0] == clip and span[2] > start and span[1] < end:
            return index
    return None


def play_order(lines: list[dict], segments: list[dict]) -> list[dict]:
    """The kept spoken lines in the order the movie plays them. A line with no piece is not played."""
    placed = []
    for line in _spoken_kept(lines):
        piece = _first_piece(line, segments)
        if piece is not None:
            placed.append((piece, _span(line)[1], line))
    placed.sort(key=lambda item: (item[0], item[1]))
    return [line for _piece, _start, line in placed]


def joined(before: dict, after: dict, segments: list[dict]) -> bool:
    """True when one line runs into the next with no cut the viewer sees between them."""
    left, right = _span(before), _span(after)
    if left[0] != right[0] or right[1] < left[2] - 0.01:
        return False
    for seg in segments or []:
        span = _span(seg)
        if span and span[0] == left[0] and span[1] <= left[2] - 0.01 and span[2] >= right[1] + 0.01:
            return True
    return False


def _ends_a_sentence(line: dict) -> bool:
    return str(line.get("text") or "").rstrip().endswith((".", "?", "!"))


def plan(
    lines: list[dict],
    segments: list[dict],
    clips: list[dict],
    *,
    beats: list[dict] | None = None,
    close: list[int] | None = None,
    cameras: dict | None = None,
) -> list[dict]:
    """The stretches that play on another camera, as runs of lines: {clip, of, line, through, reason}.

    A run starts on a line and ends on a line. The view changes only between
    lines, only after it has been held, and only to a camera that was running
    for the whole of the line it changes on.
    """
    by_main = groups(clips)
    asked = read_cameras(cameras, clips)
    if not by_main or asked["off"]:
        return []
    hold, long = PACES[asked["pace"]]
    favor = asked["favor"]
    stay = set(asked["stay"])
    opens_a_beat = {int(beat["first"]) for beat in beats or [] if _whole(beat.get("first")) is not None}
    matters = {uid for uid in close or [] if _whole(uid) is not None}
    views = {index: str(clip.get("view") or "") for index, clip in enumerate(clips)}

    def running(camera: int, line: dict) -> bool:
        _clip, start, end = _span(line)
        return camera == int(line["clip"]) or has_picture(clips[camera], start, end)

    shown: list[tuple[dict, int, str]] = []
    camera = -1
    held = 0.0
    used: dict[int, int] = {}
    before = None
    for turn, line in enumerate(play_order(lines, segments)):
        uid = int(line["id"])
        main = int(line["clip"])
        others = by_main.get(main) or []
        length = max(0.0, _span(line)[2] - _span(line)[1])
        if not others or uid in stay:
            if camera != main:
                camera, held = main, 0.0
            shown.append((line, main, ""))
            held += length
            before = line
            used[main] = turn
            continue
        ring = [main, *others]
        free = [cam for cam in ring if cam != camera and running(cam, line)]
        reason = ""
        if before is None or int(before["clip"]) != main or camera not in ring:
            # A new shot opens on its widest view, or on the main camera when nobody said which that is.
            wide = [cam for cam in ring if views[cam] == "wide" and running(cam, line)]
            if favor in ring and running(favor, line):
                camera, reason = favor, MAIN
            elif wide:
                camera, reason = wide[0], WIDE
            else:
                camera = main
            held = 0.0
        else:
            if not running(camera, line):
                reason = ENDS
            elif free and held >= hold:
                if favor in free:
                    reason = MAIN
                elif not joined(before, line, segments):
                    reason = HIDES
                elif camera == favor:
                    # On the favored camera only a jump cut, or a very long hold, takes the picture away.
                    reason = LONG if held >= 2 * long and _ends_a_sentence(before) else ""
                elif uid in opens_a_beat:
                    reason = BEAT
                elif uid in matters and views[camera] != "close" and any(views[cam] == "close" for cam in free):
                    reason = KEY
                elif held >= long and _ends_a_sentence(before):
                    reason = LONG
            if reason:
                camera = _next_camera(free, reason, favor, views, used, main)
                held = 0.0
        shown.append((line, camera, reason))
        held += length
        used[camera] = turn
        before = line

    runs: list[dict] = []
    last_turn = -2
    for turn, (line, cam, reason) in enumerate(shown):
        main = int(line["clip"])
        if cam == main:
            continue
        if runs and last_turn == turn - 1 and runs[-1]["clip"] == cam and runs[-1]["of"] == main:
            runs[-1]["through"] = int(line["id"])
        else:
            runs.append(
                {"clip": cam, "of": main, "line": int(line["id"]), "through": int(line["id"]), "reason": reason or LONG}
            )
        last_turn = turn
    return runs


def _next_camera(free: list[int], reason: str, favor: int | None, views: dict, used: dict, main: int) -> int:
    if reason == MAIN and favor in free:
        return favor
    if reason == ENDS:
        return main
    if reason == KEY:
        tight = [cam for cam in free if views.get(cam) == "close"]
        if tight:
            return tight[0]
    # Otherwise the view that has been off the screen longest.
    return min(free, key=lambda cam: used.get(cam, -1))


def run_lines(run: dict, lines: list[dict], segments: list[dict]) -> list[dict]:
    """The lines a run plays over, in the order they play."""
    order = play_order(lines, segments)
    first, through = _whole(run.get("line")), _whole(run.get("through"))
    found = []
    for line in order:
        uid = int(line["id"])
        if not found and uid != first:
            continue
        found.append(line)
        if uid == through:
            return found
    # A run whose last line is no longer played does not stand.
    return [] if through != first or not found else found[:1]


def angle_windows(angles, lines: list[dict], segments: list[dict], clips: list[dict]) -> list[dict]:
    """Where each run shows, piece by piece, with the time in the other camera's file it starts from.

    A run owns the air out to the middle of the gap on each side of it, so
    the change of view falls in the pause between two lines. Inside the run
    every piece of the main shot shows the other camera instead, whatever
    cuts were made inside its lines.
    """
    kept = sorted((_span(line) for line in _spoken_kept(lines)), key=lambda span: (span[0], span[1]))
    windows = []
    for run in angles or []:
        if not isinstance(run, dict):
            continue
        cam = _whole(run.get("clip"))
        if cam is None or not 0 <= cam < len(clips) or not is_angle(clips[cam]):
            continue
        main = int(clips[cam]["of"])
        for low, high in _stretches(run_lines(run, lines, segments), main, kept):
            for index, seg in enumerate(segments or []):
                span = _span(seg)
                if not span or span[0] != main or str(seg.get("reason") or "") == "card":
                    continue
                start, end = max(span[1], low), min(span[2], high)
                # The other camera may have been started late or stopped early.
                src = angle_time(clips[cam], start)
                if src < 0:
                    start, src = start - src, 0.0
                over = angle_time(clips[cam], end) - _number(clips[cam].get("duration"))
                if over > 0:
                    end -= over
                if end - start < WINDOW_MIN:
                    continue
                windows.append(
                    {
                        "segment": index,
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "clip": cam,
                        "src": round(src, 3),
                        "angle": True,
                    }
                )
    windows.sort(key=lambda item: (item["segment"], item["start"]))
    # Two runs never claim the same picture. The earlier one keeps it.
    out: list[dict] = []
    for window in windows:
        if out and out[-1]["segment"] == window["segment"] and window["start"] < out[-1]["end"] - 1e-3:
            continue
        out.append(window)
    return out


def _stretches(run: list[dict], main: int, kept: list[tuple[int, float, float]]) -> list[tuple[float, float]]:
    """The stretches of the main shot a run covers, each out to the middle of the air around it."""
    spans = sorted(_span(line)[1:] for line in run if _span(line)[0] == main)
    if not spans:
        return []
    mine = [(start, end) for clip, start, end in kept if clip == main]
    merged: list[list[float]] = []
    for start, end in spans:
        # Lines of the run that follow one another in the shot are one stretch.
        between = [other for other in mine if merged and merged[-1][1] <= other[0] < start]
        if merged and not between:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    found = []
    for start, end in merged:
        before = [other_end for _s, other_end in mine if other_end <= start + 1e-6]
        after = [other_start for other_start, _e in mine if other_start >= end - 1e-6]
        low = (max(before) + start) / 2 if before else float("-inf")
        high = (end + min(after)) / 2 if after else float("inf")
        found.append((low, high))
    return found


def shown_seconds(angles, lines: list[dict], segments: list[dict], clips: list[dict]) -> float:
    return sum(window["end"] - window["start"] for window in angle_windows(angles, lines, segments, clips))


def reply(angles: list[dict], clips: list[dict], seconds: float) -> str:
    """One sentence for the person about how the cameras were cut."""
    by_main = groups(clips)
    count = len({cam for cams in by_main.values() for cam in cams}) + len(by_main)
    if not by_main:
        return ""
    if not angles:
        return f"I found {count} cameras on the same take and stayed on the first."
    hidden = sum(1 for run in angles if run.get("reason") == HIDES)
    times = "once" if len(angles) == 1 else f"{len(angles)} times"
    text = f"I found {count} cameras on the same take and cut to the other view {times}, {seconds:.0f} s in all"
    if hidden:
        text += f", {hidden} of them to hide a cut" if len(angles) > 1 else ", to hide a cut"
    return text + "."


VIEW_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "views",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["views"],
            "properties": {
                "views": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["camera", "view"],
                        "properties": {
                            "camera": {"type": "integer"},
                            "view": {"type": "string", "enum": list(VIEWS)},
                        },
                    },
                }
            },
        },
    },
}

VIEW_PROMPT = (
    "These stills are the same moment of one take, each from a different camera. "
    "For each camera return its view: wide when it shows the most of the scene, "
    "close when it is the tightest on the person speaking, side for anything else. "
    "At most one camera is wide and at most one is close."
)


def read_views(payload: object, cameras: list[int]) -> dict[int, str]:
    if not isinstance(payload, dict):
        raise ValueError("not views")
    found: dict[int, str] = {}
    for item in payload["views"]:
        cam, view = _whole(item.get("camera")), str(item.get("view") or "")
        if cam in cameras and view in VIEWS and cam not in found:
            # A second wide or close is one camera too many. It is a side view.
            found[cam] = "side" if view != "side" and view in found.values() else view
    return found


def name_views(clips: list[dict], still_dir: str) -> None:
    """Note on each camera of a take whether it is the wide view, the close one, or a side view.

    One still per camera, all of the same moment, and one question. Without
    an answer the cut still switches cameras. It only does not know which is closer.
    """
    from botcut.media import grab_still

    if os.environ.get("BOTCUT_FAKE") == "1" or not os.environ.get("XAI_API_KEY"):
        return
    from botcut.llm import ask
    from botcut.pick import _jpeg_data_url

    for main, others in groups(clips).items():
        if any(clips[cam].get("view") for cam in (main, *others)):
            continue
        # A moment every camera was running for, as near the middle of the take as there is one.
        low = max([0.0, *(-_number(clips[cam].get("offset")) for cam in others)])
        high = min(
            [_number(clips[main].get("duration"))]
            + [_number(clips[cam].get("duration")) - _number(clips[cam].get("offset")) for cam in others]
        )
        if high - low < 1:
            continue
        at = (low + high) / 2
        parts: list[dict] = [{"type": "text", "text": VIEW_PROMPT}]
        ready = []
        for cam in (main, *others):
            still = os.path.join(still_dir, f"view-{cam}.jpg")
            when = at if cam == main else angle_time(clips[cam], at)
            if not grab_still(clips[cam]["path"], when, still):
                continue
            ready.append(cam)
            parts.append({"type": "text", "text": f"Camera {cam}"})
            parts.append({"type": "image_url", "image_url": {"url": _jpeg_data_url(still)}})
        if len(ready) < 2:
            continue
        try:
            found = ask(
                [{"role": "user", "content": parts}],
                VIEW_SCHEMA,
                what="the camera views",
                parse=lambda payload: read_views(payload, ready),
                read_timeout=60,
            )
        except SystemExit:
            continue
        for cam, view in found.items():
            clips[cam]["view"] = view
