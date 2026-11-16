import json
import re
import subprocess
from pathlib import Path

import pytest

from botcut.broll import (
    COVER_SCHEMA,
    COVER_SYSTEM,
    FAKE_COVER_REPLY,
    MAX_BEATS,
    RUN_MAX,
    RUN_MIN,
    accept_runs,
    beat_still_at,
    beats_from_cuts,
    broll_indexes,
    choose_covers,
    collect_beats,
    cover_user_content,
    cover_windows,
    fake_beats,
    kept_covers,
    run_length,
    spoken_kept,
)
from botcut.captions import load_words_by_clip
from botcut.cli import _beats_for_clip, main, render_saved, resolve_broll, resolve_inputs, run
from botcut.media import parse_scene_changes, probe, render_args, scene_changes
from botcut.revise import revise
from botcut.stt import transcribe_fake


def _beats(*rows):
    return {int(row["id"]): row for row in rows}


def _kept(ids, length=2.0, gap=0.5, clip=0, start=1.0):
    rows = []
    at = start
    for uid in ids:
        rows.append(
            {"id": uid, "clip": clip, "start": at, "end": at + length, "text": f"line {uid}", "keep": True, "reason": "story"}
        )
        at += length + gap
    return rows


def test_accept_runs_lays_runs_in_line_order_and_keeps_them_apart(tmp_path):
    beats = _beats(
        {"id": 0, "clip": 2, "start": 0.0, "end": 4.0},
        {"id": 1, "clip": 2, "start": 4.0, "end": 8.0},
        {"id": 2, "clip": 2, "start": 8.0, "end": 12.0},
        {"id": 3, "clip": 2, "start": 12.0, "end": 14.0},
    )
    lines = _kept([1, 2, 3, 4, 5, 6])
    segments = [{"clip": 0, "start": 0.0, "end": 30.0}]
    (tmp_path / "broll-2-2.jpg").write_bytes(b"jpeg")
    claims = [
        {"beat": True, "line": 2, "through": 2, "reason": "x"},
        {"beat": 9, "line": 2, "through": 2, "reason": "no such beat"},
        {"beat": 0, "line": 99, "through": 99, "reason": "no such line"},
        {"beat": 0, "line": 1, "through": 2, "reason": "the first line stays on the speaker"},
        {"beat": 0, "line": 5, "through": 6, "reason": "so does the last"},
        {"beat": 0, "line": 3, "through": 2, "reason": "backwards"},
        {"beat": 2, "line": 4, "through": 5, "reason": "  shows   the road  "},
        {"beat": 1, "line": 2, "through": 3, "reason": "beats go up, so this later one is out"},
        {"beat": 3, "line": 2, "through": 3, "reason": "too little file left"},
        {"beat": 3, "line": 4, "through": 4, "reason": "overlaps"},
        {"beat": 3, "line": 2, "through": 2, "reason": "one short line"},
    ]
    accepted = accept_runs(
        claims, beats=beats, lines=lines, segments=segments, durations=[30, 30, 14], still_dir=str(tmp_path)
    )
    assert accepted == [
        {
            "clip": 2,
            "line": 4,
            "through": 5,
            "start": 8.0,
            "end": 12.5,
            "reason": "shows the road",
            "still": str(tmp_path / "broll-2-2.jpg"),
        }
    ]
    assert accept_runs("nope", beats=beats, lines=lines) == []
    # Two runs in claim order land in line order, and a run never crosses another.
    two = accept_runs(
        [
            {"beat": 0, "line": 4, "through": 5, "reason": "later"},
            {"beat": 1, "line": 2, "through": 3, "reason": "earlier"},
        ],
        beats=beats,
        lines=lines,
        segments=segments,
    )
    assert [(row["line"], row["through"], row["start"]) for row in two] == [(2, 3, 4.0), (4, 5, 0.0)]


def test_accept_runs_trims_a_long_run_to_a_line_and_drops_a_short_one():
    beats = _beats({"id": 0, "clip": 1, "start": 2.0, "end": 6.0})
    lines = _kept([1, 2, 3, 4, 5, 6], length=4.0)
    segments = [{"clip": 0, "start": 0.0, "end": 60.0}]
    assert run_length(lines[1:5], segments) == 17.5
    assert run_length(lines[1:3], segments) == 8.5
    # 2..5 is 17.5 s, 2..4 is 13 s, 2..3 is 8.5 s: the run ends on line 3.
    trimmed = accept_runs(
        [{"beat": 0, "line": 2, "through": 5, "reason": "long"}], beats=beats, lines=lines, segments=segments
    )
    assert [(row["through"], row["end"]) for row in trimmed] == [(3, 10.5)]
    # One line longer than RUN_MAX is cut at RUN_MAX.
    big = accept_runs(
        [{"beat": 0, "line": 2, "through": 2, "reason": "long"}],
        beats=beats,
        lines=_kept([1, 2, 3], length=20.0),
        segments=[{"clip": 0, "start": 0.0, "end": 80.0}],
    )
    assert big[0]["end"] == 2.0 + RUN_MAX
    # Under RUN_MIN there is no run.
    short = accept_runs(
        [{"beat": 0, "line": 2, "through": 2, "reason": "short"}], beats=beats, lines=_kept([1, 2, 3], length=2.0)
    )
    assert short == []
    assert RUN_MIN == 3.0
    # Air between two lines in different segments is a cut, not length.
    # Across a cut, the tail of one segment and the head of the next are the run's too.
    split = [{"clip": 0, "start": 0.0, "end": 3.2}, {"clip": 0, "start": 3.4, "end": 60.0}]
    assert run_length(_kept([1, 2], length=2.0)[:2], split) == pytest.approx(4.3)
    assert run_length(_kept([1, 2], length=2.0, gap=0.5), None) == 4.5
    assert run_length(_kept([1, 2], length=2.0, gap=1.5), None) == 4.0


def test_schema_and_prompt_have_no_path_or_time():
    props = COVER_SCHEMA["json_schema"]["schema"]["properties"]["covers"]["items"]["properties"]
    assert set(props) == {"beat", "line", "through", "reason"}
    assert set(COVER_SCHEMA["json_schema"]["schema"]["properties"]) == {"reply", "covers"}
    clips = [
        {"path": "/secret/room.mp4", "duration": 6.5, "role": "broll"},
        {"path": "/secret/talk.mp4", "duration": 8},
    ]
    lines = [
        {"id": 4, "clip": 1, "start": 1.0, "end": 3.0, "text": "welcome to the product", "keep": True, "reason": "story"},
        {"id": 5, "clip": 1, "start": 3.2, "end": 3.4, "text": "um", "keep": False, "reason": "dropped"},
        {"id": 6, "clip": 1, "start": 5.0, "end": 7.5, "text": "here it is", "keep": True, "reason": "story"},
        {"id": 7, "clip": 1, "start": 0.0, "end": 3.0, "text": "title", "keep": True, "reason": "card"},
    ]
    segments = [{"clip": 1, "start": 0.8, "end": 3.1}, {"clip": 1, "start": 4.8, "end": 7.7}]
    beats = collect_beats(clips, {0: [(0.0, 4.0), (4.0, 6.5)]})
    assert beats == [
        {"id": 0, "clip": 0, "start": 0.0, "end": 4.0},
        {"id": 1, "clip": 0, "start": 4.0, "end": 6.5},
    ]
    text = cover_user_content(beats, lines, {}, intent="A ride home", segments=segments)
    assert "/secret/room.mp4" not in text
    for word in ("voice", "sound"):
        assert word not in COVER_SYSTEM
        assert word not in text
    assert "The movie is: A ride home" in text
    assert "2 B-roll beats, 6s in all" in text
    assert "beat 0, 4.0s, shot 0" in text
    assert "beat 1, 2.5s, shot 0" in text
    rows = text.splitlines()
    assert "[4] 2.0s welcome to the product" in rows
    assert "[5] dropped: um" in rows
    assert "[6] 2.5s here it is" in rows
    assert "title" not in text
    # The join between 4 and 6 is a cut the viewer sees, and the dropped line sits before it.
    assert rows.index("[5] dropped: um") < rows.index("— cut —") < rows.index("[6] 2.5s here it is")
    assert "1.0" not in text
    assert "5.0" not in text
    # No cut row when the lines share a segment.
    joined = cover_user_content(beats, lines, {}, segments=[{"clip": 1, "start": 0.8, "end": 7.7}])
    assert "— cut —" not in joined
    assert "The movie is" not in joined
    # The brief is an editor's.
    for phrase in ("hide a cut", "first line and the last", "never lay two back to back", "in order", "nothing earns it"):
        assert phrase in COVER_SYSTEM


def test_still_is_one_second_in_or_the_middle():
    assert beat_still_at(0.0, 5.0) == 1.0
    assert beat_still_at(4.0, 5.0) == 4.5
    assert beat_still_at(2.0, 2.4) == pytest.approx(2.2)
    assert beat_still_at(0.0, 0.0) == 0.0


def test_beats_follow_scene_changes_and_stay_between_one_and_four_seconds():
    assert beats_from_cuts([2.5, 9.0], 12.0) == [(0.0, 2.5), (2.5, 5.75), (5.75, 9.0), (9.0, 12.0)]
    # No scene change: fixed windows that divide the file evenly.
    assert beats_from_cuts([], 9.0) == [(0.0, 3.0), (3.0, 6.0), (6.0, 9.0)]
    assert fake_beats(9.0) == beats_from_cuts([], 9.0)
    # A short tail joins the span before it.
    assert beats_from_cuts([11.6], 12.0) == [(0.0, 4.0), (4.0, 8.0), (8.0, 12.0)]
    # A short head joins the span after it.
    assert beats_from_cuts([0.4, 6.0], 8.0) == [(0.0, 3.0), (3.0, 6.0), (6.0, 8.0)]
    # Cuts outside the file are ignored, and a tiny file is one beat.
    assert beats_from_cuts([-1, 0, 12, 50], 12.0) == beats_from_cuts([], 12.0)
    assert beats_from_cuts([], 0.5) == [(0.0, 0.5)]
    assert beats_from_cuts([], 0) == []
    assert beats_from_cuts(["x", None, 3.0], 6.0) == [(0.0, 3.0), (3.0, 6.0)]


def test_scene_changes_read_showinfo_lines(monkeypatch):
    stderr = "\n".join(
        [
            "[Parsed_showinfo_3 @ 0x55] config in time_base: 1/5, frame_rate: 5/1",
            "[Parsed_showinfo_3 @ 0x55] n:   0 pts:     12 pts_time:2.4     duration:      1",
            "[Parsed_showinfo_3 @ 0x55] n:   1 pts:     45 pts_time:9       duration:      1",
            "[out#0/null @ 0x56] pts_time:99 is not a frame",
        ]
    )
    assert parse_scene_changes(stderr) == [2.4, 9.0]
    assert parse_scene_changes("") == []

    seen = {}

    class Done:
        stderr = "[Parsed_showinfo_3 @ 0x55] n: 0 pts: 1 pts_time:1.2 duration: 1"
        returncode = 0

    def fake_run(cmd, **_kwargs):
        seen["cmd"] = cmd
        return Done()

    monkeypatch.setattr("botcut.media.subprocess.run", fake_run)
    assert scene_changes("/tmp/room.mp4") == [1.2]
    cmd = seen["cmd"]
    assert cmd[0] == "ffmpeg"
    assert "-an" in cmd
    graph = cmd[cmd.index("-vf") + 1]
    assert graph.startswith("fps=5,scale=160:-2,")
    assert "select='gt(scene,0.3)'" in graph
    assert graph.endswith(",showinfo")
    assert cmd[-3:] == ["-f", "null", "-"]


def test_beats_cache_is_written_once_and_fake_mode_stays_offline(monkeypatch, tmp_path):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setattr("botcut.cli.scene_changes", lambda _path: [2.5])
    clip = {"path": "/tmp/room.mp4", "duration": 6.0}
    first = _beats_for_clip(str(tmp_path), 1, "room", clip)
    assert first == [(0.0, 2.5), (2.5, 6.0)]
    cache = tmp_path / "1-room.beats.json"
    assert json.loads(cache.read_text()) == [[0.0, 2.5], [2.5, 6.0]]

    def boom(_path):
        raise AssertionError("ffmpeg")

    monkeypatch.setattr("botcut.cli.scene_changes", boom)
    assert _beats_for_clip(str(tmp_path), 1, "room", clip) == first

    monkeypatch.setenv("BOTCUT_FAKE", "1")
    assert _beats_for_clip(str(tmp_path), 2, "quiet", {"path": "/tmp/quiet.mp4", "duration": 9.0}) == [
        (0.0, 3.0),
        (3.0, 6.0),
        (6.0, 9.0),
    ]


def test_more_than_forty_beats_are_sampled_across_files():
    clips = [
        {"path": "/tmp/talk.mp4", "duration": 100},
        {"path": "/tmp/long.mp4", "duration": 240, "role": "broll"},
        {"path": "/tmp/short.mp4", "duration": 80, "role": "broll"},
    ]
    long_beats = [(i * 4.0, (i + 1) * 4.0) for i in range(60)]
    short_beats = [(i * 4.0, (i + 1) * 4.0) for i in range(20)]
    beats = collect_beats(clips, {1: long_beats, 2: short_beats})
    assert len(beats) <= MAX_BEATS
    assert [beat["id"] for beat in beats] == list(range(len(beats)))
    by_clip = {}
    for beat in beats:
        by_clip.setdefault(beat["clip"], []).append(beat)
    assert set(by_clip) == {1, 2}
    assert len(by_clip[1]) == 30
    assert len(by_clip[2]) == 10
    # Sampling spreads over the file instead of taking the first beats.
    assert by_clip[1][-1]["start"] > 200
    assert by_clip[2][-1]["start"] > 60
    # Beat ids run across files in clip order.
    assert by_clip[1][-1]["id"] < by_clip[2][0]["id"]
    assert collect_beats(clips, {1: [(0, 4), ("x", 1), (5, 5)]}) == [
        {"id": 0, "clip": 1, "start": 0.0, "end": 4.0}
    ]


def test_only_marked_clips_are_broll_and_a_cover_needs_a_spoken_line(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("botcut.broll.post", boom)
    clips = [
        {"path": "/tmp/botcut-card-1-open.mp4", "duration": 3, "role": "broll"},
        {"path": "/tmp/talk.mp4", "duration": 10},
        {"path": "/tmp/room.mp4", "duration": 8, "role": "broll"},
        {"path": "/tmp/quiet.mp4", "duration": 8},
    ]
    lines = [
        {"id": 0, "clip": 0, "start": 0, "end": 3, "text": "title", "keep": True, "reason": "card"},
        {"id": 1, "clip": 1, "start": 1, "end": 2, "text": "hello", "keep": True, "reason": "story"},
    ]
    # A card is never B-roll, and a clip with no kept speech is not guessed to be one.
    assert broll_indexes(clips) == [2]
    assert [line["id"] for line in spoken_kept(lines)] == [1]
    dropped = [{"id": 1, "clip": 1, "keep": False, "reason": "dropped", "text": "x", "start": 0, "end": 1}]
    assert spoken_kept(dropped) == []
    beats = {2: [(0.0, 4.0)]}
    assert choose_covers(clips, dropped, "/tmp/stills", beats) == ([], "")
    assert choose_covers(clips, lines, "/tmp/stills", {}) == ([], "")
    assert choose_covers([clips[1]], lines, "/tmp/stills", beats) == ([], "")
    # Fewer than three kept lines leave nothing to lay over: the first and last stay on the speaker.
    assert choose_covers(clips, lines + _kept([8], clip=1, start=5.0), "/tmp/stills", beats) == ([], "")


def test_fake_lays_one_run_over_the_second_and_third_lines(monkeypatch):
    monkeypatch.setenv("BOTCUT_FAKE", "1")

    def boom(*_args, **_kwargs):
        raise AssertionError("grab")

    monkeypatch.setattr("botcut.media.grab_still", boom)
    clips = [
        {"path": "/tmp/talk.mp4", "duration": 12},
        {"path": "/tmp/room.mp4", "duration": 5, "role": "broll"},
        {"path": "/tmp/extra.mp4", "duration": 5, "role": "broll"},
    ]
    lines = _kept([4, 7, 9, 11])
    beats = {1: [(0.0, 4.0), (4.0, 5.0)], 2: [(0.0, 4.0), (4.0, 5.0)]}
    assert choose_covers(clips, lines, "/tmp/stills", beats) == (
        [{"clip": 1, "line": 7, "through": 9, "start": 0.0, "end": 4.5, "reason": "fake"}],
        FAKE_COVER_REPLY,
    )
    # Three lines: the run is the middle one alone.
    three = choose_covers(clips, _kept([4, 7, 9], length=3.0), "/tmp/stills", beats)
    assert [(row["line"], row["through"], row["end"]) for row in three[0]] == [(7, 7, 3.0)]


def test_ask_hands_back_the_reply_and_only_runs_the_editor_may_lay(monkeypatch, tmp_path):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "secret-key")
    clips = [
        {"path": "/tmp/talk.mp4", "duration": 20},
        {"path": "/tmp/room.mp4", "duration": 8, "role": "broll"},
    ]
    lines = _kept([1, 2, 3, 4])
    seen = {}

    class Resp:
        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "reply": "I laid the road  over the middle.",
                                    "covers": [
                                        {"beat": 0, "line": 1, "through": 2, "reason": "opening"},
                                        {"beat": 1, "line": 2, "through": 3, "reason": "the road"},
                                    ],
                                }
                            )
                        }
                    }
                ]
            }

    def fake_post(_url, *, key, label, read_timeout, send):
        seen["body"] = send()["json"]
        return Resp()

    monkeypatch.setattr("botcut.broll.post", fake_post)
    monkeypatch.setattr("botcut.media.grab_still", lambda *_args: False)
    covers, reply = choose_covers(
        clips, lines, str(tmp_path), {1: [(0.0, 4.0), (4.0, 8.0)]}, intent="A ride", segments=None
    )
    assert covers == [{"clip": 1, "line": 2, "through": 3, "start": 4.0, "end": 8.0, "reason": "the road"}]
    assert reply == "I laid the road over the middle."
    assert seen["body"]["messages"][0]["content"] == COVER_SYSTEM
    user = seen["body"]["messages"][1]["content"]
    assert "The movie is: A ride" in user
    assert "[1] 2.0s line 1" in user

    # Nothing laid: no reply either, so the chat stays quiet.
    class Quiet:
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"reply": "Nothing earns it.", "covers": []})}}]}

    monkeypatch.setattr("botcut.broll.post", lambda *_a, **_k: Quiet())
    assert choose_covers(clips, lines, str(tmp_path), {1: [(0.0, 4.0)]}) == ([], "")


def test_ask_sends_a_still_per_beat_and_a_bad_body_stays_hidden(monkeypatch, tmp_path):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "secret-key")
    clips = [
        {"path": "/secret/talk.mp4", "duration": 8},
        {"path": "/secret/room.mp4", "duration": 5, "role": "broll"},
    ]
    lines = [
        {"id": 3, "clip": 0, "start": 0.0, "end": 0.8, "text": "hi", "keep": True, "reason": "story"},
        {"id": 4, "clip": 0, "start": 1.0, "end": 4.5, "text": "welcome", "keep": True, "reason": "story"},
        {"id": 5, "clip": 0, "start": 5.0, "end": 7.0, "text": "bye", "keep": True, "reason": "story"},
    ]
    beats = {1: [(0.0, 5.0)]}
    seen = {}

    class Resp:
        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "reply": "One run.",
                                    "covers": [{"beat": 0, "line": 4, "through": 4, "reason": "fits", "start": 1.25}],
                                    "note": "x",
                                }
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
    assert choose_covers(clips, lines, str(tmp_path), beats) == (
        [
            {
                "clip": 1,
                "line": 4,
                "through": 4,
                "start": 0.0,
                "end": 3.5,
                "reason": "fits",
                "still": str(tmp_path / "broll-1-0.jpg"),
            }
        ],
        "One run.",
    )
    blob = json.dumps(seen["body"])
    assert "/secret/room.mp4" not in blob
    assert "secret-key" not in blob
    assert seen["key"] == "secret-key"
    assert seen["at"] == 1.0
    assert (tmp_path / "broll-1-0.jpg").is_file()
    assert "image_url" in blob
    assert "Still for beat 0" in blob

    missed = {"n": 0}

    def miss(_video, _at, _dest):
        return False

    def miss_post(_url, *, key, label, read_timeout, send):
        missed["n"] += 1
        missed["body"] = send()["json"]
        return Resp()

    monkeypatch.setattr("botcut.media.grab_still", miss)
    monkeypatch.setattr("botcut.broll.post", miss_post)
    assert choose_covers(clips, lines, str(tmp_path / "miss"), beats) == (
        [{"clip": 1, "line": 4, "through": 4, "start": 0.0, "end": 3.5, "reason": "fits"}],
        "One run.",
    )
    assert missed["n"] == 1
    missed_blob = json.dumps(missed["body"])
    assert "beat 0" in missed_blob
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
        choose_covers(clips, lines, str(tmp_path), beats)
    assert "secret-key" not in str(exc.value)
    assert "/secret" not in str(exc.value)


def test_kept_covers_keeps_the_window():
    lines = [{"id": 1, "keep": True}, {"id": 2, "keep": False}]
    covers = [
        {"clip": 3, "line": 1, "start": 2.0, "end": 5.5},
        {"clip": 4, "line": 2, "start": 0.0, "end": 4.0},
        {"clip": 5, "line": 1},
        {"clip": "x", "line": 1},
    ]
    assert kept_covers(covers, lines) == [
        {"clip": 3, "line": 1, "start": 2.0, "end": 5.5},
        {"clip": 5, "line": 1},
    ]


def test_kept_covers_trims_a_run_at_a_dropped_line():
    lines = _kept([1, 2, 3, 4, 5], length=2.0, gap=0.5)
    run = {"clip": 3, "line": 2, "through": 4, "start": 6.0, "end": 13.0, "reason": "the road", "still": "/tmp/s.jpg"}
    assert kept_covers([run], lines) == [run]
    # Drop the last line of the run: it ends a line earlier, and the window shrinks with it.
    lines[3]["keep"] = False
    assert kept_covers([run], lines) == [{**run, "through": 3, "end": 10.5}]
    # Drop the middle: what is left is one 2 s line, under RUN_MIN, so the run goes.
    lines[3]["keep"] = True
    lines[2]["keep"] = False
    assert kept_covers([run], lines) == []
    # Drop the first line: the run goes with it.
    lines[2]["keep"] = True
    lines[1]["keep"] = False
    assert kept_covers([run], lines) == []


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
    assert basic == [{"segment": 0, "start": 1.0, "end": 3.0, "clip": 1, "src": 0.0}]

    short = _windows(
        covers=[{"clip": 1, "line": 4}],
        lines=[line],
        segments=[{"clip": 0, "start": 0.25, "end": 2.0}],
        durations=[20, 10],
    )
    assert short == [{"segment": 0, "start": 1.0, "end": 2.0, "clip": 1, "src": 0.0}]

    before = _windows(
        covers=[{"clip": 1, "line": 4}],
        lines=[{**line, "start": 0.2, "end": 3.0}],
        segments=[{"clip": 0, "start": 1.0, "end": 8.0}],
        durations=[20, 10],
    )
    assert before == [{"segment": 0, "start": 1.0, "end": 3.0, "clip": 1, "src": 0.0}]
    capped = _windows(
        covers=[{"clip": 1, "line": 4}],
        lines=[{**line, "start": 0.0, "end": 8.0}],
        segments=[{"clip": 0, "start": 0.0, "end": 10.0}],
        durations=[20, 10],
    )
    assert capped == [{"segment": 0, "start": 0.0, "end": 4.0, "clip": 1, "src": 0.0}]

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
    assert brief == [{"segment": 0, "start": 0.0, "end": 1.5, "clip": 1, "src": 0.0}]

    split = _windows(
        covers=[{"clip": 1, "line": 4}],
        lines=[{**line, "start": 1.0, "end": 6.0}],
        segments=[{"clip": 0, "start": 0.0, "end": 2.0}, {"clip": 0, "start": 4.0, "end": 8.0}],
        durations=[20, 10],
    )
    assert split == [{"segment": 0, "start": 1.0, "end": 2.0, "clip": 1, "src": 0.0}]

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


def test_window_plays_the_beat_from_its_own_start():
    line = {"id": 4, "clip": 0, "start": 1.0, "end": 3.0, "keep": True, "reason": "story"}
    deep = _windows(
        covers=[{"clip": 1, "line": 4, "start": 6.0, "end": 9.0}],
        lines=[line],
        segments=[{"clip": 0, "start": 0.0, "end": 8.0}],
        durations=[20, 10],
    )
    assert deep == [{"segment": 0, "start": 1.0, "end": 3.0, "clip": 1, "src": 6.0}]
    # A short beat ends the cover early. The line keeps playing on the speaker.
    brief = _windows(
        covers=[{"clip": 1, "line": 4, "start": 6.0, "end": 6.5}],
        lines=[line],
        segments=[{"clip": 0, "start": 0.0, "end": 8.0}],
        durations=[20, 10],
    )
    assert brief == [{"segment": 0, "start": 1.0, "end": 1.5, "clip": 1, "src": 6.0}]
    # A window past the end of the file is clamped, and one with nothing left is dropped.
    clamped = _windows(
        covers=[{"clip": 1, "line": 4, "start": 9.0, "end": 14.0}],
        lines=[line],
        segments=[{"clip": 0, "start": 0.0, "end": 8.0}],
        durations=[20, 10],
    )
    assert clamped == [{"segment": 0, "start": 1.0, "end": 2.0, "clip": 1, "src": 9.0}]
    assert (
        _windows(
            covers=[{"clip": 1, "line": 4, "start": 12.0, "end": 14.0}],
            lines=[line],
            segments=[{"clip": 0, "start": 0.0, "end": 8.0}],
            durations=[20, 10],
        )
        == []
    )


def test_run_windows_cross_the_join_and_the_footage_goes_on():
    lines = _kept([1, 2, 3, 4], length=2.0, gap=3.0)
    # Lines 2 and 3 sit in different segments: a cut the run hides.
    segments = [
        {"clip": 0, "start": 0.5, "end": 8.2},
        {"clip": 0, "start": 10.8, "end": 20.0},
    ]
    run = {"clip": 1, "line": 2, "through": 3, "start": 5.0, "end": 9.5, "reason": "hides the cut"}
    windows = cover_windows([run], lines, segments, [30, 20])
    # The run owns the air at both sides of the join, so the footage is one piece.
    assert windows == [
        {"segment": 0, "start": 6.0, "end": 8.2, "clip": 1, "src": 5.0, "continues": True},
        {"segment": 1, "start": 10.8, "end": 13.0, "clip": 1, "src": 7.2, "continued": True},
    ]
    # The file runs out inside the second segment: the window ends there, and nothing continues past it.
    short = cover_windows([{**run, "end": 8.0}], lines, segments, [30, 20])
    assert short == [
        {"segment": 0, "start": 6.0, "end": 8.2, "clip": 1, "src": 5.0, "continues": True},
        {"segment": 1, "start": 10.8, "end": 11.6, "clip": 1, "src": 7.2, "continued": True},
    ]
    gone = cover_windows([{**run, "end": 7.0}], lines, segments, [30, 20])
    assert gone == [{"segment": 0, "start": 6.0, "end": 8.0, "clip": 1, "src": 5.0}]
    # Two lines in one segment are one window, with the air between them under the B-roll.
    one = cover_windows([run], lines, [{"clip": 0, "start": 0.0, "end": 30.0}], [30, 20])
    assert one == [{"segment": 0, "start": 6.0, "end": 10.5, "clip": 1, "src": 5.0}]
    # A run is not capped at COVER_MAX the way an older one-line cover is.
    assert one[0]["end"] - one[0]["start"] > 4.0


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
        {"segment": 0, "start": 1.0, "end": 2.0, "clip": 2, "src": 0.0},
        {"segment": 0, "start": 2.0, "end": 4.0, "clip": 3, "src": 0.0},
    ]
    crowded = _windows(
        covers=[{"clip": 2, "line": 4}, {"clip": 3, "line": 5}],
        lines=[lines[0], {**lines[1], "start": 1.2, "end": 1.6}],
        segments=[{"clip": 0, "start": 0.0, "end": 10.0}],
        durations=[10, 10, 10, 0.5],
    )
    assert crowded == [{"segment": 0, "start": 1.0, "end": 2.0, "clip": 2, "src": 0.0}]
    # The later window loses its head, and its B-roll skips the same amount.
    pushed = _windows(
        covers=[{"clip": 2, "line": 4}, {"clip": 3, "line": 5, "start": 5.0, "end": 9.0}],
        lines=[{**lines[0], "end": 2.5}, {**lines[1], "start": 2.0, "end": 4.0}],
        segments=[{"clip": 0, "start": 0.0, "end": 10.0}],
        durations=[10, 10, 10, 10],
    )
    assert pushed == [
        {"segment": 0, "start": 1.0, "end": 2.5, "clip": 2, "src": 0.0},
        {"segment": 0, "start": 2.5, "end": 4.0, "clip": 3, "src": 5.5},
    ]


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
    room = {
        "path": "/tmp/room.mp4",
        "duration": 10,
        "width": 1280,
        "height": 720,
        "fps": 30.0,
        "role": "broll",
    }
    return talk, room


def test_render_keeps_the_voice_alone_under_the_cover():
    talk, room = _talk_room()
    segs = [{"clip": 0, "start": 0.25, "end": 8.0, "reason": "story"}]
    lines = [
        {"id": 4, "clip": 0, "start": 1.0, "end": 3.0, "keep": True, "reason": "story", "text": "hello"}
    ]
    covers = [{"clip": 1, "line": 4, "start": 0.0, "end": 4.0}]
    args = render_args(
        segs, [talk, room], "/tmp/out.mp4", polish=True, covers=covers, lines=lines, broll_sound="voice"
    )
    assert _timed(args) == [
        ("0.250", "0.750", "/tmp/talk.mp4"),
        ("0.000", "2.000", "/tmp/room.mp4"),
        ("1.000", "2.000", "/tmp/talk.mp4"),
        ("3.000", "5.000", "/tmp/talk.mp4"),
    ]
    branches = args[args.index("-filter_complex") + 1].split(";")
    cover_v = next(branch for branch in branches if branch.startswith("[1:v]"))
    cover_a = next(branch for branch in branches if branch.startswith("[2:a]"))
    back_v = next(branch for branch in branches if branch.startswith("[3:v]"))
    back_a = next(branch for branch in branches if branch.startswith("[3:a]"))
    assert not any(branch.startswith("[1:a]") for branch in branches)
    assert not any(branch.startswith("[2:v]") for branch in branches)
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in cover_v
    assert "scale=1280:720" not in cover_v
    assert cover_a.startswith("[2:a]aresample=osr=48000")
    assert "afade" not in cover_a
    assert cover_a.endswith("[a1]")
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
        broll_sound="voice",
    )
    assert stale == render_args(segs, [talk, room], "/tmp/out.mp4", polish=True)


def test_render_puts_no_picture_fade_on_a_join_under_a_run():
    talk, room = _talk_room()
    segs = [{"clip": 0, "start": 0.5, "end": 8.2, "reason": "a"}, {"clip": 0, "start": 10.8, "end": 20.0, "reason": "b"}]
    lines = _kept([1, 2, 3, 4], length=2.0, gap=3.0)
    for line in lines:
        line["text"] = "hello"
    covers = [{"clip": 1, "line": 2, "through": 3, "start": 5.0, "end": 9.5, "reason": "hides the cut"}]
    args = render_args(segs, [talk, room], "/tmp/out.mp4", polish=True, covers=covers, lines=lines)
    assert _timed(args) == [
        ("0.500", "5.500", "/tmp/talk.mp4"),
        ("5.000", "2.200", "/tmp/room.mp4"),
        ("6.000", "2.200", "/tmp/talk.mp4"),
        ("7.200", "2.200", "/tmp/room.mp4"),
        ("10.800", "2.200", "/tmp/talk.mp4"),
        ("13.000", "7.000", "/tmp/talk.mp4"),
    ]
    branches = args[args.index("-filter_complex") + 1].split(";")
    head = next(branch for branch in branches if branch.startswith("[0:v]"))
    first_cover = next(branch for branch in branches if branch.startswith("[1:v]"))
    second_cover = next(branch for branch in branches if branch.startswith("[3:v]"))
    tail = next(branch for branch in branches if branch.startswith("[5:v]"))
    assert "fade=t=in" in head
    assert "fade=t=out" not in first_cover
    assert "fade=t=in" not in second_cover
    assert "fade=t=out" in tail
    # The voice keeps its edges at the join.
    first_voice = next(branch for branch in branches if branch.startswith("[2:a]"))
    assert "afade=t=out" in first_voice


def test_render_seeks_into_the_broll_file_for_a_deep_beat():
    talk, room = _talk_room()
    segs = [{"clip": 0, "start": 0.25, "end": 8.0, "reason": "story"}]
    lines = [
        {"id": 4, "clip": 0, "start": 1.0, "end": 3.0, "keep": True, "reason": "story", "text": "hello"}
    ]
    covers = [{"clip": 1, "line": 4, "start": 6.0, "end": 6.7}]
    args = render_args(segs, [talk, room], "/tmp/out.mp4", polish=True, covers=covers, lines=lines)
    assert _timed(args) == [
        ("0.250", "0.750", "/tmp/talk.mp4"),
        ("6.000", "0.700", "/tmp/room.mp4"),
        ("1.000", "0.700", "/tmp/talk.mp4"),
        ("1.700", "6.300", "/tmp/talk.mp4"),
    ]


def test_silent_broll_renders_the_voice_alone_even_in_mix_mode():
    talk, room = _talk_room()
    quiet = {**room, "audio": False, "audio_codec": None, "sample_rate": 0}
    segs = [{"clip": 0, "start": 0.25, "end": 8.0, "reason": "story"}]
    lines = [
        {"id": 4, "clip": 0, "start": 1.0, "end": 3.0, "keep": True, "reason": "story", "text": "hello"}
    ]
    covers = [{"clip": 1, "line": 4, "start": 0.0, "end": 4.0}]
    args = render_args(segs, [talk, quiet], "/tmp/out.mp4", polish=True, covers=covers, lines=lines)
    assert _timed(args) == [
        ("0.250", "0.750", "/tmp/talk.mp4"),
        ("0.000", "2.000", "/tmp/room.mp4"),
        ("1.000", "2.000", "/tmp/talk.mp4"),
        ("3.000", "5.000", "/tmp/talk.mp4"),
    ]
    graph = args[args.index("-filter_complex") + 1]
    assert "amix" not in graph
    assert "volume=0.25" not in graph
    assert "[1:a]" not in graph
    branches = graph.split(";")
    assert any(branch.startswith("[2:a]aresample=osr=48000") for branch in branches)


def test_broll_does_not_set_the_picture_size():
    talk, room = _talk_room()
    segs = [{"clip": 1, "start": 0.0, "end": 2.0, "reason": "story"}]
    args = render_args(segs, [room, talk], "/tmp/out.mp4")
    graph = args[args.index("-filter_complex") + 1]
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in graph


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
        covers=[{"clip": 1, "line": 4, "start": 0.0, "end": 4.0}],
        lines=lines,
        broll_sound="voice",
    )
    assert _timed(args) == [
        ("0.000", "2.000", "/tmp/room.mp4"),
        ("0.000", "2.000", "/tmp/talk.mp4"),
        ("2.000", "4.000", "/tmp/talk.mp4"),
        ("0.000", "2.000", "/tmp/other.mp4"),
    ]
    branches = args[args.index("-filter_complex") + 1].split(";")
    cover_v = next(branch for branch in branches if branch.startswith("[0:v]"))
    cover_a = next(branch for branch in branches if branch.startswith("[1:a]"))
    back_v = next(branch for branch in branches if branch.startswith("[2:v]"))
    back_a = next(branch for branch in branches if branch.startswith("[2:a]"))
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
        covers=[{"clip": 1, "line": 4, "start": 0.0, "end": 4.0}],
        lines=lines,
        broll_sound="voice",
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


def _make_clip(path, size, tone=None, seconds=3):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=30"]
    if tone is None:
        cmd += ["-an"]
    else:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate=48000"]
    cmd += ["-t", str(seconds), str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-400:]


def test_voice_graph_encodes(tmp_path):
    talk = tmp_path / "talk.mp4"
    room = tmp_path / "room.mp4"
    _make_clip(talk, "640x360", 220)
    _make_clip(room, "320x180", 1760)
    clips = [
        {"path": str(talk), "duration": 3, "width": 640, "height": 360, "fps": 30.0, "pix_fmt": "yuv420p"},
        {
            "path": str(room),
            "duration": 3,
            "width": 320,
            "height": 180,
            "fps": 30.0,
            "pix_fmt": "yuv420p",
            "role": "broll",
        },
    ]
    segs = [{"clip": 0, "start": 0.0, "end": 2.5, "reason": "story"}]
    lines = [{"id": 4, "clip": 0, "start": 0.5, "end": 1.2, "keep": True, "reason": "story", "text": "hi"}]
    dst = tmp_path / "out.mp4"
    args = render_args(
        segs,
        clips,
        str(dst),
        polish=True,
        covers=[{"clip": 1, "line": 4, "start": 1.0, "end": 3.0}],
        lines=lines,
        broll_sound="voice",
    )
    graph = args[args.index("-filter_complex") + 1]
    assert "amix" not in graph
    assert "volume=0.25" not in graph
    assert "loudnorm" not in graph
    assert ("1.000", "0.700", str(room)) in _timed(args)
    proc = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert dst.stat().st_size > 0
    talk_band = "lowpass=f=400,volumedetect"
    room_band = "highpass=f=1000,volumedetect"
    # The voice never leaves. The B-roll sound never arrives.
    assert _mean_volume(dst, 0.10, 0.30, talk_band) > -30
    assert _mean_volume(dst, 0.10, 0.30, room_band) < -45
    assert _mean_volume(dst, 0.65, 0.40, talk_band) > -30
    assert _mean_volume(dst, 0.65, 0.40, room_band) < -45
    assert _mean_volume(dst, 1.45, 0.40, talk_band) > -30
    assert _mean_volume(dst, 1.45, 0.40, room_band) < -45


def test_silent_broll_graph_encodes(tmp_path):
    talk = tmp_path / "talk.mp4"
    quiet = tmp_path / "quiet.mp4"
    _make_clip(talk, "640x360", 220)
    _make_clip(quiet, "320x180", None)
    talk_info = probe(str(talk))
    quiet_info = probe(str(quiet), need_audio=False)
    quiet_info["role"] = "broll"
    assert quiet_info["audio"] is False
    segs = [{"clip": 0, "start": 0.0, "end": 2.5, "reason": "story"}]
    lines = [{"id": 4, "clip": 0, "start": 0.5, "end": 1.2, "keep": True, "reason": "story", "text": "hi"}]
    dst = tmp_path / "out.mp4"
    args = render_args(
        segs,
        [talk_info, quiet_info],
        str(dst),
        polish=True,
        covers=[{"clip": 1, "line": 4, "start": 0.0, "end": 3.0}],
        lines=lines,
        broll_sound="mix",
    )
    assert "amix" not in args[args.index("-filter_complex") + 1]
    proc = subprocess.run(["ffmpeg", *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert _mean_volume(dst, 0.65, 0.40, "lowpass=f=400,volumedetect") > -30


def test_render_mixes_the_clip_under_the_voice():
    talk, room = _talk_room()
    segs = [{"clip": 0, "start": 0.25, "end": 8.0, "reason": "story"}]
    lines = [
        {"id": 4, "clip": 0, "start": 1.0, "end": 3.0, "keep": True, "reason": "story", "text": "hello"}
    ]
    covers = [{"clip": 1, "line": 4, "start": 0.0, "end": 4.0}]
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
        covers=[{"clip": 1, "line": 4, "start": 0.0, "end": 4.0}],
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
        covers=[{"clip": 1, "line": 4, "start": 0.0, "end": 4.0}],
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
    talk = tmp_path / "talk.mp4"
    room = tmp_path / "room.mp4"
    _make_clip(talk, "640x360", 220)
    _make_clip(room, "320x180", 1760)
    clips = [
        {"path": str(talk), "duration": 3, "width": 640, "height": 360, "fps": 30.0, "pix_fmt": "yuv420p"},
        {
            "path": str(room),
            "duration": 3,
            "width": 320,
            "height": 180,
            "fps": 30.0,
            "pix_fmt": "yuv420p",
            "role": "broll",
        },
    ]
    segs = [{"clip": 0, "start": 0.0, "end": 2.5, "reason": "story"}]
    lines = [{"id": 4, "clip": 0, "start": 0.5, "end": 1.2, "keep": True, "reason": "story", "text": "hi"}]
    dst = tmp_path / "mixed.mp4"
    args = render_args(
        segs,
        clips,
        str(dst),
        polish=True,
        covers=[{"clip": 1, "line": 4, "start": 0.0, "end": 3.0}],
        lines=lines,
    )
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


def test_probe_accepts_a_silent_file_only_when_told(tmp_path):
    quiet = tmp_path / "quiet.mp4"
    _make_clip(quiet, "320x180", None, seconds=2)
    with pytest.raises(SystemExit, match="No audio stream"):
        probe(str(quiet))
    info = probe(str(quiet), need_audio=False)
    assert info["audio"] is False
    assert info["audio_codec"] is None
    assert info["sample_rate"] == 0
    assert info["duration"] > 1.5
    assert info["width"] == 320
    loud = tmp_path / "loud.mp4"
    _make_clip(loud, "320x180", 440, seconds=2)
    assert probe(str(loud))["audio"] is True


def test_unknown_broll_sound_is_rejected(capsys):
    # Argparse prints the choice error and raises SystemExit(2). The text is not on the exception.
    for value in ("silent", "clip"):
        with pytest.raises(SystemExit) as render_exit:
            main(["render", "out", "--b-roll-sound", value])
        assert render_exit.value.code == 2
        assert "invalid choice" in capsys.readouterr().err
        with pytest.raises(SystemExit) as run_exit:
            main(["run", "a.mp4", "--out", "out", "--b-roll-sound", value])
        assert run_exit.value.code == 2
        assert "invalid choice" in capsys.readouterr().err
        with pytest.raises(SystemExit, match="Unknown b-roll sound"):
            render_args(
                [{"clip": 0, "start": 0.0, "end": 1.0}],
                [{"path": "/tmp/a.mp4", "width": 16, "height": 16, "fps": 30.0}],
                "/tmp/out.mp4",
                broll_sound=value,
            )
    with pytest.raises(SystemExit) as old_flag:
        main(["run", "a.mp4", "--out", "out", "--b-roll"])
    assert old_flag.value.code == 2


def test_main_passes_voice_sound_and_broll_files(monkeypatch):
    seen = {}

    def fake_render(cuts, scene_transition="dip", broll_sound="mix"):
        seen["cuts"] = cuts
        seen["sound"] = broll_sound
        seen["transition"] = scene_transition

    monkeypatch.setattr("botcut.cli.render_saved", fake_render)
    main(["render", "out", "--b-roll-sound", "voice"])
    assert seen == {"cuts": "out", "sound": "voice", "transition": "dip"}

    def fake_run(files, out, **kwargs):
        seen["files"] = files
        seen["out"] = out
        seen["kwargs"] = kwargs

    monkeypatch.setattr("botcut.cli.run", fake_run)
    main(["run", "a.mp4", "b.mp4", "--out", "out", "--b-roll-file", "b.mp4", "--b-roll-file", "a.mp4"])
    assert seen["files"] == ["a.mp4", "b.mp4"]
    assert seen["kwargs"]["broll_files"] == ["b.mp4", "a.mp4"]
    assert seen["kwargs"]["broll_sound"] == "mix"
    main(["run", "a.mp4", "--out", "out"])
    assert seen["kwargs"]["broll_files"] == []


def test_shot_list_marks_broll_with_a_prefix(tmp_path):
    listing = tmp_path / "shots.txt"
    listing.write_text("# the movie\n/tmp/talk.mp4\n\nB-roll /tmp/room.mp4\nb-roll   /tmp/drone.mp4\n")
    assert resolve_inputs([str(listing)]) == ["/tmp/talk.mp4", "/tmp/room.mp4", "/tmp/drone.mp4"]
    assert resolve_broll([str(listing)]) == ["/tmp/room.mp4", "/tmp/drone.mp4"]
    assert resolve_inputs(["/tmp/a.mp4", "/tmp/b.mp4"]) == ["/tmp/a.mp4", "/tmp/b.mp4"]
    assert resolve_broll(["/tmp/a.mp4", "/tmp/b.mp4"]) == []


def test_broll_file_must_be_listed_and_not_a_card(tmp_path):
    talk = tmp_path / "talk.mp4"
    card = tmp_path / "botcut-card-1-open.mp4"
    talk.write_bytes(b"")
    card.write_bytes(b"")
    with pytest.raises(SystemExit, match="not in the list"):
        run([str(talk)], str(tmp_path / "out"), broll_files=[str(tmp_path / "nope.mp4")])
    with pytest.raises(SystemExit, match="cannot be B-roll"):
        run([str(talk), str(card)], str(tmp_path / "out"), broll_files=[str(card)])


def test_assemble_ignores_broll_and_writes_no_covers(monkeypatch, tmp_path):
    def boom(*_args, **_kwargs):
        raise AssertionError("choose_covers")

    monkeypatch.setattr("botcut.cli.choose_covers", boom)
    seen = {"need_audio": []}

    def fake_probe(path, need_audio=True):
        seen["need_audio"].append(need_audio)
        return {
            "path": path,
            "duration": 1.0,
            "width": 320,
            "height": 180,
            "fps": 30.0,
            "rotate": 0,
            "pix_fmt": "yuv420p",
        }

    monkeypatch.setattr("botcut.cli.probe", fake_probe)

    def fake_render(*_args, **kwargs):
        seen["sound"] = kwargs.get("broll_sound")

    monkeypatch.setattr("botcut.cli.render_with_progress", fake_render)
    silent = tmp_path / "silent.mp4"
    silent.write_bytes(b"")
    run([str(silent)], str(tmp_path / "out"), mode="assemble", broll_files=[str(silent)], broll_sound="voice")
    doc = json.loads((tmp_path / "out" / "cuts.json").read_text())
    assert "covers" not in doc
    assert "broll_sound" not in doc
    assert "role" not in doc["clips"][0]
    assert doc["mode"] == "assemble"
    assert seen["sound"] == "voice"
    # Assemble plays every file with its own sound, so a silent one is still refused.
    assert seen["need_audio"] == [True]


def test_fake_cut_writes_a_cover_only_for_a_marked_file(monkeypatch, tmp_path, capsys):
    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr("botcut.net.requests.post", boom)
    monkeypatch.setattr("botcut.cli.scene_changes", boom)
    calls = {"n": 0}

    def sequenced():
        calls["n"] += 1
        if calls["n"] % 2 == 1:
            # Four lines of two seconds, a second apart, so a run can sit between the first and the last.
            words = []
            for i in range(4):
                at = 0.3 + i * 3.0
                words.append({"text": f"line{i}", "start": at, "end": at + 1.0})
                words.append({"text": "here", "start": at + 1.1, "end": at + 2.0})
            return {"duration": 13.0, "words": words}
        return {"duration": 4.0, "words": []}

    monkeypatch.setattr("botcut.cli.transcribe_fake", sequenced)

    talk = tmp_path / "talk.mp4"
    room = tmp_path / "room.mp4"
    _make_clip(talk, "320x180", 440, seconds=13)
    _make_clip(room, "320x180", 440, seconds=4)
    off = tmp_path / "off"
    run([str(talk), str(room)], str(off), decide=True)
    off_doc = json.loads((off / "cuts.json").read_text())
    assert "covers" not in off_doc
    assert all("role" not in clip for clip in off_doc["clips"])
    assert not list((off / "work").glob("*.beats.json"))
    out = capsys.readouterr().out
    assert "Transcribing 2/2" in out
    assert "Reading beats" not in out

    on = tmp_path / "on"
    run([str(talk), str(room)], str(on), decide=True, broll_files=[str(room)])
    on_doc = json.loads((on / "cuts.json").read_text())
    assert on_doc["clips"][1]["role"] == "broll"
    assert "role" not in on_doc["clips"][0]
    assert len(on_doc["covers"]) == 1
    cover = on_doc["covers"][0]
    assert set(cover) == {"clip", "line", "through", "start", "end", "reason"}
    assert cover["clip"] == 1
    assert (cover["line"], cover["through"]) == (1, 2)
    assert cover["start"] == 0.0
    assert cover["end"] == pytest.approx(4.0, abs=0.2)
    assert cover["reason"] == "fake"
    assert on_doc["covers_reply"] == FAKE_COVER_REPLY
    assert "covers_reply" not in off_doc
    assert all(line["clip"] == 0 for line in on_doc["lines"])
    beats = json.loads((on / "work" / "1-room.beats.json").read_text())
    assert len(beats) == 1
    assert not list((on / "work").glob("1-room.*words.json"))
    out = capsys.readouterr().out
    assert "Transcribing 1/1" in out
    assert "Transcribing 2/2" not in out
    assert "Reading beats" in out
    assert "Choosing covers" in out


def test_render_saved_keeps_covers_and_probes_broll_without_sound(monkeypatch, tmp_path):
    seen = {"calls": [], "probes": []}

    def fake_render(*_args, **kwargs):
        seen["calls"].append(
            {
                "covers": kwargs.get("covers"),
                "lines": kwargs.get("lines"),
                "broll_sound": kwargs.get("broll_sound"),
                "clips": _args[1],
            }
        )

    monkeypatch.setattr("botcut.cli.render_with_progress", fake_render)

    def fake_probe(path, need_audio=True):
        seen["probes"].append((path, need_audio))
        return {
            "path": path,
            "duration": 12.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "rotate": 0,
            "pix_fmt": "yuv420p",
        }

    monkeypatch.setattr("botcut.cli.probe", fake_probe)
    out = tmp_path / "out"
    out.mkdir()
    cover = {"clip": 1, "line": 4, "start": 2.0, "end": 5.5}
    doc = {
        "version": 1,
        "clips": [
            {"index": 0, "path": "/tmp/talk.mp4", "duration": 12},
            {"index": 1, "path": "/tmp/room.mp4", "duration": 8, "role": "broll"},
        ],
        "lines": [
            {"id": 4, "clip": 0, "start": 1.0, "end": 3.0, "text": "hi", "keep": True, "reason": "story"}
        ],
        "segments": [{"clip": 0, "start": 0.25, "end": 8.0, "reason": "story"}],
        "covers": [cover],
        "tighten": {"max_pause": 0.8, "snap": False},
        "trimmed": True,
    }
    path = out / "cuts.json"
    path.write_text(json.dumps(doc) + "\n")
    render_saved(str(out))
    assert json.loads(path.read_text())["covers"] == [cover]
    assert seen["probes"] == [("/tmp/talk.mp4", True), ("/tmp/room.mp4", False)]
    assert seen["calls"][0]["clips"][1]["role"] == "broll"
    assert "role" not in seen["calls"][0]["clips"][0]

    doc.pop("trimmed")
    path.write_text(json.dumps(doc) + "\n")
    render_saved(str(out))
    saved = json.loads(path.read_text())
    assert saved["covers"] == [cover]
    assert saved["clips"][1]["role"] == "broll"
    assert saved["segments"] == [{"clip": 0, "start": 0.75, "end": 3.4, "reason": "story"}]
    assert len(seen["calls"]) == 2
    for call in seen["calls"]:
        assert call["covers"] == [cover]
        assert call["broll_sound"] == "mix"
        assert call["lines"][0]["id"] == 4
        assert call["lines"][0]["start"] == 1.0
        assert call["lines"][0]["end"] == 3.0
    assert "broll_sound" not in saved
    render_saved(str(out), broll_sound="voice")
    assert seen["calls"][-1]["broll_sound"] == "voice"
    assert seen["calls"][-1]["covers"] == [cover]


def test_captions_skip_a_broll_clip(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "0-talk.words.json").write_text(
        json.dumps({"words": [{"text": "hi", "start": 0.5, "end": 0.9}]}) + "\n"
    )
    doc = {
        "stt": "xai:grok-voice-transcribe-2.0",
        "clips": [
            {"index": 0, "path": "/tmp/talk.mp4", "duration": 4},
            {"index": 1, "path": "/tmp/room.mp4", "duration": 4, "role": "broll"},
        ],
    }
    assert load_words_by_clip(doc, str(tmp_path)) == [[{"text": "hi", "start": 0.5, "end": 0.9}], []]
    plain = {**doc, "clips": [doc["clips"][0], {"index": 1, "path": "/tmp/room.mp4", "duration": 4}]}
    with pytest.raises(SystemExit, match="No word cache"):
        load_words_by_clip(plain, str(tmp_path))


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
        "covers": [{"clip": 3, "line": 1, "start": 2.0, "end": 5.5}, {"clip": 4, "line": 2, "start": 0.0, "end": 4.0}],
    }
    path = tmp_path / "cuts.json"
    path.write_text(json.dumps(doc) + "\n")
    revise(str(path), "shorter")
    saved = json.loads(path.read_text())
    assert saved["covers"] == [{"clip": 3, "line": 1, "start": 2.0, "end": 5.5}]
    assert saved["lines"][0]["keep"] is True
    assert saved["lines"][1]["keep"] is False
    assert [row["id"] for row in saved["lines"]] == [1, 2]
