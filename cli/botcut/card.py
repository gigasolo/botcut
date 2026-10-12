"""A title card is its own shot: one generated still, held for three seconds.

The filename starts with botcut-card- so a later spoken cut can see the marker
on the tray path. That shot is not sent to speech-to-text or the keep model.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import tempfile
import urllib.parse

import requests

from botcut.net import post

CARD_PREFIX = "botcut-card-"
_CARD_NAME = re.compile(r"^botcut-card-[A-Za-z0-9][A-Za-z0-9_-]*\.mp4$")
IMAGE_URL = "https://api.x.ai/v1/images/generations"
IMAGE_MODEL = "grok-imagine-image-2.0"
_REDIRECTS = {301, 302, 303, 307, 308}


def is_card(path: str) -> bool:
    return os.path.basename(path).startswith(CARD_PREFIX)


def card_dir() -> str:
    """Where a card mp4 lives so a saved list can open it after a restart."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.abspath(os.path.join(base, "botcut", "cards"))


def make_card(sentence: str, dest: str) -> None:
    text = _sentence(sentence)
    path = _dest(dest)
    # Fake mode never checks the key and never opens a socket.
    if os.environ.get("BOTCUT_FAKE") == "1":
        _encode(_fake_args(text), path)
        print(f"Wrote {path}", flush=True)
        return
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")
    response = post(
        IMAGE_URL,
        key=key,
        label="Image",
        read_timeout=120,
        send=lambda: {
            "headers": {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            "json": {
                "model": IMAGE_MODEL,
                "prompt": text,
                "n": 1,
                "aspect_ratio": "16:9",
                "response_format": "url",
            },
        },
    )
    try:
        payload = response.json()
    except ValueError:
        raise SystemExit("Image response had no picture") from None
    url = _picture_url(payload)
    # Not named botcut-card-: a leftover still must not look like a shot.
    handle, image = tempfile.mkstemp(prefix="botcut-still-", suffix=".jpg")
    os.close(handle)
    try:
        _download(url, image)
        _encode(_still_args(image, text), path)
    finally:
        _remove(image)
    print(f"Wrote {path}", flush=True)


def card_sentence(path: str, fallback: str) -> str:
    """The sentence stored on the card, or the movie sentence when it has none."""
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format_tags=comment",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(proc.stdout or "{}")
        text = str(((data.get("format") or {}).get("tags") or {}).get("comment") or "").strip()
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, TypeError, ValueError):
        return fallback
    return text or fallback


def merge_cards(
    lines: list[dict], segments: list[dict], clips: list[dict], sentence: str
) -> tuple[list[dict], list[dict]]:
    """One kept line and one segment for each card, spanning that whole shot.

    Segments are added after silence tightening so a card is not cut apart.
    """
    next_id = 0
    for line in lines:
        try:
            next_id = max(next_id, int(line["id"]) + 1)
        except (KeyError, TypeError, ValueError):
            continue
    rows = list(lines)
    segs = [seg for seg in segments if not _segment_is_card(clips, seg.get("clip"))]
    for index, clip in enumerate(clips):
        path = str(clip.get("path") or "")
        if not is_card(path):
            continue
        try:
            dur = float(clip.get("duration") or 0)
        except (TypeError, ValueError):
            continue
        if dur <= 0:
            continue
        rows.append(
            {
                "id": next_id,
                "clip": index,
                "start": 0.0,
                "end": dur,
                "text": card_sentence(path, sentence),
                "keep": True,
                "reason": "card",
            }
        )
        segs.append({"clip": index, "start": 0.0, "end": dur, "reason": "card"})
        next_id += 1
    rows.sort(key=lambda row: (int(row["clip"]), float(row["start"]), int(row["id"])))
    segs.sort(key=lambda seg: (int(seg["clip"]), float(seg["start"])))
    return rows, segs


def _sentence(text: str) -> str:
    collapsed = " ".join(str(text).split())
    if not collapsed:
        raise SystemExit("Say what the card says")
    return collapsed


def _ensure_card_dir() -> str:
    path = card_dir()
    parent = os.path.dirname(path)
    try:
        os.makedirs(parent, mode=0o700, exist_ok=True)
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    except OSError:
        raise SystemExit("No card directory") from None
    try:
        info = os.lstat(path)
    except OSError:
        raise SystemExit("No card directory") from None
    # A symlink, or a directory someone else can write, would let ffmpeg follow a planted partial.
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise SystemExit("No card directory")
    if info.st_uid != os.getuid() or not (info.st_mode & stat.S_IWUSR) or info.st_mode & 0o022:
        raise SystemExit("No card directory")
    return os.path.realpath(path)


def _dest(path: str) -> str:
    directory = _ensure_card_dir()
    raw = os.path.abspath(path)
    if os.path.islink(raw):
        raise SystemExit("No card file")
    dest = os.path.realpath(raw)
    if not _CARD_NAME.fullmatch(os.path.basename(dest)):
        raise SystemExit("Card file must start with botcut-card-")
    if os.path.dirname(dest) != directory:
        raise SystemExit("No card file")
    return dest


def _https_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urllib.parse.urlparse(url.strip())
    return parsed.scheme == "https" and bool(parsed.hostname)


def _picture_url(payload: object) -> str:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise SystemExit("Image response had no picture")
    url = data[0].get("url")
    # Parsed scheme, not a prefix: only an https URL from the API.
    if not _https_url(url):
        raise SystemExit("Image response had no picture")
    return str(url).strip()


def _download(url: str, dest: str) -> None:
    # Follow a redirect only while that hop is still https. No Authorization header.
    current = url
    payload = b""
    for _hop in range(6):
        if not _https_url(current):
            raise SystemExit("Could not download the card")
        try:
            response = requests.get(current, timeout=(10, 120), allow_redirects=False)
        except requests.RequestException:
            raise SystemExit("Could not download the card") from None
        try:
            if response.status_code in _REDIRECTS:
                location = response.headers.get("Location")
                if not isinstance(location, str) or not location.strip():
                    raise SystemExit("Could not download the card")
                current = urllib.parse.urljoin(current, location.strip())
                continue
            if response.status_code != 200 or not response.content:
                raise SystemExit("Could not download the card")
            payload = bytes(response.content)
            break
        finally:
            closer = getattr(response, "close", None)
            if callable(closer):
                closer()
    else:
        raise SystemExit("Could not download the card")
    try:
        with open(dest, "wb") as handle:
            handle.write(payload)
    except OSError:
        _remove(dest)
        raise SystemExit("Could not download the card") from None


def _fake_args(sentence: str) -> list[str]:
    return [
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=160x90:d=0.2",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo",
        "-t",
        "0.2",
        *_common_args(sentence),
    ]


def _still_args(image: str, sentence: str) -> list[str]:
    return [
        "-loop",
        "1",
        "-i",
        image,
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo",
        "-t",
        "3",
        *_common_args(sentence),
    ]


def _common_args(sentence: str) -> list[str]:
    # Silent audio: the cut pipeline refuses a file with no audio stream.
    return [
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        "-metadata",
        f"comment={sentence}",
    ]


def _partial(dest: str) -> str:
    # A dot name so a half-written file is not a botcut-card- shot. O_NOFOLLOW
    # so ffmpeg is never handed a symlink planted at that path.
    partial = os.path.join(os.path.dirname(dest), "." + os.path.basename(dest) + ".part")
    try:
        fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
    except OSError:
        raise SystemExit("Could not make the card") from None
    os.close(fd)
    return partial


def _encode(args: list[str], dest: str) -> None:
    partial = _partial(dest)
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *args, "-f", "mp4", partial],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        _remove(partial)
        raise SystemExit("ffmpeg was not found") from None
    if proc.returncode != 0 or not os.path.isfile(partial) or os.path.getsize(partial) == 0:
        _remove(partial)
        raise SystemExit("Could not make the card")
    os.replace(partial, dest)


def _segment_is_card(clips: list[dict], clip: object) -> bool:
    try:
        index = int(clip)
    except (TypeError, ValueError):
        return False
    if index < 0 or index >= len(clips):
        return False
    return is_card(str(clips[index].get("path") or ""))


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        return
