"""POST to xAI. A blip is retried. The key stays out of errors and logs."""

from __future__ import annotations

import time
from collections.abc import Callable

import requests

RETRY_STATUS = {408, 429, 500, 502, 503, 504}
RETRY_DELAYS = (1.0, 2.0, 4.0)
CONNECT_TIMEOUT = 10.0
MAX_RETRY_AFTER = 30.0


def post(
    url: str,
    *,
    key: str,
    label: str,
    read_timeout: float,
    send: Callable[[], dict],
) -> requests.Response:
    """Return the 200 response. `send` is called on every try, so an upload can be reopened."""
    delays = list(RETRY_DELAYS)
    read_timeouts_left = 1
    while True:
        kwargs = send()
        try:
            try:
                response = requests.post(url, timeout=(CONNECT_TIMEOUT, read_timeout), **kwargs)
            except requests.Timeout:
                if read_timeouts_left <= 0 or not delays:
                    raise SystemExit(f"{label} timed out")
                read_timeouts_left -= 1
                _again(delays.pop(0), None)
                continue
            except requests.RequestException:
                if not delays:
                    raise SystemExit(f"{label} connection failed")
                _again(delays.pop(0), None)
                continue
        finally:
            _close_uploads(kwargs.get("files"))

        if response.status_code == 200:
            return response
        if response.status_code in RETRY_STATUS and delays:
            _again(delays.pop(0), response)
            continue
        raise SystemExit(f"{label} HTTP {response.status_code}: {_safe_body(response.text, key)}")


KEY_REJECTED = {400, 401, 403}
KEY_READ_TIMEOUT = 15.0


def check_key(base_url: str, key: str) -> None:
    """Ask xAI for its model list. Returns when the key is accepted, and says why when not."""
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=(CONNECT_TIMEOUT, KEY_READ_TIMEOUT),
        )
    except requests.RequestException:
        raise SystemExit("Could not reach xAI to check the key.")
    if response.status_code == 200:
        return
    if response.status_code in KEY_REJECTED:
        raise SystemExit("xAI did not accept that key.")
    raise SystemExit("Could not reach xAI to check the key.")


def _again(default: float, response: requests.Response | None) -> None:
    print("Trying again", flush=True)
    time.sleep(_delay(default, response))


def _delay(default: float, response: requests.Response | None) -> float:
    if response is None:
        return default
    raw = str(response.headers.get("Retry-After") or "").strip()
    try:
        return min(MAX_RETRY_AFTER, max(0.0, float(raw)))
    except ValueError:
        return default


def _safe_body(text: str, key: str) -> str:
    return text.replace(key, "[redacted]")[:300]


def _close_uploads(files) -> None:
    if not files:
        return
    for item in files:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        payload = item[1]
        handle = payload[1] if isinstance(payload, tuple) and len(payload) >= 2 else payload
        close = getattr(handle, "close", None)
        if callable(close):
            close()
