"""Tests for Phase 4: Matt-style photo title cards, thumbnails, and MP4 cover embedding."""

import json
import subprocess

from botcut import thumb
from botcut.media import probe


def test_compose_photo_card_creates_landscape_portrait_and_mp4_card(tmp_path):
    frame = tmp_path / "frame.jpg"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:d=1", "-frames:v", "1", str(frame)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr[-300:]

    jpg_land = tmp_path / "thumb_land.jpg"
    card_mp4 = tmp_path / "botcut-card-whats-new.mp4"
    res = thumb.compose_photo_card(
        str(frame),
        "What's new",
        out_jpg=str(jpg_land),
        out_card_mp4=str(card_mp4),
        subtitle="November 23, 2026",
        brand_name="GigaSolo",
        face={"x": 0.55, "y": 0.20, "w": 0.20, "h": 0.30},
        aspect="landscape",
    )
    assert res["side"] == "left"
    assert jpg_land.is_file() and jpg_land.stat().st_size > 0
    assert (probe(str(jpg_land), need_audio=False)["width"], probe(str(jpg_land), need_audio=False)["height"]) == (1920, 1080)
    card_info = probe(str(card_mp4))
    assert (card_info["width"], card_info["height"]) == (1920, 1080)
    assert card_info["audio"] is True

    jpg_port = tmp_path / "thumb_port.jpg"
    res_p = thumb.compose_photo_card(
        str(frame),
        "What's new",
        out_jpg=str(jpg_port),
        face={"x": 0.25, "y": 0.20, "w": 0.20, "h": 0.30},
        aspect="portrait",
    )
    assert res_p["side"] == "right"
    assert (probe(str(jpg_port), need_audio=False)["width"], probe(str(jpg_port), need_audio=False)["height"]) == (1080, 1920)


def test_make_photo_thumb_and_embed_into_mp4(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    proj = tmp_path / "proj"
    proj.mkdir()
    clip = tmp_path / "talk.mp4"
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:d=3",
            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(clip),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    rough = proj / "rough_cut.mp4"
    rough.write_bytes(clip.read_bytes())
    cuts = proj / "cuts.json"
    cuts.write_text(json.dumps({
        "title": "Q4 Launch",
        "clips": [{"index": 0, "path": str(clip), "duration": 3.0}],
        "lines": [{"id": 0, "clip": 0, "start": 0.5, "end": 2.5, "keep": True, "text": "Hello team."}],
    }))
    res = thumb.make_photo_thumb(str(cuts), embed=True)
    assert (proj / "rough_cut_thumb.jpg").is_file()
    assert res["jpg"] == str(proj / "rough_cut_thumb.jpg")
    # Confirm embedded MP4 still probes cleanly.
    info = probe(str(rough))
    assert info["width"] == 640 and info["audio"] is True


def test_make_card_photo_style_writes_via_dot_part_file(tmp_path, monkeypatch):
    from botcut import card

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    cards_dir = tmp_path / "xdg" / "botcut" / "cards"
    cards_dir.mkdir(parents=True)
    cards_dir.chmod(0o700)

    clip = tmp_path / "talk.mp4"
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:d=2",
            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(clip),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    dest = cards_dir / "botcut-card-ai-future-open.mp4"
    card.make_card("AI Products: The Future", str(dest), style="photo", from_video=str(clip))
    assert dest.is_file() and dest.stat().st_size > 0
    info = probe(str(dest))
    assert (info["width"], info["height"]) == (1920, 1080)
    assert info["audio"] is True


def test_live_title_overlay_renders_over_opening_live_video(tmp_path):
    from botcut import render

    clip = tmp_path / "talk.mp4"
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:d=4",
            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(clip),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    clips = [probe(str(clip))]
    segs = [{"clip": 0, "start": 0.0, "end": 4.0, "reason": "a"}]
    out = tmp_path / "live_title.mp4"
    render.render(
        segs,
        clips,
        str(out),
        "Rendering",
        "Render failed",
        encoder="x264",
        device=None,
        resolution="720p",
        aspect="landscape",
        live_title="AI Products: The Future",
        work_dir=str(tmp_path / "work"),
    )
    out_info = probe(str(out))
    assert (out_info["width"], out_info["height"]) == (1280, 720)
    assert abs(out_info["duration"] - 4.0) < 0.2


def test_live_title_overlay_continuous_across_multiple_opening_pieces(tmp_path):
    from botcut import render

    clip = tmp_path / "talk.mp4"
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:d=5",
            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(clip),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    clips = [probe(str(clip))]
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"},
        {"clip": 0, "start": 1.6, "end": 4.5, "reason": "b"},
    ]
    out = tmp_path / "live_title_multi.mp4"
    render.render(
        segs,
        clips,
        str(out),
        "Rendering",
        "Render failed",
        encoder="x264",
        device=None,
        resolution="720p",
        aspect="landscape",
        live_title="Smooth Opening Title",
        work_dir=str(tmp_path / "work"),
    )
    out_info = probe(str(out))
    assert (out_info["width"], out_info["height"]) == (1280, 720)
    assert abs(out_info["duration"] - 4.4) < 0.25
