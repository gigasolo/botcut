"""botcut-cli: transcribe, pick takes, revise a cut, make a card, render a rough cut."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from botcut import net
from botcut.broll import beats_from_cuts, choose_covers, fake_beats, is_broll
from botcut.card import is_card, make_card, merge_cards
from botcut.captions import (
    burn_args,
    load_words_by_clip,
    remap_words,
    require_subtitles,
    to_srt,
    word_cache_candidates,
)
from botcut.media import (
    extract_audio,
    probe,
    render_with_progress,
    resolve_encoder,
    scene_changes,
    silences,
)
from botcut.pick import (
    DEFAULT_INTENT,
    cut_words,
    decision_lines,
    dropped_utterances,
    kept_utterances,
    model_name,
    pick,
    segments,
    snap,
    tighten,
    unique_warnings,
    unknown_warnings,
    utterances,
)
from botcut.revise import apply_proposal, revise
from botcut.short import highlight_span, kept_on_cut, pick_highlight, short_args
from botcut.stt import transcribe_fake, transcribe_local, transcribe_xai


# Shots sent to the transcriber at once, and stills grabbed at once.
TRANSCRIBE_WORKERS = 4
STILL_WORKERS = 4


def check_key() -> None:
    """Exit 0 when xAI accepts the key. BOTCUT_FAKE accepts any key, offline."""
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise SystemExit("XAI_API_KEY is not set")
    if os.environ.get("BOTCUT_FAKE") != "1":
        net.check_key(os.environ.get("BOTCUT_LLM_BASE_URL") or "https://api.x.ai/v1", key)
    print("Key works", flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="botcut-cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="transcribe shots and render a rough cut")
    run_p.add_argument("files", nargs="+", help="shot files in order, or one .txt list")
    run_p.add_argument("--out", required=True, help="directory for cuts.json and rough_cut.mp4")
    run_p.add_argument("--stt", choices=("xai", "local"), default="xai")
    run_p.add_argument("--whisper-model", default="large-v3-turbo")
    run_p.add_argument("--max-pause", type=float, default=0.8)
    run_p.add_argument("--no-snap", action="store_true")
    run_p.add_argument("--mode", choices=("speech", "assemble"), default="speech")
    run_p.add_argument("--intent", default="", help="what this movie is, for spoken cuts")
    run_p.add_argument("--decide", action="store_true", help="write cuts.json and stop before ffmpeg")
    run_p.add_argument(
        "--scene-transition",
        choices=("dip", "off"),
        default="dip",
        help="dip through black between source files, or cut",
    )
    run_p.add_argument(
        "--b-roll-file",
        action="append",
        default=[],
        metavar="PATH",
        help="this file is B-roll: not transcribed, its picture covers spoken lines",
    )
    run_p.add_argument(
        "--b-roll-sound",
        choices=("mix", "voice"),
        default="mix",
        help="mix the B-roll sound under the voice, or play the voice alone",
    )
    render_p = sub.add_parser("render", help="encode a rough cut from a decided cuts.json")
    render_p.add_argument("cuts", help="cuts.json or the directory that holds it")
    render_p.add_argument(
        "--scene-transition",
        choices=("dip", "off"),
        default="dip",
        help="dip through black between source files, or cut",
    )
    render_p.add_argument(
        "--b-roll-sound",
        choices=("mix", "voice"),
        default="mix",
        help="mix the B-roll sound under the voice, or play the voice alone",
    )
    cap_p = sub.add_parser("captions", help="write an SRT for the rough cut")
    cap_p.add_argument("cuts", help="path to cuts.json")
    cap_p.add_argument("--burn", action="store_true", help="also write rough_cut.captioned.mp4")
    short_p = sub.add_parser("short", help="cut one 1080x1920 highlight")
    short_p.add_argument("cuts", help="path to cuts.json")
    revise_p = sub.add_parser("revise", help="revise a decided cut from a note")
    revise_p.add_argument("cuts", help="path to cuts.json")
    revise_p.add_argument("note", nargs="?", default="", help="what to change")
    revise_p.add_argument("--pace", choices=("open", "measured", "tight", "frenzied"), default="open")
    revise_p.add_argument(
        "--scene-transition",
        choices=("dip", "off"),
        default="dip",
        help="current dip between files",
    )
    revise_p.add_argument(
        "--propose",
        action="store_true",
        help="write proposal.json and print the reply; leave cuts.json alone",
    )
    revise_p.add_argument(
        "--apply",
        action="store_true",
        help="land the proposal.json written by --propose; no model call",
    )
    revise_p.add_argument(
        "--history",
        metavar="PATH",
        help="earlier chat turns as JSON, a list of {role: you|bot, text}",
    )
    card_p = sub.add_parser("card", help="make a 3 second card from a sentence")
    card_p.add_argument("--out", required=True, help="mp4 to write, named botcut-card-…")
    card_p.add_argument("sentence", help="the sentence on the card")
    sub.add_parser("key", help="check that xAI accepts XAI_API_KEY")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "run":
            run(
                args.files,
                args.out,
                stt=args.stt,
                whisper_model=args.whisper_model,
                max_pause=args.max_pause,
                snap_edges=not args.no_snap,
                mode=args.mode,
                intent=args.intent,
                decide=args.decide,
                scene_transition=args.scene_transition,
                broll_files=args.b_roll_file,
                broll_sound=args.b_roll_sound,
            )
        elif args.cmd == "render":
            render_saved(
                args.cuts,
                scene_transition=args.scene_transition,
                broll_sound=args.b_roll_sound,
            )
        elif args.cmd == "captions":
            captions(args.cuts, burn=args.burn)
        elif args.cmd == "short":
            make_short(args.cuts)
        elif args.cmd == "revise":
            if args.apply:
                if args.note or args.propose:
                    raise SystemExit("--apply takes no note")
                apply_proposal(args.cuts)
            else:
                revise(
                    args.cuts,
                    args.note,
                    pace=args.pace,
                    dip=args.scene_transition != "off",
                    propose=args.propose,
                    history=args.history,
                )
        elif args.cmd == "card":
            make_card(args.sentence, args.out)
        elif args.cmd == "key":
            check_key()
    except BrokenPipeError:
        sys.exit(0)


def run(
    files: list[str],
    out: str,
    stt: str = "xai",
    whisper_model: str = "large-v3-turbo",
    max_pause: float = 0.8,
    snap_edges: bool = True,
    mode: str = "speech",
    intent: str = "",
    decide: bool = False,
    scene_transition: str = "dip",
    broll_files: list[str] | None = None,
    broll_sound: str = "mix",
) -> None:
    if mode not in ("speech", "assemble"):
        raise SystemExit(f"Unknown mode: {mode}")
    paths = resolve_inputs(files)
    # Assemble plays every file in order with its own sound, so a B-roll mark means nothing there.
    roles = _broll_roles(paths, [*(broll_files or []), *resolve_broll(files)]) if mode == "speech" else set()
    print("Reading files", flush=True)
    clips = []
    for index, path in enumerate(paths):
        if not os.path.isfile(path):
            raise SystemExit(f"No such file: {path}")
        clip = probe(path, need_audio=index not in roles)
        if index in roles:
            clip["role"] = "broll"
        clips.append(clip)
    if mode == "assemble":
        segs = [
            {"clip": i, "start": 0.0, "end": float(clip["duration"]), "reason": "assemble"}
            for i, clip in enumerate(clips)
        ]
        doc = {
            "version": 1,
            "mode": "assemble",
            "stt": "none",
            "model": "none",
            "tighten": {"max_pause": max_pause, "snap": False},
            "clips": [_clip_row(i, clip) for i, clip in enumerate(clips)],
            "segments": segs,
            "dropped": [],
        }
        _write_cut(out, doc, segs, clips, scene_transition, broll_sound)
        return

    fake = os.environ.get("BOTCUT_FAKE") == "1"
    backend = "local" if stt == "local" else "xai"
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)
    words_by_clip: list[list] = [[] for _ in clips]
    silences_by_clip: list[list] = [[] for _ in clips]
    beats_by_clip: dict[int, list] = {}
    label = _stt_label(fake, stt, whisper_model)
    for index, clip in enumerate(clips):
        # A card has nothing heard or measured, so nothing is kept for it.
        if not is_card(clip["path"]):
            _drop_stale_caches(work, index, clip, label)
    speech = [
        (index, clip)
        for index, clip in enumerate(clips)
        if not is_card(clip["path"]) and not is_broll(clip)
    ]
    for index, clip in enumerate(clips):
        if is_broll(clip):
            # B-roll is picture. It is not transcribed and never becomes a line.
            if not beats_by_clip:
                print("Reading beats", flush=True)
            beats_by_clip[index] = _beats_for_clip(work, index, Path(clip["path"]).stem, clip)

    def listen(index: int, clip: dict) -> tuple[list, list]:
        stem = Path(clip["path"]).stem
        if fake:
            payload = transcribe_fake()
            cache = word_cache_candidates(work, index, stem, "fake")[0]
            Path(cache).write_text(json.dumps(payload) + "\n")
            return payload["words"], []
        flac = os.path.join(work, f"{index}-{stem}.flac")
        words = _words_for_clip(work, index, stem, backend, flac, clip, whisper_model)
        return words, _silences_for_clip(work, index, stem, flac, clip)

    def said(count: int) -> None:
        # The window reads this as progress: the shot being worked on, of how many.
        name = Path(speech[count - 1][1]["path"]).name
        print(f"Transcribing {count}/{len(speech)} {name}", flush=True)

    # xAI transcribes several shots at once. Whisper on this machine takes them one by one.
    workers = 1 if fake or backend == "local" else min(TRANSCRIBE_WORKERS, len(speech))
    if speech:
        said(1)
    if workers <= 1:
        for count, (index, clip) in enumerate(speech, start=1):
            if count > 1:
                said(count)
            words_by_clip[index], silences_by_clip[index] = listen(index, clip)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers) as pool:
            waiting = {pool.submit(listen, index, clip): index for index, clip in speech}
            try:
                for done, future in enumerate(as_completed(waiting), start=1):
                    index = waiting[future]
                    words_by_clip[index], silences_by_clip[index] = future.result()
                    if done < len(speech):
                        said(done + 1)
            except BaseException:
                # One shot failing stops the cut. The shots not yet started are not sent.
                pool.shutdown(wait=False, cancel_futures=True)
                raise

    utts = utterances(words_by_clip)
    movie = intent.strip() or DEFAULT_INTENT
    if speech:
        _attach_stills(utts, clips, os.path.join(work, "stills"))
        print("Choosing takes", flush=True)
        chosen = pick(utts, movie)
    else:
        chosen = []
    segs, unknown = segments(utts, chosen, [clip["duration"] for clip in clips])
    if snap_edges:
        segs = snap(segs, silences_by_clip)
    segs = tighten(segs, silences_by_clip, max_pause)
    lines = decision_lines(utts, chosen)
    segs = cut_words(segs, lines)
    lines, segs = merge_cards(lines, segs, clips, movie)
    covers: list = []
    covers_reply = ""
    if beats_by_clip:
        print("Choosing covers", flush=True)
        covers, covers_reply = choose_covers(
            clips, lines, os.path.join(work, "stills"), beats_by_clip, segments=segs, intent=movie
        )
    for line in unknown_warnings(unknown):
        print(line)
    dropped = dropped_utterances(utts, chosen)
    # BOTCUT_FAKE keeps every id, so this prints nothing in the offline tests.
    for line in unique_warnings(dropped, kept_utterances(utts, chosen)):
        print(line)

    doc = {
        "version": 1,
        "mode": "speech",
        "intent": movie,
        "stt": _stt_label(fake, stt, whisper_model),
        "model": "fake" if fake else model_name(),
        "tighten": {"max_pause": max_pause, "snap": snap_edges},
        "clips": [_clip_row(i, clip) for i, clip in enumerate(clips)],
        "segments": segs,
        "lines": lines,
        "dropped": [
            {
                "id": utt["id"],
                "clip": utt["clip"],
                "start": utt["start"],
                "end": utt["end"],
                "text": utt["text"],
            }
            for utt in dropped
        ],
    }
    if covers:
        doc["covers"] = covers
    if covers_reply:
        doc["covers_reply"] = covers_reply
    if decide:
        _write_doc(out, doc)
        kept_n = sum(1 for line in doc["lines"] if line["keep"])
        print(f"{kept_n} kept, {len(doc['lines']) - kept_n} dropped", flush=True)
        return
    _write_cut(out, doc, segs, clips, scene_transition, broll_sound)


def _clip_row(index: int, clip: dict) -> dict:
    row = {"index": index, "path": clip["path"], "duration": clip["duration"]}
    if is_broll(clip):
        row["role"] = "broll"
    return row


def _broll_roles(paths: list[str], broll_files: list[str]) -> set[int]:
    """Clip indexes marked B-roll. The file has to be one of the shots, and not a card."""
    absolute = [os.path.abspath(path) for path in paths]
    roles: set[int] = set()
    for wanted in broll_files or []:
        target = os.path.abspath(wanted)
        if target not in absolute:
            raise SystemExit(f"B-roll file is not in the list: {wanted}")
        if is_card(target):
            raise SystemExit(f"A card cannot be B-roll: {wanted}")
        roles.add(absolute.index(target))
    return roles


def _attach_stills(utts: list[dict], clips: list[dict], directory: str) -> None:
    """One JPEG at the middle of each line. A missed frame does not stop the cut."""
    from botcut.media import grab_still

    from concurrent.futures import ThreadPoolExecutor

    print("Reading pictures", flush=True)
    os.makedirs(directory, exist_ok=True)

    def grab(utt: dict) -> None:
        clip = clips[int(utt["clip"])]
        dur = float(clip.get("duration") or 0)
        mid = (float(utt["start"]) + float(utt["end"])) / 2
        if dur > 0:
            mid = min(max(0.0, mid), max(0.0, dur - 0.05))
        dest = os.path.join(directory, f"{int(utt['id'])}.jpg")
        # A still from an earlier run of this cut is the same frame. One older than the shot is not.
        fresh = os.path.isfile(dest) and os.path.getmtime(dest) >= os.path.getmtime(clip["path"])
        if fresh or grab_still(clip["path"], mid, dest):
            utt["still"] = os.path.abspath(dest)

    # Each still is one short ffmpeg seek, so several at once is the quick way through a long list.
    with ThreadPoolExecutor(max_workers=STILL_WORKERS) as pool:
        list(pool.map(grab, utts))


def _write_doc(out: str, doc: dict) -> str:
    os.makedirs(out, exist_ok=True)
    cuts_path = os.path.join(out, "cuts.json")
    Path(cuts_path).write_text(json.dumps(doc, indent=2) + "\n")
    print(f"Wrote {os.path.abspath(cuts_path)}")
    return cuts_path


def _write_cut(
    out: str,
    doc: dict,
    segs: list,
    clips: list,
    scene_transition: str = "dip",
    broll_sound: str = "mix",
) -> None:
    _write_doc(out, doc)
    if not segs:
        raise SystemExit("No segments to render")
    dst = os.path.join(out, "rough_cut.mp4")
    _level_clips(os.path.join(out, "work"), clips)
    render_with_progress(
        segs,
        clips,
        dst,
        "Rendering",
        "Render failed",
        polish=True,
        scene_transition=scene_transition,
        covers=doc.get("covers") or None,
        lines=doc.get("lines") or None,
        broll_sound=broll_sound,
    )
    kept_s = sum(seg["end"] - seg["start"] for seg in segs)
    total_s = sum(clip["duration"] for clip in clips)
    print(f"Wrote {os.path.abspath(dst)} ({kept_s:.1f}s of {total_s:.1f}s)")


def render_saved(cuts: str, scene_transition: str = "dip", broll_sound: str = "mix") -> None:
    """Encode rough_cut.mp4 from a cuts.json the tray has already confirmed."""
    path = cuts
    if os.path.isdir(path):
        path = os.path.join(path, "cuts.json")
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise SystemExit(f"No such file: {path}")
    try:
        doc = json.loads(Path(path).read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Cannot read {path}: {exc}") from exc
    out = os.path.dirname(path)
    rows = sorted(doc.get("clips") or [], key=lambda clip: int(clip["index"]))
    if not rows:
        raise SystemExit("cuts.json has no clips")
    clips = []
    for row in rows:
        broll = str(row.get("role") or "") == "broll"
        clip = probe(row["path"], need_audio=not broll)
        if broll:
            clip["role"] = "broll"
        clips.append(clip)
    lines = doc.get("lines") or []
    # A hand trim on Watch owns the segments. Rebuilding from lines would undo it.
    if lines and not doc.get("trimmed"):
        tighten_doc = doc.get("tighten") or {}
        segs = _segments_for_lines(
            lines,
            [float(clip["duration"]) for clip in clips],
            _load_silences(out, clips),
            bool(tighten_doc.get("snap", True)),
            float(tighten_doc.get("max_pause", 0.8)),
        )
        doc["segments"] = segs
        doc["dropped"] = [
            {
                "id": line["id"],
                "clip": line["clip"],
                "start": line["start"],
                "end": line["end"],
                "text": line["text"],
            }
            for line in lines
            if not line.get("keep")
        ]
    else:
        segs = doc.get("segments") or []
    _write_cut(out, doc, segs, clips, scene_transition, broll_sound)


def _segments_for_lines(
    lines: list, durations: list, silences: list, snap_edges: bool, max_pause: float
) -> list:
    utts = [
        {
            "id": int(line["id"]),
            "clip": int(line["clip"]),
            "start": float(line["start"]),
            "end": float(line["end"]),
            "text": str(line.get("text") or ""),
        }
        for line in lines
    ]
    keep = [
        {"id": int(line["id"]), "reason": str(line.get("reason") or "restored")}
        for line in lines
        if line.get("keep")
    ]
    segs, _unknown = segments(utts, keep, durations)
    if snap_edges:
        segs = snap(segs, silences)
    return cut_words(tighten(segs, silences, max_pause), lines)


def _load_silences(out: str, clips: list) -> list:
    work = os.path.join(out, "work")
    found = []
    for index, clip in enumerate(clips):
        cache = os.path.join(work, f"{index}-{Path(clip['path']).stem}.silences.json")
        if os.path.isfile(cache):
            found.append([tuple(pair) for pair in json.loads(Path(cache).read_text())])
        else:
            found.append([])
    return found


def _words_for_clip(
    work: str, index: int, stem: str, backend: str, flac: str, clip: dict, whisper_model: str
) -> list:
    for cache in word_cache_candidates(work, index, stem, backend):
        if os.path.isfile(cache):
            print(f"cache hit {cache}")
            return json.loads(Path(cache).read_text())["words"]
    if not os.path.isfile(flac):
        extract_audio(clip["path"], flac)
    if backend == "local":
        result = transcribe_local(flac, whisper_model, stem)
    else:
        result = transcribe_xai(flac)
    cache = word_cache_candidates(work, index, stem, backend)[0]
    Path(cache).write_text(json.dumps(result) + "\n")
    return result["words"]


def _drop_stale_caches(work: str, index: int, clip: dict, stt_label: str) -> None:
    """Forget what was heard in a shot if the file, or the transcriber, has changed.

    Caches are named by position and file name. A re-exported file with the
    same name, or another Whisper model, must not be answered from the old one.
    """
    stem = Path(clip["path"]).stem
    stamp_path = os.path.join(work, f"{index}-{stem}.stamp.json")
    try:
        info = os.stat(clip["path"])
    except OSError:
        return
    stamp = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "stt": stt_label}
    try:
        known = json.loads(Path(stamp_path).read_text())
    except (OSError, ValueError):
        known = None
    if known == stamp:
        return
    if known is not None:
        prefix = f"{index}-{stem}."
        for name in os.listdir(work):
            if name.startswith(prefix) and name != os.path.basename(stamp_path):
                os.remove(os.path.join(work, name))
    Path(stamp_path).write_text(json.dumps(stamp) + "\n")


def _level_clips(work: str, clips: list[dict]) -> None:
    """Note how loud each spoken shot is, once, so the render can match them to each other."""
    from concurrent.futures import ThreadPoolExecutor

    from botcut.media import loudness

    os.makedirs(work, exist_ok=True)

    def heard(numbered: tuple[int, dict]) -> None:
        index, clip = numbered
        if is_card(clip["path"]) or is_broll(clip) or not clip.get("audio", True):
            return
        cache = os.path.join(work, f"{index}-{Path(clip['path']).stem}.loudness.json")
        try:
            value = json.loads(Path(cache).read_text())["i"]
        except (OSError, ValueError, KeyError, TypeError):
            value = loudness(clip["path"])
            Path(cache).write_text(json.dumps({"i": value}) + "\n")
        if value is not None:
            clip["loudness"] = value

    with ThreadPoolExecutor(max_workers=STILL_WORKERS) as pool:
        list(pool.map(heard, enumerate(clips)))


def _beats_for_clip(work: str, index: int, stem: str, clip: dict) -> list:
    """Scene changes once per B-roll file. BOTCUT_FAKE uses fixed windows and no ffmpeg."""
    cache = os.path.join(work, f"{index}-{stem}.beats.json")
    if os.path.isfile(cache):
        return [tuple(pair) for pair in json.loads(Path(cache).read_text())]
    duration = float(clip.get("duration") or 0)
    if os.environ.get("BOTCUT_FAKE") == "1":
        pairs = fake_beats(duration)
    else:
        pairs = beats_from_cuts(scene_changes(clip["path"]), duration)
    Path(cache).write_text(json.dumps(pairs) + "\n")
    return pairs


def _silences_for_clip(work: str, index: int, stem: str, flac: str, clip: dict) -> list:
    cache = os.path.join(work, f"{index}-{stem}.silences.json")
    if os.path.isfile(cache):
        return [tuple(pair) for pair in json.loads(Path(cache).read_text())]
    if not os.path.isfile(flac):
        extract_audio(clip["path"], flac)
    pairs = silences(flac, clip["duration"])
    Path(cache).write_text(json.dumps(pairs) + "\n")
    return pairs


def _stt_label(fake: bool, stt: str, whisper_model: str) -> str:
    if fake:
        return "fake"
    if stt == "local":
        return f"local:faster-whisper:{whisper_model}"
    return "xai:grok-voice-transcribe-2.0"


def captions(cuts_path: str, burn: bool = False) -> None:
    out_dir, doc = load_cuts(cuts_path)
    mapped = remap_words(doc.get("segments") or [], load_words_by_clip(doc, out_dir))
    srt_path = os.path.join(out_dir, "rough_cut.srt")
    Path(srt_path).write_text(to_srt(mapped))
    print(f"Wrote {os.path.abspath(srt_path)}")
    if not burn:
        return
    require_subtitles()
    src = os.path.join(out_dir, "rough_cut.mp4")
    if not os.path.isfile(src):
        raise SystemExit(f"No such file: {src}")
    encoder, device = resolve_encoder()
    proc = subprocess.run(
        ["ffmpeg", *burn_args(encoder=encoder, device=device)],
        cwd=out_dir,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-500:] or "ffmpeg failed"
        raise SystemExit(f"Caption burn failed: {detail}")
    print(f"Wrote {os.path.abspath(os.path.join(out_dir, 'rough_cut.captioned.mp4'))}")


def make_short(cuts_path: str) -> None:
    out_dir, doc = load_cuts(cuts_path)
    segments = doc.get("segments") or []
    words = load_words_by_clip(doc, out_dir)
    utts = utterances(words)
    kept = kept_on_cut(utts, segments)
    if not kept:
        raise SystemExit("No kept speech to highlight")
    choice = pick_highlight(kept)
    start, end = highlight_span(segments, words, utts, int(choice["start_id"]), int(choice["end_id"]))
    length = end - start
    if length <= 0:
        raise SystemExit("Highlight is empty")
    window = []
    for word in remap_words(segments, words):
        if word["end"] <= start or word["start"] >= end:
            continue
        window.append(
            {
                "text": word["text"],
                "start": max(0.0, word["start"] - start),
                "end": min(word["end"], end) - start,
            }
        )
    Path(os.path.join(out_dir, "short.srt")).write_text(to_srt(window))
    src = os.path.join(out_dir, "rough_cut.mp4")
    if not os.path.isfile(src):
        raise SystemExit(f"No such file: {src}")
    require_subtitles()
    info = probe(src)
    encoder, device = resolve_encoder()
    proc = subprocess.run(
        [
            "ffmpeg",
            *short_args(
                start,
                length,
                int(info["width"]),
                int(info["height"]),
                encoder=encoder,
                device=device,
            ),
        ],
        cwd=out_dir,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-500:] or "ffmpeg failed"
        raise SystemExit(f"Short render failed: {detail}")
    dst = os.path.abspath(os.path.join(out_dir, "short.mp4"))
    print(f'Wrote {dst} "{choice["title"]}" ({length:.1f}s)')


def load_cuts(cuts_path: str) -> tuple[str, dict]:
    path = os.path.abspath(cuts_path)
    if not os.path.isfile(path):
        raise SystemExit(f"No such file: {path}")
    try:
        doc = json.loads(Path(path).read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Cannot read {path}: {exc}") from exc
    return os.path.dirname(path), doc


BROLL_PREFIX = "b-roll "


def _shot_list(path: str) -> list[tuple[str, bool]]:
    """One path per line. A line that starts with `b-roll ` marks that file."""
    if not os.path.isfile(path):
        raise SystemExit(f"No such file: {path}")
    rows = []
    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith(BROLL_PREFIX):
            rows.append((stripped[len(BROLL_PREFIX) :].strip(), True))
        else:
            rows.append((stripped, False))
    if not rows:
        raise SystemExit(f"No paths in {path}")
    return rows


def _is_shot_list(files: list[str]) -> bool:
    return len(files) == 1 and files[0].lower().endswith(".txt")


def resolve_inputs(files: list[str]) -> list[str]:
    if _is_shot_list(files):
        return [path for path, _broll in _shot_list(files[0])]
    return list(files)


def resolve_broll(files: list[str]) -> list[str]:
    """The files a shot list marks B-roll. Plain arguments mark none."""
    if _is_shot_list(files):
        return [path for path, broll in _shot_list(files[0]) if broll]
    return []
