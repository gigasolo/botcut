import pytest

from botcut.media import render_args
from botcut.stt import STT_FIELDS, transcribe_xai


def test_render_args_has_one_input_per_segment_and_concat():
    clips = [
        {"path": "/tmp/a.mp4", "width": 640, "height": 360, "fps": 30.0},
        {"path": "/tmp/b.mp4", "width": 1280, "height": 720, "fps": 30.0},
    ]
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"},
        {"clip": 1, "start": 0.25, "end": 2.0, "reason": "b"},
    ]
    args = render_args(segs, clips, "/tmp/out.mp4")
    assert args.count("-i") == 2
    assert args[args.index("-i") + 1] == "/tmp/a.mp4"
    graph = args[args.index("-filter_complex") + 1]
    assert "concat=n=2:v=1:a=1" in graph
    assert "scale=640:360:force_original_aspect_ratio=decrease" in graph
    assert "pad=640:360:(ow-iw)/2:(oh-ih)/2" in graph
    assert "aresample=48000" in graph
    assert "fps=30" in graph
    assert args[args.index("-c:v") + 1] == "libx264"
    assert args[args.index("-preset") + 1] == "veryfast"
    assert args[args.index("-crf") + 1] == "18"
    assert args[args.index("-c:a") + 1] == "aac"
    assert args[args.index("-movflags") + 1] == "+faststart"
    assert args[-1] == "/tmp/out.mp4"
    assert args[args.index("-t") + 1] == "1.500"


def test_stt_posts_file_last_and_redacts_the_key(monkeypatch, tmp_path):
    flac = tmp_path / "take.flac"
    flac.write_bytes(b"not really flac")
    seen = {}

    class Response:
        status_code = 400
        text = "refused token supersecret"

        def json(self):
            return {}

    def post(url, headers=None, files=None, timeout=None):
        seen["url"] = url
        seen["names"] = [item[0] for item in files]
        seen["auth"] = headers["Authorization"]
        return Response()

    monkeypatch.setenv("XAI_API_KEY", "supersecret")
    monkeypatch.setattr("botcut.stt.requests.post", post)
    with pytest.raises(SystemExit) as exc:
        transcribe_xai(str(flac))
    assert seen["url"] == "https://api.x.ai/v1/stt"
    assert seen["names"] == list(STT_FIELDS)
    assert seen["names"][-1] == "file"
    assert seen["auth"] == "Bearer supersecret"
    assert "supersecret" not in str(exc.value)
    assert "STT HTTP 400" in str(exc.value)
