# botcut-cli

Rough-cut one ordered list of shots. The Qt app calls `run`, `render`, `revise`, `card`, `captions`, and `short`.

```bash
cd cli
uv run botcut-cli run a.mp4 b.mp4 c.mp4 --out out/
uv run botcut-cli run shots.txt --out out/ --mode assemble
```

The package needs `numpy` and `opencv-python-headless` beside `requests`. `uv` installs them on the first run; a `botcut-cli` installed some other way has to be installed again.

`--mode speech` (the default) keeps the moments that match `--intent`. The default intent keeps each moment, drops flubs and true retakes, and keeps a beat that appears once. Wording about repeated takes uses the retake prompt instead. `--decide` writes `cuts.json` and stops before ffmpeg. `botcut-cli render out/` encodes after a line is restored. `--mode assemble` keeps every file from start to end, in the order given, and does not call speech-to-text or the model. Use it for riding and any clip that should appear even when nobody is talking.

`--b-roll-file PATH` marks one of the files as B-roll. Give it once per file. A B-roll file is not transcribed and never becomes a line. It is sliced into beats of one to four seconds at its scene changes, one still is taken per beat, and the model lays runs over the spoken lines the way an editor would: a run starts on a beat and goes on for 3 to 12 seconds over one or more consecutive kept lines, ending on a line, to hide a cut, show what the words describe, or rest the viewer. It sees the movie line, every line with its length, where the cuts fall, and a still per beat. It returns beat and line ids, a reason of a few words per run, and one or two sentences for the person. The first and last kept lines stay on the speaker, runs never sit back to back, and beats go up so the footage moves forward. The voice always keeps playing. `--b-roll-sound mix` (the default) plays the B-roll sound at a quarter under the voice. `--b-roll-sound voice` plays the voice alone. A B-roll file with no sound track is fine. A spoken file without one is still refused. A card cannot be B-roll, and a `--b-roll-file` that is not one of the files stops the run. `--mode assemble` ignores the mark, because it plays every file in order with its own sound.

### A second camera

Two files that filmed the same take are two cameras on it. `run` finds them itself: a later file that heard the same sound as an earlier one for at least half its length is that shot's second camera. `--angle-file PATH` marks one by hand, once per file, and is believed on a weaker match; a marked file that matches no shot stops the run with "Could not line up". The first file is nobody's second camera, and a file is B-roll or a second camera, not both.

The two are lined up by sound, in `sync.py`, with no model: the loudness of each a hundred times a second gives the shift to a hundredth of a second, the waveforms near it give the rest, and a camera that runs a little slow is followed across a long take. What was found is kept in `out/work/cameras.json`. A second camera is not transcribed, never becomes a line, and is never heard. Its clip row in `cuts.json` carries `"role": "angle"`, `of` (the shot it belongs to), `offset` and `drift` (a moment `t` of that shot is at `t + offset + drift * t` in this file), and `view` when the model was shown a still of each camera and said which is `wide`, `close`, or `side`.

Where the picture changes is decided by rule in `angles.py` and written as `angles`, runs of lines like the B-roll runs: `{clip, of, line, through, reason, still}`. The view changes only between lines, only after it has been held, and only to a camera that was running for the whole line: at a jump cut (`hides a cut`), at the first line of a beat, on a line named in `close` when one camera is the close view, and after a long hold at the end of a sentence. It is worked out again on every `render`, so a line dropped later still has its jump hidden. `cameras` holds what was asked for and is kept: `pace` (`calm` holds 6 seconds and changes after 30, `normal` 4 and 18, `busy` 2.5 and 10), `favor` (the camera to stay on most), `stay` (line ids held on the first camera), and `off`. `revise` returns `cameras` (`same`, `calm`, `normal`, `busy`, `off`) and `favor`. B-roll over a line wins the picture from the second camera. `angles_reply` is one sentence about what was done.

A single `.txt` argument is a shot list, one path per line. A line that starts with `b-roll ` marks that file, and one that starts with `angle ` marks a second camera. Blank lines and `#` comments are skipped.

`out/cuts.json` is the cut list. A B-roll clip row carries `"role": "broll"`, and a cover is a run: `{clip, line, through, start, end, reason, still}`, the first and last line ids, the window inside the B-roll file, the model's reason, and the starting beat's still. `covers_reply` is the model's sentence about what it laid. `revise` sees the beats and the runs and returns the full list of runs to keep. `out/rough_cut.mp4` is the listening render. Word timestamps are cached at `out/work/<i>-<stem>.<stt>.words.json`. An older `out/work/<i>-<stem>.words.json` still counts as an xAI cache hit. Beats are cached at `out/work/<i>-<stem>.beats.json`. A second run prints `cache hit` and does not call speech-to-text again.

```bash
uv run botcut-cli run a.mp4 --out out/ --stt local --whisper-model large-v3-turbo
uv run botcut-cli run a.mp4 --out out/ --max-pause 0.8 --no-snap
uv sync --extra local
```

`--stt` is `xai` (default) or `local`. Local transcription is faster-whisper on CPU int8 and needs `uv sync --extra local`. `--max-pause` (default `0.8`) splits a kept range when a silence inside it is longer than that. A silence is sound under -35 dB, or, in a shot with more going on behind the voice, under 8 dB above that shot's own quiet end, and never within 12 dB of the voice. `--no-snap` leaves the padded edges where they are. Otherwise an edge that lands in silence moves to 0.10 s before speech or 0.15 s after it, and a snap that would leave less than 0.3 s is skipped.

## Environment

| Variable | Default | Role |
|---|---|---|
| `XAI_API_KEY` | unset | Sent only as an Authorization header. Never written to `cuts.json` or logs. |
| `BOTCUT_LLM_BASE_URL` | `https://api.x.ai/v1` | Chat completions base URL. |
| `BOTCUT_LLM_MODEL` | `grok-4.7` | Model that returns keep ids and reasons. Grok 4.5 and newer are asked for low reasoning effort, and for high on the two requests that read the whole movie. |
| `BOTCUT_LLM_EFFORT` | unset | `low`, `medium`, `high`, or `xhigh` asks for that effort on every request, so the bench can price the difference. |
| `BOTCUT_FAKE` | unset | `1` skips the network: a fixture transcript, every id kept with reason `fake`. |

Speech-to-text is `grok-voice-transcribe-2.0` with filler words kept. Only the sound is sent: each shot's audio is written to `out/work/<n>-<name>.flac` at 16 kHz mono, and that file is what is uploaded. The model chooses utterance ids. It does not choose timestamps. One JPEG from the middle of each line is sent with the transcript, and stored under `out/work/stills/`. A missed frame does not stop the cut. The reason may mention the picture. A dropped connection, a timeout, or a brief server error is tried again. A rejected key or body is not.

A line can also be cut inside. Besides the cuts on offer below, the model returns `trim` for a line it keeps: words copied from the line that should come out, such as "you know" or the abandoned start of a thought. They are found in the line, timed from the word times, and written among the line's `cuts` with reason `trimmed` and `cut: true`. Words that are not in the line, that are most of it, or that take half of a cut already on offer, are left alone. A piece under 0.6 seconds with nobody speaking in it, like the padding in front of a line whose first "um" was cut, is left out of the movie.

`word_cuts` finds filler sounds (um, uh, er, hmm) and a phrase of one to three words said twice in a row, and works out the seconds each spans from the word times, leaving 40 ms of air on each side and skipping anything under 0.15 seconds. The model is shown them by number on the line, `{cuts: 0="um", 1="we were"}`, and returns the numbers to take for each line it keeps. Every cut on offer is written to the line in `cuts.json` as `cuts: [{from, through, start, end, reason, cut}]`, where `cut` says whether it is taken, so the window can flip one and `render` applies it. `revise` returns `fillers`: `cut` takes them all, `keep` leaves them all, `same` changes none. Kept neighbors in the same clip merge when the gap before padding is under 1 second. Each range is then padded by 0.25 seconds before and 0.40 seconds after, and clamped to the clip. The later utterance's reason is the one stored on a merged range. The sound is cleaned and leveled on every render: each spoken shot is measured once (`work/<n>-<name>.loudness.json`) and given the gain that matches it to the others, by at most +20 dB or -12 dB; the joined sound goes through `highpass=f=70,afftdn=nr=8:nf=-50:tn=1`; and a first pass with no picture measures it so `loudnorm` can set -16 LUFS, -1.5 dBTP with one linear gain. A B-roll shot's own sound is not matched. It stays a bed at a quarter of its level. A cut too quiet to measure is cleaned and left at its own level. The rough cut keeps the camera level, fades up from black, and fades out to black. A join inside a file is a crossfade: each side reaches 12 ms into the other. Across a dip the sound fades 120 ms down and up, unless `--scene-transition off`.

The movie is made in pieces. The sound is put together in one pass, and each piece of picture is encoded to its own file under `out/work/pieces`, named by what it shows, and joined without encoding again. Every piece is a whole number of frames and starts on a frame of its source, so picture and sound stay together across any number of joins. A later `render` of the same cut makes only the pieces that changed and prints `Made 1 of 80 pieces again.` A piece no render has used for two days is removed. `BOTCUT_RENDER=graph` renders the older way, as one filter graph in one encode. The app remembers that choice for every movie.

A dropped line that is not a near-duplicate of a kept line prints `unique? id N: ...`. The line stays dropped.

### Names

A name or a product word is where a transcript goes wrong: "Telnyx" comes back as "tell next". Put the ones you say in `~/.config/botcut/names.txt` (or under `$XDG_CONFIG_HOME`), one a line. A blank line or a line starting with `#` is skipped. They are sent with every transcription as words to lean toward, along with any names in the movie sentence: a capital that does not just open a sentence, like Lynn, MCP, or VirtualPBX. xAI takes at most 100, of at most 50 characters each; the list comes first and the rest are left off. The `stt` field in `cuts.json` ends in a short mark when names were sent, and a shot is transcribed again when the names change. Local Whisper is given the same names.

### Stage times

A cut ends with one line saying where the time went, longest first: `Took 6m39s: render 4m45s, choose 1m16s, stills 28s, listen 9s.` The seconds for every stage are kept in `out/work/seconds.json`: `read`, `beats`, `listen` (audio, transcript, silences), `stills` (stills and the speaker's face), `outline`, `choose`, `proof`, `covers`, `level`, and `render`. A later `render` of the same cut replaces its own stages there and leaves the rest.

A shoot of 150 lines or fewer is read and cut in one request: the outline below and the keep list come back together, and the stage is `choose`. `BOTCUT_FOLD=0` keeps the two apart. A longer shoot is outlined while its stills are read, then chosen in parts.

Otherwise a cut asks the model three things, in order. First it reads every line of the shoot at once, as words only, and returns an outline: the beats, the groups of lines that say the same thing however far apart, one line the movie could open on, and the length the movie sentence asks for ("a ninety second update" is 90; no length is 0). A shoot under six lines has no outline. Then it chooses lines, as before, and each request is shown the beats, the retake groups that touch its lines with the words of the takes it cannot see, and, when a length was asked for, its share of it. When there are more stills than one request carries, retakes get them first. Last it reads the cut back as a viewer gets it: kept lines with their lengths, a `— cut —` row at each join, dropped lines in place, and what `check.py` noticed. It returns changes, not a new list: ids to drop, ids to put back, cut numbers to take, and one or two sentences that open the chat (`cut_reply`). A line it does not name stays as it was. With no length asked for, a proof that would take out more than 30 percent of the kept seconds is not applied. If the outline or the proof cannot be had, the cut goes on without it and prints `Cutting without an outline` or `Kept the cut as first made`.

The proof may also name one kept line for the movie to open on. `cuts.json` then carries `hook`, that line's id, and its piece is first in `segments` with `"hook": true`. The line leaves its place; nothing else moves, and `lines` stays in the order they were said. B-roll never runs across it, captions follow the new order, and the short is measured in the body of the movie. Dropping that line, or **Put it back** on its row, removes `hook`.

## Revise

```bash
uv run botcut-cli revise out/cuts.json --pace measured --scene-transition dip -- "Drop the second take"
```

`revise` rewrites the sentence, the pace, dip on or off, and which lines stay, and the model also returns a one or two sentence reply to the person. The note is the argument after `--`, so a note that looks like a flag stays text. It does not return times, padding, or a join other than dip. It does not start ffmpeg. `BOTCUT_FAKE=1` applies a fixture and does not call the network. Without a key, and with fake mode off, the command is refused.

```bash
uv run botcut-cli revise out/cuts.json --propose --history out/chat.json -- "Make it tighter"
uv run botcut-cli revise out/cuts.json --apply
```

`--propose` asks the model and writes `out/proposal.json` (the note, the reply, and the fields above) without touching `cuts.json`, and prints the reply. `--history PATH` passes earlier chat turns, a JSON list of `{"role": "you" | "bot", "text": "…"}`, before the note. `--apply` takes no note: it lands the proposal in `cuts.json`, with the same result as a plain `revise`, and removes `proposal.json`. The app always goes through `--propose` and `--apply`, so a change is shown and agreed to before it moves anything.

## Card

```bash
uv run botcut-cli card --out /path/botcut-card-open.mp4 -- "The movie in one sentence"
```

`key` asks xAI for its model list with `XAI_API_KEY` and exits 0 when the key is accepted. A refused key stops with "xAI did not accept that key." A network failure stops with "Could not reach xAI to check the key." `BOTCUT_FAKE=1` accepts any key and does not call the network.

`card` writes a 3 second 16:9 mp4. The destination file name starts with `botcut-card-` and ends in `.mp4`, and the directory is the app card directory. The sentence is the argument after `--`. `BOTCUT_FAKE=1` writes a tiny movie and does not call the network. A spoken cut keeps that file as one line with reason `card` and does not transcribe it.

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

`run` also asks the model where the speaker's face is in each spoken shot: one still, a third of the way in, answered as `{found, x, y, w, h}` in fractions of the picture, and kept in `work/<n>-<name>.face.json` and on the clip in `cuts.json` as `face`. A failed or missing answer is not an error. The zoom and the short frame the speaker with it. `BOTCUT_FAKE=1` uses a fixed box.

### Zoom

`run` and `render` take `--zoom off|auto|cuts|push|lines`. The default is `off`: every piece plays as shot. The others move in on the speaker's face, and leave B-roll, a second camera, cards, rotated shots, and shots under 1080 lines as shot. The face is found in the still of each line by a small detector that runs on this machine (`botcut/data`), kept in `work/faces.json`, and the nearest one in time is what a piece is framed on.

- `auto`: the three below together, as two framings, wide and a fifth closer. The picture goes from one to the other at a join between lines once it has been held 4 seconds; a line named in `close` is tight; a wide stretch of 8 seconds or more is given the slow push; and the speaker comes back wide from B-roll, another camera, or another shot. This is what the window's **Auto** is.

- `cuts`: across a join inside one shot the picture goes from wide to 1/1.12 of the frame, or back, so a jump cut reads as a change of shot. The framing never changes at a cut inside a line, such as an "um" taken out, and is held at least 4 seconds. A cut to another shot starts wide.
- `push`: each stretch between joins moves in by half a percent a second, up to 8 percent, toward the face, and starts wide again at the next join between lines. Across a cut inside a line it carries on from where it was. The picture is resampled between pixels on every frame (`perspective`, `eval=frame`), so the move does not step. It is the slowest to render: about 2.4 times the plain render on 4K.
- `lines`: the lines named in `close` play at 1/1.15 of the frame, the rest wide. The proof pass returns `close`, the ids of the few kept lines that carry the point: whole lines, never two that play one after the other, at most one in four, and none is a fine answer. It is saved in `cuts.json` on every cut, whatever the zoom, so choosing it later needs only a render. A named line is split out of the piece it sits in, with a quarter second of lead and 0.4 seconds of tail, never past the middle of the air to a neighbour. `revise` and `render` drop an id whose line is no longer kept. A cut made before this has no `close`, and nothing is zoomed.

`short` asks for one contiguous highlight and writes `out/short.mp4` at 1080×1920 with those captions burned in. It prints `Wrote <path> "<title>" (<len>s)`. Landscape frames are cropped to 9:16 around the speaker of the highlight's first line, or around the center when that shot has no face on record, and then scaled. A frame that is already 9:16 or taller is only scaled. `BOTCUT_FAKE=1` uses the first three kept lines and does not call the network. A real highlight is asked to land between 30 and 60 seconds; a shorter range is still used when that is what comes back.

## Bench

```bash
uv run botcut-cli bench save ~/Videos/BotCut/ride.mp4 ride
uv run botcut-cli bench run
uv run botcut-cli bench run ride --replay
uv run botcut-cli bench list
```

`bench save` keeps a finished cut as a case under `~/.local/share/botcut/bench/<name>/`: its `cuts.json` as you left it, the word and silence caches, and the line stills. It takes a movie, a project folder, or a `cuts.json`. Save a case after you have dropped, kept, and flipped what the model got wrong, because that list is what the model is scored against.

`bench run` builds the lines again from the saved words, asks the model to choose, and compares. Lines are weighed by their length. `precision` is the share of the seconds the model kept that you kept too. `recall` is the share of the seconds you kept that the model kept. `flipped` counts lines kept by one and not the other. `cuts` counts the cuts inside lines, on lines both kept, where the model and you agree. `jumps` counts the joins that show as a jump when nothing hides them: two pieces of the same shot with something taken out between lines. `flags` counts what a viewer would notice in the model's cut, with yours beside it for scale: `twice` is a point kept twice, `leans` is a line that opens on and, but, so, or because with the line before it dropped, and `flash` is a piece shorter than 0.6 seconds. No model is asked for these. One row per run is appended to `bench/history.jsonl` with the model, a short hash of the prompt wording, and every case's numbers, and the Overall line says what the last run over the same cases scored.

Each real answer is saved under the case's `replies/`, filed by the exact question that got it. `--replay` reads those and calls nothing. A prompt that has changed is a different question, so a replay of it stops with "The prompt changed since it was recorded" and needs a real run.

Every cut also carries `review`, the few spots worth a person's look, most telling first: `{kind, ids, text}` for two kept lines that say the same thing, a line that leans on a dropped one, a line dropped though nothing like it is kept, and a piece on screen for a blink, and one row saying how many jump cuts show when no zoom or second camera hides them. It is written again on every render.

`run` prints `Used N tokens in M requests.` and stores the counts in `cuts.json` as `usage`. Set `BOTCUT_PRICE_IN` and `BOTCUT_PRICE_OUT`, in dollars per million tokens, to add the cost.
