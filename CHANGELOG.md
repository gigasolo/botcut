# Changelog

User-facing changes in this fork. Dates are the days the work landed on `master`.

## 2026-11-15

- BotCut cuts inside a line now, not only whole lines. An "um" or "uh", and words said twice in a row as a stumbled restart, are found from the word timings and offered to the model by number. It says which come out and leaves a repeat that was meant, like "no, no". It never returns a time.
- A kept line shows its cuts in place: struck through when taken out, underlined when left in. Click one to flip it, then **Update movie**. In the chat, "leave the ums in" or "take out every um" changes them all at once, as a proposal to apply.
- Captions follow the cuts, so a word that was cut is not in the subtitles.
- Every movie comes out with clean, level sound, and there is nothing to set. Each shot's voice is matched to the others before the join, so a quiet take does not sit quiet beside a loud one. Low rumble is removed and steady hiss is brought down a little. The whole movie is then set to -16 LUFS with one steady gain, measured in a quick listening pass before the encode. Three camera clips at -32, -17, and -19 LUFS come out at -17, -16, and -16.
- One press makes the movie. **Cut** transcribes, chooses the lines, lays the B-roll, renders, and puts the movie in `~/Videos/BotCut`, named after the first shot. It opens on Movie, playing. There is no stop at Lines, no Render press, and no save dialog on the way.
- Lines and the chat are where you change it afterwards. After a line, the pace, the fade, or a handle changes, the filled button reads **Update movie** on Lines and on Movie, and it renders over the same file. When the movie already has the lines, Lines has no filled button.
- A cut is kept as a project under `~/.local/share/botcut/projects`, not in `/tmp`. A movie opened from Recents after a restart comes back with its lines, its shots, and its chat history file, and can be changed again. A project whose movie has been deleted is cleaned up after a day.
- **Save a copy…** replaces **Export another size…**. It copies the movie as it stands, or re-encodes it smaller, and leaves the movie on screen alone.
- A render that fails after the lines were chosen keeps the lines. Only the render is left to try again.
- The progress bar runs once across the whole cut, through transcribing, choosing, B-roll, and rendering. It used to stay empty until the render.
- Shots are transcribed four at a time on xAI. Stills are grabbed four at a time and reused on a second run.
- A shoot of more than 150 lines is sent to the model in overlapping parts, each with its own stills, and the answers are merged. A reply that is not the expected shape is asked for once more before the cut stops.
- A re-exported shot with the same name, or another Whisper model, no longer gets the old transcript. A sound file or B-roll file ffmpeg cannot read stops the cut and says so, where it used to pass as "no pauses" or "no cuts".
- A job that fails now says why and keeps saying it. The reason stays in the action bar, in the accent color, until you try again or move on. Before, a bad key, no network, or a failed cut fell back to the usual sentence with no word of what happened.
- Stop sits beside the progress button and ends the running job, along with any ffmpeg it started. It is not a failure and says nothing.
- Saving an xAI key asks xAI whether it accepts it. A refused key is forgotten and Settings says so. With no network the key is kept. Save key does nothing with an empty field, Forget key is its own button, and Done keeps a key you typed but did not save.
- Captions and the vertical short land beside the movie you saved, as `movie.srt` and `movie_short.mp4`. They were written to the temporary cut folder and reported as failed.
- Keeping a dropped line saves the list at once, as dropping one does.
- `botcut some.botcut.json` opens that list.
- BotCut is one product now. The separate one-file trimmer is gone: no **Trim one file instead…**, no Ctrl+O, no keep-list files, and no split or join on the filmstrip. Trimming stays where it is useful, on the finished movie.
- One way per thing. X is the key that drops or keeps a line, and K and D are gone. Fade is the switch under the picture, and its copy in Settings is gone.
- `botcut-cli review` is removed. The app never ran it.
- The window finds `botcut-cli` through `BOTCUT_CLI`, then `PATH`, then `uv` with the `cli` folder of the checkout it was built from. The path `~/code/botcut/cli` is no longer written into the app.

## 2026-11-09

- B-roll is laid like an editor would: in runs of three to twelve seconds over one or more lines, to hide a cut, to show what the words describe, or to rest the viewer. The first and last lines stay on the speaker, runs are spaced out, and the footage moves forward. Covering nothing is allowed. The movie line steers it.
- The chat opens after a cut with the model's own sentence about what it laid and why, and "B-roll over 3 stretches, 31 s." Nothing waits on Apply. "Less B-roll" or "none over the opening" in the chat comes back as a proposal.
- The first line of a run shows a still from the footage, the file, the run's length, and the reason. The lines under it read "B-roll goes on". Remove B-roll on any of them takes the run.
- A run plays as one piece in the movie and in the preview, across the cuts inside it, with no fade on those joins.

## 2026-11-08

- B-roll covers about half of the spoken lines, spread from the first line to the last, with the beats in order so the footage moves forward. The model sees each line's length, and a line under a second and a half is never covered. The first real cut had laid two beats over fifty lines.
- Play on a line, or the kept lines in a row, shows the B-roll picture over a covered line while the voice goes on. Before, only the rendered movie showed a cover.
- The action sentence on Lines counts the covered lines: "50 of 56 lines kept, 2:40, 15 with B-roll."

## 2026-11-06

- A full-range B-roll clip, such as a HoverAir file, renders beside the DJI shots. Each branch brings a full-range source to limited range before the join, where VA-API frames could not be converted. A failed render now names ffmpeg's actual complaint instead of its last line.

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
