"""Group words into utterances and turn kept ids into padded ranges.

The model returns ids and reasons. It never supplies timestamps.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

from botcut.llm import ask, chat_fields, llm_url, model_name, reasoning_effort  # noqa: F401

UTTERANCE_GAP = 0.5
MERGE_GAP = 1.0
PAD_BEFORE = 0.25
PAD_AFTER = 0.40
# Token-set overlap, or a 4-token phrase contained in order inside a kept line.
NEAR_JACCARD = 0.5
NEAR_MIN_TOKENS = 4

DEFAULT_INTENT = (
    "Keep each moment in order. Drop flubs and true retakes. Keep a beat that appears only once."
)

RETAKE_PROMPT = (
    "These are takes recorded in order for one video. "
    "When a line is repeated, keep the last complete clean take unless an earlier one is clearly better. "
    'Drop false starts, flubs, "let me redo that", off-topic chatter, and filler-only utterances. '
    "Never drop unique content. Return ids only."
)

STORY_PROMPT = (
    "These clips are one movie, in order. "
    "Drop false starts, flubs, and filler-only lines. "
    "When the same line is a retake, keep the last clean one. "
    "Keep a beat that appears only once. "
    "Do not drop a clip that has its own content. "
    "Return ids only."
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
                        "required": ["id", "reason", "cuts", "trim"],
                        "properties": {
                            "id": {"type": "integer"},
                            "reason": {"type": "string"},
                            # Numbers from the cuts offered on that line. Never times.
                            "cuts": {"type": "array", "items": {"type": "integer"}},
                            # Words of the line to take out, copied as said. Never times.
                            "trim": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                }
            },
        },
    },
}


# The whole shoot is read once before any line is judged. A shoot of fewer lines
# than this fits in one keep request, where every retake is already side by side.
OUTLINE_MIN_LINES = 6
OUTLINE_MAX_LINES = 1500
# A length nobody would ask a rough cut for is not a length.
TARGET_MAX = 4 * 3600

OUTLINE_PROMPT = (
    "You are the editor reading every line of a shoot before cutting it. "
    "These clips are one movie, in order. Read all of it first. "
    "Return the beats of the movie in order, each with a title of two to five words "
    "and its first and last line ids. "
    "Return every group of lines that say the same thing, however far apart they are, "
    "as retakes, each group's ids in order. A group has at least two lines. "
    "Return as hook the id of the one line that would open the movie best if it were "
    "moved to the very front, a complete thought that makes a viewer want the rest, "
    "or -1 when the movie already opens well or no line stands on its own. "
    "Return as target_seconds the length the movie sentence asks for, in seconds, "
    "or 0 when it names no length. "
    "Do not invent ids. Do not return times."
)

OUTLINE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "outline",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["beats", "retakes", "hook", "target_seconds"],
            "properties": {
                "beats": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["title", "first", "last"],
                        "properties": {
                            "title": {"type": "string"},
                            "first": {"type": "integer"},
                            "last": {"type": "integer"},
                        },
                    },
                },
                "retakes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["ids"],
                        "properties": {"ids": {"type": "array", "items": {"type": "integer"}}},
                    },
                },
                "hook": {"type": "integer"},
                "target_seconds": {"type": "integer"},
            },
        },
    },
}


def no_outline() -> dict:
    return {"beats": [], "retakes": [], "hook": -1, "target_seconds": 0}


def _whole(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def read_outline(payload: object, utts: list[dict]) -> dict:
    """The outline with only ids that exist. Anything else in it is left out, not trusted."""
    if not isinstance(payload, dict):
        raise ValueError("not an outline")
    order = {int(u["id"]): index for index, u in enumerate(utts)}
    beats = []
    for item in payload["beats"]:
        first, last = _whole(item.get("first")), _whole(item.get("last"))
        title = " ".join(str(item.get("title") or "").split())[:60]
        if first in order and last in order and order[first] <= order[last] and title:
            beats.append({"title": title, "first": first, "last": last})
    retakes = []
    grouped: set[int] = set()
    for item in payload["retakes"]:
        ids = []
        for value in item.get("ids") or []:
            uid = _whole(value)
            if uid in order and uid not in grouped and uid not in ids:
                ids.append(uid)
        if len(ids) >= 2:
            ids.sort(key=lambda uid: order[uid])
            retakes.append(ids)
            grouped.update(ids)
    hook = _whole(payload["hook"])
    target = _whole(payload["target_seconds"]) or 0
    return {
        "beats": beats,
        "retakes": retakes,
        "hook": hook if hook in order else -1,
        "target_seconds": target if 0 < target <= TARGET_MAX else 0,
    }


def _outline_rows(utts: list[dict]) -> str:
    return "\n".join(
        f"[{u['id']}] (clip {u['clip']}, {float(u['end']) - float(u['start']):.1f}s) {u['text']}"
        for u in utts
    )


def outline(utts: list[dict], intent: str = "") -> dict:
    """Read the whole shoot once: its beats, its retakes, a line to open on, a length.

    One request carries every line, as words only. A cut still happens when
    this cannot be had: the lines are then judged the way they were before.
    """
    if os.environ.get("BOTCUT_FAKE") == "1":
        return no_outline()
    if not OUTLINE_MIN_LINES <= len(utts) <= OUTLINE_MAX_LINES:
        return no_outline()
    line = intent.strip() or DEFAULT_INTENT
    try:
        return ask(
            [
                {"role": "system", "content": f"{OUTLINE_PROMPT}\nThe movie is: {line}"},
                {"role": "user", "content": _outline_rows(utts)},
            ],
            OUTLINE_SCHEMA,
            what="an outline",
            parse=lambda parsed: read_outline(parsed, utts),
            read_timeout=300,
            tries=2,
            effort="high",
        )
    except SystemExit as stop:
        # With no key nothing can be asked, and the cut should say so.
        if "XAI_API_KEY" in str(stop):
            raise
        print("Cutting without an outline", flush=True)
        return no_outline()


def outline_note(plan: dict | None, part: list[dict], utts: list[dict]) -> str:
    """What the whole shoot says, for a request that may carry only part of it."""
    if not plan:
        return ""
    by_id = {int(u["id"]): u for u in utts}
    here = {int(u["id"]) for u in part}
    body = []
    beats = [beat for beat in plan.get("beats") or [] if beat["first"] in by_id and beat["last"] in by_id]
    if beats:
        body.append("The beats of the whole movie, in order:")
        body.extend(
            f"{number}. {beat['title']} (lines {beat['first']}-{beat['last']})"
            for number, beat in enumerate(beats, start=1)
        )
    groups = [
        group
        for group in plan.get("retakes") or []
        if any(uid in here for uid in group) and all(uid in by_id for uid in group)
    ]
    if groups:
        body.append(
            "Lines that say the same thing. Keep one of each group, the last complete clean take "
            "unless an earlier one is clearly better. A line marked elsewhere is decided in "
            "another part by this same rule, so drop yours when that one is the take to keep:"
        )
        for group in groups:
            body.append(
                " / ".join(
                    f"[{uid}]{'' if uid in here else ' (elsewhere)'} {by_id[uid]['text']}" for uid in group
                )
            )
    target = int(plan.get("target_seconds") or 0)
    if target > 0:
        total = sum(float(u["end"]) - float(u["start"]) for u in utts)
        mine = sum(float(u["end"]) - float(u["start"]) for u in part)
        body.append(
            f"The movie should run about {target}s. Every line together runs {total:.0f}s, "
            f"and the lines here run {mine:.0f}s, so keep about {_share(target, total, mine):.0f}s of them: "
            "the ones the movie cannot do without. Each line shows its start and end in seconds. "
            "Where this and keeping every beat disagree, the length wins."
        )
    return "\n".join(body) + "\n\n" if body else ""


def _share(target: float, total: float, mine: float) -> float:
    if total <= 0:
        return mine
    return min(mine, target * mine / total)


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
            spoken = {"text": text, "start": start, "end": end}
            if current is None:
                current = _utt(next_id, clip, start, end, text)
                current["words"] = [spoken]
                next_id += 1
                continue
            if start - current["end"] > UTTERANCE_GAP:
                found.append(current)
                current = _utt(next_id, clip, start, end, text)
                current["words"] = [spoken]
                next_id += 1
            else:
                current["end"] = end
                current["text"] = f"{current['text']} {text}"
                current["words"].append(spoken)
        if current is not None:
            found.append(current)
    for utt in found:
        utt["cuts"] = word_cuts(utt)
    return found


# Sounds that carry no words. A cut inside a line only ever removes these, or a
# phrase said twice in a row.
FILLERS = {"um", "umm", "uhm", "uh", "uhh", "er", "erm", "ah", "hmm", "mm", "mhm"}
# The longest phrase looked for as a stumbled restart: "we were, we were going".
RESTART_WORDS = 3
# Air left on each side of a cut inside a line, and the shortest cut worth a jump.
CUT_AIR = 0.04
CUT_MIN = 0.15


def _bare(text: str) -> str:
    return re.sub(r"[^a-z0-9']", "", text.lower())


def word_cuts(utt: dict) -> list[dict]:
    """Stretches inside a line that could come out, by word position.

    The times are worked out here, from the word times. The model is only
    offered these by number, and says which to take.
    """
    words = utt.get("words") or []
    # A word with a space in it would not line up with the text on screen.
    if len(words) < 2 or len(str(utt.get("text") or "").split()) != len(words):
        return []
    bare = [_bare(str(word["text"])) for word in words]
    spans: list[tuple[int, int, str]] = []
    index = 0
    while index < len(words):
        if bare[index] in FILLERS:
            last = index
            while last + 1 < len(words) and bare[last + 1] in FILLERS:
                last += 1
            spans.append((index, last, "filler"))
            index = last + 1
            continue
        took = 0
        for size in range(RESTART_WORDS, 0, -1):
            first = bare[index : index + size]
            again = bare[index + size : index + 2 * size]
            if len(again) == size and first == again and all(first):
                spans.append((index, index + size - 1, "said twice"))
                took = size
                break
        index += took or 1
    found = []
    for first, last, reason in spans:
        row = _cut_row(utt, first, last, reason)
        if row is not None:
            found.append(row)
    return found


def _cut_row(utt: dict, first: int, last: int, reason: str) -> dict | None:
    """The stretch that takes words first..last out of a line, or None when it is not worth a jump."""
    words = utt.get("words") or []
    # A line that is nothing else is dropped as a line, not cut down to nothing.
    if first < 0 or last >= len(words) or first > last or (first == 0 and last == len(words) - 1):
        return None
    before = float(words[first - 1]["end"]) if first > 0 else float(utt["start"])
    after = float(words[last + 1]["start"]) if last + 1 < len(words) else float(utt["end"])
    start = min(float(words[first]["start"]), before + CUT_AIR) if first > 0 else before
    end = max(float(words[last]["end"]), after - CUT_AIR) if last + 1 < len(words) else after
    if end - start < CUT_MIN:
        return None
    return {
        "from": first,
        "through": last,
        "start": round(start, 3),
        "end": round(end, 3),
        "reason": reason,
        "cut": False,
    }


# A trim the model names may take at most this share of a line's words, and
# must leave this many. More than that is a line to drop, not to cut down.
TRIM_SHARE_MAX = 0.6
TRIM_WORDS_LEFT = 2


def trim_cuts(utt: dict, phrases: list, known: list[dict] | None = None) -> list[dict]:
    """The cuts that take the named words out of a line, each already taken.

    The model copies words from the line. They are found here, in order, and
    the times come from the word times. Words that are not in the line, that
    are most of it, or that only partly overlap a cut already on offer, are
    left alone. `known` is the cuts on offer: one a trim swallows whole is
    replaced by it.
    """
    words = utt.get("words") or []
    if len(words) < 2 or len(str(utt.get("text") or "").split()) != len(words):
        return []
    bare = [_bare(str(word["text"])) for word in words]
    offered = [(int(cut["from"]), int(cut["through"])) for cut in known or []]
    claimed: list[tuple[int, int]] = []
    found = []
    for phrase in phrases or []:
        wanted = [token for token in (_bare(part) for part in str(phrase or "").split()) if token]
        if not wanted or len(wanted) > len(words) * TRIM_SHARE_MAX:
            continue
        for first in range(len(words) - len(wanted) + 1):
            last = first + len(wanted) - 1
            if bare[first : last + 1] != wanted:
                continue
            if any(first <= c_last and c_first <= last for c_first, c_last in claimed):
                continue
            # A cut on offer is either inside the trim or clear of it.
            if any(
                first <= o_last and o_first <= last and not (first <= o_first and o_last <= last)
                for o_first, o_last in offered
            ):
                continue
            gone = sum(c_last - c_first + 1 for c_first, c_last in claimed) + len(wanted)
            if len(words) - gone < TRIM_WORDS_LEFT:
                break
            row = _cut_row(utt, first, last, "trimmed")
            if row is not None:
                claimed.append((first, last))
                found.append({**row, "cut": True})
            break
    return sorted(found, key=lambda cut: cut["from"])


def cut_words(segments: list[dict], lines: list[dict]) -> list[dict]:
    """Take the chosen cuts of the kept lines out of the ranges that will be rendered."""
    gone: dict[int, list[tuple[float, float]]] = {}
    for line in lines:
        if not line.get("keep"):
            continue
        for cut in line.get("cuts") or []:
            if cut.get("cut"):
                gone.setdefault(int(line["clip"]), []).append((float(cut["start"]), float(cut["end"])))
    if not gone:
        return segments
    out = []
    for seg in segments:
        pieces = [(float(seg["start"]), float(seg["end"]))]
        for cut_start, cut_end in sorted(gone.get(int(seg["clip"]), [])):
            nxt = []
            for start, end in pieces:
                if cut_end <= start or cut_start >= end:
                    nxt.append((start, end))
                    continue
                if cut_start - start >= CUT_MIN:
                    nxt.append((start, cut_start))
                if end - cut_end >= CUT_MIN:
                    nxt.append((cut_end, end))
            pieces = nxt
        out.extend({**seg, "start": start, "end": end} for start, end in pieces)
    return out


# A piece shorter than this flashes by. One with nobody speaking in it is left out.
PIECE_MIN = 0.6
SPEECH_MIN = 0.08


def settle(segments: list[dict], lines: list[dict]) -> list[dict]:
    """Leave out the pieces that are only a flash of air.

    Padding before a line whose first sound was cut, or after one whose last
    was, is a quarter second of nobody speaking between two jumps. A short
    piece with words in it stays: the sentence needs them.
    """
    said: dict[int, list[tuple[float, float]]] = {}
    for line in lines or []:
        if not isinstance(line, dict) or not line.get("keep"):
            continue
        try:
            clip, spans = int(line["clip"]), [(float(line["start"]), float(line["end"]))]
            for cut in line.get("cuts") or []:
                if not cut.get("cut"):
                    continue
                low, high = float(cut["start"]), float(cut["end"])
                spans = [
                    part
                    for start, end in spans
                    for part in ((start, min(end, low)), (max(start, high), end))
                    if part[1] > part[0]
                ]
        except (KeyError, TypeError, ValueError):
            continue
        said.setdefault(clip, []).extend(spans)
    out = []
    for seg in segments:
        start, end = float(seg["start"]), float(seg["end"])
        if str(seg.get("reason") or "") != "card" and end - start < PIECE_MIN:
            spoken = sum(
                max(0.0, min(end, high) - max(start, low)) for low, high in said.get(int(seg["clip"]), [])
            )
            if spoken < SPEECH_MIN:
                continue
        out.append(seg)
    # A movie of nothing but flashes still plays what it has.
    return out or segments


# A long shoot goes to the model in parts, so no request carries more lines
# than it reads well, and every part gets its own stills.
CHUNK_LINES = 150
CHUNK_OVERLAP = 10
CHUNK_WORKERS = 3


def pick(utts: list[dict], intent: str = "", outline: dict | None = None) -> list[dict]:
    if os.environ.get("BOTCUT_FAKE") == "1":
        return [_kept(u["id"], "fake", range(len(u.get("cuts") or []))) for u in utts]
    # The key is asked for where the request is made, so a replayed answer needs none.
    parts = chunks(utts)
    retaken = {uid for group in (outline or {}).get("retakes") or [] for uid in group}
    if len(parts) == 1:
        return _ask_keep(utts, intent, before=outline_note(outline, utts, utts), prefer=retaken)
    from concurrent.futures import ThreadPoolExecutor

    def ask(numbered: tuple[int, dict]) -> list[dict]:
        number, part = numbered
        note = (
            f"\nThese lines are part {number} of {len(parts)} of the movie. "
            "Lines before or after them exist and are judged separately."
        )
        kept = _ask_keep(
            part["lines"],
            intent,
            note,
            before=outline_note(outline, part["lines"], utts),
            prefer=retaken,
        )
        return [item for item in kept if item["id"] in part["owned"]]

    with ThreadPoolExecutor(max_workers=CHUNK_WORKERS) as pool:
        answers = list(pool.map(ask, enumerate(parts, start=1)))
    return [item for answer in answers for item in answer]


def _kept(uid, reason, cuts, trim=()) -> dict:
    """One kept line. The cuts taken inside it are listed only when there are some."""
    row = {"id": int(uid), "reason": str(reason)}
    numbers = [int(number) for number in cuts]
    if numbers:
        row["cuts"] = numbers
    phrases = [" ".join(str(phrase).split()) for phrase in trim or [] if str(phrase).strip()]
    if phrases:
        row["trim"] = phrases
    return row


def chunks(utts: list[dict], size: int = CHUNK_LINES, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """Overlapping runs of lines. Each id is owned by exactly one run.

    Neighbours share `overlap` lines so a retake across the join is seen whole.
    The shared lines are split down the middle: each run decides the half
    nearer its own body.
    """
    if len(utts) <= size:
        return [{"lines": utts, "owned": {u["id"] for u in utts}}]
    step = size - overlap
    half = overlap // 2
    parts = []
    start = 0
    while True:
        end = min(len(utts), start + size)
        last = end == len(utts)
        own_from = start + (half if start > 0 else 0)
        own_to = end if last else start + step + half
        parts.append(
            {
                "lines": utts[start:end],
                "owned": {u["id"] for u in utts[own_from:own_to]},
            }
        )
        if last:
            return parts
        start += step


def _ask_keep(
    utts: list[dict],
    intent: str,
    note: str = "",
    *,
    before: str = "",
    prefer: set[int] | None = None,
) -> list[dict]:
    # A reply that is not the schema is asked for once more before the cut stops.
    return ask(
        [
            {"role": "system", "content": system_prompt(intent) + note},
            {"role": "user", "content": user_content(utts, before=before, prefer=prefer)},
        ],
        KEEP_SCHEMA,
        what="a keep list",
        parse=lambda parsed: [
            _kept(item["id"], item["reason"], item.get("cuts") or [], item.get("trim") or [])
            for item in parsed["keep"]
        ],
        tries=2,
    )


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


def hook_line(lines: list[dict], hook: object) -> dict | None:
    """The kept spoken line the movie opens on, or None when there is none."""
    if isinstance(hook, bool) or not isinstance(hook, int) or hook < 0:
        return None
    for line in lines or []:
        try:
            if int(line["id"]) != hook:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        if line.get("keep") and str(line.get("reason") or "") != "card":
            return line
        return None
    return None


def play_order(segments: list[dict], lines: list[dict], hook: object) -> list[dict]:
    """The pieces in the order they play: the hook line first, then everything as it was.

    The hook is lifted out of the piece it sits in with its usual lead and tail,
    and never more than half the air to a neighbour, and is gone from its place. Its pieces carry `hook`, so what
    reads the cut later can tell the opening from the body. Nothing else moves.
    """
    segments = [{key: value for key, value in seg.items() if key != "hook"} for seg in segments]
    line = hook_line(lines, hook)
    if line is None:
        return segments
    clip = int(line["clip"])
    start, end = float(line["start"]), float(line["end"])
    low, high = start - PAD_BEFORE, end + PAD_AFTER
    for other in lines:
        try:
            if int(other["clip"]) != clip or int(other["id"]) == int(line["id"]):
                continue
            other_start, other_end = float(other["start"]), float(other["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if other_end <= start:
            low = max(low, (other_end + start) / 2)
        elif other_start >= end:
            high = min(high, (end + other_start) / 2)
    opening, body = [], []
    for seg in segments:
        seg_start, seg_end = float(seg["start"]), float(seg["end"])
        if int(seg["clip"]) != clip or seg_end <= low or seg_start >= high or seg.get("reason") == "card":
            body.append(seg)
            continue
        if low - seg_start >= CUT_MIN:
            body.append({**seg, "end": low})
        opening.append({**seg, "start": max(seg_start, low), "end": min(seg_end, high), "hook": True})
        if seg_end - high >= CUT_MIN:
            body.append({**seg, "start": high})
    return [*opening, *body]


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


def system_prompt(intent: str = "") -> str:
    """Story prompt by default. A line about repeated takes keeps the retake prompt.

    The default sentence mentions retakes as something to drop, so that wording
    stays on the story prompt.
    """
    line = intent.strip() or DEFAULT_INTENT
    if _retake_job(line):
        return f"{RETAKE_PROMPT}\nThe movie is: {line}"
    return f"{STORY_PROMPT}\nThe movie is: {line}"


def _retake_job(intent: str) -> bool:
    text = intent.lower()
    if text == DEFAULT_INTENT.lower():
        return False
    return "repeated take" in text or "retake" in text


def decision_lines(utts: list[dict], keep: list[dict]) -> list[dict]:
    reasons = {int(item["id"]): str(item["reason"]) for item in keep}
    taken = {int(item["id"]): {int(number) for number in item.get("cuts") or []} for item in keep}
    trims = {int(item["id"]): item.get("trim") or [] for item in keep}
    kept = kept_utterances(utts, keep)
    dropped = dropped_utterances(utts, keep)
    drop_reason = {}
    for utt in dropped:
        if any(near_duplicate(utt["text"], other["text"]) for other in kept):
            drop_reason[int(utt["id"])] = "retake"
        else:
            drop_reason[int(utt["id"])] = "unique?"
    rows = []
    for utt in utts:
        uid = int(utt["id"])
        kept_reason = reasons.get(uid)
        row = {
            "id": uid,
            "clip": int(utt["clip"]),
            "start": float(utt["start"]),
            "end": float(utt["end"]),
            "text": str(utt["text"]),
            "keep": kept_reason is not None,
            "reason": kept_reason if kept_reason is not None else drop_reason.get(uid, "dropped"),
        }
        still = str(utt.get("still") or "")
        if still and os.path.isfile(still):
            row["still"] = os.path.abspath(still)
        # Every cut on offer is listed, so one the model left in can still be taken by hand.
        offered = [
            {**cut, "cut": number in taken.get(uid, set())}
            for number, cut in enumerate(utt.get("cuts") or [])
        ]
        # Words the model named on a line it kept come out too, and can be put back by hand.
        named = trim_cuts(utt, trims.get(uid) or [], offered) if kept_reason is not None else []
        if named:
            offered = [
                cut
                for cut in offered
                if not any(new["from"] <= cut["from"] and cut["through"] <= new["through"] for new in named)
            ]
            offered = sorted([*offered, *named], key=lambda cut: cut["from"])
        if offered:
            row["cuts"] = offered
        rows.append(row)
    return rows


def _utt(uid: int, clip: int, start: float, end: float, text: str) -> dict:
    return {"id": uid, "clip": clip, "start": start, "end": end, "text": text}


# A long interview can have more stills than one request should carry.
MAX_STILLS = 40


CUTS_NOTE = (
    "Some lines end with cuts on offer, numbered from 0: a filler sound, or words said twice in a row. "
    "For a line you keep, return the numbers of the cuts that should come out, or an empty list. "
    "Take a filler. Take a stumbled restart. Leave words said twice on purpose, like \"no, no\" "
    "or \"very, very\". A line with no cuts on offer gets an empty list.\n\n"
)


def _offer(utt: dict) -> str:
    cuts = utt.get("cuts") or []
    if not cuts:
        return ""
    words = utt.get("words") or []
    said = [
        " ".join(str(word["text"]) for word in words[cut["from"] : cut["through"] + 1]) for cut in cuts
    ]
    return " {cuts: " + ", ".join(f'{number}="{text}"' for number, text in enumerate(said)) + "}"


TRIM_NOTE = (
    "For a line you keep, return as trim the words inside it that should come out, copied exactly "
    "as they are written, a few words at a time: a crutch that carries nothing (\"you know\", "
    "\"I mean\", \"sort of\", a \"like\" or \"so\" that is only a pause), the abandoned start of a "
    "thought that is said again in other words, a stutter. Never trim words the sentence needs, "
    "never most of a line, and never what a cut on offer already takes. Most lines get an empty list.\n\n"
)


def _user_message(utts: list[dict]) -> str:
    rows = "\n".join(
        f"[{u['id']}] (clip {u['clip']}, {u['start']:.2f}-{u['end']:.2f}) {u['text']}{_offer(u)}"
        for u in utts
    )
    return (CUTS_NOTE if any(u.get("cuts") for u in utts) else "") + TRIM_NOTE + rows


def shown_stills(ready: list[dict], prefer: set[int] | None = None) -> list[dict]:
    """At most MAX_STILLS lines to show, in order.

    Retakes go first: which of two takes looks better is the question a picture
    answers. What is left is spread evenly over the other lines.
    """
    if len(ready) <= MAX_STILLS:
        return ready
    first = [u for u in ready if int(u["id"]) in (prefer or set())]
    if len(first) > MAX_STILLS:
        step = len(first) / MAX_STILLS
        first = [first[int(i * step)] for i in range(MAX_STILLS)]
    rest = [u for u in ready if int(u["id"]) not in (prefer or set())]
    room = MAX_STILLS - len(first)
    if room > 0 and rest:
        step = len(rest) / room
        rest = [rest[int(i * step)] for i in range(room)] if len(rest) > room else rest
    else:
        rest = []
    order = {int(u["id"]): index for index, u in enumerate(ready)}
    return sorted([*first, *rest], key=lambda u: order[int(u["id"])])


def user_content(
    utts: list[dict], *, before: str = "", prefer: set[int] | None = None
) -> str | list[dict]:
    """Text when no still exists. Otherwise the lines, then one JPEG per shown line.

    `before` is what the whole shoot says, and goes ahead of the lines.
    """
    ready = [u for u in utts if u.get("still") and os.path.isfile(str(u["still"]))]
    if not ready:
        return before + _user_message(utts)
    ready = shown_stills(ready, prefer)
    parts: list[dict] = [
        {
            "type": "text",
            "text": (
                "A still from the middle of a line follows that line when one exists. "
                "Drop a blurred, dark, or unusable picture. Keep a clean look. "
                "Return ids and reasons only. A reason may mention the picture.\n\n"
                + before
                + _user_message(utts)
            ),
        }
    ]
    for utt in ready:
        parts.append({"type": "text", "text": f"Still for [{int(utt['id'])}]"})
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": _jpeg_data_url(str(utt["still"]))},
            }
        )
    return parts


def _jpeg_data_url(path: str) -> str:
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return "data:image/jpeg;base64," + encoded


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


