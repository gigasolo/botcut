import subprocess

import pytest

from botcut.media import grab_still, render_args, render_percent, resolve_encoder
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
    assert "-progress" not in args
    assert "loudnorm" not in graph
    assert "fade=" not in graph


def _graph(args):
    return args[args.index("-filter_complex") + 1]


def _clips():
    return [
        {"path": "/tmp/a.mp4", "width": 640, "height": 360, "fps": 30.0},
        {"path": "/tmp/b.mp4", "width": 640, "height": 360, "fps": 30.0},
    ]


def test_rough_cut_fades_the_open_and_the_close():
    clips = [{"path": "/tmp/a.mp4", "width": 640, "height": 360, "fps": 30.0}]
    segs = [{"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"}]
    graph = _graph(render_args(segs, clips, "/tmp/out.mp4", polish=True, scene_transition="off"))
    assert "fade=t=in:st=0:d=0.500:color=black" in graph
    assert "fade=t=out:st=0.700:d=0.800:color=black" in graph
    assert "afade=t=in:st=0:d=0.020" in graph
    assert "afade=t=out:st=1.480:d=0.020" in graph


def test_same_file_joins_stay_hard():
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"},
        {"clip": 0, "start": 2.0, "end": 3.5, "reason": "b"},
    ]
    for switch in ("dip", "off"):
        graph = _graph(render_args(segs, _clips(), "/tmp/out.mp4", polish=True, scene_transition=switch))
        branches = graph.split(";")
        assert "fade=t=in:st=0:d=0.500:color=black" in branches[0]
        assert "fade=t=out" not in branches[0]
        assert "fade=t=in" not in branches[2]
        assert "fade=t=out:st=0.700:d=0.800:color=black" in branches[2]
        assert "d=0.180" not in graph
        assert "d=0.120" not in graph
        assert "d=0.020" in branches[1]
        assert "d=0.020" in branches[3]


def test_file_change_dips_when_the_switch_is_on():
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"},
        {"clip": 1, "start": 0.25, "end": 2.0, "reason": "b"},
    ]
    graph = _graph(render_args(segs, _clips(), "/tmp/out.mp4", polish=True, scene_transition="dip"))
    branches = graph.split(";")
    assert "fade=t=in:st=0:d=0.500:color=black,fade=t=out:st=1.320:d=0.180:color=black" in branches[0]
    assert "fade=t=in:st=0:d=0.180:color=black,fade=t=out:st=0.950:d=0.800:color=black" in branches[2]
    assert "afade=t=in:st=0:d=0.020,afade=t=out:st=1.380:d=0.120" in branches[1]
    assert "afade=t=in:st=0:d=0.120,afade=t=out:st=1.730:d=0.020" in branches[3]


def test_file_change_stays_a_cut_when_the_switch_is_off():
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"},
        {"clip": 1, "start": 0.25, "end": 2.0, "reason": "b"},
    ]
    graph = _graph(render_args(segs, _clips(), "/tmp/out.mp4", polish=True, scene_transition="off"))
    branches = graph.split(";")
    assert "fade=t=in:st=0:d=0.500:color=black" in branches[0]
    assert "d=0.180" not in graph
    assert "fade=t=out:st=0.950:d=0.800:color=black" in branches[2]
    assert "d=0.120" not in graph
    assert "d=0.020" in branches[1]
    assert "d=0.020" in branches[3]


def test_short_segment_scales_the_bookends():
    clips = [{"path": "/tmp/a.mp4", "width": 640, "height": 360, "fps": 30.0}]
    segs = [{"clip": 0, "start": 0.0, "end": 0.5, "reason": "a"}]
    graph = _graph(render_args(segs, clips, "/tmp/out.mp4", polish=True))
    assert "fade=t=in:st=0:d=0.173:color=black" in graph
    assert "fade=t=out:st=0.223:d=0.277:color=black" in graph


def test_vaapi_polish_fades_before_upload():
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"},
        {"clip": 1, "start": 0.0, "end": 1.5, "reason": "b"},
    ]
    graph = _graph(
        render_args(
            segs,
            _clips(),
            "/tmp/out.mp4",
            encoder="vaapi",
            device="/dev/dri/renderD128",
            polish=True,
        )
    )
    branch = graph.split(";")[0]
    assert "hwdownload" in branch
    assert "fade=t=in" in branch
    assert branch.index("fade=") < branch.index("hwupload")


def test_polish_fade_filter_encodes(tmp_path):
    def tiny(path, color):
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=64x64:r=30:d=1",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000",
                "-t",
                "1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr[-400:]

    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    tiny(first, "black")
    tiny(second, "white")
    out = tmp_path / "out.mp4"
    clips = [
        {"path": str(first), "width": 64, "height": 64, "fps": 30.0},
        {"path": str(second), "width": 64, "height": 64, "fps": 30.0},
    ]
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.0, "reason": "a"},
        {"clip": 1, "start": 0.0, "end": 1.0, "reason": "b"},
    ]
    args = render_args(segs, clips, str(out), polish=True)
    proc = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert out.stat().st_size > 0


def test_rough_cut_audio_fades_and_levels():
    clips = [{"path": "/tmp/a.mp4", "width": 640, "height": 360, "fps": 30.0}]
    segs = [{"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"}]
    args = render_args(segs, clips, "/tmp/out.mp4", polish=True)
    graph = args[args.index("-filter_complex") + 1]
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in graph
    assert "afade=t=in:st=0:d=0.020" in graph
    assert "afade=t=out:st=1.480:d=0.020" in graph
    assert "aresample=48000" in graph


def test_render_args_uses_vaapi_and_downloads_only_a_mismatched_rate():
    clips = [
        {"path": "/tmp/a.mp4", "width": 640, "height": 360, "fps": 30.0},
        {"path": "/tmp/b.mp4", "width": 1280, "height": 720, "fps": 24.0},
    ]
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"},
        {"clip": 1, "start": 0.25, "end": 2.0, "reason": "b"},
    ]
    args = render_args(segs, clips, "/tmp/out.mp4", encoder="vaapi", device="/dev/dri/renderD128")
    assert args.count("-hwaccel") == 2
    assert args.count("-hwaccel_device") == 2
    assert "/dev/dri/renderD128" in args
    graph = args[args.index("-filter_complex") + 1]
    branches = graph.split(";")
    assert branches[0].startswith("[0:v]scale_vaapi=")
    assert "fps=" not in branches[0]
    assert "scale_vaapi=640:360:format=nv12:force_original_aspect_ratio=decrease" in branches[0]
    assert "hwdownload,format=nv12,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1,format=nv12,hwupload" in branches[0]
    assert "pad_vaapi" not in graph
    assert branches[2].startswith("[1:v]scale_vaapi=")
    assert "fps=30,format=nv12,hwupload" in branches[2]
    assert "libx264" not in args
    assert "-crf" not in args
    assert args[args.index("-c:v") + 1] == "h264_vaapi"
    assert args[args.index("-qp") + 1] == "20"
    assert args[args.index("-c:a") + 1] == "aac"


def test_render_args_keeps_a_rotated_input_on_the_software_graph():
    clips = [
        {"path": "/tmp/a.mp4", "width": 1920, "height": 1080, "fps": 30.0},
        {"path": "/tmp/b.mp4", "width": 1080, "height": 1920, "fps": 30.0, "rotate": -90},
    ]
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.0, "reason": "a"},
        {"clip": 1, "start": 0.0, "end": 1.0, "reason": "b"},
    ]
    args = render_args(segs, clips, "/tmp/out.mp4", encoder="vaapi", device="/dev/dri/renderD128")
    assert args.count("-hwaccel") == 1
    graph = args[args.index("-filter_complex") + 1]
    branches = graph.split(";")
    assert branches[0].startswith("[0:v]scale_vaapi=")
    assert "hwdownload" in branches[0]
    assert branches[2].startswith("[1:v]scale=")
    assert "hwupload" in branches[2]
    assert "scale_vaapi" not in branches[2]


def test_resolve_encoder_falls_back_and_can_be_forced(monkeypatch):
    monkeypatch.delenv("BOTCUT_ENCODER", raising=False)
    monkeypatch.setattr("botcut.media.vaapi_device", lambda: None)
    assert resolve_encoder() == ("x264", None)

    monkeypatch.setenv("BOTCUT_ENCODER", "x264")
    monkeypatch.setattr("botcut.media.vaapi_device", lambda: "/dev/dri/renderD128")
    assert resolve_encoder() == ("x264", None)

    monkeypatch.setenv("BOTCUT_ENCODER", "auto")
    assert resolve_encoder() == ("vaapi", "/dev/dri/renderD128")

    monkeypatch.setenv("BOTCUT_ENCODER", "vaapi")
    monkeypatch.setattr("botcut.media.vaapi_device", lambda: None)
    with pytest.raises(SystemExit, match="no VA-API device"):
        resolve_encoder()

    monkeypatch.setenv("BOTCUT_ENCODER", "nvenc")
    with pytest.raises(SystemExit, match="must be x264 or vaapi"):
        resolve_encoder()


def test_render_percent_uses_kept_duration():
    assert render_percent(0, 10) == 0
    assert render_percent(5_000_000, 10) == 50
    assert render_percent(11_000_000, 10) == 100
    assert render_percent(1_000_000, 0) == 0


def test_stt_posts_file_last_and_redacts_the_key(monkeypatch, tmp_path):
    flac = tmp_path / "take.flac"
    flac.write_bytes(b"not really flac")
    seen = {"calls": 0}

    class Response:
        status_code = 400
        text = "refused token supersecret"
        headers = {}

        def json(self):
            return {}

    def post(url, headers=None, files=None, timeout=None):
        seen["calls"] += 1
        seen["url"] = url
        seen["names"] = [item[0] for item in files]
        seen["auth"] = headers["Authorization"]
        return Response()

    monkeypatch.setenv("XAI_API_KEY", "supersecret")
    monkeypatch.setattr("botcut.net.requests.post", post)
    with pytest.raises(SystemExit) as exc:
        transcribe_xai(str(flac))
    assert seen["calls"] == 1
    assert seen["url"] == "https://api.x.ai/v1/stt"
    assert seen["names"] == list(STT_FIELDS)
    assert seen["names"][-1] == "file"
    assert seen["auth"] == "Bearer supersecret"
    assert "supersecret" not in str(exc.value)
    assert "STT HTTP 400" in str(exc.value)


def test_grab_still_writes_one_jpeg(tmp_path):
    video = tmp_path / "shot.mp4"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=640x360:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=f=440",
            "-t",
            "1",
            str(video),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]
    dest = tmp_path / "stills" / "0.jpg"
    assert grab_still(str(video), 0.4, str(dest))
    assert dest.stat().st_size > 0
    assert grab_still(str(tmp_path / "missing.mp4"), 0.0, str(tmp_path / "no.jpg")) is False
