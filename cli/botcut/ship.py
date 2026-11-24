"""Ship Pack: auto-generated chapter timestamps, social/Slack post drafts, thumbnail, captions, and dual-format renders."""

from __future__ import annotations

import json
import os
from pathlib import Path

from botcut import brand as brand_kit
from botcut.captions import load_words_by_clip, remap_words, to_ass, to_srt
from botcut.thumb import embed_thumbnail, make_photo_thumb


POSTS_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "ship_posts",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["x_post", "linkedin_post", "slack_summary"],
            "properties": {
                "x_post": {"type": "string"},
                "linkedin_post": {"type": "string"},
                "slack_summary": {"type": "string"},
            },
        },
    },
}

POSTS_SYSTEM = (
    "You write crisp, authentic launch and update copy from a video's final transcript and chapters. "
    "No buzzwords, no cringe hype, no hashtags unless truly needed. "
    "Return: x_post (concise X post including the chapter timestamps when present), "
    "linkedin_post (clear 2-4 short paragraphs for LinkedIn), "
    "and slack_summary (3-5 tight bullet points for an internal team update)."
)


def format_stamp(seconds: float) -> str:
    whole = max(0, int(round(seconds)))
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _line_timeline_pos(line: dict, segments: list[dict]) -> float | None:
    """Where a kept line starts on the rendered movie timeline, in seconds."""
    try:
        clip = int(line["clip"])
        lstart = float(line["start"])
        lend = float(line["end"])
    except (KeyError, TypeError, ValueError):
        return None
    cursor = 0.0
    for seg in segments or []:
        try:
            sclip = int(seg["clip"])
            sstart = float(seg["start"])
            send = float(seg["end"])
        except (KeyError, TypeError, ValueError):
            continue
        length = max(0.0, send - sstart)
        if sclip == clip and send > lstart and sstart < lend:
            offset = max(0.0, lstart - sstart)
            return cursor + offset
        cursor += length
    return None


def chapters(doc: dict) -> list[dict]:
    """Map outline beats onto the finished movie timeline as timestamped chapters."""
    segments = doc.get("segments") or []
    lines = doc.get("lines") or []
    by_id = {
        int(line["id"]): line
        for line in lines
        if isinstance(line, dict) and line.get("keep") and "id" in line
    }
    beats = (doc.get("outline") or {}).get("beats") or []
    found: list[dict] = []
    for beat in beats:
        if not isinstance(beat, dict):
            continue
        title = " ".join(str(beat.get("title") or "").split()).strip()
        if not title:
            continue
        try:
            first_id = int(beat["first"])
            last_id = int(beat.get("last", first_id))
        except (KeyError, TypeError, ValueError):
            continue
        # Find the first kept line inside this beat's id range.
        pos = None
        for uid in range(first_id, last_id + 1):
            line = by_id.get(uid)
            if line is None:
                continue
            pos = _line_timeline_pos(line, segments)
            if pos is not None:
                break
        if pos is None:
            continue
        if found and abs(pos - found[-1]["seconds"]) < 4.0:
            continue
        found.append({"seconds": round(pos, 2), "stamp": format_stamp(pos), "title": title})
    found.sort(key=lambda row: row["seconds"])
    return found


def format_chapters(rows: list[dict]) -> str:
    return "\n".join(f"{row['stamp']} {row['title']}" for row in rows) + ("\n" if rows else "")


def draft_posts(doc: dict, chapter_rows: list[dict], *, title: str = "") -> dict:
    """Draft X, LinkedIn, and Slack copy from the final kept lines and chapters."""
    kept_text = " ".join(
        str(line.get("text") or "").strip()
        for line in (doc.get("lines") or [])
        if isinstance(line, dict) and line.get("keep") and str(line.get("reason") or "") != "card"
    ).strip()
    eff_title = title.strip() or str(doc.get("title") or "").strip() or "Update"
    chap_block = format_chapters(chapter_rows).strip()

    fallback = {
        "x_post": f"{eff_title}\n\n{chap_block}".strip() if chap_block else eff_title,
        "linkedin_post": f"{eff_title}\n\n{kept_text[:600]}".strip(),
        "slack_summary": f"*{eff_title}*\n" + (
            "\n".join(f"- {r['title']} ({r['stamp']})" for r in chapter_rows)
            if chapter_rows
            else f"- {kept_text[:240]}"
        ),
    }
    if os.environ.get("BOTCUT_FAKE") == "1" or not os.environ.get("XAI_API_KEY") or not kept_text:
        return fallback

    from botcut.llm import ask

    prompt = f"Title: {eff_title}\n\nChapters:\n{chap_block or '(none)'}\n\nTranscript:\n{kept_text[:8000]}"
    try:
        return ask(
            [
                {"role": "system", "content": POSTS_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            POSTS_SCHEMA,
            what="post drafts",
            parse=lambda p: {
                "x_post": str(p["x_post"]).strip(),
                "linkedin_post": str(p["linkedin_post"]).strip(),
                "slack_summary": str(p["slack_summary"]).strip(),
            },
            read_timeout=60,
        )
    except SystemExit:
        return fallback


def make_ship_pack(
    cuts_path: str,
    out_dir: str | None = None,
    *,
    title: str = "",
    resolution: str = "1080p",
    include_portrait: bool = True,
) -> dict:
    """Build a ready-to-publish Ship Pack folder beside the project or at `out_dir`."""
    from botcut.cli import load_cuts, render_saved

    proj_dir, doc = load_cuts(cuts_path)
    eff_title = title.strip() or str(doc.get("title") or "").strip() or "video"
    safe = "".join(c if (c.isalnum() or c in " -_") else "-" for c in eff_title).strip() or "video"
    pack_dir = os.path.abspath(out_dir or os.path.join(proj_dir, f"{safe}_ship"))
    os.makedirs(pack_dir, exist_ok=True)

    # 1. Chapters + post drafts.
    chap_rows = chapters(doc)
    chap_path = os.path.join(pack_dir, "chapters.txt")
    Path(chap_path).write_text(format_chapters(chap_rows), encoding="utf-8")

    posts = draft_posts(doc, chap_rows, title=eff_title)
    posts_path = os.path.join(pack_dir, "posts.md")
    Path(posts_path).write_text(
        f"# {eff_title}\n\n"
        f"## X Post\n\n{posts['x_post']}\n\n"
        f"## LinkedIn\n\n{posts['linkedin_post']}\n\n"
        f"## Slack / Internal Summary\n\n{posts['slack_summary']}\n",
        encoding="utf-8",
    )

    # 2. Matt-style landscape thumbnail.
    thumb_path = os.path.join(pack_dir, "thumb_landscape.jpg")
    make_photo_thumb(cuts_path, title=eff_title, out_jpg=thumb_path, aspect="landscape", embed=False)

    # 3. Landscape master render directly from originals + embed cover poster.
    land_mp4 = os.path.join(pack_dir, f"video_{resolution}.mp4")
    render_saved(cuts_path, resolution=resolution, aspect="landscape", out_file=land_mp4)
    if os.path.isfile(thumb_path) and os.path.isfile(land_mp4):
        embed_thumbnail(land_mp4, thumb_path)

    # 4. Portrait master render (optional, default on).
    port_mp4 = None
    if include_portrait:
        port_mp4 = os.path.join(pack_dir, f"video_portrait_{resolution}.mp4")
        render_saved(cuts_path, resolution=resolution, aspect="portrait", out_file=port_mp4)

    # 5. SRT & social ASS captions (when speech transcript exists).
    srt_path = None
    ass_path = None
    try:
        mapped = remap_words(doc.get("segments") or [], load_words_by_clip(doc, proj_dir))
        if mapped:
            srt_path = os.path.join(pack_dir, "captions.srt")
            Path(srt_path).write_text(to_srt(mapped), encoding="utf-8")
            kit = brand_kit.load_brand()
            ass_path = os.path.join(pack_dir, "captions_portrait.ass")
            Path(ass_path).write_text(to_ass(mapped, width=1080, height=1920, brand=kit), encoding="utf-8")
    except SystemExit:
        pass

    return {
        "dir": pack_dir,
        "chapters": chap_path,
        "posts": posts_path,
        "thumb": thumb_path,
        "landscape": land_mp4,
        "portrait": port_mp4,
        "srt": srt_path,
        "ass": ass_path,
    }
