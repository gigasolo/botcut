# Changelog

User-facing changes in this fork. Dates are the days the work landed on `master`.

## 2026-11-06

- A full-range B-roll clip, such as a HoverAir file, renders beside the DJI shots. Each branch brings a full-range source to limited range before the join, where VA-API frames could not be converted. A failed render now names ffmpeg's actual complaint instead of its last line.

## 2026-11-09

- B-roll is laid like an editor would: in runs of three to twelve seconds over one or more lines, to hide a cut, to show what the words describe, or to rest the viewer. The first and last lines stay on the speaker, runs are spaced out, and the footage moves forward. Covering nothing is allowed. The movie line steers it.
- The chat opens after a cut with the model's own sentence about what it laid and why, and "B-roll over 3 stretches, 31 s." Nothing waits on Apply. "Less B-roll" or "none over the opening" in the chat comes back as a proposal.
- The first line of a run shows a still from the footage, the file, the run's length, and the reason. The lines under it read "B-roll goes on". Remove B-roll on any of them takes the run.
- A run plays as one piece in the movie and in the preview, across the cuts inside it, with no fade on those joins.

## 2026-11-08

- B-roll covers about half of the spoken lines, spread from the first line to the last, with the beats in order so the footage moves forward. The model sees each line's length, and a line under a second and a half is never covered. The first real cut had laid two beats over fifty lines.
- Play on a line, or the kept lines in a row, shows the B-roll picture over a covered line while the voice goes on. Before, only the rendered movie showed a cover.
- The action sentence on Lines counts the covered lines: "50 of 56 lines kept, 2:40, 15 with B-roll."

## 2026-11-05

- The window is the picture, the list, and one next action. The filled button sits beside its sentence in an action bar at the bottom. The steps are a breadcrumb in the top bar with no counts. The left column and the chat under the lines drag to resize, and the sizes are remembered.
- The chat is a transcript. BotCut replies in words with the change it would make, and nothing changes until you press Apply or answer yes. Leave it drops the proposal. Undo sits on the turn that changed the cut. `botcut-cli revise` takes `--propose`, `--history`, and `--apply`, and the model returns a `reply`.
- A line row has one word, Drop or Keep. Clicking a row is the one way to jump to a line. The block row under the picture is a plain timeline that shows where playback is and seeks on a click. Search, filters, the Review button, the count tiles, the key hints, Previous and Next, and the third column are gone.
- The movie sentence, the pace, and the fade are one row under the picture. Cover shots has no row: B-roll is marked on the shot, and the sound choice is in Settings.
- A shot can be marked B-roll on the shot list, and marked back as a shot. The row then reads "B-roll" where the size was. The saved list keeps the mark.
- A B-roll shot is not transcribed. It is sliced into beats of one to four seconds at its scene changes, and the model lays beats over spoken lines, choosing by the words and a still from each beat. One file can cover many lines. The voice always keeps playing.
- The "Cover lines with other shots" switch is gone. Marking a shot is the switch. The Decisions column counts the B-roll shots instead.
- "Keep a B-roll shot's sound under the voice" stays. Off now plays the voice alone instead of the clip's own sound. A B-roll file with no sound track is accepted.
- `botcut-cli run` takes `--b-roll-file PATH` and `--b-roll-sound mix|voice`. A `.txt` shot list marks a file with a `b-roll ` prefix. `--b-roll` and `--b-roll-sound clip` are gone.

## 2026-10-29

- Window colors come from the theme: background, surface, raised, and foreground. Opening a shot says "Opening…". A change to the line list says "Changing…".
- The window is one plan pane, and Settings, Help, and title cards are dialogs.
- Choosing 1080p or 720p when saving an unedited rough cut re-encodes to that size. Original still copies the file.
- The footer names the next action. A missing xAI key offers to add one. Quitting during a job asks first.

## 2026-10-12

- Cut in B-roll, off until Settings turns it on, covers a spoken line with a clip's picture. Mix the clip's sound under the voice is the default. Turning that off plays the clip's own sound.
- Change this cut revises the lines, the sentence, the pace, and Dip to black. It does not encode. Revert puts the previous cut back.
- Open card and Close card add a shot at the front or the end of the tray. The footer reads "Making the card…". One job runs at a time.
- Watch on a plan cut trims each source range. An untouched plan still Saves by copying. After a handle moves, Export re-encodes, and Captions and Short wait for that export.
- Watch names the line under the playhead on a plan cut.
- At the minimum window the sentence, the pace, the cards, the lines, Render, and the footer stay on screen. The sentence shrinks before a line row does. The pace stays locked while a job runs.
- The README and `docs/github-release.md` describe the local Arch package and how a GitHub release would be attached later. No release was published. The package still does not install `botcut-cli`.

## 2026-10-11

- Play on a line shows that segment, then pauses at the end. The picture sits beside the lines.
- The shot screen holds the movie sentence, a pace from Open to Frenzied, and Dip to black. Captions and Short stay available after Save.

## 2026-10-10

- The sidebar lists recent shot lists and finished cuts. A list reopens, a cut plays, and List on a cut reopens its shot list.

## 2026-10-09

- The README, the CLI notes, and `docs/` match the sidebar window, Spoken cuts, and the keyring.
- Spoken cuts send one still from the middle of each line with the transcript. The line row shows that still. A missed frame does not stop the cut.
- Each shot row shows a picture from one second into the file. While a cut is running, Open list, Add videos, reorder, remove, Trim one file, and the cut settings stay locked. Save list stays available.
- Shot pictures are kept until the clip's size or time changes. An empty picture pulses while it is being made. A brief network failure is tried again.

## 2026-10-08

- The window gathers several shots, cuts them, and then opens the trimmer on the rough cut.
- Spoken cuts uses one movie line, lists every kept and dropped line, and encodes only when you press Render. Turning it off keeps every file, in order, and needs no key.
- The xAI key is stored in the keyring. The window never shows the stored key.
- Save copies an unedited rough cut. A hand trim is exported as a new encode. Captions and a vertical Short are on the watch bar while that rough cut is still open.
- The window is a sidebar for Shots, Watch, Help, and Settings. Dip to black between files is a setting.

## 2026-10-06

- `botcut-cli captions` writes an SRT for the rough cut. `botcut-cli short` writes one 1080×1920 highlight.
- `botcut file.keep.json` opens that video with the keep ranges already laid out. Ctrl+Z once restores the full source.
- `botcut-cli review` builds a master and can open that keep-list. The app does not run review after a cut.
- Rough cuts snap to silences. `--stt local` transcribes with faster-whisper.
- The app is BotCut and installs beside stock Omacut. The Arch package name is `botcut`.

## 2026-10-05

- `botcut-cli run` rough-cuts an ordered list of shots.
