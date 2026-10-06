from pathlib import Path

import pytest

from botcut.cli import word_cache_candidates
from botcut.media import parse_silences
from botcut.pick import snap, tighten
from botcut.stt import transcribe_local


def test_parse_silences_closes_a_trailing_start():
    stderr = (Path(__file__).parent / "fixtures" / "silencedetect.txt").read_text()
    assert parse_silences(stderr, 4.0) == [(0.0, 0.42), (3.5, 4.0)]


def test_snap_moves_edges_into_speech():
    segs = [{"clip": 0, "start": 0.2, "end": 1.8, "reason": "keep"}]
    silences = [[(0.0, 0.5), (1.5, 2.2)]]
    snapped = snap(segs, silences)
    assert snapped[0]["start"] == pytest.approx(0.40)
    assert snapped[0]["end"] == pytest.approx(1.65)
    assert snapped[0]["reason"] == "keep"


def test_snap_refuses_to_shrink_below_0_3s():
    segs = [{"clip": 0, "start": 0.10, "end": 1.05, "reason": "keep"}]
    # Snapped start 0.90 and snapped end 1.15 would leave 0.25 s.
    silences = [[(0.0, 1.0), (1.0, 2.0)]]
    assert snap(segs, silences) == segs


def test_tighten_splits_a_two_second_silence():
    segs = [{"clip": 0, "start": 0.0, "end": 10.0, "reason": "later"}]
    silences = [[(4.0, 6.0)]]
    pieces = tighten(segs, silences, 0.8)
    assert pieces == [
        {"clip": 0, "start": 0.0, "end": 4.15, "reason": "later"},
        {"clip": 0, "start": 5.85, "end": 10.0, "reason": "later"},
    ]


def test_xai_cache_still_accepts_the_b1_filename():
    names = word_cache_candidates("/tmp/work", 1, "take", "xai")
    assert names[0].endswith("1-take.xai.words.json")
    assert names[1].endswith("1-take.words.json")
    assert len(word_cache_candidates("/tmp/work", 1, "take", "local")) == 1


def test_local_stt_import_is_optional():
    pytest.importorskip("faster_whisper")
    assert callable(transcribe_local)
