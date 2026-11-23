"""The whole shoot read once, before any line is judged."""

import json
import threading

import pytest

from botcut import pick as picking
from botcut.llm import chat_fields
from botcut.pick import no_outline, outline, outline_note, pick, read_outline, shown_stills


def _utts(count, text="line {i}"):
    return [
        {"id": i, "clip": 0, "start": float(i * 2), "end": i * 2 + 1.5, "text": text.format(i=i)}
        for i in range(count)
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


def test_an_outline_keeps_only_what_points_at_real_lines():
    utts = _utts(10)
    plan = read_outline(
        {
            "beats": [
                {"title": "  The   opening ", "first": 0, "last": 3},
                {"title": "Backwards", "first": 6, "last": 4},
                {"title": "Nowhere", "first": 4, "last": 99},
                {"title": "", "first": 4, "last": 5},
            ],
            "retakes": [
                {"ids": [7, 2, 2, 50]},
                {"ids": [2, 8]},
                {"ids": [9]},
                {"ids": [True, 5]},
            ],
            "hook": 42,
            "target_seconds": 90,
        },
        utts,
    )
    assert plan["beats"] == [{"title": "The opening", "first": 0, "last": 3}]
    # In line order, without the id that does not exist. A line is in one group only,
    # and a group of one is not a retake.
    assert plan["retakes"] == [[2, 7]]
    assert plan["hook"] == -1
    assert plan["target_seconds"] == 90
    silly = read_outline({"beats": [], "retakes": [], "hook": 3, "target_seconds": 10**7}, utts)
    assert (silly["hook"], silly["target_seconds"]) == (3, 0)
    with pytest.raises(ValueError):
        read_outline(["not", "an", "outline"], utts)


def test_a_short_shoot_and_an_offline_run_ask_for_no_outline(live, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("no request was expected")

    monkeypatch.setattr("botcut.net.requests.post", boom)
    assert outline(_utts(5), "A talk") == no_outline()
    monkeypatch.setenv("BOTCUT_FAKE", "1")
    assert outline(_utts(40), "A talk") == no_outline()


def test_the_outline_request_carries_every_line_and_thinks_harder(live, monkeypatch):
    seen = {}
    answer = {
        "beats": [{"title": "All of it", "first": 0, "last": 7}],
        "retakes": [{"ids": [1, 6]}],
        "hook": 4,
        "target_seconds": 60,
    }

    def post(url, headers=None, json=None, timeout=None):
        seen["body"] = json
        return _Reply(answer)

    monkeypatch.setattr("botcut.net.requests.post", post)
    plan = outline(_utts(8), "A one minute update")
    assert plan == {
        "beats": [{"title": "All of it", "first": 0, "last": 7}],
        "retakes": [[1, 6]],
        "hook": 4,
        "target_seconds": 60,
    }
    body = seen["body"]
    assert body["reasoning_effort"] == "high"
    assert body["messages"][0]["content"].endswith("The movie is: A one minute update")
    rows = body["messages"][1]["content"].splitlines()
    assert rows[0] == "[0] (clip 0, 1.5s) line 0"
    assert len(rows) == 8
    assert body["response_format"]["json_schema"]["name"] == "outline"


def test_a_cut_goes_on_without_an_outline_but_not_without_a_key(live, monkeypatch, capsys):
    monkeypatch.setattr("botcut.net.requests.post", lambda *_a, **_k: _Reply("not json"))
    assert outline(_utts(8)) == no_outline()
    assert "Cutting without an outline" in capsys.readouterr().out
    monkeypatch.delenv("XAI_API_KEY")
    with pytest.raises(SystemExit, match="XAI_API_KEY is not set"):
        outline(_utts(8))


def test_the_note_names_beats_retakes_elsewhere_and_a_share_of_the_length():
    utts = _utts(10, text="say {i}")
    plan = {
        "beats": [{"title": "Start", "first": 0, "last": 4}, {"title": "End", "first": 5, "last": 9}],
        "retakes": [[1, 8], [5, 6]],
        "hook": -1,
        "target_seconds": 6,
    }
    note = outline_note(plan, utts[:5], utts)
    assert "1. Start (lines 0-4)\n2. End (lines 5-9)" in note
    assert "[1] say 1 / [8] (elsewhere) say 8" in note
    # A group with no line in this part is not this part's business.
    assert "say 5" not in note
    # Ten lines of 1.5s are 15s. Half of them are here, so half of the six seconds are.
    assert "should run about 6s. Every line together runs 15s, and the lines here run 8s" in note
    assert "keep about 3s of them" in note
    assert note.endswith("\n\n")
    assert outline_note(no_outline(), utts, utts) == ""
    assert outline_note(None, utts, utts) == ""


def test_a_retake_across_two_parts_is_shown_to_both(live, monkeypatch):
    utts = _utts(400)
    utts[20]["text"] = "we opened the shop in spring"
    utts[380]["text"] = "we opened the shop in the spring"
    plan = {"beats": [], "retakes": [[20, 380]], "hook": -1, "target_seconds": 0}
    users = []
    lock = threading.Lock()

    def post(url, headers=None, json=None, timeout=None):
        text = json["messages"][1]["content"]
        with lock:
            users.append(text)
        return _Reply({"keep": []})

    monkeypatch.setattr("botcut.net.requests.post", post)
    assert pick(utts, "A talk", plan) == []
    assert len(users) == 3
    first = next(text for text in users if "\n[20] (clip 0" in text or text.startswith("[20] "))
    last = next(text for text in users if "[399] (clip 0" in text)
    middle = next(text for text in users if text is not first and text is not last)
    assert "[20] we opened the shop in spring / [380] (elsewhere) we opened the shop in the spring" in first
    assert "[20] (elsewhere) we opened the shop in spring / [380] we opened the shop in the spring" in last
    assert "elsewhere" not in middle
    # The lines themselves still follow, in the form they always had.
    assert "\n[380] (clip 0, 760.00-761.50) we opened the shop in the spring" in last


def test_stills_go_to_retakes_first_when_there_are_too_many(monkeypatch):
    monkeypatch.setattr(picking, "MAX_STILLS", 4)
    ready = _utts(20)
    assert shown_stills(ready[:3], {1}) == ready[:3]
    shown = [u["id"] for u in shown_stills(ready, {17, 3, 18})]
    assert {3, 17, 18} <= set(shown)
    assert len(shown) == 4
    assert shown == sorted(shown)
    # With nothing to prefer, the stills are spread over the lines as before.
    assert [u["id"] for u in shown_stills(ready)] == [0, 5, 10, 15]
    # More retakes than room: the room goes to them, spread evenly.
    many = [u["id"] for u in shown_stills(ready, set(range(10)))]
    assert len(many) == 4 and max(many) < 10


def test_effort_is_per_request_or_one_for_all_and_never_sent_to_a_model_without_it(live, monkeypatch):
    assert chat_fields() == {"model": "grok-4.7", "reasoning_effort": "low"}
    assert chat_fields(effort="high") == {"model": "grok-4.7", "reasoning_effort": "high"}
    assert chat_fields(effort="enormous") == {"model": "grok-4.7", "reasoning_effort": "low"}
    assert chat_fields("grok-4.3", effort="high") == {"model": "grok-4.3"}
    monkeypatch.setenv("BOTCUT_LLM_EFFORT", "medium")
    assert chat_fields() == {"model": "grok-4.7", "reasoning_effort": "medium"}
    assert chat_fields(effort="high") == {"model": "grok-4.7", "reasoning_effort": "medium"}
    monkeypatch.setenv("BOTCUT_LLM_EFFORT", "loud")
    assert chat_fields(effort="high") == {"model": "grok-4.7", "reasoning_effort": "high"}
