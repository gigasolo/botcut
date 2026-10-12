import json
import os
import socket
import subprocess
import tempfile

import pytest

from botcut.captions import load_words_by_clip
from botcut.card import IMAGE_MODEL, IMAGE_URL, card_sentence, make_card
from botcut.cli import main, run
from botcut.media import probe


def _boom(*_args, **_kwargs):
    raise AssertionError("socket")


def _clip(path, seconds):
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=f=440",
            "-t",
            str(seconds),
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]


def _jpeg(path):
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90",
            "-frames:v",
            "1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-400:]
    return path.read_bytes()


def _cards(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    return tmp_path / "xdg" / "botcut" / "cards"


def _watch_stills(monkeypatch):
    made = []
    real = tempfile.mkstemp

    def wrapped(*args, **kwargs):
        pair = real(*args, **kwargs)
        made.append(pair[1])
        return pair

    monkeypatch.setattr("botcut.card.tempfile.mkstemp", wrapped)
    return made


def _no_partial(dest, stills):
    assert not (dest.parent / f".{dest.name}.part").exists()
    assert not dest.with_name(dest.name + ".part").exists()
    assert not dest.with_name(dest.name + ".still.jpg").exists()
    assert all(not os.path.exists(path) for path in stills)


def test_fake_card_is_decodable_without_a_socket(monkeypatch, tmp_path):
    cards = _cards(monkeypatch, tmp_path)
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.setenv("XAI_API_KEY", "supersecret")
    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr("botcut.net.requests.post", _boom)
    monkeypatch.setattr("botcut.card.requests.get", _boom)

    dest = cards / "botcut-card-1-open.mp4"
    argv = ["card", "--out", str(dest), "--", "A quiet ride"]
    assert "supersecret" not in " ".join(argv)
    main(argv)
    assert dest.is_file()
    info = probe(str(dest))
    assert info["duration"] > 0
    assert info["width"] > 0
    assert info["audio_codec"]
    assert card_sentence(str(dest), "") == "A quiet ride"
    assert b"supersecret" not in dest.read_bytes()
    _no_partial(dest, [])


def test_card_refuses_without_a_key(monkeypatch, tmp_path):
    cards = _cards(monkeypatch, tmp_path)
    called = {"post": False}

    def post(*_args, **_kwargs):
        called["post"] = True
        raise AssertionError("network")

    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr("botcut.net.requests.post", post)
    monkeypatch.setattr("botcut.card.requests.get", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    dest = cards / "botcut-card-1-open.mp4"
    with pytest.raises(SystemExit, match="XAI_API_KEY is not set"):
        main(["card", "--out", str(dest), "--", "A quiet ride"])
    assert called["post"] is False
    assert not dest.exists()


def test_card_hides_the_key_and_downloads_the_returned_url(monkeypatch, tmp_path):
    cards = _cards(monkeypatch, tmp_path)
    stills = _watch_stills(monkeypatch)
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "supersecret")
    jpeg = _jpeg(tmp_path / "still.jpg")
    seen = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": [{"url": "https://imgen.example/one.jpeg"}]}

    def post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["body"] = json
        seen["auth"] = headers["Authorization"]
        return Response()

    def get(url, timeout=None, headers=None, **kwargs):
        seen["get_url"] = url
        seen["get_headers"] = headers
        seen["get_kwargs"] = kwargs

        class Download:
            status_code = 200
            content = jpeg

        return Download()

    monkeypatch.setattr("botcut.net.requests.post", post)
    monkeypatch.setattr("botcut.card.requests.get", get)
    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)

    dest = cards / "botcut-card-9-close.mp4"
    argv = ["card", "--out", str(dest), "--", "A quiet ride"]
    assert "supersecret" not in " ".join(argv)
    main(argv)
    assert seen["url"] == IMAGE_URL
    assert seen["auth"] == "Bearer supersecret"
    assert seen["body"]["model"] == IMAGE_MODEL
    assert seen["body"]["prompt"] == "A quiet ride"
    assert seen["body"]["n"] == 1
    assert seen["body"]["aspect_ratio"] == "16:9"
    assert seen["body"]["response_format"] == "url"
    assert "supersecret" not in json.dumps(seen["body"])
    assert seen["get_url"] == "https://imgen.example/one.jpeg"
    assert seen["get_headers"] is None
    assert seen["get_kwargs"].get("allow_redirects") is False
    assert "supersecret" not in json.dumps(seen["get_kwargs"])
    info = probe(str(dest))
    assert info["duration"] == pytest.approx(3.0, abs=0.15)
    assert info["audio_codec"]
    assert card_sentence(str(dest), "") == "A quiet ride"
    assert b"supersecret" not in dest.read_bytes()
    _no_partial(dest, stills)
    assert stills


def test_missing_ffmpeg_leaves_no_card(monkeypatch, tmp_path):
    cards = _cards(monkeypatch, tmp_path)
    stills = _watch_stills(monkeypatch)
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "supersecret")

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": [{"url": "https://imgen.example/one.jpeg"}]}

    def post(url, headers=None, json=None, timeout=None):
        return Response()

    def get(url, timeout=None, **kwargs):
        class Download:
            status_code = 200
            content = b"not a picture"

        return Download()

    def run(cmd, **kwargs):
        if cmd and cmd[0] == "ffmpeg":
            raise FileNotFoundError(cmd[0])
        raise AssertionError(cmd)

    monkeypatch.setattr("botcut.net.requests.post", post)
    monkeypatch.setattr("botcut.card.requests.get", get)
    monkeypatch.setattr("botcut.card.subprocess.run", run)
    dest = cards / "botcut-card-1-open.mp4"
    with pytest.raises(SystemExit, match="ffmpeg was not found"):
        make_card("A quiet ride", str(dest))
    assert not dest.exists()
    _no_partial(dest, stills)
    assert "supersecret" not in " ".join(["card", "--out", str(dest), "--", "A quiet ride"])


def test_plain_url_is_not_downloaded(monkeypatch, tmp_path):
    cards = _cards(monkeypatch, tmp_path)
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "supersecret")

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": [{"url": "http://127.0.0.1/secret.jpeg"}]}

    def post(url, headers=None, json=None, timeout=None):
        return Response()

    def get(*_args, **_kwargs):
        raise AssertionError("download")

    monkeypatch.setattr("botcut.net.requests.post", post)
    monkeypatch.setattr("botcut.card.requests.get", get)
    dest = cards / "botcut-card-1-open.mp4"
    with pytest.raises(SystemExit, match="no picture"):
        make_card("A quiet ride", str(dest))
    assert not dest.exists()
    _no_partial(dest, [])


def test_https_redirect_is_followed_without_the_key(monkeypatch, tmp_path):
    cards = _cards(monkeypatch, tmp_path)
    stills = _watch_stills(monkeypatch)
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "supersecret")
    jpeg = _jpeg(tmp_path / "still.jpg")
    seen = []

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": [{"url": "https://imgen.example/start"}]}

    def post(url, headers=None, json=None, timeout=None):
        return Response()

    def get(url, timeout=None, headers=None, **kwargs):
        seen.append((url, headers, kwargs))
        if url == "https://imgen.example/start":

            class Hop:
                status_code = 302
                headers = {"Location": "https://cdn.example/one.jpeg"}
                content = b""

                def close(self):
                    return None

            return Hop()

        class Download:
            status_code = 200
            content = jpeg
            headers = {}

            def close(self):
                return None

        return Download()

    monkeypatch.setattr("botcut.net.requests.post", post)
    monkeypatch.setattr("botcut.card.requests.get", get)
    dest = cards / "botcut-card-redirect-open.mp4"
    make_card("A quiet ride", str(dest))
    assert [row[0] for row in seen] == [
        "https://imgen.example/start",
        "https://cdn.example/one.jpeg",
    ]
    assert all(row[1] is None for row in seen)
    assert all(row[2].get("allow_redirects") is False for row in seen)
    assert all("supersecret" not in json.dumps(row[2]) for row in seen)
    assert dest.is_file()
    _no_partial(dest, stills)


def test_http_redirect_is_not_downloaded(monkeypatch, tmp_path):
    cards = _cards(monkeypatch, tmp_path)
    stills = _watch_stills(monkeypatch)
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "supersecret")
    fetched = []

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": [{"url": "https://imgen.example/start"}]}

    def post(url, headers=None, json=None, timeout=None):
        return Response()

    def get(url, timeout=None, headers=None, **kwargs):
        fetched.append(url)
        assert headers is None
        assert kwargs.get("allow_redirects") is False

        class Hop:
            status_code = 302
            headers = {"Location": "http://127.0.0.1/secret.jpeg"}
            content = b"nope"

            def close(self):
                return None

        return Hop()

    monkeypatch.setattr("botcut.net.requests.post", post)
    monkeypatch.setattr("botcut.card.requests.get", get)
    dest = cards / "botcut-card-redirect-close.mp4"
    with pytest.raises(SystemExit, match="Could not download the card"):
        make_card("A quiet ride", str(dest))
    assert fetched == ["https://imgen.example/start"]
    assert not dest.exists()
    _no_partial(dest, stills)


def test_card_refuses_a_path_outside_the_card_directory(monkeypatch, tmp_path):
    _cards(monkeypatch, tmp_path)
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    dest = tmp_path / "botcut-card-sec.mp4"
    with pytest.raises(SystemExit, match="No card file"):
        main(["card", "--out", str(dest), "--", "--help"])
    assert not dest.exists()


def test_card_directory_symlink_is_refused(monkeypatch, tmp_path):
    real = tmp_path / "elsewhere"
    real.mkdir()
    link_parent = tmp_path / "xdg" / "botcut"
    link_parent.mkdir(parents=True)
    (link_parent / "cards").symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    dest = link_parent / "cards" / "botcut-card-1-open.mp4"
    with pytest.raises(SystemExit, match="No card directory"):
        make_card("Hi", str(dest))
    assert not (real / "botcut-card-1-open.mp4").exists()


def test_partial_symlink_is_not_followed(monkeypatch, tmp_path):
    cards = _cards(monkeypatch, tmp_path)
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    cards.mkdir(parents=True, mode=0o700)
    victim = tmp_path / "victim"
    victim.write_text("keep")
    dest = cards / "botcut-card-1-open.mp4"
    planted = cards / f".{dest.name}.part"
    planted.symlink_to(victim)
    with pytest.raises(SystemExit, match="Could not make the card"):
        make_card("A quiet ride", str(dest))
    assert victim.read_text() == "keep"
    assert not dest.exists()
    assert planted.is_symlink()


def test_help_sentence_is_positional(monkeypatch, tmp_path, capsys):
    cards = _cards(monkeypatch, tmp_path)
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    dest = cards / "botcut-card-help.mp4"
    with pytest.raises(SystemExit) as caught:
        main(["card", "--out", str(dest), "--help"])
    assert caught.value.code in (0, None)
    assert not dest.exists()
    assert "usage:" in capsys.readouterr().out

    main(["card", "--out", str(dest), "--", "--help"])
    assert dest.is_file()
    assert card_sentence(str(dest), "") == "--help"


def test_decide_keeps_a_card_without_a_transcript(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr("botcut.net.requests.post", _boom)
    monkeypatch.setattr("botcut.card.requests.get", _boom)

    cards = _cards(monkeypatch, tmp_path)
    open_card = cards / "botcut-card-1-open.mp4"
    close_card = cards / "botcut-card-2-close.mp4"
    talk = tmp_path / "talk.mp4"
    make_card("Hello there", str(open_card))
    make_card("See you", str(close_card))
    _clip(talk, 3)

    from botcut.pick import pick as real_pick
    from botcut.stt import transcribe_fake

    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return transcribe_fake()

    seen = {}

    def spy(utts, intent=""):
        seen["utts"] = list(utts)
        seen["intent"] = intent
        return real_pick(utts, intent)

    monkeypatch.setattr("botcut.cli.transcribe_fake", counting)
    monkeypatch.setattr("botcut.cli.pick", spy)

    out = tmp_path / "out"
    run(
        [str(open_card), str(talk), str(close_card)],
        str(out),
        decide=True,
        intent="A quiet ride",
    )
    assert calls["n"] == 1
    assert seen["intent"] == "A quiet ride"
    assert seen["utts"]
    assert {utt["clip"] for utt in seen["utts"]} == {1}
    assert all(utt["text"] not in ("Hello there", "See you") for utt in seen["utts"])

    doc = json.loads((out / "cuts.json").read_text())
    cards = [line for line in doc["lines"] if line["reason"] == "card"]
    assert [line["clip"] for line in cards] == [0, 2]
    assert all(line["keep"] is True for line in cards)
    assert cards[0]["text"] == "Hello there"
    assert cards[1]["text"] == "See you"
    assert cards[0]["start"] == 0
    assert cards[0]["end"] == pytest.approx(doc["clips"][0]["duration"])
    assert cards[1]["start"] == 0
    assert cards[1]["end"] == pytest.approx(doc["clips"][2]["duration"])
    speech = [line for line in doc["lines"] if line["clip"] == 1]
    assert speech
    assert all(line["reason"] != "card" for line in speech)
    segs = [seg for seg in doc["segments"] if seg["reason"] == "card"]
    assert [seg["clip"] for seg in segs] == [0, 2]
    assert segs[0]["end"] == pytest.approx(doc["clips"][0]["duration"])
    assert segs[1]["end"] == pytest.approx(doc["clips"][2]["duration"])
    assert doc["segments"][0]["clip"] == 0
    assert doc["segments"][-1]["clip"] == 2
    names = [path.name for path in (out / "work").iterdir()]
    assert not any(name.startswith("0-botcut-card") or name.startswith("2-botcut-card") for name in names)
    assert not (out / "rough_cut.mp4").exists()

    def no_pick(*_args, **_kwargs):
        raise AssertionError("keep model")

    def no_stt():
        raise AssertionError("stt")

    monkeypatch.setattr("botcut.cli.pick", no_pick)
    monkeypatch.setattr("botcut.cli.transcribe_fake", no_stt)
    alone = tmp_path / "alone"
    run([str(open_card)], str(alone), decide=True, intent="A quiet ride")
    only = json.loads((alone / "cuts.json").read_text())
    assert len(only["lines"]) == 1
    assert only["lines"][0]["reason"] == "card"
    assert only["lines"][0]["keep"] is True
    assert only["lines"][0]["text"] == "Hello there"
    assert only["lines"][0]["start"] == 0
    assert only["lines"][0]["end"] == pytest.approx(only["clips"][0]["duration"])
    assert only["segments"] == [
        {
            "clip": 0,
            "start": 0.0,
            "end": only["clips"][0]["duration"],
            "reason": "card",
        }
    ]


def test_captions_skip_a_card_with_no_transcript(tmp_path):
    doc = {
        "stt": "fake",
        "clips": [{"index": 0, "path": str(tmp_path / "botcut-card-1-open.mp4"), "duration": 3}],
    }
    assert load_words_by_clip(doc, str(tmp_path)) == [[]]
