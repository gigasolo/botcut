import pytest

from botcut.pick import (
    dropped_utterances,
    near_duplicate,
    pick,
    segments,
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
    assert segs[0]["start"] == pytest.approx(0.85)
    assert segs[0]["end"] == pytest.approx(3.75)
    assert segs[1]["start"] == pytest.approx(0.05)
    assert segs[1]["end"] == pytest.approx(1.05)


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
    assert segs[0]["end"] == pytest.approx(1.25)
    assert segs[1]["start"] == pytest.approx(1.85)
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
    assert segs[0]["start"] == pytest.approx(0.85)
    assert segs[0]["end"] == pytest.approx(3.25)


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
