"""Names the transcript should lean toward, and how long each stage of a cut took."""

import json

import pytest

from botcut import cli
from botcut.stt import key_terms, names_in, names_path, terms_mark, transcribe_xai


@pytest.fixture
def config(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def _names(config, text):
    path = config / "botcut" / "names.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_names_in_a_sentence_are_capitals_that_do_not_just_open_it():
    assert names_in("A talk to the team about Telnyx and the MCP work.") == ["Telnyx", "MCP"]
    # A word that opens a sentence is a name only when its shape says so.
    assert names_in("Lynn will be there. VirtualPBX is moving. Nothing else.") == ["VirtualPBX"]
    # Names side by side are one name. The person is not a name.
    assert names_in("What I told Lynn Baker, and why I'm moving us to 3CX in 90 days") == [
        "Lynn Baker",
        "3CX",
    ]
    assert names_in("Keep each moment in order. Drop flubs and true retakes.") == []
    assert names_in("") == []


def test_the_kept_list_comes_first_and_the_sentence_adds_to_it(config):
    assert names_path() == config / "botcut" / "names.txt"
    assert key_terms("About Kazoo") == ["Kazoo"]
    _names(
        config,
        "# people\nTelnyx\n\n  Virtual   PBX  \ntelnyx\n" + "x" * 51 + "\nlower case is fine\n",
    )
    assert key_terms("An update on Kazoo and Telnyx") == [
        "Telnyx",
        "Virtual PBX",
        "lower case is fine",
        "Kazoo",
    ]


def test_no_more_terms_are_sent_than_are_taken(config):
    _names(config, "\n".join(f"Name{i}" for i in range(150)))
    terms = key_terms("About Kazoo")
    assert len(terms) == 100
    assert terms[0] == "Name0" and terms[-1] == "Name99"


def test_terms_ride_before_the_file_and_none_are_sent_without_a_list(monkeypatch, tmp_path):
    flac = tmp_path / "take.flac"
    flac.write_bytes(b"not really flac")
    seen = []

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"duration": 1.0, "words": [{"text": "Telnyx", "start": 0.0, "end": 0.5}]}

    def post(url, headers=None, files=None, timeout=None):
        seen.append([(name, part[1] if part[0] is None else "upload") for name, part in files])
        return Response()

    monkeypatch.setenv("XAI_API_KEY", "secret")
    monkeypatch.setattr("botcut.net.requests.post", post)
    assert transcribe_xai(str(flac), ["Telnyx", "Lynn Baker"])["words"][0]["text"] == "Telnyx"
    assert seen[0][-3:] == [("keyterm", "Telnyx"), ("keyterm", "Lynn Baker"), ("file", "upload")]
    transcribe_xai(str(flac))
    assert [name for name, _ in seen[1]] == ["model", "language", "filler_words", "file"]


def test_another_list_of_names_forgets_what_was_heard(tmp_path):
    assert terms_mark([]) == ""
    plain = cli._stt_label(False, "xai", "small")
    named = cli._stt_label(False, "xai", "small", ["Telnyx"])
    assert plain == "xai:grok-voice-transcribe-2.0"
    assert named.startswith(plain + "+") and len(named) == len(plain) + 7
    assert named != cli._stt_label(False, "xai", "small", ["Telnyx", "Kazoo"])
    assert cli._stt_label(False, "local", "small", ["Telnyx"]).startswith("local:faster-whisper:small+")
    assert cli._stt_label(True, "xai", "small", ["Telnyx"]) == "fake"

    work = tmp_path / "work"
    work.mkdir()
    shot = tmp_path / "talk.mp4"
    shot.write_bytes(b"a take")
    clip = {"path": str(shot)}
    words = work / "0-talk.xai.words.json"
    cli._drop_stale_caches(str(work), 0, clip, named)
    words.write_text("{}")
    cli._drop_stale_caches(str(work), 0, clip, named)
    assert words.exists()
    cli._drop_stale_caches(str(work), 0, clip, plain)
    assert not words.exists()


def test_a_cut_is_transcribed_with_the_names(monkeypatch, tmp_path, config):
    _names(config, "Telnyx\n")
    heard = {}
    work = tmp_path / "work"
    work.mkdir()
    flac = work / "0-talk.flac"
    flac.write_bytes(b"sound")

    def xai(path, terms=()):
        heard["terms"] = list(terms)
        return {"duration": 1.0, "words": []}

    monkeypatch.setattr(cli, "transcribe_xai", xai)
    terms = key_terms("An update for Lynn")
    cli._words_for_clip(str(work), 0, "talk", "xai", str(flac), {"path": "talk.mp4"}, "small", terms)
    assert heard["terms"] == ["Telnyx", "Lynn"]


def test_the_clock_gives_each_stage_what_passed_since_the_last(monkeypatch):
    ticks = iter([10.0, 12.5, 12.5, 80.0, 81.0])
    monkeypatch.setattr(cli.time, "perf_counter", lambda: next(ticks))
    clock = cli._Clock()
    clock.lap("listen")
    clock.lap("stills")
    clock.lap("choose")
    # A stage that runs twice adds up.
    clock.lap("listen")
    assert clock.seconds == {"listen": 3.5, "stills": 0.0, "choose": 67.5}


def test_the_time_is_said_longest_first_without_the_instant_stages():
    line = cli.took_line({"read": 0.3, "listen": 9.2, "choose": 76.0, "render": 285.4, "stills": 28.0})
    assert line == "Took 6m39s: render 4m45s, choose 1m16s, stills 28s, listen 9s."
    assert cli.took_line({"read": 0.2}) == "Took 0s."
    assert cli.took_line({}) == "Took 0s."


def test_a_later_render_adds_to_what_the_cut_took(tmp_path, capsys):
    first = cli._Clock()
    first.seconds = {"listen": 9.0, "choose": 70.0, "render": 200.0}
    cli._took(str(tmp_path), first, fresh=True)
    again = cli._Clock()
    again.seconds = {"read": 0.1, "render": 150.0}
    cli._took(str(tmp_path), again, fresh=False)
    kept = json.loads((tmp_path / "work" / "seconds.json").read_text())
    assert kept == {"listen": 9.0, "choose": 70.0, "render": 150.0, "read": 0.1}
    out = capsys.readouterr().out.splitlines()
    assert out == ["Took 4m39s: render 3m20s, choose 1m10s, listen 9s.", "Took 2m30s: render 2m30s."]
    # A new cut starts the count over.
    cli._took(str(tmp_path), again, fresh=True)
    assert json.loads((tmp_path / "work" / "seconds.json").read_text()) == {"read": 0.1, "render": 150.0}
