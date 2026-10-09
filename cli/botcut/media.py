"""Probe shots, extract speech audio, and build the rough-cut ffmpeg command."""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import threading


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
        codec = None
        pix_fmt = None
    else:
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
        fps = _parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")
        codec = video.get("codec_name")
        pix_fmt = video.get("pix_fmt")
    return {
        "path": os.path.abspath(path),
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "rotate": _rotation(video) if video is not None else 0,
        "codec": codec,
        "pix_fmt": pix_fmt,
        "audio_codec": audio.get("codec_name"),
        "sample_rate": int(audio.get("sample_rate") or 0),
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


def render_percent(out_time_us: int, kept_s: float) -> int:
    if kept_s <= 0 or out_time_us <= 0:
        return 0
    return min(100, round((out_time_us / 1_000_000) / kept_s * 100))


def render_with_progress(
    segments: list[dict],
    clips: list[dict],
    dst: str,
    label: str,
    fail_prefix: str,
    polish: bool = False,
    scene_transition: str = "dip",
) -> None:
    """Encode segments and print '<label> N%' as ffmpeg advances.

    Progress stays on stdout. ffmpeg's own log stays off that stream so a UI
    can show the percentage without the filter graph.
    """
    kept_s = sum(float(seg["end"]) - float(seg["start"]) for seg in segments)
    encoder, device = resolve_encoder()
    # args[0] is the leading -y. The progress flags replace it so one ffmpeg
    # process still reports Rendering N% / Opening N%.
    args = render_args(
        segments,
        clips,
        dst,
        encoder=encoder,
        device=device,
        polish=polish,
        scene_transition=scene_transition,
    )
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *args[1:]]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    err_parts: list[str] = []

    def drain() -> None:
        if proc.stderr is not None:
            err_parts.append(proc.stderr.read())

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    print(f"{label} 0%", flush=True)
    last = 0
    try:
        if proc.stdout is None:
            raise SystemExit(f"{fail_prefix}: ffmpeg failed")
        for raw in proc.stdout:
            line = raw.strip()
            if not line.startswith("out_time_us="):
                continue
            value = line.split("=", 1)[1]
            if not value.lstrip("-").isdigit():
                continue
            percent = render_percent(int(value), kept_s)
            if percent == last:
                continue
            last = percent
            print(f"{label} {percent}%", flush=True)
    finally:
        code = proc.wait()
        thread.join()
    if code != 0:
        detail = (err_parts[0] if err_parts else "").strip()[-500:] or "ffmpeg failed"
        raise SystemExit(f"{fail_prefix}: {detail}")


def resolve_encoder() -> tuple[str, str | None]:
    """Pick libx264 or the first VA-API render node that opens.

    BOTCUT_ENCODER=x264 forces the CPU encode. BOTCUT_ENCODER=vaapi fails
    when no device opens. Unset tries the Arc and falls back to libx264.
    """
    raw = os.environ.get("BOTCUT_ENCODER", "").strip().lower()
    if raw in ("", "auto"):
        device = vaapi_device()
        if device:
            return ("vaapi", device)
        return ("x264", None)
    if raw == "x264":
        return ("x264", None)
    if raw == "vaapi":
        device = vaapi_device()
        if not device:
            raise SystemExit("BOTCUT_ENCODER=vaapi but no VA-API device opened")
        return ("vaapi", device)
    raise SystemExit(f"BOTCUT_ENCODER must be x264 or vaapi, not {raw}")


def vaapi_device() -> str | None:
    cached = getattr(vaapi_device, "cached", None)
    if cached is not None:
        return cached[0]
    found = _open_vaapi_device()
    vaapi_device.cached = (found,)
    return found


# Picture bookends, and the dip on each side of a file change. Audio at a
# file change is longer than the click-guard used inside one file.
OPEN_FADE = 0.50
CLOSE_FADE = 0.80
DIP_FADE = 0.18
SCENE_AUDIO = 0.12
JOIN_AUDIO = 0.02


def _transition(value: str) -> str:
    return value if value in ("dip", "off") else "dip"


def _fit_pair(duration: float, fade_in: float, fade_out: float) -> tuple[float, float]:
    if duration <= 0 or (fade_in <= 0 and fade_out <= 0):
        return 0.0, 0.0
    budget = duration * 0.9
    need = fade_in + fade_out
    if need > budget:
        scale = budget / need
        fade_in *= scale
        fade_out *= scale
    fade_in = round(fade_in, 3)
    fade_out = round(fade_out, 3)
    if fade_in + fade_out > duration and fade_out > 0:
        fade_out = round(max(0.0, duration - fade_in), 3)
    return fade_in, fade_out


def _picture_edges(index: int, segments: list[dict], scene_transition: str) -> tuple[float, float]:
    last = len(segments) - 1
    fade_in = OPEN_FADE if index == 0 else 0.0
    fade_out = CLOSE_FADE if index == last else 0.0
    if scene_transition != "dip":
        return fade_in, fade_out
    clip = int(segments[index]["clip"])
    if index > 0 and clip != int(segments[index - 1]["clip"]):
        fade_in = DIP_FADE
    if index < last and clip != int(segments[index + 1]["clip"]):
        fade_out = DIP_FADE
    return fade_in, fade_out


def _audio_edges(
    index: int, segments: list[dict], duration: float, scene_transition: str
) -> tuple[float, float]:
    if duration <= 0:
        return 0.001, 0.001
    if duration < 0.08:
        short = max(0.001, duration / 4)
        return _fit_pair(duration, short, short)
    last = len(segments) - 1
    fade_in = JOIN_AUDIO
    fade_out = JOIN_AUDIO
    if scene_transition == "dip":
        clip = int(segments[index]["clip"])
        if index > 0 and clip != int(segments[index - 1]["clip"]):
            fade_in = SCENE_AUDIO
        if index < last and clip != int(segments[index + 1]["clip"]):
            fade_out = SCENE_AUDIO
    return _fit_pair(duration, fade_in, fade_out)


def _picture_suffix(duration: float, fade_in: float, fade_out: float) -> str:
    fade_in, fade_out = _fit_pair(duration, fade_in, fade_out)
    parts: list[str] = []
    if fade_in > 0:
        parts.append(f"fade=t=in:st=0:d={fade_in:.3f}:color=black")
    if fade_out > 0:
        start = max(0.0, round(duration - fade_out, 3))
        parts.append(f"fade=t=out:st={start:.3f}:d={fade_out:.3f}:color=black")
    return ("," + ",".join(parts)) if parts else ""


def _audio_chain(
    index: int, seg: dict, polish: bool, segments: list[dict], scene_transition: str
) -> str:
    if not polish:
        return f"[{index}:a]aresample=48000[a{index}]"
    duration = max(0.0, float(seg["end"]) - float(seg["start"]))
    fade_in, fade_out = _audio_edges(index, segments, duration, scene_transition)
    fade_at = max(0.0, round(duration - fade_out, 3))
    return (
        f"[{index}:a]aresample=48000,loudnorm=I=-16:TP=-1.5:LRA=11,"
        f"afade=t=in:st=0:d={fade_in:.3f},afade=t=out:st={fade_at:.3f}:d={fade_out:.3f}[a{index}]"
    )


def render_args(
    segments: list[dict],
    clips: list[dict],
    dst: str,
    encoder: str = "x264",
    device: str | None = None,
    polish: bool = False,
    scene_transition: str = "dip",
) -> list[str]:
    if not segments:
        raise SystemExit("No segments to render")
    if encoder not in ("x264", "vaapi"):
        raise SystemExit(f"Unknown encoder {encoder}")
    if encoder == "vaapi" and not device:
        raise SystemExit("VA-API encode needs a device")
    ref = clips[0]
    width, height, fps = int(ref["width"]), int(ref["height"]), float(ref["fps"])
    if width <= 0 or height <= 0 or fps <= 0:
        raise SystemExit(f"Clip has no video to render: {ref['path']}")
    args = ["-y"]
    if encoder == "vaapi":
        args += ["-init_hw_device", f"vaapi=va:{device}", "-filter_hw_device", "va"]
    fps_s = _fps(fps)
    transition = _transition(scene_transition)
    filters = []
    for i, seg in enumerate(segments):
        clip = clips[seg["clip"]]
        duration = max(0.0, float(seg["end"]) - float(seg["start"]))
        picture = ""
        if polish:
            fade_in, fade_out = _picture_edges(i, segments, transition)
            picture = _picture_suffix(duration, fade_in, fade_out)
        on_gpu = encoder == "vaapi" and not _rotated(clip) and _vaapi_decodable(clip)
        if on_gpu:
            args += [
                "-hwaccel",
                "vaapi",
                "-hwaccel_device",
                str(device),
                "-hwaccel_output_format",
                "vaapi",
            ]
        args += [
            "-ss",
            _num(seg["start"]),
            "-t",
            _num(seg["end"] - seg["start"]),
            "-i",
            clip["path"],
        ]
        if not on_gpu:
            filters.append(
                f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps_s}"
                + picture
                + (",format=nv12,hwupload" if encoder == "vaapi" else "")
                + f"[v{i}]"
            )
        else:
            # scale_vaapi keeps the 4K resize on the Arc. This GPU drops the
            # surface when more than one VA-API input stays on the device
            # through concat, so each branch downloads, pads, and uploads
            # again for h264_vaapi. The dip runs on those software frames.
            chain = (
                f"[{i}:v]scale_vaapi={width}:{height}:format=nv12:force_original_aspect_ratio=decrease,"
                f"hwdownload,format=nv12,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
            )
            if not _same_rate(clip, fps):
                chain += f",fps={fps_s}"
            filters.append(chain + picture + f",format=nv12,hwupload[v{i}]")
        filters.append(_audio_chain(i, seg, polish, segments, transition))
    concat_in = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
    filters.append(f"{concat_in}concat=n={len(segments)}:v=1:a=1[v][a]")
    args += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-map",
        "[a]",
    ]
    if encoder == "vaapi":
        args += ["-c:v", "h264_vaapi", "-qp", "20"]
    else:
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
    args += ["-c:a", "aac", "-movflags", "+faststart", dst]
    return args


def _open_vaapi_device() -> str | None:
    for node in sorted(glob.glob("/dev/dri/renderD*")):
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-init_hw_device",
                f"vaapi=va:{node}",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=16x16:d=0.1",
                "-frames:v",
                "1",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return node
    return None


def _rotation(video: dict) -> int:
    tags = video.get("tags") or {}
    raw = tags.get("rotate")
    degrees = _degrees(raw)
    for item in video.get("side_data_list") or []:
        if isinstance(item, dict) and "rotation" in item:
            degrees = _degrees(item.get("rotation"))
    return degrees


def _degrees(raw: object) -> int:
    if raw in (None, ""):
        return 0
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return 0


def _rotated(clip: dict) -> bool:
    return _degrees(clip.get("rotate")) % 360 != 0


# 4:2:0 formats the Arc VA-API decoder accepts. yuv444p (ffmpeg's default for
# an unpinned test pattern) stays on the CPU decoder.
_VAAPI_PIX = {"yuv420p", "yuvj420p", "nv12", "yuv420p10le", "p010le"}


def _vaapi_decodable(clip: dict) -> bool:
    pix = clip.get("pix_fmt")
    if not pix:
        return True
    return str(pix) in _VAAPI_PIX


def _same_rate(clip: dict, ref: float) -> bool:
    try:
        rate = float(clip.get("fps") if clip.get("fps") not in (None, "") else ref)
    except (TypeError, ValueError):
        return True
    return abs(rate - ref) < 0.01


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
