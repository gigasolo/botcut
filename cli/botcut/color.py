"""Automatic color and exposure matching between cameras on the same take.

Two different cameras (or lenses/lighting angles) rarely match out of the box.
Since sync.py aligns Camera B to Camera A to the frame, we sample paired frames
across their overlap and compute gentle exposure, contrast, saturation, and
white-balance corrections so cuts between angles look cohesive.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from botcut.angles import angle_time, groups
from botcut.media import cached_still

# Sample points across the shared overlap between main and angle cameras.
SAMPLE_SHARES = (0.2, 0.5, 0.8)
# Gentle clamps so automatic matching never creates harsh artifacts or clipping.
MAX_BRIGHTNESS = 0.12
MIN_CONTRAST = 0.85
MAX_CONTRAST = 1.18
MIN_SAT = 0.85
MAX_SAT = 1.18
MAX_BALANCE = 0.12
# Deltas smaller than this are left alone (no filter needed).
DEADBAND = 0.015


def _frame_stats(image_path: str) -> dict | None:
    """Mean/std luminance, HSV saturation, and RGB channel means in [0, 1]."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    if not os.path.isfile(image_path):
        return None
    bgr = cv2.imread(image_path)
    if bgr is None or bgr.size == 0:
        return None
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32) / 255.0
    luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    return {
        "luma_mean": float(np.mean(luma)),
        "luma_std": float(np.std(luma)),
        "sat_mean": float(np.mean(hsv[:, :, 1])),
        "r_mean": float(np.mean(rgb[:, :, 0])),
        "g_mean": float(np.mean(rgb[:, :, 1])),
        "b_mean": float(np.mean(rgb[:, :, 2])),
    }


def compute_match(ref_samples: list[dict], cam_samples: list[dict]) -> dict | None:
    """Compute gentle eq + colorbalance parameters that bring `cam` closer to `ref`."""
    import numpy as np

    if not ref_samples or not cam_samples:
        return None
    ref_l = float(np.median([s["luma_mean"] for s in ref_samples]))
    cam_l = float(np.median([s["luma_mean"] for s in cam_samples]))
    ref_std = float(np.median([s["luma_std"] for s in ref_samples]))
    cam_std = float(np.median([s["luma_std"] for s in cam_samples]))
    ref_sat = float(np.median([s["sat_mean"] for s in ref_samples]))
    cam_sat = float(np.median([s["sat_mean"] for s in cam_samples]))

    brightness = max(-MAX_BRIGHTNESS, min(MAX_BRIGHTNESS, ref_l - cam_l))
    contrast = max(MIN_CONTRAST, min(MAX_CONTRAST, ref_std / max(0.05, cam_std)))
    saturation = max(MIN_SAT, min(MAX_SAT, ref_sat / max(0.05, cam_sat)))

    # Midtone white-balance delta: shift each channel relative to overall luma shift.
    ref_rgb = np.array([
        float(np.median([s["r_mean"] for s in ref_samples])),
        float(np.median([s["g_mean"] for s in ref_samples])),
        float(np.median([s["b_mean"] for s in ref_samples])),
    ])
    cam_rgb = np.array([
        float(np.median([s["r_mean"] for s in cam_samples])),
        float(np.median([s["g_mean"] for s in cam_samples])),
        float(np.median([s["b_mean"] for s in cam_samples])),
    ])
    # Normalize each camera by its own mean RGB so white balance is decoupled from exposure.
    ref_norm = ref_rgb / max(0.05, float(ref_rgb.mean()))
    cam_norm = cam_rgb / max(0.05, float(cam_rgb.mean()))
    wb = np.clip((ref_norm - cam_norm) * 0.6, -MAX_BALANCE, MAX_BALANCE)

    out = {
        "brightness": round(float(brightness), 3),
        "contrast": round(float(contrast), 3),
        "saturation": round(float(saturation), 3),
        "rm": round(float(wb[0]), 3),
        "gm": round(float(wb[1]), 3),
        "bm": round(float(wb[2]), 3),
    }
    if not color_filter(out):
        return None
    return out


def color_filter(match: dict | None) -> str:
    """Turn a color_match dict into an ffmpeg filter chain, or empty string when negligible."""
    if not isinstance(match, dict):
        return ""
    try:
        b = float(match.get("brightness") or 0.0)
        c = float(match.get("contrast") or 1.0)
        s = float(match.get("saturation") or 1.0)
        rm = float(match.get("rm") or 0.0)
        gm = float(match.get("gm") or 0.0)
        bm = float(match.get("bm") or 0.0)
    except (TypeError, ValueError):
        return ""
    parts: list[str] = []
    if abs(b) >= DEADBAND or abs(c - 1.0) >= DEADBAND or abs(s - 1.0) >= DEADBAND:
        parts.append(f"eq=brightness={b:.3f}:contrast={c:.3f}:saturation={s:.3f}")
    if max(abs(rm), abs(gm), abs(bm)) >= DEADBAND:
        parts.append(f"colorbalance=rm={rm:.3f}:gm={gm:.3f}:bm={bm:.3f}")
    return ",".join(parts)


def match_cameras(work: str, clips: list[dict]) -> None:
    """Compute and cache color_match for every second camera against its main camera."""
    if os.environ.get("BOTCUT_FAKE") == "1":
        return
    by_main = groups(clips)
    if not by_main:
        return
    os.makedirs(work, exist_ok=True)
    stills = os.path.join(work, "stills")
    os.makedirs(stills, exist_ok=True)
    cache_path = os.path.join(work, "color_match.json")
    try:
        cache = json.loads(Path(cache_path).read_text())
    except (OSError, ValueError):
        cache = {}
    if not isinstance(cache, dict):
        cache = {}
    changed = False

    def _stamp(path: str) -> list:
        try:
            info = os.stat(path)
            return [os.path.abspath(path), info.st_size, info.st_mtime_ns]
        except OSError:
            return [os.path.abspath(path), 0, 0]

    for main_idx, cam_list in by_main.items():
        main_clip = clips[main_idx]
        main_dur = float(main_clip.get("duration") or 0)
        if main_dur <= 0:
            continue
        for cam_idx in cam_list:
            cam_clip = clips[cam_idx]
            cam_dur = float(cam_clip.get("duration") or 0)
            if cam_dur <= 0:
                continue
            key = f"{main_idx}:{cam_idx}"
            stamps = [_stamp(main_clip["path"]), _stamp(cam_clip["path"]), cam_clip.get("offset", 0.0)]
            entry = cache.get(key)
            if isinstance(entry, dict) and entry.get("stamps") == stamps:
                if entry.get("match"):
                    cam_clip["color_match"] = entry["match"]
                continue
            # Shared overlap in main_clip's time.
            offset = float(cam_clip.get("offset") or 0.0)
            low = max(0.0, -offset)
            high = min(main_dur, cam_dur - offset)
            if high - low < 1.0:
                continue
            ref_stats = []
            cam_stats = []
            for idx, share in enumerate(SAMPLE_SHARES):
                t_main = low + (high - low) * share
                t_cam = angle_time(cam_clip, t_main)
                if t_cam < 0 or t_cam > cam_dur:
                    continue
                ref_img = os.path.join(stills, f"cm-ref-{main_idx}-{cam_idx}-{idx}.jpg")
                cam_img = os.path.join(stills, f"cm-cam-{main_idx}-{cam_idx}-{idx}.jpg")
                if cached_still(main_clip["path"], t_main, ref_img) and cached_still(cam_clip["path"], t_cam, cam_img):
                    rs = _frame_stats(ref_img)
                    cs = _frame_stats(cam_img)
                    if rs and cs:
                        ref_stats.append(rs)
                        cam_stats.append(cs)
            found = compute_match(ref_stats, cam_stats)
            cache[key] = {"stamps": stamps, "match": found}
            changed = True
            if found:
                cam_clip["color_match"] = found

    if changed:
        try:
            Path(cache_path).write_text(json.dumps(cache, indent=2) + "\n")
        except OSError:
            pass
