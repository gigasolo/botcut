"""Render a cut as pieces: the sound in one pass, the picture a piece at a time.

The sound is put together here, sample by sample, so a join inside a shot can
be a real crossfade and not two fades with a hole between them. Each piece of
picture is encoded to its own small file under work/pieces, named by what it
shows, and the movie is those files joined without encoding them again. A
piece that has not changed since the last render is not made twice, so
dropping one line costs the few pieces around it.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path

from botcut.card import is_card
from botcut.color import color_filter
from botcut.frame import portrait_crop
from botcut.media import (
    _fps,
    _full_range,
    _num,
    _picture_suffix,
    _rotated,
    _sound_chain,
    _transition,
    _vaapi_decodable,
    _video_filter,
    cut_pieces,
    encoder_args,
    ffmpeg_error_detail,
    level_gain,
    parse_loudness,
    target_size,
)

RATE = 48000
# How far each side of a join inside a shot reaches into the other. The two
# overlap for twice this, one fading down as the other comes up.
CROSS = 0.012
# A B-roll shot's own sound, under the voice.
BED = 0.25
BED_FADE = 0.03
# Auto-ducked background music levels: -24 dB under voice, -16 dB in pauses/bookends.
MUSIC_DUCK = 0.063
MUSIC_OPEN = 0.16
MUSIC_FADE_OUT = 1.2
# Live title overlay timing over the opening seconds of live video.
LIVE_TITLE_IN = 0.20
LIVE_TITLE_FADE_IN = 0.35
LIVE_TITLE_OUT = 2.75
LIVE_TITLE_FADE_OUT = 0.45
LIVE_TITLE_END = LIVE_TITLE_OUT + LIVE_TITLE_FADE_OUT
# Pieces encoded at once. Each ffmpeg already uses several cores.
PIECE_WORKERS = 3
# A piece nothing has used for this long is removed.
PIECE_KEEP_SECONDS = 2 * 24 * 3600
# Maximum disk space for cached pieces before evicting oldest unused pieces.
PIECE_CACHE_MAX_BYTES = 1536 * 1024 * 1024


def _piece_cache_max_bytes() -> int:
    raw = os.environ.get("BOTCUT_PIECE_CACHE_MB", "").strip()
    if raw:
        try:
            mb = float(raw)
            if mb > 0:
                return int(mb * 1024 * 1024)
        except ValueError:
            pass
    return PIECE_CACHE_MAX_BYTES


def timeline(pieces: list[dict], fps: float) -> list[dict]:
    """The pieces on a grid of whole frames.

    Every piece gets a whole number of frames. Inside one stretch of voice
    the boundaries are rounded together, so the picture cuts while the sound
    goes on unbroken, and the speaker's picture starts on the frame the sound
    is at. A piece that rounds to no frames is left out.
    """
    rate = Fraction(fps).limit_denominator(1001)
    out: list[dict] = []
    at = 0
    index = 0
    while index < len(pieces):
        seg = pieces[index]["segment"]
        group = []
        while index < len(pieces) and pieces[index]["segment"] == seg:
            group.append(pieces[index])
            index += 1
        first = group[0]
        origin = float(first.get("voice_start", first["start"]))
        # A cut can only show whole frames of its source. Starting the voice on
        # the frame that is shown, and not where the cut was asked for, keeps
        # the two together to the sample. It moves the cut by half a frame at most.
        origin = float(Fraction(round(origin * rate)) / rate)
        for piece in group:
            voice_at = float(piece.get("voice_start", piece["start"]))
            low = round((voice_at - origin) * rate)
            high = round((voice_at + float(piece["span"]) - origin) * rate)
            frames = high - low
            if frames <= 0:
                continue
            offset = float(Fraction(low) / rate)
            # The speaker's own picture, and another camera on the same moment, stay in step with the voice.
            synced = "voice" not in piece or piece.get("angle")
            start = float(piece["start"]) + (origin + offset - voice_at if synced else 0.0)
            out.append(
                {
                    **piece,
                    "start": max(0.0, start),
                    "frames": frames,
                    "at": at,
                    "voice_clip": int(piece.get("voice", piece["clip"])),
                    "voice_at": origin + offset,
                    "length": float(Fraction(frames) / rate),
                }
            )
            at += frames
    return out


def _samples(frames: int, fps: float) -> int:
    rate = Fraction(fps).limit_denominator(1001)
    return int(round(Fraction(frames) * RATE / rate))


def voice_runs(placed: list[dict], fps: float) -> list[dict]:
    """The stretches of unbroken voice: one per segment, as sample positions on the movie."""
    runs: list[dict] = []
    for piece in placed:
        begin = _samples(piece["at"], fps)
        end = _samples(piece["at"] + piece["frames"], fps)
        if runs and runs[-1]["segment"] == piece["segment"]:
            runs[-1]["end"] = end
            runs[-1]["a_out"] = piece["a_out"]
            continue
        runs.append(
            {
                "segment": piece["segment"],
                "clip": piece["voice_clip"],
                "source": piece["voice_at"],
                "begin": begin,
                "end": end,
                "a_in": piece["a_in"],
                "a_out": piece["a_out"],
            }
        )
    return runs


class Sounds:
    """Each file's sound, read once at 48 kHz stereo and cached under work/sound."""

    def __init__(self, work: str, clips: list[dict]) -> None:
        self._work = work
        self.sound_dir = os.path.join(work, "sound")
        os.makedirs(self.sound_dir, exist_ok=True)
        self._clips = clips
        self._open: dict[int, object] = {}
        self.used: set[str] = set()
        self._lock = threading.Lock()
        # Clean up any leftover partial extracts from stopped renders.
        for name in os.listdir(self.sound_dir):
            if name.endswith(".part"):
                try:
                    os.remove(os.path.join(self.sound_dir, name))
                except OSError:
                    pass

    def _cache_path(self, clip: dict) -> str:
        path = str(clip["path"])
        try:
            info = os.stat(path)
            stamp = [info.st_size, info.st_mtime_ns]
        except OSError:
            stamp = [0, 0]
        digest = hashlib.sha1(json.dumps([os.path.abspath(path), *stamp]).encode("utf-8")).hexdigest()[:16]
        return os.path.join(self.sound_dir, f"sound-{digest}.raw")

    def preload(self, indexes: list[int] | set[int]) -> None:
        missing = []
        for idx in sorted(set(indexes)):
            if idx < 0 or idx >= len(self._clips):
                continue
            clip = self._clips[idx]
            if not clip.get("audio", True):
                continue
            path = self._cache_path(clip)
            if not (os.path.isfile(path) and os.path.getsize(path) >= 4):
                missing.append(idx)
        if len(missing) <= 1:
            return
        pool = ThreadPoolExecutor(max_workers=min(PIECE_WORKERS, len(missing)))
        try:
            list(pool.map(self.of, missing))
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            pool.shutdown(wait=True)

    def of(self, index: int):
        """The samples of one clip as an array of frames by two, or None when it has no sound."""
        import numpy as np

        with self._lock:
            if index in self._open:
                return self._open[index]
        clip = self._clips[index]
        found = None
        if clip.get("audio", True):
            path = self._cache_path(clip)
            if not (os.path.isfile(path) and os.path.getsize(path) >= 4):
                part = f"{path}.{threading.get_ident()}.part"
                try:
                    proc = subprocess.run(
                        [
                            "ffmpeg", "-y", "-v", "error", "-i", clip["path"], "-vn", "-map", "0:a:0",
                            # Sample 0 is the start of the file, even when the sound track starts late.
                            "-af", f"aresample={RATE}:async=1:first_pts=0",
                            "-ac", "2", "-f", "s16le", part,
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if proc.returncode != 0:
                        raise SystemExit(
                            f"Could not read the sound of {os.path.basename(clip['path'])}: "
                            f"{ffmpeg_error_detail(proc.stderr or '')}"
                        )
                    os.replace(part, path)
                except BaseException:
                    try:
                        os.remove(part)
                    except OSError:
                        pass
                    raise
            now = time.time()
            try:
                os.utime(path, (now, now))
            except OSError:
                pass
            if os.path.isfile(path) and os.path.getsize(path) >= 4:
                found = np.memmap(path, dtype=np.int16, mode="r").reshape(-1, 2)
            with self._lock:
                self.used.add(path)
        with self._lock:
            self._open[index] = found
        return found

    def close(self) -> None:
        with self._lock:
            self._open.clear()


def _take(source, begin: int, count: int):
    """`count` frames from `begin`, as floats, with silence where the file has none."""
    import numpy as np

    out = np.zeros((max(0, count), 2), dtype=np.float32)
    if source is None or count <= 0:
        return out
    low, high = max(0, begin), min(len(source), begin + count)
    if high > low:
        out[low - begin : high - begin] = np.asarray(source[low:high], dtype=np.float32) / 32768.0
    return out


def _load_music_samples(path: str, total: int):
    """Decode `path` to 48 kHz stereo float32 of length `total`, looping cleanly if shorter."""
    import numpy as np

    if not path or not os.path.isfile(path) or total <= 0:
        return None
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", path, "-vn",
            "-af", f"aresample={RATE}:async=1:first_pts=0",
            "-ac", "2", "-f", "s16le", "-",
        ],
        capture_output=True,
    )
    if proc.returncode != 0 or len(proc.stdout) < 4:
        return None
    track = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32).reshape(-1, 2) / 32768.0
    if len(track) == 0:
        return None
    if len(track) >= total:
        return track[:total].copy()
    reps = (total // len(track)) + 1
    return np.tile(track, (reps, 1))[:total].copy()


def _duck_music(voice, music):
    """Auto-duck `music` under `voice`: -24 dB during speech, -16 dB during pauses, smooth envelope."""
    import numpy as np

    total = len(voice)
    if total == 0:
        return music
    # Compute 50ms RMS speech activity envelope and upsample smoothly.
    hop = RATE // 20
    frames = max(1, total // hop)
    mono = np.mean(np.abs(voice[: frames * hop]), axis=1).reshape(frames, hop)
    rms = np.sqrt(np.mean(mono * mono, axis=1) + 1e-12)
    speaking = (rms > 0.015).astype(np.float32)
    # Smooth with a 15-frame (~0.75s) moving average for natural swell/duck transitions.
    kernel = np.ones(min(15, frames), dtype=np.float32) / min(15, frames)
    smooth = np.convolve(speaking, kernel, mode="same")
    gain_blocks = MUSIC_OPEN - (MUSIC_OPEN - MUSIC_DUCK) * np.clip(smooth, 0.0, 1.0)
    gain = np.interp(
        np.arange(total, dtype=np.float32),
        (np.arange(frames, dtype=np.float32) + 0.5) * hop,
        gain_blocks,
    ).astype(np.float32)
    bed = music * gain[:, None]
    _shape(bed, int(0.5 * RATE), rising=True, equal_power=False)
    _shape(bed, int(MUSIC_FADE_OUT * RATE), rising=False, equal_power=False)
    return bed


def mix(
    placed: list[dict],
    clips: list[dict],
    sounds,
    fps: float,
    *,
    polish: bool = True,
    scene_transition: str = "dip",
    broll_sound: str = "mix",
    level: bool = True,
    music: str | None = None,
):
    """The sound of the whole cut as one array.

    A join inside a shot, or between shots when there is no dip, is a
    crossfade: each side reaches CROSS into the other. A dip between two
    shots fades one out and the next in. Each shot's voice gets the gain that
    matches it to the others. `sounds.of(i)` gives a clip's samples.
    """
    import numpy as np

    runs = voice_runs(placed, fps)
    total = runs[-1]["end"] if runs else 0
    out = np.zeros((total, 2), dtype=np.float32)
    cross = int(CROSS * RATE)
    dip = _transition(scene_transition) == "dip"
    for number, run in enumerate(runs):
        source = sounds.of(run["clip"])
        count = run["end"] - run["begin"]
        if count <= 0:
            continue
        before = runs[number - 1] if number else None
        after = runs[number + 1] if number + 1 < len(runs) else None
        src = int(round(run["source"] * RATE))
        # A crossfade needs sound on the far side of the join, on both sides of it.
        lead = cross if polish and _crosses(before, run, dip, cross) else 0
        tail = cross if polish and _crosses(run, after, dip, cross) else 0
        lead = min(lead, src, run["begin"])
        tail = min(tail, total - run["end"])
        chunk = _take(source, src - lead, lead + count + tail)
        gain = 10 ** (level_gain(clips[run["clip"]]) / 20) if level else 1.0
        if gain != 1.0:
            chunk *= gain
        if polish:
            _shape(chunk, 2 * lead if lead else int(run["a_in"] * RATE), rising=True, equal_power=bool(lead))
            _shape(chunk, 2 * tail if tail else int(run["a_out"] * RATE), rising=False, equal_power=bool(tail))
        out[run["begin"] - lead : run["end"] + tail] += chunk
    if broll_sound == "mix":
        fade = int(BED_FADE * RATE)
        for piece in placed:
            if "voice" not in piece or piece.get("angle"):
                continue
            source = sounds.of(piece["clip"])
            if source is None:
                continue
            begin = _samples(piece["at"], fps)
            end = min(total, _samples(piece["at"] + piece["frames"], fps))
            chunk = _take(source, int(round(float(piece["start"]) * RATE)), end - begin) * BED
            # A run that goes on across a join is one stretch of footage, and so is its sound.
            if not piece.get("continued"):
                _shape(chunk, fade, rising=True, equal_power=False)
            if not piece.get("continues"):
                _shape(chunk, fade, rising=False, equal_power=False)
            out[begin:end] += chunk
    if music and total > 0:
        bed = _load_music_samples(music, total)
        if bed is not None:
            out += _duck_music(out, bed)
    return np.clip(out, -1.0, 1.0)


def _crosses(left: dict | None, right: dict | None, dip: bool, cross: int) -> bool:
    """True when the join between two stretches of voice is a crossfade and not two fades."""
    if left is None or right is None:
        return False
    if dip and left["clip"] != right["clip"]:
        return False
    # Each side has to be long enough to hold the overlap and still play.
    return min(left["end"] - left["begin"], right["end"] - right["begin"]) > 4 * cross


def _shape(chunk, count: int, *, rising: bool, equal_power: bool) -> None:
    """Fade the head (rising) or the tail of a chunk over `count` frames, in place."""
    import numpy as np

    count = min(int(count), len(chunk) // 2)
    if count <= 0:
        return
    ramp = (np.arange(count, dtype=np.float32) + 0.5) / count
    if equal_power:
        ramp = np.sin(ramp * (np.pi / 2))
    if rising:
        chunk[:count] *= ramp[:, None]
    else:
        chunk[-count:] *= ramp[::-1, None]


def write_wav(path: str, samples) -> None:
    import numpy as np

    with wave.open(path, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes((samples * 32767.0).astype(np.int16).tobytes())


def measure(wav: str) -> dict | None:
    """Listen to the joined sound once, so the level is set by one steady gain."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", wav, "-af", _sound_chain(None, True), "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return parse_loudness(proc.stderr or "")


def _effective_size(clip: dict) -> tuple[int, int]:
    w, h = int(clip.get("width") or 0), int(clip.get("height") or 0)
    try:
        rot = abs(int(round(float(clip.get("rotate") or 0)))) % 180
    except (TypeError, ValueError):
        rot = 0
    return (h, w) if rot == 90 else (w, h)


def _split_screen_args(
    piece: dict,
    clip: dict,
    voice_clip: dict,
    dst: str,
    *,
    width: int,
    height: int,
    fps: float,
    encoder: str,
    device: str | None,
    polish: bool,
) -> list[str]:
    """Portrait split-screen: B-roll/screen fitted in the top 56%, face-tracked speaker in the bottom 44%."""
    args = ["-y"]
    if encoder == "vaapi":
        args += ["-init_hw_device", f"vaapi=va:{device}", "-filter_hw_device", "va"]
    length = piece["length"]
    fps_s = _fps(fps)
    picture = _picture_suffix(length, piece["fade_in"], piece["fade_out"]) if polish else ""
    top_h = max(2, (int(height * 0.56) // 2) * 2)
    bot_h = max(2, height - top_h)
    top_range = ":in_range=pc:out_range=tv" if _full_range(clip) else ""
    bot_range = ":in_range=pc:out_range=tv" if _full_range(voice_clip) else ""
    voice_at = float(piece.get("voice_at", piece.get("voice_start", 0.0)))
    v_crop = portrait_crop(voice_clip, width, bot_h, at=voice_at + length / 2)
    v_crop_prefix = f"{v_crop}," if v_crop else ""
    fmt_tail = ",format=nv12,hwupload" if encoder == "vaapi" else ",format=yuv420p"
    graph = (
        f"[0:v]scale={width}:{top_h}:force_original_aspect_ratio=decrease{top_range},"
        f"pad={width}:{top_h}:(ow-iw)/2:(oh-ih)/2:color=#111318,setsar=1,fps={fps_s}[top];"
        f"[1:v]{v_crop_prefix}scale={width}:{bot_h}:force_original_aspect_ratio=increase{bot_range},"
        f"crop={width}:{bot_h},setsar=1,fps={fps_s}[bot];"
        f"[top][bot]vstack=inputs=2{picture}{fmt_tail}[v0]"
    )
    seek0 = max(0.0, float(piece["start"]) - 0.25 / fps)
    seek1 = max(0.0, voice_at - 0.25 / fps)
    span = _num(length + 2.0 / fps + 0.05)
    if clip.get("is_image"):
        args += ["-loop", "1", "-framerate", fps_s, "-t", span, "-i", clip["path"]]
    else:
        args += ["-ss", _num(seek0), "-t", span, "-i", clip["path"]]
    args += ["-ss", _num(seek1), "-t", span, "-i", voice_clip["path"]]
    args += ["-filter_complex", graph, "-map", "[v0]", "-an", "-frames:v", str(piece["frames"])]
    args += [*encoder_args(encoder), "-bf", "0", "-video_track_timescale", "90000", dst]
    return args


def _ken_burns_expr(fps: float) -> str:
    """Subtle 4% smooth slow zoom for still images, using sub-pixel perspective resampling."""
    zoom = f"min(1+0.004*(on/{fps:g}),1.05)"
    left = f"W*0.5*(1-1/({zoom}))"
    top = f"H*0.5*(1-1/({zoom}))"
    right = f"{left}+W/({zoom})"
    bottom = f"{top}+H/({zoom})"
    return (
        f"perspective=x0='{left}':y0='{top}':x1='{right}':y1='{top}'"
        f":x2='{left}':y2='{bottom}':x3='{right}':y3='{bottom}'"
        ":sense=source:eval=frame:interpolation=cubic"
    )


def _studio_bg(studio_frame: str) -> tuple[str, str, float]:
    """Return (canvas_hex, bezel_hex, inner_ratio) for studio-framed slides and screen recordings."""
    if studio_frame == "light":
        return ("#F2F4F7", "#D9DEE6", 0.90)
    if studio_frame == "none":
        return ("#000000", "#000000", 1.0)
    return ("#111318", "#1E2430", 0.94)


def _pip_args(
    piece: dict,
    clip: dict,
    voice_clip: dict,
    dst: str,
    *,
    width: int,
    height: int,
    fps: float,
    encoder: str,
    device: str | None,
    polish: bool,
    studio_frame: str = "dark",
) -> list[str]:
    """Landscape Picture-in-Picture: B-roll/screen/slide full frame with face-tracked speaker in corner."""
    args = ["-y"]
    if encoder == "vaapi":
        args += ["-init_hw_device", f"vaapi=va:{device}", "-filter_hw_device", "va"]
    length = piece["length"]
    fps_s = _fps(fps)
    picture = _picture_suffix(length, piece["fade_in"], piece["fade_out"]) if polish else ""
    main_range = ":in_range=pc:out_range=tv" if _full_range(clip) else ""
    voice_range = ":in_range=pc:out_range=tv" if _full_range(voice_clip) else ""
    voice_at = float(piece.get("voice_at", piece.get("voice_start", 0.0)))
    pip_w = max(64, (int(width * 0.22) // 2) * 2)
    pip_h = max(64, (int(pip_w * 0.75) // 2) * 2)
    margin = max(16, int(width * 0.02))
    v_crop = portrait_crop(voice_clip, pip_w, pip_h, at=voice_at + length / 2)
    v_crop_prefix = f"{v_crop}," if v_crop else ""
    fmt_tail = ",format=nv12,hwupload" if encoder == "vaapi" else ",format=yuv420p"
    canvas_col, bezel_col, ratio = _studio_bg(studio_frame)
    inner_w = max(2, (int(width * ratio) // 2) * 2)
    inner_h = max(2, (int(height * ratio) // 2) * 2)
    bezel = f"pad=iw+6:ih+6:3:3:color={bezel_col}," if studio_frame != "none" else ""
    if clip.get("is_image"):
        bg = (
            f"[0:v]scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease{main_range},"
            f"{bezel}pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={canvas_col},setsar=1,fps={fps_s},"
            f"{_ken_burns_expr(fps)}[bg]"
        )
    else:
        bg = (
            f"[0:v]scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease{main_range},"
            f"{bezel}pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={canvas_col},setsar=1,fps={fps_s}[bg]"
        )
    graph = (
        f"{bg};"
        f"[1:v]{v_crop_prefix}scale={pip_w}:{pip_h}:force_original_aspect_ratio=increase{voice_range},"
        f"crop={pip_w}:{pip_h},setsar=1,fps={fps_s},pad=iw+6:ih+6:3:3:color={bezel_col}[pip];"
        f"[bg][pip]overlay=x=W-w-{margin}:y=H-h-{margin}{picture}{fmt_tail}[v0]"
    )
    seek0 = max(0.0, float(piece["start"]) - 0.25 / fps)
    seek1 = max(0.0, voice_at - 0.25 / fps)
    span = _num(length + 2.0 / fps + 0.05)
    if clip.get("is_image"):
        args += ["-loop", "1", "-framerate", fps_s, "-t", span, "-i", clip["path"]]
    else:
        args += ["-ss", _num(seek0), "-t", span, "-i", clip["path"]]
    args += ["-ss", _num(seek1), "-t", span, "-i", voice_clip["path"]]
    args += ["-filter_complex", graph, "-map", "[v0]", "-an", "-frames:v", str(piece["frames"])]
    args += [*encoder_args(encoder), "-bf", "0", "-video_track_timescale", "90000", dst]
    return args


def piece_args(
    piece: dict,
    clip: dict,
    dst: str,
    *,
    width: int,
    height: int,
    fps: float,
    encoder: str,
    device: str | None,
    polish: bool,
    clips: list[dict] | None = None,
    pip: bool = False,
    studio_frame: str = "dark",
    live_overlay: tuple[str, float] | None = None,
) -> list[str]:
    """ffmpeg arguments that encode one piece of picture, with no sound, to its own file."""
    is_portrait = height > width
    is_cover = "voice" in piece and not piece.get("angle")
    card = is_card(str(clip.get("path") or ""))
    if is_cover and not card and clips is not None:
        voice_idx = int(piece.get("voice_clip", piece["voice"]))
        if 0 <= voice_idx < len(clips):
            voice_clip = clips[voice_idx]
            has_voice_video = int(voice_clip.get("width") or 0) > 0 and int(voice_clip.get("height") or 0) > 0
            if is_portrait and has_voice_video:
                clip_w, clip_h = _effective_size(clip)
                if clip_w > clip_h or clip.get("is_image"):
                    return _split_screen_args(
                        piece,
                        clip,
                        voice_clip,
                        dst,
                        width=width,
                        height=height,
                        fps=fps,
                        encoder=encoder,
                        device=device,
                        polish=polish,
                    )
            elif not is_portrait and pip and has_voice_video:
                return _pip_args(
                    piece,
                    clip,
                    voice_clip,
                    dst,
                    width=width,
                    height=height,
                    fps=fps,
                    encoder=encoder,
                    device=device,
                    polish=polish,
                    studio_frame=studio_frame,
                )

    punch = piece["punch"]
    if is_portrait and not is_cover and not card:
        mid = float(piece["start"]) + float(piece["length"]) / 2
        p_crop = portrait_crop(clip, width, height, at=mid)
        if p_crop:
            punch = f"{p_crop},{punch}" if punch.startswith("perspective=") else p_crop

    cm = color_filter(clip.get("color_match"))
    if cm:
        punch = f"{punch},{cm}" if punch else cm

    length = piece["length"]
    fps_s = _fps(fps)
    picture = _picture_suffix(length, piece["fade_in"], piece["fade_out"]) if polish else ""

    if clip.get("is_image"):
        args = ["-y"]
        if encoder == "vaapi":
            args += ["-init_hw_device", f"vaapi=va:{device}", "-filter_hw_device", "va"]
        canvas_col, bezel_col, ratio = _studio_bg(studio_frame)
        inner_w = max(2, (int(width * ratio) // 2) * 2)
        inner_h = max(2, (int(height * ratio) // 2) * 2)
        bezel = f"pad=iw+6:ih+6:3:3:color={bezel_col}," if studio_frame != "none" else ""
        range_opts = ":in_range=pc:out_range=tv" if _full_range(clip) else ""
        fmt_tail = ",format=nv12,hwupload" if encoder == "vaapi" else ",format=yuv420p"
        graph = (
            f"[0:v]scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease{range_opts},"
            f"{bezel}pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={canvas_col},setsar=1,fps={fps_s},"
            f"{_ken_burns_expr(fps)}{picture}{fmt_tail}[v0]"
        )
        args += ["-loop", "1", "-framerate", fps_s, "-t", _num(length + 2.0 / fps + 0.05), "-i", clip["path"]]
        args += ["-filter_complex", graph, "-map", "[v0]", "-an", "-frames:v", str(piece["frames"])]
        args += [*encoder_args(encoder), "-bf", "0", "-video_track_timescale", "90000", dst]
        return args

    on_gpu = (
        encoder == "vaapi"
        and not punch
        and not live_overlay
        and not _rotated(clip)
        and _vaapi_decodable(clip)
    )
    args = ["-y"]
    if encoder == "vaapi":
        args += ["-init_hw_device", f"vaapi=va:{device}", "-filter_hw_device", "va"]
    if on_gpu:
        args += ["-hwaccel", "vaapi", "-hwaccel_device", str(device), "-hwaccel_output_format", "vaapi"]
    # A little more than the piece is read, and the frame count ends it exactly.
    # The seek lands a quarter frame early, so the frame at the cut is the first one read.
    seek = max(0.0, float(piece["start"]) - 0.25 / fps)
    span = _num(length + 2.0 / fps + 0.05)
    args += ["-ss", _num(seek), "-t", span, "-i", clip["path"]]
    if live_overlay:
        ov_png, piece_t0 = live_overlay
        args += ["-loop", "1", "-framerate", fps_s, "-t", span, "-i", ov_png]
        # Build base video on software frames, composite fading live title overlay, then upload if VAAPI.
        base = _video_filter(0, 0, clip, width, height, fps, fps_s, "x264", False, picture, punch)
        base = base.replace("[v0]", "[base]")
        end_local = max(0.0, LIVE_TITLE_END - piece_t0)
        ov_chain = (
            f"[1:v]format=rgba,"
            f"setpts=PTS+{piece_t0:.6f}/TB,"
            f"fade=t=in:st={LIVE_TITLE_IN:.3f}:d={LIVE_TITLE_FADE_IN:.3f}:alpha=1,"
            f"fade=t=out:st={LIVE_TITLE_OUT:.3f}:d={LIVE_TITLE_FADE_OUT:.3f}:alpha=1,"
            f"setpts=PTS-STARTPTS[ov]"
        )
        fmt_tail = ",format=nv12,hwupload" if encoder == "vaapi" else ",format=yuv420p"
        graph = f"{base};{ov_chain};[base][ov]overlay=0:0:shortest=1:enable='between(t,0,{end_local:.3f})'{fmt_tail}[v0]"
    else:
        graph = _video_filter(0, 0, clip, width, height, fps, fps_s, encoder, on_gpu, picture, punch)
    args += ["-filter_complex", graph, "-map", "[v0]", "-an", "-frames:v", str(piece["frames"])]
    # No frame looks ahead past the end of its own file, so the files join cleanly.
    args += [*encoder_args(encoder), "-bf", "0", "-video_track_timescale", "90000", dst]
    return args


def piece_key(
    piece: dict, clip: dict, args: list[str], extra_clips: list[dict] | None = None
) -> str:
    """A name for what this piece shows. The same source, range, and look is the same file."""
    stamps = []
    for item in [clip, *(extra_clips or [])]:
        try:
            info = os.stat(item["path"])
            stamps.append([info.st_size, info.st_mtime_ns])
        except OSError:
            stamps.append([0, 0])
    # The destination is the last argument and is named after this key, so it is left out.
    stamp_field = stamps[0] if len(stamps) == 1 else stamps
    text = json.dumps([stamp_field, args[:-1], piece["frames"]])
    return hashlib.sha1(text.encode()).hexdigest()[:20]


def render(
    segments: list[dict],
    clips: list[dict],
    dst: str,
    label: str,
    fail_prefix: str,
    *,
    encoder: str,
    device: str | None,
    polish: bool = True,
    scene_transition: str = "dip",
    covers=None,
    lines=None,
    broll_sound: str = "mix",
    clean_sound: bool = True,
    zoom: str = "off",
    close=None,
    angles=None,
    resolution: str = "source",
    aspect: str = "source",
    work_dir: str | None = None,
    pip: bool = False,
    music: str | None = None,
    studio_frame: str = "dark",
    live_title: str | None = None,
) -> dict:
    """Make the movie at `dst` and say how much of it was already made: {pieces, made}."""
    if not segments:
        raise SystemExit("No segments to render")
    width, height, fps = target_size(clips, resolution=resolution, aspect=aspect)
    work = work_dir or os.path.join(os.path.dirname(os.path.abspath(dst)), "work")
    store = os.path.join(work, "pieces")
    os.makedirs(store, exist_ok=True)
    placed = timeline(
        cut_pieces(
            segments,
            clips,
            polish=polish,
            scene_transition=scene_transition,
            covers=covers,
            lines=lines,
            zoom=zoom,
            close=close,
            angles=angles,
        ),
        fps,
    )
    if not placed:
        raise SystemExit("No segments to render")
    print(f"{label} 0%", flush=True)

    # Legacy working sound files from older versions go before this render starts.
    for name in os.listdir(work):
        if name.startswith("sound-") and name.endswith(".raw"):
            try:
                os.remove(os.path.join(work, name))
            except OSError:
                pass
    wav = os.path.join(work, "cut.wav")
    listing = os.path.join(work, "pieces.txt")
    sounds = Sounds(work, clips)
    try:
        # The sound first: it is quick, and a file that cannot be read stops the cut before the long part.
        needed_sound = {piece["voice_clip"] for piece in placed}
        if broll_sound == "mix":
            needed_sound.update(
                piece["clip"] for piece in placed if "voice" in piece and not piece.get("angle")
            )
        sounds.preload(needed_sound)
        try:
            write_wav(
                wav,
                mix(
                    placed,
                    clips,
                    sounds,
                    fps,
                    polish=polish,
                    scene_transition=scene_transition,
                    broll_sound=broll_sound,
                    level=clean_sound,
                    music=music,
                ),
            )
        finally:
            sounds.close()
        measured = measure(wav) if clean_sound else None

        overlay_png = None
        if live_title and str(live_title).strip():
            from botcut.thumb import make_live_overlay_png

            first_clip = clips[placed[0]["clip"]]
            first_face = first_clip.get("face")
            if not first_face and first_clip.get("faces"):
                # Convert nearest [at, cx, cy] into a face box for layout side detection.
                _t, fcx, fcy = first_clip["faces"][0]
                first_face = {"x": max(0.0, fcx - 0.1), "y": max(0.0, fcy - 0.12), "w": 0.2, "h": 0.24}
            ov_hash = hashlib.sha1(
                json.dumps([str(live_title).strip(), width, height, first_face]).encode("utf-8")
            ).hexdigest()[:12]
            overlay_png = os.path.join(work, f"live-title-{ov_hash}.png")
            make_live_overlay_png(
                width,
                height,
                str(live_title).strip(),
                face=first_face,
                dest=overlay_png,
            )

        jobs = []
        for piece in placed:
            clip = clips[piece["clip"]]
            piece_t0 = piece["at"] / fps
            piece_ov = (
                (overlay_png, piece_t0)
                if overlay_png and piece_t0 < LIVE_TITLE_END and not is_card(str(clip.get("path") or ""))
                else None
            )
            args = piece_args(
                piece,
                clip,
                "",
                width=width,
                height=height,
                fps=fps,
                encoder=encoder,
                device=device,
                polish=polish,
                clips=clips,
                pip=pip,
                studio_frame=studio_frame,
                live_overlay=piece_ov,
            )
            extra = (
                [clips[piece["voice_clip"]]]
                if (height > width or pip) and "voice" in piece and not piece.get("angle")
                else None
            )
            path = os.path.join(store, piece_key(piece, clip, args, extra_clips=extra) + ".mp4")
            jobs.append({"piece": piece, "args": [*args[:-1], path], "path": path})
        total_frames = sum(job["piece"]["frames"] for job in jobs)
        done_frames = 0
        lock = threading.Lock()
        last = [0]

        def advance(frames: int) -> None:
            nonlocal done_frames
            with lock:
                done_frames += frames
                # The last few percent are the join.
                percent = min(97, int(done_frames * 97 / max(1, total_frames)))
                if percent != last[0]:
                    last[0] = percent
                    print(f"{label} {percent}%", flush=True)

        todo = []
        seen: set[str] = set()
        now = time.time()
        for job in jobs:
            if job["path"] in seen:
                advance(job["piece"]["frames"])
                continue
            seen.add(job["path"])
            if os.path.isfile(job["path"]) and os.path.getsize(job["path"]) > 0:
                # Used again, so it is not one to clear out.
                os.utime(job["path"], (now, now))
                advance(job["piece"]["frames"])
            else:
                todo.append(job)

        active_procs: set[subprocess.Popen] = set()
        procs_lock = threading.Lock()

        def encode(job: dict) -> None:
            part = job["path"] + ".part.mp4"
            proc = subprocess.Popen(
                ["ffmpeg", "-loglevel", "error", "-nostats", *job["args"][:-1], part],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            with procs_lock:
                active_procs.add(proc)
            try:
                _out, stderr = proc.communicate()
            finally:
                with procs_lock:
                    active_procs.discard(proc)
            if proc.returncode != 0 or not os.path.isfile(part) or os.path.getsize(part) == 0:
                try:
                    os.remove(part)
                except OSError:
                    pass
                raise SystemExit(f"{fail_prefix}: {ffmpeg_error_detail(stderr or '')}")
            os.replace(part, job["path"])

        if todo:
            pool = ThreadPoolExecutor(max_workers=min(PIECE_WORKERS, len(todo)))
            waiting = {pool.submit(encode, job): job for job in todo}
            try:
                for future in as_completed(waiting):
                    future.result()
                    advance(waiting[future]["piece"]["frames"])
            except BaseException:
                with procs_lock:
                    for active in list(active_procs):
                        try:
                            active.terminate()
                        except OSError:
                            pass
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            else:
                pool.shutdown(wait=True)

        Path(listing).write_text(
            "".join("file '" + job["path"].replace("'", "'\\''") + "'\n" for job in jobs)
        )
        args = ["ffmpeg", "-y", "-loglevel", "error", "-nostats", "-f", "concat", "-safe", "0", "-i", listing, "-i", wav]
        args += ["-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"]
        if clean_sound:
            args += ["-af", _sound_chain(measured, False)]
        args += ["-c:a", "aac", "-ar", str(RATE), "-movflags", "+faststart", dst]
        proc = subprocess.run(args, capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(f"{fail_prefix}: {ffmpeg_error_detail(proc.stderr or '')}")
        print(f"{label} 100%", flush=True)
        _clear_out(store, seen, now)
        _clear_out(sounds.sound_dir, sounds.used, now)
        return {"pieces": len(seen), "made": len(todo), "seconds": total_frames / fps}
    finally:
        for leftover in (wav, listing):
            try:
                os.remove(leftover)
            except OSError:
                pass


def _clear_out(store: str, used: set[str], now: float, max_bytes: int | None = None) -> None:
    """Remove pieces no render has used for a while, anything left half written, and excess cache."""
    try:
        names = os.listdir(store)
    except OSError:
        return
    kept: list[tuple[float, int, str, bool]] = []
    total_size = 0
    for name in names:
        path = os.path.join(store, name)
        in_use = path in used
        try:
            info = os.stat(path)
        except OSError:
            continue
        if not in_use and (
            name.endswith(".part.mp4")
            or name.endswith(".part")
            or now - info.st_mtime > PIECE_KEEP_SECONDS
        ):
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        total_size += info.st_size
        kept.append((info.st_mtime, info.st_size, path, in_use))
    limit = _piece_cache_max_bytes() if max_bytes is None else max_bytes
    if limit > 0 and total_size > limit:
        for _mtime, size, path, in_use in sorted(kept, key=lambda item: item[0]):
            if in_use:
                continue
            try:
                os.remove(path)
                total_size -= size
            except OSError:
                continue
            if total_size <= limit:
                break
