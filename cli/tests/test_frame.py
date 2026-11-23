"""The zoom on the speaker, and a short that follows the speaker."""

import json
import subprocess

from botcut import cli
from botcut.frame import (
    DEFAULT_FOCUS,
    ask_face,
    close_ids,
    close_spans,
    find_faces,
    focus,
    inside_a_line,
    parse_face,
    punch_crop,
    punched,
    push_filter,
    push_starts,
    split_close,
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


def _said(uid, start, end, keep=True):
    return {"id": uid, "clip": 0, "start": start, "end": end, "keep": keep, "text": f"line {uid}", "reason": "ok"}


def test_a_cut_inside_a_line_is_told_from_a_join_between_lines():
    lines = [_said(0, 0.0, 6.0), _said(1, 8.0, 12.0)]
    # An "um" taken out of line 0 at 2.0-2.5.
    assert inside_a_line({"clip": 0, "start": 0.0, "end": 2.0}, {"clip": 0, "start": 2.5, "end": 6.4}, lines)
    # Line 0 ends, line 1 begins.
    assert not inside_a_line({"clip": 0, "start": 2.5, "end": 6.4}, {"clip": 0, "start": 7.75, "end": 12.4}, lines)
    assert not inside_a_line({"clip": 0, "start": 0.0, "end": 2.0}, {"clip": 1, "start": 2.5, "end": 6.0}, lines)
    assert not inside_a_line({"clip": 0, "start": 0.0, "end": 2.0}, {"clip": 0, "start": 2.5, "end": 6.0}, None)
    # A filler at the very end of a line sits on the line's edge. It is still a cut inside the line.
    edge = [{**_said(0, 1.6, 4.74), "cuts": [{"from": 5, "through": 5, "start": 4.34, "end": 4.74, "cut": True}]}]
    assert inside_a_line({"clip": 0, "start": 1.35, "end": 4.34}, {"clip": 0, "start": 4.74, "end": 9.9}, edge)
    edge[0]["cuts"][0]["cut"] = False
    assert not inside_a_line({"clip": 0, "start": 1.35, "end": 4.34}, {"clip": 0, "start": 4.74, "end": 9.9}, edge)


def test_the_zoom_on_cuts_changes_between_lines_once_a_framing_has_been_held():
    clips = [_clip("/tmp/a.mp4"), _clip("/tmp/b.mp4"), _clip("/tmp/small.mp4", 1280, 720)]
    plain = lambda clip: True
    # Five seconds each, every join between lines: wide and tight take turns, and a new shot starts wide.
    long = [{"clip": c, "start": i * 10.0, "end": i * 10.0 + 5.0} for i, c in enumerate([0, 0, 0, 1, 1, 0, 2, 2])]
    #                                    a      a     a      b      b     a      small  small
    assert punched(long, clips, plain) == [False, True, False, False, True, False, False, False]
    # A shot that may not be zoomed, such as B-roll or a card, never is.
    assert punched(long, clips, lambda clip: False) == [False] * 8
    # Pieces under a second: the framing waits until it has been held four seconds.
    quick = [{"clip": 0, "start": float(i), "end": i + 0.9} for i in range(8)]
    assert punched(quick, clips, plain) == [False, False, False, False, False, True, True, True]
    # A cut inside a line never changes the framing, however long it has been held.
    lines = [_said(0, 0.0, 12.0), _said(1, 14.0, 20.0)]
    pieces = [
        {"clip": 0, "start": 0.0, "end": 5.0},
        {"clip": 0, "start": 5.5, "end": 12.4},
        {"clip": 0, "start": 13.75, "end": 20.4},
    ]
    assert punched(pieces, clips, plain, lines) == [False, False, True]
    assert punched(pieces, clips, plain) == [False, True, False]


def test_the_slow_push_starts_wide_at_a_join_and_carries_on_across_a_cut_inside_a_line():
    lines = [_said(0, 0.0, 12.0), _said(1, 14.0, 20.0)]
    pieces = [
        {"clip": 0, "start": 0.0, "end": 5.0},
        {"clip": 0, "start": 5.5, "end": 12.4},
        {"clip": 0, "start": 13.75, "end": 20.4},
    ]
    assert push_starts(pieces, lines) == [0.0, 5.0, 0.0]
    assert push_starts(pieces) == [0.0, 0.0, 0.0]
    move = push_filter(_clip(face={"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3}), 5.0)
    # Half a percent a second from where it had got to, never past eight percent, toward the face.
    assert "min(1+0.005*(on/30+5.000),1.08)" in move
    assert move.startswith("perspective=x0='W*0.5000*(1-1/(")
    assert "y0='H*0.3500*(1-1/(" in move
    assert move.endswith(":sense=source:eval=frame:interpolation=cubic")


def test_a_line_shown_close_is_cut_out_of_the_piece_it_sits_in():
    lines = [_said(0, 0.0, 4.0), _said(1, 4.6, 9.0), _said(2, 9.6, 14.0), _said(3, 20.0, 24.0, keep=False)]
    # Dropped, unknown and repeated ids are not shown close.
    assert close_ids([1, 3, 99, 1, True, "2"], lines) == [1]
    assert close_ids(None, lines) == []
    # The line with its lead and tail, and never past the middle of the air to a neighbour.
    assert close_spans(lines, [1]) == {0: [(4.35, 9.3)]}
    piece = {"clip": 0, "start": 0.0, "end": 14.4}
    parts = split_close(piece, [(4.35, 9.3)])
    assert [(part["start"], part["end"], bool(part.get("tight"))) for part in parts] == [
        (0.0, 4.35, False),
        (4.35, 9.3, True),
        (9.3, 14.4, False),
    ]
    # A sliver is not split off: the piece that ends just after the line is all close.
    short = split_close({"clip": 0, "start": 4.2, "end": 9.5}, [(4.35, 9.3)])
    assert [(part["start"], part["end"], bool(part.get("tight"))) for part in short] == [(4.2, 9.5, True)]
    # A piece the line is not in is left whole and wide.
    away = split_close({"clip": 0, "start": 10.0, "end": 14.0}, [(4.35, 9.3)])
    assert away == [{"clip": 0, "start": 10.0, "end": 14.0}]


def _zoom_case():
    clips = [
        _clip("/tmp/talk.mp4", face={"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3}),
        _clip("/tmp/room.mp4", role="broll"),
    ]
    segs = [
        {"clip": 0, "start": 0.0, "end": 5.0, "reason": "a"},
        {"clip": 0, "start": 6.0, "end": 16.0, "reason": "b"},
    ]
    lines = [
        {"id": 0, "clip": 0, "start": 0.0, "end": 5.0, "keep": True, "text": "a"},
        {"id": 1, "clip": 0, "start": 6.0, "end": 8.0, "keep": True, "text": "b"},
        {"id": 2, "clip": 0, "start": 8.0, "end": 12.0, "keep": True, "text": "c"},
        {"id": 3, "clip": 0, "start": 12.0, "end": 16.0, "keep": True, "text": "d"},
    ]
    covers = [{"clip": 1, "line": 2, "through": 2, "start": 0.0, "end": 4.0, "reason": "shows it"}]
    return clips, segs, lines, covers


def test_no_zoom_unless_asked_and_only_the_speaker_is_zoomed():
    clips, segs, lines, covers = _zoom_case()

    def graph(**more):
        args = render_args(segs, clips, "/tmp/o.mp4", covers=covers, lines=lines, **more)
        return [part for part in args[args.index("-filter_complex") + 1].split(";") if ":v]" in part], args

    plain, _ = graph()
    assert not any("crop=" in part or "perspective=" in part for part in plain)
    assert graph(zoom="off")[0] == plain

    # On cuts. First piece wide. After the join: the speaker tight, the B-roll as shot, the speaker tight again.
    branches, _ = graph(zoom="cuts")
    assert [("crop=1714:964:103:0" in part) for part in branches] == [False, True, False, True]
    # On VA-API the zoomed pieces are decoded in software, where the crop runs.
    _, args = graph(zoom="cuts", encoder="vaapi", device="/dev/dri/renderD128")
    assert args.count("-hwaccel") < len(branches)

    # Slow push. Every piece of the speaker moves, the B-roll does not, and the speaker comes
    # back from under the B-roll as far in as the push had got by then: 6 seconds into the piece.
    branches, _ = graph(zoom="push")
    assert [("perspective=" in part) for part in branches] == [True, True, False, True]
    assert "(on/30+0.000)" in branches[0] and "(on/30+0.000)" in branches[1]
    assert "(on/30+6.000)" in branches[3]

    # Key lines. Line 3 is the one that carries the point: 1920 / 1.15 = 1669, 1080 / 1.15 = 939, made even.
    branches, _ = graph(zoom="lines", close=[3])
    assert [("crop=1668:938:126:0" in part) for part in branches] == [False, False, False, True]
    # With no line named, or the named line gone, nothing is zoomed.
    assert graph(zoom="lines")[0] == plain
    assert graph(zoom="lines", close=[42])[0] == plain

    import pytest

    with pytest.raises(SystemExit, match="Unknown zoom"):
        graph(zoom="wild")


def test_a_small_shot_is_never_zoomed():
    clips, segs, lines, covers = _zoom_case()
    clips[0] = _clip("/tmp/talk.mp4", 1280, 720)
    for zoom in ("cuts", "push", "lines"):
        args = render_args(segs, clips, "/tmp/o.mp4", lines=lines, zoom=zoom, close=[3])
        graph = args[args.index("-filter_complex") + 1]
        assert "crop=" not in graph and "perspective=" not in graph


def test_every_zoom_encodes_at_the_same_size(tmp_path):
    src = tmp_path / "talk.mp4"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=s=1920x1080:r=30:d=12",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "12",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]
    clips = [_clip(str(src), duration=12.0, face={"x": 0.4, "y": 0.2, "w": 0.2, "h": 0.3})]
    segs = [
        {"clip": 0, "start": 0.2, "end": 5.0, "reason": "a"},
        {"clip": 0, "start": 6.0, "end": 11.0, "reason": "b"},
    ]
    lines = [_said(0, 0.2, 5.0), _said(1, 6.0, 8.0), _said(2, 8.6, 11.0)]
    for zoom in ("cuts", "push", "lines"):
        out = tmp_path / f"{zoom}.mp4"
        args = render_args(segs, clips, str(out), polish=True, lines=lines, zoom=zoom, close=[2])
        graph = args[args.index("-filter_complex") + 1]
        assert ("perspective=" in graph) if zoom == "push" else ("crop=" in graph)
        proc = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr[-500:]
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "csv=p=0", str(out)],
            capture_output=True, text=True,
        )
        size, length = probe.stdout.split()
        assert size == "1920,1080"
        # Splitting a piece to show a line close neither loses nor adds time.
        assert abs(float(length) - 9.8) < 0.2


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
