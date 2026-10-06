import json
import os
import subprocess

from botcut.cli import resolve_inputs, run


def test_txt_list_skips_blanks_and_comments(tmp_path):
    listing = tmp_path / "shots.txt"
    listing.write_text("# note\n\n/tmp/a.mp4\n  /tmp/b.mp4  \n")
    assert resolve_inputs([str(listing)]) == ["/tmp/a.mp4", "/tmp/b.mp4"]


def test_fake_run_writes_a_playable_rough_cut(monkeypatch, tmp_path, capsys):
    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr("botcut.stt.requests.post", boom)
    monkeypatch.setattr("botcut.pick.requests.post", boom)

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
    captured = capsys.readouterr().out
    assert "cuts.json" in captured
    assert "rough_cut.mp4" in captured
    assert "Traceback" not in captured
    assert "XAI_API_KEY=" not in captured
    assert "unique?" not in captured

    doc = json.loads((out / "cuts.json").read_text())
    assert doc["version"] == 1
    assert doc["stt"] == "fake"
    assert doc["model"] == "fake"
    assert [clip["index"] for clip in doc["clips"]] == [0, 1]
    assert all(os.path.isabs(clip["path"]) for clip in doc["clips"])
    assert doc["segments"]
    assert doc["dropped"] == []
    for seg in doc["segments"]:
        assert {"clip", "start", "end", "reason"} <= set(seg)
        assert seg["end"] > seg["start"]
        assert seg["reason"] == "fake"

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(out / "rough_cut.mp4"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(probe.stdout.strip()) > 0
