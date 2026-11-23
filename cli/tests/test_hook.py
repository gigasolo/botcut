"""One line lifted to the front of the movie, and everything that has to know it moved."""

import json

from botcut import cli
from botcut.broll import accept_runs, cover_user_content
from botcut.captions import remap_words
from botcut.pick import hook_line, play_order
from botcut.revise import _land
from botcut.short import highlight_span


def _line(uid, start, end, text="words", keep=True, reason="ok", clip=0):
    return {"id": uid, "clip": clip, "start": start, "end": end, "text": text, "keep": keep, "reason": reason}


# Four lines in one shot, played as two pieces. Line 2 sits inside the second.
LINES = [
    _line(0, 1.0, 3.0),
    _line(1, 10.0, 12.0),
    _line(2, 12.6, 14.6),
    _line(3, 15.0, 17.0),
    _line(4, 20.0, 22.0, keep=False, reason="retake"),
]
PIECES = [
    {"clip": 0, "start": 0.75, "end": 3.4, "reason": "ok"},
    {"clip": 0, "start": 9.75, "end": 17.4, "reason": "ok"},
]


def _spans(pieces):
    return [(seg["clip"], round(seg["start"], 2), round(seg["end"], 2), bool(seg.get("hook"))) for seg in pieces]


def test_the_hook_is_lifted_out_of_its_piece_and_plays_first():
    ordered = play_order(PIECES, LINES, 2)
    # It takes its usual quarter second of lead, and no more than half the air to the
    # line after it. Its place is closed up behind it.
    assert _spans(ordered) == [
        (0, 12.35, 14.8, True),
        (0, 0.75, 3.4, False),
        (0, 9.75, 12.35, False),
        (0, 14.8, 17.4, False),
    ]
    # Nothing is played twice and nothing is lost.
    assert round(sum(seg["end"] - seg["start"] for seg in ordered), 2) == round(
        sum(seg["end"] - seg["start"] for seg in PIECES), 2
    )
    # Ordering what is already ordered changes nothing.
    assert _spans(play_order(ordered, LINES, 2)) == _spans(ordered)
    # The pieces handed in are not written on.
    assert "hook" not in PIECES[1]


def test_a_hook_at_the_edge_of_a_piece_leaves_no_sliver():
    ordered = play_order(PIECES, LINES, 1)
    assert _spans(ordered) == [
        (0, 9.75, 12.3, True),
        (0, 0.75, 3.4, False),
        (0, 12.3, 17.4, False),
    ]


def test_no_hook_a_dropped_hook_and_a_card_leave_the_order_alone():
    cards = [*LINES, _line(9, 0.0, 3.0, reason="card", clip=1)]
    for hook in (None, -1, 4, 9, 77, True, "2"):
        assert _spans(play_order(PIECES, cards, hook)) == _spans(PIECES), hook
        assert hook_line(cards, hook) is None
    assert hook_line(LINES, 2)["id"] == 2
    # A mark left by an earlier order does not outlive the hook.
    stale = [{**PIECES[0], "hook": True}, PIECES[1]]
    assert _spans(play_order(stale, LINES, None)) == _spans(PIECES)


def test_captions_follow_the_order_the_pieces_play_in():
    words = [
        {"text": "first", "start": 1.0, "end": 1.4},
        {"text": "hook", "start": 12.6, "end": 13.0},
        {"text": "last", "start": 15.0, "end": 15.4},
    ]
    mapped = remap_words(play_order(PIECES, LINES, 2), [words])
    assert [word["text"] for word in mapped] == ["hook", "first", "last"]
    assert round(mapped[0]["start"], 2) == 0.25


def test_a_highlight_is_measured_in_the_body_not_from_the_opening():
    words = [
        {"text": "one", "start": 10.0, "end": 10.4},
        {"text": "hook", "start": 12.6, "end": 13.0},
        {"text": "three", "start": 15.0, "end": 15.4},
    ]
    utts = [{**line} for line in LINES]
    ordered = play_order(PIECES, LINES, 2)
    start, end = highlight_span(ordered, [words], utts, 1, 3)
    # The opening is 2.45s and the first piece 2.65s, so line 1 starts 5.35s in.
    assert (round(start, 2), round(end, 2)) == (5.35, 8.3)
    # A highlight of nothing but the opening line is the opening.
    start, end = highlight_span(ordered, [words], utts, 2, 2)
    assert (round(start, 2), round(end, 2)) == (0.25, 0.65)


def test_b_roll_never_runs_across_the_line_that_left_its_place():
    lines = [_line(i, i * 5.0, i * 5.0 + 4.0) for i in range(6)]
    beats = {0: {"id": 0, "clip": 1, "start": 0.0, "end": 4.0}, 1: {"id": 1, "clip": 1, "start": 4.0, "end": 8.0}}
    claims = [
        {"beat": 0, "line": 1, "through": 2, "reason": "shows it"},
        {"beat": 1, "line": 3, "through": 4, "reason": "rest"},
    ]
    both = accept_runs(claims, beats=beats, lines=lines, durations=[30.0, 60.0])
    assert [(run["line"], run["through"]) for run in both] == [(1, 2), (3, 4)]
    one = accept_runs(claims, beats=beats, lines=lines, durations=[30.0, 60.0], hook=2)
    assert [(run["line"], run["through"]) for run in one] == [(3, 4)]
    text = cover_user_content(list(beats.values()), lines, {}, hook=2)
    assert "[2] 4.0s words (opens the movie, moved to the front; stay on the speaker)" in text
    assert "[1] 4.0s words\n" in text


def test_a_change_in_the_chat_keeps_the_opening_until_its_line_is_dropped(tmp_path):
    path = tmp_path / "cuts.json"
    doc = {"clips": [{"index": 0, "path": "/tmp/talk.mp4", "duration": 30.0}], "lines": LINES, "hook": 2}
    result = {
        "reply": "ok",
        "intent": "A talk",
        "pace": "open",
        "dip": True,
        "deliver": "none",
        "covers": None,
        "fillers": "same",
        "keep": [{"id": uid, "reason": "ok"} for uid in (0, 1, 2)],
    }
    doc["close"] = [0, 2]
    _land(str(path), dict(doc), LINES, result)
    assert json.loads(path.read_text())["hook"] == 2
    # The lines shown close stay so while they are kept, like the opening.
    assert json.loads(path.read_text())["close"] == [0, 2]
    result["keep"] = [{"id": uid, "reason": "ok"} for uid in (0, 1, 3)]
    _land(str(path), dict(doc), LINES, result)
    assert "hook" not in json.loads(path.read_text())
    assert json.loads(path.read_text())["close"] == [0]
    result["keep"] = [{"id": uid, "reason": "ok"} for uid in (1, 3)]
    _land(str(path), dict(doc), LINES, result)
    assert "close" not in json.loads(path.read_text())


seen_more: list[dict] = []


def _render_stub(monkeypatch, seen):
    monkeypatch.setattr(cli, "probe", lambda path, need_audio=True: {"path": path, "duration": 30.0})
    monkeypatch.setattr(cli, "_level_clips", lambda *a: None)

    def render(segs, clips, dst, *_a, **more):
        seen.append(_spans(segs))
        seen_more.append(more)

    monkeypatch.setattr(cli, "render_with_progress", render)


def test_a_render_puts_the_opening_first_and_forgets_it_when_its_line_goes(monkeypatch, tmp_path):
    seen = []
    _render_stub(monkeypatch, seen)
    out = tmp_path / "out"
    out.mkdir()
    doc = {
        "version": 1,
        "tighten": {"max_pause": 0.8, "snap": False},
        "clips": [{"index": 0, "path": "/tmp/talk.mp4", "duration": 30.0}],
        "lines": LINES,
        "hook": 2,
        "close": [1, 2],
    }
    (out / "cuts.json").write_text(json.dumps(doc))
    cli.render_saved(str(out))
    # No zoom unless the render is told one. The lines to show close ride along either way.
    assert (seen_more[-1]["zoom"], seen_more[-1]["close"]) == ("off", [1, 2])
    cli.render_saved(str(out), zoom="lines")
    assert (seen_more[-1]["zoom"], seen_more[-1]["close"]) == ("lines", [1, 2])
    assert seen[-1][0] == (0, 12.35, 14.8, True)
    assert [span[3] for span in seen[-1]] == [True, False, False, False]
    saved = json.loads((out / "cuts.json").read_text())
    assert saved["hook"] == 2 and saved["segments"][0]["hook"] is True

    # The person drops that line. The movie opens where the shoot did, and stays that way.
    saved["lines"][2]["keep"] = False
    (out / "cuts.json").write_text(json.dumps(saved))
    cli.render_saved(str(out))
    assert not any(span[3] for span in seen[-1])
    assert seen[-1][0][1] == 0.75
    assert "hook" not in json.loads((out / "cuts.json").read_text())
    # A dropped line is not shown close either.
    assert json.loads((out / "cuts.json").read_text())["close"] == [1]
    assert seen_more[-1]["close"] == [1]

    # A hand trim owns the pieces, in the order it left them.
    trimmed = json.loads((out / "cuts.json").read_text())
    trimmed["trimmed"] = True
    trimmed["segments"] = [
        {"clip": 0, "start": 12.35, "end": 14.0, "reason": "ok", "hook": True},
        {"clip": 0, "start": 0.75, "end": 3.4, "reason": "ok"},
    ]
    (out / "cuts.json").write_text(json.dumps(trimmed))
    cli.render_saved(str(out))
    assert seen[-1] == [(0, 12.35, 14.0, True), (0, 0.75, 3.4, False)]


def test_a_cut_opens_on_the_line_the_proof_names(monkeypatch, tmp_path):
    # The two-request way, as a shoot too long for one request is cut.
    monkeypatch.setenv("BOTCUT_FOLD", "0")
    monkeypatch.setenv("XAI_API_KEY", "secret")
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    shot = tmp_path / "talk.mp4"
    shot.write_bytes(b"x")
    said = ["Hello there.", "We make chairs.", "By hand.", "Nobody else does this.", "Come by.", "Goodbye now."]
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
    answers = {
        "outline": {"beats": [], "retakes": [], "hook": 3, "target_seconds": 0},
        "keep": {"keep": [{"id": uid, "reason": "ok", "cuts": []} for uid in range(6)]},
        "proof": {
            "reply": "Chairs, opening on the boast.",
            "drop": [],
            "restore": [],
            "cuts": [],
            "hook": 3,
            "close": [1],
        },
    }
    shown = {}

    class Reply:
        status_code = 200
        text = ""

        def __init__(self, content):
            self._content = json.dumps(content)

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    def post(url, headers=None, json=None, timeout=None):
        name = json["response_format"]["json_schema"]["name"]
        shown[name] = json["messages"][1]["content"]
        return Reply(answers[name])

    monkeypatch.setattr("botcut.net.requests.post", post)
    cli.run([str(shot)], str(tmp_path / "out"), decide=True)
    # The first read only suggests. The proof, which read the cut, is what decides.
    assert "line 3 looked like one the movie could open on" in shown["proof"]
    doc = json.loads((tmp_path / "out" / "cuts.json").read_text())
    assert doc["hook"] == 3
    # The line that carries the point is kept with the cut, whatever the zoom is set to.
    assert doc["close"] == [1]
    first = doc["segments"][0]
    assert first["hook"] is True and first["start"] <= 15.0 < first["end"]
    assert not any(seg.get("hook") for seg in doc["segments"][1:])
    # The lines stay in the order they were said.
    assert [line["id"] for line in doc["lines"]] == list(range(6))

    # Without the proof's say-so, nothing moves.
    answers["proof"]["hook"] = -1
    answers["proof"]["close"] = []
    cli.run([str(shot)], str(tmp_path / "out2"), decide=True)
    doc = json.loads((tmp_path / "out2" / "cuts.json").read_text())
    assert "hook" not in doc
    assert "close" not in doc
    assert not any(seg.get("hook") for seg in doc["segments"])
