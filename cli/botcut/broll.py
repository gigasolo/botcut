"""Lay B-roll beats over spoken lines.

A file marked B-roll is sliced into beats at its scene changes. The model
returns beat and line ids. A stored cover carries the beat's window inside the
B-roll file, and the render clips that window to the spoken line.
"""

from __future__ import annotations

import json
import os

from botcut.card import is_card
from botcut.net import post
from botcut.pick import MAX_STILLS, _jpeg_data_url, chat_fields, llm_url

# A run of B-roll is at least RUN_MIN and at most RUN_MAX seconds in the cut.
RUN_MIN = 3.0
RUN_MAX = 12.0
# A cover from an older cut names one line and no run. It plays up to this long.
COVER_MAX = 4.0
BEAT_MIN = 1.0
BEAT_MAX = COVER_MAX
MAX_BEATS = MAX_STILLS
# Two kept lines with no segment list are continuous when this little air sits between them.
GAP_MAX = 1.0

FAKE_COVER_REPLY = "I laid the B-roll over one stretch."

# One sentence on what a run is. The cut's brief and the chat's brief both carry it,
# so "less B-roll" comes back in the same shape it was laid.
RUN_SENTENCE = (
    "A run is one starting beat laid over one or more consecutive kept lines, "
    "3 to 12 seconds long, and it ends on a line. The footage plays on from that beat."
)

COVER_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "covers",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["reply", "covers"],
            "properties": {
                "reply": {"type": "string"},
                "covers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["beat", "line", "through", "reason"],
                        "properties": {
                            "beat": {"type": "integer"},
                            "line": {"type": "integer"},
                            "through": {"type": "integer"},
                            "reason": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}

COVER_SYSTEM = (
    "You are the editor laying B-roll over a spoken rough cut. "
    "B-roll is cover, not decoration. Use it to hide a cut between kept lines, "
    "to show what the words describe, or to rest the viewer during a long stretch on the speaker. "
    + RUN_SENTENCE
    + " Stay on the speaker for the first line and the last, for direct address, a joke, "
    "or a line that carries feeling. Space the runs out and never lay two back to back. "
    "Use the beats in order so the footage moves forward. "
    "Covering little, or nothing, is fine when nothing earns it. "
    "Return the starting beat id, the first and last line ids, a reason of two to four words, "
    "and one or two plain sentences to the person saying what you laid and why. "
    "Do not return times, paths, or a new picture."
)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def is_broll(clip: object) -> bool:
    if not isinstance(clip, dict):
        return False
    if str(clip.get("role") or "") != "broll":
        return False
    return not is_card(str(clip.get("path") or ""))


def broll_indexes(clips: list[dict]) -> list[int]:
    """Clips marked B-roll. A card is never B-roll."""
    return [index for index, clip in enumerate(clips or []) if is_broll(clip)]


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


def line_length(line: dict) -> float:
    try:
        return max(0.0, float(line["end"]) - float(line["start"]))
    except (KeyError, TypeError, ValueError):
        return 0.0


def beats_from_cuts(cuts, duration: float) -> list[tuple[float, float]]:
    """Spans between scene changes, each between BEAT_MIN and BEAT_MAX long.

    A short span merges into its neighbour. A long span is divided evenly.
    With no cuts the file is fixed BEAT_MAX windows.
    """
    try:
        total = float(duration or 0)
    except (TypeError, ValueError):
        total = 0.0
    if total <= 0:
        return []
    if total < BEAT_MIN:
        return [(0.0, round(total, 3))]
    points = []
    for value in cuts or []:
        at = _as_float(value)
        if at is None or at <= 0 or at >= total:
            continue
        points.append(round(at, 3))
    bounds = [0.0, *sorted(set(points)), total]
    spans: list[tuple[float, float]] = []
    for start, end in zip(bounds, bounds[1:]):
        if end - start <= 0.001:
            continue
        if spans and end - start < BEAT_MIN:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    if len(spans) >= 2 and spans[0][1] - spans[0][0] < BEAT_MIN:
        spans[1] = (spans[0][0], spans[1][1])
        spans.pop(0)
    beats: list[tuple[float, float]] = []
    for start, end in spans:
        span = end - start
        parts = max(1, int(-(-span // BEAT_MAX)))
        step = span / parts
        for i in range(parts):
            a = start + i * step
            b = end if i == parts - 1 else start + (i + 1) * step
            beats.append((round(a, 3), round(b, 3)))
    return beats


def fake_beats(duration: float) -> list[tuple[float, float]]:
    """Fixed windows, with no ffmpeg. BOTCUT_FAKE stays offline and deterministic."""
    return beats_from_cuts([], duration)


def _sample(rows: list, limit: int) -> list:
    if len(rows) <= limit:
        return list(rows)
    if limit <= 0:
        return []
    step = len(rows) / limit
    return [rows[int(i * step)] for i in range(limit)]


def collect_beats(clips: list[dict], beats_by_clip: dict) -> list[dict]:
    """Beats over every B-roll clip, in clip order, numbered after sampling.

    More than MAX_BEATS are sampled evenly inside each file, so every file
    stays represented and the model only sees ids it may return.
    """
    per_clip: list[tuple[int, list[tuple[float, float]]]] = []
    total = 0
    for index in broll_indexes(clips):
        pairs = []
        for pair in (beats_by_clip or {}).get(index) or []:
            try:
                start, end = float(pair[0]), float(pair[1])
            except (TypeError, ValueError, IndexError):
                continue
            if end - start > 0.001:
                pairs.append((start, end))
        if pairs:
            per_clip.append((index, pairs))
            total += len(pairs)
    if total > MAX_BEATS:
        sampled = []
        for index, pairs in per_clip:
            quota = max(1, int(MAX_BEATS * len(pairs) / total))
            sampled.append((index, _sample(pairs, quota)))
        per_clip = sampled
    beats = []
    for index, pairs in per_clip:
        for start, end in pairs:
            beats.append({"id": len(beats), "clip": index, "start": start, "end": end})
    return beats


def beat_still_at(start: float, end: float) -> float:
    """One second in, or the middle of a shorter beat."""
    span = max(0.0, float(end) - float(start))
    return float(start) + min(1.0, span / 2.0)


def _segment_of(line: dict, segments) -> int | None:
    """Index of the spoken segment this line sits in, or None."""
    try:
        clip = int(line["clip"])
        start = float(line["start"])
        end = float(line["end"])
    except (KeyError, TypeError, ValueError):
        return None
    for index, seg in enumerate(segments or []):
        try:
            if int(seg["clip"]) != clip:
                continue
            seg_start = float(seg["start"])
            seg_end = float(seg["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end > seg_start and start < seg_end:
            return index
    return None


def continuous(first: dict, second: dict, segments=None) -> bool:
    """True when the second kept line follows the first with no cut the viewer sees."""
    if segments:
        a = _segment_of(first, segments)
        return a is not None and a == _segment_of(second, segments)
    try:
        if int(first["clip"]) != int(second["clip"]):
            return False
        gap = float(second["start"]) - float(first["end"])
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= gap <= GAP_MAX


def run_length(run_lines: list[dict], segments=None) -> float:
    """Seconds the run takes in the cut: the lines, plus the air kept between them.

    Across a cut, that air is the tail of one segment and the head of the next.
    """
    total = 0.0
    prev = None
    for line in run_lines:
        total += line_length(line)
        if prev is not None:
            total += _air_between(prev, line, segments)
        prev = line
    return total


def _air_between(prev: dict, line: dict, segments=None) -> float:
    try:
        prev_end = float(prev["end"])
        start = float(line["start"])
    except (KeyError, TypeError, ValueError):
        return 0.0
    if continuous(prev, line, segments):
        return max(0.0, start - prev_end)
    if not segments:
        return 0.0
    a = _segment_of(prev, segments)
    b = _segment_of(line, segments)
    if a is None or b is None:
        return 0.0
    try:
        tail = float(segments[a]["end"]) - prev_end
        head = start - float(segments[b]["start"])
    except (KeyError, TypeError, ValueError):
        return 0.0
    return max(0.0, tail) + max(0.0, head)


def _short_reason(value: object) -> str:
    words = " ".join(str(value or "").split())
    return words[:48]


def accept_runs(
    claims,
    *,
    beats: dict,
    lines: list[dict],
    segments=None,
    durations=None,
    still_dir: str | None = None,
) -> list[dict]:
    """Runs the editor laid, in line order.

    A run starts on a beat that exists and covers kept spoken lines from `line`
    through `through`, in list order. The first and last kept lines stay on the
    speaker. Runs do not overlap, and their beats go up, so the footage moves
    forward. A run past RUN_MAX is cut back a line at a time; one under RUN_MIN,
    or with too little file left after its beat, is dropped.
    """
    kept = spoken_kept(lines)
    index_of = {int(line["id"]): i for i, line in enumerate(kept)}
    accepted = []
    taken: list[tuple[int, int]] = []
    last_beat = -1
    if not isinstance(claims, list):
        return []
    for item in claims:
        if not isinstance(item, dict):
            continue
        beat_id = _as_int(item.get("beat"))
        first = _as_int(item.get("line"))
        last = item.get("through")
        last = first if last is None else _as_int(last)
        if beat_id is None or first is None or last is None:
            continue
        beat = beats.get(beat_id)
        if beat is None or beat_id <= last_beat:
            continue
        if first not in index_of or last not in index_of:
            continue
        i, j = index_of[first], index_of[last]
        if j < i or i == 0 or j >= len(kept) - 1:
            continue
        if any(not (j < a or i > b) for a, b in taken):
            continue
        clip = int(beat["clip"])
        beat_start = float(beat["start"])
        remaining = float("inf")
        if durations is not None and 0 <= clip < len(durations):
            try:
                remaining = float(durations[clip] or 0) - beat_start
            except (TypeError, ValueError):
                remaining = 0.0
        if remaining < RUN_MIN:
            continue
        length = run_length(kept[i : j + 1], segments)
        while j > i and length > RUN_MAX:
            j -= 1
            length = run_length(kept[i : j + 1], segments)
        length = min(length, RUN_MAX, remaining)
        if length < RUN_MIN:
            continue
        row = {
            "clip": clip,
            "line": first,
            "through": int(kept[j]["id"]),
            "start": round(beat_start, 3),
            "end": round(beat_start + length, 3),
            "reason": _short_reason(item.get("reason")),
        }
        if still_dir:
            still = os.path.join(still_dir, f"broll-{clip}-{beat_id}.jpg")
            if os.path.isfile(still):
                row["still"] = os.path.abspath(still)
        accepted.append(row)
        taken.append((i, j))
        last_beat = beat_id
    accepted.sort(key=lambda row: index_of[int(row["line"])])
    return accepted


def fake_claims(beats: list[dict], lines: list[dict]) -> list[dict]:
    """One run on the first beat over the second and third kept lines."""
    kept = spoken_kept(lines)
    if not beats or len(kept) < 3:
        return []
    first = kept[1]
    last = kept[min(2, len(kept) - 2)]
    return [
        {
            "beat": int(beats[0]["id"]),
            "line": int(first["id"]),
            "through": int(last["id"]),
            "reason": "fake",
        }
    ]


def cover_user_content(beats: list[dict], lines: list[dict], stills: dict, *, intent: str = "", segments=None):
    """The movie line, the beats, and every line in order. No paths and no timestamps.

    A kept line carries its length. A dropped line is marked. A cut row sits
    between two kept lines the viewer will see joined.
    """
    total = 0.0
    for beat in beats:
        total += float(beat["end"]) - float(beat["start"])
    body = []
    if intent:
        body.append(f"The movie is: {intent}")
    body.append(
        f"{len(beats)} B-roll beats, {total:.0f}s in all, each a few seconds of one shot. "
        "A still, when one exists, is that beat. Return beat and line ids only."
    )
    for beat in beats:
        dur = float(beat["end"]) - float(beat["start"])
        body.append(f"beat {int(beat['id'])}, {dur:.1f}s, shot {int(beat['clip'])}")
    body.append("")
    body.append("The lines in order, each kept one with its length. A cut row is a join the viewer will see.")
    prev_kept = None
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        uid = _as_int(line.get("id"))
        if uid is None or str(line.get("reason") or "") == "card":
            continue
        text = line.get("text") or ""
        if line.get("keep"):
            if prev_kept is not None and not continuous(prev_kept, line, segments):
                body.append("— cut —")
            body.append(f"[{uid}] {line_length(line):.1f}s {text}")
            prev_kept = line
        else:
            body.append(f"[{uid}] dropped: {text}")
    text = "\n".join(body)
    ready = [
        int(beat["id"])
        for beat in beats
        if stills.get(int(beat["id"])) and os.path.isfile(str(stills[int(beat["id"])]))
    ]
    if not ready:
        return text
    parts: list[dict] = [{"type": "text", "text": text}]
    for beat_id in ready:
        parts.append({"type": "text", "text": f"Still for beat {beat_id}"})
        parts.append(
            {"type": "image_url", "image_url": {"url": _jpeg_data_url(str(stills[beat_id]))}}
        )
    return parts


def beat_stills(clips: list[dict], beats: list[dict], still_dir: str) -> dict[int, str]:
    """One still per beat, grabbed once and kept in still_dir. A missed frame still sends the beat."""
    from botcut.media import grab_still

    os.makedirs(still_dir, exist_ok=True)
    stills: dict[int, str] = {}
    for beat in beats:
        clip = clips[int(beat["clip"])]
        dest = os.path.join(still_dir, f"broll-{int(beat['clip'])}-{int(beat['id'])}.jpg")
        if os.path.isfile(dest):
            stills[int(beat["id"])] = dest
            continue
        at = beat_still_at(float(beat["start"]), float(beat["end"]))
        if grab_still(str(clip.get("path") or ""), at, dest):
            stills[int(beat["id"])] = dest
    return stills


def _ask(
    clips: list[dict], beats: list[dict], lines: list[dict], still_dir: str, *, intent: str, segments
) -> tuple[list, str]:
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")
    stills = beat_stills(clips, beats, still_dir)
    body = {
        **chat_fields(),
        "messages": [
            {"role": "system", "content": COVER_SYSTEM},
            {
                "role": "user",
                "content": cover_user_content(beats, lines, stills, intent=intent, segments=segments),
            },
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
    reply = payload.get("reply")
    reply = " ".join(reply.split()) if isinstance(reply, str) else ""
    return payload["covers"], reply


def clip_durations(clips: list[dict]) -> list[float]:
    durations = []
    for clip in clips or []:
        try:
            durations.append(float(clip.get("duration") or 0))
        except (TypeError, ValueError):
            durations.append(0.0)
    return durations


def choose_covers(
    clips: list[dict],
    lines: list[dict],
    still_dir: str,
    beats_by_clip: dict,
    *,
    segments=None,
    intent: str = "",
) -> tuple[list[dict], str]:
    """The runs the editor laid and its sentence to the person. Empty when nothing can be laid."""
    beats = collect_beats(clips, beats_by_clip)
    if not beats or len(spoken_kept(lines)) < 3:
        return [], ""
    if os.environ.get("BOTCUT_FAKE") == "1":
        claims = fake_claims(beats, lines)
        reply = FAKE_COVER_REPLY if claims else ""
    else:
        claims, reply = _ask(clips, beats, lines, still_dir, intent=intent, segments=segments)
    covers = accept_runs(
        claims,
        beats={int(beat["id"]): beat for beat in beats},
        lines=lines,
        segments=segments,
        durations=clip_durations(clips),
        still_dir=still_dir,
    )
    return covers, (reply if covers else "")


def run_lines(cover: dict, lines: list[dict]) -> list[dict]:
    """The kept spoken lines a run covers, in list order. Empty when its first line is gone."""
    first = _as_int(cover.get("line"))
    through = _as_int(cover.get("through"))
    if first is None:
        return []
    found = []
    started = False
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        uid = _as_int(line.get("id"))
        if uid is None:
            continue
        if not started:
            if uid != first:
                continue
            started = True
        kept = bool(line.get("keep")) and str(line.get("reason") or "") != "card"
        if not kept:
            break
        found.append(line)
        if through is None or uid == through:
            break
    return found


def kept_covers(covers, lines: list[dict]) -> list[dict]:
    """Runs trimmed to the lines still kept. Do not add one.

    A run whose first line is dropped goes. A dropped line inside a run ends it
    there; a run that falls under RUN_MIN goes. An older one-line cover keeps its window.
    """
    found = []
    for item in covers or []:
        if not isinstance(item, dict):
            continue
        clip = _as_int(item.get("clip"))
        first = _as_int(item.get("line"))
        if clip is None or first is None:
            continue
        alive = run_lines(item, lines)
        if not alive:
            continue
        row = {"clip": clip, "line": first}
        start = _as_float(item.get("start"))
        end = _as_float(item.get("end"))
        through = _as_int(item.get("through"))
        if through is None:
            if start is not None and end is not None:
                row["start"] = start
                row["end"] = end
            found.append(row)
            continue
        new_through = int(alive[-1]["id"])
        if start is None or end is None:
            continue
        if new_through != through:
            length = min(run_length(alive), end - start)
            if length < RUN_MIN:
                continue
            end = round(start + length, 3)
        row["through"] = new_through
        row["start"] = start
        row["end"] = end
        for key in ("reason", "still"):
            if item.get(key):
                row[key] = str(item[key])
        found.append(row)
    return found


def cover_windows(covers, lines, segments, durations) -> list[dict]:
    """Where each run shows, segment by segment, with the B-roll time it starts from.

    A run crosses the joins between its lines' segments, and `src` goes on
    across them so the footage is one piece. A window carries `continues`
    when the run goes on into the next segment and `continued` when it came
    from the one before, so the render puts no fade on that join. An older
    one-line cover stays inside its line, up to COVER_MAX, from its window's start.
    """
    raw = []
    for order, item in enumerate(covers or []):
        if not isinstance(item, dict):
            continue
        clip = _as_int(item.get("clip"))
        if clip is None or clip < 0 or clip >= len(durations):
            continue
        try:
            broll_dur = float(durations[clip] or 0)
        except (TypeError, ValueError):
            continue
        if broll_dur <= 0:
            continue
        legacy = _as_int(item.get("through")) is None
        alive = run_lines(item, lines)
        if not alive:
            continue
        src_start = _as_float(item.get("start"))
        src_end = _as_float(item.get("end"))
        src_start = 0.0 if src_start is None else min(max(0.0, src_start), broll_dur)
        src_end = broll_dur if src_end is None else min(max(src_start, src_end), broll_dur)
        groups: list[list] = []
        for line in alive:
            try:
                spoken = int(line["clip"])
                line_start = float(line["start"])
                line_end = float(line["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if spoken == clip:
                continue
            index = _segment_of(line, segments)
            if index is None:
                continue
            seg_start = float(segments[index]["start"])
            seg_end = float(segments[index]["end"])
            win_start = max(seg_start, line_start)
            win_end = min(seg_end, line_end)
            if groups and groups[-1][0] == index:
                groups[-1][2] = max(groups[-1][2], win_end)
            else:
                groups.append([index, win_start, win_end, seg_start, seg_end])
        src = src_start
        for k, (index, win_start, win_end, seg_start, seg_end) in enumerate(groups):
            # Across a join the run owns the air at the segment's edges too, so the
            # footage is one piece from the first line to the last.
            if k > 0:
                win_start = seg_start
            if k < len(groups) - 1:
                win_end = seg_end
            span = win_end - win_start
            if legacy:
                span = min(span, COVER_MAX)
            available = src_end - src
            if available <= 0.001:
                break
            length = min(span, available)
            if length <= 0.001:
                continue
            raw.append(
                {
                    "segment": index,
                    "start": win_start,
                    "end": win_start + length,
                    "clip": clip,
                    "order": order,
                    "src": src,
                    "continued": k > 0,
                    "continues": k < len(groups) - 1 and src_end - (src + length) > 0.001,
                }
            )
            src += length
    by_seg: dict[int, list] = {}
    for item in raw:
        by_seg.setdefault(int(item["segment"]), []).append(item)
    windows = []
    for index in sorted(by_seg):
        items = sorted(by_seg[index], key=lambda item: (float(item["start"]), int(item["order"])))
        cursor = None
        for item in items:
            start = float(item["start"])
            end = float(item["end"])
            src = float(item["src"])
            # Overlap only shrinks the later window, and none is left if it cannot.
            # The B-roll keeps step with the window it lost.
            if cursor is not None and start < cursor:
                src += cursor - start
                start = cursor
            if end - start <= 0.001:
                continue
            window = {
                "segment": index,
                "start": round(start, 3),
                "end": round(end, 3),
                "clip": int(item["clip"]),
                "src": round(src, 3),
            }
            if item["continued"]:
                window["continued"] = True
            if item["continues"]:
                window["continues"] = True
            windows.append(window)
            cursor = end
    return windows
