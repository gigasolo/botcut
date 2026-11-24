"""Revise a decided cut from a note.

The model returns a reply to the person, a sentence, a pace, dip on or off, keep
ids, and a delivery. It does not return times. The file's max_pause stays put
until the next Cut or Render.

`revise CUTS NOTE` applies the change at once. `revise CUTS NOTE --propose` only
writes `proposal.json` beside cuts.json and prints the reply, so the window can
show it and ask before anything moves. `revise CUTS --apply` then lands that
proposal without calling the model again.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from botcut.broll import (
    RUN_SENTENCE,
    accept_runs,
    beat_stills,
    broll_indexes,
    clip_durations,
    collect_beats,
    kept_covers,
)
from botcut import angles as cams
from botcut.llm import ask
from botcut.frame import close_ids
from botcut.pick import hook_line

# The offscreen revise test expects these sentences.
FAKE_INTENT = "A frenzied cut."
FAKE_REPLY = "I'd drop the last line and cut every breath."

PROPOSAL_NAME = "proposal.json"
HISTORY_TURNS = 12

PACES = ("open", "measured", "tight", "frenzied")
DELIVERS = ("none", "render", "captions", "short")
# What to do with the cuts inside lines: fillers and words said twice.
FILLERS = ("same", "cut", "keep")
# How often the picture changes between cameras on the same take. same leaves it as it is.
CAMERAS = ("same", "calm", "normal", "busy", "off")
_FIELDS = {"reply", "intent", "pace", "dip", "keep", "deliver", "covers", "fillers", "cameras", "favor"}
_LATER_FIELDS = {"covers", "fillers", "cameras", "favor"}
_KEEP_FIELDS = {"id", "reason"}
_COVER_FIELDS = {"beat", "line", "through", "reason"}

REVISE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "revise",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "reply", "intent", "pace", "dip", "keep", "deliver", "covers", "fillers", "cameras", "favor",
            ],
            "properties": {
                "reply": {"type": "string"},
                "intent": {"type": "string"},
                "pace": {"type": "string", "enum": list(PACES)},
                "dip": {"type": "boolean"},
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
                },
                "deliver": {"type": "string", "enum": list(DELIVERS)},
                "fillers": {"type": "string", "enum": list(FILLERS)},
                "cameras": {"type": "string", "enum": list(CAMERAS)},
                "favor": {"type": "integer"},
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

REVISE_SYSTEM = (
    "Revise one rough cut from the user's note. "
    "Return a reply, the movie sentence, the pace, whether to dip to black, "
    "the utterance ids to keep and a short reason for each, and how to deliver. "
    "The reply is one or two plain sentences to the person: what you would change "
    "and why, or an answer when nothing should change. Earlier turns are context. "
    "Pace is open, measured, tight, or frenzied. "
    "Deliver is none, render, captions, or short. "
    "Deliver never changes the picture. "
    "Fillers is same, cut, or keep. cut takes every filler sound and stumbled restart out of the kept "
    "lines, keep leaves them all in, and same changes none of them. "
    "none only means not to mark render, captions, or short. "
    "Cameras is same, calm, normal, busy, or off: how often the picture changes between cameras that "
    "filmed the same take. same leaves the cameras and favor as they are, and off stays on the main "
    "camera. Favor is the number of the camera to stay on most of the time, or -1 for none. "
    "With no cameras listed, return same and -1. "
    "Do not return times, padding, or any join other than dip on or off. "
    "A listed id is kept. An id you leave out is dropped. Do not invent ids. "
    "Covers is the full list of B-roll runs to keep. "
    + RUN_SENTENCE
    + " A listed run stays. A run you leave out goes. Add one only on a beat that is listed, "
    "with a reason of two to four words. With no beats listed, return no covers."
)


def apply_revise(lines: list[dict], keep: list[dict]) -> list[dict]:
    """Listed ids stay, with the model's reason. Any other current id is dropped.

    An id that is not already a line is ignored. Times on the line are copied through.
    """
    known = {}
    for line in lines:
        try:
            known[int(line["id"])] = line
        except (KeyError, TypeError, ValueError):
            continue
    reasons = {}
    for item in keep:
        try:
            uid = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if uid not in known:
            continue
        reasons[uid] = str(item.get("reason") or "")
    updated = []
    for line in lines:
        row = dict(line)
        if str(line.get("reason") or "") == "card":
            row["keep"] = True
            row["reason"] = "card"
            updated.append(row)
            continue
        try:
            uid = int(line["id"])
        except (KeyError, TypeError, ValueError):
            updated.append(row)
            continue
        if uid in reasons:
            row["keep"] = True
            row["reason"] = reasons[uid]
        else:
            row["keep"] = False
            row["reason"] = "dropped"
        updated.append(row)
    return updated


def parse_revise(payload: dict) -> dict:
    # A proposal saved before cuts inside lines has no fillers, and one with no B-roll has no covers.
    if not isinstance(payload, dict) or not (_FIELDS - _LATER_FIELDS <= set(payload) <= _FIELDS):
        raise SystemExit("LLM response was not a revise")
    # A proposal saved before there were second cameras says nothing about them.
    cameras = payload.get("cameras") or "same"
    favor = payload.get("favor")
    if favor is None:
        favor = -1
    if cameras not in CAMERAS or isinstance(favor, bool) or not isinstance(favor, int):
        raise SystemExit("LLM response was not a revise")
    fillers = payload.get("fillers", "same")
    if fillers is None:
        fillers = "same"
    if fillers not in FILLERS:
        raise SystemExit("LLM response was not a revise")
    reply = payload["reply"]
    covers = payload.get("covers")
    if covers is not None:
        if not isinstance(covers, list):
            raise SystemExit("LLM response was not a revise")
        for item in covers:
            if not isinstance(item, dict) or set(item) != _COVER_FIELDS:
                raise SystemExit("LLM response was not a revise")
            for key in ("beat", "line", "through"):
                if isinstance(item[key], bool) or not isinstance(item[key], int):
                    raise SystemExit("LLM response was not a revise")
            if not isinstance(item["reason"], str):
                raise SystemExit("LLM response was not a revise")
    intent = payload["intent"]
    pace = payload["pace"]
    dip = payload["dip"]
    keep = payload["keep"]
    deliver = payload["deliver"]
    if not isinstance(reply, str) or not reply.strip():
        raise SystemExit("LLM response was not a revise")
    if not isinstance(intent, str) or not intent.strip():
        raise SystemExit("LLM response was not a revise")
    if pace not in PACES or deliver not in DELIVERS or type(dip) is not bool:
        raise SystemExit("LLM response was not a revise")
    if not isinstance(keep, list):
        raise SystemExit("LLM response was not a revise")
    parsed_keep = []
    for item in keep:
        if not isinstance(item, dict) or set(item) != _KEEP_FIELDS:
            raise SystemExit("LLM response was not a revise")
        uid = item["id"]
        reason = item["reason"]
        if isinstance(uid, bool) or not isinstance(uid, int) or not isinstance(reason, str):
            raise SystemExit("LLM response was not a revise")
        parsed_keep.append({"id": uid, "reason": reason})
    return {
        "reply": " ".join(reply.split()),
        "intent": intent.strip(),
        "pace": pace,
        "dip": dip,
        "keep": parsed_keep,
        "deliver": deliver,
        "covers": None if covers is None else [dict(item) for item in covers],
        "fillers": fillers,
        "cameras": cameras,
        "favor": favor if favor >= 0 else -1,
    }


def proposal_path(cuts_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(cuts_path)), PROPOSAL_NAME)


def read_history(path: str | None) -> list[dict]:
    """Prior turns as chat messages. A missing or odd file is no history."""
    if not path or not os.path.isfile(path):
        return []
    try:
        rows = json.loads(Path(path).read_text())
    except ValueError:
        return []
    if not isinstance(rows, list):
        return []
    turns = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "")
        text = " ".join(str(row.get("text") or "").split())
        if not text:
            continue
        if role == "you":
            turns.append({"role": "user", "content": text})
        elif role == "bot":
            turns.append({"role": "assistant", "content": text})
    return turns[-HISTORY_TURNS:]


def revise(
    cuts_path: str,
    note: str,
    *,
    pace: str = "open",
    dip: bool = True,
    propose: bool = False,
    history: str | None = None,
) -> None:
    text = " ".join(note.split())
    if not text:
        raise SystemExit("Say what to change")
    if pace not in PACES:
        raise SystemExit(f"Unknown pace: {pace}")
    from botcut.cli import load_cuts

    out_dir, doc = load_cuts(cuts_path)
    lines = doc.get("lines") or []
    if not lines:
        raise SystemExit("No lines to revise")
    print("Revising", flush=True)
    clips = doc.get("clips") or []
    beats = collect_beats(clips, load_beats(out_dir, clips))
    result = _plan(
        lines,
        text,
        str(doc.get("intent") or ""),
        pace,
        bool(dip),
        read_history(history),
        beats=beats,
        covers=current_runs(doc.get("covers"), beats),
        clips=clips,
        still_dir=os.path.join(out_dir, "work", "stills"),
        cameras=cameras_note(doc),
    )
    if not cams.groups(clips):
        result["cameras"], result["favor"] = "same", -1
    if not beats:
        # No B-roll in this cut: the proposal says nothing about runs, and the window does not either.
        result["covers"] = None
    if propose:
        # Nothing moves yet. The window shows the reply and asks before it applies.
        Path(proposal_path(cuts_path)).write_text(json.dumps({"note": text, **result}, indent=2) + "\n")
        print(result["reply"], flush=True)
        return
    _land(cuts_path, doc, lines, result)


def apply_proposal(cuts_path: str) -> None:
    """Land the proposal written by --propose. No model call."""
    from botcut.cli import load_cuts

    path = proposal_path(cuts_path)
    if not os.path.isfile(path):
        raise SystemExit("No proposal to apply")
    try:
        stored = json.loads(Path(path).read_text())
    except ValueError:
        raise SystemExit("The proposal could not be read")
    if not isinstance(stored, dict):
        raise SystemExit("The proposal could not be read")
    result = parse_revise({key: stored.get(key) for key in _FIELDS})
    _out_dir, doc = load_cuts(cuts_path)
    lines = doc.get("lines") or []
    if not lines:
        raise SystemExit("No lines to revise")
    _land(cuts_path, doc, lines, result)
    os.remove(path)


def _land(cuts_path: str, doc: dict, lines: list[dict], result: dict) -> None:
    new_lines = apply_revise(lines, result["keep"])
    if result.get("fillers") in ("cut", "keep"):
        for line in new_lines:
            if line.get("cuts"):
                line["cuts"] = [{**cut, "cut": result["fillers"] == "cut"} for cut in line["cuts"]]
    out_dir = os.path.dirname(os.path.abspath(cuts_path))
    clips = doc.get("clips") or []
    beats = collect_beats(clips, load_beats(out_dir, clips))
    # The line the movie opens on stays the opening while it is kept.
    opening = hook_line(new_lines, doc.get("hook"))
    hook = int(opening["id"]) if opening else None
    if hook is None:
        doc.pop("hook", None)
    # A line shown close stays so while it is kept.
    close = close_ids(doc.get("close"), new_lines)
    if close:
        doc["close"] = close
    else:
        doc.pop("close", None)
    claims = result.get("covers")
    if claims is None or not beats:
        # An older proposal, or no B-roll in the cut: the runs follow the lines.
        covers = kept_covers(doc.get("covers"), new_lines)
    else:
        covers = accept_runs(
            claims,
            beats={int(beat["id"]): beat for beat in beats},
            lines=new_lines,
            segments=None,
            durations=clip_durations(clips),
            still_dir=os.path.join(out_dir, "work", "stills"),
            hook=hook,
        )
    if covers:
        doc["covers"] = covers
    else:
        doc.pop("covers", None)
    if result.get("cameras", "same") != "same" and cams.groups(clips):
        asked = cams.read_cameras(doc.get("cameras"), clips)
        if result["cameras"] == "off":
            asked["off"] = True
        else:
            asked["off"] = False
            asked["pace"] = result["cameras"]
        asked["favor"] = cams.read_cameras({"favor": result.get("favor")}, clips)["favor"]
        if cams.write_cameras(asked):
            doc["cameras"] = cams.write_cameras(asked)
        else:
            doc.pop("cameras", None)
    doc["intent"] = result["intent"]
    doc["lines"] = new_lines
    doc["dropped"] = [
        {
            "id": int(line["id"]),
            "clip": int(line.get("clip") or 0),
            "start": float(line.get("start") or 0),
            "end": float(line.get("end") or 0),
            "text": str(line.get("text") or ""),
        }
        for line in new_lines
        if not line.get("keep")
    ]
    doc["revise"] = {"pace": result["pace"], "dip": result["dip"], "deliver": result["deliver"]}
    # The next Cut or Render applies the pace. A revise must not move max_pause.
    path = os.path.abspath(cuts_path)
    Path(path).write_text(json.dumps(doc, indent=2) + "\n")
    kept_n = sum(1 for line in new_lines if line.get("keep"))
    print(f"{kept_n} kept, {len(new_lines) - kept_n} dropped", flush=True)


def _plan(
    lines: list[dict],
    note: str,
    intent: str,
    pace: str,
    dip: bool,
    history: list[dict] | None = None,
    *,
    beats: list[dict] | None = None,
    covers: list[dict] | None = None,
    clips: list[dict] | None = None,
    still_dir: str | None = None,
    cameras: str = "",
) -> dict:
    if os.environ.get("BOTCUT_FAKE") == "1":
        return parse_revise(_fake(lines, covers))
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")
    text = _user_message(lines, note, intent, pace, dip, beats, covers, cameras)
    content: str | list = text
    if beats and clips and still_dir:
        from botcut.pick import _jpeg_data_url

        stills = beat_stills(clips, beats, still_dir)
        if stills:
            parts: list[dict] = [{"type": "text", "text": text}]
            for beat in beats:
                still = stills.get(int(beat["id"]))
                if not still:
                    continue
                parts.append({"type": "text", "text": f"Still for beat {int(beat['id'])}"})
                parts.append({"type": "image_url", "image_url": {"url": _jpeg_data_url(still)}})
            content = parts
    return ask(
        [
            {"role": "system", "content": REVISE_SYSTEM},
            *(history or []),
            {"role": "user", "content": content},
        ],
        REVISE_SCHEMA,
        what="a revise",
        parse=parse_revise,
    )


def _fake(lines: list[dict], covers: list[dict] | None = None) -> dict:
    # Drop the last id so an offline test with two lines sees one go.
    ids = []
    for line in lines:
        if str(line.get("reason") or "") == "card":
            continue
        try:
            ids.append(int(line["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    keep = [{"id": uid, "reason": "fake"} for uid in ids[:-1]]
    keep.append({"id": 10**9, "reason": "unknown"})
    return {
        "reply": FAKE_REPLY,
        "intent": FAKE_INTENT,
        "pace": "frenzied",
        "dip": False,
        "keep": keep,
        "deliver": "render",
        "covers": list(covers or []),
        "fillers": "same",
        "cameras": "same",
        "favor": -1,
    }


def cameras_note(doc: dict) -> str:
    """The cameras on each take and how they are cut now, for the model. Empty with one camera."""
    clips = doc.get("clips") or []
    by_main = cams.groups(clips)
    if not by_main:
        return ""
    asked = cams.read_cameras(doc.get("cameras"), clips)
    rows = ["Cameras that filmed the same take:"]
    for main, others in by_main.items():
        for cam in (main, *others):
            what = "the main camera" if cam == main else "another camera"
            view = str(clips[cam].get("view") or "")
            name = os.path.basename(str(clips[cam].get("path") or ""))
            rows.append(f"camera {cam}, {what}{', the ' + view + ' view' if view else ''}, {name}")
    now = "off" if asked["off"] else asked["pace"]
    favor = asked["favor"] if asked["favor"] is not None else -1
    runs = len(doc.get("angles") or [])
    rows.append(f"Cameras now: {now}, favor {favor}. The picture goes to another camera {runs} times.")
    return "\n".join(rows)


def _user_message(
    lines: list[dict],
    note: str,
    intent: str,
    pace: str,
    dip: bool,
    beats: list[dict] | None = None,
    covers: list[dict] | None = None,
    cameras: str = "",
) -> str:
    body = [
        f"The movie is: {intent}",
        f"Pace: {pace}",
        f"Dip to black: {'on' if dip else 'off'}",
        "",
    ]
    for line in lines:
        if str(line.get("reason") or "") == "card":
            continue
        try:
            uid = int(line["id"])
        except (KeyError, TypeError, ValueError):
            continue
        state = "keep" if line.get("keep") else "drop"
        body.append(f"[{uid}] {state} ({line.get('reason') or ''}) {line.get('text') or ''}")
    if beats:
        body.append("")
        body.append("B-roll beats, each a few seconds of one shot:")
        for beat in beats:
            dur = float(beat["end"]) - float(beat["start"])
            body.append(f"beat {int(beat['id'])}, {dur:.1f}s, shot {int(beat['clip'])}")
        body.append("")
        if covers:
            body.append("B-roll runs laid now:")
            for item in covers:
                body.append(
                    f"run: beat {item['beat']}, lines {item['line']}-{item['through']}, {item['reason']}"
                )
        else:
            body.append("No B-roll is laid now.")
    if cameras:
        body.append("")
        body.append(cameras)
    body.append("")
    body.append(f"Note: {note}")
    return "\n".join(body)


def _beat_id(cover: dict, beats: list[dict]) -> int | None:
    """The beat a stored run starts on, by its window's start."""
    start = cover.get("start")
    try:
        start = float(start)
    except (TypeError, ValueError):
        return None
    for beat in beats:
        if int(beat["clip"]) == int(cover.get("clip", -1)) and abs(float(beat["start"]) - start) < 0.002:
            return int(beat["id"])
    return None


def current_runs(covers, beats: list[dict]) -> list[dict]:
    """Stored runs as claims the model can hand back."""
    rows = []
    for item in covers or []:
        if not isinstance(item, dict) or item.get("through") is None:
            continue
        beat = _beat_id(item, beats)
        if beat is None:
            continue
        rows.append(
            {
                "beat": beat,
                "line": int(item["line"]),
                "through": int(item["through"]),
                "reason": str(item.get("reason") or ""),
            }
        )
    return rows


def load_beats(out_dir: str, clips: list[dict]) -> dict:
    """The beats cache the cut wrote, by clip index. No ffmpeg: a missing cache is no beats."""
    found = {}
    for index in broll_indexes(clips):
        clip = clips[index]
        stem = Path(str(clip.get("path") or "")).stem
        cache = os.path.join(out_dir, "work", f"{index}-{stem}.beats.json")
        if not os.path.isfile(cache):
            continue
        try:
            rows = json.loads(Path(cache).read_text())
        except ValueError:
            continue
        if isinstance(rows, list):
            found[index] = rows
    return found
