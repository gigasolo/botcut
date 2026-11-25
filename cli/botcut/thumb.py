"""Minimal photo-overlay title cards and video thumbnails (Matt-style).

Picks an engaging frame from the video where the speaker is sharp and well-lit,
re-composes them onto a rule-of-thirds side when centered, applies a soft
directional dark scrim behind the text side only, and renders crisp white
geometric typography (brand/logo, large title, quiet date/subtitle) as a
thumbnail JPEG, MP4 cover art, or 3-second opening title card.
"""

from __future__ import annotations

import datetime
import html
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from botcut.brand import hex_to_ass, load_brand
from botcut.card import is_card
from botcut.frame import find_face
from botcut.media import cached_still, ffmpeg_error_detail


FRAME_PICK_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "best_frame",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["index"],
            "properties": {"index": {"type": "integer"}},
        },
    },
}

FRAME_PICK_PROMPT = (
    "You are a photo editor picking the single most flattering thumbnail frame of a speaker for a minimal title card. "
    "STRICTLY REJECT any frame where the speaker is mid-syllable, has an open or awkward mouth, tongue visible, "
    "blinking or half-closed eyes, looking down/away, or motion blur. "
    "Strongly prefer a relaxed closed-mouth expression or warm natural smile with eyes open and looking toward the camera, "
    "and clean space on one side for white title text. Return only its 0-based index."
)


def _detect_face_landmarks(image_path: str) -> tuple[dict | None, float]:
    """Return (face_box, pose_bonus) using YuNet landmarks (rewards front-facing, level eyes, high confidence)."""
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    try:
        import cv2
    except ImportError:
        return find_face(image_path), 0.0
    from botcut.frame import _DETECTOR, _MODEL, parse_face

    if not os.path.isfile(_MODEL) or not os.path.isfile(image_path):
        return find_face(image_path), 0.0
    image = cv2.imread(image_path)
    if image is None or image.size == 0:
        return None, 0.0
    height, width = image.shape[:2]
    try:
        detector = getattr(_DETECTOR, "yunet", None)
        if detector is None:
            detector = cv2.FaceDetectorYN.create(_MODEL, "", (width, height), 0.7, 0.3, 20)
            _DETECTOR.yunet = detector
        else:
            detector.setInputSize((width, height))
        _count, faces = detector.detect(image)
    except cv2.error:
        return None, 0.0
    if faces is None or not len(faces):
        return None, 0.0
    best = max(faces, key=lambda f: f[2] * f[3])
    x, y, w, h = (float(v) for v in best[:4])
    x, y = max(0.0, x), max(0.0, y)
    w, h = min(w, width - x), min(h, height - y)
    box = parse_face({"found": True, "x": x / width, "y": y / height, "w": w / width, "h": h / height})
    if not box:
        return None, 0.0
    pose_bonus = 0.0
    if len(best) >= 15:
        re_x, re_y, le_x, le_y, nose_x = (float(v) for v in best[4:9])
        conf = float(best[14])
        eye_span = abs(le_x - re_x)
        if eye_span > 1.0:
            # Level eyes + nose centered between eyes = looking directly at camera.
            tilt = abs(le_y - re_y) / eye_span
            nose_center = abs(((re_x + le_x) / 2.0) - nose_x) / eye_span
            if tilt < 0.14:
                pose_bonus += 8.0
            if nose_center < 0.22:
                pose_bonus += 10.0
        if conf >= 0.88:
            pose_bonus += 8.0
    return box, pose_bonus


def _quiet_moments(video: str, duration: float, limit: int = 10) -> list[float]:
    """Find silent/pause midpoints in `video` where the speaker is not mid-syllable."""
    from botcut.media import parse_silences

    if duration <= 2.0:
        return [max(0.0, duration * 0.5)]
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-nostats",
                "-i", video, "-vn",
                "-af", "silencedetect=n=-30dB:d=0.35",
                "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=25,
        )
        pairs = parse_silences(proc.stderr or "", duration) if proc.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        pairs = []
    # Skip the very first/last 1.5s (hitting record/stop) and pick pause midpoints.
    mids = [
        (s + e) / 2.0
        for s, e in pairs
        if (e - s) >= 0.35 and 1.5 <= (s + e) / 2.0 <= max(1.6, duration - 1.5)
    ]
    if len(mids) >= 3:
        step = max(1, len(mids) // limit)
        return mids[::step][:limit]
    # Fallback: sample evenly across the body of the clip.
    return [duration * share for share in (0.10, 0.20, 0.30, 0.42, 0.54, 0.66, 0.78, 0.88)]


def score_frame(image_path: str) -> dict | None:
    """Score a candidate still for sharpness, pleasant exposure, clear face framing, and front-facing pose."""
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
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(np.mean(gray)) / 255.0
    face, pose_bonus = _detect_face_landmarks(image_path)

    score = min(30.0, sharpness / 12.0) + pose_bonus
    if 0.22 <= brightness <= 0.80:
        score += 15.0
    if face:
        area = float(face["w"]) * float(face["h"])
        cx = float(face["x"]) + float(face["w"]) / 2.0
        score += 40.0
        if 0.02 <= area <= 0.35:
            score += 15.0
        if cx < 0.42 or cx > 0.58:
            score += 10.0
    return {
        "score": round(score, 2),
        "face": face,
        "sharpness": round(sharpness, 2),
        "brightness": round(brightness, 3),
    }


def _grab_full_frame(video: str, at: float, dest: str) -> bool:
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{max(0.0, at):.3f}",
            "-i", video,
            "-frames:v", "1",
            "-q:v", "2",
            dest,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0


def _ask_best_frame(candidates: list[dict]) -> int | None:
    if os.environ.get("BOTCUT_FAKE") == "1" or not os.environ.get("XAI_API_KEY"):
        return None
    from botcut.llm import ask
    from botcut.pick import _jpeg_data_url

    content: list[dict] = [{"type": "text", "text": FRAME_PICK_PROMPT}]
    for idx, item in enumerate(candidates):
        if os.path.isfile(item["still"]):
            content.append({"type": "text", "text": f"Frame {idx}:"})
            content.append({"type": "image_url", "image_url": {"url": _jpeg_data_url(item["still"])}})
    if len(content) <= 1:
        return None
    try:
        chosen = ask(
            [{"role": "user", "content": content}],
            FRAME_PICK_SCHEMA,
            what="a thumbnail frame",
            parse=lambda p: int(p["index"]),
            read_timeout=60,
        )
        return chosen if 0 <= chosen < len(candidates) else None
    except (SystemExit, ValueError, TypeError):
        return None


def pick_best_frame(
    clips: list[dict],
    lines: list[dict] | None,
    work: str,
    *,
    use_ai: bool = True,
) -> dict:
    """Choose the best frame across kept spoken lines (or first spoken clip) for a photo title card."""
    stills_dir = os.path.join(work, "stills")
    os.makedirs(stills_dir, exist_ok=True)
    candidates: list[dict] = []

    kept = [
        line for line in (lines or [])
        if isinstance(line, dict)
        and line.get("keep")
        and str(line.get("reason") or "") != "card"
    ]
    if kept:
        # Prefer pause moments right after a kept line ends (mouth closed/relaxed, not mid-word).
        step = max(1, len(kept) // 10)
        for idx_k, line in enumerate(kept[::step][:10]):
            try:
                cidx = int(line["clip"])
                end_t = float(line["end"])
                start_t = float(line["start"])
                uid = int(line["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= cidx < len(clips)):
                continue
            clip = clips[cidx]
            dur = float(clip.get("duration") or 0.0)
            at = min(dur - 0.1, end_t + 0.15) if dur > end_t + 0.25 else max(0.0, start_t - 0.12)
            still = os.path.join(stills_dir, f"thumb-pause-{uid}.jpg")
            if cached_still(clip["path"], at, still):
                stats = score_frame(still)
                if stats:
                    candidates.append({"clip": cidx, "path": clip["path"], "at": at, "still": still, **stats})

    if not candidates:
        for idx, clip in enumerate(clips):
            path = str(clip.get("path") or "")
            if is_card(path) or str(clip.get("role") or "") in ("broll", "angle") or clip.get("is_image"):
                continue
            dur = max(0.0, float(clip.get("duration") or 0.0))
            for k, at in enumerate(_quiet_moments(path, dur, limit=10)):
                still = os.path.join(stills_dir, f"thumb-cand-{idx}-{k}.jpg")
                if cached_still(path, at, still):
                    stats = score_frame(still)
                    if stats:
                        candidates.append({"clip": idx, "path": path, "at": at, "still": still, **stats})
            if candidates:
                break

    if not candidates:
        raise SystemExit("No video frame available for the thumbnail")

    candidates.sort(key=lambda item: -item["score"])
    winner = candidates[0]
    if use_ai and len(candidates) >= 2:
        top = candidates[:6]
        ai_idx = _ask_best_frame(top)
        if ai_idx is not None:
            winner = top[ai_idx]
    return winner


def _prepare_canvas(
    frame_path: str,
    width: int,
    height: int,
    face: dict | None,
    logo_path: str = "",
) -> tuple[str, str]:
    """Scale/recompose frame, apply directional dark scrim, composite logo, return (png_path, text_side)."""
    import cv2
    import numpy as np

    bgr = cv2.imread(frame_path)
    if bgr is None or bgr.size == 0:
        raise SystemExit(f"Could not read frame: {frame_path}")
    src_h, src_w = bgr.shape[:2]
    cx = (float(face["x"]) + float(face["w"]) / 2.0) if isinstance(face, dict) else 0.5
    cy = (float(face["y"]) + float(face["h"]) / 2.0) if isinstance(face, dict) else 0.38

    portrait = height > width
    # Gently shift centered speakers onto the right third in landscape so left title text has clean space.
    if not portrait and 0.38 <= cx <= 0.62 and src_w >= 640:
        zoom = 1.18
        crop_w = int(round(src_w / zoom))
        crop_h = int(round(src_h / zoom))
        # Place face at ~0.70 of the cropped width.
        left = int(round(cx * src_w - 0.70 * crop_w))
        left = max(0, min(src_w - crop_w, left))
        top = int(round(cy * src_h - 0.40 * crop_h))
        top = max(0, min(src_h - crop_h, top))
        bgr = bgr[top : top + crop_h, left : left + crop_w]
        cx = (cx * src_w - left) / max(1, crop_w)

    # Cover-scale to target (width, height).
    scale = max(width / bgr.shape[1], height / bgr.shape[0])
    new_w = max(width, int(round(bgr.shape[1] * scale)))
    new_h = max(height, int(round(bgr.shape[0] * scale)))
    resized = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    x0 = max(0, min(new_w - width, int(round(cx * new_w - (0.5 if portrait else cx) * width))))
    y0 = max(0, min(new_h - height, (new_h - height) // 2))
    canvas = resized[y0 : y0 + height, x0 : x0 + width].astype(np.float32)

    text_side = "left" if cx >= 0.45 else "right"
    if portrait:
        # In portrait, soft bottom-up gradient scrim for lower-third title placement.
        t = np.linspace(0.0, 1.0, height, dtype=np.float32)
        ramp = np.clip((t - 0.38) / 0.62, 0.0, 1.0)
        alpha = 0.62 * (0.5 - 0.5 * np.cos(np.pi * ramp))
        canvas *= (1.0 - alpha[:, None, None])
    else:
        # Directional horizontal scrim: 58% dark on text side, 0% over speaker's face.
        t = np.linspace(0.0, 1.0, width, dtype=np.float32)
        if text_side == "left":
            ramp = np.clip((0.64 - t) / 0.64, 0.0, 1.0)
        else:
            ramp = np.clip((t - 0.36) / 0.64, 0.0, 1.0)
        alpha = 0.58 * (0.5 - 0.5 * np.cos(np.pi * ramp))
        canvas *= (1.0 - alpha[None, :, None])

    out_bgr = np.clip(canvas, 0, 255).astype(np.uint8)

    # Composite optional PNG logo cleanly in the top corner of the text zone.
    if logo_path and os.path.isfile(logo_path):
        logo = cv2.imread(logo_path, cv2.IMREAD_UNCHANGED)
        if logo is not None and logo.size > 0:
            target_lh = max(36, int(height * 0.065))
            lh, lw = logo.shape[:2]
            new_lw = max(1, int(round(lw * target_lh / lh)))
            logo = cv2.resize(logo, (new_lw, target_lh), interpolation=cv2.INTER_AREA)
            margin_x = int(width * 0.065)
            margin_y = int(height * 0.11)
            lx = margin_x if text_side == "left" else max(0, width - margin_x - new_lw)
            ly = margin_y
            if ly + target_lh <= height and lx + new_lw <= width:
                if logo.shape[2] == 4:
                    a = (logo[:, :, 3:4].astype(np.float32) / 255.0)
                    roi = out_bgr[ly : ly + target_lh, lx : lx + new_lw].astype(np.float32)
                    blended = roi * (1.0 - a) + logo[:, :, :3].astype(np.float32) * a
                    out_bgr[ly : ly + target_lh, lx : lx + new_lw] = np.clip(blended, 0, 255).astype(np.uint8)
                else:
                    out_bgr[ly : ly + target_lh, lx : lx + new_lw] = logo[:, :, :3]

    handle, png_path = tempfile.mkstemp(prefix="botcut-thumb-canvas-", suffix=".png")
    os.close(handle)
    cv2.imwrite(png_path, out_bgr)
    return png_path, text_side


def _esc(text: str) -> str:
    return str(text).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _build_overlay_ass(
    width: int,
    height: int,
    *,
    title: str,
    subtitle: str,
    brand_name: str,
    text_side: str,
    has_logo: bool,
    font: str,
    text_color: str,
) -> str:
    portrait = height > width
    white = hex_to_ass(text_color)
    muted = hex_to_ass(text_color, alpha=0x26)
    none = "&H00000000&"

    # Clean geometric sans-serif sizes proportioned to canvas (Matt-style editorial hierarchy).
    brand_size = max(32, int(round(height * (0.032 if portrait else 0.072))))
    title_size = max(56, int(round(height * (0.082 if portrait else 0.215))))
    sub_size = max(24, int(round(height * (0.024 if portrait else 0.044))))

    margin_x = int(width * 0.062)
    align = 7 if (portrait or text_side == "left") else 9
    anchor_x = margin_x if align == 7 else (width - margin_x)
    brand_x = anchor_x + (int(height * 0.085) if (has_logo and align == 7) else 0)
    brand_y = int(height * (0.58 if portrait else 0.105))
    title_y = int(height * (0.65 if portrait else 0.255))
    sub_y = int(height * (0.89 if portrait else 0.855))

    wrapped = textwrap.wrap(" ".join(title.split()), width=9 if not portrait else 14)[:3]
    title_lines = r"\N".join(_esc(line) for line in wrapped)

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Brand,{font},{brand_size},{white},{white},{none},{none},-1,0,0,0,100,100,-1,0,1,0,0,{align},0,0,0,1",
        f"Style: Title,{font},{title_size},{white},{white},{none},{none},0,0,0,0,100,100,-3,0,1,0,0,{align},0,0,0,1",
        f"Style: Sub,{font},{sub_size},{muted},{muted},{none},{none},0,0,0,0,100,100,0,0,1,0,0,{align},0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if brand_name.strip():
        lines.append(
            f"Dialogue: 0,0:00:00.00,0:00:10.00,Brand,,0,0,0,,{{\\an{align}\\pos({brand_x},{brand_y})}}{_esc(brand_name.strip())}"
        )
    if title_lines:
        lines.append(
            f"Dialogue: 0,0:00:00.00,0:00:10.00,Title,,0,0,0,,{{\\an{align}\\pos({anchor_x},{title_y})}}{title_lines}"
        )
    if subtitle.strip():
        lines.append(
            f"Dialogue: 0,0:00:00.00,0:00:10.00,Sub,,0,0,0,,{{\\an{align}\\pos({anchor_x},{sub_y})}}{_esc(subtitle.strip())}"
        )
    return "\n".join(lines) + "\n"


def _resolve_font(requested: str) -> str:
    """Resolve `requested` font; fall back from Inter -> Adwaita Sans (Inter variable font on Linux)."""
    name = (requested or "Inter").strip()
    if shutil.which("fc-list"):
        try:
            proc = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=5)
            families = {line.strip().lower() for line in (proc.stdout or "").splitlines() if line.strip()}
            if name.lower() in families:
                return name
            for fallback in ("Adwaita Sans", "Inter", "Plus Jakarta Sans", "Geist", "Noto Sans", "Liberation Sans"):
                if fallback.lower() in families:
                    return fallback
        except (OSError, subprocess.TimeoutExpired):
            pass
    return name


def _smart_typography(text: str) -> str:
    """Upgrade straight apostrophes and double hyphens to typographic punctuation."""
    s = " ".join(str(text or "").split())
    s = s.replace("'", "\u2019").replace("--", "\u2014")
    return s


def _balanced_wrap(text: str, max_chars: int, max_lines: int = 3) -> list[str]:
    """Wrap `text` into visually balanced lines (avoiding awkward orphan words)."""
    words = text.split()
    if not words:
        return []
    if len(text) <= max_chars:
        return [text]
    raw = textwrap.wrap(text, width=max_chars, break_long_words=False, break_on_hyphens=False)
    if len(raw) <= max_lines:
        # If 2 lines and the second line is much shorter than the first, try balancing near the midpoint.
        if len(raw) == 2 and len(words) >= 2:
            best = raw
            best_diff = abs(len(raw[0]) - len(raw[1]))
            for split in range(1, len(words)):
                a = " ".join(words[:split])
                b = " ".join(words[split:])
                if max(len(a), len(b)) <= max_chars + 2:
                    diff = abs(len(a) - len(b))
                    if diff < best_diff:
                        best_diff = diff
                        best = [a, b]
            return best
        return raw
    return raw[:max_lines]


def _render_svg_overlay(
    width: int,
    height: int,
    *,
    title: str,
    subtitle: str,
    brand_name: str,
    text_side: str,
    has_logo: bool,
    font: str,
    text_color: str,
) -> str | None:
    """Render crisp, sub-pixel anti-aliased Swiss typography to a transparent PNG via rsvg-convert."""
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        return None
    portrait = height > width
    title_clean = _smart_typography(title)
    sub_clean = _smart_typography(subtitle)
    brand_clean = _smart_typography(brand_name)

    # Dynamic editorial type scale based on title length.
    n = len(title_clean)
    if portrait:
        if n <= 14:
            title_size, max_chars = int(width * 0.135), 11
        elif n <= 28:
            title_size, max_chars = int(width * 0.102), 14
        else:
            title_size, max_chars = int(width * 0.082), 17
        brand_size = int(width * 0.052)
        sub_size = int(width * 0.036)
    else:
        if n <= 14:
            title_size, max_chars = int(height * 0.205), 8
        elif n <= 26:
            title_size, max_chars = int(height * 0.132), 13
        else:
            title_size, max_chars = int(height * 0.098), 18
        brand_size = int(height * 0.062)
        sub_size = int(height * 0.039)

    title_lines = _balanced_wrap(title_clean, max_chars=max_chars, max_lines=3)
    line_height = round(title_size * (0.98 if n <= 14 else 1.06))
    letter_spacing = round(-title_size * 0.028, 2)

    margin_x = int(width * 0.0625)
    left_aligned = portrait or text_side == "left"
    anchor = "start" if left_aligned else "end"
    anchor_x = margin_x if left_aligned else (width - margin_x)
    logo_offset = int(height * 0.078) if (has_logo and not portrait) else 0
    brand_x = (anchor_x + logo_offset) if left_aligned else (anchor_x - logo_offset)

    # Vertical grid matching Matt's layout: top brand, optically centered headline, quiet bottom date.
    if portrait:
        brand_y = int(height * 0.56)
        block_h = line_height * max(1, len(title_lines))
        title_start_y = int(height * 0.62) + int(title_size * 0.82)
        sub_y = min(int(height * 0.91), title_start_y + block_h + int(height * 0.035))
    else:
        brand_y = int(height * 0.165)
        sub_y = int(height * 0.895)
        block_h = line_height * max(1, len(title_lines))
        # Center the headline block optically between the brand zone and date zone.
        zone_top = int(height * (0.25 if brand_clean else 0.14))
        zone_bot = int(height * (0.81 if sub_clean else 0.88))
        title_start_y = zone_top + max(0, (zone_bot - zone_top - block_h) // 2) + int(title_size * 0.82)

    font_esc = html.escape(font)
    color_esc = html.escape(text_color or "#FFFFFF")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<filter id="soft" x="-10%" y="-10%" width="120%" height="120%">',
        '<feDropShadow dx="0" dy="3" stdDeviation="10" flood-color="#000000" flood-opacity="0.28"/>',
        "</filter>",
        "</defs>",
    ]
    if brand_clean:
        parts.append(
            f'<text x="{brand_x}" y="{brand_y}" text-anchor="{anchor}" '
            f'font-family="{font_esc}, sans-serif" font-size="{brand_size}" font-weight="600" '
            f'letter-spacing="{round(-brand_size * 0.02, 2)}" fill="{color_esc}" filter="url(#soft)">'
            f'{html.escape(brand_clean)}</text>'
        )
    if title_lines:
        for idx, line in enumerate(title_lines):
            y = title_start_y + idx * line_height
            parts.append(
                f'<text x="{anchor_x}" y="{y}" text-anchor="{anchor}" '
                f'font-family="{font_esc}, sans-serif" font-size="{title_size}" font-weight="500" '
                f'letter-spacing="{letter_spacing}" fill="{color_esc}" filter="url(#soft)">'
                f'{html.escape(line)}</text>'
            )
    if sub_clean:
        parts.append(
            f'<text x="{anchor_x}" y="{sub_y}" text-anchor="{anchor}" '
            f'font-family="{font_esc}, sans-serif" font-size="{sub_size}" font-weight="400" '
            f'letter-spacing="{round(-sub_size * 0.01, 2)}" fill="{color_esc}" fill-opacity="0.88" filter="url(#soft)">'
            f'{html.escape(sub_clean)}</text>'
        )
    parts.append("</svg>")

    h_svg, svg_path = tempfile.mkstemp(prefix="botcut-overlay-", suffix=".svg")
    os.close(h_svg)
    h_png, png_path = tempfile.mkstemp(prefix="botcut-overlay-", suffix=".png")
    os.close(h_png)
    try:
        Path(svg_path).write_text("\n".join(parts), encoding="utf-8")
        proc = subprocess.run(
            [rsvg, "-w", str(width), "-h", str(height), "-o", png_path, svg_path],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0 or not os.path.isfile(png_path) or os.path.getsize(png_path) == 0:
            try:
                os.remove(png_path)
            except OSError:
                pass
            return None
        return png_path
    finally:
        try:
            os.remove(svg_path)
        except OSError:
            pass


def _alpha_composite(base_png: str, overlay_png: str) -> None:
    """Alpha-blend transparent RGBA `overlay_png` onto `base_png` in place."""
    import cv2
    import numpy as np

    base = cv2.imread(base_png, cv2.IMREAD_COLOR)
    over = cv2.imread(overlay_png, cv2.IMREAD_UNCHANGED)
    if base is None or over is None or over.shape[2] != 4:
        return
    if over.shape[:2] != base.shape[:2]:
        over = cv2.resize(over, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_AREA)
    alpha = over[:, :, 3:4].astype(np.float32) / 255.0
    blended = base.astype(np.float32) * (1.0 - alpha) + over[:, :, :3].astype(np.float32) * alpha
    cv2.imwrite(base_png, np.clip(blended, 0, 255).astype(np.uint8))


def make_live_overlay_png(
    width: int,
    height: int,
    title: str,
    *,
    subtitle: str | None = None,
    brand_name: str | None = None,
    logo_path: str | None = None,
    face: dict | None = None,
    brand: dict | None = None,
    dest: str | None = None,
) -> str:
    """Create a transparent RGBA PNG (directional scrim + Swiss typography) for compositing over live video.

    When the speaker is off-center in landscape, uses the Matt-style left/right layout on the open side.
    When the speaker is centered, uses a face-safe lower-left editorial layout with a soft bottom scrim.
    """
    import cv2
    import numpy as np

    kit = load_brand() if brand is None else {**load_brand(), **brand}
    eff_brand = brand_name if brand_name is not None else (kit.get("brand_name") or kit.get("speaker_name") or "")
    eff_logo = logo_path if logo_path is not None else str(kit.get("logo") or "")
    eff_sub = (
        subtitle
        if subtitle is not None
        else datetime.date.today().strftime("%B %-d, %Y")
    )
    font = _resolve_font(kit["font"])
    portrait = height > width
    cx = (float(face["x"]) + float(face["w"]) / 2.0) if isinstance(face, dict) else 0.5
    centered_landscape = (not portrait) and (0.43 <= cx <= 0.57)
    text_side = "left" if cx >= 0.45 else "right"

    # Build transparent RGBA scrim layer (black with smooth cosine alpha).
    rgba = np.zeros((height, width, 4), dtype=np.float32)
    if portrait or centered_landscape:
        # Soft bottom-up scrim so lower-left typography pops without touching the speaker's face.
        t = np.linspace(0.0, 1.0, height, dtype=np.float32)
        start_y = 0.46 if portrait else 0.54
        ramp = np.clip((t - start_y) / (1.0 - start_y), 0.0, 1.0)
        alpha = 0.62 * (0.5 - 0.5 * np.cos(np.pi * ramp))
        rgba[:, :, 3] = alpha[:, None] * 255.0
    else:
        t = np.linspace(0.0, 1.0, width, dtype=np.float32)
        if text_side == "left":
            ramp = np.clip((0.60 - t) / 0.60, 0.0, 1.0)
        else:
            ramp = np.clip((t - 0.40) / 0.60, 0.0, 1.0)
        alpha = 0.56 * (0.5 - 0.5 * np.cos(np.pi * ramp))
        rgba[:, :, 3] = alpha[None, :] * 255.0

    # Render SVG typography (using lower-left compact mode when speaker is centered in landscape).
    if centered_landscape:
        svg_png = _render_centered_live_svg(
            width,
            height,
            title=title,
            subtitle=eff_sub,
            brand_name=eff_brand,
            font=font,
            text_color="#FFFFFF",
        )
    else:
        svg_png = _render_svg_overlay(
            width,
            height,
            title=title,
            subtitle=eff_sub,
            brand_name=eff_brand,
            text_side=text_side,
            has_logo=bool(eff_logo and os.path.isfile(eff_logo)),
            font=font,
            text_color="#FFFFFF",
        )

    if svg_png:
        try:
            over = cv2.imread(svg_png, cv2.IMREAD_UNCHANGED)
            if over is not None and over.shape[2] == 4:
                if over.shape[:2] != (height, width):
                    over = cv2.resize(over, (width, height), interpolation=cv2.INTER_AREA)
                # Porter-Duff "source over" RGBA compositing.
                sa = over[:, :, 3:4].astype(np.float32) / 255.0
                da = rgba[:, :, 3:4] / 255.0
                out_a = sa + da * (1.0 - sa)
                safe_a = np.where(out_a > 1e-5, out_a, 1.0)
                out_rgb = (over[:, :, :3].astype(np.float32) * sa + rgba[:, :, :3] * da * (1.0 - sa)) / safe_a
                rgba[:, :, :3] = out_rgb
                rgba[:, :, 3:4] = out_a * 255.0
        finally:
            try:
                os.remove(svg_png)
            except OSError:
                pass

    if dest is None:
        h_out, dest = tempfile.mkstemp(prefix="botcut-live-title-", suffix=".png")
        os.close(h_out)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    cv2.imwrite(dest, np.clip(rgba, 0, 255).astype(np.uint8))
    return dest


def _render_centered_live_svg(
    width: int,
    height: int,
    *,
    title: str,
    subtitle: str,
    brand_name: str,
    font: str,
    text_color: str,
) -> str | None:
    """Face-safe lower-left editorial overlay when a speaker is centered in a landscape live shot."""
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        return None
    title_clean = _smart_typography(title)
    sub_clean = _smart_typography(subtitle)
    brand_clean = _smart_typography(brand_name)

    title_size = int(height * (0.088 if len(title_clean) <= 24 else 0.068))
    brand_size = int(height * 0.036)
    sub_size = int(height * 0.032)
    title_lines = _balanced_wrap(title_clean, max_chars=26, max_lines=2)
    line_height = round(title_size * 1.08)

    margin_x = int(width * 0.055)
    sub_y = int(height * 0.915)
    title_start_y = sub_y - int(height * 0.055) - (len(title_lines) - 1) * line_height
    brand_y = title_start_y - int(title_size * 0.95) - int(height * 0.012)

    font_esc = html.escape(font)
    color_esc = html.escape(text_color or "#FFFFFF")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<filter id="soft" x="-10%" y="-10%" width="120%" height="120%">',
        '<feDropShadow dx="0" dy="3" stdDeviation="10" flood-color="#000000" flood-opacity="0.32"/>',
        "</filter>",
        "</defs>",
    ]
    if brand_clean:
        parts.append(
            f'<text x="{margin_x}" y="{brand_y}" text-anchor="start" '
            f'font-family="{font_esc}, sans-serif" font-size="{brand_size}" font-weight="600" '
            f'letter-spacing="{round(-brand_size * 0.015, 2)}" fill="{color_esc}" fill-opacity="0.92" filter="url(#soft)">'
            f'{html.escape(brand_clean)}</text>'
        )
    for idx, line in enumerate(title_lines):
        y = title_start_y + idx * line_height
        parts.append(
            f'<text x="{margin_x}" y="{y}" text-anchor="start" '
            f'font-family="{font_esc}, sans-serif" font-size="{title_size}" font-weight="500" '
            f'letter-spacing="{round(-title_size * 0.024, 2)}" fill="{color_esc}" filter="url(#soft)">'
            f'{html.escape(line)}</text>'
        )
    if sub_clean:
        parts.append(
            f'<text x="{margin_x}" y="{sub_y}" text-anchor="start" '
            f'font-family="{font_esc}, sans-serif" font-size="{sub_size}" font-weight="400" '
            f'fill="{color_esc}" fill-opacity="0.85" filter="url(#soft)">'
            f'{html.escape(sub_clean)}</text>'
        )
    parts.append("</svg>")

    h_svg, svg_path = tempfile.mkstemp(prefix="botcut-live-svg-", suffix=".svg")
    os.close(h_svg)
    h_png, png_path = tempfile.mkstemp(prefix="botcut-live-svg-", suffix=".png")
    os.close(h_png)
    try:
        Path(svg_path).write_text("\n".join(parts), encoding="utf-8")
        proc = subprocess.run(
            [rsvg, "-w", str(width), "-h", str(height), "-o", png_path, svg_path],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0 or not os.path.isfile(png_path) or os.path.getsize(png_path) == 0:
            try:
                os.remove(png_path)
            except OSError:
                pass
            return None
        return png_path
    finally:
        try:
            os.remove(svg_path)
        except OSError:
            pass


def compose_photo_card(
    frame_path: str,
    title: str,
    *,
    out_jpg: str | None = None,
    out_card_mp4: str | None = None,
    subtitle: str | None = None,
    brand_name: str | None = None,
    logo_path: str | None = None,
    face: dict | None = None,
    aspect: str = "landscape",
    brand: dict | None = None,
) -> dict:
    """Render a Matt-style minimal photo title card as a JPEG thumbnail and/or 3s opening MP4."""
    kit = load_brand() if brand is None else {**load_brand(), **brand}
    width, height = (1080, 1920) if aspect == "portrait" else (1920, 1080)
    eff_brand = brand_name if brand_name is not None else (kit.get("brand_name") or kit.get("speaker_name") or "")
    eff_logo = logo_path if logo_path is not None else str(kit.get("logo") or "")
    eff_sub = (
        subtitle
        if subtitle is not None
        else datetime.date.today().strftime("%B %-d, %Y")
    )
    font = _resolve_font(kit["font"])
    canvas_png, text_side = _prepare_canvas(frame_path, width, height, face, logo_path=eff_logo)
    overlay_png = _render_svg_overlay(
        width,
        height,
        title=title,
        subtitle=eff_sub,
        brand_name=eff_brand,
        text_side=text_side,
        has_logo=bool(eff_logo and os.path.isfile(eff_logo)),
        font=font,
        text_color="#FFFFFF",
    )
    ass_path = None
    try:
        if overlay_png:
            _alpha_composite(canvas_png, overlay_png)
            vf_jpg = []
            vf_mp4 = "fade=t=in:st=0:d=0.30:color=black,fade=t=out:st=2.60:d=0.40:color=black"
        else:
            ass_text = _build_overlay_ass(
                width,
                height,
                title=_smart_typography(title),
                subtitle=_smart_typography(eff_sub),
                brand_name=_smart_typography(eff_brand),
                text_side=text_side,
                has_logo=bool(eff_logo and os.path.isfile(eff_logo)),
                font=font,
                text_color="#FFFFFF",
            )
            handle, ass_path = tempfile.mkstemp(prefix="botcut-thumb-", suffix=".ass")
            os.close(handle)
            Path(ass_path).write_text(ass_text, encoding="utf-8")
            escaped_ass = ass_path.replace("\\", "\\\\").replace(":", "\\:")
            vf_jpg = ["-vf", f"ass='{escaped_ass}'"]
            vf_mp4 = (
                f"ass='{escaped_ass}',"
                "fade=t=in:st=0:d=0.30:color=black,"
                "fade=t=out:st=2.60:d=0.40:color=black"
            )

        if out_jpg:
            os.makedirs(os.path.dirname(os.path.abspath(out_jpg)), exist_ok=True)
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", canvas_png,
                    *vf_jpg,
                    "-frames:v", "1", "-q:v", "2",
                    out_jpg,
                ],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                raise SystemExit(f"Could not write thumbnail: {ffmpeg_error_detail(proc.stderr or '')}")
        if out_card_mp4:
            os.makedirs(os.path.dirname(os.path.abspath(out_card_mp4)), exist_ok=True)
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-loop", "1", "-framerate", "30", "-t", "3", "-i", canvas_png,
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", "3",
                    "-vf", vf_mp4,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-movflags", "+faststart",
                    "-metadata", f"comment={title}",
                    "-f", "mp4",
                    out_card_mp4,
                ],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                raise SystemExit(f"Could not write photo title card: {ffmpeg_error_detail(proc.stderr or '')}")
    finally:
        for tmp in (canvas_png, overlay_png, ass_path):
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    return {"jpg": out_jpg, "card": out_card_mp4, "side": text_side}


def embed_thumbnail(mp4_path: str, jpg_path: str) -> None:
    """Attach a JPEG cover poster to an MP4 without re-encoding video or audio."""
    if not os.path.isfile(mp4_path) or not os.path.isfile(jpg_path):
        return
    part = mp4_path + ".thumb.part.mp4"
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", mp4_path,
            "-i", jpg_path,
            "-map", "0:v:0", "-map", "0:a?", "-map", "1:v:0",
            "-c", "copy",
            "-disposition:v:1", "attached_pic",
            "-movflags", "+faststart",
            part,
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        try:
            os.remove(part)
        except OSError:
            pass
        raise SystemExit(f"Could not embed thumbnail: {ffmpeg_error_detail(proc.stderr or '')}")
    os.replace(part, mp4_path)


def make_photo_thumb(
    cuts_path: str,
    *,
    title: str = "",
    subtitle: str | None = None,
    brand_name: str | None = None,
    out_jpg: str | None = None,
    out_card_mp4: str | None = None,
    aspect: str = "landscape",
    embed: bool = False,
) -> dict:
    """Pick the best frame from a BotCut project and render a Matt-style thumbnail/card."""
    from botcut.cli import load_cuts

    out_dir, doc = load_cuts(cuts_path)
    clips = doc.get("clips") or []
    lines = doc.get("lines") or []
    work = os.path.join(out_dir, "work")
    winner = pick_best_frame(clips, lines, work)

    handle, hi_frame = tempfile.mkstemp(prefix="botcut-hiframe-", suffix=".jpg")
    os.close(handle)
    try:
        frame_src = hi_frame if _grab_full_frame(winner["path"], winner["at"], hi_frame) else winner["still"]
        eff_title = title.strip() or str(doc.get("title") or "").strip() or str(doc.get("intent") or "").strip()[:48] or "Update"
        jpg = out_jpg or (os.path.join(out_dir, "rough_cut_thumb.jpg") if not out_card_mp4 else None)
        result = compose_photo_card(
            frame_src,
            eff_title,
            out_jpg=jpg,
            out_card_mp4=out_card_mp4,
            subtitle=subtitle,
            brand_name=brand_name,
            face=winner.get("face"),
            aspect=aspect,
        )
        if embed and jpg:
            mp4 = os.path.join(out_dir, "rough_cut.mp4")
            if os.path.isfile(mp4):
                embed_thumbnail(mp4, jpg)
        return result
    finally:
        try:
            os.remove(hi_frame)
        except OSError:
            pass
