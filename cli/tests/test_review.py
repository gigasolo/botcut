import json
import os
import subprocess

import pytest

from botcut.cli import review
from botcut.review import compatible, concat_line, drifted, keep_list, launch, offsets


def test_offsets_are_a_running_total():
    clips = [{"duration": 3.0}, {"duration": 2.5}, {"duration": 4.0}]
    assert offsets(clips) == pytest.approx([0.0, 3.0, 5.5])


def test_keep_list_maps_into_master_time_and_sorts():
    doc = {
        "segments": [
            {"clip": 1, "start": 0.5, "end": 1.0, "reason": "later"},
            {"clip": 0, "start": 0.0, "end": 0.4, "reason": "first"},
        ]
    }
    listing = keep_list(doc, offsets([{"duration": 3.0}, {"duration": 2.5}, {"duration": 4.0}]))
    assert listing["source"] == "master.mp4"
    assert listing["keep"][0]["start"] == pytest.approx(0.0)
    assert listing["keep"][0]["end"] == pytest.approx(0.4)
    assert listing["keep"][1]["start"] == pytest.approx(3.5)
    assert listing["keep"][1]["end"] == pytest.approx(4.0)
    assert listing["keep"][1]["label"] == "later"


def test_compatible_rejects_a_different_frame_size():
    base = {"codec": "h264", "width": 1920, "height": 1080, "fps": 30.0, "audio_codec": "aac", "sample_rate": 48000}
    other = {**base, "height": 720, "width": 1280}
    assert compatible([base, base]) is True
    assert compatible([base, other]) is False


def test_drift_threshold_is_a_tenth_of_a_second_per_clip():
    assert drifted(6.5, 6.0, 2) is True
    assert drifted(6.1, 6.0, 2) is False


def test_concat_line_escapes_quotes(tmp_path):
    path = tmp_path / "it's.mp4"
    escaped = os.path.abspath(path).replace("'", r"'\''")
    assert concat_line(str(path)) == f"file '{escaped}'"


def test_launch_names_install_when_the_app_is_missing(monkeypatch, capsys):
    monkeypatch.setattr("botcut.review.shutil.which", lambda _name: None)
    launch("/tmp/master.keep.json")
    out = capsys.readouterr().out
    assert "BotCut app not found" in out
    assert "botcut /tmp/master.keep.json" in out


def test_launch_starts_botcut_detached(monkeypatch):
    seen = {}
    monkeypatch.setattr("botcut.review.shutil.which", lambda name: "/usr/bin/botcut" if name == "botcut" else None)

    def popen(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("botcut.review.subprocess.Popen", popen)
    launch("/tmp/master.keep.json")
    assert seen["args"] == ["/usr/bin/botcut", "/tmp/master.keep.json"]
    assert seen["kwargs"]["start_new_session"] is True


def test_fake_review_builds_a_six_second_master(monkeypatch, tmp_path, capsys):
    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr("botcut.stt.requests.post", boom)
    monkeypatch.setattr("botcut.pick.requests.post", boom)

    from botcut.cli import run

    clips = []
    for name in ("a.mp4", "b.mp4"):
        path = tmp_path / name
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=640x360:rate=30",
                "-f",
                "lavfi",
                "-i",
                "sine=f=440",
                "-t",
                "3",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr[-400:]
        clips.append(str(path))

    out = tmp_path / "out"
    run(clips, str(out))
    rough = out / "rough_cut.mp4"
    assert rough.is_file()
    review(str(out / "cuts.json"), no_open=True)
    review(str(out / "cuts.json"), no_open=True)
    captured = capsys.readouterr().out
    assert "Review:" in captured
    assert "master.keep.json" in captured
    assert "master up to date" in captured
    assert "Traceback" not in captured
    assert rough.is_file()

    listing = json.loads((out / "master.keep.json").read_text())
    assert listing["source"] == "master.mp4"
    assert listing["keep"]
    for item in listing["keep"]:
        assert 0 <= item["start"] < item["end"] <= 6.2

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(out / "master.mp4"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert abs(float(probe.stdout.strip()) - 6.0) <= 0.2
