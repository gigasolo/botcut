"""Line up two recordings of the same moment by their sound.

Two cameras running on one take hear the same room. The loudness of each,
taken a hundred times a second, rises and falls together, and the shift that
makes the two match best is how far apart the cameras were started. That is
found first, to a hundredth of a second, and then the waveforms themselves
are compared near it for the rest.

Nothing here asks a model. A match is a number, and a weak one is no match.
"""

from __future__ import annotations

import subprocess

RATE = 16000
HOP = 160
# How far the best shift stands above the rest, in standard deviations.
# Two takes of the same words are far below this. The same take is far above it.
SURE = 18.0
# What a person marked as another camera is believed on less.
LIKELY = 12.0
# The two have to share at least this much of the take.
OVERLAP_MIN = 5.0
# A fine match is looked for this far either side of the rough one.
REFINE_REACH = 0.08
REFINE_WINDOW = 8.0


def load(path: str):
    """A file's sound as 16 kHz mono samples, or None when it cannot be read."""
    import numpy as np

    proc = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", path, "-vn", "-map", "0:a:0",
            "-af", f"aresample={RATE}:async=1:first_pts=0", "-ac", "1", "-f", "s16le", "-",
        ],
        capture_output=True,
    )
    if proc.returncode != 0 or len(proc.stdout) < 2 * RATE:
        return None
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def envelope(samples):
    """How the loudness moves, a hundred times a second: only the rises, evened out."""
    import numpy as np

    count = len(samples) // HOP
    if count < 2:
        return np.zeros(0, dtype=np.float32)
    frames = samples[: count * HOP].reshape(count, HOP)
    level = np.log10(np.mean(frames * frames, axis=1) + 1e-9)
    rise = np.maximum(0.0, np.diff(level, prepend=level[0]))
    spread = float(rise.std())
    if spread <= 1e-9:
        return np.zeros(count, dtype=np.float32)
    return ((rise - rise.mean()) / spread).astype(np.float32)


def _correlate(a, b):
    """Every shift of b against a at once. Index k is b starting k steps after a; the far end wraps to before it."""
    import numpy as np

    size = 1
    while size < len(a) + len(b):
        size *= 2
    return np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size)), size), size


def rough(env_a, env_b) -> tuple[float, float]:
    """The shift of b that matches a best, in seconds, and how far it stands out.

    A positive shift means the same sound is later in a than in b: b's camera
    was started that much after a's.
    """
    import numpy as np

    if len(env_a) < 100 or len(env_b) < 100:
        return 0.0, 0.0
    found, size = _correlate(env_a, env_b)
    # Only shifts that leave the two overlapping are real.
    valid = np.concatenate([found[: len(env_a)], found[size - len(env_b) + 1 :]])
    spread = float(valid.std())
    if spread <= 1e-9:
        return 0.0, 0.0
    best = int(np.argmax(found))
    if len(env_a) <= best <= size - len(env_b):
        return 0.0, 0.0
    shift = best if best < len(env_a) else best - size
    # The peak is measured against the shifts away from it, so a wide peak does not flatter itself.
    away = np.ones(size, dtype=bool)
    for index in range(best - 20, best + 21):
        away[index % size] = False
    away[len(env_a) : size - len(env_b) + 1] = False
    rest = found[away]
    if len(rest) < 50:
        return shift * HOP / RATE, 0.0
    score = (float(found[best]) - float(rest.mean())) / max(1e-9, float(rest.std()))
    return shift * HOP / RATE, score


def fine(a, b, shift: float, at: float) -> float | None:
    """The shift near `shift` that matches the waveforms around `at` seconds of a, or None.

    The loud parts are flattened first, so one clap does not decide it.
    """
    import numpy as np

    count = int(REFINE_WINDOW * RATE)
    start_a = int(at * RATE)
    start_b = int((at - shift) * RATE)
    if start_a < 0 or start_b < 0 or start_a + count > len(a) or start_b + count > len(b):
        return None
    left, right = a[start_a : start_a + count], b[start_b : start_b + count]
    if float(np.abs(left).max()) < 1e-4 or float(np.abs(right).max()) < 1e-4:
        return None
    size = 2 * count
    cross = np.fft.rfft(left, size) * np.conj(np.fft.rfft(right, size))
    found = np.fft.irfft(cross / (np.abs(cross) + 1e-9), size)
    reach = int(REFINE_REACH * RATE)
    near = np.concatenate([found[-reach:], found[: reach + 1]])
    best = int(np.argmax(near))
    # A peak that barely clears the rest is noise.
    if float(near[best]) < 5 * float(np.abs(near).mean()):
        return None
    # A peak after the middle is the sound arriving later in a than the rough shift said.
    return shift + (best - reach) / RATE


def line_up(a, b, sure: float = SURE) -> dict | None:
    """How b sits against a: {offset, drift, score, start, end}, or None when they are not the same take.

    A moment t seconds into a is at t + offset + drift * t in b. `start` and
    `end` are the stretch of a that b also has.
    """
    import numpy as np

    shift, score = rough(envelope(a), envelope(b))
    if score < sure:
        return None
    start = max(0.0, shift)
    end = min(len(a) / RATE, shift + len(b) / RATE)
    if end - start < OVERLAP_MIN:
        return None
    points = []
    room = end - start - REFINE_WINDOW
    if room > 0:
        for share in (0.1, 0.3, 0.5, 0.7, 0.9):
            at = start + room * share
            found = fine(a, b, shift, at)
            if found is not None:
                points.append((at + REFINE_WINDOW / 2, found))
    drift = 0.0
    if len(points) >= 3 and points[-1][0] - points[0][0] > 60:
        # Two cameras rarely run at exactly the same speed. Over a long take it shows.
        slope, base = np.polyfit([p[0] for p in points], [p[1] for p in points], 1)
        if abs(slope) < 1e-3 and abs(slope) * (end - start) > 0.01:
            drift, shift = float(slope), float(base)
        else:
            shift = float(np.median([p[1] for p in points]))
    elif points:
        shift = float(np.median([p[1] for p in points]))
    # In a's time: b's own clock reads t - shift, and slips by drift a second.
    return {
        "offset": round(-shift, 4),
        "drift": round(-drift, 7),
        "score": round(score, 1),
        "start": round(max(0.0, shift), 3),
        "end": round(end, 3),
    }
