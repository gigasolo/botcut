"""Probe shots, extract speech audio, and build the rough-cut ffmpeg command."""

from __future__ import annotations

import json
import os
import re
import subprocess


def probe(path: str) -> dict:
    if not os.path.isfile(path):
        raise SystemExit(f"No such file: {path}")
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "ffprobe failed"
        raise SystemExit(f"Cannot probe {path}: {detail}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise SystemExit(f"No audio stream: {path}")
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    duration = float((data.get("format") or {}).get("duration") or audio.get("duration") or 0)
    if video is None:
        width, height, fps = 0, 0, 0.0
    else:
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
        fps = _parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")
    return {
        "path": os.path.abspath(path),
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
    }


def parse_silences(stderr: str, duration: float) -> list[tuple[float, float]]:
    pairs = []
    pending = None
    for line in stderr.splitlines():
        start = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start:
            pending = float(start.group(1))
            continue
        end = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end and pending is not None:
            pairs.append((pending, float(end.group(1))))
            pending = None
    if pending is not None and duration > pending:
        pairs.append((pending, duration))
    return pairs


def silences(flac: str, duration: float) -> list[tuple[float, float]]:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            flac,
            "-af",
            "silencedetect=noise=-35dB:d=0.3",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    return parse_silences(proc.stderr or "", duration)


def extract_audio(path: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac", dst],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-400:] or "ffmpeg failed"
        raise SystemExit(f"Audio extract failed for {path}: {detail}")


def render_args(segments: list[dict], clips: list[dict], dst: str) -> list[str]:
    if not segments:
        raise SystemExit("No segments to render")
    ref = clips[0]
    width, height, fps = int(ref["width"]), int(ref["height"]), float(ref["fps"])
    if width <= 0 or height <= 0 or fps <= 0:
        raise SystemExit(f"Clip has no video to render: {ref['path']}")
    args = ["-y"]
    for seg in segments:
        clip = clips[seg["clip"]]
        args += [
            "-ss",
            _num(seg["start"]),
            "-t",
            _num(seg["end"] - seg["start"]),
            "-i",
            clip["path"],
        ]
    fps_s = _fps(fps)
    filters = []
    for i in range(len(segments)):
        filters.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps_s}[v{i}]"
        )
        filters.append(f"[{i}:a]aresample=48000[a{i}]")
    concat_in = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
    filters.append(f"{concat_in}concat=n={len(segments)}:v=1:a=1[v][a]")
    args += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        dst,
    ]
    return args


def _parse_rate(rate: str) -> float:
    if "/" in str(rate):
        num, den = str(rate).split("/", 1)
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    return float(rate)


def _num(value: float) -> str:
    return f"{value:.3f}"


def _fps(fps: float) -> str:
    if abs(fps - round(fps)) < 1e-3:
        return str(int(round(fps)))
    return f"{fps:.3f}".rstrip("0").rstrip(".")
