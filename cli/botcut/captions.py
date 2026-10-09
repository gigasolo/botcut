"""Map source words onto the rough cut and write an SRT."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


FORCE_STYLE = "FontName=Inter,FontSize=18,Bold=1,Outline=2,Shadow=0,Alignment=2,MarginV=40"
MAX_CHARS = 32
MAX_DUR = 2.0
CUE_GAP = 0.4


def word_cache_candidates(work: str, index: int, stem: str, backend: str) -> list[str]:
    names = [f"{index}-{stem}.{backend}.words.json"]
    if backend == "xai":
        names.append(f"{index}-{stem}.words.json")
    return [os.path.join(work, name) for name in names]


def stt_backend(stt: str) -> str:
    if stt == "fake":
        return "fake"
    if stt.startswith("local:"):
        return "local"
    return "xai"


def load_words_by_clip(doc: dict, out_dir: str) -> list[list[dict]]:
    clips = doc.get("clips") or []
    if not clips:
        raise SystemExit("cuts.json has no clips")
    backend = stt_backend(str(doc.get("stt") or ""))
    work = os.path.join(out_dir, "work")
    by_index: dict[int, list[dict]] = {}
    for clip in clips:
        index = int(clip["index"])
        stem = Path(clip["path"]).stem
        candidates = word_cache_candidates(work, index, stem, backend)
        found = next((path for path in candidates if os.path.isfile(path)), None)
        if found is None:
            raise SystemExit(f"No word cache: {candidates[0]}")
        by_index[index] = read_words(found)
    last = max(by_index)
    return [by_index.get(i, []) for i in range(last + 1)]


def read_words(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text())
    rows = data if isinstance(data, list) else (data.get("words") or [])
    words = []
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        words.append({"text": text, "start": float(row["start"]), "end": float(row["end"])})
    return words


def remap_words(segments: list[dict], words_by_clip: list[list[dict]]) -> list[dict]:
    mapped = []
    timeline = 0.0
    for seg in segments:
        start = float(seg["start"])
        end = float(seg["end"])
        length = max(0.0, end - start)
        clip = int(seg["clip"])
        words = words_by_clip[clip] if 0 <= clip < len(words_by_clip) else []
        for word in words:
            wstart = float(word["start"])
            if not (start <= wstart < end):
                continue
            text = str(word["text"]).strip()
            if not text:
                continue
            mapped_start = timeline + (wstart - start)
            mapped_end = timeline + (float(word["end"]) - start)
            mapped_end = min(mapped_end, timeline + length)
            if mapped_end < mapped_start:
                mapped_end = mapped_start
            if mapped_start < 0:
                mapped_start = 0.0
            mapped.append({"text": text, "start": mapped_start, "end": mapped_end})
        timeline += length
    return mapped


def group_cues(
    words: list[dict],
    max_chars: int = MAX_CHARS,
    max_dur: float = MAX_DUR,
    gap: float = CUE_GAP,
) -> list[dict]:
    cues: list[dict] = []
    current: list[dict] = []

    def flush() -> None:
        if not current:
            return
        start = float(current[0]["start"])
        end = min(float(current[-1]["end"]), start + max_dur)
        if end < start:
            end = start
        cues.append({"text": " ".join(str(word["text"]) for word in current), "start": start, "end": end})
        current.clear()

    for word in words:
        if not current:
            current.append(word)
            continue
        pause = float(word["start"]) - float(current[-1]["end"])
        joined = " ".join(str(item["text"]) for item in current) + " " + str(word["text"])
        dur = float(word["end"]) - float(current[0]["start"])
        if pause > gap or len(joined) > max_chars or dur > max_dur:
            flush()
        current.append(word)
    flush()
    return cues


def to_srt(words: list[dict], max_chars: int = MAX_CHARS, max_dur: float = MAX_DUR) -> str:
    lines = []
    for index, cue in enumerate(group_cues(words, max_chars=max_chars, max_dur=max_dur), start=1):
        lines.append(str(index))
        lines.append(f"{srt_time(cue['start'])} --> {srt_time(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")
    return "\n".join(lines)


def srt_time(seconds: float) -> str:
    millis = int(round(max(0.0, seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def subtitles_filter(srt_name: str) -> str:
    return f"subtitles={srt_name}:force_style='{FORCE_STYLE}'"


def burn_args(encoder: str = "x264", device: str | None = None) -> list[str]:
    if encoder not in ("x264", "vaapi"):
        raise SystemExit(f"Unknown encoder {encoder}")
    if encoder == "vaapi" and not device:
        raise SystemExit("VA-API encode needs a device")
    if encoder == "vaapi":
        # Libass draws on software frames. Decode and encode stay on the GPU.
        video_filter = f"hwdownload,format=nv12,{subtitles_filter('rough_cut.srt')},format=nv12,hwupload"
        return [
            "-y",
            "-init_hw_device",
            f"vaapi=va:{device}",
            "-filter_hw_device",
            "va",
            "-hwaccel",
            "vaapi",
            "-hwaccel_device",
            str(device),
            "-hwaccel_output_format",
            "vaapi",
            "-i",
            "rough_cut.mp4",
            "-vf",
            video_filter,
            "-c:v",
            "h264_vaapi",
            "-qp",
            "20",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            "rough_cut.captioned.mp4",
        ]
    return [
        "-y",
        "-i",
        "rough_cut.mp4",
        "-vf",
        subtitles_filter("rough_cut.srt"),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        "rough_cut.captioned.mp4",
    ]


def ffmpeg_has_filter(name: str) -> bool:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
    )
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == name:
            return True
    return False


def require_subtitles() -> None:
    if not ffmpeg_has_filter("subtitles"):
        raise SystemExit("ffmpeg was built without the subtitles filter (libass)")
