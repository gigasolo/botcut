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
                        "required": ["id", "reason", "cuts"],
                        "properties": {
                            "id": {"type": "integer"},
                            "reason": {"type": "string"},
                            # Numbers from the cuts offered on that line. Never times.
                            "cuts": {"type": "array", "items": {"type": "integer"}},
                        },
                    },
                }
            },
        },
    },
}


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
        # A line that is nothing else is dropped as a line, not cut down to nothing.
        if first == 0 and last == len(words) - 1:
            continue
        before = float(words[first - 1]["end"]) if first > 0 else float(utt["start"])
        after = float(words[last + 1]["start"]) if last + 1 < len(words) else float(utt["end"])
        start = min(float(words[first]["start"]), before + CUT_AIR) if first > 0 else before
        end = max(float(words[last]["end"]), after - CUT_AIR) if last + 1 < len(words) else after
        if end - start < CUT_MIN:
            continue
        found.append(
            {
                "from": first,
                "through": last,
                "start": round(start, 3),
                "end": round(end, 3),
                "reason": reason,
                "cut": False,
            }
        )
    return found


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


# A long shoot goes to the model in parts, so no request carries more lines
# than it reads well, and every part gets its own stills.
CHUNK_LINES = 150
CHUNK_OVERLAP = 10
CHUNK_WORKERS = 3


def pick(utts: list[dict], intent: str = "") -> list[dict]:
    if os.environ.get("BOTCUT_FAKE") == "1":
        return [_kept(u["id"], "fake", range(len(u.get("cuts") or []))) for u in utts]
    # The key is asked for where the request is made, so a replayed answer needs none.
    parts = chunks(utts)
    if len(parts) == 1:
        return _ask_keep(utts, intent)
    from concurrent.futures import ThreadPoolExecutor

    def ask(numbered: tuple[int, dict]) -> list[dict]:
        number, part = numbered
        note = (
            f"\nThese lines are part {number} of {len(parts)} of the movie. "
            "Lines before or after them exist and are judged separately."
        )
        kept = _ask_keep(part["lines"], intent, note)
        return [item for item in kept if item["id"] in part["owned"]]

    with ThreadPoolExecutor(max_workers=CHUNK_WORKERS) as pool:
        answers = list(pool.map(ask, enumerate(parts, start=1)))
    return [item for answer in answers for item in answer]


def _kept(uid, reason, cuts) -> dict:
    """One kept line. The cuts taken inside it are listed only when there are some."""
    row = {"id": int(uid), "reason": str(reason)}
    numbers = [int(number) for number in cuts]
    if numbers:
        row["cuts"] = numbers
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


def _ask_keep(utts: list[dict], intent: str, note: str = "") -> list[dict]:
    # A reply that is not the schema is asked for once more before the cut stops.
    return ask(
        [
            {"role": "system", "content": system_prompt(intent) + note},
            {"role": "user", "content": user_content(utts)},
        ],
        KEEP_SCHEMA,
        what="a keep list",
        parse=lambda parsed: [
            _kept(item["id"], item["reason"], item.get("cuts") or []) for item in parsed["keep"]
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
        offered = utt.get("cuts") or []
        if offered:
            row["cuts"] = [
                {**cut, "cut": number in taken.get(uid, set())} for number, cut in enumerate(offered)
            ]
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


def _user_message(utts: list[dict]) -> str:
    rows = "\n".join(
        f"[{u['id']}] (clip {u['clip']}, {u['start']:.2f}-{u['end']:.2f}) {u['text']}{_offer(u)}"
        for u in utts
    )
    return (CUTS_NOTE + rows) if any(u.get("cuts") for u in utts) else rows


def user_content(utts: list[dict]) -> str | list[dict]:
    """Text when no still exists. Otherwise the lines, then one JPEG per shown line."""
    ready = [u for u in utts if u.get("still") and os.path.isfile(str(u["still"]))]
    if not ready:
        return _user_message(utts)
    if len(ready) > MAX_STILLS:
        step = len(ready) / MAX_STILLS
        ready = [ready[int(i * step)] for i in range(MAX_STILLS)]
    parts: list[dict] = [
        {
            "type": "text",
            "text": (
                "A still from the middle of a line follows that line when one exists. "
                "Drop a blurred, dark, or unusable picture. Keep a clean look. "
                "Return ids and reasons only. A reason may mention the picture.\n\n"
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


