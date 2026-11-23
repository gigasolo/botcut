"""Plain checks on a finished cut. No model is asked.

Each flag names something a viewer would notice: a point made twice, a line
that opens on a word leaning on one that was dropped, a piece too short to
read as a shot, a movie well off the length that was asked for. The bench
counts them, and the proof pass is shown them.
"""

from __future__ import annotations

import re

from botcut.pick import near_duplicate

# A line that opens on one of these follows from the line before it.
LEANS = {"and", "but", "so", "because", "or", "then", "also"}
# A piece shorter than this flashes by.
PIECE_MIN = 0.6
# How far off the asked length a cut can be before it is flagged.
LENGTH_SLACK = 0.15

KINDS = ("twice", "leans", "flash", "long", "short")


def _spoken(lines: list[dict]) -> list[dict]:
    return [
        line
        for line in lines or []
        if isinstance(line, dict) and str(line.get("reason") or "") != "card" and "id" in line
    ]


def _first_word(text: str) -> str:
    found = re.match(r"[^a-z0-9']*([a-z0-9']+)", str(text or "").lower())
    return found.group(1) if found else ""


def _length(row: dict) -> float:
    try:
        return max(0.0, float(row["end"]) - float(row["start"]))
    except (KeyError, TypeError, ValueError):
        return 0.0


def cut_seconds(lines: list[dict], segments: list[dict] | None = None) -> float:
    """How long the cut plays: the pieces when there are some, otherwise the kept lines."""
    if segments:
        return sum(_length(seg) for seg in segments)
    return sum(_length(line) for line in lines or [] if isinstance(line, dict) and line.get("keep"))


def flags(lines: list[dict], segments: list[dict] | None = None, target: float = 0.0) -> list[dict]:
    """What a viewer would notice, as rows of kind, line ids, and a sentence."""
    found: list[dict] = []
    spoken = _spoken(lines)
    kept = [line for line in spoken if line.get("keep")]
    for index, line in enumerate(kept):
        for earlier in kept[:index]:
            if near_duplicate(str(earlier.get("text") or ""), str(line.get("text") or "")):
                found.append(
                    {
                        "kind": "twice",
                        "ids": [int(earlier["id"]), int(line["id"])],
                        "text": f"Lines {int(earlier['id'])} and {int(line['id'])} say the same thing.",
                    }
                )
                break
    for before, line in zip(spoken, spoken[1:]):
        if not line.get("keep") or before.get("keep"):
            continue
        word = _first_word(line.get("text"))
        if word in LEANS:
            found.append(
                {
                    "kind": "leans",
                    "ids": [int(line["id"])],
                    "text": f'Line {int(line["id"])} opens on "{word}" and the line before it is dropped.',
                }
            )
    for seg in segments or []:
        if str(seg.get("reason") or "") == "card":
            continue
        length = _length(seg)
        if 0 < length < PIECE_MIN:
            found.append(
                {
                    "kind": "flash",
                    "ids": [],
                    "text": f"A piece of shot {int(seg.get('clip', 0))} is only {length:.1f}s long.",
                }
            )
    if target and target > 0:
        total = cut_seconds(lines, segments)
        if total > target * (1 + LENGTH_SLACK):
            found.append(
                {"kind": "long", "ids": [], "text": f"The cut is {total:.0f}s and {target:.0f}s was asked for."}
            )
        elif total < target * (1 - LENGTH_SLACK):
            found.append(
                {"kind": "short", "ids": [], "text": f"The cut is {total:.0f}s and {target:.0f}s was asked for."}
            )
    return found


def counts(found: list[dict]) -> dict:
    """How many of each kind, leaving out the kinds with none."""
    tally: dict[str, int] = {}
    for flag in found:
        kind = str(flag.get("kind") or "")
        tally[kind] = tally.get(kind, 0) + 1
    return {kind: tally[kind] for kind in KINDS if kind in tally}


def jumps(segments: list[dict] | None, lines: list[dict] | None = None) -> int:
    """How many joins a viewer sees as a jump: the same shot, a different moment.

    A cut inside a line, such as an "um" taken out, is counted too when it
    leaves a piece on screen for less than PIECE_MIN, because that reads as a
    stutter. A join between two shots is a change of picture, not a jump.
    """
    from botcut.frame import inside_a_line

    count = 0
    rows = [seg for seg in segments or [] if str(seg.get("reason") or "") != "card"]
    for before, after in zip(rows, rows[1:]):
        try:
            same = int(before["clip"]) == int(after["clip"])
            touching = abs(float(after["start"]) - float(before["end"])) < 0.02
        except (KeyError, TypeError, ValueError):
            continue
        if not same or touching:
            continue
        if inside_a_line(before, after, lines) and min(_length(before), _length(after)) >= PIECE_MIN:
            continue
        count += 1
    return count
