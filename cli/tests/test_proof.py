"""The cut read back: what the proof sees, what it may change, and what it may not."""

import json

import pytest

from botcut import proof as proofing
from botcut.proof import apply_changes, changed, no_changes, proof, proof_message, read_proof


def _line(uid, text, keep=True, length=2.0, reason="ok", gap=0.2, cuts=None):
    start = uid * (2.0 + gap)
    row = {
        "id": uid,
        "clip": 0,
        "start": start,
        "end": start + length,
        "text": text,
        "keep": keep,
        "reason": reason,
    }
    if cuts is not None:
        row["cuts"] = cuts
    return row


def _cut(first, through, taken):
    return {"from": first, "through": through, "start": 0.0, "end": 0.3, "reason": "filler", "cut": taken}


LINES = [
    _line(0, "Welcome to the shop."),
    _line(1, "We um built it we built it by hand.", cuts=[_cut(1, 1, True), _cut(2, 4, False)]),
    _line(2, "Let me redo that.", keep=False, reason="unique?"),
    _line(3, "And that is the whole story."),
    _line(4, "Thanks for watching."),
    _line(5, "How we built it", reason="card"),
]
# Lines 0 and 1 play as one piece. The drop of line 2 makes a join before line 3.
PIECES = [
    {"clip": 0, "start": 0.0, "end": 4.4, "reason": "ok"},
    {"clip": 0, "start": 6.4, "end": 11.0, "reason": "ok"},
]


class _Reply:
    status_code = 200
    text = ""

    def __init__(self, content):
        self._content = content if isinstance(content, str) else json.dumps(content)

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "secret")
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.delenv("BOTCUT_LLM_MODEL", raising=False)
    monkeypatch.delenv("BOTCUT_LLM_EFFORT", raising=False)


def _answer(**fields):
    return {"reply": "It holds.", "drop": [], "restore": [], "cuts": [], "hook": -1, **fields}


def test_the_proof_reads_the_cut_as_it_plays():
    plan = {
        "beats": [{"title": "The shop", "first": 0, "last": 4}],
        "retakes": [],
        "hook": 3,
        "target_seconds": 5,
    }
    flags = [{"kind": "leans", "ids": [3], "text": 'Line 3 opens on "and" and the line before it is dropped.'}]
    text = proof_message(LINES, PIECES, intent="A shop tour", outline=plan, flags=flags)
    rows = text.splitlines()
    assert rows[0] == "The movie is: A shop tour"
    assert rows[1] == "The cut runs 9s. About 5s was asked for."
    assert "1. The shop (lines 0-4)" in rows
    assert "On the first read, line 3 looked like one the movie could open on." in rows
    body = rows[rows.index("[0] 2.0s Welcome to the shop.") :]
    assert body[:6] == [
        "[0] 2.0s Welcome to the shop.",
        '[1] 2.0s We um built it we built it by hand. {cuts: 0="um" taken, 1="built it we" left in}',
        "[2] dropped: Let me redo that.",
        "— cut —",
        "[3] 2.0s And that is the whole story.",
        "[4] 2.0s Thanks for watching.",
    ]
    # A card is not a line anyone said, so it is not in what is read.
    assert "How we built it" not in text
    assert rows[-1] == '- Line 3 opens on "and" and the line before it is dropped.'
    plain = proof_message(LINES, PIECES)
    assert plain.splitlines()[0] == "The cut runs 9s. No length was asked for."
    assert "plain check" not in plain and "beats" not in plain


def test_only_changes_that_point_at_real_lines_in_the_right_state_are_read():
    changes = read_proof(
        _answer(
            reply="  A shop tour.\n I put the redo back. ",
            drop=[{"id": 4, "reason": "a   long   goodbye"}, {"id": 2, "reason": "already gone"}, {"id": 99, "reason": "x"}],
            restore=[{"id": 2, "reason": "needed"}, {"id": 0, "reason": "already kept"}, {"id": 5, "reason": "a card"}],
            cuts=[{"id": 1, "take": [1, 0, 1]}, {"id": 0, "take": [0]}, {"id": 4, "take": []}],
            hook=3,
        ),
        LINES,
    )
    assert changes == {
        "reply": "A shop tour. I put the redo back.",
        "drop": [{"id": 4, "reason": "a long goodbye"}],
        "restore": [{"id": 2, "reason": "needed"}],
        "cuts": [{"id": 1, "take": [0, 1]}],
        "hook": 3,
        "close": [],
    }
    assert changed(changes)
    assert not changed(no_changes())
    with pytest.raises(ValueError):
        read_proof("no", LINES)


def test_a_cut_number_that_was_never_offered_changes_nothing():
    changes = read_proof(_answer(cuts=[{"id": 1, "take": [0, 2]}]), LINES)
    assert changes["cuts"] == []


def test_a_proof_may_not_gut_the_movie_unless_a_length_was_asked_for():
    most = [{"id": uid, "reason": "tighter"} for uid in (0, 1, 3)]
    # Three of four kept lines, with no length asked for: that is a second cut, not a proof.
    assert read_proof(_answer(drop=most), LINES)["drop"] == []
    # One of four is a fix.
    assert read_proof(_answer(drop=most[:1]), LINES)["drop"] == most[:1]
    # With a length to hit, taking a lot out is the job.
    assert read_proof(_answer(drop=most), LINES, target=2.0)["drop"] == most
    # It can never take out every line.
    everything = most + [{"id": 4, "reason": "tighter"}]
    assert read_proof(_answer(drop=everything), LINES, target=2.0)["drop"] == []


def test_a_hook_has_to_be_a_line_that_is_in_the_movie():
    assert read_proof(_answer(hook=2), LINES)["hook"] == -1
    assert read_proof(_answer(hook=2, restore=[{"id": 2, "reason": "needed"}]), LINES)["hook"] == 2
    assert read_proof(_answer(hook=4, drop=[{"id": 4, "reason": "goodbye"}]), LINES)["hook"] == -1
    assert read_proof(_answer(hook=5), LINES)["hook"] == -1
    assert read_proof(_answer(hook=True), LINES)["hook"] == -1


def test_changes_land_on_the_lines_named_and_nothing_else_moves():
    changes = {
        "reply": "",
        "drop": [{"id": 4, "reason": "long goodbye"}],
        "restore": [{"id": 2, "reason": ""}],
        "cuts": [{"id": 1, "take": [1]}],
        "hook": -1,
    }
    after = apply_changes(LINES, changes)
    assert [(line["id"], line["keep"], line["reason"]) for line in after] == [
        (0, True, "ok"),
        (1, True, "ok"),
        (2, True, "restored"),
        (3, True, "ok"),
        (4, False, "long goodbye"),
        (5, True, "card"),
    ]
    assert [cut["cut"] for cut in after[1]["cuts"]] == [False, True]
    assert after[0] == LINES[0]
    # The lines handed in are not written on.
    assert LINES[4]["keep"] is True and LINES[1]["cuts"][0]["cut"] is True


def test_the_proof_request_thinks_harder_and_is_shown_what_the_check_found(live, monkeypatch):
    seen = {}

    def post(url, headers=None, json=None, timeout=None):
        seen["body"] = json
        return _Reply(_answer(reply="A shop tour. I put the redo back.", restore=[{"id": 2, "reason": "needed"}]))

    monkeypatch.setattr("botcut.net.requests.post", post)
    changes = proof(LINES, PIECES, intent="A shop tour")
    assert changes["restore"] == [{"id": 2, "reason": "needed"}]
    body = seen["body"]
    assert body["reasoning_effort"] == "high"
    assert body["response_format"]["json_schema"]["name"] == "proof"
    assert body["messages"][0]["content"] == proofing.PROOF_SYSTEM
    assert 'Line 3 opens on "and" and the line before it is dropped.' in body["messages"][1]["content"]


def test_a_cut_stands_as_made_when_the_proof_cannot_be_had(live, monkeypatch, capsys):
    monkeypatch.setattr("botcut.net.requests.post", lambda *_a, **_k: _Reply("not json"))
    assert proof(LINES, PIECES) == no_changes()
    assert "Kept the cut as first made" in capsys.readouterr().out
    monkeypatch.delenv("XAI_API_KEY")
    with pytest.raises(SystemExit, match="XAI_API_KEY is not set"):
        proof(LINES, PIECES)


def test_a_few_lines_and_an_offline_run_are_not_proofed(live, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("no request was expected")

    monkeypatch.setattr("botcut.net.requests.post", boom)
    assert proof(LINES[:3], PIECES) == no_changes()
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    assert proof(LINES, PIECES) == no_changes()


def test_a_cut_reads_the_shoot_chooses_then_reads_itself_back(live, monkeypatch, tmp_path, capsys):
    # The two-request way, as a shoot too long for one request is cut.
    monkeypatch.setenv("BOTCUT_FOLD", "0")
    from botcut import cli

    shot = tmp_path / "talk.mp4"
    shot.write_bytes(b"x")
    said = ["Hello there.", "We make chairs.", "We make chairs.", "By hand.", "And they last.", "Come by.", "Goodbye now."]
    words = []
    for index, text in enumerate(said):
        for offset, word in enumerate(text.split()):
            start = index * 5.0 + offset * 0.4
            words.append({"text": word, "start": start, "end": start + 0.3})
    monkeypatch.setattr(cli, "probe", lambda path, need_audio=True: {"path": path, "duration": 40.0})
    monkeypatch.setattr(cli, "_words_for_clip", lambda *a: words)
    monkeypatch.setattr(cli, "_silences_for_clip", lambda *a: [])
    monkeypatch.setattr(cli, "_attach_stills", lambda *a: None)
    monkeypatch.setattr(cli, "find_faces", lambda *a: None)
    asked = []
    answers = {
        "outline": {
            "beats": [{"title": "Chairs", "first": 0, "last": 6}],
            "retakes": [{"ids": [1, 2]}],
            "hook": -1,
            "target_seconds": 0,
        },
        # The first pass drops the wrong take's twin, and a line the story needs.
        "keep": {"keep": [{"id": uid, "reason": "ok", "cuts": []} for uid in (0, 1, 2, 4, 5, 6)]},
        "proof": _answer(
            reply="A short word about the chairs. I took out the second take and put a line back.",
            drop=[{"id": 2, "reason": "said twice"}],
            restore=[{"id": 3, "reason": "sets up next"}],
        ),
    }

    def post(url, headers=None, json=None, timeout=None):
        name = json["response_format"]["json_schema"]["name"]
        asked.append((name, json["messages"][1]["content"]))
        return _Reply(answers[name])

    monkeypatch.setattr("botcut.net.requests.post", post)
    cli.run([str(shot)], str(tmp_path / "out"), intent="A word about our chairs", decide=True)
    assert [name for name, _ in asked] == ["outline", "keep", "proof"]
    # The keep request was told which lines are the same thing.
    assert "[1] We make chairs. / [2] We make chairs." in asked[1][1]
    # The proof was shown the first pass's cut, with what the plain check found in it.
    assert "[3] dropped: By hand." in asked[2][1]
    assert "- Lines 1 and 2 say the same thing." in asked[2][1]
    assert '- Line 4 opens on "and" and the line before it is dropped.' in asked[2][1]

    doc = json.loads((tmp_path / "out" / "cuts.json").read_text())
    assert [(line["id"], line["keep"], line["reason"]) for line in doc["lines"]] == [
        (0, True, "ok"),
        (1, True, "ok"),
        (2, False, "said twice"),
        (3, True, "sets up next"),
        (4, True, "ok"),
        (5, True, "ok"),
        (6, True, "ok"),
    ]
    assert [row["id"] for row in doc["dropped"]] == [2]
    # The pieces were built again from the proofed lines: nothing of line 2 is in them.
    assert not any(seg["start"] < 11.0 and seg["end"] > 10.0 for seg in doc["segments"])
    assert any(seg["start"] <= 15.0 < seg["end"] for seg in doc["segments"])
    assert doc["cut_reply"].startswith("A short word about the chairs.")
    assert doc["outline"] == {
        "beats": [{"title": "Chairs", "first": 0, "last": 6}],
        "retakes": [[1, 2]],
        "target_seconds": 0,
    }
    out = capsys.readouterr().out.splitlines()
    assert out.index("Choosing takes") < out.index("Checking the cut")
    assert "6 kept, 1 dropped" in out


def test_lines_to_show_close_are_kept_lines_never_neighbours_and_only_a_few():
    lines = [_line(uid, f"line {uid}", keep=uid != 3) for uid in range(13)]
    # Twelve lines play, so three at most. 3 is dropped, 99 is nowhere, 6 plays right after 5,
    # and 4 plays right after 2 once 3 is gone.
    changes = read_proof(_answer(close=[5, 3, 99, 6, 5, 2, 4, 9, 11]), lines)
    assert changes["close"] == [2, 5, 9]
    # A line the proof itself takes out is not shown close, and one it puts back can be.
    changes = read_proof(
        _answer(close=[5, 3], drop=[{"id": 5, "reason": "said twice"}], restore=[{"id": 3, "reason": "needed"}]),
        lines,
    )
    assert changes["close"] == [3]
    # Too few lines for one in four.
    assert read_proof(_answer(close=[1]), lines[:3])["close"] == []
    # An answer recorded before this was asked for has none.
    old = _answer()
    old.pop("close", None)
    assert read_proof(old, lines)["close"] == []
    assert no_changes()["close"] == []


def test_a_shoot_that_fits_in_one_request_is_read_and_cut_in_it(live, monkeypatch, tmp_path):
    from botcut import cli

    shot = tmp_path / "talk.mp4"
    shot.write_bytes(b"x")
    said = ["Hello there.", "We make chairs.", "We make chairs.", "By hand.", "And they last.", "Come by.", "Goodbye now."]
    words = []
    for index, text in enumerate(said):
        for offset, word in enumerate(text.split()):
            start = index * 5.0 + offset * 0.4
            words.append({"text": word, "start": start, "end": start + 0.3})
    monkeypatch.setattr(cli, "probe", lambda path, need_audio=True: {"path": path, "duration": 40.0})
    monkeypatch.setattr(cli, "_words_for_clip", lambda *a: words)
    monkeypatch.setattr(cli, "_silences_for_clip", lambda *a: [])
    monkeypatch.setattr(cli, "_attach_stills", lambda *a: None)
    monkeypatch.setattr(cli, "find_faces", lambda *a: None)
    asked = []
    answers = {
        "cut": {
            "beats": [{"title": "Chairs", "first": 0, "last": 6}],
            "retakes": [{"ids": [1, 2]}],
            "hook": -1,
            "target_seconds": 30,
            "keep": [
                {"id": uid, "reason": "ok", "cuts": [], "trim": ["there"] if uid == 0 else []}
                for uid in (0, 2, 3, 4, 5, 6)
            ],
        },
        "proof": _answer(reply="It holds as cut."),
    }

    def post(url, headers=None, json=None, timeout=None):
        name = json["response_format"]["json_schema"]["name"]
        asked.append((name, json))
        return _Reply(answers[name])

    monkeypatch.setattr("botcut.net.requests.post", post)
    cli.run([str(shot)], str(tmp_path / "out"), intent="A thirty second word about our chairs", decide=True)
    # One request reads the shoot and chooses. Then the proof, which is the one given time to think.
    assert [name for name, _ in asked] == ["cut", "proof"]
    assert asked[0][1]["reasoning_effort"] == "low"
    assert asked[1][1]["reasoning_effort"] == "high"
    assert "Read all of it first" in asked[0][1]["messages"][0]["content"]
    doc = json.loads((tmp_path / "out" / "cuts.json").read_text())
    assert [line["id"] for line in doc["lines"] if line["keep"]] == [0, 2, 3, 4, 5, 6]
    assert doc["outline"] == {
        "beats": [{"title": "Chairs", "first": 0, "last": 6}],
        "retakes": [[1, 2]],
        "target_seconds": 30,
    }
    # The length it read out of the sentence is what the proof holds the cut to.
    assert "About 30s was asked for." in asked[1][1]["messages"][1]["content"]
    took = json.loads((tmp_path / "out" / "work" / "seconds.json").read_text())
    assert "outline" not in took and "choose" in took
