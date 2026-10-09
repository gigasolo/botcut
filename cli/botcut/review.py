"""Build one master file and a keep-list the BotCut app can open."""

from __future__ import annotations

import os
import shutil
import subprocess

from botcut.media import probe, render_with_progress

FPS_TOLERANCE = 0.01


def offsets(clips: list[dict]) -> list[float]:
    found = []
    cursor = 0.0
    for clip in clips:
        found.append(cursor)
        cursor += float(clip["duration"])
    return found


def compatible(clips: list[dict]) -> bool:
    if not clips:
        return False
    first = clips[0]
    if not first.get("codec") or int(first.get("width") or 0) <= 0 or int(first.get("height") or 0) <= 0:
        return False
    if float(first.get("fps") or 0) <= 0 or not first.get("audio_codec") or int(first.get("sample_rate") or 0) <= 0:
        return False
    for clip in clips[1:]:
        if clip.get("codec") != first.get("codec"):
            return False
        if int(clip.get("width") or 0) != int(first["width"]) or int(clip.get("height") or 0) != int(first["height"]):
            return False
        if abs(float(clip.get("fps") or 0) - float(first["fps"])) > FPS_TOLERANCE:
            return False
        if clip.get("audio_codec") != first.get("audio_codec"):
            return False
        if int(clip.get("sample_rate") or 0) != int(first["sample_rate"]):
            return False
    return True


def drifted(master_duration: float, expected: float, n_clips: int) -> bool:
    return abs(master_duration - expected) > 0.1 * n_clips


def source_clips(doc: dict) -> list[dict]:
    rows = sorted(doc.get("clips") or [], key=lambda clip: int(clip["index"]))
    if not rows:
        raise SystemExit("cuts.json has no clips")
    return [probe(row["path"]) for row in rows]


def keep_list(doc: dict, offs: list[float]) -> dict:
    items = []
    for seg in doc.get("segments") or []:
        clip = int(seg["clip"])
        if clip < 0 or clip >= len(offs):
            raise SystemExit(f"Segment clip {clip} is outside the master")
        item = {
            "start": offs[clip] + float(seg["start"]),
            "end": offs[clip] + float(seg["end"]),
        }
        if seg.get("reason"):
            item["label"] = str(seg["reason"])
        items.append(item)
    items.sort(key=lambda item: (item["start"], item["end"]))
    return {"source": "master.mp4", "keep": items}


def build_master(clips: list[dict], out_dir: str, rebuild: bool) -> str:
    if not clips:
        raise SystemExit("cuts.json has no clips")
    os.makedirs(out_dir, exist_ok=True)
    master_path = os.path.join(out_dir, "master.mp4")
    if (
        not rebuild
        and os.path.isfile(master_path)
        and _newer_than_sources(master_path, clips)
    ):
        print("master up to date")
        return master_path
    if compatible(clips):
        _stream_copy(clips, out_dir, master_path)
        master_s = probe(master_path)["duration"]
        expected = sum(float(clip["duration"]) for clip in clips)
        drift = abs(master_s - expected)
        if drifted(master_s, expected, len(clips)):
            print(f"master drift {drift:.1f}s; re-encoding")
            _render_normalized(clips, master_path)
    else:
        _render_normalized(clips, master_path)
    return master_path


def launch(keep_path: str) -> None:
    exe = shutil.which("botcut")
    if not exe:
        print(f"BotCut app not found; run ./bin/install, then: botcut {keep_path}")
        return
    subprocess.Popen(
        [exe, keep_path],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def concat_line(path: str) -> str:
    escaped = os.path.abspath(path).replace("'", r"'\''")
    return f"file '{escaped}'"


def _newer_than_sources(master_path: str, clips: list[dict]) -> bool:
    master_mtime = os.path.getmtime(master_path)
    return all(os.path.isfile(clip["path"]) and master_mtime >= os.path.getmtime(clip["path"]) for clip in clips)


def _stream_copy(clips: list[dict], out_dir: str, master_path: str) -> None:
    work = os.path.join(out_dir, "work")
    os.makedirs(work, exist_ok=True)
    listing = os.path.join(work, "concat.txt")
    with open(listing, "w", encoding="utf-8") as handle:
        for clip in clips:
            handle.write(concat_line(clip["path"]) + "\n")
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            listing,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            master_path,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-500:] or "ffmpeg failed"
        raise SystemExit(f"Master copy failed: {detail}")


def _render_normalized(clips: list[dict], master_path: str) -> None:
    segments = [
        {"clip": i, "start": 0.0, "end": float(clip["duration"]), "reason": "master"}
        for i, clip in enumerate(clips)
    ]
    render_with_progress(segments, clips, master_path, "Opening", "Master render failed")
