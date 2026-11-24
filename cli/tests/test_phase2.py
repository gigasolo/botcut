"""Tests for Phase 2: camera color matching, multi-cam zoom suppression, per-line camera choice, still images, and PiP."""

import subprocess

from botcut import angles, color, render
from botcut.media import cut_pieces, is_image, probe


def test_color_match_computes_gentle_clamped_filter():
    ref = [{"luma_mean": 0.55, "luma_std": 0.20, "sat_mean": 0.35, "r_mean": 0.56, "g_mean": 0.55, "b_mean": 0.54}]
    cam = [{"luma_mean": 0.45, "luma_std": 0.16, "sat_mean": 0.30, "r_mean": 0.42, "g_mean": 0.45, "b_mean": 0.48}]
    match = color.compute_match(ref, cam)
    assert match is not None
    assert 0.08 <= match["brightness"] <= 0.12
    assert 1.10 <= match["contrast"] <= 1.18
    assert match["rm"] > 0 and match["bm"] < 0
    expr = color.color_filter(match)
    assert "eq=brightness=" in expr and "colorbalance=" in expr

    # Identical cameras produce no filter.
    assert color.compute_match(ref, ref) is None
    assert color.color_filter(None) == ""


def test_multicam_suppresses_digital_punch_in_zoom():
    clips = [
        {"path": "/tmp/a.mp4", "width": 1920, "height": 1080, "fps": 30.0, "duration": 20.0},
        {"path": "/tmp/b.mp4", "width": 1920, "height": 1080, "fps": 30.0, "duration": 20.0, "role": "angle", "of": 0, "offset": 0.0},
    ]
    segs = [
        {"clip": 0, "start": 0.0, "end": 5.0, "reason": "a"},
        {"clip": 0, "start": 7.0, "end": 12.0, "reason": "b"},
    ]
    lines = [
        {"id": 0, "clip": 0, "start": 0.0, "end": 5.0, "keep": True, "text": "one."},
        {"id": 1, "clip": 0, "start": 7.0, "end": 12.0, "keep": True, "text": "two."},
    ]
    runs = [{"clip": 1, "of": 0, "line": 1, "through": 1, "reason": "hides a cut"}]
    pieces = cut_pieces(segs, clips, lines=lines, zoom="cuts", angles=runs)
    assert all(not p["punch"] for p in pieces)


def test_angles_prefer_forces_specific_line_to_chosen_camera():
    clips = [
        {"path": "/tmp/a.mp4", "duration": 20.0},
        {"path": "/tmp/b.mp4", "duration": 20.0, "role": "angle", "of": 0, "offset": 0.0},
    ]
    lines = [
        {"id": 0, "clip": 0, "start": 0.0, "end": 2.0, "keep": True, "text": "first."},
        {"id": 1, "clip": 0, "start": 2.1, "end": 4.0, "keep": True, "text": "second."},
    ]
    segs = [{"clip": 0, "start": 0.0, "end": 4.0, "reason": "a"}]
    runs = angles.plan(lines, segs, clips, cameras={"prefer": {"1": 1}})
    assert len(runs) == 1
    assert runs[0]["clip"] == 1 and runs[0]["line"] == 1 and runs[0]["reason"] == "chosen camera"


def test_still_image_probes_and_renders_with_ken_burns_and_pip(tmp_path):
    slide = tmp_path / "slide.png"
    speaker = tmp_path / "speaker.mp4"
    # Create a real 320x180 PNG slide and 320x180 spoken video.
    p1 = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:d=1", "-frames:v", "1", str(slide)],
        capture_output=True, text=True,
    )
    assert p1.returncode == 0, p1.stderr[-300:]
    p2 = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=4",
            "-f", "lavfi", "-i", "sine=f=440:r=48000:d=4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(speaker),
        ],
        capture_output=True, text=True,
    )
    assert p2.returncode == 0, p2.stderr[-300:]

    assert is_image(str(slide))
    slide_info = probe(str(slide))
    assert slide_info["is_image"] is True
    assert slide_info["audio"] is False
    assert slide_info["width"] == 320 and slide_info["height"] == 180
    slide_info["role"] = "broll"

    spk_info = probe(str(speaker))
    clips = [spk_info, slide_info]
    segs = [{"clip": 0, "start": 0.0, "end": 3.0, "reason": "a"}]
    lines = [
        {"id": 0, "clip": 0, "start": 0.0, "end": 1.0, "keep": True, "text": "intro"},
        {"id": 1, "clip": 0, "start": 1.0, "end": 2.0, "keep": True, "text": "slide"},
        {"id": 2, "clip": 0, "start": 2.0, "end": 3.0, "keep": True, "text": "outro"},
    ]
    covers = [{"clip": 1, "line": 1, "through": 1, "start": 0.0, "end": 1.0, "reason": "slide"}]
    out_pip = tmp_path / "landscape_pip.mp4"
    render.render(
        segs, clips, str(out_pip), "Rendering", "Render failed",
        encoder="x264", device=None, covers=covers, lines=lines,
        resolution="720p", aspect="landscape", pip=True, work_dir=str(tmp_path / "w1"),
    )
    out_info = probe(str(out_pip))
    assert (out_info["width"], out_info["height"]) == (1280, 720)
