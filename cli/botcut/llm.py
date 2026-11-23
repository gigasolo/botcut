"""One way to ask the model a question.

Every request is a list of messages and a strict JSON shape for the answer.
This is the only place that knows the endpoint, counts tokens, and can record
a real answer or play one back.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path

from botcut.net import post

_MALFORMED = (ValueError, KeyError, TypeError, IndexError, AttributeError)
_lock = threading.Lock()
_usage = {"requests": 0, "input": 0, "output": 0}
_tape: "Tape | None" = None


def model_name() -> str:
    return os.environ.get("BOTCUT_LLM_MODEL") or "grok-4.7"


def reasoning_effort(model: str) -> str | None:
    """Low effort for Grok 4.5 and newer. Older chat models omit the field."""
    name = model.split("/")[-1]
    if not name.startswith("grok-4."):
        return None
    minor = name.removeprefix("grok-4.").split("-", 1)[0]
    if minor.isdigit() and int(minor) >= 5:
        return "low"
    return None


EFFORTS = ("low", "medium", "high", "xhigh")


def chat_fields(model: str | None = None, effort: str | None = None) -> dict:
    """The model, and how hard it should think when it takes that setting.

    A request may ask for more than the usual low effort: reading the whole
    shoot is worth it, choosing a face box is not. BOTCUT_LLM_EFFORT sets one
    effort for every request, so the bench can price the difference.
    """
    chosen = model_name() if model is None else model
    fields: dict = {"model": chosen}
    usual = reasoning_effort(chosen)
    if usual:
        forced = (os.environ.get("BOTCUT_LLM_EFFORT") or "").strip().lower()
        if forced in EFFORTS:
            usual = forced
        elif effort in EFFORTS:
            usual = effort
        fields["reasoning_effort"] = usual
    return fields


def llm_url() -> str:
    base = os.environ.get("BOTCUT_LLM_BASE_URL") or "https://api.x.ai/v1"
    return base.rstrip("/") + "/chat/completions"


def ask(
    messages: list[dict],
    schema: dict,
    *,
    what: str,
    parse: Callable[[object], object] | None = None,
    read_timeout: float = 120,
    tries: int = 1,
    effort: str | None = None,
):
    """Ask once and return the answer, read by `parse` when one is given.

    `what` names the answer for the person: "a keep list". An answer that is
    not JSON, or that `parse` cannot read, is asked for again up to `tries`
    times, and then the job stops with "LLM response was not <what>".
    `effort` asks for more thought than usual on this one request.
    """
    tape = _tape
    if tape is not None and tape.replay:
        content = tape.read(what, messages)
        try:
            payload = json.loads(content)
            return parse(payload) if parse else payload
        except _MALFORMED:
            raise SystemExit(f"LLM response was not {what}")
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")
    body = {**chat_fields(effort=effort), "messages": messages, "response_format": schema}
    for attempt in range(max(1, tries)):
        response = post(
            llm_url(),
            key=key,
            label="LLM",
            read_timeout=read_timeout,
            send=lambda: {
                "headers": {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                "json": body,
            },
        )
        try:
            answer = response.json()
            _count(answer.get("usage") if isinstance(answer, dict) else None)
            content = answer["choices"][0]["message"]["content"]
            payload = json.loads(content)
            result = parse(payload) if parse else payload
        except _MALFORMED:
            if attempt + 1 < max(1, tries):
                print("Trying again", flush=True)
            continue
        if tape is not None:
            tape.write(what, messages, content)
        return result
    raise SystemExit(f"LLM response was not {what}")


def _count(usage) -> None:
    with _lock:
        _usage["requests"] += 1
        if not isinstance(usage, dict):
            return
        for ours, theirs in (("input", "prompt_tokens"), ("output", "completion_tokens")):
            value = usage.get(theirs)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                _usage[ours] += value


def usage() -> dict:
    """Requests and tokens since the last reset, and the cost when the prices are known."""
    with _lock:
        tally = dict(_usage)
    tally["model"] = model_name()
    cost = _cost(tally["input"], tally["output"])
    if cost is not None:
        tally["usd"] = cost
    return tally


def reset_usage() -> None:
    with _lock:
        for name in _usage:
            _usage[name] = 0


def _cost(tokens_in: int, tokens_out: int) -> float | None:
    """Dollars, from BOTCUT_PRICE_IN and BOTCUT_PRICE_OUT per million tokens.

    Prices change and are not written into the program. With neither set, only
    tokens are reported.
    """
    try:
        price_in = float(os.environ["BOTCUT_PRICE_IN"])
        price_out = float(os.environ["BOTCUT_PRICE_OUT"])
    except (KeyError, ValueError):
        return None
    return round((tokens_in * price_in + tokens_out * price_out) / 1_000_000, 4)


def usage_line(tally: dict) -> str:
    """One sentence for the person: 'Used 12,340 tokens in 3 requests, about $0.04.'"""
    tokens = int(tally.get("input", 0)) + int(tally.get("output", 0))
    requests = int(tally.get("requests", 0))
    if requests <= 0:
        return ""
    asked = "1 request" if requests == 1 else f"{requests} requests"
    line = f"Used {tokens:,} tokens in {asked}"
    if "usd" in tally:
        line += f", about ${float(tally['usd']):.2f}"
    return line + "."


class Tape:
    """Real answers kept beside a bench case, to score against or to play back offline.

    An answer is filed under the question that got it. A changed prompt is a
    different question, so a replay of it is refused instead of answered wrongly.
    """

    def __init__(self, directory: str, replay: bool = False):
        self.directory = directory
        self.replay = replay

    def _path(self, what: str, messages: list[dict]) -> str:
        digest = hashlib.sha1(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]
        slug = re.sub(r"[^a-z0-9]+", "-", what.lower()).strip("-") or "answer"
        return os.path.join(self.directory, f"{slug}-{digest}.json")

    def write(self, what: str, messages: list[dict], content: str) -> None:
        os.makedirs(self.directory, exist_ok=True)
        Path(self._path(what, messages)).write_text(json.dumps({"what": what, "content": content}) + "\n")

    def read(self, what: str, messages: list[dict]) -> str:
        path = self._path(what, messages)
        try:
            return str(json.loads(Path(path).read_text())["content"])
        except (OSError, ValueError, KeyError):
            raise SystemExit(
                f"No recorded answer for {what}. The prompt changed since it was recorded, "
                "so this needs a real run."
            )


def use_tape(tape: Tape | None) -> None:
    global _tape
    _tape = tape
