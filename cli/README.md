# botcut-cli

Rough-cut one ordered list of shots. The Qt app calls `run`, `render`, `captions`, and `short`. It does not run `review` after a cut.

```bash
cd cli
uv run botcut-cli run a.mp4 b.mp4 c.mp4 --out out/
uv run botcut-cli run shots.txt --out out/ --mode assemble
```

`--mode speech` (the default) keeps the moments that match `--intent`. The default intent keeps each moment, drops flubs and true retakes, and keeps a beat that appears once. Wording about repeated takes uses the retake prompt instead. `--decide` writes `cuts.json` and stops before ffmpeg. `botcut-cli render out/` encodes after a line is restored. `--mode assemble` keeps every file from start to end, in the order given, and does not call speech-to-text or the model. Use it for riding, B-roll, and any clip that should appear even when nobody is talking.

A single `.txt` argument is a shot list, one path per line. Blank lines and `#` comments are skipped.

`out/cuts.json` is the cut list. `out/rough_cut.mp4` is the listening render. Word timestamps are cached at `out/work/<i>-<stem>.<stt>.words.json`. An older `out/work/<i>-<stem>.words.json` still counts as an xAI cache hit. A second run prints `cache hit` and does not call speech-to-text again.

```bash
uv run botcut-cli run a.mp4 --out out/ --stt local --whisper-model large-v3-turbo
uv run botcut-cli run a.mp4 --out out/ --max-pause 0.8 --no-snap
uv sync --extra local
```

`--stt` is `xai` (default) or `local`. Local transcription is faster-whisper on CPU int8 and needs `uv sync --extra local`. `--max-pause` (default `0.8`) splits a kept range when a silence inside it is longer than that. `--no-snap` leaves the padded edges where they are. Otherwise an edge that lands in silence moves to 0.10 s before speech or 0.15 s after it, and a snap that would leave less than 0.3 s is skipped.

## Environment

| Variable | Default | Role |
|---|---|---|
| `XAI_API_KEY` | unset | Sent only as an Authorization header. Never written to `cuts.json` or logs. |
| `BOTCUT_LLM_BASE_URL` | `https://api.x.ai/v1` | Chat completions base URL. |
| `BOTCUT_LLM_MODEL` | `grok-4.7` | Model that returns keep ids and reasons. Grok 4.5 and newer are asked for low reasoning effort. |
| `BOTCUT_FAKE` | unset | `1` skips the network: a fixture transcript, every id kept with reason `fake`. |

Speech-to-text is `grok-voice-transcribe-2.0` with filler words kept. The model chooses utterance ids. It does not choose timestamps. One JPEG from the middle of each line is sent with the transcript, and stored under `out/work/stills/`. A missed frame does not stop the cut. The reason may mention the picture.

Kept neighbors in the same clip merge when the gap before padding is under 1 second. Each range is then padded by 0.25 seconds before and 0.40 seconds after, and clamped to the clip. The later utterance's reason is the one stored on a merged range. The rough cut levels the clips, fades up from black, and fades out to black. Joins inside one file fade the audio by 20 ms. Between source files the picture dips through black and the audio fades for 120 ms, unless `--scene-transition off`. The app remembers that choice for every movie. The review master stays a straight concat.

A dropped line that is not a near-duplicate of a kept line prints `unique? id N: ...`. The line stays dropped.

## Captions

```bash
uv run botcut-cli captions out/cuts.json
uv run botcut-cli captions out/cuts.json --burn
```

`captions` writes `out/rough_cut.srt` from the word cache under `out/work/`. Cues stay within 32 characters and 2.0 seconds, and break when the next word is more than 0.4 seconds away. `--burn` also writes `out/rough_cut.captioned.mp4`: Inter 18 bold, a 2px outline, bottom center. Words are not stored in `cuts.json`.

## Short

```bash
uv run botcut-cli short out/cuts.json
```

`short` asks for one contiguous highlight and writes `out/short.mp4` at 1080×1920 with those captions burned in. It prints `Wrote <path> "<title>" (<len>s)`. Landscape frames are center-cropped with `crop=ih*9/16:ih` and then scaled. A frame that is already 9:16 or taller is only scaled. `BOTCUT_FAKE=1` uses the first three kept lines and does not call the network. A real highlight is asked to land between 30 and 60 seconds; a shorter range is still used when that is what comes back.

## Review

```bash
uv run botcut-cli review out/cuts.json
uv run botcut-cli review out/cuts.json --no-open
```

`review` builds `out/master.mp4` from every shot, in order, and writes `out/master.keep.json` with the rough-cut ranges in master time. When the shots share a codec, size, frame rate, and audio format, the master is a stream copy. Otherwise it is re-encoded the same way as the rough cut. A stream copy that drifts by more than 0.1 seconds per clip prints `master drift …s; re-encoding` and is rebuilt. A second run prints `master up to date`. BotCut opens the keep-list when `botcut` is on `PATH`. `--no-open` skips that. `rough_cut.mp4` stays where it is.
