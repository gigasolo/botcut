"""botcut-cli run: transcribe, pick takes, write cuts.json, render a rough cut."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from botcut.media import extract_audio, probe, render_args, silences
from botcut.pick import (
    dropped_utterances,
    kept_utterances,
    model_name,
    pick,
    segments,
    snap,
    tighten,
    unique_warnings,
    unknown_warnings,
    utterances,
)
from botcut.stt import transcribe_fake, transcribe_local, transcribe_xai


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="botcut-cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="transcribe shots and render a rough cut")
    run_p.add_argument("files", nargs="+", help="shot files in order, or one .txt list")
    run_p.add_argument("--out", required=True, help="directory for cuts.json and rough_cut.mp4")
    run_p.add_argument("--stt", choices=("xai", "local"), default="xai")
    run_p.add_argument("--whisper-model", default="large-v3-turbo")
    run_p.add_argument("--max-pause", type=float, default=0.8)
    run_p.add_argument("--no-snap", action="store_true")
    args = parser.parse_args(argv)
    try:
        run(
            args.files,
            args.out,
            stt=args.stt,
            whisper_model=args.whisper_model,
            max_pause=args.max_pause,
            snap_edges=not args.no_snap,
        )
    except BrokenPipeError:
        sys.exit(0)


def run(
    files: list[str],
    out: str,
    stt: str = "xai",
    whisper_model: str = "large-v3-turbo",
    max_pause: float = 0.8,
    snap_edges: bool = True,
) -> None:
    paths = resolve_inputs(files)
    clips = []
    for path in paths:
        if not os.path.isfile(path):
            raise SystemExit(f"No such file: {path}")
        clips.append(probe(path))

    fake = os.environ.get("BOTCUT_FAKE") == "1"
    backend = "local" if stt == "local" else "xai"
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)
    words_by_clip = []
    silences_by_clip = []
    for index, clip in enumerate(clips):
        stem = Path(clip["path"]).stem
        if fake:
            words_by_clip.append(transcribe_fake()["words"])
            silences_by_clip.append([])
            continue
        flac = os.path.join(work, f"{index}-{stem}.flac")
        words_by_clip.append(_words_for_clip(work, index, stem, backend, flac, clip, whisper_model))
        silences_by_clip.append(_silences_for_clip(work, index, stem, flac, clip))

    utts = utterances(words_by_clip)
    chosen = pick(utts)
    segs, unknown = segments(utts, chosen, [clip["duration"] for clip in clips])
    if snap_edges:
        segs = snap(segs, silences_by_clip)
    segs = tighten(segs, silences_by_clip, max_pause)
    for line in unknown_warnings(unknown):
        print(line)
    dropped = dropped_utterances(utts, chosen)
    # BOTCUT_FAKE keeps every id, so this prints nothing in the offline tests.
    for line in unique_warnings(dropped, kept_utterances(utts, chosen)):
        print(line)

    doc = {
        "version": 1,
        "stt": _stt_label(fake, stt, whisper_model),
        "model": "fake" if fake else model_name(),
        "tighten": {"max_pause": max_pause, "snap": snap_edges},
        "clips": [
            {"index": i, "path": clip["path"], "duration": clip["duration"]}
            for i, clip in enumerate(clips)
        ],
        "segments": segs,
        "dropped": [
            {
                "id": utt["id"],
                "clip": utt["clip"],
                "start": utt["start"],
                "end": utt["end"],
                "text": utt["text"],
            }
            for utt in dropped
        ],
    }
    os.makedirs(out, exist_ok=True)
    cuts_path = os.path.join(out, "cuts.json")
    Path(cuts_path).write_text(json.dumps(doc, indent=2) + "\n")
    print(f"Wrote {os.path.abspath(cuts_path)}")
    if not segs:
        raise SystemExit("No segments to render")
    dst = os.path.join(out, "rough_cut.mp4")
    proc = subprocess.run(
        ["ffmpeg", *render_args(segs, clips, dst)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-500:] or "ffmpeg failed"
        raise SystemExit(f"Render failed: {detail}")
    kept_s = sum(seg["end"] - seg["start"] for seg in segs)
    total_s = sum(clip["duration"] for clip in clips)
    print(f"Wrote {os.path.abspath(dst)} ({kept_s:.1f}s of {total_s:.1f}s)")


def word_cache_candidates(work: str, index: int, stem: str, backend: str) -> list[str]:
    names = [f"{index}-{stem}.{backend}.words.json"]
    if backend == "xai":
        names.append(f"{index}-{stem}.words.json")
    return [os.path.join(work, name) for name in names]


def _words_for_clip(
    work: str, index: int, stem: str, backend: str, flac: str, clip: dict, whisper_model: str
) -> list:
    for cache in word_cache_candidates(work, index, stem, backend):
        if os.path.isfile(cache):
            print(f"cache hit {cache}")
            return json.loads(Path(cache).read_text())["words"]
    if not os.path.isfile(flac):
        extract_audio(clip["path"], flac)
    if backend == "local":
        result = transcribe_local(flac, whisper_model, stem)
    else:
        result = transcribe_xai(flac)
    cache = word_cache_candidates(work, index, stem, backend)[0]
    Path(cache).write_text(json.dumps(result) + "\n")
    return result["words"]


def _silences_for_clip(work: str, index: int, stem: str, flac: str, clip: dict) -> list:
    cache = os.path.join(work, f"{index}-{stem}.silences.json")
    if os.path.isfile(cache):
        return [tuple(pair) for pair in json.loads(Path(cache).read_text())]
    if not os.path.isfile(flac):
        extract_audio(clip["path"], flac)
    pairs = silences(flac, clip["duration"])
    Path(cache).write_text(json.dumps(pairs) + "\n")
    return pairs


def _stt_label(fake: bool, stt: str, whisper_model: str) -> str:
    if fake:
        return "fake"
    if stt == "local":
        return f"local:faster-whisper:{whisper_model}"
    return "xai:grok-voice-transcribe-2.0"


def resolve_inputs(files: list[str]) -> list[str]:
    if len(files) == 1 and files[0].lower().endswith(".txt"):
        path = files[0]
        if not os.path.isfile(path):
            raise SystemExit(f"No such file: {path}")
        paths = []
        for line in Path(path).read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            paths.append(stripped)
        if not paths:
            raise SystemExit(f"No paths in {path}")
        return paths
    return list(files)
