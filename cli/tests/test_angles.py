"""Cutting between two cameras on the same take."""

import pytest

from botcut import angles
from botcut.media import cut_pieces, render_args


def _clips(offset=-2.0, duration=120.0, **angle):
    return [
        {"path": "/tmp/a.mp4", "width": 1920, "height": 1080, "fps": 30.0, "duration": 120.0},
        {"path": "/tmp/b.mp4", "width": 1920, "height": 1080, "fps": 30.0, "duration": duration,
         "role": "angle", "of": 0, "offset": offset, **angle},
    ]


def _line(uid, start, end, text="Words here.", **more):
    return {"id": uid, "clip": 0, "start": start, "end": end, "keep": True, "text": text, "reason": "x", **more}


# Five lines of five seconds. A jump before line 2 and before line 4; the rest run on.
LINES = [_line(0, 10, 15), _line(1, 15.3, 20), _line(2, 30, 35), _line(3, 35.3, 40), _line(4, 50, 55)]
PIECES = [
    {"clip": 0, "start": 9.75, "end": 20.4, "reason": "x"},
    {"clip": 0, "start": 29.75, "end": 40.4, "reason": "x"},
    {"clip": 0, "start": 49.75, "end": 55.4, "reason": "x"},
]


def test_the_view_changes_at_a_jump_cut_and_goes_back_at_the_next():
    runs = angles.plan(LINES, PIECES, _clips())
    assert runs == [{"clip": 1, "of": 0, "line": 2, "through": 3, "reason": angles.HIDES}]
    # No second camera, or cutting turned off, is no runs.
    assert angles.plan(LINES, PIECES, _clips()[:1]) == []
    assert angles.plan(LINES, PIECES, _clips(), cameras={"off": True}) == []


def test_a_view_is_held_before_it_changes_and_never_changes_inside_a_run_of_speech():
    # Jumps every two seconds: the view is held through the ones that come too soon.
    lines = [_line(i, 10 + 6 * i, 12 + 6 * i) for i in range(6)]
    pieces = [{"clip": 0, "start": line["start"] - 0.25, "end": line["end"] + 0.4, "reason": "x"} for line in lines]
    runs = angles.plan(lines, pieces, _clips())
    assert [(run["line"], run["through"]) for run in runs] == [(2, 3)]
    assert [(run["line"], run["through"]) for run in angles.plan(lines, pieces, _clips(), cameras={"pace": "busy"})] == [
        (2, 3)
    ]
    # One long unbroken take changes view only when it has been on a long time, at the end of a sentence.
    talk = [_line(i, 10 + 5 * i, 14.8 + 5 * i) for i in range(10)]
    whole = [{"clip": 0, "start": 9.75, "end": 60.2, "reason": "x"}]
    runs = angles.plan(talk, whole, _clips())
    assert [(run["line"], run["reason"]) for run in runs] == [(4, angles.LONG)]
    assert angles.plan(talk, whole, _clips(), cameras={"pace": "calm"})[0]["line"] == 7


def test_a_new_beat_and_a_line_that_matters_are_places_to_change():
    talk = [_line(i, 10 + 5 * i, 14.8 + 5 * i) for i in range(6)]
    whole = [{"clip": 0, "start": 9.75, "end": 40.2, "reason": "x"}]
    beats = [{"title": "Start", "first": 0, "last": 1}, {"title": "Turn", "first": 2, "last": 5}]
    assert angles.plan(talk, whole, _clips(), beats=beats)[0] == {
        "clip": 1, "of": 0, "line": 2, "through": 5, "reason": angles.BEAT,
    }
    # The line that carries the point goes to the camera that is close, when it is known which that is.
    close = angles.plan(talk, whole, _clips(view="close"), close=[3])
    assert [(run["line"], run["through"], run["reason"]) for run in close] == [(3, 5, angles.KEY)]
    # A shot whose wide view is the second camera opens on it.
    wide = angles.plan(talk, whole, _clips(view="wide"))
    assert wide[0]["line"] == 0 and wide[0]["reason"] == angles.WIDE


def test_the_person_can_favor_a_camera_or_hold_a_stretch_on_the_main_one():
    runs = angles.plan(LINES, PIECES, _clips(), cameras={"favor": 1})
    # It opens on the favored camera, leaves it to hide a jump cut, and is back as soon as the view has been held.
    assert [(run["line"], run["through"]) for run in runs] == [(0, 1), (3, 3)]
    assert angles.plan(LINES, PIECES, _clips(), cameras={"stay": [2, 3]}) == [
        {"clip": 1, "of": 0, "line": 4, "through": 4, "reason": angles.HIDES}
    ]
    assert angles.read_cameras({"pace": "wild", "favor": 9, "stay": [3, "x", 3]}, _clips()) == {
        "pace": "normal", "favor": None, "stay": [3], "off": False,
    }
    assert angles.write_cameras(angles.read_cameras({})) == {}
    assert angles.write_cameras({"pace": "calm", "favor": 1, "stay": [4, 2], "off": True}) == {
        "pace": "calm", "favor": 1, "stay": [2, 4], "off": True,
    }


def test_a_camera_that_was_not_running_is_not_cut_to():
    # The second camera started at 33 s of the take: it has no picture for line 2.
    late = _clips(offset=-33.0)
    assert [(run["line"], run["through"]) for run in angles.plan(LINES, PIECES, late)] == [(4, 4)]
    # One that stops at 37 s has line 2 and not line 3.
    short = _clips(offset=0.0, duration=37.0)
    assert angles.plan(LINES, PIECES, short) == [
        {"clip": 1, "of": 0, "line": 2, "through": 2, "reason": angles.HIDES}
    ]


def test_a_run_shows_the_other_camera_at_the_same_moment_with_the_main_cameras_sound():
    clips = _clips(offset=-2.0)
    runs = [{"clip": 1, "of": 0, "line": 2, "through": 3, "reason": angles.HIDES}]
    windows = angles.angle_windows(runs, LINES, PIECES, clips)
    # The whole piece between the two jumps, read from the second camera two seconds earlier in its file.
    assert windows == [{"segment": 1, "start": 29.75, "end": 40.4, "clip": 1, "src": 27.75, "angle": True}]
    pieces = cut_pieces(PIECES, clips, polish=True, lines=LINES, angles=runs)
    assert [(piece["clip"], piece.get("voice"), piece.get("angle", False)) for piece in pieces] == [
        (0, None, False), (1, 0, True), (0, None, False),
    ]
    graph = render_args(PIECES, clips, "/tmp/o.mp4", lines=LINES, angles=runs)
    graph = graph[graph.index("-filter_complex") + 1]
    # The second camera's own sound is never mixed in.
    assert "amix" not in graph and "volume=0.25" not in graph


def test_a_run_inside_a_longer_piece_changes_view_in_the_pause_between_two_lines():
    whole = [{"clip": 0, "start": 9.75, "end": 55.4, "reason": "x"}]
    runs = [{"clip": 1, "of": 0, "line": 1, "through": 2, "reason": angles.BEAT}]
    lines = [_line(0, 10, 15), _line(1, 16, 20), _line(2, 20.4, 30), _line(3, 31, 40)]
    (window,) = angles.angle_windows(runs, lines, whole, _clips(offset=1.5, drift=0.001))
    # Halfway through the air before line 1, to halfway through the air after line 2.
    assert (window["start"], window["end"]) == (15.5, 30.5)
    assert window["src"] == pytest.approx(15.5 + 1.5 + 0.0155, abs=0.001)


def test_a_cut_inside_a_line_stays_on_the_other_camera():
    lines = [
        _line(0, 10, 15),
        _line(1, 20, 26, cuts=[{"from": 1, "through": 1, "start": 22.0, "end": 22.6, "cut": True}]),
        _line(2, 40, 45),
    ]
    pieces = [
        {"clip": 0, "start": 9.75, "end": 15.4, "reason": "x"},
        {"clip": 0, "start": 19.75, "end": 22.0, "reason": "x"},
        {"clip": 0, "start": 22.6, "end": 26.4, "reason": "x"},
        {"clip": 0, "start": 39.75, "end": 45.4, "reason": "x"},
    ]
    runs = angles.plan(lines, pieces, _clips())
    assert runs == [{"clip": 1, "of": 0, "line": 1, "through": 1, "reason": angles.HIDES}]
    windows = angles.angle_windows(runs, lines, pieces, _clips())
    assert [(w["segment"], w["start"], w["end"]) for w in windows] == [(1, 19.75, 22.0), (2, 22.6, 26.4)]


def test_broll_over_a_line_wins_the_picture_from_the_other_camera():
    clips = [*_clips(), {"path": "/tmp/c.mp4", "width": 1920, "height": 1080, "fps": 30.0, "duration": 30.0, "role": "broll"}]
    runs = [{"clip": 1, "of": 0, "line": 2, "through": 3, "reason": angles.HIDES}]
    covers = [{"clip": 2, "line": 3, "through": 3, "start": 0.0, "end": 4.0, "reason": "shows it"}]
    pieces = cut_pieces(PIECES, clips, polish=True, lines=LINES, angles=runs, covers=covers)
    middle = [(piece["clip"], round(piece["span"], 2)) for piece in pieces if piece["segment"] == 1]
    assert middle == [(1, 5.55), (2, 4.0), (1, 1.1)]


def test_the_sentence_about_the_cameras():
    clips = _clips()
    runs = angles.plan(LINES, PIECES, clips)
    seconds = angles.shown_seconds(runs, LINES, PIECES, clips)
    assert angles.reply(runs, clips, seconds) == (
        "I found 2 cameras on the same take and cut to the other view once, 11 s in all, to hide a cut."
    )
    assert angles.reply([], clips, 0) == "I found 2 cameras on the same take and stayed on the first."
    assert angles.reply([], clips[:1], 0) == ""


def test_which_camera_is_wide_and_which_is_close():
    found = angles.read_views(
        {"views": [{"camera": 0, "view": "wide"}, {"camera": 1, "view": "wide"}, {"camera": 7, "view": "close"}]},
        [0, 1],
    )
    assert found == {0: "wide", 1: "side"}


def _take(path, seconds=40):
    """The sound of a take: bursts like a voice, and a beep on every second."""
    import wave

    import numpy as np

    rng = np.random.default_rng(4)
    rate = 48000
    out = np.zeros(seconds * rate, dtype=np.float32)
    at = 0
    while at < len(out):
        burst = int(rng.uniform(0.08, 0.5) * rate)
        end = min(len(out), at + burst)
        out[at:end] = rng.normal(0, rng.uniform(0.03, 0.12), end - at)
        at = end + int(rng.uniform(0.03, 0.4) * rate)
    t = np.arange(len(out)) / rate
    out += 0.6 * np.sin(2 * np.pi * 1000 * t) * ((t % 1.0) < 0.1)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())


def _camera(path, take, started, seconds, base):
    """A camera started `started` seconds into the take. Its picture flashes white on every second of the take."""
    import subprocess

    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s=64x64:r=30:d={seconds}",
            "-ss", str(started), "-i", str(take),
            "-vf", f"geq=lum='if(lt(mod(T+{started},1),0.1),255,{base})':cb=128:cr=128",
            "-af", "lowpass=f=5000,volume=0.5" if started else "anull",
            "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "15", "-c:a", "aac", "-b:a", "192k",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]


def test_two_cameras_are_found_by_their_sound_and_cut_between_in_step(tmp_path, monkeypatch):
    import json
    import subprocess

    import numpy as np

    from botcut import cli, render
    from botcut.media import probe
    from test_render import _flashes

    def _beeps(path):
        """When the 1 kHz beep starts, heard through the talk around it."""
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "48000",
             "-af", "bandpass=f=1000:width_type=h:w=60", "-f", "s16le", "-"],
            capture_output=True,
        )
        heard = np.abs(np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32))
        step = 480
        blocks = heard[: len(heard) // step * step].reshape(-1, step).mean(axis=1)
        loud = blocks > 0.4 * blocks.max()
        return [i * step / 48000 for i in range(len(loud)) if loud[i] and (i == 0 or not loud[i - 1])]

    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    take = tmp_path / "take.wav"
    _take(take)
    _camera(tmp_path / "a.mp4", take, 0, 40, 16)
    # The second camera was started three and a quarter seconds in: half a frame off the first.
    _camera(tmp_path / "b.mp4", take, 3.25, 34, 110)
    out = tmp_path / "out"
    (out / "work").mkdir(parents=True)
    clips = [probe(str(tmp_path / "a.mp4")), probe(str(tmp_path / "b.mp4"))]
    cli.find_cameras(str(out / "work"), clips, set())
    assert clips[1]["role"] == "angle" and clips[1]["of"] == 0
    assert clips[1]["offset"] == pytest.approx(-3.25, abs=0.01)
    assert "role" not in clips[0]
    # Asked again, it is read from what was kept.
    monkeypatch.setattr("botcut.sync.line_up", lambda *args, **kwargs: pytest.fail("lined up twice"))
    again = [probe(str(tmp_path / "a.mp4")), probe(str(tmp_path / "b.mp4"))]
    cli.find_cameras(str(out / "work"), again, set())
    assert again[1]["offset"] == clips[1]["offset"]

    lines = [
        {"id": i, "clip": 0, "start": start, "end": end, "keep": True, "text": "Words here.", "reason": "x"}
        for i, (start, end) in enumerate([(5.1, 9.0), (9.3, 13.0), (18.2, 22.0), (22.3, 26.0), (31.4, 35.0)])
    ]
    pieces = [
        {"clip": 0, "start": 4.85, "end": 13.4, "reason": "x"},
        {"clip": 0, "start": 17.95, "end": 26.4, "reason": "x"},
        {"clip": 0, "start": 31.15, "end": 35.4, "reason": "x"},
    ]
    doc = {"lines": lines, "clips": [cli._clip_row(i, clip) for i, clip in enumerate(clips)]}
    assert doc["clips"][1]["role"] == "angle" and doc["clips"][1]["of"] == 0
    cli.plan_cameras(doc, clips, pieces, str(out))
    assert [(run["clip"], run["line"], run["through"], run["reason"]) for run in doc["angles"]] == [
        (1, 2, 3, "hides a cut")
    ]
    assert doc["angles"][0]["still"].endswith("angle-1-2.jpg")
    assert doc["angles_reply"].startswith("I found 2 cameras on the same take and cut to the other view once")

    movie = out / "rough_cut.mp4"
    render.render(
        pieces, clips, str(movie), "Rendering", "Render failed", encoder="x264", device=None,
        scene_transition="off", lines=lines, angles=doc["angles"],
    )
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(movie), "-map", "0:v:0", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True,
    )
    light = np.frombuffer(proc.stdout, dtype=np.uint8)
    # First piece on the first camera, the middle piece on the second, the last back on the first.
    assert light[100] < 40 and 80 < light[int(8.55 * 30) + 100] < 140 and light[int(17.0 * 30) + 60] < 40
    # On either camera a flash is on the beep: the second camera shows the same moment the sound is at.
    flashes, beeps = _flashes(movie), _beeps(movie)
    assert len(flashes) == len(beeps) >= 18
    # The first and the last are under the fade that opens and closes the movie.
    for flash, beep in list(zip(flashes, beeps))[1:-1]:
        assert abs(flash - beep) <= 1 / 30 + 0.025, (flashes, beeps)
    # The second camera's quieter sound is never the one heard.
    written = json.loads(json.dumps(doc))
    assert "offset" in written["clips"][1]


def _tone_clip(path, seconds):
    import subprocess

    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=f=440:duration={seconds}", "-t", str(seconds), str(path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]


def _four_lines():
    words = []
    for i in range(4):
        at = 0.3 + i * 3.0
        words.append({"text": f"line{i}", "start": at, "end": at + 1.0})
        words.append({"text": "here.", "start": at + 1.1, "end": at + 2.0})
    return {"duration": 13.0, "words": words}


def test_a_file_marked_as_a_second_camera_is_not_transcribed_and_takes_the_picture(monkeypatch, tmp_path, capsys):
    import json

    from botcut import cli
    from botcut.revise import apply_proposal, parse_revise, proposal_path

    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr("botcut.cli.transcribe_fake", _four_lines)
    talk, other = tmp_path / "talk.mp4", tmp_path / "other.mp4"
    _tone_clip(talk, 13)
    _tone_clip(other, 13)
    out = tmp_path / "out"
    cli.main(["run", str(talk), str(other), "--out", str(out), "--decide", "--angle-file", str(other)])
    said = capsys.readouterr().out
    assert "Transcribing 1/1" in said and "Transcribing 2/" not in said
    doc = json.loads((out / "cuts.json").read_text())
    assert doc["clips"][1] == {**doc["clips"][1], "role": "angle", "of": 0, "offset": 0.0}
    assert all(line["clip"] == 0 for line in doc["lines"])
    # Four lines with a jump between each: the view is held four seconds, then goes to the second camera.
    assert [(run["clip"], run["line"], run["through"], run["reason"]) for run in doc["angles"]] == [
        (1, 2, 3, "hides a cut")
    ]
    assert "cut to the other view once" in doc["angles_reply"]

    # Asked in the chat to stay on one camera, the next render plans none.
    proposal = {
        "note": "stay on the main camera", "reply": "I'd stay on the main camera.", "intent": doc["intent"],
        "pace": "open", "dip": True, "deliver": "none", "fillers": "same", "cameras": "off", "favor": -1,
        "keep": [{"id": line["id"], "reason": line["reason"]} for line in doc["lines"]],
    }
    Path = __import__("pathlib").Path
    Path(proposal_path(str(out / "cuts.json"))).write_text(json.dumps(proposal))
    apply_proposal(str(out / "cuts.json"))
    doc = json.loads((out / "cuts.json").read_text())
    assert doc["cameras"] == {"off": True}
    seen = {}
    monkeypatch.setattr(cli, "render_with_progress", lambda *args, **kwargs: seen.update(kwargs))
    cli.render_saved(str(out))
    assert seen["angles"] is None
    doc = json.loads((out / "cuts.json").read_text())
    assert "angles" not in doc and "angles_reply" not in doc
    # Favoring the second camera puts it back on: the movie opens there, and leaves it to hide a jump.
    doc["cameras"] = {"favor": 1}
    (out / "cuts.json").write_text(json.dumps(doc))
    cli.render_saved(str(out))
    assert [(run["line"], run["through"]) for run in seen["angles"]] == [(0, 1)]
    # An older proposal says nothing about cameras, and changes nothing about them.
    old = parse_revise({key: proposal[key] for key in ("reply", "intent", "pace", "dip", "keep", "deliver")})
    assert (old["cameras"], old["favor"]) == ("same", -1)


def test_a_shot_list_marks_a_second_camera_and_a_file_cannot_be_both(tmp_path, monkeypatch):
    from botcut import cli

    listing = tmp_path / "shots.txt"
    listing.write_text("/tmp/a.mp4\nangle /tmp/b.mp4\nb-roll /tmp/c.mp4\n")
    assert cli.resolve_inputs([str(listing)]) == ["/tmp/a.mp4", "/tmp/b.mp4", "/tmp/c.mp4"]
    assert cli.resolve_angles([str(listing)]) == ["/tmp/b.mp4"]
    assert cli.resolve_broll([str(listing)]) == ["/tmp/c.mp4"]
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _tone_clip(a, 2)
    _tone_clip(b, 2)
    with pytest.raises(SystemExit, match="not both"):
        cli.run([str(a), str(b)], str(tmp_path / "o"), decide=True, broll_files=[str(b)], angle_files=[str(b)])
    with pytest.raises(SystemExit, match="not in the list"):
        cli.run([str(a)], str(tmp_path / "o"), decide=True, angle_files=[str(b)])
    # The first file has no shot before it to be the second camera of.
    with pytest.raises(SystemExit, match="second camera needs a shot"):
        cli.run([str(a), str(b)], str(tmp_path / "o"), decide=True, angle_files=[str(a)])


def test_two_takes_that_do_not_match_stop_a_marked_camera_and_are_left_alone_unmarked(tmp_path, monkeypatch):
    from botcut import cli
    from botcut.media import probe

    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    take, again = tmp_path / "take.wav", tmp_path / "again.wav"
    _take(take, 12)
    _take(again, 12)
    _camera(tmp_path / "a.mp4", take, 0, 12, 16)
    # A different take: the same beeps on every second, other words.
    import numpy as np, wave

    rng = np.random.default_rng(99)
    with wave.open(str(again), "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(48000)
        body = np.zeros(12 * 48000, dtype=np.float32)
        at = 0
        while at < len(body):
            end = min(len(body), at + int(rng.uniform(0.08, 0.5) * 48000))
            body[at:end] = rng.normal(0, 0.1, end - at)
            at = end + int(rng.uniform(0.03, 0.4) * 48000)
        handle.writeframes((np.clip(body, -1, 1) * 32767).astype(np.int16).tobytes())
    _camera(tmp_path / "b.mp4", again, 0, 12, 16)
    work = tmp_path / "work"
    work.mkdir()
    clips = [probe(str(tmp_path / "a.mp4")), probe(str(tmp_path / "b.mp4"))]
    cli.find_cameras(str(work), clips, set())
    assert "role" not in clips[0] and "role" not in clips[1]
    with pytest.raises(SystemExit, match="Could not line up b.mp4"):
        cli.find_cameras(str(work), clips, {1})


def test_find_cameras_prevents_marked_angle_chaining_onto_unmarked_angle(tmp_path, monkeypatch):
    from botcut import cli, sync

    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    clips = []
    for name in ("cam0.mp4", "cam1_marked.mp4", "cam2_unmarked.mp4"):
        p = tmp_path / name
        p.write_bytes(b"x")
        clips.append({"path": str(p), "duration": 20.0, "audio": True})

    monkeypatch.setattr(sync, "load", lambda path: path)

    # cam2_unmarked matches cam0 (so cam2 becomes an angle of cam0).
    # cam1_marked matches cam2 slightly higher than cam0; without processing unmarked first,
    # cam1_marked would chain onto cam2 and get dropped by angles.groups().
    def fake_line_up(main, other, sure=0):
        if main.endswith("cam0.mp4") and other.endswith("cam2_unmarked.mp4"):
            return {"start": 0.0, "end": 18.0, "offset": 0.0, "drift": 0.0, "score": 0.9}
        if main.endswith("cam2_unmarked.mp4") and other.endswith("cam1_marked.mp4"):
            return {"start": 0.0, "end": 18.0, "offset": 0.0, "drift": 0.0, "score": 0.99}
        if main.endswith("cam0.mp4") and other.endswith("cam1_marked.mp4"):
            return {"start": 0.0, "end": 18.0, "offset": 0.0, "drift": 0.0, "score": 0.85}
        return None

    monkeypatch.setattr(sync, "line_up", fake_line_up)
    work = tmp_path / "work"
    work.mkdir()
    cli.find_cameras(str(work), clips, {1})
    assert clips[2]["role"] == "angle" and clips[2]["of"] == 0
    assert clips[1]["role"] == "angle" and clips[1]["of"] == 0
    assert angles.groups(clips) == {0: [1, 2]}
