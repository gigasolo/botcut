"""Punch-ins on jump cuts, and a short that follows the speaker."""

import json
import subprocess

from botcut import cli
from botcut.frame import (
    DEFAULT_FOCUS,
    ask_face,
    find_faces,
    focus,
    parse_face,
    punch_crop,
    punched,
    vertical_left,
)
from botcut.media import render_args
from botcut.short import short_args


def _clip(path="/tmp/a.mp4", width=1920, height=1080, **more):
    return {"path": path, "width": width, "height": height, "fps": 30.0, "duration": 20.0, **more}


def test_a_face_must_be_a_box_inside_the_picture():
    assert parse_face({"found": True, "x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3}) == {
        "x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3,
    }
    for bad in (
        {"found": False, "x": 0, "y": 0, "w": 0, "h": 0},
        {"found": True, "x": 0.9, "y": 0.2, "w": 0.3, "h": 0.3},
        {"found": True, "x": -0.1, "y": 0.2, "w": 0.2, "h": 0.3},
        {"found": True, "x": 0.4, "y": 0.2, "w": 0.0, "h": 0.3},
        {"found": True, "x": "left", "y": 0.2, "w": 0.2, "h": 0.3},
        {"found": True, "x": 0.4},
        "a face",
    ):
        assert parse_face(bad) is None


def test_the_frame_holds_on_the_face_or_where_a_talking_head_sits():
    assert focus(_clip(face={"x": 0.6, "y": 0.1, "w": 0.2, "h": 0.3})) == (0.7, 0.25)
    assert focus(_clip()) == DEFAULT_FOCUS
    assert focus(_clip(face={"x": 2, "y": 0, "w": 1, "h": 1})) == DEFAULT_FOCUS


def test_the_punch_in_is_a_crop_around_the_speaker_that_stays_in_the_picture():
    # 1920 / 1.12 = 1714, 1080 / 1.12 = 964, both even. Centered on the face at (0.5, 0.35).
    assert punch_crop(_clip(face={"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3})) == "crop=1714:964:103:0"
    # A speaker at the right edge: the crop stops at the edge and does not show black.
    assert punch_crop(_clip(face={"x": 0.85, "y": 0.6, "w": 0.15, "h": 0.3})) == "crop=1714:964:206:116"


def test_jump_cuts_alternate_wide_and_tight_and_a_new_shot_starts_wide():
    clips = [_clip("/tmp/a.mp4"), _clip("/tmp/b.mp4"), _clip("/tmp/small.mp4", 1280, 720)]
    segs = [{"clip": c, "start": float(i), "end": i + 0.9} for i, c in enumerate([0, 0, 0, 1, 1, 0, 2, 2])]
    plain = lambda clip: True
    #                                    a      a     a      b      b     a      small  small
    assert punched(segs, clips, plain) == [False, True, False, False, True, False, False, False]
    # A shot that may not be punched in, such as B-roll or a card, never is.
    assert punched(segs, clips, lambda clip: False) == [False] * 8


def test_the_render_punches_in_only_the_speaker_and_only_when_asked():
    clips = [
        _clip("/tmp/talk.mp4", face={"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3}),
        _clip("/tmp/room.mp4", role="broll"),
    ]
    segs = [
        {"clip": 0, "start": 0.0, "end": 4.0, "reason": "a"},
        {"clip": 0, "start": 6.0, "end": 14.0, "reason": "b"},
    ]
    lines = [
        {"id": 0, "clip": 0, "start": 0.0, "end": 4.0, "keep": True, "text": "a"},
        {"id": 1, "clip": 0, "start": 6.0, "end": 8.0, "keep": True, "text": "b"},
        {"id": 2, "clip": 0, "start": 8.0, "end": 12.0, "keep": True, "text": "c"},
        {"id": 3, "clip": 0, "start": 12.0, "end": 14.0, "keep": True, "text": "d"},
    ]
    covers = [{"clip": 1, "line": 2, "through": 2, "start": 0.0, "end": 4.0, "reason": "shows it"}]

    def graph(**more):
        args = render_args(segs, clips, "/tmp/o.mp4", covers=covers, lines=lines, **more)
        return args[args.index("-filter_complex") + 1], args

    plain, _ = graph()
    assert "crop=" not in plain
    tight, _ = graph(punch_in=True)
    branches = [part for part in tight.split(";") if ":v]" in part]
    # First piece wide. After the jump: the speaker tight, the B-roll as shot, the speaker tight again.
    assert [("crop=1714:964:103:0" in part) for part in branches] == [False, True, False, True]
    # On VA-API the punched-in pieces are decoded in software, where the crop runs.
    _, args = graph(punch_in=True, encoder="vaapi", device="/dev/dri/renderD128")
    assert args.count("-hwaccel") < len(branches)


def test_a_punched_in_cut_encodes_at_the_same_size(tmp_path):
    src = tmp_path / "talk.mp4"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=s=1920x1080:r=30:d=4",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "4",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]
    clips = [_clip(str(src), duration=4.0, face={"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3})]
    segs = [
        {"clip": 0, "start": 0.2, "end": 1.4, "reason": "a"},
        {"clip": 0, "start": 2.2, "end": 3.6, "reason": "b"},
    ]
    out = tmp_path / "out.mp4"
    args = render_args(segs, clips, str(out), polish=True, punch_in=True)
    proc = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(out)],
        capture_output=True, text=True,
    )
    assert probe.stdout.strip() == "1920,1080"


def test_the_short_is_cropped_around_the_speaker():
    # A 1920 wide frame cropped to 9:16 is 606 wide. Centered on 0.7 it starts at 1041.
    assert vertical_left(1920, 1080, 0.7) == 1041
    assert vertical_left(1920, 1080, 0.02) == 0
    assert vertical_left(1920, 1080, 0.99) == 1314
    follows = short_args(1.0, 30.0, 1920, 1080, center=0.7)
    assert "crop=ih*9/16:ih:1041:0" in follows[follows.index("-vf") + 1]
    middle = short_args(1.0, 30.0, 1920, 1080)
    assert "crop=ih*9/16:ih," in middle[middle.index("-vf") + 1]

    doc = {
        "lines": [{"id": 0, "clip": 0}, {"id": 1, "clip": 1}],
        "clips": [
            {"index": 0, "path": "/tmp/a.mp4"},
            {"index": 1, "path": "/tmp/b.mp4", "face": {"x": 0.6, "y": 0.1, "w": 0.2, "h": 0.3}},
        ],
    }
    assert cli._short_center(doc, 1) == 0.7
    # A shot with no face found keeps the crop in the middle.
    assert cli._short_center(doc, 0) is None


def test_faces_are_asked_for_once_per_spoken_shot_and_never_stop_a_cut(monkeypatch, tmp_path):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "secret")
    asked = []

    def grab(video, at, dest):
        open(dest, "wb").write(b"jpeg")
        return True

    monkeypatch.setattr("botcut.media.grab_still", grab)

    class Reply:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(
                {"found": True, "x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3})}}]}

    def post(url, headers=None, json=None, timeout=None):
        asked.append(json)
        return Reply()

    monkeypatch.setattr("botcut.net.requests.post", post)
    clips = [_clip(str(tmp_path / "talk.mp4")), _clip(str(tmp_path / "room.mp4"), role="broll")]
    spoken = lambda clip: clip.get("role") != "broll"
    find_faces(str(tmp_path / "work"), clips, spoken)
    assert clips[0]["face"] == {"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3}
    assert "face" not in clips[1]
    assert len(asked) == 1
    # One picture is sent, with a strict shape to answer in, and no times.
    body = asked[0]
    assert body["response_format"]["json_schema"]["strict"] is True
    assert [part["type"] for part in body["messages"][0]["content"]] == ["text", "image_url"]

    # A second run reads what the first one found.
    again = [_clip(str(tmp_path / "talk.mp4"))]
    find_faces(str(tmp_path / "work"), again, spoken)
    assert again[0]["face"] == clips[0]["face"]
    assert len(asked) == 1

    # The service being down, or answering with nonsense, leaves the frame on the middle.
    def down(*_a, **_k):
        raise __import__("requests").ConnectionError("down")

    monkeypatch.setattr("botcut.net.requests.post", down)
    monkeypatch.setattr("botcut.net.time.sleep", lambda _s: None)
    still = tmp_path / "still.jpg"
    still.write_bytes(b"jpeg")
    assert ask_face(str(still)) is None
