"""Plain checks on a finished cut."""

from botcut import check


def _line(uid, text, keep=True, start=None, length=2.0, reason="ok", clip=0):
    start = uid * 3.0 if start is None else start
    return {
        "id": uid,
        "clip": clip,
        "start": start,
        "end": start + length,
        "text": text,
        "keep": keep,
        "reason": reason,
    }


def test_a_point_kept_twice_is_flagged_once_with_both_lines():
    lines = [
        _line(0, "We opened the shop in the spring of last year"),
        _line(1, "Something else entirely happened after"),
        _line(2, "We opened the shop in the spring of last year again"),
        _line(3, "We opened the shop in the spring of last year", keep=False),
    ]
    found = check.flags(lines)
    assert [(flag["kind"], flag["ids"]) for flag in found] == [("twice", [0, 2])]
    assert found[0]["text"] == "Lines 0 and 2 say the same thing."


def test_a_line_that_leans_on_a_dropped_one_is_flagged():
    lines = [
        _line(0, "First we tried it the slow way.", keep=False),
        _line(1, "And that is why it broke."),
        _line(2, "So we fixed it."),
        _line(3, "Thanks", keep=False),
        _line(4, "Because nobody asked."),
    ]
    found = check.flags(lines)
    # Line 2 follows a kept line, so its "So" has something to lean on.
    assert [(flag["kind"], flag["ids"]) for flag in found] == [("leans", [1]), ("leans", [4])]
    assert 'opens on "and"' in found[0]["text"]


def test_a_card_is_never_what_a_line_leans_on_or_repeats():
    lines = [
        _line(0, "How we built the shop", reason="card"),
        _line(1, "How we built the shop"),
        _line(2, "But first a word."),
    ]
    assert check.flags(lines) == []


def test_a_piece_too_short_to_read_is_flagged_and_a_card_is_not():
    segments = [
        {"clip": 0, "start": 0.0, "end": 4.0, "reason": "ok"},
        {"clip": 0, "start": 6.0, "end": 6.4, "reason": "ok"},
        {"clip": 1, "start": 0.0, "end": 0.2, "reason": "card"},
    ]
    found = check.flags([], segments)
    assert [flag["kind"] for flag in found] == ["flash"]
    assert found[0]["text"] == "A piece of shot 0 is only 0.4s long."


def test_length_is_judged_against_what_was_asked_and_only_then():
    lines = [_line(0, "One thing"), _line(1, "Another thing"), _line(2, "Gone", keep=False)]
    assert check.cut_seconds(lines) == 4.0
    assert check.flags(lines) == []
    assert check.flags(lines, target=4.4) == []
    assert [flag["kind"] for flag in check.flags(lines, target=3.0)] == ["long"]
    assert [flag["kind"] for flag in check.flags(lines, target=10.0)] == ["short"]
    # The pieces are what plays, so they are what is measured when there are some.
    pieces = [{"clip": 0, "start": 0.0, "end": 10.0, "reason": "ok"}]
    assert check.cut_seconds(lines, pieces) == 10.0
    assert check.flags(lines, pieces, target=10.0) == []


def test_counts_name_only_the_kinds_that_happened():
    found = [{"kind": "leans"}, {"kind": "twice"}, {"kind": "leans"}]
    assert check.counts(found) == {"twice": 1, "leans": 2}
    assert check.counts([]) == {}


def test_a_jump_is_a_join_inside_one_shot_and_not_a_change_of_shot():
    from botcut.check import jumps

    lines = [
        {"id": 0, "clip": 0, "start": 1.0, "end": 6.0, "keep": True, "text": "a",
         "cuts": [{"from": 1, "through": 1, "start": 3.0, "end": 3.5, "cut": True}]},
        {"id": 1, "clip": 0, "start": 9.0, "end": 12.0, "keep": True, "text": "b"},
        {"id": 2, "clip": 1, "start": 0.0, "end": 3.0, "keep": True, "text": "c"},
    ]
    pieces = [
        {"clip": 0, "start": 0.75, "end": 3.0, "reason": "a"},
        {"clip": 0, "start": 3.5, "end": 6.4, "reason": "a"},
        {"clip": 0, "start": 8.75, "end": 12.4, "reason": "b"},
        {"clip": 1, "start": 0.0, "end": 3.4, "reason": "c"},
    ]
    # The "um" taken out inside a line is not counted. The join between two lines is. The new shot is not.
    assert jumps(pieces, lines) == 1
    # A sliver left by a cut inside a line reads as a stutter, and is counted.
    pieces[0]["start"] = 2.8
    assert jumps(pieces, lines) == 2
    assert jumps([], lines) == 0
