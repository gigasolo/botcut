"""The movie made in pieces: whole frames, a crossfade at a join, and pieces that are not made twice."""

import os
import subprocess

import numpy as np
import pytest

from botcut import render
from botcut.media import cut_pieces


def _clip(path="/tmp/a.mp4", **more):
    return {"path": path, "width": 64, "height": 64, "fps": 30.0, "duration": 20.0, **more}


def test_every_piece_is_a_whole_number_of_frames_and_the_voice_is_unbroken_inside_a_segment():
    clips = [_clip(), _clip("/tmp/b.mp4", role="broll")]
    segs = [{"clip": 0, "start": 1.013, "end": 7.049, "reason": "a"}, {"clip": 0, "start": 9.5, "end": 11.26, "reason": "b"}]
    lines = [
        {"id": 0, "clip": 0, "start": 1.2, "end": 2.9, "keep": True, "text": "a"},
        {"id": 1, "clip": 0, "start": 3.117, "end": 6.3, "keep": True, "text": "b"},
        {"id": 2, "clip": 0, "start": 6.5, "end": 6.9, "keep": True, "text": "c"},
        {"id": 3, "clip": 0, "start": 9.7, "end": 11.0, "keep": True, "text": "d"},
    ]
    covers = [{"clip": 1, "line": 1, "through": 1, "start": 2.0, "end": 6.0, "reason": "shows it"}]
    placed = render.timeline(cut_pieces(segs, clips, polish=True, covers=covers, lines=lines), 30.0)
    assert [piece["clip"] for piece in placed] == [0, 1, 0, 0]
    assert all(isinstance(piece["frames"], int) and piece["frames"] > 0 for piece in placed)
    # The pieces follow each other on the movie with no frame between them.
    assert placed[0]["at"] == 0
    for before, after in zip(placed, placed[1:]):
        assert after["at"] == before["at"] + before["frames"]
    assert sum(piece["frames"] for piece in placed) == 234
    # Inside the first segment the voice goes on from where the piece before stopped, to the frame.
    for before, after in zip(placed, placed[1:3]):
        assert after["voice_at"] == pytest.approx(before["voice_at"] + before["frames"] / 30.0)
    # The speaker's picture starts where the voice is. The B-roll starts where the run said.
    assert placed[2]["start"] == pytest.approx(placed[2]["voice_at"])
    assert placed[1]["start"] == 2.0
    runs = render.voice_runs(placed, 30.0)
    assert [(run["clip"], run["begin"], run["end"]) for run in runs] == [(0, 0, 181 * 1600), (0, 181 * 1600, 234 * 1600)]
    # A cut starts on a frame of its source, so the picture shown is the one the sound belongs to.
    assert runs[0]["source"] == pytest.approx(1.0) and runs[1]["source"] == pytest.approx(9.5)


class _Tones:
    """A steady value per clip, so what plays where can be read off the mix."""

    def __init__(self, levels, seconds=30):
        self._levels = levels
        self._seconds = seconds

    def of(self, index):
        level = self._levels.get(index)
        if level is None:
            return None
        return np.full((render.RATE * self._seconds, 2), int(level * 32767), dtype=np.int16)


def test_a_join_inside_a_shot_is_a_crossfade_and_a_dip_between_shots_is_two_fades():
    clips = [_clip(), _clip("/tmp/b.mp4")]
    segs = [
        {"clip": 0, "start": 1.0, "end": 3.0, "reason": "a"},
        {"clip": 0, "start": 5.0, "end": 7.0, "reason": "b"},
        {"clip": 1, "start": 1.0, "end": 3.0, "reason": "c"},
    ]
    placed = render.timeline(cut_pieces(segs, clips, polish=True), 30.0)
    out = render.mix(placed, clips, _Tones({0: 0.5, 1: 0.5}), 30.0, level=False)
    assert len(out) == 6 * render.RATE
    # In the middle of the first join both sides are playing: the level does not fall to nothing.
    join = 2 * render.RATE
    assert out[join - 400 : join + 400, 0].min() > 0.45
    # Between the two shots the sound goes down and comes back.
    change = 4 * render.RATE
    assert abs(out[change, 0]) < 0.05
    assert out[change - render.RATE // 2, 0] == pytest.approx(0.5, abs=0.01)
    # It opens and closes on a short fade, and holds its level in between.
    assert abs(out[0, 0]) < 0.05 and abs(out[-1, 0]) < 0.05
    assert out[render.RATE, 0] == pytest.approx(0.5, abs=0.01)


def test_broll_sound_sits_under_the_voice_and_another_camera_is_never_heard():
    clips = [_clip(), _clip("/tmp/b.mp4", role="broll")]
    segs = [{"clip": 0, "start": 0.0, "end": 8.0, "reason": "a"}]
    lines = [
        {"id": 0, "clip": 0, "start": 0.0, "end": 2.0, "keep": True, "text": "a"},
        {"id": 1, "clip": 0, "start": 2.0, "end": 6.0, "keep": True, "text": "b"},
        {"id": 2, "clip": 0, "start": 6.0, "end": 8.0, "keep": True, "text": "c"},
    ]
    covers = [{"clip": 1, "line": 1, "through": 1, "start": 0.0, "end": 4.0, "reason": "shows it"}]
    placed = render.timeline(cut_pieces(segs, clips, polish=True, covers=covers, lines=lines), 30.0)
    tones = _Tones({0: 0.4, 1: 0.4})
    mixed = render.mix(placed, clips, tones, 30.0, level=False)
    assert mixed[render.RATE, 0] == pytest.approx(0.4, abs=0.01)
    assert mixed[4 * render.RATE, 0] == pytest.approx(0.4 + 0.4 * render.BED, abs=0.01)
    voice = render.mix(placed, clips, tones, 30.0, level=False, broll_sound="voice")
    assert voice[4 * render.RATE, 0] == pytest.approx(0.4, abs=0.01)
    # A silent B-roll file adds nothing and is not an error.
    silent = render.mix(placed, clips, _Tones({0: 0.4}), 30.0, level=False)
    assert silent[4 * render.RATE, 0] == pytest.approx(0.4, abs=0.01)
    for piece in placed:
        if "voice" in piece:
            piece["angle"] = True
    assert render.mix(placed, clips, tones, 30.0, level=False)[4 * render.RATE, 0] == pytest.approx(0.4, abs=0.01)


def test_a_quiet_shot_is_brought_up_before_the_join():
    clips = [_clip(loudness=-22.0)]
    placed = render.timeline(cut_pieces([{"clip": 0, "start": 0.0, "end": 2.0, "reason": "a"}], clips, polish=True), 30.0)
    out = render.mix(placed, clips, _Tones({0: 0.1}), 30.0)
    assert out[render.RATE, 0] == pytest.approx(0.1 * 10 ** (6 / 20), abs=0.005)


def _ticking(path, seconds=12, rate=30):
    """A shot that flashes white and beeps for the first three frames of every second."""
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s=64x64:r={rate}:d={seconds}",
            "-f", "lavfi", "-i", f"aevalsrc=0.6*sin(2*PI*1000*t)*lt(mod(t\\,1)\\,0.1):s=48000:d={seconds}",
            "-vf", "geq=lum='if(lt(mod(T,1),0.1),255,16)':cb=128:cr=128",
            "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "15", "-c:a", "aac", "-b:a", "192k",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]


def _flashes(path) -> list[float]:
    """The times the picture turns white."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True,
    )
    assert proc.returncode == 0
    bright = np.frombuffer(proc.stdout, dtype=np.uint8) > 128
    return [index / 30.0 for index in range(len(bright)) if bright[index] and (index == 0 or not bright[index - 1])]


def _beeps(path) -> list[float]:
    """The times the sound starts."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
        capture_output=True,
    )
    assert proc.returncode == 0
    loud = np.abs(np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)) > 2000
    step = 480
    blocks = loud[: len(loud) // step * step].reshape(-1, step).any(axis=1)
    return [index * step / 48000 for index in range(len(blocks)) if blocks[index] and (index == 0 or not blocks[index - 1])]


def _frames(path) -> int:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    return int(proc.stdout.strip().strip(","))


def test_the_picture_and_the_sound_stay_together_across_many_joins(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTCUT_ENCODER", "x264")
    src = tmp_path / "tick.mp4"
    _ticking(src)
    clips = [_clip(str(src), duration=12.0)]
    # Ragged edges on purpose: nothing here lands on a frame.
    segs = [
        {"clip": 0, "start": 0.713, "end": 2.441, "reason": "a"},
        {"clip": 0, "start": 3.607, "end": 4.219, "reason": "b"},
        {"clip": 0, "start": 4.811, "end": 7.377, "reason": "c"},
        {"clip": 0, "start": 7.913, "end": 9.151, "reason": "d"},
        {"clip": 0, "start": 9.677, "end": 11.523, "reason": "e"},
    ]
    out = tmp_path / "rough_cut.mp4"
    first = render.render(segs, clips, str(out), "Rendering", "Render failed", encoder="x264", device=None, scene_transition="off")
    assert first["pieces"] == 5 and first["made"] == 5
    placed = render.timeline(cut_pieces(segs, clips, polish=True, scene_transition="off"), 30.0)
    assert _frames(out) == sum(piece["frames"] for piece in placed)
    flashes, beeps = _flashes(out), _beeps(out)
    assert len(flashes) >= 5 and len(flashes) == len(beeps)
    # Every beep is within a frame of its flash, at the end of the movie as at the start.
    for flash, beep in zip(flashes, beeps):
        assert abs(flash - beep) <= 1 / 30 + 0.012, (flashes, beeps)

    # One piece taken out: the others are not made again.
    again = render.render(
        [seg for seg in segs if seg["reason"] != "c"], clips, str(out), "Rendering", "Render failed",
        encoder="x264", device=None, scene_transition="off",
    )
    assert again["pieces"] == 4 and again["made"] == 0
    assert _frames(out) == sum(piece["frames"] for piece in placed if piece["segment"] != 2)
    # A change to the source is a change to every piece of it.
    os.utime(src, ns=(1, 1))
    assert render.render(segs[:1], clips, str(out), "Rendering", "Render failed", encoder="x264", device=None)["made"] == 1
    # Nothing is left behind but the pieces and cached sound.
    assert sorted(os.listdir(tmp_path / "work")) == ["pieces", "sound"]


def test_a_piece_no_render_has_used_for_days_is_cleared_out(tmp_path):
    store = tmp_path / "pieces"
    store.mkdir()
    for name in ("used.mp4", "recent.mp4", "old.mp4", "half.mp4.part.mp4"):
        (store / name).write_bytes(b"x")
    now = 1_000_000.0
    os.utime(store / "old.mp4", (now - 3 * 24 * 3600, now - 3 * 24 * 3600))
    os.utime(store / "recent.mp4", (now - 3600, now - 3600))
    render._clear_out(str(store), {str(store / "used.mp4")}, now)
    assert sorted(os.listdir(store)) == ["recent.mp4", "used.mp4"]


def test_piece_cache_lru_cap_evicts_oldest_unused_and_keeps_used(tmp_path):
    store = tmp_path / "pieces"
    store.mkdir()
    now = 1_000_000.0
    files = [("used.mp4", 100, now - 500), ("oldest.mp4", 100, now - 400), ("middle.mp4", 100, now - 200), ("newest.mp4", 100, now - 10)]
    for name, size, mtime in files:
        p = store / name
        p.write_bytes(b"x" * size)
        os.utime(p, (mtime, mtime))
    render._clear_out(str(store), {str(store / "used.mp4")}, now, max_bytes=250)
    assert sorted(os.listdir(store)) == ["newest.mp4", "used.mp4"]


def test_target_size_supports_resolutions_and_aspects():
    from botcut.media import target_size

    uhd = [_clip(width=3840, height=2160, fps=30.0)]
    assert target_size(uhd, "source", "source") == (3840, 2160, 30.0)
    assert target_size(uhd, "1080p", "source") == (1920, 1080, 30.0)
    assert target_size(uhd, "720p", "landscape") == (1280, 720, 30.0)
    assert target_size(uhd, "1080p", "portrait") == (1080, 1920, 30.0)
    assert target_size(uhd, "720p", "portrait") == (720, 1280, 30.0)
    assert target_size(uhd, "1440p", "landscape") == (2560, 1440, 30.0)
    assert target_size(uhd, "source", "portrait") == (2160, 3840, 30.0)


def test_portrait_piece_args_crops_speaker_and_splits_broll():
    from botcut.frame import portrait_crop

    speaker = _clip("/tmp/a.mp4", width=1920, height=1080, face={"x": 0.7, "y": 0.2, "w": 0.1, "h": 0.2})
    broll = _clip("/tmp/b.mp4", width=1920, height=1080, role="broll")
    assert portrait_crop(speaker, 1080, 1920) == "crop=606:1080:1137:0"

    segs = [{"clip": 0, "start": 0.0, "end": 6.0, "reason": "a"}]
    lines = [
        {"id": 0, "clip": 0, "start": 0.0, "end": 2.0, "keep": True, "text": "a"},
        {"id": 1, "clip": 0, "start": 2.0, "end": 5.0, "keep": True, "text": "b"},
        {"id": 2, "clip": 0, "start": 5.0, "end": 6.0, "keep": True, "text": "c"},
    ]
    covers = [{"clip": 1, "line": 1, "through": 1, "start": 0.0, "end": 3.0, "reason": "demo"}]
    placed = render.timeline(cut_pieces(segs, [speaker, broll], polish=True, covers=covers, lines=lines), 30.0)
    spk_args = render.piece_args(
        placed[0], speaker, "/tmp/p0.mp4", width=1080, height=1920, fps=30.0, encoder="x264", device=None, polish=True, clips=[speaker, broll]
    )
    assert "crop=606:1080:1137:0" in spk_args[spk_args.index("-filter_complex") + 1]
    split_args = render.piece_args(
        placed[1], broll, "/tmp/p1.mp4", width=1080, height=1920, fps=30.0, encoder="x264", device=None, polish=True, clips=[speaker, broll]
    )
    graph = split_args[split_args.index("-filter_complex") + 1]
    assert "vstack=inputs=2" in graph
    assert split_args.count("-i") == 2


def test_portrait_render_and_out_file_re_render(tmp_path):
    from botcut.media import probe

    src_a = tmp_path / "speaker.mp4"
    src_b = tmp_path / "screen.mp4"
    for path, color in ((src_a, "blue"), (src_b, "green")):
        proc = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=30:d=4",
                "-f", "lavfi", "-i", "sine=f=440:r=48000:d=4",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                str(path),
            ],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr[-400:]

    clips = [
        {"path": str(src_a), "width": 320, "height": 180, "fps": 30.0, "duration": 4.0, "audio": True},
        {"path": str(src_b), "width": 320, "height": 180, "fps": 30.0, "duration": 4.0, "audio": True, "role": "broll"},
    ]
    segs = [{"clip": 0, "start": 0.0, "end": 3.0, "reason": "a"}]
    lines = [
        {"id": 0, "clip": 0, "start": 0.0, "end": 1.0, "keep": True, "text": "a"},
        {"id": 1, "clip": 0, "start": 1.0, "end": 2.0, "keep": True, "text": "b"},
        {"id": 2, "clip": 0, "start": 2.0, "end": 3.0, "keep": True, "text": "c"},
    ]
    covers = [{"clip": 1, "line": 1, "through": 1, "start": 0.0, "end": 1.0, "reason": "demo"}]
    out_portrait = tmp_path / "export_portrait.mp4"
    work = tmp_path / "proj_work"
    render.render(
        segs, clips, str(out_portrait), "Rendering", "Render failed",
        encoder="x264", device=None, covers=covers, lines=lines,
        resolution="720p", aspect="portrait", work_dir=str(work),
    )
    info = probe(str(out_portrait))
    assert (info["width"], info["height"]) == (720, 1280)
    assert not (tmp_path / "work").exists()
    assert (work / "pieces").is_dir()
