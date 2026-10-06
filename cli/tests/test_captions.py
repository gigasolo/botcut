import json

import pytest

from botcut.captions import group_cues, load_words_by_clip, remap_words, to_srt


def test_remap_across_two_clips_starts_at_zero_and_stays_ordered():
    segments = [
        {"clip": 0, "start": 1.0, "end": 2.0, "reason": "a"},
        {"clip": 1, "start": 0.0, "end": 1.0, "reason": "b"},
    ]
    words = [
        [
            {"text": "skip", "start": 0.2, "end": 0.4},
            {"text": "one", "start": 1.0, "end": 1.4},
            {"text": "two", "start": 1.5, "end": 1.9},
        ],
        [{"text": "three", "start": 0.1, "end": 0.4}, {"text": "late", "start": 1.2, "end": 1.4}],
    ]
    mapped = remap_words(segments, words)
    assert [word["text"] for word in mapped] == ["one", "two", "three"]
    assert mapped[0]["start"] == pytest.approx(0.0)
    assert mapped[0]["end"] == pytest.approx(0.4)
    assert mapped[1]["start"] == pytest.approx(0.5)
    assert mapped[2]["start"] == pytest.approx(1.1)
    starts = [word["start"] for word in mapped]
    assert starts == sorted(starts)
    assert all(word["end"] >= word["start"] for word in mapped)


def test_srt_cues_stay_within_32_chars_and_two_seconds():
    words = []
    t = 0.0
    for _ in range(40):
        words.append({"text": "word", "start": t, "end": t + 0.3})
        t += 0.35
    words.append({"text": "gap", "start": t + 0.5, "end": t + 0.8})
    cues = group_cues(words)
    assert len(cues) > 1
    for cue in cues:
        assert len(cue["text"]) <= 32
        assert cue["end"] - cue["start"] <= 2.0
    srt = to_srt(words)
    assert "-->" in srt
    assert srt.splitlines()[1].startswith("00:")


def test_missing_word_cache_names_the_file(tmp_path):
    cuts = {
        "stt": "xai:grok-voice-transcribe-2.0",
        "clips": [{"index": 0, "path": "/tmp/take.mp4", "duration": 3}],
        "segments": [],
    }
    with pytest.raises(SystemExit, match=r"No word cache: .*/0-take\.xai\.words\.json"):
        load_words_by_clip(cuts, str(tmp_path))


def test_captions_writes_srt_without_burning(tmp_path, capsys):
    from botcut.cli import captions

    work = tmp_path / "work"
    work.mkdir()
    (work / "0-take.fake.words.json").write_text(
        json.dumps(
            {
                "duration": 2,
                "words": [
                    {"text": "hello", "start": 0.2, "end": 0.5},
                    {"text": "there", "start": 0.6, "end": 0.9},
                ],
            }
        )
    )
    doc = {
        "stt": "fake",
        "clips": [{"index": 0, "path": str(tmp_path / "take.mp4"), "duration": 2}],
        "segments": [{"clip": 0, "start": 0.0, "end": 1.0, "reason": "fake"}],
    }
    cuts = tmp_path / "cuts.json"
    cuts.write_text(json.dumps(doc))
    captions(str(cuts), burn=False)
    text = (tmp_path / "rough_cut.srt").read_text()
    assert "hello there" in text
    assert "rough_cut.srt" in capsys.readouterr().out
    assert not (tmp_path / "rough_cut.captioned.mp4").exists()
