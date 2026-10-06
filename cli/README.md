# botcut-cli

Rough-cut one ordered list of shots. The Qt app is unchanged in this step.

```bash
cd cli
uv run botcut-cli run a.mp4 b.mp4 c.mp4 --out out/
```

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
| `BOTCUT_LLM_MODEL` | `grok-4.3` | Model that returns keep ids and reasons. |
| `BOTCUT_FAKE` | unset | `1` skips the network: a fixture transcript, every id kept with reason `fake`. |

Speech-to-text is `grok-voice-transcribe-2.0` with filler words kept. The model chooses utterance ids. It does not choose timestamps.

Kept neighbors in the same clip merge when the gap before padding is under 1 second. Each range is then padded by 0.15 seconds before and 0.25 seconds after, and clamped to the clip. The later utterance's reason is the one stored on a merged range.

A dropped line that is not a near-duplicate of a kept line prints `unique? id N: ...`. The line stays dropped.
