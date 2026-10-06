import os
import subprocess

from botcut.cli import run
from botcut.short import pick_highlight, short_args


def test_short_args_crops_landscape_and_only_scales_vertical():
    wide = " ".join(short_args(1.25, 12.0, 1920, 1080))
    assert "crop=ih*9/16:ih" in wide
    assert "scale=1080:1920" in wide
    tall = " ".join(short_args(0.0, 8.0, 1080, 1920))
    assert "crop=" not in tall
    assert "scale=1080:1920" in tall


def test_fake_highlight_uses_the_first_three_ids(monkeypatch):
    monkeypatch.setenv("BOTCUT_FAKE", "1")

    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("botcut.short.requests.post", boom)
    choice = pick_highlight(
        [
            {"id": 4, "clip": 0, "start": 0.0, "end": 1.0, "text": "a"},
            {"id": 5, "clip": 0, "start": 1.0, "end": 2.0, "text": "b"},
            {"id": 9, "clip": 1, "start": 0.0, "end": 1.0, "text": "c"},
            {"id": 10, "clip": 1, "start": 1.0, "end": 2.0, "text": "d"},
        ]
    )
    assert choice == {"start_id": 4, "end_id": 9, "title": "Fake highlight"}


def test_fake_short_is_1080x1920(monkeypatch, tmp_path, capsys):
    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr("botcut.stt.requests.post", boom)
    monkeypatch.setattr("botcut.pick.requests.post", boom)
    monkeypatch.setattr("botcut.short.requests.post", boom)

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
    from botcut.cli import make_short

    make_short(str(out / "cuts.json"))
    captured = capsys.readouterr().out
    assert "Wrote" in captured
    assert "short.mp4" in captured
    assert "Traceback" not in captured
    assert os.path.isfile(out / "short.mp4")
    assert os.path.isfile(out / "rough_cut.mp4")

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(out / "short.mp4"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout.strip() == "1080x1920"
