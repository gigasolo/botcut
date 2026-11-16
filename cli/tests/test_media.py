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
    assert "aresample=osr=48000" in graph
    assert "fps=30" in graph
    assert args[args.index("-c:v") + 1] == "libx264"
    assert args[args.index("-preset") + 1] == "veryfast"
    assert args[args.index("-crf") + 1] == "18"
    assert args[args.index("-c:a") + 1] == "aac"
    assert args[args.index("-ar") + 1] == "48000"
    assert args[args.index("-movflags") + 1] == "+faststart"
    assert args[-1] == "/tmp/out.mp4"
    assert args[args.index("-t") + 1] == "1.500"
    assert "-progress" not in args
    assert "loudnorm" not in graph
    assert "fade=" not in graph


def test_render_args_scales_a_leading_card_to_the_camera():
    clips = [
        {"path": "/tmp/botcut-card-1-open.mp4", "width": 160, "height": 90, "fps": 25.0},
        {"path": "/tmp/talk.mp4", "width": 1920, "height": 1080, "fps": 30.0},
    ]
    segs = [
        {"clip": 0, "start": 0.0, "end": 3.0, "reason": "card"},
        {"clip": 1, "start": 0.0, "end": 1.0, "reason": "story"},
    ]
    graph = _graph(render_args(segs, clips, "/tmp/out.mp4"))
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in graph
    assert "fps=30" in graph
    assert "scale=160:90" not in graph


def test_render_args_uses_the_first_card_when_every_shot_is_a_card():
    clips = [
        {"path": "/tmp/botcut-card-a-open.mp4", "width": 160, "height": 90, "fps": 25.0},
        {"path": "/tmp/botcut-card-b-close.mp4", "width": 1280, "height": 720, "fps": 30.0},
    ]
    segs = [
        {"clip": 0, "start": 0.0, "end": 3.0, "reason": "card"},
        {"clip": 1, "start": 0.0, "end": 3.0, "reason": "card"},
    ]
    graph = _graph(render_args(segs, clips, "/tmp/out.mp4"))
    assert "scale=160:90:force_original_aspect_ratio=decrease" in graph
    assert "fps=25" in graph


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
    assert "loudnorm" not in graph
    assert "afade=t=in:st=0:d=0.020" in graph
    assert "afade=t=out:st=1.480:d=0.020" in graph
    assert "aresample=osr=48000" in graph
    assert args[args.index("-ar") + 1] == "48000"


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


def test_render_args_brings_a_full_range_clip_to_limited_in_its_own_branch():
    # A Hover clip is yuvj420p, color_range pc. The DJI next to it is limited.
    # concat cannot fix that on VA-API frames, so the branch converts first.
    clips = [
        {"path": "/tmp/dji.mp4", "width": 2688, "height": 1512, "fps": 25.0, "pix_fmt": "yuv420p10le",
         "color_range": "tv"},
        {"path": "/tmp/hover.mp4", "width": 3840, "height": 2160, "fps": 29.97, "pix_fmt": "yuvj420p",
         "color_range": "pc"},
        {"path": "/tmp/phone.mp4", "width": 1920, "height": 1080, "fps": 30.0, "pix_fmt": "yuv420p",
         "color_range": "pc"},
    ]
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.0, "reason": "a"},
        {"clip": 1, "start": 27.0, "end": 29.0, "reason": "b"},
        {"clip": 2, "start": 0.0, "end": 1.0, "reason": "c"},
    ]
    args = render_args(segs, clips, "/tmp/out.mp4", encoder="vaapi", device="/dev/dri/renderD128")
    branches = args[args.index("-filter_complex") + 1].split(";")
    assert branches[0].startswith("[0:v]scale_vaapi=")
    assert "range" not in branches[0]
    assert branches[2].startswith("[1:v]scale_vaapi=")
    assert "hwdownload,format=nv12,scale=in_range=pc:out_range=tv,pad=2688:1512" in branches[2]
    assert "hwdownload,format=nv12,scale=in_range=pc:out_range=tv,pad=2688:1512" in branches[4]

    cpu = render_args(segs, clips, "/tmp/out.mp4")
    cpu_branches = cpu[cpu.index("-filter_complex") + 1].split(";")
    assert "range" not in cpu_branches[0]
    assert "[1:v]scale=2688:1512:force_original_aspect_ratio=decrease:in_range=pc:out_range=tv,pad=" in cpu_branches[2]
    assert "[2:v]scale=2688:1512:force_original_aspect_ratio=decrease:in_range=pc:out_range=tv,pad=" in cpu_branches[4]


def test_ffmpeg_error_detail_names_the_cause_not_the_thread_exits():
    from botcut.media import ffmpeg_error_detail

    log = "\n".join(
        [
            "[in#43 @ 0x1] stream 0, timescale not set",
            "Impossible to convert between the formats supported by the filter 'graph 0 input from stream 2:0' and the filter 'auto_scale_8'",
            "Link 'graph 0 input from stream 2:0.default' -> 'auto_scale_8.default':",
            "[fc#0 @ 0x2] Error reinitializing filters!",
            "[vost#0:0/h264_vaapi @ 0x3] [enc:h264_vaapi @ 0x4] Could not open encoder before EOF",
            "[vost#0:0/h264_vaapi @ 0x3] Task finished with error code: -22 (Invalid argument)",
            "[out#0/mp4 @ 0x5] Nothing was written into output file, because at least one of its streams received no packets.",
        ]
    )
    assert ffmpeg_error_detail(log).startswith("Impossible to convert between the formats")
    assert ffmpeg_error_detail("") == "ffmpeg failed"
    assert ffmpeg_error_detail("[in#1] stream 0, timescale not set\nx\n") == "x"


def _graph(args):
    return args[args.index("-filter_complex") + 1]


def test_clean_sound_runs_over_the_joined_cut_and_is_what_gets_written():
    from botcut.media import CLEAN_FILTER

    clips = [{"path": "/tmp/a.mp4", "width": 640, "height": 360, "fps": 30.0}]
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"},
        {"clip": 0, "start": 3.0, "end": 4.5, "reason": "b"},
    ]
    plain = render_args(segs, clips, "/tmp/out.mp4", polish=True)
    assert "loudnorm" not in _graph(plain) and "afftdn" not in _graph(plain)
    assert "[a]" in plain

    measured = {"i": -27.3, "tp": -9.1, "lra": 4.2, "thresh": -37.8, "offset": 0.4}
    args = render_args(segs, clips, "/tmp/out.mp4", polish=True, clean_sound=True, measured=measured)
    last = _graph(args).split(";")[-1]
    # One chain after the join, so the noise floor and the gain do not change at every cut.
    assert last.startswith(f"[a]{CLEAN_FILTER},loudnorm=I=-16.0:TP=-1.5:LRA=11.0")
    assert "measured_I=-27.3" in last and "measured_thresh=-37.8" in last and "linear=true" in last
    assert last.endswith("aresample=osr=48000[sound]")
    assert "[sound]" in args and "[a]" not in args

    # With nothing measured, the sound is cleaned and left at its own level.
    unmeasured = _graph(render_args(segs, clips, "/tmp/out.mp4", clean_sound=True)).split(";")[-1]
    assert unmeasured == f"[a]{CLEAN_FILTER}[sound]"


def test_the_measuring_pass_has_no_picture_and_no_file():
    clips = [{"path": "/tmp/a.mp4", "width": 640, "height": 360, "fps": 30.0}]
    segs = [
        {"clip": 0, "start": 0.0, "end": 1.5, "reason": "a"},
        {"clip": 0, "start": 3.0, "end": 4.5, "reason": "b"},
    ]
    args = render_args(
        segs, clips, "-", encoder="vaapi", device="/dev/dri/renderD128", polish=True, measure=True
    )
    graph = _graph(args)
    assert "[0:v]" not in graph and "[v]" not in graph
    assert "concat=n=2:v=0:a=1[a]" in graph
    assert "print_format=json" in graph
    assert args[-3:] == ["-f", "null", "-"]
    assert "-hwaccel" not in args and "-init_hw_device" not in args and "-c:v" not in args


def test_parse_loudness_reads_the_last_report_and_refuses_silence():
    from botcut.media import parse_loudness

    report = (
        "[Parsed_loudnorm_2 @ 0x1] \n"
        '{\n\t"input_i" : "-27.31",\n\t"input_tp" : "-9.10",\n\t"input_lra" : "4.20",\n'
        '\t"input_thresh" : "-37.80",\n\t"output_i" : "-16.1",\n\t"target_offset" : "0.40"\n}\n'
    )
    assert parse_loudness(report) == {"i": -27.31, "tp": -9.1, "lra": 4.2, "thresh": -37.8, "offset": 0.4}
    # A card, or a shot with the mic off, has no level to bring up.
    assert parse_loudness(report.replace("-27.31", "-inf")) is None
    assert parse_loudness(report.replace("-27.31", "-70.00")) is None
    assert parse_loudness("ffmpeg said nothing useful") is None


def _loudness_of(path) -> float:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]
    summary = proc.stderr[proc.stderr.rindex("Integrated loudness:") :]
    return float(summary.split("I:")[1].split("LUFS")[0])


def test_a_quiet_recording_and_a_hot_one_both_leave_at_the_same_level(tmp_path, capsys):
    from botcut.media import render_with_progress

    def shot(path, volume):
        # Pink noise is closer to a voice in a room than a pure tone is.
        proc = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=gray:s=64x64:r=30:d=6",
                "-f", "lavfi", "-i", f"anoisesrc=color=pink:sample_rate=48000:amplitude={volume}:duration=6",
                "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr[-400:]

    results = {}
    for name, volume in (("quiet", 0.02), ("hot", 0.8)):
        src = tmp_path / f"{name}.mp4"
        shot(src, volume)
        clips = [{"path": str(src), "width": 64, "height": 64, "fps": 30.0, "duration": 6.0}]
        segs = [
            {"clip": 0, "start": 0.2, "end": 2.6, "reason": "a"},
            {"clip": 0, "start": 3.0, "end": 5.6, "reason": "b"},
        ]
        out = tmp_path / f"{name}-out.mp4"
        render_with_progress(segs, clips, str(out), "Rendering", "Render failed", polish=True)
        results[name] = (_loudness_of(src), _loudness_of(out))
    # They went in more than 20 LU apart and come out within 1 LU of the target.
    assert results["hot"][0] - results["quiet"][0] > 20
    for before, after in results.values():
        assert abs(after - (-16.0)) <= 1.0, results
    assert "Rendering 0%" in capsys.readouterr().out


def test_each_shot_is_matched_before_the_join_and_the_bed_is_left_alone():
    from botcut.media import level_gain

    assert level_gain({"loudness": -32.3}) == 16.3
    assert level_gain({"loudness": -10.0}) == -6.0
    # A whisper is not lifted without limit, and a shot with no sound is left alone.
    assert level_gain({"loudness": -50.0}) == 20.0
    assert level_gain({"loudness": -75.0}) == 0.0
    assert level_gain({}) == 0.0

    clips = [
        {"path": "/tmp/quiet.mp4", "width": 640, "height": 360, "fps": 30.0, "duration": 9.0, "loudness": -32.3},
        {"path": "/tmp/room.mp4", "width": 640, "height": 360, "fps": 30.0, "duration": 9.0, "role": "broll"},
    ]
    segs = [{"clip": 0, "start": 0.0, "end": 8.0, "reason": "a"}]
    lines = [
        {"id": 0, "clip": 0, "start": 0.0, "end": 2.0, "keep": True, "text": "a"},
        {"id": 1, "clip": 0, "start": 2.0, "end": 6.0, "keep": True, "text": "b"},
        {"id": 2, "clip": 0, "start": 6.0, "end": 8.0, "keep": True, "text": "c"},
    ]
    covers = [{"clip": 1, "line": 1, "through": 1, "start": 0.0, "end": 4.0, "reason": "shows it"}]
    graph = _graph(render_args(segs, clips, "/tmp/o.mp4", clean_sound=True, covers=covers, lines=lines))
    # The voice gets the gain, alone and under the B-roll. The B-roll's own sound stays at its bed level.
    assert "[0:a]volume=16.3dB,aresample" in graph
    assert "volume=16.3dB[g1]" in graph and "[g1][b1]amix" in graph
    assert graph.count("volume=0.25") == 1
    # Without the clean pass nothing is touched.
    assert "volume=16.3dB" not in _graph(render_args(segs, clips, "/tmp/o.mp4", covers=covers, lines=lines))


def test_a_quiet_shot_and_a_loud_one_sound_alike_in_the_movie(tmp_path):
    from botcut import cli
    from botcut.media import render_with_progress

    clips = []
    # About 15 LU apart, like a lapel mic beside a camera mic. Both are inside what a gain can match.
    for name, volume in (("quiet", 0.09), ("hot", 0.5)):
        src = tmp_path / f"{name}.mp4"
        proc = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=gray:s=64x64:r=30:d=6",
                "-f", "lavfi", "-i", f"anoisesrc=color=pink:sample_rate=48000:amplitude={volume}:duration=6",
                "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr[-400:]
        clips.append({"path": str(src), "width": 64, "height": 64, "fps": 30.0, "duration": 6.0})
    cli._level_clips(str(tmp_path / "work"), clips)
    assert 12 < clips[1]["loudness"] - clips[0]["loudness"] < 19
    # Measured once: the second call reads what the first wrote.
    assert (tmp_path / "work" / "0-quiet.loudness.json").exists()

    segs = [
        {"clip": 0, "start": 0.5, "end": 5.5, "reason": "a"},
        {"clip": 1, "start": 0.5, "end": 5.5, "reason": "b"},
    ]
    out = tmp_path / "out.mp4"
    render_with_progress(segs, clips, str(out), "Rendering", "Render failed", scene_transition="off")

    def part(start):
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-ss", str(start), "-t", "4", "-i", str(out),
             "-af", "ebur128", "-f", "null", "-"],
            capture_output=True,
            text=True,
        )
        summary = proc.stderr[proc.stderr.rindex("Integrated loudness:") :]
        return float(summary.split("I:")[1].split("LUFS")[0])

    first, second = part(0.5), part(5.5)
    assert abs(first - second) <= 2.0, (first, second)
    assert abs(_loudness_of(out) - (-16.0)) <= 1.5
