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

from botcut.media import (
    _fps,
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
    frame_size,
    level_gain,
    parse_loudness,
)

RATE = 48000
# How far each side of a join inside a shot reaches into the other. The two
# overlap for twice this, one fading down as the other comes up.
CROSS = 0.012
# A B-roll shot's own sound, under the voice.
BED = 0.25
BED_FADE = 0.03
# Pieces encoded at once. Each ffmpeg already uses several cores.
PIECE_WORKERS = 3
# A piece nothing has used for this long is removed.
PIECE_KEEP_SECONDS = 2 * 24 * 3600


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
    """Each file's sound, read once at 48 kHz stereo and kept on disk while the cut is built."""

    def __init__(self, work: str, clips: list[dict]) -> None:
        self._work = work
        self._clips = clips
        self._open: dict[int, object] = {}
        self._paths: list[str] = []

    def of(self, index: int):
        """The samples of one clip as an array of frames by two, or None when it has no sound."""
        import numpy as np

        if index in self._open:
            return self._open[index]
        clip = self._clips[index]
        found = None
        if clip.get("audio", True):
            path = os.path.join(self._work, f"sound-{index}.raw")
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error", "-i", clip["path"], "-vn", "-map", "0:a:0",
                    # Sample 0 is the start of the file, even when the sound track starts late.
                    "-af", f"aresample={RATE}:async=1:first_pts=0",
                    "-ac", "2", "-f", "s16le", path,
                ],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise SystemExit(
                    f"Could not read the sound of {os.path.basename(clip['path'])}: "
                    f"{ffmpeg_error_detail(proc.stderr or '')}"
                )
            self._paths.append(path)
            if os.path.getsize(path) >= 4:
                found = np.memmap(path, dtype=np.int16, mode="r").reshape(-1, 2)
        self._open[index] = found
        return found

    def close(self) -> None:
        self._open.clear()
        for path in self._paths:
            try:
                os.remove(path)
            except OSError:
                pass


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
) -> list[str]:
    """ffmpeg arguments that encode one piece of picture, with no sound, to its own file."""
    punch = piece["punch"]
    on_gpu = encoder == "vaapi" and not punch and not _rotated(clip) and _vaapi_decodable(clip)
    args = ["-y"]
    if encoder == "vaapi":
        args += ["-init_hw_device", f"vaapi=va:{device}", "-filter_hw_device", "va"]
    if on_gpu:
        args += ["-hwaccel", "vaapi", "-hwaccel_device", str(device), "-hwaccel_output_format", "vaapi"]
    length = piece["length"]
    picture = _picture_suffix(length, piece["fade_in"], piece["fade_out"]) if polish else ""
    graph = _video_filter(0, 0, clip, width, height, fps, _fps(fps), encoder, on_gpu, picture, punch)
    # A little more than the piece is read, and the frame count ends it exactly.
    # The seek lands a quarter frame early, so the frame at the cut is the first one read.
    seek = max(0.0, float(piece["start"]) - 0.25 / fps)
    args += ["-ss", _num(seek), "-t", _num(length + 2.0 / fps + 0.05), "-i", clip["path"]]
    args += ["-filter_complex", graph, "-map", "[v0]", "-an", "-frames:v", str(piece["frames"])]
    # No frame looks ahead past the end of its own file, so the files join cleanly.
    args += [*encoder_args(encoder), "-bf", "0", "-video_track_timescale", "90000", dst]
    return args


def piece_key(piece: dict, clip: dict, args: list[str]) -> str:
    """A name for what this piece shows. The same source, range, and look is the same file."""
    try:
        info = os.stat(clip["path"])
        stamp = [info.st_size, info.st_mtime_ns]
    except OSError:
        stamp = [0, 0]
    # The destination is the last argument and is named after this key, so it is left out.
    text = json.dumps([stamp, args[:-1], piece["frames"]])
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
) -> dict:
    """Make the movie at `dst` and say how much of it was already made: {pieces, made}."""
    if not segments:
        raise SystemExit("No segments to render")
    width, height, fps = frame_size(clips)
    work = os.path.join(os.path.dirname(os.path.abspath(dst)), "work")
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

    # The sound first: it is quick, and a file that cannot be read stops the cut before the long part.
    wav = os.path.join(work, "cut.wav")
    sounds = Sounds(work, clips)
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
            ),
        )
    finally:
        sounds.close()
    measured = measure(wav) if clean_sound else None

    jobs = []
    for piece in placed:
        clip = clips[piece["clip"]]
        args = piece_args(
            piece, clip, "", width=width, height=height, fps=fps, encoder=encoder, device=device, polish=polish
        )
        path = os.path.join(store, piece_key(piece, clip, args) + ".mp4")
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

    def encode(job: dict) -> None:
        part = job["path"] + ".part.mp4"
        proc = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-nostats", *job["args"][:-1], part],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not os.path.isfile(part) or os.path.getsize(part) == 0:
            try:
                os.remove(part)
            except OSError:
                pass
            raise SystemExit(f"{fail_prefix}: {ffmpeg_error_detail(proc.stderr or '')}")
        os.replace(part, job["path"])

    if todo:
        with ThreadPoolExecutor(max_workers=min(PIECE_WORKERS, len(todo))) as pool:
            waiting = {pool.submit(encode, job): job for job in todo}
            try:
                for future in as_completed(waiting):
                    future.result()
                    advance(waiting[future]["piece"]["frames"])
            except BaseException:
                pool.shutdown(wait=False, cancel_futures=True)
                raise

    listing = os.path.join(work, "pieces.txt")
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
    for leftover in (wav, listing):
        try:
            os.remove(leftover)
        except OSError:
            pass
    _clear_out(store, seen, now)
    return {"pieces": len(seen), "made": len(todo), "seconds": total_frames / fps}


def _clear_out(store: str, used: set[str], now: float) -> None:
    """Remove pieces no render has used for a while, and anything left half written."""
    try:
        names = os.listdir(store)
    except OSError:
        return
    for name in names:
        path = os.path.join(store, name)
        if path in used:
            continue
        try:
            if name.endswith(".part.mp4") or now - os.path.getmtime(path) > PIECE_KEEP_SECONDS:
                os.remove(path)
        except OSError:
            continue
