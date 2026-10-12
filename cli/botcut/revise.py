"""Revise a decided cut from a note.

The model returns a sentence, a pace, dip on or off, keep ids, and a delivery.
It does not return times. The file's max_pause stays put until the next Cut or Render.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from botcut.net import post
from botcut.pick import chat_fields, llm_url

# The offscreen revise test expects this sentence.
FAKE_INTENT = "A frenzied cut."

PACES = ("open", "measured", "tight", "frenzied")
DELIVERS = ("none", "render", "captions", "short")
_FIELDS = {"intent", "pace", "dip", "keep", "deliver"}
_KEEP_FIELDS = {"id", "reason"}

REVISE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "revise",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["intent", "pace", "dip", "keep", "deliver"],
            "properties": {
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
            },
        },
    },
}

REVISE_SYSTEM = (
    "Revise one rough cut from the user's note. "
    "Return the movie sentence, the pace, whether to dip to black, "
    "the utterance ids to keep and a short reason for each, and how to deliver. "
    "Pace is open, measured, tight, or frenzied. "
    "Deliver is none, render, captions, or short. "
    "Deliver never changes the picture. "
    "none only means not to mark render, captions, or short. "
    "Do not return times, padding, or any join other than dip on or off. "
    "A listed id is kept. An id you leave out is dropped. Do not invent ids."
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
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise SystemExit("LLM response was not a revise")
    intent = payload["intent"]
    pace = payload["pace"]
    dip = payload["dip"]
    keep = payload["keep"]
    deliver = payload["deliver"]
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
        "intent": intent.strip(),
        "pace": pace,
        "dip": dip,
        "keep": parsed_keep,
        "deliver": deliver,
    }


def revise(cuts_path: str, note: str, *, pace: str = "open", dip: bool = True) -> None:
    text = " ".join(note.split())
    if not text:
        raise SystemExit("Say what to change")
    if pace not in PACES:
        raise SystemExit(f"Unknown pace: {pace}")
    from botcut.cli import load_cuts

    _out_dir, doc = load_cuts(cuts_path)
    lines = doc.get("lines") or []
    if not lines:
        raise SystemExit("No lines to revise")
    print("Revising", flush=True)
    result = _plan(lines, text, str(doc.get("intent") or ""), pace, bool(dip))
    new_lines = apply_revise(lines, result["keep"])
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


def _plan(lines: list[dict], note: str, intent: str, pace: str, dip: bool) -> dict:
    if os.environ.get("BOTCUT_FAKE") == "1":
        return parse_revise(_fake(lines))
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")
    body = {
        **chat_fields(),
        "messages": [
            {"role": "system", "content": REVISE_SYSTEM},
            {"role": "user", "content": _user_message(lines, note, intent, pace, dip)},
        ],
        "response_format": REVISE_SCHEMA,
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
        return parse_revise(json.loads(response.json()["choices"][0]["message"]["content"]))
    except (ValueError, KeyError, TypeError, IndexError):
        raise SystemExit("LLM response was not a revise")


def _fake(lines: list[dict]) -> dict:
    # Drop the last id so an offline test with two lines sees one go.
    ids = []
    for line in lines:
        try:
            ids.append(int(line["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    keep = [{"id": uid, "reason": "fake"} for uid in ids[:-1]]
    keep.append({"id": 10**9, "reason": "unknown"})
    return {
        "intent": FAKE_INTENT,
        "pace": "frenzied",
        "dip": False,
        "keep": keep,
        "deliver": "render",
    }


def _user_message(lines: list[dict], note: str, intent: str, pace: str, dip: bool) -> str:
    body = [
        f"The movie is: {intent}",
        f"Pace: {pace}",
        f"Dip to black: {'on' if dip else 'off'}",
        "",
    ]
    for line in lines:
        try:
            uid = int(line["id"])
        except (KeyError, TypeError, ValueError):
            continue
        state = "keep" if line.get("keep") else "drop"
        body.append(f"[{uid}] {state} ({line.get('reason') or ''}) {line.get('text') or ''}")
    body.append("")
    body.append(f"Note: {note}")
    return "\n".join(body)
