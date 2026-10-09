import pytest

from botcut.pick import (
    DEFAULT_INTENT,
    chat_fields,
    decision_lines,
    dropped_utterances,
    model_name,
    near_duplicate,
    pick,
    segments,
    system_prompt,
    unique_warnings,
    unknown_warnings,
    utterances,
)


def test_utterance_gap_split():
    words = [
        {"text": "hello", "start": 0.0, "end": 0.4},
        {"text": "there", "start": 0.9, "end": 1.2},
        {"text": "friend", "start": 1.72, "end": 2.1},
    ]
    # 0.9 - 0.4 == 0.5 stays together. 1.72 - 1.2 == 0.52 starts a new utterance.
    utts = utterances([words])
    assert [u["id"] for u in utts] == [0, 1]
    assert utts[0]["text"] == "hello there"
    assert utts[0]["start"] == 0.0
    assert utts[0]["end"] == 1.2
    assert utts[1]["text"] == "friend"
    assert utts[1]["clip"] == 0

    both = utterances([words[:1], [{"text": "next", "start": 0.0, "end": 0.2}]])
    assert [(u["id"], u["clip"]) for u in both] == [(0, 0), (1, 1)]


def test_segment_merges_on_unpadded_gap_then_pads():
    utts = [
        {"id": 1, "clip": 0, "start": 1.0, "end": 2.0, "text": "first take"},
        {"id": 2, "clip": 0, "start": 2.6, "end": 3.5, "text": "second take"},
        {"id": 3, "clip": 1, "start": 0.2, "end": 0.8, "text": "other clip"},
    ]
    keep = [
        {"id": 2, "reason": "later"},
        {"id": 1, "reason": "first"},
        {"id": 3, "reason": "clip one"},
    ]
    segs, unknown = segments(utts, keep, [10.0, 5.0])
    assert unknown == []
    assert [(s["clip"], s["reason"]) for s in segs] == [(0, "later"), (1, "clip one")]
    assert segs[0]["start"] == pytest.approx(0.75)
    assert segs[0]["end"] == pytest.approx(3.90)
    assert segs[1]["start"] == pytest.approx(0.0)
    assert segs[1]["end"] == pytest.approx(1.20)


def test_gap_of_one_second_does_not_merge():
    utts = [
        {"id": 1, "clip": 0, "start": 0.2, "end": 1.0, "text": "alpha beta gamma"},
        {"id": 2, "clip": 0, "start": 2.0, "end": 3.0, "text": "delta epsilon zeta"},
    ]
    segs, unknown = segments(
        utts,
        [{"id": 1, "reason": "early"}, {"id": 2, "reason": "late"}],
        [10.0],
    )
    assert unknown == []
    assert len(segs) == 2
    assert segs[0]["end"] == pytest.approx(1.40)
    assert segs[1]["start"] == pytest.approx(1.75)
    assert segs[0]["reason"] == "early"
    assert segs[1]["reason"] == "late"


def test_segment_pads_and_clamps():
    utts = [{"id": 1, "clip": 0, "start": 0.05, "end": 2.9, "text": "edge case here"}]
    segs, _unknown = segments(utts, [{"id": 1, "reason": "keep"}], [3.0])
    assert segs == [{"clip": 0, "start": 0.0, "end": 3.0, "reason": "keep"}]


def test_unknown_id_is_ignored():
    utts = [{"id": 1, "clip": 0, "start": 1.0, "end": 2.0, "text": "hello there friend"}]
    segs, unknown = segments(
        utts,
        [{"id": 1, "reason": "yes"}, {"id": 99, "reason": "no"}],
        [10.0],
    )
    assert unknown == [99]
    assert unknown_warnings(unknown) == ["unknown id 99"]
    assert len(segs) == 1
    assert segs[0]["reason"] == "yes"


def test_overlapping_keeps_collapse_and_keep_the_later_reason():
    utts = [
        {"id": 1, "clip": 0, "start": 1.0, "end": 2.5, "text": "one"},
        {"id": 2, "clip": 0, "start": 2.0, "end": 3.0, "text": "two"},
    ]
    segs, _unknown = segments(
        utts,
        [{"id": 1, "reason": "early"}, {"id": 2, "reason": "later"}],
        [10.0],
    )
    assert len(segs) == 1
    assert segs[0]["reason"] == "later"
    assert segs[0]["start"] == pytest.approx(0.75)
    assert segs[0]["end"] == pytest.approx(3.40)


def test_unique_warning_skips_near_duplicates():
    kept = [{"id": 2, "text": "welcome to the product today"}]
    retake = [{"id": 1, "text": "welcome to the product"}]
    unique = [{"id": 4, "text": "the price is forty nine dollars"}]
    assert unique_warnings(retake, kept) == []
    assert unique_warnings(unique, kept) == ["unique? id 4: the price is forty nine dollars"]
    assert near_duplicate("put the button above", "we should put the button right above the fold")
    assert dropped_utterances(
        [
            {"id": 1, "clip": 0, "start": 0, "end": 1, "text": "welcome to the product"},
            {"id": 4, "clip": 0, "start": 2, "end": 3, "text": "the price is forty nine dollars"},
        ],
        [{"id": 1, "reason": "keep"}],
    )[0]["id"] == 4


def test_fake_pick_keeps_every_id_without_a_key(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setenv("BOTCUT_FAKE", "1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setattr("botcut.pick.requests.post", boom)
    assert pick([{"id": 3, "text": "hello"}, {"id": 4, "text": "again"}]) == [
        {"id": 3, "reason": "fake"},
        {"id": 4, "reason": "fake"},
    ]


def test_story_prompt_carries_the_intent_and_retakes_stay_retakes():
    story = system_prompt("a ride along the coast")
    assert "a ride along the coast" in story
    assert "one movie" in story
    assert "takes recorded in order" not in story
    default = system_prompt("")
    assert DEFAULT_INTENT in default
    assert "one movie" in default
    retake = system_prompt("repeated takes of the intro")
    assert "takes recorded in order" in retake
    assert "repeated takes of the intro" in retake


def test_decision_lines_mark_a_unique_drop():
    utts = [
        {"id": 1, "clip": 0, "start": 0.0, "end": 1.0, "text": "welcome to the product"},
        {"id": 4, "clip": 1, "start": 0.0, "end": 1.0, "text": "the price is forty nine dollars"},
    ]
    lines = decision_lines(utts, [{"id": 1, "reason": "clean"}])
    assert lines[0]["keep"] is True
    assert lines[0]["reason"] == "clean"
    assert lines[1]["keep"] is False
    assert lines[1]["reason"] == "unique?"


def test_default_model_is_grok_4_7_with_low_effort(monkeypatch):
    monkeypatch.delenv("BOTCUT_LLM_MODEL", raising=False)
    assert model_name() == "grok-4.7"
    assert chat_fields() == {"model": "grok-4.7", "reasoning_effort": "low"}
    assert chat_fields("grok-4.5") == {"model": "grok-4.5", "reasoning_effort": "low"}
    assert chat_fields("grok-4.6") == {"model": "grok-4.6", "reasoning_effort": "low"}
    assert chat_fields("grok-4.3") == {"model": "grok-4.3"}
    monkeypatch.setenv("BOTCUT_LLM_MODEL", "grok-4.3")
    assert model_name() == "grok-4.3"
    assert chat_fields() == {"model": "grok-4.3"}


def test_pick_sends_low_effort_and_hides_the_key(monkeypatch):
    monkeypatch.delenv("BOTCUT_LLM_MODEL", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "supersecret")
    seen = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": '{"keep": [{"id": 0, "reason": "ok"}]}'}}]}

    def post(url, headers=None, json=None, timeout=None):
        seen["body"] = json
        seen["auth"] = headers["Authorization"]
        return Response()

    monkeypatch.setattr("botcut.pick.requests.post", post)
    assert pick([{"id": 0, "clip": 0, "start": 0.0, "end": 1.0, "text": "hello"}]) == [
        {"id": 0, "reason": "ok"}
    ]
    assert seen["body"]["model"] == "grok-4.7"
    assert seen["body"]["reasoning_effort"] == "low"
    assert seen["auth"] == "Bearer supersecret"
    assert "supersecret" not in str(seen["body"])
