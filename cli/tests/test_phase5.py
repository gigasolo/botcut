"""Tests for Phase 5: Ship Pack (chapters, posts, thumbnail, dual-format renders), Studio Frame, and L-cuts."""

import json
import subprocess

from botcut import angles, render, ship
from botcut.media import probe


def test_chapters_map_beats_onto_rendered_timeline():
    doc = {
        "title": "What's new in BotCut",
        "segments": [
            {"clip": 0, "start": 2.0, "end": 12.0, "reason": "a"},
            {"clip": 0, "start": 20.0, "end": 35.0, "reason": "b"},
        ],
        "lines": [
            {"id": 0, "clip": 0, "start": 2.0, "end": 7.0, "keep": True, "text": "Intro"},
            {"id": 1, "clip": 0, "start": 20.5, "end": 28.0, "keep": True, "text": "Second topic"},
        ],
        "outline": {
            "beats": [
                {"title": "Intro", "first": 0, "last": 0},
                {"title": "Multi-cam polish", "first": 1, "last": 1},
            ]
        },
    }
    rows = ship.chapters(doc)
    assert [(r["stamp"], r["title"]) for r in rows] == [("00:00", "Intro"), ("00:10", "Multi-cam polish")]
    text = ship.format_chapters(rows)
    assert "00:00 Intro\n00:10 Multi-cam polish\n" == text


def test_lcut_shifts_interior_angle_boundaries():
    clips = [
        {"path": "/tmp/a.mp4", "duration": 30.0},
        {"path": "/tmp/b.mp4", "duration": 30.0, "role": "angle", "of": 0, "offset": 0.0},
    ]
    lines = [
        {"id": 0, "clip": 0, "start": 0.0, "end": 4.0, "keep": True, "text": "a"},
        {"id": 1, "clip": 0, "start": 4.2, "end": 9.0, "keep": True, "text": "b"},
        {"id": 2, "clip": 0, "start": 9.2, "end": 14.0, "keep": True, "text": "c"},
    ]
    segs = [{"clip": 0, "start": 0.0, "end": 14.0, "reason": "all"}]
    runs = [{"clip": 1, "of": 0, "line": 1, "through": 1, "reason": "beat"}]
    hard = angles.angle_windows(runs, lines, segs, clips, lcut=0.0)
    smooth = angles.angle_windows(runs, lines, segs, clips, lcut=0.15)
    assert hard[0]["start"] == 4.1
    assert smooth[0]["start"] == 4.25
    assert smooth[0]["end"] > hard[0]["end"]


def test_studio_light_frame_and_ship_pack_e2e(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    clip = tmp_path / "talk.mp4"
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:d=3",
            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(clip),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    proj = tmp_path / "proj"
    proj.mkdir()
    cuts = proj / "cuts.json"
    cuts.write_text(json.dumps({
        "title": "Q4 Launch",
        "mode": "assemble",
        "clips": [{"index": 0, "path": str(clip), "duration": 3.0}],
        "segments": [{"clip": 0, "start": 0.0, "end": 2.5, "reason": "a"}],
        "lines": [{"id": 0, "clip": 0, "start": 0.0, "end": 2.5, "keep": True, "text": "Welcome team."}],
        "outline": {"beats": [{"title": "Welcome", "first": 0, "last": 0}]},
    }))
    pack = ship.make_ship_pack(str(cuts), str(tmp_path / "pack"), resolution="720p", include_portrait=True)
    assert (tmp_path / "pack" / "chapters.txt").is_file()
    assert (tmp_path / "pack" / "posts.md").is_file()
    assert (tmp_path / "pack" / "thumb_landscape.jpg").is_file()
    assert (probe(pack["landscape"])["width"], probe(pack["landscape"])["height"]) == (1280, 720)
    assert (probe(pack["portrait"])["width"], probe(pack["portrait"])["height"]) == (720, 1280)

    # Confirm light studio frame helper produces light canvas colors.
    assert render._studio_bg("light")[0] == "#F2F4F7"
    assert render._studio_bg("dark")[0] == "#111318"
