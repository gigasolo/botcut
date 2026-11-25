"""Two cameras on one take are lined up by their sound."""

import numpy as np
import pytest

from botcut import sync


def _talk(seconds, seed=0):
    """Something like a voice: noise that comes in bursts of uneven length, with pauses."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(seconds * sync.RATE), dtype=np.float32)
    at = 0
    while at < len(out):
        burst = int(rng.uniform(0.08, 0.5) * sync.RATE)
        gap = int(rng.uniform(0.03, 0.4) * sync.RATE)
        end = min(len(out), at + burst)
        out[at:end] = rng.normal(0, rng.uniform(0.05, 0.3), end - at)
        at = end + gap
    return out


def _other_mic(samples, seed=9):
    """The same room through another microphone: duller, quieter, with its own hiss."""
    rng = np.random.default_rng(seed)
    dull = np.convolve(samples, np.ones(6) / 6, mode="same")
    return (0.4 * dull + rng.normal(0, 0.01, len(samples))).astype(np.float32)


def test_a_camera_started_later_is_found_to_the_millisecond():
    a = _talk(90)
    late = int(12.345 * sync.RATE)
    b = _other_mic(a)[late : late + 60 * sync.RATE]
    found = sync.line_up(a, b)
    assert found is not None and found["score"] > sync.SURE
    # A moment t seconds into a is at t - 12.345 in b.
    assert found["offset"] == pytest.approx(-12.345, abs=0.002)
    assert found["drift"] == 0.0
    assert found["start"] == pytest.approx(12.345, abs=0.01) and found["end"] == pytest.approx(72.345, abs=0.01)


def test_a_camera_started_earlier_has_a_positive_offset():
    a = _talk(60, seed=3)
    b = np.concatenate([_talk(7.5, seed=4), _other_mic(a)])
    found = sync.line_up(a, b)
    assert found["offset"] == pytest.approx(7.5, abs=0.002)
    assert found["start"] == 0.0 and found["end"] == pytest.approx(60.0, abs=0.01)


def test_two_takes_of_the_same_kind_are_not_the_same_take():
    assert sync.line_up(_talk(60, seed=1), _talk(60, seed=2)) is None
    assert sync.line_up(_talk(60, seed=1), np.zeros(60 * sync.RATE, dtype=np.float32)) is None
    # Sharing three seconds of a take is not enough to cut between them.
    a = _talk(60, seed=5)
    assert sync.line_up(a, np.concatenate([a[-3 * sync.RATE :], _talk(50, seed=6)])) is None


def test_a_camera_that_runs_a_little_slow_is_followed_across_a_long_take():
    a = _talk(400, seed=7)
    # b's clock runs 100 parts in a million slow: 40 ms over the take, more than a frame.
    rate = 1 - 100e-6
    places = np.arange(int(len(a) * rate)) / rate
    b = np.interp(places, np.arange(len(a)), _other_mic(a)).astype(np.float32)
    found = sync.line_up(a, b)
    assert found is not None
    assert found["drift"] == pytest.approx(-100e-6, abs=20e-6)
    for at in (20.0, 200.0, 380.0):
        assert at + found["offset"] + found["drift"] * at == pytest.approx(at * rate, abs=0.004)
