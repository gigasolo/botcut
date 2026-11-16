"""Long shoots, repeated runs, and several shots at once."""

import json
import os
import threading

import pytest

from botcut import cli
from botcut.media import silences
from botcut.pick import chunks, pick


def _utts(count):
    return [
        {"id": i, "clip": 0, "start": float(i), "end": i + 0.5, "text": f"line {i}"} for i in range(count)
    ]


def test_a_short_list_is_one_part():
    utts = _utts(150)
    parts = chunks(utts)
    assert len(parts) == 1
    assert parts[0]["owned"] == set(range(150))


def test_every_line_of_a_long_list_is_owned_once_and_neighbours_overlap():
    utts = _utts(400)
    parts = chunks(utts)
    assert len(parts) == 3
    owned = [uid for part in parts for uid in sorted(part["owned"])]
    assert owned == list(range(400))
    # Each part sees ten lines of the next, so a retake across the join is read whole.
    first = [u["id"] for u in parts[0]["lines"]]
    second = [u["id"] for u in parts[1]["lines"]]
    assert first[-10:] == second[:10]
    # The shared lines are split down the middle.
    assert max(parts[0]["owned"]) == 144
    assert min(parts[1]["owned"]) == 145


class _Reply:
    status_code = 200
    text = ""

    def __init__(self, content):
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def test_a_long_list_is_asked_in_parts_and_merged_by_owner(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "secret")
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    systems = []
    lock = threading.Lock()

    def post(url, headers=None, json=None, timeout=None):
        text = json["messages"][1]["content"]
        ids = [int(row.split("]")[0][1:]) for row in text.splitlines()]
        with lock:
            systems.append(json["messages"][0]["content"])
        # Each part keeps every line it was shown, including the shared ones.
        keep = [{"id": uid, "reason": "ok"} for uid in ids]
        return _Reply(__import__("json").dumps({"keep": keep}))

    monkeypatch.setattr("botcut.net.requests.post", post)
    kept = pick(_utts(400))
    # A shared line comes back from two parts and is kept once, in order.
    assert [item["id"] for item in kept] == list(range(400))
    assert len(systems) == 3
    assert all("of 3 of the movie" in system for system in systems)


def test_a_reply_that_is_not_a_keep_list_is_asked_for_once_more(monkeypatch, capsys):
    monkeypatch.setenv("XAI_API_KEY", "secret")
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    replies = ["not json", '{"keep": [{"id": 0, "reason": "ok"}]}']
    monkeypatch.setattr("botcut.net.requests.post", lambda *_a, **_k: _Reply(replies.pop(0)))
    assert pick(_utts(1)) == [{"id": 0, "reason": "ok"}]
    assert "Trying again" in capsys.readouterr().out

    replies[:] = ["not json", "still not json"]
    with pytest.raises(SystemExit, match="not a keep list"):
        pick(_utts(1))


def test_a_replaced_shot_or_another_transcriber_forgets_what_was_heard(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    shot = tmp_path / "talk.mp4"
    shot.write_bytes(b"first take")
    clip = {"path": str(shot)}
    cli._drop_stale_caches(str(work), 0, clip, "xai:grok-voice-transcribe-2.0")
    words = work / "0-talk.xai.words.json"
    pauses = work / "0-talk.silences.json"
    other = work / "1-talk.xai.words.json"
    for path in (words, pauses, other):
        path.write_text("{}")

    # The same file and transcriber: everything heard is still good.
    cli._drop_stale_caches(str(work), 0, clip, "xai:grok-voice-transcribe-2.0")
    assert words.exists() and pauses.exists()

    # A re-export under the same name is a different recording.
    shot.write_bytes(b"second take, longer")
    cli._drop_stale_caches(str(work), 0, clip, "xai:grok-voice-transcribe-2.0")
    assert not words.exists() and not pauses.exists()
    assert other.exists()

    words.write_text("{}")
    cli._drop_stale_caches(str(work), 0, clip, "local:faster-whisper:small")
    assert not words.exists()
    assert json.loads((work / "0-talk.stamp.json").read_text())["stt"] == "local:faster-whisper:small"


def test_shots_are_transcribed_together_and_land_in_their_own_order(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "secret")
    paths = []
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        path = tmp_path / name
        path.write_bytes(b"x")
        paths.append(str(path))
    monkeypatch.setattr(cli, "probe", lambda path, need_audio=True: {"path": path, "duration": 10.0})
    started = threading.Barrier(3, timeout=5)

    def words_for(work, index, stem, backend, flac, clip, whisper_model):
        # All three are in flight before any returns: they were not sent one by one.
        started.wait()
        return [{"text": stem, "start": 0.0, "end": 0.4}]

    monkeypatch.setattr(cli, "_words_for_clip", words_for)
    monkeypatch.setattr(cli, "_silences_for_clip", lambda *a: [])
    monkeypatch.setattr(cli, "_attach_stills", lambda *a: None)
    monkeypatch.setattr(cli, "pick", lambda utts, intent="": [{"id": u["id"], "reason": "ok"} for u in utts])
    cli.run(paths, str(tmp_path / "out"), decide=True)
    doc = json.loads((tmp_path / "out" / "cuts.json").read_text())
    assert [(line["clip"], line["text"]) for line in doc["lines"]] == [(0, "a"), (1, "b"), (2, "c")]
    shown = [row for row in capsys.readouterr().out.splitlines() if row.startswith("Transcribing")]
    assert [row.split()[1] for row in shown] == ["1/3", "2/3", "3/3"]


def test_one_shot_failing_stops_the_cut(monkeypatch, tmp_path):
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "secret")
    paths = []
    for name in ("a.mp4", "b.mp4"):
        path = tmp_path / name
        path.write_bytes(b"x")
        paths.append(str(path))
    monkeypatch.setattr(cli, "probe", lambda path, need_audio=True: {"path": path, "duration": 10.0})

    def words_for(work, index, stem, *rest):
        if stem == "b":
            raise SystemExit("STT HTTP 500: down")
        return []

    monkeypatch.setattr(cli, "_words_for_clip", words_for)
    monkeypatch.setattr(cli, "_silences_for_clip", lambda *a: [])
    with pytest.raises(SystemExit, match="STT HTTP 500"):
        cli.run(paths, str(tmp_path / "out"), decide=True)
    assert not os.path.exists(tmp_path / "out" / "cuts.json")


def test_a_recording_ffmpeg_cannot_read_is_not_taken_for_one_with_no_pauses(tmp_path):
    broken = tmp_path / "broken.flac"
    broken.write_bytes(b"not audio")
    with pytest.raises(SystemExit, match="Could not read the sound"):
        silences(str(broken), 10.0)
