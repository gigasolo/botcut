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
    pieces = tighten(segs, silences, 0.85)
    assert pieces == [
        {"clip": 0, "start": 0.0, "end": 4.22, "reason": "later"},
        {"clip": 0, "start": 5.82, "end": 10.0, "reason": "later"},
    ]


def test_tighten_respects_min_savings_and_cooldown():
    segs = [{"clip": 0, "start": 0.0, "end": 15.0, "reason": "talk"}]
    # 0.60s pause on measured (0.85s trigger) is untouched; 0.90s at 2.0s cuts;
    # 0.95s at 3.8s is within 2.5s cooldown so skipped; 2.0s major stall at 5.0s still cuts.
    silences = [[(0.5, 1.1), (2.0, 2.9), (3.8, 4.75), (5.0, 7.0)]]
    pieces = tighten(segs, silences, 0.85)
    assert len(pieces) == 3
    assert pieces[0]["end"] == pytest.approx(2.22)
    assert pieces[1]["start"] == pytest.approx(2.72)
    assert pieces[1]["end"] == pytest.approx(5.22)
    assert pieces[2]["start"] == pytest.approx(6.82)


def test_tighten_context_aware_beat_vs_mid_sentence():
    segs = [{"clip": 0, "start": 0.0, "end": 12.0, "reason": "talk"}]
    lines = [
        {"id": 1, "clip": 0, "start": 0.0, "end": 3.0, "text": "And then we", "keep": True},
        {"id": 2, "clip": 0, "start": 3.7, "end": 6.0, "text": "shipped the release.", "keep": True},
        {"id": 3, "clip": 0, "start": 7.1, "end": 11.0, "text": "Next topic.", "keep": True},
    ]
    beats = [{"title": "Release", "first": 1, "last": 2}]
    # 0.70s mid-sentence hesitation (3.0..3.7) cuts on measured (trigger 0.85 - 0.25 = 0.60, saves 0.30? wait 0.80s saves 0.40s).
    # 1.10s beat transition (6.0..7.1) is preserved because beat bonus raises trigger to 1.20s.
    silences = [[(3.0, 3.8), (6.0, 7.1)]]
    pieces = tighten(segs, silences, 0.85, lines=lines, beats=beats)
    assert len(pieces) == 2
    assert pieces[0]["end"] == pytest.approx(3.22)
    assert pieces[1]["start"] == pytest.approx(3.62)


def test_cut_words_coalesces_adjacent_silence():
    from botcut.pick import cut_words

    segs = [{"clip": 0, "start": 0.0, "end": 6.0, "reason": "talk"}]
    lines = [
        {
            "id": 1,
            "clip": 0,
            "start": 0.0,
            "end": 6.0,
            "text": "So um we shipped.",
            "keep": True,
            "cuts": [{"from": 1, "through": 1, "start": 2.0, "end": 2.3, "cut": True}],
        }
    ]
    silences = [[(1.5, 1.98), (2.32, 2.9)]]
    out = cut_words(segs, lines, silences_by_clip=silences)
    assert len(out) == 2
    assert out[0]["end"] == pytest.approx(1.62)
    assert out[1]["start"] == pytest.approx(2.78)


def test_phase3_trim_note_crossfade_and_tiny_trim_framing():
    from botcut.frame import AutoFraming
    from botcut.pick import TRIM_NOTE, TRIM_NOTE_GENTLE, trim_note_for_pace
    from botcut.render import CROSS, PAUSE_CROSS, RATE, _join_cross

    assert trim_note_for_pace(1.4) == TRIM_NOTE_GENTLE
    assert trim_note_for_pace(0.85) == TRIM_NOTE_GENTLE
    assert trim_note_for_pace(0.55) == TRIM_NOTE
    assert trim_note_for_pace(0.35) == TRIM_NOTE

    word_c = int(CROSS * RATE)
    pause_c = int(PAUSE_CROSS * RATE)
    left = {"clip": 0, "source": 0.0, "begin": 0, "end": 2 * RATE}
    right_word = {"clip": 0, "source": 2.15, "begin": 2 * RATE, "end": 4 * RATE}
    right_pause = {"clip": 0, "source": 3.20, "begin": 2 * RATE, "end": 4 * RATE}
    assert _join_cross(left, right_word, True, word_c, pause_c) == word_c
    assert _join_cross(left, right_pause, True, word_c, pause_c) == pause_c

    auto = AutoFraming()
    assert auto.frame(0, 5.0, close=False, runs_on=False, same_footage=False, gap=0.0) is False
    # Tiny 0.25s trim stays wide instead of hopping zoom.
    assert auto.frame(0, 5.0, close=False, runs_on=False, same_footage=False, gap=0.25) is False
    # Real 1.8s jump toggles tight.
    assert auto.frame(0, 5.0, close=False, runs_on=False, same_footage=False, gap=1.80) is True


def test_xai_cache_still_accepts_the_b1_filename():
    names = word_cache_candidates("/tmp/work", 1, "take", "xai")
    assert names[0].endswith("1-take.xai.words.json")
    assert names[1].endswith("1-take.words.json")
    assert len(word_cache_candidates("/tmp/work", 1, "take", "local")) == 1


def test_local_stt_import_is_optional():
    pytest.importorskip("faster_whisper")
    assert callable(transcribe_local)


def test_a_noisy_shot_gets_a_higher_pause_level_and_a_quiet_one_keeps_the_usual():
    import numpy as np

    from botcut.media import levels_of, silence_threshold

    assert silence_threshold(None) == -35.0
    assert silence_threshold((-60.0, -20.0)) == -35.0
    # A street at -30 under a voice at -8: a pause is what is under -22.
    assert silence_threshold((-30.0, -8.0)) == -22.0
    assert silence_threshold((-30.0, -12.0)) == -24.0
    # Never within 12 dB of the voice, and never above -18.
    assert silence_threshold((-30.0, -30.0)) == -35.0
    assert silence_threshold((-10.0, -2.0)) == -18.0
    rng = np.random.default_rng(1)
    room = rng.normal(0, 0.01, 16000 * 4)
    voice = rng.normal(0, 0.2, 16000 * 4)
    samples = (np.concatenate([room, voice]) * 32767).clip(-32768, 32767).astype(np.int16)
    floor, loud = levels_of(samples)
    assert -41 < floor < -39 and -15 < loud < -13
    assert levels_of(np.zeros(16000 * 4, dtype=np.int16)) is None
