"""Probe shots, extract speech audio, and build the rough-cut ffmpeg command."""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import threading

from botcut.card import is_card


def grab_still(video: str, at: float, dest: str) -> bool:
    """One software-decoded JPEG from the middle of a line. A failure leaves the cut running."""
    if not os.path.isfile(video):
        return False
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    when = max(0.0, at)
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{when:.3f}",
                "-i",
                video,
                "-frames:v",
                "1",
                "-vf",
                "scale=320:-2",
                "-q:v",
                "5",
                dest,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0


def probe(path: str, need_audio: bool = True) -> dict:
    """Read one file. A spoken shot needs a sound track. B-roll may be silent."""
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
    if audio is None and need_audio:
        raise SystemExit(f"No audio stream: {path}")
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    fallback = (audio or video or {}).get("duration") or 0
    duration = float((data.get("format") or {}).get("duration") or fallback)
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
        # "pc" is full range, as a Hover or a phone JPEG-style stream writes it.
        "color_range": (video.get("color_range") if video is not None else None) or None,
        "audio": audio is not None,
        "audio_codec": audio.get("codec_name") if audio is not None else None,
        "sample_rate": int(audio.get("sample_rate") or 0) if audio is not None else 0,
    }


def parse_scene_changes(stderr: str) -> list[float]:
    """Frame times from showinfo lines, one per scene change."""
    found = []
    for line in stderr.splitlines():
        if "showinfo" not in line:
            continue
        match = re.search(r"pts_time:\s*(-?[0-9.]+)", line)
        if not match:
            continue
        try:
            found.append(float(match.group(1)))
        except ValueError:
            continue
    return found


def scene_changes(path: str, threshold: float = 0.3) -> list[float]:
    """Where the picture of a B-roll file changes. Sampled at 5 fps and small, so the compare is cheap."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            path,
            "-an",
            "-vf",
            f"fps=5,scale=160:-2,select='gt(scene,{threshold})',showinfo",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    # A failed read must not pass for a file with no cuts in it.
    if proc.returncode != 0:
        raise SystemExit(f"Could not read {os.path.basename(path)}: {ffmpeg_error_detail(proc.stderr or '')}")
    return parse_scene_changes(proc.stderr or "")


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


# The level under which a stretch counts as a pause, for a quiet room. A shot with
# more going on behind the voice gets a higher one, worked out from its own sound.
SILENCE_DB = -35.0
SILENCE_OVER_FLOOR = 8.0
SILENCE_UNDER_VOICE = 12.0
SILENCE_DB_MAX = -18.0


def sound_levels(flac: str) -> tuple[float, float] | None:
    """How loud the room and the voice are in a recording, in dB below full scale.

    The sound is read in 50 ms steps. The quiet end of them is the room and
    the loud end is the voice. None when it cannot be read or is all silence.
    """
    import numpy as np

    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", flac, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return levels_of(np.frombuffer(proc.stdout, dtype=np.int16))


def levels_of(samples, rate: int = 16000) -> tuple[float, float] | None:
    import numpy as np

    step = rate // 20
    count = len(samples) // step
    if count < 20:
        return None
    frames = samples[: count * step].astype(np.float32).reshape(count, step) / 32768.0
    level = 10 * np.log10(np.mean(frames * frames, axis=1) + 1e-12)
    # Digital silence, as in a file padded by an export, is not the room.
    heard = level[level > -80.0]
    if len(heard) < 20:
        return None
    return float(np.percentile(heard, 5)), float(np.percentile(heard, 90))


def silence_threshold(levels: tuple[float, float] | None) -> float:
    """The level that separates a pause from the voice in this recording."""
    if levels is None:
        return SILENCE_DB
    floor, voice = levels
    wanted = max(SILENCE_DB, floor + SILENCE_OVER_FLOOR)
    # Never so high that quiet words count as a pause.
    return round(min(wanted, max(SILENCE_DB, voice - SILENCE_UNDER_VOICE), SILENCE_DB_MAX), 1)


def silences(flac: str, duration: float) -> list[tuple[float, float]]:
    threshold = silence_threshold(sound_levels(flac))
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            flac,
            "-af",
            f"silencedetect=noise={threshold:g}dB:d=0.3",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    # A failed read must not pass for a recording with no pauses in it.
    if proc.returncode != 0:
        raise SystemExit(f"Could not read the sound: {ffmpeg_error_detail(proc.stderr or '')}")
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
    covers=None,
    lines=None,
    broll_sound: str = "mix",
    clean_sound: bool = True,
    zoom: str = "off",
    close=None,
    angles=None,
) -> dict | None:
    """Encode segments and print '<label> N%' as the render advances.

    Returns what the render reused, {pieces, made}, when it was made in pieces.


    Progress stays on stdout. ffmpeg's own log stays off that stream so a UI
    can show the percentage without the filter graph.
    """
    kept_s = sum(float(seg["end"]) - float(seg["start"]) for seg in segments)
    encoder, device = resolve_encoder()
    if os.environ.get("BOTCUT_RENDER", "").strip().lower() != "graph":
        from botcut import render

        return render.render(
            segments,
            clips,
            dst,
            label,
            fail_prefix,
            encoder=encoder,
            device=device,
            polish=polish,
            scene_transition=scene_transition,
            covers=covers,
            lines=lines,
            broll_sound=broll_sound,
            clean_sound=clean_sound,
            zoom=zoom,
            close=close,
            angles=angles,
        )
    # BOTCUT_RENDER=graph is the older way: the whole movie as one filter graph, encoded in one go.
    print(f"{label} 0%", flush=True)
    # The sound is listened to once before the encode, so the level is set by
    # one steady gain and not by a compressor riding the voice.
    measured = None
    if clean_sound:
        measured = measure_loudness(
            segments,
            clips,
            polish=polish,
            scene_transition=scene_transition,
            covers=covers,
            lines=lines,
            broll_sound=broll_sound,
            angles=angles,
        )
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
        covers=covers,
        lines=lines,
        broll_sound=broll_sound,
        clean_sound=clean_sound,
        measured=measured,
        zoom=zoom,
        close=close,
        angles=angles,
    )
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *args[1:]]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    err_parts: list[str] = []

    def drain() -> None:
        if proc.stderr is not None:
            err_parts.append(proc.stderr.read())

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
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
        raise SystemExit(f"{fail_prefix}: {ffmpeg_error_detail(err_parts[0] if err_parts else '')}")


def ffmpeg_error_detail(stderr: str) -> str:
    """The line in ffmpeg's log that names the problem.

    The thread exits at the end say only "Invalid argument". The cause sits
    earlier, so the first line that reads like one wins, then the last line.
    """
    noise = ("timescale not set", "deprecated pixel format", "Task finished", "Terminating thread",
             "Nothing was written", "Could not open encoder before EOF", "Conversion failed")
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    lines = [line for line in lines if not any(mark in line for mark in noise)]
    if not lines:
        return "ffmpeg failed"
    telling = ("Impossible to convert", "Error", "error", "Invalid", "No such", "Cannot", "cannot",
               "Could not", "not supported", "Unsupported", "failed")
    for line in lines:
        if any(mark in line for mark in telling):
            return line[:300]
    return lines[-1][:300]


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
# Every movie leaves at the same level, the one streaming speech is mixed to.
LOUDNESS_I = -16.0
LOUDNESS_TP = -1.5
LOUDNESS_LRA = 11.0
# Rumble below the voice goes, and steady hiss comes down a little. This is
# meant to be heard as a quieter room, not as processing.
CLEAN_FILTER = "highpass=f=70,afftdn=nr=8:nf=-50:tn=1"
# Quieter than this is silence or a card. There is no level to bring up.
QUIETEST_SOUND = -60.0


# A shot is brought toward the target by this much at most. Past that, the
# gain would mostly be lifting the room.
LEVEL_UP_MAX = 20.0
LEVEL_DOWN_MAX = 12.0


def loudness(path: str) -> float | None:
    """How loud a file's sound is over its whole length, in LUFS. None when it has none to measure."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "ebur128", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return parse_integrated(proc.stderr or "")


def parse_integrated(stderr: str) -> float | None:
    at = stderr.rfind("Integrated loudness:")
    if at < 0:
        return None
    found = re.search(r"I:\s*(-?\d+(?:\.\d+)?) LUFS", stderr[at:])
    if not found:
        return None
    value = float(found.group(1))
    return value if value >= QUIETEST_SOUND else None


def level_gain(clip: dict) -> float:
    """Decibels that bring this shot's voice to the level every shot is matched to."""
    try:
        heard = float(clip.get("loudness"))
    except (TypeError, ValueError):
        return 0.0
    if heard != heard or heard < QUIETEST_SOUND:
        return 0.0
    return round(max(-LEVEL_DOWN_MAX, min(LEVEL_UP_MAX, LOUDNESS_I - heard)), 1)


def parse_loudness(stderr: str) -> dict | None:
    """The numbers loudnorm prints after a measuring pass, or None when there is nothing to level."""
    end = stderr.rfind("}")
    start = stderr.rfind("{", 0, end)
    if start < 0 or end < 0:
        return None
    try:
        raw = json.loads(stderr[start : end + 1])
        found = {
            "i": float(raw["input_i"]),
            "tp": float(raw["input_tp"]),
            "lra": float(raw["input_lra"]),
            "thresh": float(raw["input_thresh"]),
            "offset": float(raw["target_offset"]),
        }
    except (ValueError, KeyError, TypeError):
        return None
    if any(value != value or value in (float("inf"), float("-inf")) for value in found.values()):
        return None
    if found["i"] < QUIETEST_SOUND:
        return None
    return found


def measure_loudness(
    segments: list[dict],
    clips: list[dict],
    polish: bool = False,
    scene_transition: str = "dip",
    covers=None,
    lines=None,
    broll_sound: str = "mix",
    angles=None,
) -> dict | None:
    """Play the cut's sound through once, with no picture, and measure it.

    A pass that fails is not a reason to lose the movie. It renders cleaned
    and at its own level.
    """
    args = render_args(
        segments,
        clips,
        "-",
        polish=polish,
        scene_transition=scene_transition,
        covers=covers,
        lines=lines,
        broll_sound=broll_sound,
        clean_sound=True,
        measure=True,
        angles=angles,
    )
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return None
    return parse_loudness(proc.stderr or "")


def _sound_chain(measured: dict | None, measure: bool) -> str:
    target = f"loudnorm=I={LOUDNESS_I}:TP={LOUDNESS_TP}:LRA={LOUDNESS_LRA}"
    if measure:
        return f"{CLEAN_FILTER},{target}:print_format=json"
    if measured is None:
        return CLEAN_FILTER
    return (
        f"{CLEAN_FILTER},{target}"
        f":measured_I={measured['i']}:measured_TP={measured['tp']}:measured_LRA={measured['lra']}"
        f":measured_thresh={measured['thresh']}:offset={measured['offset']}:linear=true"
        ",aresample=osr=48000"
    )


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


def _audio_filter(
    in_index: int,
    out_index: int,
    polish: bool,
    duration: float,
    fade_in: float,
    fade_out: float,
    mix_index: int | None = None,
    gain_db: float = 0.0,
) -> str:
    # The gain is on the voice alone. A B-roll shot's own sound stays a quiet bed under it.
    level = f"volume={gain_db:.1f}dB," if abs(gain_db) >= 0.1 else ""
    if mix_index is not None:
        # duration=first follows the voice, the first input, so a short clip does not end the window.
        voice = f"[{mix_index}:a]"
        lead = ""
        if level:
            lead = f"[{mix_index}:a]{level[:-1]}[g{out_index}];"
            voice = f"[g{out_index}]"
        chain = (
            f"{lead}[{in_index}:a]volume=0.25[b{out_index}];"
            f"{voice}[b{out_index}]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            f"aresample=osr=48000"
        )
    else:
        chain = f"[{in_index}:a]{level}aresample=osr=48000"
    if polish and fade_in > 0:
        chain += f",afade=t=in:st=0:d={fade_in:.3f}"
    if polish and fade_out > 0:
        fade_at = max(0.0, round(duration - fade_out, 3))
        chain += f",afade=t=out:st={fade_at:.3f}:d={fade_out:.3f}"
    return chain + f"[a{out_index}]"


def _full_range(clip: dict) -> bool:
    """A full-range source. Every branch into concat has to agree on the range,
    and a VA-API frame cannot be converted there, so the branch does it first."""
    if str(clip.get("color_range") or "").lower() in ("pc", "full", "jpeg"):
        return True
    return str(clip.get("pix_fmt") or "").startswith("yuvj")


def _video_filter(
    in_index: int,
    out_index: int,
    clip: dict,
    width: int,
    height: int,
    fps: float,
    fps_s: str,
    encoder: str,
    on_gpu: bool,
    picture: str,
    punch: str = "",
) -> str:
    # Limited range, like the cameras. A full-range clip is converted in its
    # own branch, before it meets the others.
    range_opts = ":in_range=pc:out_range=tv" if _full_range(clip) else ""
    if not on_gpu:
        # A punch-in is a crop around the speaker, scaled back up to the frame.
        tight = f"{punch}," if punch else ""
        return (
            f"[{in_index}:v]{tight}scale={width}:{height}:force_original_aspect_ratio=decrease{range_opts},"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps_s}"
            + picture
            + (",format=nv12,hwupload" if encoder == "vaapi" else "")
            + f"[v{out_index}]"
        )
    # scale_vaapi keeps the 4K resize on the Arc. This GPU drops the
    # surface when more than one VA-API input stays on the device
    # through concat, so each branch downloads, pads, and uploads
    # again for h264_vaapi. The dip runs on those software frames.
    to_tv = "scale=in_range=pc:out_range=tv," if range_opts else ""
    chain = (
        f"[{in_index}:v]scale_vaapi={width}:{height}:format=nv12:force_original_aspect_ratio=decrease,"
        f"hwdownload,format=nv12,{to_tv}pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    if not _same_rate(clip, fps):
        chain += f",fps={fps_s}"
    return chain + picture + f",format=nv12,hwupload[v{out_index}]"


def cut_pieces(
    segments: list[dict],
    clips: list[dict],
    *,
    polish: bool = False,
    scene_transition: str = "dip",
    covers=None,
    lines=None,
    zoom: str = "off",
    close=None,
    angles=None,
) -> list[dict]:
    """The cut as the pieces of picture that play, in order, each with the sound under it.

    A piece is one stretch of one file's picture: `clip`, `start`, `span`,
    the fades on it, and the crop or move that zooms it. When the picture is
    not the speaker's own, B-roll or another camera, `voice` and
    `voice_start` say where the sound comes from, and `angle` marks another
    camera on the same moment, whose own sound is never played.
    """
    transition = _transition(scene_transition)
    durations = []
    for clip in clips:
        try:
            durations.append(float(clip.get("duration") or 0))
        except (TypeError, ValueError):
            durations.append(0.0)
    by_segment: dict[int, list[dict]] = {}
    if covers:
        from botcut.broll import cover_windows

        for window in cover_windows(covers, lines or [], segments, durations):
            by_segment.setdefault(int(window["segment"]), []).append(window)
    if angles:
        from botcut.angles import angle_windows

        # B-roll laid over a line wins the picture. The other camera shows around it.
        for window in angle_windows(angles, lines or [], segments, clips):
            by_segment.setdefault(int(window["segment"]), []).append(window)

    def plain(clip: dict) -> bool:
        return (
            not is_card(str(clip.get("path") or ""))
            and str(clip.get("role") or "") != "broll"
            and not _rotated(clip)
        )

    tight = [False] * len(segments)
    pushed = [0.0] * len(segments)
    close_by_clip: dict[int, list] = {}
    if zoom == "cuts":
        from botcut.frame import punched

        tight = punched(segments, clips, plain, lines)
    elif zoom == "push":
        from botcut.frame import push_starts

        pushed = push_starts(segments, lines)
    elif zoom == "lines":
        from botcut.frame import close_spans

        close_by_clip = close_spans(lines, close)
    auto = None
    stretches: list[float] = []
    if zoom == "auto":
        from botcut.frame import AutoFraming, close_spans, push_starts, stretch_lengths

        auto = AutoFraming()
        close_by_clip = close_spans(lines, close)
        pushed = push_starts(segments, lines)
        stretches = stretch_lengths(segments, lines)
    found: list[dict] = []
    # Outer fades are chosen on the spoken segments. A cover cut inside one
    # segment is not a scene change, so it does not get those fades.
    for i, seg in enumerate(segments):
        spoken = int(seg["clip"])
        seg_start = float(seg["start"])
        seg_end = float(seg["end"])
        duration = max(0.0, seg_end - seg_start)
        pic_in, pic_out = (0.0, 0.0)
        aud_in, aud_out = (0.0, 0.0)
        if polish:
            pic_in, pic_out = _picture_edges(i, segments, transition)
            aud_in, aud_out = _audio_edges(i, segments, duration, transition)
        pieces: list[dict] = []
        cursor = seg_start
        for window in _one_picture(by_segment.get(i, [])):
            win_start = float(window["start"])
            win_end = float(window["end"])
            if win_start - cursor > 1e-3:
                pieces.append({"clip": spoken, "start": cursor, "end": win_start})
            if win_end - win_start > 1e-3:
                # The voice goes on under the cover, so the spoken file is opened at this window too.
                length = win_end - win_start
                src = float(window.get("src") or 0.0)
                piece = {
                    "clip": int(window["clip"]),
                    "start": src,
                    "end": src + length,
                    "voice": spoken,
                    "voice_start": win_start,
                }
                if window.get("angle"):
                    piece["angle"] = True
                # A run that goes on across this segment's join is one piece of
                # footage. A fade there would be a dip inside the B-roll.
                if window.get("continued"):
                    piece["continued"] = True
                if window.get("continues"):
                    piece["continues"] = True
                pieces.append(piece)
            cursor = max(cursor, win_end)
        if seg_end - cursor > 1e-3 or not pieces:
            pieces.append(
                {
                    "clip": spoken,
                    "start": seg_start if not pieces else cursor,
                    "end": seg_end,
                }
            )
        if close_by_clip.get(spoken) and seg.get("reason") != "card":
            from botcut.frame import split_close

            # A line shown close starts and ends inside the piece it is part of.
            pieces = [
                part
                for piece in pieces
                for part in (
                    split_close(piece, close_by_clip[spoken])
                    if piece["clip"] == spoken and "voice" not in piece
                    else [piece]
                )
            ]
        single = len(pieces) == 1 and pieces[0]["clip"] == spoken and "voice" not in pieces[0]
        last_piece = len(pieces) - 1
        for j, piece in enumerate(pieces):
            video = clips[int(piece["clip"])]
            if single:
                video_start = seg["start"]
                span = seg["end"] - seg["start"]
                shown = duration
                fade_in, fade_out = pic_in, pic_out
                a_in, a_out = aud_in, aud_out
            else:
                video_start = piece["start"]
                span = piece["end"] - piece["start"]
                shown = max(0.0, span)
                fade_in = pic_in if j == 0 and not piece.get("continued") else 0.0
                fade_out = pic_out if j == last_piece and not piece.get("continues") else 0.0
                raw_in = aud_in if j == 0 else 0.0
                raw_out = aud_out if j == last_piece else 0.0
                a_in, a_out = _fit_pair(shown, raw_in, raw_out) if polish else (0.0, 0.0)
            # Only the speaker's own picture is zoomed. B-roll over the line is left as shot.
            punch = ""
            middle = float(video_start) + float(span) / 2
            own = int(piece["clip"]) == spoken and "voice" not in piece
            if zoom != "off" and own:
                from botcut.frame import (
                    CLOSE_IN,
                    PUSH_STRETCH,
                    TIGHT,
                    can_punch_in,
                    inside_a_line,
                    punch_crop,
                    push_filter,
                )

                if not (plain(video) and can_punch_in(video)):
                    if auto:
                        auto.other_picture()
                elif zoom == "cuts" and tight[i]:
                    punch = punch_crop(video, at=middle)
                elif zoom == "lines" and piece.get("tight"):
                    punch = punch_crop(video, CLOSE_IN, at=middle)
                elif zoom == "push":
                    punch = push_filter(video, pushed[i] + float(video_start) - seg_start, at=middle)
                elif auto:
                    runs_on = j == 0 and i > 0 and inside_a_line(segments[i - 1], seg, lines)
                    if auto.frame(
                        spoken, float(span), close=bool(piece.get("tight")), runs_on=runs_on, same_footage=j > 0
                    ):
                        punch = punch_crop(video, TIGHT, at=middle)
                    elif stretches[i] >= PUSH_STRETCH:
                        # A long wide stretch creeps in, so it is not a locked-off frame for half a minute.
                        punch = push_filter(video, pushed[i] + float(video_start) - seg_start, at=middle)
            elif auto and not own:
                auto.other_picture()
            row = {
                "segment": i,
                "spoken": spoken,
                "clip": int(piece["clip"]),
                "start": video_start,
                "span": span,
                "shown": shown,
                "fade_in": fade_in,
                "fade_out": fade_out,
                "a_in": a_in,
                "a_out": a_out,
                "punch": punch,
                "first": j == 0,
                "last": j == last_piece,
            }
            if "voice" in piece:
                row["voice"] = int(piece["voice"])
                row["voice_start"] = float(piece["voice_start"])
            if piece.get("angle"):
                row["angle"] = True
            found.append(row)
    return found


def _one_picture(windows: list[dict]) -> list[dict]:
    """The windows of one segment in order, with B-roll shown where it and another camera overlap."""
    covers = sorted((w for w in windows if not w.get("angle")), key=lambda item: float(item["start"]))
    angles = sorted((w for w in windows if w.get("angle")), key=lambda item: float(item["start"]))
    if not covers or not angles:
        return covers or angles
    out = list(covers)
    for window in angles:
        start, end = float(window["start"]), float(window["end"])
        src = float(window.get("src") or 0.0)
        parts = [(start, end)]
        for cover in covers:
            low, high = float(cover["start"]), float(cover["end"])
            parts = [
                part
                for left, right in parts
                for part in ((left, min(right, low)), (max(left, high), right))
                if part[1] - part[0] > 1e-3
            ]
        for left, right in parts:
            out.append({**window, "start": left, "end": right, "src": src + (left - start)})
    return sorted(out, key=lambda item: float(item["start"]))


def render_args(
    segments: list[dict],
    clips: list[dict],
    dst: str,
    encoder: str = "x264",
    device: str | None = None,
    polish: bool = False,
    scene_transition: str = "dip",
    covers=None,
    lines=None,
    broll_sound: str = "mix",
    clean_sound: bool = False,
    measured: dict | None = None,
    measure: bool = False,
    zoom: str = "off",
    close=None,
    angles=None,
) -> list[str]:
    """ffmpeg arguments for the cut, as one filter graph.

    `zoom` moves in on the speaker: `cuts` goes from wide to a little tighter
    at a join between lines, so a jump cut reads as a change of framing;
    `push` creeps in between joins; `lines` shows the lines named in `close`
    tighter than the rest. `off` plays every piece as shot.

    `clean_sound` cleans the joined sound and, with `measured`, brings it to
    the target level. `measure` builds the sound alone, with no picture, and
    has loudnorm print what it hears.
    """
    if not segments:
        raise SystemExit("No segments to render")
    if encoder not in ("x264", "vaapi"):
        raise SystemExit(f"Unknown encoder {encoder}")
    if broll_sound not in ("mix", "voice"):
        raise SystemExit(f"Unknown b-roll sound {broll_sound}")
    if zoom not in ZOOM_NAMES:
        raise SystemExit(f"Unknown zoom {zoom}")
    if encoder == "vaapi" and not device:
        raise SystemExit("VA-API encode needs a device")
    width, height, fps = frame_size(clips)
    args = ["-y"]
    if measure:
        # Listening needs no picture, so nothing here touches the GPU or the encoder.
        encoder = "x264"
        zoom = "off"
    if encoder == "vaapi":
        args += ["-init_hw_device", f"vaapi=va:{device}", "-filter_hw_device", "va"]
    fps_s = _fps(fps)
    filters = []
    out_i = 0
    in_i = 0
    for piece in cut_pieces(
        segments,
        clips,
        polish=polish,
        scene_transition=scene_transition,
        covers=covers,
        lines=lines,
        zoom=zoom,
        close=close,
        angles=angles,
    ):
        video = clips[piece["clip"]]
        punch = piece["punch"]
        shown = piece["shown"]
        a_in, a_out = piece["a_in"], piece["a_out"]
        # The zoom runs on software frames, so a zoomed piece is decoded there.
        on_gpu = encoder == "vaapi" and not punch and not _rotated(video) and _vaapi_decodable(video)
        if on_gpu:
            args += [
                "-hwaccel",
                "vaapi",
                "-hwaccel_device",
                str(device),
                "-hwaccel_output_format",
                "vaapi",
            ]
        args += ["-ss", _num(piece["start"]), "-t", _num(piece["span"]), "-i", video["path"]]
        v_in = in_i
        in_i += 1
        voice_in = None
        if "voice" in piece:
            voice = clips[piece["voice"]]
            args += ["-ss", _num(piece["voice_start"]), "-t", _num(piece["span"]), "-i", voice["path"]]
            voice_in = in_i
            in_i += 1
        picture = _picture_suffix(shown, piece["fade_in"], piece["fade_out"]) if polish else ""
        if not measure:
            filters.append(
                _video_filter(v_in, out_i, video, width, height, fps, fps_s, encoder, on_gpu, picture, punch)
            )
        # Each shot's voice is matched to the others before the join, so a
        # quiet take is not left quiet beside a loud one.
        speaker = clips[piece["voice"]] if "voice" in piece else video
        gain = level_gain(speaker) if clean_sound or measure else 0.0
        if voice_in is None:
            filters.append(_audio_filter(v_in, out_i, polish, shown, a_in, a_out, gain_db=gain))
        elif broll_sound == "mix" and video.get("audio", True) and not piece.get("angle"):
            filters.append(_audio_filter(v_in, out_i, polish, shown, a_in, a_out, voice_in, gain_db=gain))
        else:
            # Voice only. A silent B-roll file has no [N:a] to mix, so it lands here too.
            filters.append(_audio_filter(voice_in, out_i, polish, shown, a_in, a_out, gain_db=gain))
        out_i += 1
    sound = "[a]"
    if measure:
        concat_in = "".join(f"[a{i}]" for i in range(out_i))
        filters.append(f"{concat_in}concat=n={out_i}:v=0:a=1[a]")
    else:
        concat_in = "".join(f"[v{i}][a{i}]" for i in range(out_i))
        filters.append(f"{concat_in}concat=n={out_i}:v=1:a=1[v][a]")
    if clean_sound or measure:
        filters.append(f"[a]{_sound_chain(measured, measure)}[sound]")
        sound = "[sound]"
    if measure:
        return [*args, "-filter_complex", ";".join(filters), "-map", sound, "-f", "null", "-"]
    args += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-map",
        sound,
    ]
    args += [*encoder_args(encoder), "-c:a", "aac", "-ar", "48000", "-movflags", "+faststart", dst]
    return args


ZOOM_NAMES = ("off", "auto", "cuts", "push", "lines")


def encoder_args(encoder: str) -> list[str]:
    if encoder == "vaapi":
        return ["-c:v", "h264_vaapi", "-qp", "20"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]


def frame_size(clips: list[dict]) -> tuple[int, int, float]:
    """The size and rate the movie is made at: the first camera shot's.

    An open card is clips[0]. Its still is not the camera's size or rate.
    B-roll is not the camera either.
    """
    ref = clips[0]
    for clip in clips:
        if is_card(str(clip.get("path") or "")) or str(clip.get("role") or "") in ("broll", "angle"):
            continue
        ref = clip
        break
    width, height, fps = int(ref["width"]), int(ref["height"]), float(ref["fps"])
    if width <= 0 or height <= 0 or fps <= 0:
        raise SystemExit(f"Clip has no video to render: {ref['path']}")
    return width, height, fps


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
