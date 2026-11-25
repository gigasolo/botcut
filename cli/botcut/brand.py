"""Brand kit and video type presets for fast, cohesive finishing."""

from __future__ import annotations

import json
import os
from pathlib import Path

PRESET_NAMES = ("custom", "internal", "marketing", "monologue")

DEFAULT_BRAND = {
    "brand_name": "",
    "font": "Inter",
    "bg_color": "#0F1218",
    "surface_color": "#181D27",
    "text_color": "#F5F7FA",
    "accent_color": "#3B82F6",
    "speaker_name": "",
    "speaker_title": "",
    "logo": "",
    "music": "",
}

PRESETS: dict[str, dict] = {
    "custom": {
        "label": "Custom",
        "aspect": "source",
        "resolution": "source",
        "pace": "open",
        "max_pause": 1.4,
        "zoom": "off",
        "pip": False,
        "captions": "srt",
        "lower_third": False,
        "music": False,
        "intent": "",
    },
    "internal": {
        "label": "Internal Update",
        "aspect": "landscape",
        "resolution": "1080p",
        "pace": "measured",
        "max_pause": 0.85,
        "zoom": "off",
        "pip": True,
        "captions": "srt",
        "lower_third": False,
        "music": False,
        "intent": (
            "Clear internal team update. Keep every key announcement and decision in order, "
            "drop flubs and retakes, and keep explanations crisp."
        ),
    },
    "marketing": {
        "label": "External Marketing",
        "aspect": "landscape",
        "resolution": "1080p",
        "pace": "tight",
        "max_pause": 0.55,
        "zoom": "subtle",
        "pip": True,
        "captions": "social",
        "lower_third": True,
        "music": True,
        "intent": (
            "Polished external marketing and thought leadership video. Lead with a strong hook, "
            "tighten pacing, drop tangents and retakes, and keep the sharpest product and story points."
        ),
    },
    "monologue": {
        "label": "Monologue / Social",
        "aspect": "portrait",
        "resolution": "1080p",
        "pace": "tight",
        "max_pause": 0.55,
        "zoom": "medium",
        "pip": False,
        "captions": "social",
        "lower_third": False,
        "music": False,
        "intent": (
            "Engaging monologue for social media and LinkedIn. Keep natural flow and authenticity, "
            "drop stumbles and retakes, and keep punchy self-contained thoughts."
        ),
    },
}


def brand_path() -> str:
    override = os.environ.get("BOTCUT_BRAND", "").strip()
    if override:
        return os.path.abspath(override)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.abspath(os.path.join(base, "botcut", "brand.json"))


def load_brand(path: str | None = None) -> dict:
    """Load the user's brand kit, falling back cleanly to DEFAULT_BRAND."""
    target = path or brand_path()
    merged = dict(DEFAULT_BRAND)
    try:
        raw = json.loads(Path(target).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return merged
    if isinstance(raw, dict):
        for key in DEFAULT_BRAND:
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                merged[key] = val.strip()
    return merged


def init_brand(path: str | None = None) -> str:
    """Write a default brand.json if one does not exist yet, and return its path."""
    target = path or brand_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if not os.path.isfile(target):
        Path(target).write_text(json.dumps(DEFAULT_BRAND, indent=2) + "\n", encoding="utf-8")
    return target


def preset_config(name: str) -> dict:
    if name not in PRESETS:
        raise SystemExit(f"Unknown preset: {name}")
    return dict(PRESETS[name])


def hex_to_ass(color: str, alpha: int = 0) -> str:
    """Convert #RRGGBB to ASS &HAABBGGRR& color syntax."""
    raw = str(color or "#FFFFFF").strip().lstrip("#")
    if len(raw) != 6:
        raw = "FFFFFF"
    try:
        r = int(raw[0:2], 16)
        g = int(raw[2:4], 16)
        b = int(raw[4:6], 16)
    except ValueError:
        r, g, b = 255, 255, 255
    a = max(0, min(255, int(alpha)))
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}&"


def resolve_music(music_arg: str | None, brand: dict | None = None) -> str | None:
    """Return a playable audio file path from an explicit arg or brand kit folder/file."""
    candidate = (music_arg or "").strip() or str((brand or {}).get("music") or "").strip()
    if not candidate:
        return None
    expanded = os.path.abspath(os.path.expanduser(candidate))
    if os.path.isfile(expanded):
        return expanded
    if os.path.isdir(expanded):
        exts = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}
        for name in sorted(os.listdir(expanded)):
            if os.path.splitext(name)[1].lower() in exts:
                return os.path.join(expanded, name)
    return None
