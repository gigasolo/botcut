import json
import socket

import pytest

from botcut.cli import main
from botcut.revise import FAKE_INTENT, REVISE_SCHEMA, REVISE_SYSTEM, apply_revise, parse_revise, revise


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
        "intent": "A ride",
        "pace": "tight",
        "dip": True,
        "keep": [{"id": 1, "reason": "clean"}],
        "deliver": "none",
    }
    assert parse_revise(good)["pace"] == "tight"
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
    assert set(schema["properties"]) == {"intent", "pace", "dip", "keep", "deliver"}
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
