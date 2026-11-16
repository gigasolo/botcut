"""Cuts inside a line: fillers and words said twice."""

import json

import pytest

from botcut import cli
from botcut.captions import remap_words
from botcut.pick import cut_words, decision_lines, pick, user_content, utterances, word_cuts
from botcut.revise import parse_revise


def _words(*rows):
    return [{"text": text, "start": start, "end": end} for text, start, end in rows]


SAID = _words(
    ("So", 1.00, 1.20),
    ("um", 1.40, 1.80),
    ("we", 2.00, 2.15),
    ("were", 2.15, 2.40),
    ("we", 2.60, 2.75),
    ("were", 2.75, 3.00),
    ("building", 3.00, 3.50),
    ("this.", 3.50, 3.90),
)


def test_fillers_and_restarts_are_found_and_timed_from_the_words():
    utt = utterances([SAID])[0]
    assert utt["text"] == "So um we were we were building this."
    cuts = utt["cuts"]
    assert [(c["from"], c["through"], c["reason"]) for c in cuts] == [(1, 1, "filler"), (2, 3, "said twice")]
    # The cut leaves a breath on each side: 40 ms after "So" and 40 ms before "we".
    assert (cuts[0]["start"], cuts[0]["end"]) == (1.24, 1.96)
    # The first "we were" goes, from a breath after the word before it to just before the second.
    assert (cuts[1]["start"], cuts[1]["end"]) == (1.84, 2.56)
    assert all(cut["cut"] is False for cut in cuts)


def test_nothing_is_offered_where_a_cut_would_be_wrong():
    # A line that is only a filler is dropped as a line.
    assert word_cuts(utterances([_words(("Um", 0.0, 0.4))])[0]) == []
    # A filler too short to be worth a jump is left.
    quick = utterances([_words(("I", 0.0, 0.2), ("uh", 0.2, 0.28), ("know", 0.28, 0.6))])[0]
    assert quick["cuts"] == []
    # Ordinary speech has nothing to cut.
    plain = utterances([_words(("Hello", 0.0, 0.4), ("there", 0.5, 0.9))])[0]
    assert plain["cuts"] == []
    # A word with a space in it would not line up with the text on screen.
    odd = {"start": 0.0, "end": 1.0, "text": "New York um yes",
           "words": _words(("New York", 0.0, 0.4), ("um", 0.4, 0.8), ("yes", 0.8, 1.0))}
    assert word_cuts(odd) == []


def test_the_model_is_offered_cuts_by_number_and_never_times(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "secret")
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    utts = utterances([SAID])
    text = user_content(utts)
    assert '{cuts: 0="um", 1="we were"}' in text
    assert "numbered from 0" in text
    seen = {}

    class Reply:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(
                {"keep": [{"id": 0, "reason": "the point", "cuts": [0, 1, 7]}]})}}]}

    def post(url, headers=None, json=None, timeout=None):
        seen["schema"] = json["response_format"]["json_schema"]["schema"]
        return Reply()

    monkeypatch.setattr("botcut.net.requests.post", post)
    chosen = pick(utts)
    assert chosen == [{"id": 0, "reason": "the point", "cuts": [0, 1, 7]}]
    item = seen["schema"]["properties"]["keep"]["items"]
    assert item["required"] == ["id", "reason", "cuts"]
    assert item["properties"]["cuts"] == {"type": "array", "items": {"type": "integer"}}
    # A number that was never offered is ignored. Both real cuts are marked taken.
    line = decision_lines(utts, chosen)[0]
    assert [cut["cut"] for cut in line["cuts"]] == [True, True]
    assert line["cuts"][0]["reason"] == "filler"


def test_taken_cuts_come_out_of_the_rendered_range_and_the_captions():
    utts = utterances([SAID])
    lines = decision_lines(utts, [{"id": 0, "reason": "ok", "cuts": [0]}])
    segs = [{"clip": 0, "start": 0.75, "end": 4.3, "reason": "ok"}]
    cut = cut_words(segs, lines)
    assert [(s["start"], s["end"]) for s in cut] == [(0.75, 1.24), (1.96, 4.3)]
    assert all(s["reason"] == "ok" for s in cut)
    said = [word["text"] for word in remap_words(cut, [SAID])]
    assert said == ["So", "we", "were", "we", "were", "building", "this."]

    # A cut left in, a dropped line, and a line with no cuts all leave the range whole.
    assert cut_words(segs, decision_lines(utts, [{"id": 0, "reason": "ok"}])) == segs
    dropped = decision_lines(utts, [])
    dropped[0]["cuts"][0]["cut"] = True
    assert cut_words(segs, dropped) == segs


def test_a_saved_plan_renders_with_its_cuts_and_restoring_one_brings_the_words_back():
    utts = utterances([SAID])
    lines = decision_lines(utts, [{"id": 0, "reason": "ok", "cuts": [0, 1]}])
    segs = cli._segments_for_lines(lines, [10.0], [[]], True, 0.8)
    # Two cuts that touch come out as one stretch.
    assert [(round(s["start"], 2), round(s["end"], 2)) for s in segs] == [(0.75, 1.24), (2.56, 4.3)]
    # The window flips one back on: its words are in the next render.
    lines[0]["cuts"][1]["cut"] = False
    segs = cli._segments_for_lines(lines, [10.0], [[]], True, 0.8)
    assert [(round(s["start"], 2), round(s["end"], 2)) for s in segs] == [(0.75, 1.24), (1.96, 4.3)]


def test_the_chat_can_take_every_filler_out_or_leave_them_all_in(tmp_path):
    from botcut.revise import _land

    utts = utterances([SAID])
    lines = decision_lines(utts, [{"id": 0, "reason": "ok", "cuts": [0]}])
    doc = {"clips": [{"index": 0, "path": "/tmp/a.mp4", "duration": 10.0}], "lines": lines, "segments": []}
    cuts_path = tmp_path / "cuts.json"
    base = {"reply": "Done.", "intent": "A talk", "pace": "open", "dip": True,
            "keep": [{"id": 0, "reason": "ok"}], "deliver": "none"}

    _land(str(cuts_path), doc, doc["lines"], parse_revise({**base, "fillers": "keep"}))
    assert [cut["cut"] for cut in json.loads(cuts_path.read_text())["lines"][0]["cuts"]] == [False, False]
    _land(str(cuts_path), doc, doc["lines"], parse_revise({**base, "fillers": "cut"}))
    assert [cut["cut"] for cut in json.loads(cuts_path.read_text())["lines"][0]["cuts"]] == [True, True]
    # "same", and a proposal saved before this existed, change nothing.
    _land(str(cuts_path), doc, doc["lines"], parse_revise(base))
    assert [cut["cut"] for cut in json.loads(cuts_path.read_text())["lines"][0]["cuts"]] == [True, True]
    with pytest.raises(SystemExit, match="not a revise"):
        parse_revise({**base, "fillers": "some"})
