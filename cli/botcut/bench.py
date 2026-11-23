"""Score the prompts against cuts the person finished by hand.

A case is a finished project: what was heard, the stills, and the line list as
it was left. Running a case asks the model to choose again from the same
words and measures how close it comes to that list. A prompt change is then
a number that moved, not a feeling.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from botcut import check, llm
from botcut.captions import load_words_by_clip
from botcut.proof import PROOF_SYSTEM, apply_changes, changed, proof
from botcut.pick import (
    CUTS_NOTE,
    DEFAULT_INTENT,
    OUTLINE_PROMPT,
    TRIM_NOTE,
    decision_lines,
    outline,
    pick,
    system_prompt,
    utterances,
)


def bench_root() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.abspath(os.path.join(base, "botcut", "bench"))


def _case_dir(name: str) -> str:
    if not name or name != os.path.basename(name) or name.startswith("."):
        raise SystemExit(f"Not a case name: {name}")
    return os.path.join(bench_root(), name)


def save(cuts_path: str, name: str) -> None:
    """Keep a finished project as a case. Nothing is transcribed again when it runs."""
    from botcut.cli import load_cuts

    if os.path.isdir(cuts_path):
        cuts_path = os.path.join(cuts_path, "cuts.json")
    elif not cuts_path.endswith(".json"):
        cuts_path = _cuts_for_movie(cuts_path)
    out_dir, doc = load_cuts(cuts_path)
    lines = doc.get("lines") or []
    if not lines:
        raise SystemExit("This cut has no lines to score against")
    case = _case_dir(name)
    if os.path.exists(case):
        raise SystemExit(f"There is already a case called {name}")
    # Fail before anything is written if what was heard is not there to copy.
    load_words_by_clip(doc, out_dir)
    work = os.path.join(out_dir, "work")
    os.makedirs(os.path.join(case, "work", "stills"))
    for entry in os.listdir(work):
        if entry.endswith((".words.json", ".silences.json")):
            shutil.copy2(os.path.join(work, entry), os.path.join(case, "work", entry))
    for line in lines:
        still = os.path.join(work, "stills", f"{int(line['id'])}.jpg")
        if os.path.isfile(still):
            shutil.copy2(still, os.path.join(case, "work", "stills"))
    Path(os.path.join(case, "cuts.json")).write_text(json.dumps(doc, indent=2) + "\n")
    kept = sum(1 for line in lines if line.get("keep"))
    print(f"Saved case {name}: {kept} of {len(lines)} lines kept", flush=True)


def _cuts_for_movie(movie: str) -> str:
    """The project a finished movie came from, so a case can be saved by naming the movie."""
    wanted = os.path.abspath(movie)
    projects = os.path.join(os.path.dirname(bench_root()), "projects")
    if os.path.isdir(projects):
        for entry in sorted(os.listdir(projects), reverse=True):
            try:
                known = json.loads(Path(os.path.join(projects, entry, "project.json")).read_text())["movie"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if os.path.abspath(str(known)) == wanted:
                return os.path.join(projects, entry, "cuts.json")
    raise SystemExit(f"No project was found for {movie}")


def case_names() -> list[str]:
    root = bench_root()
    if not os.path.isdir(root):
        return []
    return sorted(
        entry for entry in os.listdir(root) if os.path.isfile(os.path.join(root, entry, "cuts.json"))
    )


def prompt_version() -> str:
    """A short name for the wording now in use, so history rows can be told apart."""
    text = system_prompt(DEFAULT_INTENT) + CUTS_NOTE + TRIM_NOTE + OUTLINE_PROMPT + PROOF_SYSTEM
    return hashlib.sha1(text.encode()).hexdigest()[:8]


def compare(want: list[dict], got: list[dict]) -> dict:
    """How close the model's lines are to the person's, weighted by how long each line is."""
    wanted = {int(line["id"]): line for line in want}
    chosen = {int(line["id"]): line for line in got if int(line["id"]) in wanted}

    def seconds(ids) -> float:
        return sum(float(wanted[i]["end"]) - float(wanted[i]["start"]) for i in ids)

    want_keep = {i for i, line in wanted.items() if line.get("keep") and i in chosen}
    got_keep = {i for i, line in chosen.items() if line.get("keep")}
    both = want_keep & got_keep
    cuts_same = 0
    cuts_offered = 0
    for uid in both:
        mine = wanted[uid].get("cuts") or []
        theirs = chosen[uid].get("cuts") or []
        if len(mine) != len(theirs):
            continue
        cuts_offered += len(mine)
        cuts_same += sum(1 for a, b in zip(mine, theirs) if bool(a.get("cut")) == bool(b.get("cut")))
    return {
        "lines": len(chosen),
        "flipped": len(want_keep ^ got_keep),
        # Of what the model kept, how much the person kept too.
        "precision": round(seconds(both) / seconds(got_keep), 3) if got_keep else 1.0,
        # Of what the person kept, how much the model kept.
        "recall": round(seconds(both) / seconds(want_keep), 3) if want_keep else 1.0,
        "kept_seconds": round(seconds(got_keep), 1),
        "want_seconds": round(seconds(want_keep), 1),
        "cuts_same": cuts_same,
        "cuts_offered": cuts_offered,
    }


def score(name: str, replay: bool = False) -> dict:
    case = _case_dir(name)
    try:
        doc = json.loads(Path(os.path.join(case, "cuts.json")).read_text())
    except (OSError, ValueError):
        raise SystemExit(f"No case called {name}")
    utts = utterances(load_words_by_clip(doc, case))
    for utt in utts:
        still = os.path.join(case, "work", "stills", f"{int(utt['id'])}.jpg")
        if os.path.isfile(still):
            utt["still"] = still
    llm.reset_usage()
    llm.use_tape(llm.Tape(os.path.join(case, "replies"), replay=replay))
    began = time.monotonic()
    try:
        # The same passes a cut makes: read the shoot, choose the lines, read the cut back.
        intent = str(doc.get("intent") or "")
        plan = outline(utts, intent)
        got = decision_lines(utts, pick(utts, intent, plan))
        changes = proof(got, _pieces(doc, case, got), intent=intent, outline=plan)
        if changed(changes):
            got = apply_changes(got, changes)
    finally:
        llm.use_tape(None)
    result = compare(doc.get("lines") or [], got)
    # What a viewer would notice in the model's cut, and in the person's for scale.
    pieces = _pieces(doc, case, got)
    want_pieces = _pieces(doc, case, doc.get("lines") or [])
    result["flags"] = check.counts(check.flags(got, pieces))
    result["want_flags"] = check.counts(check.flags(doc.get("lines") or [], want_pieces))
    # Joins that show as a jump when nothing hides them: no second camera, no zoom.
    result["jumps"] = check.jumps(pieces, got)
    result["want_jumps"] = check.jumps(want_pieces, doc.get("lines") or [])
    tally = llm.usage()
    result["seconds"] = round(time.monotonic() - began, 1)
    result["tokens"] = tally["input"] + tally["output"]
    if "usd" in tally:
        result["usd"] = tally["usd"]
    return result


def _pieces(doc: dict, case: str, lines: list[dict]) -> list[dict]:
    """The ranges these lines would render as, with the case's pace and silences."""
    from botcut.cli import _load_silences, _segments_for_lines

    clips = doc.get("clips") or []
    tighten = doc.get("tighten") or {}
    try:
        return _segments_for_lines(
            [line for line in lines if str(line.get("reason") or "") != "card"],
            [float(clip.get("duration") or 0) for clip in clips],
            _load_silences(case, clips),
            bool(tighten.get("snap", True)),
            float(tighten.get("max_pause", 0.8)),
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return []


def _flag_words(tally: dict) -> str:
    return ", ".join(f"{kind} {count}" for kind, count in tally.items()) or "none"


def _row(name: str, result: dict) -> str:
    cuts = f"{result['cuts_same']}/{result['cuts_offered']}" if result["cuts_offered"] else "-"
    row = (
        f"{name}: precision {result['precision']:.2f}, recall {result['recall']:.2f}, "
        f"flipped {result['flipped']} of {result['lines']}, cuts {cuts}, "
        f"{result['tokens']:,} tokens, {result['seconds']}s"
    )
    if "jumps" in result:
        row += f", jumps {result['jumps']} (yours {result.get('want_jumps', 0)})"
    if result.get("flags") or result.get("want_flags"):
        row += f", flags {_flag_words(result.get('flags') or {})}"
        row += f" (yours {_flag_words(result.get('want_flags') or {})})"
    if "usd" in result:
        row += f", ${result['usd']:.2f}"
    return row


def run(names: list[str], replay: bool = False) -> dict:
    """Score the named cases, or all of them, print a row each, and add the run to the history."""
    chosen = names or case_names()
    if not chosen:
        raise SystemExit("No cases yet. Save one with: botcut-cli bench save CUTS NAME")
    results = {}
    for name in chosen:
        results[name] = score(name, replay=replay)
        print(_row(name, results[name]), flush=True)
    kept = sum(r["kept_seconds"] for r in results.values())
    want = sum(r["want_seconds"] for r in results.values())
    shared_p = sum(r["precision"] * r["kept_seconds"] for r in results.values())
    shared_r = sum(r["recall"] * r["want_seconds"] for r in results.values())
    overall = {
        "precision": round(shared_p / kept, 3) if kept else 1.0,
        "recall": round(shared_r / want, 3) if want else 1.0,
        "flipped": sum(r["flipped"] for r in results.values()),
        "lines": sum(r["lines"] for r in results.values()),
        "tokens": sum(r["tokens"] for r in results.values()),
        "flags": sum(sum((r.get("flags") or {}).values()) for r in results.values()),
    }
    entry = {
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": llm.model_name(),
        "prompt": prompt_version(),
        "replay": replay,
        "cases": results,
        "overall": overall,
    }
    history = os.path.join(bench_root(), "history.jsonl")
    before = _last_overall(history, set(results))
    os.makedirs(bench_root(), exist_ok=True)
    with open(history, "a") as handle:
        handle.write(json.dumps(entry) + "\n")
    line = (
        f"Overall: precision {overall['precision']:.2f}, recall {overall['recall']:.2f}, "
        f"flipped {overall['flipped']} of {overall['lines']}, {overall['flags']} flags"
    )
    if before is not None:
        line += (
            f" (was {before['precision']:.2f}, {before['recall']:.2f}, "
            f"{before['flipped']}, {before.get('flags', 0)} flags with prompt {before['prompt']})"
        )
    print(line, flush=True)
    return entry


def _last_overall(history: str, cases: set[str]) -> dict | None:
    """The last run over the same cases, to say what changed."""
    try:
        rows = Path(history).read_text().splitlines()
    except OSError:
        return None
    for raw in reversed(rows):
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if set(entry.get("cases") or {}) == cases:
            return {**entry["overall"], "prompt": entry.get("prompt", "?")}
    return None
