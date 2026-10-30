import json
import re
import subprocess
from pathlib import Path

import pytest

from botcut.broll import (
    COVER_SCHEMA,
    COVER_SYSTEM,
    accept_covers,
    broll_still_at,
    candidate_indexes,
    choose_covers,
    cover_user_content,
    cover_windows,
    spoken_kept,
)
from botcut.cli import main, render_saved, run
from botcut.media import render_args
from botcut.revise import revise
from botcut.stt import transcribe_fake


def test_accept_keeps_the_first_valid_claim_and_strips_times():
    claims = [
        {"clip": True, "line": 4},
        {"clip": 9, "line": 4},
        {"clip": 0, "line": 4},
        {"clip": 2, "line": 99},
        {"clip": 2, "line": 4, "start": 1.2, "end": 3.0},
        {"clip": 3, "line": 4},
        {"clip": 3, "line": 5},
        {"clip": 3, "line": 6},
    ]
    accepted = accept_covers(claims, candidates={2, 3}, kept_ids={4, 5, 6}, speech={0})
    assert accepted == [{"clip": 2, "line": 4}, {"clip": 3, "line": 5}]
    assert set(accepted[0]) == {"clip", "line"}
    # A talking clip is rejected even when it was listed as a candidate.
    assert accept_covers([{"clip": 0, "line": 4}], candidates={0, 2}, kept_ids={4}, speech={0}) == []


def test_schema_and_prompt_have_no_path_or_time():
    props = COVER_SCHEMA["json_schema"]["schema"]["properties"]["covers"]["items"]["properties"]
    assert set(props) == {"clip", "line"}
    clips = [
        {"path": "/secret/room.mp4", "duration": 5},
        {"path": "/secret/talk.mp4", "duration": 8},
    ]
    kept = [
        {
            "id": 4,
            "clip": 1,
            "start": 1.0,
            "end": 3.0,
            "text": "welcome to the product",
            "keep": True,
            "reason": "story",
        }
    ]
    text = cover_user_content(clips, [0], kept, {})
    assert "/secret/room.mp4" not in text
    assert "voice" not in COVER_SYSTEM
    assert "sound" not in COVER_SYSTEM
    assert "voice" not in text
    assert "sound" not in text
    assert "welcome to the product" in text
    assert "clip 0" in text
    assert "5.0s" in text
    assert "1.0" not in text
    assert "3.0" not in text


def test_still_is_one_second_or_the_middle():
    assert broll_still_at(5) == 1.0
    assert broll_still_at(1) == 1.0
    assert broll_still_at(0.4) == pytest.approx(0.2)
    assert broll_still_at(0) == 0


def test_cards_are_not_candidates_and_a_silent_clip_needs_a_spoken_line(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("botcut.broll.post", boom)
    clips = [
        {"path": "/tmp/botcut-card-1-open.mp4", "duration": 3},
        {"path": "/tmp/talk.mp4", "duration": 10},
        {"path": "/tmp/room.mp4", "duration": 8},
    ]
    lines = [
        {"id": 0, "clip": 0, "start": 0, "end": 3, "text": "title", "keep": True, "reason": "card"},
        {"id": 1, "clip": 1, "start": 1, "end": 2, "text": "hello", "keep": True, "reason": "story"},
    ]
    assert candidate_indexes(clips, lines) == [2]
    assert [line["id"] for line in spoken_kept(lines)] == [1]
    dropped = [{"id": 1, "clip": 0, "keep": False, "reason": "dropped", "text": "x", "start": 0, "end": 1}]
    assert candidate_indexes([{"path": "/tmp/a.mp4", "duration": 4}], dropped) == [0]
    assert spoken_kept(dropped) == []
    assert choose_covers([{"path": "/tmp/a.mp4", "duration": 4}], dropped, "/tmp/stills") == []


def test_fake_assigns_in_tray_order_and_skips_the_still(monkeypatch):
    monkeypatch.setenv("BOTCUT_FAKE", "1")

    def boom(*_args, **_kwargs):
        raise AssertionError("grab")

    monkeypatch.setattr("botcut.media.grab_still", boom)
    clips = [
        {"path": "/tmp/talk.mp4", "duration": 8},
        {"path": "/tmp/room.mp4", "duration": 5},
        {"path": "/tmp/extra.mp4", "duration": 5},
    ]
    lines = [
        {"id": 7, "clip": 0, "start": 4, "end": 5, "text": "later", "keep": True, "reason": "story"},
        {"id": 4, "clip": 0, "start": 1, "end": 2, "text": "earlier", "keep": True, "reason": "story"},
    ]
    assert choose_covers(clips, lines, "/tmp/stills") == [
        {"clip": 1, "line": 4},
        {"clip": 2, "line": 7},
    ]


def test_ask_sends_a_still_and_a_bad_body_stays_hidden(monkeypatch, tmp_path):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "secret-key")
    clips = [
        {"path": "/secret/talk.mp4", "duration": 8},
        {"path": "/secret/room.mp4", "duration": 5},
    ]
    lines = [
        {
            "id": 4,
            "clip": 0,
            "start": 1.0,
            "end": 3.0,
            "text": "welcome",
            "keep": True,
            "reason": "story",
        }
    ]
    seen = {}

    class Resp:
        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"covers": [{"clip": 1, "line": 4, "start": 1.25}], "note": "x"}
                            )
                        }
                    }
                ]
            }

    def fake_post(_url, *, key, label, read_timeout, send):
        payload = send()
        seen["body"] = payload["json"]
        seen["key"] = key
        assert label == "LLM"
        assert read_timeout == 120
        return Resp()

    def grab(_video, at, dest):
        seen["at"] = at
        Path(dest).write_bytes(b"jpeg-bytes")
        return True

    monkeypatch.setattr("botcut.broll.post", fake_post)
    monkeypatch.setattr("botcut.media.grab_still", grab)
    assert choose_covers(clips, lines, str(tmp_path)) == [{"clip": 1, "line": 4}]
    blob = json.dumps(seen["body"])
    assert "/secret/room.mp4" not in blob
    assert "secret-key" not in blob
    assert seen["key"] == "secret-key"
    assert seen["at"] == 1.0
    assert (tmp_path / "broll-1.jpg").is_file()
    assert "image_url" in blob

    missed = {"n": 0}

    def miss(_video, _at, _dest):
        return False

    def miss_post(_url, *, key, label, read_timeout, send):
        missed["n"] += 1
        missed["body"] = send()["json"]
        return Resp()

    monkeypatch.setattr("botcut.media.grab_still", miss)
    monkeypatch.setattr("botcut.broll.post", miss_post)
    assert choose_covers(clips, lines, str(tmp_path)) == [{"clip": 1, "line": 4}]
    assert missed["n"] == 1
    missed_blob = json.dumps(missed["body"])
    assert "clip 1" in missed_blob
    assert "welcome" in missed_blob
    assert "image_url" not in missed_blob
    assert "/secret/room.mp4" not in missed_blob

    def bad_post(_url, *, key, label, read_timeout, send):
        class Broken:
            def json(self):
                return {"choices": [{"message": {"content": "nope secret-key /secret/room.mp4"}}]}

        return Broken()

    monkeypatch.setattr("botcut.broll.post", bad_post)
    with pytest.raises(SystemExit, match="not a cover list") as exc:
        choose_covers(clips, lines, str(tmp_path))
    assert "secret-key" not in str(exc.value)
    assert "/secret" not in str(exc.value)


def _windows(**kwargs):
    covers = kwargs["covers"]
    lines = kwargs["lines"]
    segments = kwargs["segments"]
    durations = kwargs["durations"]
    return cover_windows(covers, lines, segments, durations)


def test_window_is_capped_and_stays_on_the_earliest_segment():
    line = {"id": 4, "clip": 0, "start": 1.0, "end": 3.0, "keep": True, "reason": "story"}
    basic = _windows(
        covers=[{"clip": 1, "line": 4}],
        lines=[line],
        segments=[{"clip": 0, "start": 0.25, "end": 8.0}],
        durations=[20, 10],
    )
    assert basic == [{"segment": 0, "start": 1.0, "end": 3.0, "clip": 1}]

    short = _windows(
        covers=[{"clip": 1, "line": 4}],
        lines=[line],
        segments=[{"clip": 0, "start": 0.25, "end": 2.0}],
        durations=[20, 10],
    )
    assert short == [{"segment": 0, "start": 1.0, "end": 2.0, "clip": 1}]

    before = _windows(
        covers=[{"clip": 1, "line": 4}],
        lines=[{**line, "start": 0.2, "end": 3.0}],
        segments=[{"clip": 0, "start": 1.0, "end": 8.0}],
        durations=[20, 10],
    )
    assert before == [{"segment": 0, "start": 1.0, "end": 3.0, "clip": 1}]
    capped = _windows(
        covers=[{"clip": 1, "line": 4}],
        lines=[{**line, "start": 0.0, "end": 8.0}],
        segments=[{"clip": 0, "start": 0.0, "end": 10.0}],
        durations=[20, 10],
    )
    assert capped == [{"segment": 0, "start": 0.0, "end": 4.0, "clip": 1}]

    assert (
        _windows(
            covers=[{"clip": 1, "line": 4}],
            lines=[{**line, "start": 5.0, "end": 6.0}],
            segments=[{"clip": 0, "start": 0.0, "end": 2.0}],
            durations=[20, 10],
        )
        == []
    )
    brief = _windows(
        covers=[{"clip": 1, "line": 4}],
        lines=[{**line, "start": 0.0, "end": 8.0}],
        segments=[{"clip": 0, "start": 0.0, "end": 10.0}],
        durations=[20, 1.5],
    )
    assert brief == [{"segment": 0, "start": 0.0, "end": 1.5, "clip": 1}]

    split = _windows(
        covers=[{"clip": 1, "line": 4}],
        lines=[{**line, "start": 1.0, "end": 6.0}],
        segments=[{"clip": 0, "start": 0.0, "end": 2.0}, {"clip": 0, "start": 4.0, "end": 8.0}],
        durations=[20, 10],
    )
    assert split == [{"segment": 0, "start": 1.0, "end": 2.0, "clip": 1}]

    assert (
        _windows(
            covers=[
                {"clip": 0, "line": 4},
                {"clip": 1, "line": 9},
                {"clip": 1, "line": 8},
                {"clip": 1, "line": 3},
            ],
            lines=[
                line,
                {**line, "id": 8, "keep": False, "reason": "dropped"},
                {**line, "id": 3, "reason": "card"},
            ],
            segments=[{"clip": 0, "start": 0.0, "end": 8.0}],
            durations=[20, 10],
        )
        == []
    )


def test_overlapping_windows_shrink_and_one_can_drop():
    lines = [
        {"id": 4, "clip": 0, "start": 1.0, "end": 2.0, "keep": True, "reason": "story"},
        {"id": 5, "clip": 0, "start": 2.0, "end": 4.0, "keep": True, "reason": "story"},
    ]
    both = _windows(
        covers=[{"clip": 2, "line": 4}, {"clip": 3, "line": 5}],
        lines=lines,
        segments=[{"clip": 0, "start": 0.0, "end": 10.0}],
        durations=[10, 10, 10, 10],
    )
    assert both == [
        {"segment": 0, "start": 1.0, "end": 2.0, "clip": 2},
        {"segment": 0, "start": 2.0, "end": 4.0, "clip": 3},
    ]
    crowded = _windows(
        covers=[{"clip": 2, "line": 4}, {"clip": 3, "line": 5}],
        lines=[lines[0], {**lines[1], "start": 1.2, "end": 1.6}],
        segments=[{"clip": 0, "start": 0.0, "end": 10.0}],
        durations=[10, 10, 10, 0.5],
    )
    assert crowded == [{"segment": 0, "start": 1.0, "end": 2.0, "clip": 2}]


def _timed(args):
    found = []
    i = 0
    while i < len(args) - 5:
        if args[i] == "-ss" and args[i + 2] == "-t" and args[i + 4] == "-i":
            found.append((args[i + 1], args[i + 3], args[i + 5]))
            i += 6
            continue
        i += 1
    return found


def _talk_room():
    talk = {"path": "/tmp/talk.mp4", "duration": 20, "width": 1920, "height": 1080, "fps": 30.0}
    room = {"path": "/tmp/room.mp4", "duration": 10, "width": 1280, "height": 720, "fps": 30.0}
    return talk, room


def test_render_plays_broll_sound_then_returns_to_the_speaker():
    talk, room = _talk_room()
    segs = [{"clip": 0, "start": 0.25, "end": 8.0, "reason": "story"}]
    lines = [
        {"id": 4, "clip": 0, "start": 1.0, "end": 3.0, "keep": True, "reason": "story", "text": "hello"}
    ]
    covers = [{"clip": 1, "line": 4}]
    args = render_args(
        segs, [talk, room], "/tmp/out.mp4", polish=True, covers=covers, lines=lines, broll_sound="clip"
    )
    assert _timed(args) == [
        ("0.250", "0.750", "/tmp/talk.mp4"),
        ("0.000", "2.000", "/tmp/room.mp4"),
        ("3.000", "5.000", "/tmp/talk.mp4"),
    ]
    branches = args[args.index("-filter_complex") + 1].split(";")
    cover_v = next(branch for branch in branches if branch.startswith("[1:v]"))
    cover_a = next(branch for branch in branches if branch.startswith("[1:a]"))
    back_v = next(branch for branch in branches if branch.startswith("[2:v]"))
    back_a = next(branch for branch in branches if branch.startswith("[2:a]"))
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in cover_v
    assert "scale=1280:720" not in cover_v
    assert "afade" not in cover_a
    assert "fade=t=in" not in back_v
    assert "afade=t=in" not in back_a
    assert "concat=n=3:v=1:a=1" in branches[-1]
    graph = args[args.index("-filter_complex") + 1]
    assert "loudnorm" not in graph
    assert "amix" not in graph
    assert "volume=0.25" not in graph
    stale = render_args(
        segs,
        [talk, room],
        "/tmp/out.mp4",
        polish=True,
        covers=[{"clip": 1, "line": 99}],
        lines=lines,
        broll_sound="clip",
    )
    assert stale == render_args(segs, [talk, room], "/tmp/out.mp4", polish=True)


def test_cover_boundary_is_not_a_scene_change():
    talk, room = _talk_room()
    other = {"path": "/tmp/other.mp4", "duration": 10, "width": 1920, "height": 1080, "fps": 30.0}
    clips = [talk, room, other]
    segs = [
        {"clip": 0, "start": 0.0, "end": 6.0, "reason": "story"},
        {"clip": 2, "start": 0.0, "end": 2.0, "reason": "story"},
    ]
    lines = [{"id": 4, "clip": 0, "start": 0.0, "end": 2.0, "keep": True, "reason": "story", "text": "hi"}]
    args = render_args(
        segs,
        clips,
        "/tmp/out.mp4",
        polish=True,
        covers=[{"clip": 1, "line": 4}],
        lines=lines,
        broll_sound="clip",
    )
    assert _timed(args) == [
        ("0.000", "2.000", "/tmp/room.mp4"),
        ("2.000", "4.000", "/tmp/talk.mp4"),
        ("0.000", "2.000", "/tmp/other.mp4"),
    ]
    branches = args[args.index("-filter_complex") + 1].split(";")
    cover_v = next(branch for branch in branches if branch.startswith("[0:v]"))
    cover_a = next(branch for branch in branches if branch.startswith("[0:a]"))
    back_v = next(branch for branch in branches if branch.startswith("[1:v]"))
    back_a = next(branch for branch in branches if branch.startswith("[1:a]"))
    assert "fade=t=in:st=0:d=0.500" in cover_v
    assert "fade=t=out" not in cover_v
    assert "afade=t=in:st=0:d=0.020" in cover_a
    assert "afade=t=out" not in cover_a
    assert "fade=t=out:st=3.820:d=0.180" in back_v
    assert "fade=t=in" not in back_v
    assert "afade=t=out:st=3.880:d=0.120" in back_a
    assert "afade=t=in" not in back_a
    assert "amix" not in args[args.index("-filter_complex") + 1]
    assert "volume=0.25" not in args[args.index("-filter_complex") + 1]

    for clip in clips:
        clip["pix_fmt"] = "yuv420p"
    va = render_args(
        segs,
        clips,
        "/tmp/out.mp4",
        encoder="vaapi",
        device="/dev/dri/renderD128",
        polish=True,
        covers=[{"clip": 1, "line": 4}],
        lines=lines,
        broll_sound="clip",
    )
    inputs = []
    hw = False
    index = 0
    while index < len(va):
        if va[index] == "-hwaccel":
            hw = True
        elif va[index] == "-i" and index + 1 < len(va):
            inputs.append((va[index + 1], hw))
            hw = False
            index += 1
        index += 1
    assert inputs == [
        ("/tmp/room.mp4", True),
        ("/tmp/talk.mp4", True),
        ("/tmp/other.mp4", True),
    ]
    va_branches = va[va.index("-filter_complex") + 1].split(";")
    video_branches = [branch for branch in va_branches if branch.startswith("[") and ":v]" in branch[:8]]
    assert len(video_branches) == 3
    assert all("hwdownload" in branch for branch in video_branches)
    assert "scale_vaapi=1920:1080" in video_branches[0]
    assert "amix" not in va[va.index("-filter_complex") + 1]
    assert "volume=0.25" not in va[va.index("-filter_complex") + 1]


def _mean_volume(path, start, length, audio_filter):
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{length:.3f}",
            "-i",
            str(path),
            "-vn",
            "-af",
            audio_filter,
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]
    match = re.search(r"mean_volume:\s*(-inf|-?\d+(?:\.\d+)?) dB", proc.stderr)
    assert match, proc.stderr[-400:]
    if match.group(1) == "-inf":
        return -999.0
    return float(match.group(1))


def test_cover_graph_encodes(tmp_path):
    def clip(path, size, tone):
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=size={size}:rate=30",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={tone}:sample_rate=48000",
                "-t",
                "3",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr[-400:]

    talk = tmp_path / "talk.mp4"
    room = tmp_path / "room.mp4"
    clip(talk, "640x360", 220)
    clip(room, "320x180", 1760)
    clips = [
        {"path": str(talk), "duration": 3, "width": 640, "height": 360, "fps": 30.0, "pix_fmt": "yuv420p"},
        {"path": str(room), "duration": 3, "width": 320, "height": 180, "fps": 30.0, "pix_fmt": "yuv420p"},
    ]
    segs = [{"clip": 0, "start": 0.0, "end": 2.5, "reason": "story"}]
    lines = [{"id": 4, "clip": 0, "start": 0.5, "end": 1.2, "keep": True, "reason": "story", "text": "hi"}]
    dst = tmp_path / "out.mp4"
    args = render_args(
        segs, clips, str(dst), polish=True, covers=[{"clip": 1, "line": 4}], lines=lines, broll_sound="clip"
    )
    graph = args[args.index("-filter_complex") + 1]
    assert "amix" not in graph
    assert "volume=0.25" not in graph
    assert "loudnorm" not in graph
    proc = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert dst.stat().st_size > 0
    talk_band = "lowpass=f=400,volumedetect"
    room_band = "highpass=f=1000,volumedetect"
    assert _mean_volume(dst, 0.10, 0.30, talk_band) > -30
    assert _mean_volume(dst, 0.10, 0.30, room_band) < -45
    assert _mean_volume(dst, 0.65, 0.40, room_band) > -30
    assert _mean_volume(dst, 0.65, 0.40, talk_band) < -45
    assert _mean_volume(dst, 1.45, 0.40, talk_band) > -30
    assert _mean_volume(dst, 1.45, 0.40, room_band) < -45


def test_render_mixes_the_clip_under_the_voice():
    talk, room = _talk_room()
    segs = [{"clip": 0, "start": 0.25, "end": 8.0, "reason": "story"}]
    lines = [
        {"id": 4, "clip": 0, "start": 1.0, "end": 3.0, "keep": True, "reason": "story", "text": "hello"}
    ]
    covers = [{"clip": 1, "line": 4}]
    args = render_args(segs, [talk, room], "/tmp/out.mp4", polish=True, covers=covers, lines=lines)
    assert _timed(args) == [
        ("0.250", "0.750", "/tmp/talk.mp4"),
        ("0.000", "2.000", "/tmp/room.mp4"),
        ("1.000", "2.000", "/tmp/talk.mp4"),
        ("3.000", "5.000", "/tmp/talk.mp4"),
    ]
    graph = args[args.index("-filter_complex") + 1]
    assert graph.count("volume=0.25") == 1
    assert graph.count("amix=inputs=2:duration=first:dropout_transition=0:normalize=0") == 1
    assert "loudnorm" not in graph
    branches = graph.split(";")
    volume = next(branch for branch in branches if "volume=0.25" in branch)
    mixed = next(branch for branch in branches if "amix=" in branch)
    assert volume.startswith("[1:a]volume=0.25")
    assert "afade" not in volume
    assert "amix" not in volume
    assert mixed.startswith("[2:a]")
    assert "afade" not in mixed
    assert mixed.index("amix=") < mixed.index("aresample=")
    cover_v = next(branch for branch in branches if branch.startswith("[1:v]"))
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in cover_v
    assert not any(branch.startswith("[2:v]") for branch in branches)
    back_a = next(branch for branch in branches if branch.startswith("[3:a]"))
    assert back_a.startswith("[3:a]aresample=osr=48000")
    assert "amix" not in back_a
    assert "volume=" not in back_a
    assert "concat=n=3:v=1:a=1" in branches[-1]
    stale = render_args(
        segs,
        [talk, room],
        "/tmp/out.mp4",
        polish=True,
        covers=[{"clip": 1, "line": 99}],
        lines=lines,
    )
    assert stale == render_args(segs, [talk, room], "/tmp/out.mp4", polish=True)
    assert "amix" not in stale[stale.index("-filter_complex") + 1]

    other = {"path": "/tmp/other.mp4", "duration": 10, "width": 1920, "height": 1080, "fps": 30.0}
    edge_clips = [talk, room, other]
    edge_segs = [
        {"clip": 0, "start": 0.0, "end": 6.0, "reason": "story"},
        {"clip": 2, "start": 0.0, "end": 2.0, "reason": "story"},
    ]
    edge_lines = [
        {"id": 4, "clip": 0, "start": 0.0, "end": 2.0, "keep": True, "reason": "story", "text": "hi"}
    ]
    edge = render_args(
        edge_segs,
        edge_clips,
        "/tmp/out.mp4",
        polish=True,
        covers=[{"clip": 1, "line": 4}],
        lines=edge_lines,
        broll_sound="mix",
    )
    assert _timed(edge) == [
        ("0.000", "2.000", "/tmp/room.mp4"),
        ("0.000", "2.000", "/tmp/talk.mp4"),
        ("2.000", "4.000", "/tmp/talk.mp4"),
        ("0.000", "2.000", "/tmp/other.mp4"),
    ]
    edge_graph = edge[edge.index("-filter_complex") + 1]
    edge_branches = edge_graph.split(";")
    edge_volume = next(branch for branch in edge_branches if "volume=0.25" in branch)
    edge_mix = next(branch for branch in edge_branches if "amix=" in branch)
    assert edge_volume == "[0:a]volume=0.25[b0]"
    assert "afade" not in edge_volume
    assert edge_mix.startswith("[1:a]")
    assert edge_mix.index("amix=") < edge_mix.index("afade=")
    assert edge_mix.count("afade=") == 1
    assert "afade=t=in:st=0:d=0.020" in edge_mix
    assert "afade=t=out" not in edge_mix
    edge_v = next(branch for branch in edge_branches if branch.startswith("[0:v]"))
    edge_back_v = next(branch for branch in edge_branches if branch.startswith("[2:v]"))
    edge_back_a = next(branch for branch in edge_branches if branch.startswith("[2:a]"))
    assert "fade=t=in:st=0:d=0.500" in edge_v
    assert "fade=t=out" not in edge_v
    assert "fade=t=out:st=3.820:d=0.180" in edge_back_v
    assert "fade=t=in" not in edge_back_v
    assert "afade=t=out:st=3.880:d=0.120" in edge_back_a
    assert "afade=t=in" not in edge_back_a
    assert "loudnorm" not in edge_graph

    for clip in edge_clips:
        clip["pix_fmt"] = "yuv420p"
    va = render_args(
        edge_segs,
        edge_clips,
        "/tmp/out.mp4",
        encoder="vaapi",
        device="/dev/dri/renderD128",
        polish=True,
        covers=[{"clip": 1, "line": 4}],
        lines=edge_lines,
        broll_sound="mix",
    )
    inputs = []
    hw = False
    index = 0
    while index < len(va):
        if va[index] == "-hwaccel":
            hw = True
        elif va[index] == "-i" and index + 1 < len(va):
            inputs.append((va[index + 1], hw))
            hw = False
            index += 1
        index += 1
    assert inputs == [
        ("/tmp/room.mp4", True),
        ("/tmp/talk.mp4", False),
        ("/tmp/talk.mp4", True),
        ("/tmp/other.mp4", True),
    ]
    va_branches = va[va.index("-filter_complex") + 1].split(";")
    video_branches = [branch for branch in va_branches if branch.startswith("[") and ":v]" in branch[:8]]
    assert len(video_branches) == 3
    assert all("hwdownload" in branch for branch in video_branches)
    assert "scale_vaapi=1920:1080" in video_branches[0]
    assert not any(branch.startswith("[1:v]") for branch in va_branches)


def test_mix_graph_encodes(tmp_path):
    def clip(path, size, tone):
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=size={size}:rate=30",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={tone}:sample_rate=48000",
                "-t",
                "3",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr[-400:]

    talk = tmp_path / "talk.mp4"
    room = tmp_path / "room.mp4"
    clip(talk, "640x360", 220)
    clip(room, "320x180", 1760)
    clips = [
        {"path": str(talk), "duration": 3, "width": 640, "height": 360, "fps": 30.0, "pix_fmt": "yuv420p"},
        {"path": str(room), "duration": 3, "width": 320, "height": 180, "fps": 30.0, "pix_fmt": "yuv420p"},
    ]
    segs = [{"clip": 0, "start": 0.0, "end": 2.5, "reason": "story"}]
    lines = [{"id": 4, "clip": 0, "start": 0.5, "end": 1.2, "keep": True, "reason": "story", "text": "hi"}]
    dst = tmp_path / "mixed.mp4"
    args = render_args(segs, clips, str(dst), polish=True, covers=[{"clip": 1, "line": 4}], lines=lines)
    graph = args[args.index("-filter_complex") + 1]
    assert "volume=0.25" in graph
    assert "amix=inputs=2:duration=first:dropout_transition=0:normalize=0" in graph
    assert "loudnorm" not in graph
    proc = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    talk_band = "lowpass=f=400,volumedetect"
    room_band = "highpass=f=1000,volumedetect"
    assert _mean_volume(dst, 0.10, 0.30, talk_band) > -30
    assert _mean_volume(dst, 0.10, 0.30, room_band) < -45
    assert _mean_volume(dst, 0.65, 0.40, talk_band) > -30
    # volume=0.25 sits under a full-scale -30 and still well above silence.
    assert _mean_volume(dst, 0.65, 0.40, room_band) > -38
    assert _mean_volume(dst, 1.45, 0.40, talk_band) > -30
    assert _mean_volume(dst, 1.45, 0.40, room_band) < -45


def test_unknown_broll_sound_is_rejected(capsys):
    # Argparse prints the choice error and raises SystemExit(2). The text is not on the exception.
    with pytest.raises(SystemExit) as render_exit:
        main(["render", "out", "--b-roll-sound", "silent"])
    assert render_exit.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    with pytest.raises(SystemExit) as run_exit:
        main(["run", "a.mp4", "--out", "out", "--b-roll-sound", "silent"])
    assert run_exit.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    with pytest.raises(SystemExit, match="Unknown b-roll sound"):
        render_args(
            [{"clip": 0, "start": 0.0, "end": 1.0}],
            [{"path": "/tmp/a.mp4", "width": 16, "height": 16, "fps": 30.0}],
            "/tmp/out.mp4",
            broll_sound="silent",
        )


def test_main_passes_clip_sound_to_render_saved(monkeypatch):
    seen = {}

    def fake_render(cuts, scene_transition="dip", broll_sound="mix"):
        seen["cuts"] = cuts
        seen["sound"] = broll_sound
        seen["transition"] = scene_transition

    monkeypatch.setattr("botcut.cli.render_saved", fake_render)
    main(["render", "out", "--b-roll-sound", "clip"])
    assert seen == {"cuts": "out", "sound": "clip", "transition": "dip"}


def test_assemble_with_broll_writes_no_covers(monkeypatch, tmp_path):
    def boom(*_args, **_kwargs):
        raise AssertionError("choose_covers")

    monkeypatch.setattr("botcut.cli.choose_covers", boom)
    monkeypatch.setattr(
        "botcut.cli.probe",
        lambda path: {
            "path": path,
            "duration": 1.0,
            "width": 320,
            "height": 180,
            "fps": 30.0,
            "rotate": 0,
            "pix_fmt": "yuv420p",
        },
    )
    seen = {}

    def fake_render(*_args, **kwargs):
        seen["sound"] = kwargs.get("broll_sound")

    monkeypatch.setattr("botcut.cli.render_with_progress", fake_render)
    silent = tmp_path / "silent.mp4"
    silent.write_bytes(b"")
    run([str(silent)], str(tmp_path / "out"), mode="assemble", broll=True, broll_sound="clip")
    doc = json.loads((tmp_path / "out" / "cuts.json").read_text())
    assert "covers" not in doc
    assert "broll_sound" not in doc
    assert doc["mode"] == "assemble"
    assert seen["sound"] == "clip"


def test_fake_cut_writes_a_cover_only_when_asked(monkeypatch, tmp_path):
    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr("botcut.net.requests.post", boom)
    calls = {"n": 0}

    def sequenced():
        calls["n"] += 1
        if calls["n"] % 2 == 1:
            return transcribe_fake()
        return {"duration": 4.0, "words": []}

    monkeypatch.setattr("botcut.cli.transcribe_fake", sequenced)

    def make(path):
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=320x180:rate=30",
                "-f",
                "lavfi",
                "-i",
                "sine=f=440",
                "-t",
                "4",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr[-400:]

    talk = tmp_path / "talk.mp4"
    room = tmp_path / "room.mp4"
    make(talk)
    make(room)
    off = tmp_path / "off"
    run([str(talk), str(room)], str(off), decide=True, broll=False)
    off_doc = json.loads((off / "cuts.json").read_text())
    assert "covers" not in off_doc

    on = tmp_path / "on"
    run([str(talk), str(room)], str(on), decide=True, broll=True)
    on_doc = json.loads((on / "cuts.json").read_text())
    assert on_doc["covers"] == [{"clip": 1, "line": 0}]
    assert set(on_doc["covers"][0]) == {"clip", "line"}


def test_render_saved_keeps_covers(monkeypatch, tmp_path):
    seen = {"calls": []}

    def fake_render(*_args, **kwargs):
        seen["calls"].append(
            {
                "covers": kwargs.get("covers"),
                "lines": kwargs.get("lines"),
                "broll_sound": kwargs.get("broll_sound"),
            }
        )

    monkeypatch.setattr("botcut.cli.render_with_progress", fake_render)
    monkeypatch.setattr(
        "botcut.cli.probe",
        lambda path: {
            "path": path,
            "duration": 12.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "rotate": 0,
            "pix_fmt": "yuv420p",
        },
    )
    out = tmp_path / "out"
    out.mkdir()
    doc = {
        "version": 1,
        "clips": [
            {"index": 0, "path": "/tmp/talk.mp4", "duration": 12},
            {"index": 1, "path": "/tmp/room.mp4", "duration": 8},
        ],
        "lines": [
            {"id": 4, "clip": 0, "start": 1.0, "end": 3.0, "text": "hi", "keep": True, "reason": "story"}
        ],
        "segments": [{"clip": 0, "start": 0.25, "end": 8.0, "reason": "story"}],
        "covers": [{"clip": 1, "line": 4}],
        "tighten": {"max_pause": 0.8, "snap": False},
        "trimmed": True,
    }
    path = out / "cuts.json"
    path.write_text(json.dumps(doc) + "\n")
    render_saved(str(out))
    assert json.loads(path.read_text())["covers"] == [{"clip": 1, "line": 4}]

    doc.pop("trimmed")
    path.write_text(json.dumps(doc) + "\n")
    render_saved(str(out))
    saved = json.loads(path.read_text())
    assert saved["covers"] == [{"clip": 1, "line": 4}]
    assert saved["segments"] == [{"clip": 0, "start": 0.75, "end": 3.4, "reason": "story"}]
    assert len(seen["calls"]) == 2
    for call in seen["calls"]:
        assert call["covers"] == [{"clip": 1, "line": 4}]
        assert call["broll_sound"] == "mix"
        assert call["lines"][0]["id"] == 4
        assert call["lines"][0]["start"] == 1.0
        assert call["lines"][0]["end"] == 3.0
    assert "broll_sound" not in saved
    render_saved(str(out), broll_sound="clip")
    assert seen["calls"][-1]["broll_sound"] == "clip"
    assert seen["calls"][-1]["covers"] == [{"clip": 1, "line": 4}]
    assert set(json.loads(path.read_text())["covers"][0]) == {"clip", "line"}


def test_revise_drops_a_cover_when_it_drops_the_line(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    lines = [
        {"id": 1, "clip": 0, "start": 0.2, "end": 1.2, "text": "keep me", "keep": True, "reason": "story"},
        {"id": 2, "clip": 0, "start": 1.4, "end": 2.4, "text": "drop me", "keep": True, "reason": "story"},
    ]
    doc = {
        "version": 1,
        "mode": "speech",
        "intent": "A quiet ride",
        "tighten": {"max_pause": 0.8, "snap": True},
        "clips": [{"index": 0, "path": "/tmp/a.mp4", "duration": 10}],
        "segments": [{"clip": 0, "start": 0.0, "end": 4.0, "reason": "story"}],
        "lines": lines,
        "dropped": [],
        "covers": [{"clip": 3, "line": 1}, {"clip": 4, "line": 2}],
    }
    path = tmp_path / "cuts.json"
    path.write_text(json.dumps(doc) + "\n")
    revise(str(path), "shorter")
    saved = json.loads(path.read_text())
    assert saved["covers"] == [{"clip": 3, "line": 1}]
    assert saved["lines"][0]["keep"] is True
    assert saved["lines"][1]["keep"] is False
    assert [row["id"] for row in saved["lines"]] == [1, 2]
