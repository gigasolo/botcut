"""The bench: finished cuts as cases, scored and replayed."""

import json

import pytest

from botcut import bench, llm
from botcut.pick import decision_lines, utterances


def _words(*rows):
    return [{"text": text, "start": start, "end": end} for text, start, end in rows]


SAID = _words(
    ("Take", 0.0, 0.3), ("one.", 0.3, 0.8),
    ("So", 2.0, 2.2), ("um", 2.4, 2.8), ("this", 3.0, 3.3), ("works.", 3.3, 3.9),
    ("Bye", 6.0, 6.4), ("now.", 6.4, 7.0),
)


def _project(tmp_path, keep=(1, 2), cut_um=True):
    """A finished cut on disk: the person kept lines 1 and 2 and took the um out."""
    out = tmp_path / "project"
    (out / "work" / "stills").mkdir(parents=True)
    (out / "work" / "0-talk.xai.words.json").write_text(json.dumps({"duration": 8.0, "words": SAID}))
    (out / "work" / "0-talk.silences.json").write_text("[]")
    (out / "work" / "stills" / "1.jpg").write_bytes(b"jpeg")
    utts = utterances([SAID])
    lines = decision_lines(utts, [{"id": uid, "reason": "mine", "cuts": [0] if cut_um else []} for uid in keep])
    doc = {
        "version": 1,
        "stt": "xai:grok-voice-transcribe-2.0",
        "intent": "A short talk",
        "clips": [{"index": 0, "path": "/tmp/talk.mp4", "duration": 8.0}],
        "lines": lines,
    }
    (out / "cuts.json").write_text(json.dumps(doc))
    return out


@pytest.fixture
def data(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("BOTCUT_FAKE", raising=False)
    monkeypatch.delenv("BOTCUT_PRICE_IN", raising=False)
    monkeypatch.delenv("BOTCUT_PRICE_OUT", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "secret")
    yield tmp_path
    llm.use_tape(None)


class _Reply:
    status_code = 200
    text = ""

    def __init__(self, keep, usage=None):
        self._keep, self._usage = keep, usage

    def json(self):
        body = {"choices": [{"message": {"content": json.dumps({"keep": self._keep})}}]}
        if self._usage:
            body["usage"] = self._usage
        return body


def test_a_finished_cut_is_saved_as_a_case_with_what_was_heard(data, capsys):
    out = _project(data)
    bench.save(str(out), "talk")
    case = data / "data" / "botcut" / "bench" / "talk"
    assert sorted(p.name for p in (case / "work").iterdir()) == [
        "0-talk.silences.json", "0-talk.xai.words.json", "stills",
    ]
    assert (case / "work" / "stills" / "1.jpg").exists()
    assert "Saved case talk: 2 of 3 lines kept" in capsys.readouterr().out
    assert bench.case_names() == ["talk"]
    with pytest.raises(SystemExit, match="already a case"):
        bench.save(str(out), "talk")
    with pytest.raises(SystemExit, match="Not a case name"):
        bench.save(str(out), "../escape")

    # A case can be saved by naming the movie. Its project is looked up.
    project = data / "data" / "botcut" / "projects" / "20261115-120000-000"
    project.parent.mkdir(parents=True)
    out.rename(project)
    (project / "project.json").write_text(json.dumps({"movie": str(data / "ride.mp4")}))
    bench.save(str(data / "ride.mp4"), "ride")
    assert bench.case_names() == ["ride", "talk"]
    with pytest.raises(SystemExit, match="No project was found"):
        bench.save(str(data / "other.mp4"), "other")


def test_lines_are_compared_by_how_long_they_are_not_how_many():
    utts = utterances([SAID])
    want = decision_lines(utts, [{"id": 1, "reason": "x", "cuts": [0]}, {"id": 2, "reason": "x"}])
    # The model kept the short first line and the long middle one, and left the um in.
    got = decision_lines(utts, [{"id": 0, "reason": "y"}, {"id": 1, "reason": "y"}])
    result = bench.compare(want, got)
    assert result["flipped"] == 2
    assert result["precision"] == pytest.approx(1.9 / 2.7, abs=0.001)
    assert result["recall"] == pytest.approx(1.9 / 2.9, abs=0.001)
    assert (result["cuts_same"], result["cuts_offered"]) == (0, 1)
    same = bench.compare(want, want)
    assert (same["precision"], same["recall"], same["flipped"]) == (1.0, 1.0, 0)
    assert (same["cuts_same"], same["cuts_offered"]) == (1, 1)


def test_a_run_scores_counts_tokens_and_says_what_changed_since_last_time(data, monkeypatch, capsys):
    bench.save(str(_project(data)), "talk")
    answers = [
        [{"id": 1, "reason": "ok", "cuts": [0]}, {"id": 2, "reason": "ok", "cuts": []}],
        [{"id": 0, "reason": "ok", "cuts": []}, {"id": 1, "reason": "ok", "cuts": []}],
    ]
    sent = []

    def post(url, headers=None, json=None, timeout=None):
        sent.append(json)
        return _Reply(answers.pop(0), {"prompt_tokens": 900, "completion_tokens": 100})

    monkeypatch.setattr("botcut.net.requests.post", post)
    first = bench.run([])
    assert first["cases"]["talk"]["precision"] == 1.0
    assert first["cases"]["talk"]["tokens"] == 1000
    # The saved still went with the line, as it does in a real cut.
    assert any(part.get("type") == "image_url" for part in sent[0]["messages"][1]["content"])
    out = capsys.readouterr().out
    assert "talk: precision 1.00, recall 1.00, flipped 0 of 3, cuts 1/1, 1,000 tokens" in out
    assert "(was" not in out
    # Line 1 opens on "So" with the line before it dropped, and taking its um out leaves
    # "So" as a piece of half a second. Both are in the model's cut and in the person's.
    assert first["cases"]["talk"]["flags"] == {"leans": 1, "flash": 1}
    assert first["cases"]["talk"]["want_flags"] == {"leans": 1, "flash": 1}
    assert "flags leans 1, flash 1 (yours leans 1, flash 1)" in out
    assert "flipped 0 of 3, 2 flags" in out

    second = bench.run(["talk"])
    assert second["overall"]["flipped"] == 2
    assert second["cases"]["talk"]["flags"] == {}
    out = capsys.readouterr().out
    assert "flags none (yours leans 1, flash 1)" in out
    assert "(was 1.00, 1.00, 0, 2 flags with prompt" in out
    history = (data / "data" / "botcut" / "bench" / "history.jsonl").read_text().splitlines()
    assert len(history) == 2
    assert json.loads(history[0])["prompt"] == bench.prompt_version()


def test_a_recorded_answer_replays_with_no_network_until_the_prompt_changes(data, monkeypatch):
    bench.save(str(_project(data)), "talk")
    monkeypatch.setattr(
        "botcut.net.requests.post",
        lambda *_a, **_k: _Reply([{"id": 1, "reason": "ok", "cuts": [0]}, {"id": 2, "reason": "ok", "cuts": []}]),
    )
    live = bench.score("talk")

    def no_network(*_a, **_k):
        raise AssertionError("a replay must not call out")

    monkeypatch.setattr("botcut.net.requests.post", no_network)
    monkeypatch.delenv("XAI_API_KEY")
    replayed = bench.score("talk", replay=True)
    assert (replayed["precision"], replayed["flipped"]) == (live["precision"], live["flipped"])
    assert replayed["tokens"] == 0

    # Different wording is a different question. An old answer is not passed off as its answer.
    monkeypatch.setattr("botcut.pick.STORY_PROMPT", "Keep everything.")
    with pytest.raises(SystemExit, match="The prompt changed"):
        bench.score("talk", replay=True)


def test_usage_is_one_sentence_and_dollars_only_when_prices_are_given(monkeypatch):
    monkeypatch.delenv("BOTCUT_PRICE_IN", raising=False)
    monkeypatch.delenv("BOTCUT_PRICE_OUT", raising=False)
    llm.reset_usage()
    llm._count({"prompt_tokens": 12000, "completion_tokens": 340})
    llm._count(None)
    tally = llm.usage()
    assert (tally["requests"], tally["input"], tally["output"]) == (2, 12000, 340)
    assert llm.usage_line(tally) == "Used 12,340 tokens in 2 requests."
    monkeypatch.setenv("BOTCUT_PRICE_IN", "3")
    monkeypatch.setenv("BOTCUT_PRICE_OUT", "15")
    assert llm.usage_line(llm.usage()) == "Used 12,340 tokens in 2 requests, about $0.04."
    llm.reset_usage()
    assert llm.usage_line(llm.usage()) == ""


def test_compare_guards_zero_duration_lines():
    want = [{"id": 0, "start": 1.0, "end": 1.0, "keep": True}]
    got = [{"id": 0, "start": 1.0, "end": 1.0, "keep": True}]
    result = bench.compare(want, got)
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
