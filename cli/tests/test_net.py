import requests

from botcut.net import post


class _Response:
    def __init__(self, status, headers=None, text=""):
        self.status_code = status
        self.headers = headers or {}
        self.text = text


def _patch_post(monkeypatch, func):
    monkeypatch.setattr("botcut.net.requests.post", func)
    monkeypatch.setattr("botcut.net.time.sleep", lambda _seconds: None)


def test_connection_error_is_retried_then_succeeds(monkeypatch, capsys):
    calls = {"n": 0}
    sends = {"n": 0}

    def fake_post(url, timeout=None, **_kwargs):
        calls["n"] += 1
        assert timeout == (10.0, 300)
        if calls["n"] == 1:
            raise requests.ConnectionError("down")
        return _Response(200)

    def send():
        sends["n"] += 1
        return {"headers": {"Authorization": "Bearer supersecret"}}

    _patch_post(monkeypatch, fake_post)
    response = post("https://example.test", key="supersecret", label="STT", read_timeout=300, send=send)
    assert response.status_code == 200
    assert calls["n"] == 2
    assert sends["n"] == 2
    out = capsys.readouterr().out
    assert "Trying again" in out
    assert "supersecret" not in out


def test_http_500_is_retried_and_400_is_not(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, timeout=None, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Response(500, text="busy supersecret")
        return _Response(200)

    _patch_post(monkeypatch, fake_post)
    response = post(
        "https://example.test",
        key="supersecret",
        label="LLM",
        read_timeout=120,
        send=lambda: {"json": {}},
    )
    assert response.status_code == 200
    assert calls["n"] == 2

    calls["n"] = 0

    def rejected(url, timeout=None, **_kwargs):
        calls["n"] += 1
        return _Response(400, text="nope supersecret")

    monkeypatch.setattr("botcut.net.requests.post", rejected)
    try:
        post(
            "https://example.test",
            key="supersecret",
            label="STT",
            read_timeout=300,
            send=lambda: {"json": {}},
        )
    except SystemExit as exc:
        assert calls["n"] == 1
        assert "STT HTTP 400" in str(exc)
        assert "supersecret" not in str(exc)
        assert "[redacted]" in str(exc)
    else:
        raise AssertionError("400 should fail once")


def test_read_timeout_is_retried_once(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, timeout=None, **_kwargs):
        calls["n"] += 1
        raise requests.Timeout("slow")

    _patch_post(monkeypatch, fake_post)
    try:
        post(
            "https://example.test",
            key="supersecret",
            label="STT",
            read_timeout=300,
            send=lambda: {},
        )
    except SystemExit as exc:
        assert str(exc) == "STT timed out"
        assert calls["n"] == 2
    else:
        raise AssertionError("timeout should fail")


def test_retry_after_is_capped_at_thirty_seconds(monkeypatch):
    sleeps = []
    calls = {"n": 0}

    def fake_post(url, timeout=None, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Response(429, headers={"Retry-After": "120"})
        return _Response(200)

    monkeypatch.setattr("botcut.net.requests.post", fake_post)
    monkeypatch.setattr("botcut.net.time.sleep", lambda seconds: sleeps.append(seconds))
    post(
        "https://example.test",
        key="supersecret",
        label="LLM",
        read_timeout=120,
        send=lambda: {},
    )
    assert sleeps == [30.0]
