"""botcut-cli: transcribe, pick takes, revise a cut, make a card, render a rough cut."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from botcut import angles as cameras
from botcut import brand as brand_kit
from botcut import llm, net
from botcut.broll import beats_from_cuts, choose_covers, fake_beats, is_broll
from botcut.card import is_card, make_card, merge_cards
from botcut.captions import (
    burn_args,
    burn_ass_args,
    load_words_by_clip,
    remap_words,
    require_subtitles,
    to_ass,
    to_srt,
    word_cache_candidates,
)
from botcut.media import (
    ASPECTS,
    RESOLUTIONS,
    cached_still,
    extract_audio,
    ffmpeg_error_detail,
    is_image,
    probe,
    render_percent,
    render_with_progress,
    resolve_encoder,
    scene_changes,
    silences,
)
from botcut.pick import (
    DEFAULT_INTENT,
    cut_words,
    decision_lines,
    folds,
    model_name,
    hook_line,
    no_outline,
    outline,
    pick,
    play_order,
    read_shoot,
    segments,
    settle,
    snap,
    tighten,
    unique_warnings,
    unknown_warnings,
    utterances,
)
from botcut.frame import ZOOMS, close_ids, faces_along, find_faces, focus
from botcut.revise import apply_proposal, revise
from botcut.proof import apply_changes, changed, no_changes, proof
from botcut.short import highlight_span, kept_on_cut, pick_highlight, short_args
from botcut.stt import key_terms, terms_mark, transcribe_fake, transcribe_local, transcribe_xai


ZOOM_HELP = (
    "zoom in on the speaker: all three ways together (auto), or only at a join between lines (cuts), "
    "slowly between joins (push), or on the lines that carry the point (lines)"
)

# Shots sent to the transcriber at once, and stills grabbed at once.
TRANSCRIBE_WORKERS = 4
STILL_WORKERS = 4

_FLAC_LOCKS_GUARD = threading.Lock()
_FLAC_LOCKS: dict[str, threading.Lock] = {}


def _ensure_flac(clip_path: str, flac: str) -> None:
    if os.path.isfile(flac):
        return
    with _FLAC_LOCKS_GUARD:
        lock = _FLAC_LOCKS.setdefault(flac, threading.Lock())
    with lock:
        if not os.path.isfile(flac):
            extract_audio(clip_path, flac)


def _pool_map(fn, items, max_workers: int = STILL_WORKERS) -> list:
    seq = list(items)
    if not seq:
        return []
    workers = min(max_workers, len(seq))
    if workers <= 1:
        return [fn(item) for item in seq]
    from concurrent.futures import ThreadPoolExecutor

    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        return list(pool.map(fn, seq))
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)


def _run_ffmpeg_progress(
    args: list[str],
    duration: float,
    label: str,
    fail_prefix: str,
    *,
    cwd: str | None = None,
) -> None:
    """Run ffmpeg with -progress pipe:1, printing '<label> N%' and cleanly terminating on cancel."""
    lead = args[1:] if args and args[0] == "-y" else args
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *lead]
    print(f"{label} 0%", flush=True)
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    err_parts: list[str] = []

    def drain() -> None:
        if proc.stderr is not None:
            err_parts.append(proc.stderr.read())

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    last = 0
    try:
        if proc.stdout is None:
            raise SystemExit(f"{fail_prefix}: ffmpeg failed")
        for raw in proc.stdout:
            line = raw.strip()
            if not line.startswith("out_time_us="):
                continue
            value = line.split("=", 1)[1]
            if not value.lstrip("-").isdigit():
                continue
            percent = render_percent(int(value), duration)
            if percent == last:
                continue
            last = percent
            print(f"{label} {percent}%", flush=True)
    except BaseException:
        if proc.poll() is None:
            proc.terminate()
        raise
    finally:
        code = proc.wait()
        thread.join()
    if code != 0:
        raise SystemExit(f"{fail_prefix}: {ffmpeg_error_detail(err_parts[0] if err_parts else '')}")
    if last < 100:
        print(f"{label} 100%", flush=True)


class _Clock:
    """Seconds spent in each stage of a cut, in the order the stages ran."""

    def __init__(self) -> None:
        self._last = time.perf_counter()
        self.seconds: dict[str, float] = {}

    def lap(self, stage: str) -> None:
        """Everything since the last lap went to this stage."""
        now = time.perf_counter()
        self.seconds[stage] = round(self.seconds.get(stage, 0.0) + now - self._last, 2)
        self._last = now


def _span(seconds: float) -> str:
    whole = int(round(seconds))
    return f"{whole // 60}m{whole % 60:02d}s" if whole >= 60 else f"{whole}s"


def took_line(seconds: dict) -> str:
    """'Took 6m39s: render 4m45s, choose 1m16s, listen 9s.' Longest first, under a second left out."""
    total = sum(seconds.values())
    parts = [
        f"{stage} {_span(spent)}"
        for stage, spent in sorted(seconds.items(), key=lambda item: -item[1])
        if spent >= 1
    ]
    return f"Took {_span(total)}" + (": " + ", ".join(parts) if parts else "") + "."


def _took(out: str, clock: _Clock, fresh: bool) -> None:
    """Say how long the stages took, and keep it in work/seconds.json.

    It is kept beside the caches and not in cuts.json, so nothing is written to
    cuts.json after a render that the window may have changed in the meantime.
    A render of a saved cut adds its stages to what the cut itself took.
    """
    path = os.path.join(out, "work", "seconds.json")
    known: dict = {}
    if not fresh:
        try:
            known = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            known = {}
        if not isinstance(known, dict):
            known = {}
    known.update(clock.seconds)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(json.dumps(known) + "\n")
    except OSError:
        pass
    print(took_line(clock.seconds), flush=True)


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
    run_p.add_argument(
        "--angle-file",
        action="append",
        default=[],
        metavar="PATH",
        help="this file is another camera on a take one of the other files filmed",
    )
    run_p.add_argument("--zoom", choices=ZOOMS, default="off", help=ZOOM_HELP)
    run_p.add_argument(
        "--resolution",
        choices=RESOLUTIONS,
        default="source",
        help="output resolution: source, 2160p, 1440p, 1080p, or 720p",
    )
    run_p.add_argument(
        "--aspect",
        choices=ASPECTS,
        default="source",
        help="output aspect ratio: source, landscape (16:9), or portrait (9:16)",
    )
    run_p.add_argument(
        "--pip",
        action="store_true",
        help="show the speaker picture-in-picture over landscape B-roll/screens/slides",
    )
    run_p.add_argument(
        "--preset",
        choices=brand_kit.PRESET_NAMES,
        default="custom",
        help="video type preset: custom, internal, marketing, or monologue",
    )
    run_p.add_argument(
        "--music",
        default=None,
        metavar="PATH",
        help="background music track (auto-ducked under voice)",
    )
    run_p.add_argument(
        "--live-title",
        default=None,
        metavar="TEXT",
        help="fade a minimal title overlay over the first 3 seconds of live video",
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
    render_p.add_argument("--zoom", choices=ZOOMS, default="off", help=ZOOM_HELP)
    render_p.add_argument(
        "--resolution",
        choices=RESOLUTIONS,
        default=None,
        help="output resolution: source, 2160p, 1440p, 1080p, or 720p",
    )
    render_p.add_argument(
        "--aspect",
        choices=ASPECTS,
        default=None,
        help="output aspect ratio: source, landscape (16:9), or portrait (9:16)",
    )
    render_p.add_argument(
        "--out-file",
        default=None,
        metavar="PATH",
        help="render directly to this mp4 path without replacing rough_cut.mp4",
    )
    render_p.add_argument(
        "--pip",
        action="store_true",
        default=None,
        help="show the speaker picture-in-picture over landscape B-roll/screens/slides",
    )
    render_p.add_argument(
        "--music",
        default=None,
        metavar="PATH",
        help="background music track (auto-ducked under voice)",
    )
    render_p.add_argument(
        "--live-title",
        default=None,
        metavar="TEXT",
        help="fade a minimal title overlay over the first 3 seconds of live video",
    )
    cap_p = sub.add_parser("captions", help="write an SRT or styled ASS for the rough cut")
    cap_p.add_argument("cuts", help="path to cuts.json")
    cap_p.add_argument("--burn", action="store_true", help="also write rough_cut.captioned.mp4")
    cap_p.add_argument(
        "--style",
        choices=("srt", "social"),
        default="srt",
        help="caption format: srt (plain subtitles) or social (word-highlighted ASS)",
    )
    cap_p.add_argument(
        "--lower-third",
        action="store_true",
        help="include speaker lower-third from brand.json (with --style social)",
    )
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
    card_p.add_argument(
        "--style",
        choices=("photo", "typo", "ai"),
        default="ai",
        help="photo overlay on a key frame (photo), solid typographic card (typo), or AI image (ai)",
    )
    card_p.add_argument("--from", dest="from_video", default=None, help="source video to pull key frame from (for --style photo)")
    card_p.add_argument("--aspect", choices=("landscape", "portrait"), default="landscape", help="card orientation")
    card_p.add_argument("sentence", help="the sentence on the card")
    brand_p = sub.add_parser("brand", help="view or initialize ~/.config/botcut/brand.json")
    brand_p.add_argument("brand_cmd", choices=("show", "init"), default="show", nargs="?")
    thumb_p = sub.add_parser("thumb", help="make a Matt-style minimal photo thumbnail or opening title card")
    thumb_p.add_argument("cuts", help="path to cuts.json or project folder")
    thumb_p.add_argument("--title", default="", help="headline on the card")
    thumb_p.add_argument("--subtitle", default=None, help="bottom line (defaults to today's date)")
    thumb_p.add_argument("--brand", default=None, help="top brand/product label")
    thumb_p.add_argument("--out", default=None, help="output JPEG thumbnail path")
    thumb_p.add_argument("--card", default=None, help="also write a 3-second opening MP4 card here")
    thumb_p.add_argument("--aspect", choices=("landscape", "portrait"), default="landscape")
    thumb_p.add_argument("--embed", action="store_true", help="embed thumbnail into rough_cut.mp4 cover art")
    ship_p = sub.add_parser("ship", help="generate a Ship Pack: chapters, post drafts, thumbnail, captions, and renders")
    ship_p.add_argument("cuts", help="path to cuts.json or project folder")
    ship_p.add_argument("--out", default=None, help="output folder for the ship pack")
    ship_p.add_argument("--title", default="", help="title for the pack, thumbnail, and posts")
    ship_p.add_argument("--resolution", choices=RESOLUTIONS, default="1080p")
    ship_p.add_argument("--no-portrait", action="store_true", help="skip the 9:16 portrait render")
    sub.add_parser("key", help="check that xAI accepts XAI_API_KEY")
    bench_p = sub.add_parser("bench", help="score the prompts against cuts finished by hand")
    bench_sub = bench_p.add_subparsers(dest="bench_cmd", required=True)
    bench_save = bench_sub.add_parser("save", help="keep a finished cut as a case")
    bench_save.add_argument("cuts", help="path to cuts.json, or its folder")
    bench_save.add_argument("name", help="a short name for the case")
    bench_run = bench_sub.add_parser("run", help="ask the model again and score it")
    bench_run.add_argument("names", nargs="*", help="cases to run; all of them when none is named")
    bench_run.add_argument(
        "--replay", action="store_true", help="use the answers recorded last time; no network"
    )
    bench_sub.add_parser("list", help="name the saved cases")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "run":
            run_extra: dict = {}
            if args.resolution != "source":
                run_extra["resolution"] = args.resolution
            if args.aspect != "source":
                run_extra["aspect"] = args.aspect
            if args.pip:
                run_extra["pip"] = True
            if args.preset != "custom":
                run_extra["preset"] = args.preset
            if args.music:
                run_extra["music"] = args.music
            if args.live_title:
                run_extra["live_title"] = args.live_title
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
                zoom=args.zoom,
                angle_files=args.angle_file,
                **run_extra,
            )
        elif args.cmd == "render":
            render_extra: dict = {}
            if args.resolution is not None:
                render_extra["resolution"] = args.resolution
            if args.aspect is not None:
                render_extra["aspect"] = args.aspect
            if args.out_file is not None:
                render_extra["out_file"] = args.out_file
            if args.pip is not None:
                render_extra["pip"] = args.pip
            if args.music is not None:
                render_extra["music"] = args.music
            if args.live_title is not None:
                render_extra["live_title"] = args.live_title
            render_saved(
                args.cuts,
                scene_transition=args.scene_transition,
                broll_sound=args.b_roll_sound,
                zoom=args.zoom,
                **render_extra,
            )
        elif args.cmd == "captions":
            cap_extra: dict = {}
            if args.style != "srt":
                cap_extra["style"] = args.style
            if args.lower_third:
                cap_extra["lower_third"] = True
            captions(args.cuts, burn=args.burn, **cap_extra)
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
            card_extra: dict = {}
            if args.style != "ai":
                card_extra["style"] = args.style
            if args.aspect != "landscape":
                card_extra["aspect"] = args.aspect
            if args.from_video:
                card_extra["from_video"] = args.from_video
            make_card(args.sentence, args.out, **card_extra)
        elif args.cmd == "brand":
            if args.brand_cmd == "init":
                path = brand_kit.init_brand()
                print(f"Brand kit ready at {path}")
            else:
                print(json.dumps(brand_kit.load_brand(), indent=2))
        elif args.cmd == "thumb":
            from botcut.thumb import make_photo_thumb

            res = make_photo_thumb(
                args.cuts,
                title=args.title,
                subtitle=args.subtitle,
                brand_name=args.brand,
                out_jpg=args.out,
                out_card_mp4=args.card,
                aspect=args.aspect,
                embed=args.embed,
            )
            if res.get("jpg"):
                print(f"Wrote {os.path.abspath(res['jpg'])}", flush=True)
            if res.get("card"):
                print(f"Wrote {os.path.abspath(res['card'])}", flush=True)
        elif args.cmd == "ship":
            from botcut.ship import make_ship_pack

            pack = make_ship_pack(
                args.cuts,
                args.out,
                title=args.title,
                resolution=args.resolution,
                include_portrait=not args.no_portrait,
            )
            print(f"Ship Pack ready at {pack['dir']}", flush=True)
        elif args.cmd == "key":
            check_key()
        elif args.cmd == "bench":
            from botcut import bench

            if args.bench_cmd == "save":
                bench.save(args.cuts, args.name)
            elif args.bench_cmd == "run":
                bench.run(args.names, replay=args.replay)
            else:
                for name in bench.case_names():
                    print(name)
    except KeyboardInterrupt:
        print("Cancelled", file=sys.stderr, flush=True)
        sys.exit(130)
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
    zoom: str = "off",
    angle_files: list[str] | None = None,
    resolution: str = "source",
    aspect: str = "source",
    pip: bool = False,
    preset: str = "custom",
    music: str | None = None,
    live_title: str | None = None,
) -> None:
    if mode not in ("speech", "assemble"):
        raise SystemExit(f"Unknown mode: {mode}")
    if preset != "custom":
        cfg = brand_kit.preset_config(preset)
        if resolution == "source":
            resolution = cfg["resolution"]
        if aspect == "source":
            aspect = cfg["aspect"]
        if max_pause == 0.8:
            max_pause = float(cfg["max_pause"])
        if zoom == "off":
            zoom = str(cfg["zoom"])
        if not pip:
            pip = bool(cfg["pip"])
        if not intent.strip() and cfg.get("intent"):
            intent = str(cfg["intent"])
        if music is None and cfg.get("music"):
            music = brand_kit.resolve_music(None, brand_kit.load_brand())
    if max_pause <= 0:
        raise SystemExit("--max-pause must be greater than 0")
    clock = _Clock()
    paths = resolve_inputs(files)
    # Assemble plays every file in order with its own sound, so a B-roll mark means nothing there.
    image_roles = {i for i, p in enumerate(paths) if is_image(p)} if mode == "speech" else set()
    roles = (
        (_broll_roles(paths, [*(broll_files or []), *resolve_broll(files)]) | image_roles)
        if mode == "speech"
        else set()
    )
    other_cameras = (
        _broll_roles(paths, [*(angle_files or []), *resolve_angles(files)], what="A second camera")
        if mode == "speech"
        else set()
    )
    if roles & other_cameras:
        raise SystemExit("A file is B-roll or a second camera, not both")
    print("Reading files", flush=True)
    for path in paths:
        if not os.path.isfile(path):
            raise SystemExit(f"No such file: {path}")

    def _probe_one(item: tuple[int, str]) -> dict:
        index, path = item
        clip = probe(path, need_audio=index not in roles)
        if index in roles:
            clip["role"] = "broll"
        return clip

    clips = _pool_map(_probe_one, enumerate(paths))
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
        clock.lap("read")
        _write_cut(
            out,
            doc,
            segs,
            clips,
            scene_transition,
            broll_sound,
            clock=clock,
            fresh=True,
            zoom=zoom,
            resolution=resolution,
            aspect=aspect,
            pip=pip,
            music=music,
            live_title=live_title,
        )
        return

    fake = os.environ.get("BOTCUT_FAKE") == "1"
    backend = "local" if stt == "local" else "xai"
    llm.reset_usage()
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)
    words_by_clip: list[list] = [[] for _ in clips]
    silences_by_clip: list[list] = [[] for _ in clips]
    beats_by_clip: dict[int, list] = {}
    # Names the transcript should lean toward: the person's kept list, and any in the movie sentence.
    terms = [] if fake else key_terms(intent)
    label = _stt_label(fake, stt, whisper_model, terms)
    for index, clip in enumerate(clips):
        # A card has nothing heard or measured, so nothing is kept for it.
        if not is_card(clip["path"]):
            _drop_stale_caches(work, index, clip, label)
    # Two files that heard the same take are two cameras on it. The second is never transcribed.
    find_cameras(work, clips, other_cameras)
    speech = [
        (index, clip)
        for index, clip in enumerate(clips)
        if not is_card(clip["path"]) and not is_broll(clip) and not cameras.is_angle(clip)
    ]
    clock.lap("read")
    broll_list = [(index, clip) for index, clip in enumerate(clips) if is_broll(clip)]
    if broll_list:
        print("Reading beats", flush=True)
        # B-roll is picture. It is not transcribed and never becomes a line.
        for (index, _clip), beats in zip(
            broll_list,
            _pool_map(
                lambda item: _beats_for_clip(work, item[0], Path(item[1]["path"]).stem, item[1]),
                broll_list,
            ),
        ):
            beats_by_clip[index] = beats
        clock.lap("beats")

    def listen(index: int, clip: dict) -> tuple[list, list]:
        stem = Path(clip["path"]).stem
        if fake:
            payload = transcribe_fake()
            cache = word_cache_candidates(work, index, stem, "fake")[0]
            Path(cache).write_text(json.dumps(payload) + "\n")
            return payload["words"], []
        flac = os.path.join(work, f"{index}-{stem}.flac")
        if backend == "xai":
            from concurrent.futures import ThreadPoolExecutor

            sp = ThreadPoolExecutor(max_workers=1)
            sil_future = sp.submit(_silences_for_clip, work, index, stem, flac, clip)
            try:
                words = _words_for_clip(work, index, stem, backend, flac, clip, whisper_model, terms)
                pauses = sil_future.result()
            except BaseException:
                sp.shutdown(wait=False, cancel_futures=True)
                raise
            else:
                sp.shutdown(wait=True)
            return words, pauses
        words = _words_for_clip(work, index, stem, backend, flac, clip, whisper_model, terms)
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

        pool = ThreadPoolExecutor(max_workers=workers)
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
        else:
            pool.shutdown(wait=True)

    utts = utterances(words_by_clip)
    clock.lap("listen")
    movie = intent.strip() or DEFAULT_INTENT
    if speech:
        # A long shoot is outlined while its stills are read: the outline is words only.
        ahead = None
        if not folds(utts):
            from concurrent.futures import ThreadPoolExecutor

            ahead = ThreadPoolExecutor(max_workers=1)
            outlined = ahead.submit(outline, utts, movie)
        try:
            _attach_stills(utts, clips, os.path.join(work, "stills"))
            find_faces(work, clips, lambda clip: not is_card(clip["path"]) and not is_broll(clip))
            clock.lap("stills")
            print("Choosing takes", flush=True)
            plan = outlined.result() if ahead else None
            if ahead:
                clock.lap("outline")
        finally:
            if ahead:
                ahead.shutdown(wait=False, cancel_futures=True)
        plan, chosen = read_shoot(utts, movie, plan)
        clock.lap("choose")
    else:
        plan = no_outline()
        chosen = []
    segs, unknown = segments(utts, chosen, [clip["duration"] for clip in clips])
    if snap_edges:
        segs = snap(segs, silences_by_clip)
    segs = tighten(segs, silences_by_clip, max_pause)
    lines = decision_lines(utts, chosen)
    segs = settle(cut_words(segs, lines), lines)
    changes = no_changes()
    if speech:
        # The cut is read back once, as a viewer gets it, and what trips is fixed.
        print("Checking the cut", flush=True)
        changes = proof(lines, segs, intent=movie, outline=plan)
        if changed(changes):
            lines = apply_changes(lines, changes)
            segs = _segments_for_lines(
                lines, [clip["duration"] for clip in clips], silences_by_clip, snap_edges, max_pause
            )
        clock.lap("proof")
    dropped = [line for line in lines if not line["keep"]]
    kept = [line for line in lines if line["keep"]]
    lines, segs = merge_cards(lines, segs, clips, movie)
    # One line may open the movie. The proof names it, having read the cut without it in place.
    # When a live title overlay is set, open on the actual start of the video instead of lifting
    # a hook from later in the shoot (which creates a jarring jump when the title fades out).
    has_live_title = bool(live_title and str(live_title).strip())
    opening = None if has_live_title else hook_line(lines, changes["hook"])
    hook = int(opening["id"]) if opening else None
    segs = play_order(segs, lines, hook)
    covers: list = []
    covers_reply = ""
    if beats_by_clip:
        print("Choosing covers", flush=True)
        covers, covers_reply = choose_covers(
            clips, lines, os.path.join(work, "stills"), beats_by_clip, segments=segs, intent=movie, hook=hook
        )
        clock.lap("covers")
    for line in unknown_warnings(unknown):
        print(line)
    # BOTCUT_FAKE keeps every id, so this prints nothing in the offline tests.
    for line in unique_warnings(dropped, kept):
        print(line)

    doc = {
        "version": 1,
        "mode": "speech",
        "intent": movie,
        "stt": label,
        "model": "fake" if fake else model_name(),
        "tighten": {"max_pause": max_pause, "snap": snap_edges},
        "clips": [_clip_row(i, clip) for i, clip in enumerate(clips)],
        "segments": segs,
        "lines": lines,
        # What the whole shoot was read as, so a later pass over this cut starts from it.
        "outline": {key: plan[key] for key in ("beats", "retakes", "target_seconds")},
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
    if hook is not None:
        doc["hook"] = hook
    if cameras.groups(clips):
        cameras.name_views(clips, os.path.join(work, "stills"))
        doc["clips"] = [_clip_row(i, clip) for i, clip in enumerate(clips)]
        clock.lap("cameras")
    # The lines that carry the point, kept whatever the zoom is, so choosing Key lines later needs no new cut.
    close = close_ids(changes.get("close"), lines)
    if close:
        doc["close"] = close
    plan_cameras(doc, clips, segs, out)
    if changes["reply"]:
        # What the editor says about the cut it read back. The window opens the chat with it.
        doc["cut_reply"] = changes["reply"]
    # What this cut asked of the model, so the window can say so once.
    tally = llm.usage()
    if tally["requests"]:
        doc["usage"] = tally
        print(llm.usage_line(tally), flush=True)
    if decide:
        _review(doc, segs, zoom)
        _write_doc(out, doc)
        kept_n = sum(1 for line in doc["lines"] if line["keep"])
        print(f"{kept_n} kept, {len(doc['lines']) - kept_n} dropped", flush=True)
        clock.lap("write")
        _took(out, clock, fresh=True)
        return
    _write_cut(
        out,
        doc,
        segs,
        clips,
        scene_transition,
        broll_sound,
        clock=clock,
        fresh=True,
        zoom=zoom,
        resolution=resolution,
        aspect=aspect,
        pip=pip,
        music=music,
        live_title=live_title,
    )


def _clip_row(index: int, clip: dict) -> dict:
    row = {"index": index, "path": clip["path"], "duration": clip["duration"]}
    if is_broll(clip):
        row["role"] = "broll"
    if cameras.is_angle(clip):
        # Another camera on the take shot `of` filmed, and where that take is in this file.
        row["role"] = "angle"
        for key in ("of", "offset", "drift", "view"):
            if clip.get(key) not in (None, "", 0.0) or key in ("of", "offset"):
                row[key] = clip.get(key)
    elif clip.get("view"):
        row["view"] = clip["view"]
    # Where the speaker is, so a later render and the short frame them the same way.
    if clip.get("face"):
        row["face"] = clip["face"]
    return row


def _broll_roles(paths: list[str], broll_files: list[str], what: str = "B-roll") -> set[int]:
    """Clip indexes marked B-roll, or a second camera. The file has to be one of the shots, and not a card."""
    absolute = [os.path.abspath(path) for path in paths]
    roles: set[int] = set()
    for wanted in broll_files or []:
        target = os.path.abspath(wanted)
        if target not in absolute:
            raise SystemExit(f"{what} file is not in the list: {wanted}")
        if is_card(target):
            raise SystemExit(f"A card cannot be {'B-roll' if what == 'B-roll' else 'a second camera'}: {wanted}")
        roles.add(absolute.index(target))
    return roles


# Two files are taken for two cameras on one take only when they share this much of the shorter one.
CAMERA_SHARE = 0.5


def find_cameras(work: str, clips: list[dict], marked: set[int]) -> None:
    """Mark each file that is another camera on a take an earlier file filmed.

    A file the person marked is lined up with whichever shot matches it best,
    and the cut stops if none does. Among the rest, a later file that heard
    the same sound as an earlier one for at least half its length is taken
    for its second camera. What is found is kept in work/cameras.json.
    """
    from botcut import sync

    spoken = [
        index
        for index, clip in enumerate(clips)
        if not is_card(clip["path"]) and not is_broll(clip) and clip.get("audio", True)
    ]
    for index in marked:
        if index not in spoken:
            raise SystemExit(f"A second camera needs sound to be lined up: {clips[index]['path']}")
    if len(spoken) < 2:
        if marked:
            raise SystemExit("A second camera needs a shot to be the second camera of")
        return
    if os.environ.get("BOTCUT_FAKE") == "1":
        # Offline, a marked file is the second camera of the shot before it, started at the same moment.
        for index in sorted(marked):
            before = [other for other in spoken if other < index and other not in marked]
            if not before:
                raise SystemExit("A second camera needs a shot to be the second camera of")
            clips[index].update({"role": "angle", "of": before[-1], "offset": 0.0})
        return
    stamps = []
    for index in spoken:
        info = os.stat(clips[index]["path"])
        stamps.append([clips[index]["path"], info.st_size, info.st_mtime_ns, index in marked])
    cache = os.path.join(work, "cameras.json")
    try:
        known = json.loads(Path(cache).read_text())
        found = known["found"] if known.get("stamps") == stamps else None
    except (OSError, ValueError, KeyError, AttributeError):
        found = None
    if found is None:
        print("Listening for a second camera", flush=True)
        sounds = dict(zip(spoken, _pool_map(lambda index: sync.load(clips[index]["path"]), spoken)))
        found = {}
        # Process unmarked clips first so marked second cameras cannot chain onto another angle.
        order = [index for index in spoken if index not in marked] + [index for index in spoken if index in marked]
        for index in order:
            if sounds[index] is None:
                continue
            best = None
            for main in spoken:
                # A second camera follows the shot it belongs to in the list, unless the person marked it.
                if main == index or main in marked or str(main) in found or sounds[main] is None:
                    continue
                if index not in marked and main > index:
                    continue
                match = sync.line_up(
                    sounds[main], sounds[index], sure=sync.LIKELY if index in marked else sync.SURE
                )
                if match is None:
                    continue
                shared = match["end"] - match["start"]
                shorter = min(float(clips[main]["duration"]), float(clips[index]["duration"]))
                if index not in marked and shared < CAMERA_SHARE * shorter:
                    continue
                if best is None or match["score"] > best[1]["score"]:
                    best = (main, match)
            if best is not None:
                found[str(index)] = {"of": best[0], "offset": best[1]["offset"], "drift": best[1]["drift"]}
        Path(cache).write_text(json.dumps({"stamps": stamps, "found": found}) + "\n")
    for index in sorted(marked):
        if str(index) not in found:
            raise SystemExit(
                f"Could not line up {os.path.basename(clips[index]['path'])} with another shot. "
                "A second camera has to hear the same take."
            )
    for key, row in found.items():
        index = int(key)
        clips[index].update({"role": "angle", "of": int(row["of"]), "offset": float(row["offset"])})
        if row.get("drift"):
            clips[index]["drift"] = float(row["drift"])
        print(
            f"Two cameras: {os.path.basename(clips[index]['path'])} is the same take as "
            f"{os.path.basename(clips[int(row['of'])]['path'])}",
            flush=True,
        )


def plan_cameras(doc: dict, clips: list[dict], segs: list[dict], out: str) -> None:
    """Decide where the picture goes to another camera, and write it on the cut as `angles`.

    It is worked out again on every render, from the lines as they now are, so
    a line dropped later still has its jump cut hidden. What the person asked
    for in `cameras` is kept and followed.
    """
    from botcut.media import grab_still

    for key in ("angles", "angles_reply"):
        doc.pop(key, None)
    if not cameras.groups(clips) or not doc.get("lines"):
        return
    asked = cameras.read_cameras(doc.get("cameras"), clips)
    if cameras.write_cameras(asked):
        doc["cameras"] = cameras.write_cameras(asked)
    else:
        doc.pop("cameras", None)
    lines = doc["lines"]
    runs = cameras.plan(
        lines,
        segs,
        clips,
        beats=(doc.get("outline") or {}).get("beats"),
        close=doc.get("close"),
        cameras=asked,
    )
    by_id = {int(line["id"]): line for line in lines if isinstance(line, dict) and "id" in line}
    stills = os.path.join(out, "work", "stills")
    if os.environ.get("BOTCUT_FAKE") != "1" and runs:
        def _grab_run(run: dict) -> None:
            # A frame of the other camera at the moment the run starts, for the row that shows it.
            first = by_id.get(run["line"])
            if first is None:
                return
            clip = clips[run["clip"]]
            at = cameras.angle_time(clip, (float(first["start"]) + float(first["end"])) / 2)
            still = os.path.join(stills, f"angle-{run['clip']}-{run['line']}.jpg")
            if cached_still(clip["path"], at, still):
                run["still"] = os.path.abspath(still)

        _pool_map(_grab_run, runs)
    if runs:
        doc["angles"] = runs
    if not asked["off"]:
        doc["angles_reply"] = cameras.reply(runs, clips, cameras.shown_seconds(runs, lines, segs, clips))


def _attach_stills(utts: list[dict], clips: list[dict], directory: str) -> None:
    """One JPEG at the middle of each line. A missed frame does not stop the cut."""
    print("Reading pictures", flush=True)
    os.makedirs(directory, exist_ok=True)

    def grab(utt: dict) -> None:
        clip = clips[int(utt["clip"])]
        dur = float(clip.get("duration") or 0)
        mid = (float(utt["start"]) + float(utt["end"])) / 2
        if dur > 0:
            mid = min(max(0.0, mid), max(0.0, dur - 0.05))
        dest = os.path.join(directory, f"{int(utt['id'])}.jpg")
        if cached_still(clip["path"], mid, dest):
            utt["still"] = os.path.abspath(dest)

    # Each still is one short ffmpeg seek, so several at once is the quick way through a long list.
    _pool_map(grab, utts)


def _review(doc: dict, segs: list, zoom: str = "off") -> None:
    """Note on the cut the few spots worth a look, so the window can lead the person to them."""
    from botcut import check

    doc.pop("review", None)
    if doc.get("mode") != "speech" or not doc.get("lines"):
        return
    target = float((doc.get("outline") or {}).get("target_seconds") or 0)
    found = check.review(doc["lines"], segs, target, hidden=zoom != "off" or bool(doc.get("angles")))
    if found:
        doc["review"] = found


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
    clock: _Clock | None = None,
    fresh: bool = False,
    zoom: str = "off",
    resolution: str = "source",
    aspect: str = "source",
    out_file: str | None = None,
    pip: bool = False,
    music: str | None = None,
    live_title: str | None = None,
) -> None:
    if resolution != "source":
        doc["resolution"] = resolution
    else:
        doc.pop("resolution", None)
    if aspect != "source":
        doc["aspect"] = aspect
    else:
        doc.pop("aspect", None)
    if pip:
        doc["pip"] = True
    else:
        doc.pop("pip", None)
    if music:
        doc["music"] = os.path.abspath(music)
    else:
        doc.pop("music", None)
    if live_title and str(live_title).strip():
        doc["live_title"] = str(live_title).strip()
    else:
        doc.pop("live_title", None)
    if out_file is None:
        _review(doc, segs, zoom)
        _write_doc(out, doc)
    if not segs:
        raise SystemExit("No segments to render")
    dst = os.path.abspath(out_file) if out_file else os.path.join(out, "rough_cut.mp4")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    work = os.path.join(out, "work")
    _level_clips(work, clips)
    if doc.get("angles"):
        from botcut.color import match_cameras

        match_cameras(work, clips)
    if zoom != "off" or aspect == "portrait" or pip:
        # Where the speaker is at each line (and on second cameras), for zoom, PiP, and portrait framing.
        faces_along(work, clips, doc.get("lines"), angles=doc.get("angles"))
    if clock:
        clock.lap("level")
    made = render_with_progress(
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
        zoom=zoom,
        close=doc.get("close"),
        angles=doc.get("angles") or None,
        resolution=resolution,
        aspect=aspect,
        work_dir=work,
        pip=pip,
        music=music,
        live_title=live_title,
    )
    kept_s = sum(seg["end"] - seg["start"] for seg in segs)
    total_s = sum(clip["duration"] for clip in clips)
    print(f"Wrote {os.path.abspath(dst)} ({kept_s:.1f}s of {total_s:.1f}s)")
    if made and not fresh and made["pieces"] > made["made"]:
        # A change to a cut that was already rendered only makes what the change touched.
        print(f"Made {made['made']} of {made['pieces']} pieces again.", flush=True)
    if clock and out_file is None:
        clock.lap("render")
        _took(out, clock, fresh)


def render_saved(
    cuts: str,
    scene_transition: str = "dip",
    broll_sound: str = "mix",
    zoom: str = "off",
    resolution: str | None = None,
    aspect: str | None = None,
    out_file: str | None = None,
    pip: bool | None = None,
    music: str | None = None,
    live_title: str | None = None,
) -> None:
    """Encode rough_cut.mp4 from a cuts.json the tray has already confirmed."""
    clock = _Clock()
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
    def _probe_row(row: dict) -> dict:
        broll = str(row.get("role") or "") == "broll"
        clip = probe(row["path"], need_audio=not broll)
        if broll:
            clip["role"] = "broll"
        if str(row.get("role") or "") == "angle":
            clip["role"] = "angle"
            for key in ("of", "offset", "drift"):
                if key in row:
                    clip[key] = row[key]
        if row.get("view"):
            clip["view"] = row["view"]
        if row.get("face"):
            clip["face"] = row["face"]
        return clip

    clips = _pool_map(_probe_row, rows)
    lines = doc.get("lines") or []
    eff_live_title = live_title if live_title is not None else (doc.get("live_title") or None)
    newly_added_live_title = bool(eff_live_title and str(eff_live_title).strip()) and not bool(doc.get("live_title"))
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
        # The opening line plays first for as long as it is kept. Dropped, it opens nothing.
        # Adding a live title clears any lifted hook so the title fades over the actual opening footage.
        if newly_added_live_title or hook_line(lines, doc.get("hook")) is None:
            doc.pop("hook", None)
        # A line shown close is one that is still in the movie.
        close = close_ids(doc.get("close"), lines)
        if close:
            doc["close"] = close
        else:
            doc.pop("close", None)
        segs = play_order(segs, lines, doc.get("hook"))
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
    plan_cameras(doc, clips, segs, out)
    clock.lap("read")
    eff_res = resolution if resolution is not None else str(doc.get("resolution") or "source")
    eff_aspect = aspect if aspect is not None else str(doc.get("aspect") or "source")
    eff_pip = bool(doc.get("pip")) if pip is None else bool(pip)
    eff_music = music if music is not None else (doc.get("music") or None)
    eff_live_title = live_title if live_title is not None else (doc.get("live_title") or None)
    if eff_res not in RESOLUTIONS:
        eff_res = "source"
    if eff_aspect not in ASPECTS:
        eff_aspect = "source"
    _write_cut(
        out,
        doc,
        segs,
        clips,
        scene_transition,
        broll_sound,
        clock=clock,
        zoom=zoom,
        resolution=eff_res,
        aspect=eff_aspect,
        out_file=out_file,
        pip=eff_pip,
        music=eff_music,
        live_title=eff_live_title,
    )


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
    return settle(cut_words(tighten(segs, silences, max_pause), lines), lines)


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
    work: str,
    index: int,
    stem: str,
    backend: str,
    flac: str,
    clip: dict,
    whisper_model: str,
    terms: list[str] | tuple[str, ...] = (),
) -> list:
    for cache in word_cache_candidates(work, index, stem, backend):
        if os.path.isfile(cache):
            print(f"cache hit {cache}")
            return json.loads(Path(cache).read_text())["words"]
    _ensure_flac(clip["path"], flac)
    if backend == "local":
        result = transcribe_local(flac, whisper_model, stem, terms)
    else:
        result = transcribe_xai(flac, terms)
    cache = word_cache_candidates(work, index, stem, backend)[0]
    Path(cache).write_text(json.dumps(result) + "\n")
    return result["words"]


def _drop_stale_caches(work: str, index: int, clip: dict, stt_label: str) -> None:
    """Forget what was heard in a shot if the file, or the transcriber, has changed.

    Caches are named by position and file name. A re-exported file with the
    same name, another Whisper model, or another list of names to listen for,
    must not be answered from the old one.
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
        same_file = (
            isinstance(known, dict)
            and known.get("size") == stamp["size"]
            and known.get("mtime_ns") == stamp["mtime_ns"]
        )
        for name in os.listdir(work):
            if not name.startswith(prefix) or name == os.path.basename(stamp_path):
                continue
            if same_file and not name.endswith(".words.json"):
                continue
            os.remove(os.path.join(work, name))
    Path(stamp_path).write_text(json.dumps(stamp) + "\n")


def _level_clips(work: str, clips: list[dict]) -> None:
    """Note how loud each spoken shot is, once, so the render can match them to each other."""
    from botcut.media import loudness

    os.makedirs(work, exist_ok=True)

    def heard(numbered: tuple[int, dict]) -> None:
        index, clip = numbered
        if is_card(clip["path"]) or is_broll(clip) or cameras.is_angle(clip) or not clip.get("audio", True):
            return
        cache = os.path.join(work, f"{index}-{Path(clip['path']).stem}.loudness.json")
        try:
            value = json.loads(Path(cache).read_text())["i"]
        except (OSError, ValueError, KeyError, TypeError):
            value = loudness(clip["path"])
            Path(cache).write_text(json.dumps({"i": value}) + "\n")
        if value is not None:
            clip["loudness"] = value

    _pool_map(heard, enumerate(clips))


def _beats_for_clip(work: str, index: int, stem: str, clip: dict) -> list:
    """Scene changes once per B-roll file. Still images are one beat. BOTCUT_FAKE uses fixed windows."""
    if clip.get("is_image"):
        return [(0.0, float(clip.get("duration") or 12.0))]
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
    _ensure_flac(clip["path"], flac)
    pairs = silences(flac, clip["duration"])
    Path(cache).write_text(json.dumps(pairs) + "\n")
    return pairs


def _stt_label(
    fake: bool, stt: str, whisper_model: str, terms: list[str] | tuple[str, ...] = ()
) -> str:
    """Which transcriber heard the shots, marked when it was given names to listen for."""
    if fake:
        return "fake"
    if stt == "local":
        return f"local:faster-whisper:{whisper_model}{terms_mark(terms)}"
    return f"xai:grok-voice-transcribe-2.0{terms_mark(terms)}"


def captions(
    cuts_path: str,
    burn: bool = False,
    style: str = "srt",
    lower_third: bool = False,
) -> None:
    out_dir, doc = load_cuts(cuts_path)
    mapped = remap_words(doc.get("segments") or [], load_words_by_clip(doc, out_dir))
    if not mapped:
        raise SystemExit("No words to caption")
    if style == "social":
        src = os.path.join(out_dir, "rough_cut.mp4")
        width, height = 1920, 1080
        if os.path.isfile(src):
            info = probe(src, need_audio=False)
            if int(info.get("width") or 0) > 0 and int(info.get("height") or 0) > 0:
                width, height = int(info["width"]), int(info["height"])
        kit = brand_kit.load_brand()
        lt = (kit["speaker_name"], kit["speaker_title"]) if lower_third and kit.get("speaker_name") else None
        ass_text = to_ass(mapped, width=width, height=height, brand=kit, lower_third=lt)
        ass_path = os.path.join(out_dir, "rough_cut.ass")
        Path(ass_path).write_text(ass_text, encoding="utf-8")
        print(f"Wrote {os.path.abspath(ass_path)}")
        if not burn:
            return
        require_subtitles()
        if not os.path.isfile(src):
            raise SystemExit(f"No such file: {src}")
        duration = float(probe(src, need_audio=False).get("duration") or 0)
        encoder, device = resolve_encoder()
        _run_ffmpeg_progress(
            burn_ass_args("rough_cut.ass", encoder=encoder, device=device),
            duration,
            "Burning captions",
            "Caption burn failed",
            cwd=out_dir,
        )
        print(f"Wrote {os.path.abspath(os.path.join(out_dir, 'rough_cut.captioned.mp4'))}")
        return
    srt = to_srt(mapped)
    if not srt.strip():
        raise SystemExit("No words to caption")
    srt_path = os.path.join(out_dir, "rough_cut.srt")
    Path(srt_path).write_text(srt)
    print(f"Wrote {os.path.abspath(srt_path)}")
    if not burn:
        return
    require_subtitles()
    src = os.path.join(out_dir, "rough_cut.mp4")
    if not os.path.isfile(src):
        raise SystemExit(f"No such file: {src}")
    duration = float(probe(src, need_audio=False).get("duration") or 0)
    encoder, device = resolve_encoder()
    _run_ffmpeg_progress(
        burn_args(encoder=encoder, device=device),
        duration,
        "Burning captions",
        "Caption burn failed",
        cwd=out_dir,
    )
    print(f"Wrote {os.path.abspath(os.path.join(out_dir, 'rough_cut.captioned.mp4'))}")


def _short_center(doc: dict, start_id: int) -> float | None:
    """Where the speaker of the highlight is across the frame. None keeps the crop in the middle."""
    clip_of = {int(line["id"]): int(line["clip"]) for line in doc.get("lines") or [] if "id" in line}
    wanted = clip_of.get(start_id)
    for row in doc.get("clips") or []:
        if int(row.get("index", -1)) == wanted and row.get("face"):
            return focus(row)[0]
    return None


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
    srt = to_srt(window)
    if not window or not srt.strip():
        raise SystemExit("No words to caption")
    Path(os.path.join(out_dir, "short.srt")).write_text(srt)
    src = os.path.join(out_dir, "rough_cut.mp4")
    if not os.path.isfile(src):
        raise SystemExit(f"No such file: {src}")
    require_subtitles()
    info = probe(src)
    encoder, device = resolve_encoder()
    _run_ffmpeg_progress(
        short_args(
            start,
            length,
            int(info["width"]),
            int(info["height"]),
            encoder=encoder,
            device=device,
            center=_short_center(doc, int(choice["start_id"])),
        ),
        length,
        "Rendering short",
        "Short render failed",
        cwd=out_dir,
    )
    dst = os.path.abspath(os.path.join(out_dir, "short.mp4"))
    print(f'Wrote {dst} "{choice["title"]}" ({length:.1f}s)')


def load_cuts(cuts_path: str) -> tuple[str, dict]:
    path = cuts_path
    if os.path.isdir(path):
        path = os.path.join(path, "cuts.json")
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise SystemExit(f"No such file: {path}")
    try:
        doc = json.loads(Path(path).read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Cannot read {path}: {exc}") from exc
    return os.path.dirname(path), doc


BROLL_PREFIX = "b-roll "
ANGLE_PREFIX = "angle "


def _shot_list(path: str) -> list[tuple[str, str]]:
    """One path per line. A line that starts with `b-roll ` or `angle ` marks that file."""
    if not os.path.isfile(path):
        raise SystemExit(f"No such file: {path}")
    rows = []
    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith(BROLL_PREFIX):
            rows.append((stripped[len(BROLL_PREFIX) :].strip(), "broll"))
        elif stripped.lower().startswith(ANGLE_PREFIX):
            rows.append((stripped[len(ANGLE_PREFIX) :].strip(), "angle"))
        else:
            rows.append((stripped, ""))
    if not rows:
        raise SystemExit(f"No paths in {path}")
    return rows


def _is_shot_list(files: list[str]) -> bool:
    return len(files) == 1 and files[0].lower().endswith(".txt")


def resolve_inputs(files: list[str]) -> list[str]:
    if _is_shot_list(files):
        return [path for path, _role in _shot_list(files[0])]
    return list(files)


def resolve_broll(files: list[str]) -> list[str]:
    """The files a shot list marks B-roll. Plain arguments mark none."""
    if _is_shot_list(files):
        return [path for path, role in _shot_list(files[0]) if role == "broll"]
    return []


def resolve_angles(files: list[str]) -> list[str]:
    """The files a shot list marks as a second camera."""
    if _is_shot_list(files):
        return [path for path, role in _shot_list(files[0]) if role == "angle"]
    return []
