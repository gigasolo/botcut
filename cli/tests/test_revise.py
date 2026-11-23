import json
import socket

import pytest

from botcut.cli import main
from botcut.revise import (
    FAKE_INTENT,
    FAKE_REPLY,
    REVISE_SCHEMA,
    REVISE_SYSTEM,
    apply_proposal,
    apply_revise,
    parse_revise,
    read_history,
    revise,
)


def _line(uid, text, keep=True, reason="story"):
    return {
        "id": uid,
        "clip": 0,
        "start": 0.2 + uid,
        "end": 1.2 + uid,
        "text": text,
        "keep": keep,
        "reason": reason,
        "still": f"/tmp/{uid}.jpg",
    }


def _write(tmp_path, lines, max_pause=0.8):
    doc = {
        "version": 1,
        "mode": "speech",
        "intent": "A quiet ride",
        "tighten": {"max_pause": max_pause, "snap": True},
        "clips": [{"index": 0, "path": "/tmp/a.mp4", "duration": 10}],
        "segments": [{"clip": 0, "start": 0.0, "end": 4.0, "reason": "story"}],
        "lines": lines,
        "dropped": [],
    }
    path = tmp_path / "cuts.json"
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def test_apply_keeps_listed_ids_and_drops_the_rest():
    lines = [_line(1, "hello", keep=False), _line(2, "the stumble", keep=True)]
    updated = apply_revise(lines, [{"id": 1, "reason": "clean"}, {"id": 99, "reason": "nope"}])
    assert len(updated) == 2
    assert updated[0]["keep"] is True
    assert updated[0]["reason"] == "clean"
    assert updated[0]["start"] == lines[0]["start"]
    assert updated[0]["still"] == lines[0]["still"]
    assert updated[1]["keep"] is False
    assert updated[1]["reason"] == "dropped"
    assert updated[1]["text"] == "the stumble"
    assert updated[1]["end"] == lines[1]["end"]


def test_parse_rejects_times_padding_and_a_bad_pace():
    good = {
        "reply": "I'd keep  the first line.",
        "intent": "A ride",
        "pace": "tight",
        "dip": True,
        "keep": [{"id": 1, "reason": "clean"}],
        "deliver": "none",
    }
    assert parse_revise(good)["pace"] == "tight"
    assert parse_revise(good)["reply"] == "I'd keep the first line."
    no_reply = {key: value for key, value in good.items() if key != "reply"}
    with pytest.raises(SystemExit, match="not a revise"):
        parse_revise(no_reply)
    blank_reply = {**good, "reply": "  "}
    with pytest.raises(SystemExit, match="not a revise"):
        parse_revise(blank_reply)
    timed = {**good, "keep": [{"id": 1, "reason": "clean", "start": 0.2}]}
    with pytest.raises(SystemExit, match="not a revise"):
        parse_revise(timed)
    padded = {**good, "padding": 0.2}
    with pytest.raises(SystemExit, match="not a revise"):
        parse_revise(padded)
    bad_pace = {**good, "pace": "faster"}
    with pytest.raises(SystemExit, match="not a revise"):
        parse_revise(bad_pace)
    schema = REVISE_SCHEMA["json_schema"]["schema"]
    assert set(schema["properties"]) == {
            "reply", "intent", "pace", "dip", "keep", "deliver", "covers", "fillers", "cameras", "favor",
        }
    assert set(schema["properties"]["covers"]["items"]["properties"]) == {"beat", "line", "through", "reason"}
    assert "A listed run stays." in REVISE_SYSTEM
    assert parse_revise(good)["covers"] is None
    with_covers = {**good, "covers": [{"beat": 2, "line": 3, "through": 4, "reason": "the road"}]}
    assert parse_revise(with_covers)["covers"] == [{"beat": 2, "line": 3, "through": 4, "reason": "the road"}]
    timed_cover = {**good, "covers": [{"beat": 2, "line": 3, "through": 4, "reason": "x", "start": 1.0}]}
    with pytest.raises(SystemExit, match="not a revise"):
        parse_revise(timed_cover)
    assert "reply" in schema["required"]
    assert "The reply is one or two plain sentences" in REVISE_SYSTEM
    assert "start" not in json.dumps(schema)
    assert "Do not return times" in REVISE_SYSTEM
    assert "Deliver never changes the picture." in REVISE_SYSTEM
    assert "none only means not to mark render, captions, or short." in REVISE_SYSTEM
    assert "A listed id is kept." in REVISE_SYSTEM


def test_fake_revise_drops_one_id_and_leaves_max_pause(monkeypatch, tmp_path):
    def boom(*_args, **_kwargs):
        raise AssertionError("socket")

    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr("botcut.net.requests.post", boom)

    path = _write(tmp_path, [_line(1, "hello"), _line(2, "the stumble")])
    before = json.loads(path.read_text())
    revise(str(path), "drop the stumble", pace="measured", dip=True)
    doc = json.loads(path.read_text())
    assert doc["tighten"] == before["tighten"]
    assert doc["segments"] == before["segments"]
    assert doc["intent"] == FAKE_INTENT
    assert doc["revise"] == {"pace": "frenzied", "dip": False, "deliver": "render"}
    assert [line["id"] for line in doc["lines"]] == [1, 2]
    assert doc["lines"][0]["keep"] is True
    assert doc["lines"][0]["reason"] == "fake"
    assert doc["lines"][0]["start"] == before["lines"][0]["start"]
    assert doc["lines"][1]["keep"] is False
    assert doc["lines"][1]["reason"] == "dropped"
    assert not (tmp_path / "rough_cut.mp4").exists()
    assert "supersecret" not in path.read_text()


def test_revise_refuses_without_a_key_and_does_not_call_out(monkeypatch, tmp_path):
    called = {"post": False}

    def boom(*_args, **_kwargs):
        called["post"] = True
        raise AssertionError("network")

    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr("botcut.net.requests.post", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    path = _write(tmp_path, [_line(1, "hello")])
    before = path.read_text()
    with pytest.raises(SystemExit, match="XAI_API_KEY is not set"):
        revise(str(path), "make it tighter")
    assert called["post"] is False
    assert path.read_text() == before


def test_revise_hides_the_key_and_leaves_max_pause(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.delenv("BOTCUT_LLM_MODEL", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "supersecret")
    seen = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "reply": "Shorter it is.",
                                    "intent": "Shorter.",
                                    "pace": "frenzied",
                                    "dip": False,
                                    "keep": [{"id": 1, "reason": "clean"}],
                                    "deliver": "captions",
                                }
                            )
                        }
                    }
                ]
            }

    def post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["body"] = json
        seen["auth"] = headers["Authorization"]
        return Response()

    monkeypatch.setattr("botcut.net.requests.post", post)
    path = _write(tmp_path, [_line(1, "hello"), _line(2, "the stumble")], max_pause=0.8)
    argv = ["revise", str(path), "make it tighter", "--pace", "open", "--scene-transition", "dip"]
    assert "supersecret" not in " ".join(argv)
    assert "--max-pause" not in argv
    main(argv)
    captured = capsys.readouterr()
    assert "supersecret" not in captured.out
    assert "supersecret" not in captured.err
    assert "supersecret" not in path.read_text()
    assert "supersecret" not in json.dumps(seen["body"])
    assert seen["auth"] == "Bearer supersecret"
    assert seen["body"]["response_format"] == REVISE_SCHEMA
    assert "Do not return times" in seen["body"]["messages"][0]["content"]
    doc = json.loads(path.read_text())
    assert doc["tighten"]["max_pause"] == pytest.approx(0.8)
    assert doc["intent"] == "Shorter."
    assert doc["lines"][1]["reason"] == "dropped"
    assert doc["revise"]["deliver"] == "captions"
    assert doc["revise"]["pace"] == "frenzied"
    assert not (tmp_path / "rough_cut.mp4").exists()
    assert not (tmp_path / "rough_cut.srt").exists()


def test_help_note_is_positional_and_bare_help_does_not_rewrite(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    path = _write(tmp_path, [_line(1, "hello"), _line(2, "the stumble")])
    doc = json.loads(path.read_text())
    doc["revise"] = {"pace": "open", "dip": True, "deliver": "none"}
    path.write_text(json.dumps(doc, indent=2) + "\n")

    bare = path.read_text()
    with pytest.raises(SystemExit) as caught:
        main(["revise", str(path), "--help"])
    assert caught.value.code in (0, None)
    assert path.read_text() == bare
    help_out = capsys.readouterr().out
    assert "usage:" in help_out

    main(["revise", str(path), "--pace", "measured", "--scene-transition", "dip", "--", "--help"])
    revised = json.loads(path.read_text())
    assert revised["intent"] == FAKE_INTENT
    assert revised["revise"]["pace"] == "frenzied"
    assert revised["lines"][1]["reason"] == "dropped"
    assert "usage:" not in capsys.readouterr().out


def test_propose_writes_a_proposal_and_leaves_cuts_alone(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    path = _write(tmp_path, [_line(1, "hello"), _line(2, "the stumble")])
    before = path.read_text()
    main(["revise", str(path), "--pace", "measured", "--propose", "--", "drop the stumble"])
    assert path.read_text() == before
    proposal = json.loads((tmp_path / "proposal.json").read_text())
    assert proposal["note"] == "drop the stumble"
    assert proposal["reply"] == FAKE_REPLY
    assert proposal["intent"] == FAKE_INTENT
    assert proposal["pace"] == "frenzied"
    assert proposal["dip"] is False
    assert [item["id"] for item in proposal["keep"]] == [1, 10**9]
    # No B-roll in the cut, so the proposal says nothing about runs.
    assert proposal["covers"] is None
    assert FAKE_REPLY in capsys.readouterr().out


def test_apply_lands_the_proposal_without_the_model(monkeypatch, tmp_path):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("botcut.net.requests.post", boom)
    path = _write(tmp_path, [_line(1, "hello"), _line(2, "the stumble")])
    with pytest.raises(SystemExit, match="No proposal to apply"):
        apply_proposal(str(path))
    proposal = {
        "note": "drop the stumble",
        "reply": "Dropping the stumble.",
        "intent": "Clean.",
        "pace": "tight",
        "dip": True,
        "keep": [{"id": 1, "reason": "clean"}],
        "deliver": "none",
    }
    (tmp_path / "proposal.json").write_text(json.dumps(proposal))
    main(["revise", str(path), "--apply"])
    doc = json.loads(path.read_text())
    assert doc["intent"] == "Clean."
    assert doc["revise"] == {"pace": "tight", "dip": True, "deliver": "none"}
    assert doc["lines"][0]["keep"] is True
    assert doc["lines"][0]["reason"] == "clean"
    assert doc["lines"][1]["keep"] is False
    assert doc["lines"][1]["reason"] == "dropped"
    assert not (tmp_path / "proposal.json").exists()
    with pytest.raises(SystemExit, match="--apply takes no note"):
        main(["revise", str(path), "--apply", "--", "again"])


def test_history_turns_go_before_the_note(monkeypatch, tmp_path):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "supersecret")
    seen = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "reply": "Done.",
                                    "intent": "Shorter.",
                                    "pace": "tight",
                                    "dip": True,
                                    "keep": [{"id": 1, "reason": "clean"}],
                                    "deliver": "none",
                                }
                            )
                        }
                    }
                ]
            }

    def post(url, headers=None, json=None, timeout=None):
        seen["body"] = json
        return Response()

    monkeypatch.setattr("botcut.net.requests.post", post)
    history = tmp_path / "chat.json"
    history.write_text(
        json.dumps(
            [
                {"role": "you", "text": "make it  tighter"},
                {"role": "bot", "text": "I'd drop two lines."},
                {"role": "bot", "text": ""},
                {"role": "odd", "text": "ignored"},
                "not a turn",
            ]
        )
    )
    assert read_history(str(history)) == [
        {"role": "user", "content": "make it tighter"},
        {"role": "assistant", "content": "I'd drop two lines."},
    ]
    assert read_history(str(tmp_path / "missing.json")) == []
    path = _write(tmp_path, [_line(1, "hello"), _line(2, "the stumble")])
    main(["revise", str(path), "--propose", "--history", str(history), "--", "yes, and shorter"])
    messages = seen["body"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "make it tighter"}
    assert messages[2] == {"role": "assistant", "content": "I'd drop two lines."}
    assert messages[3]["role"] == "user"
    assert messages[3]["content"].endswith("Note: yes, and shorter")
    assert (tmp_path / "proposal.json").exists()


def _broll_doc(tmp_path, lines, covers):
    doc = {
        "version": 1,
        "mode": "speech",
        "intent": "A ride",
        "tighten": {"max_pause": 0.8, "snap": True},
        "clips": [
            {"index": 0, "path": "/tmp/a.mp4", "duration": 40},
            {"index": 1, "path": "/tmp/room.mp4", "duration": 12, "role": "broll"},
        ],
        "segments": [{"clip": 0, "start": 0.0, "end": 40.0, "reason": "story"}],
        "lines": lines,
        "dropped": [],
        "covers": covers,
    }
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "1-room.beats.json").write_text(json.dumps([[0.0, 4.0], [4.0, 8.0], [8.0, 12.0]]))
    path = tmp_path / "cuts.json"
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def _runs_lines():
    rows = []
    for uid in range(1, 6):
        rows.append(_line(uid, f"line {uid}"))
        rows[-1]["start"] = uid * 3.0
        rows[-1]["end"] = uid * 3.0 + 2.5
    return rows


def test_revise_shows_the_model_the_beats_and_the_runs_and_lands_its_list(monkeypatch, tmp_path):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "supersecret")
    lines = _runs_lines()
    laid = [
        {"clip": 1, "line": 2, "through": 3, "start": 4.0, "end": 9.5, "reason": "hides the cut"},
        {"clip": 1, "line": 4, "through": 4, "start": 8.0, "end": 10.5, "reason": "the road"},
    ]
    path = _broll_doc(tmp_path, lines, laid)
    seen = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "reply": "I took the second run off.",
                                    "intent": "A ride",
                                    "pace": "open",
                                    "dip": True,
                                    "keep": [{"id": uid, "reason": "story"} for uid in range(1, 6)],
                                    "deliver": "none",
                                    "covers": [{"beat": 1, "line": 2, "through": 3, "reason": "hides the cut"}],
                                }
                            )
                        }
                    }
                ]
            }

    def post(url, headers=None, json=None, timeout=None):
        seen["body"] = json
        return Response()

    monkeypatch.setattr("botcut.net.requests.post", post)
    monkeypatch.setattr("botcut.media.grab_still", lambda *_args: False)
    revise(str(path), "less B-roll")
    user = seen["body"]["messages"][-1]["content"]
    assert "beat 0, 4.0s, shot 1" in user
    assert "beat 2, 4.0s, shot 1" in user
    assert "run: beat 1, lines 2-3, hides the cut" in user
    assert "run: beat 2, lines 4-4, the road" in user
    assert "/tmp/room.mp4" not in user
    saved = json.loads(path.read_text())
    # The listed run stays, resolved again from its beat; the unlisted one goes.
    assert saved["covers"] == [
        {"clip": 1, "line": 2, "through": 3, "start": 4.0, "end": 9.5, "reason": "hides the cut"}
    ]


def test_revise_without_broll_lists_no_beats_and_keeps_the_covers_it_has(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    lines = _runs_lines()
    laid = [{"clip": 1, "line": 2, "through": 3, "start": 4.0, "end": 9.5, "reason": "hides the cut"}]
    path = _broll_doc(tmp_path, lines, laid)
    # Fake revise drops the last line, which the run does not touch, and hands the runs back.
    revise(str(path), "shorter")
    saved = json.loads(path.read_text())
    assert saved["covers"] == laid
    assert saved["lines"][-1]["keep"] is False
