"""Read the cut back before anyone else sees it.

The first pass judges lines. This one reads the movie those choices made, top
to bottom, joins and all, and fixes what a viewer would trip on. It returns
changes to make, never a whole new list, so a line it does not mention stays
as it was. It returns ids and cut numbers. It does not return times.
"""

from __future__ import annotations

import os

from botcut import check
from botcut.broll import continuous, line_length
from botcut.llm import ask

# Fewer lines than this is a cut a person reads at a glance.
PROOF_MIN_LINES = 4
# With no length asked for, a proof that takes out more than this share of the
# kept seconds is a second cut, not a proof, and is not applied.
DROP_SHARE_MAX = 0.3
# At most this share of the kept lines can be named to be shown close.
CLOSE_SHARE_MAX = 0.25

PROOF_SYSTEM = (
    "You are the editor watching the rough cut you just made, start to finish, "
    "before anyone else sees it. Fix only what a viewer would trip on: a point made twice, "
    "a line that leans on one that was dropped, a thought cut off or left hanging, "
    "a retake that slipped through, a dropped line the story cannot do without, "
    "and a movie well over or under the length that was asked for. "
    "Most cuts need few changes, and none is a fine answer. "
    "Return drop, the ids of kept lines to take out, and restore, the ids of dropped lines "
    "to put back, each with a reason of two to four words. "
    "Return cuts only for a kept line whose cuts on offer should change: the line's id and "
    "the full list of the cut numbers to take. "
    "Return hook, the id of the one kept line the movie should open on, moved to the very "
    "front, or -1 to leave the order alone. A hook is a complete thought that makes a viewer "
    "want the rest, and the movie must still make sense when that line is gone from its place. "
    "Return close, the ids of the few kept lines that carry the point of the movie: the claim, "
    "the turn, the line a viewer should remember. They can be shown closer on the speaker. "
    "Name whole lines, never two that play one after the other, at most one line in four, "
    "and none is a fine answer. "
    "Return reply, one or two plain sentences to the person: what the movie is, and what you "
    "fixed or that it holds as cut. "
    "A line you do not mention stays as it is. Do not invent ids. Do not return times."
)

_CHANGE = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "reason"],
        "properties": {"id": {"type": "integer"}, "reason": {"type": "string"}},
    },
}

PROOF_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "proof",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["reply", "drop", "restore", "cuts", "hook", "close"],
            "properties": {
                "reply": {"type": "string"},
                "drop": _CHANGE,
                "restore": _CHANGE,
                "cuts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "take"],
                        "properties": {
                            "id": {"type": "integer"},
                            "take": {"type": "array", "items": {"type": "integer"}},
                        },
                    },
                },
                "hook": {"type": "integer"},
                "close": {"type": "array", "items": {"type": "integer"}},
            },
        },
    },
}


def no_changes() -> dict:
    return {"reply": "", "drop": [], "restore": [], "cuts": [], "hook": -1, "close": []}


def _whole(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _reason(value: object) -> str:
    return " ".join(str(value or "").split())[:48]


def _spoken(lines: list[dict]) -> list[dict]:
    return [
        line
        for line in lines or []
        if isinstance(line, dict) and str(line.get("reason") or "") != "card" and "id" in line
    ]


def _offer(line: dict) -> str:
    """The cuts on a kept line, each by number, with what it takes out and whether it is taken."""
    cuts = line.get("cuts") or []
    if not cuts:
        return ""
    words = str(line.get("text") or "").split()
    parts = []
    for number, cut in enumerate(cuts):
        try:
            said = " ".join(words[int(cut["from"]) : int(cut["through"]) + 1])
        except (KeyError, TypeError, ValueError):
            said = ""
        parts.append(f'{number}="{said}" {"taken" if cut.get("cut") else "left in"}')
    return " {cuts: " + ", ".join(parts) + "}"


def proof_message(
    lines: list[dict],
    segments: list[dict],
    *,
    intent: str = "",
    outline: dict | None = None,
    flags: list[dict] | None = None,
) -> str:
    """The cut as it plays: kept lines with their lengths, the joins, and what was dropped."""
    plan = outline or {}
    target = int(plan.get("target_seconds") or 0)
    total = check.cut_seconds(lines, segments)
    body = []
    if intent:
        body.append(f"The movie is: {intent}")
    if target > 0:
        body.append(f"The cut runs {total:.0f}s. About {target}s was asked for.")
    else:
        body.append(f"The cut runs {total:.0f}s. No length was asked for.")
    beats = plan.get("beats") or []
    if beats:
        body.append("")
        body.append("The beats of the shoot, in order:")
        body.extend(
            f"{number}. {beat['title']} (lines {beat['first']}-{beat['last']})"
            for number, beat in enumerate(beats, start=1)
        )
    hook = _whole(plan.get("hook"))
    if hook is not None and hook >= 0:
        body.append(f"On the first read, line {hook} looked like one the movie could open on.")
    body.append("")
    body.append(
        "The cut as it plays. A kept line shows its length. A cut row is a join the viewer will see. "
        "A dropped line is marked and is not in the movie."
    )
    prev = None
    for line in _spoken(lines):
        uid = int(line["id"])
        text = str(line.get("text") or "")
        if line.get("keep"):
            if prev is not None and not continuous(prev, line, segments):
                body.append("— cut —")
            body.append(f"[{uid}] {line_length(line):.1f}s {text}{_offer(line)}")
            prev = line
        else:
            body.append(f"[{uid}] dropped: {text}")
    if flags:
        body.append("")
        body.append("A plain check noticed these. Each may be fine; judge it:")
        body.extend(f"- {flag['text']}" for flag in flags)
    return "\n".join(body)


def read_proof(payload: object, lines: list[dict], target: float = 0.0) -> dict:
    """The changes that can be made. Anything that points nowhere is left out.

    A line named to drop and to restore is left alone. Drops that would empty
    the movie, or with no length asked for take out more than DROP_SHARE_MAX
    of it, are not made.
    """
    if not isinstance(payload, dict):
        raise ValueError("not a proof")
    spoken = {int(line["id"]): line for line in _spoken(lines)}

    def changes(key: str, kept: bool) -> list[dict]:
        found, seen = [], set()
        for item in payload[key]:
            uid = _whole(item.get("id"))
            line = spoken.get(uid)
            if line is None or uid in seen or bool(line.get("keep")) != kept:
                continue
            seen.add(uid)
            found.append({"id": uid, "reason": _reason(item.get("reason"))})
        return found

    drop = changes("drop", True)
    restore = changes("restore", False)
    kept_seconds = sum(line_length(line) for line in spoken.values() if line.get("keep"))
    gone = sum(line_length(spoken[item["id"]]) for item in drop)
    kept_after = sum(1 for line in spoken.values() if line.get("keep")) - len(drop) + len(restore)
    if kept_after <= 0 or (not target and kept_seconds > 0 and gone > DROP_SHARE_MAX * kept_seconds):
        drop = []
    dropped = {item["id"] for item in drop}
    cuts = []
    named = set()
    for item in payload["cuts"]:
        uid = _whole(item.get("id"))
        line = spoken.get(uid)
        if line is None or uid in named or uid in dropped or not line.get("keep"):
            continue
        offered = len(line.get("cuts") or [])
        take = sorted(
            {number for number in (_whole(value) for value in item.get("take") or []) if number is not None}
        )
        if not offered or any(number < 0 or number >= offered for number in take):
            continue
        named.add(uid)
        cuts.append({"id": uid, "take": take})
    hook = _whole(payload["hook"])
    line = spoken.get(hook)
    restored = {item["id"] for item in restore}
    stands = line is not None and hook not in dropped and (line.get("keep") or hook in restored)
    # The lines to show close are read against the cut as it will be: kept, in order,
    # never two neighbours, and no more than a share of them.
    playing = [
        uid
        for uid, row in spoken.items()
        if uid not in dropped and (row.get("keep") or uid in restored)
    ]
    place = {uid: index for index, uid in enumerate(playing)}
    limit = int(len(playing) * CLOSE_SHARE_MAX)
    close: list[int] = []
    # An answer recorded before lines could be shown close names none.
    for value in payload.get("close") or []:
        uid = _whole(value)
        if uid not in place or uid in close or len(close) >= limit:
            continue
        if any(abs(place[uid] - place[other]) == 1 for other in close):
            continue
        close.append(uid)
    reply = payload["reply"]
    return {
        "reply": " ".join(reply.split()) if isinstance(reply, str) else "",
        "drop": drop,
        "restore": restore,
        "cuts": cuts,
        "hook": hook if stands else -1,
        "close": sorted(close, key=place.get),
    }


def apply_changes(lines: list[dict], changes: dict) -> list[dict]:
    """The lines with the proof's changes made. A line it did not name is copied through."""
    drop = {item["id"]: item["reason"] for item in changes.get("drop") or []}
    restore = {item["id"]: item["reason"] for item in changes.get("restore") or []}
    take = {item["id"]: set(item["take"]) for item in changes.get("cuts") or []}
    out = []
    for line in lines:
        row = dict(line)
        try:
            uid = int(line["id"])
        except (KeyError, TypeError, ValueError):
            out.append(row)
            continue
        if str(line.get("reason") or "") == "card":
            out.append(row)
            continue
        if uid in drop:
            row["keep"] = False
            row["reason"] = drop[uid] or "dropped"
        elif uid in restore:
            row["keep"] = True
            row["reason"] = restore[uid] or "restored"
        if uid in take and row.get("cuts"):
            row["cuts"] = [
                {**cut, "cut": number in take[uid]} for number, cut in enumerate(row["cuts"])
            ]
        out.append(row)
    return out


def changed(changes: dict) -> bool:
    return bool(changes.get("drop") or changes.get("restore") or changes.get("cuts"))


def proof(
    lines: list[dict],
    segments: list[dict],
    *,
    intent: str = "",
    outline: dict | None = None,
) -> dict:
    """What to change in this cut, and a sentence to the person. One round, no more.

    The cut stands as first made when the answer cannot be had.
    """
    if os.environ.get("BOTCUT_FAKE") == "1" or len(_spoken(lines)) < PROOF_MIN_LINES:
        return no_changes()
    target = float((outline or {}).get("target_seconds") or 0)
    found = check.flags(lines, segments, target)
    try:
        return ask(
            [
                {"role": "system", "content": PROOF_SYSTEM},
                {
                    "role": "user",
                    "content": proof_message(lines, segments, intent=intent, outline=outline, flags=found),
                },
            ],
            PROOF_SCHEMA,
            what="a proof",
            parse=lambda parsed: read_proof(parsed, lines, target),
            read_timeout=300,
            tries=2,
            effort="high",
        )
    except SystemExit as stop:
        if "XAI_API_KEY" in str(stop):
            raise
        print("Kept the cut as first made", flush=True)
        return no_changes()
