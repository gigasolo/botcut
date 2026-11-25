"""Tests for Phase 3: Brand Kit, 3 Video Presets, Word-Highlighted ASS Captions, Lower-Thirds, Typographic Cards, and Auto-Ducked Music."""

import json
import subprocess

import numpy as np

from botcut import brand, captions, card, render
from botcut.media import cut_pieces, probe


def test_brand_kit_init_load_and_presets(tmp_path, monkeypatch):
    cfg = tmp_path / "brand.json"
    monkeypatch.setenv("BOTCUT_BRAND", str(cfg))
    created = brand.init_brand()
    assert created == str(cfg)
    data = json.loads(cfg.read_text())
    assert data["font"] == "Inter"

    data["accent_color"] = "#FF5500"
    data["speaker_name"] = "Lon Baker"
    data["speaker_title"] = "CEO"
    cfg.write_text(json.dumps(data))
    loaded = brand.load_brand()
    assert loaded["accent_color"] == "#FF5500"
    assert loaded["speaker_name"] == "Lon Baker"

    assert brand.hex_to_ass("#3B82F6") == "&H00F6823B&"
    assert brand.preset_config("internal")["aspect"] == "landscape"
    assert brand.preset_config("marketing")["lower_third"] is True
    assert brand.preset_config("monologue")["aspect"] == "portrait"


def test_social_ass_captions_and_lower_third():
    words = [
        {"text": "Hello", "start": 0.2, "end": 0.5},
        {"text": "team", "start": 0.5, "end": 0.9},
        {"text": "today", "start": 0.9, "end": 1.3},
    ]
    ass = captions.to_ass(
        words,
        width=1080,
        height=1920,
        brand={"accent_color": "#3B82F6"},
        lower_third=("Lon Baker", "CEO"),
    )
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert "Lon Baker" in ass and "CEO" in ass
    assert r"{\c&H00F6823B&}Hello" in ass
    assert r"{\c&H00F6823B&}team" in ass


def test_typographic_card_renders_offline_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    cards_dir = tmp_path / "xdg" / "botcut" / "cards"
    cards_dir.mkdir(parents=True)
    os_mode_dir = cards_dir
    os_mode_dir.chmod(0o700)
    dest = cards_dir / "botcut-card-q3-update.mp4"
    card.make_card("Q3 Company Update", str(dest), style="typo", aspect="landscape")
    assert dest.is_file() and dest.stat().st_size > 0
    info = probe(str(dest))
    assert (info["width"], info["height"]) == (1920, 1080)
    assert info["audio"] is True
    assert card.card_sentence(str(dest), "") == "Q3 Company Update"


def test_auto_ducked_music_ducks_under_voice_and_swells_in_silence(tmp_path):
    music = tmp_path / "bed.wav"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=220:r=48000:d=2", "-ac", "2", str(music)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    # 4 seconds total: first 2s loud speech, last 2s silence.
    voice = np.zeros((4 * render.RATE, 2), dtype=np.float32)
    voice[: 2 * render.RATE] = 0.5
    bed = render._load_music_samples(str(music), len(voice))
    assert bed is not None and len(bed) == len(voice)
    ducked = render._duck_music(voice, bed)
    speech_rms = float(np.sqrt(np.mean(ducked[int(0.8 * render.RATE) : int(1.4 * render.RATE)] ** 2)))
    quiet_rms = float(np.sqrt(np.mean(ducked[int(2.4 * render.RATE) : int(2.8 * render.RATE)] ** 2)))
    assert quiet_rms > speech_rms * 1.8
