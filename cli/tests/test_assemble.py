import json
import subprocess

from botcut.cli import run


def _clip(path, seconds):
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
            str(seconds),
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]


def test_assemble_keeps_every_file_in_order(monkeypatch, tmp_path, capsys):
    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setattr("botcut.stt.requests.post", boom)
    monkeypatch.setattr("botcut.pick.requests.post", boom)

    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    _clip(first, 3)
    _clip(second, 3)
    out = tmp_path / "out"
    run([str(first), str(second)], str(out), mode="assemble")
    captured = capsys.readouterr().out
    assert "Reading files" in captured
    assert "Rendering" in captured
    assert "Transcribing" not in captured
    assert "Choosing takes" not in captured
    assert "Traceback" not in captured
    assert "unique?" not in captured

    doc = json.loads((out / "cuts.json").read_text())
    assert doc["mode"] == "assemble"
    assert doc["stt"] == "none"
    assert doc["dropped"] == []
    assert [seg["clip"] for seg in doc["segments"]] == [0, 1]
    assert doc["segments"][0]["reason"] == "assemble"
    assert doc["segments"][0]["start"] == 0
    assert doc["segments"][1]["start"] == 0
    assert doc["segments"][0]["end"] == doc["clips"][0]["duration"]
    assert doc["segments"][1]["end"] == doc["clips"][1]["duration"]

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
    assert abs(float(probe.stdout.strip()) - 6.0) <= 0.4
