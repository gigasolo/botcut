# Changelog

User-facing changes in this fork. Dates are the days the work landed on `master`.

## 2026-10-12

- Change this cut revises the lines, the sentence, the pace, and Dip to black. It does not encode. Revert puts the previous cut back.
- Open card and Close card add a shot at the front or the end of the tray. The footer reads "Making the card…". One job runs at a time.
- Watch on a plan cut trims each source range. An untouched plan still Saves by copying. After a handle moves, Export re-encodes, and Captions and Short wait for that export.
- At the minimum window the sentence, the pace, the cards, the lines, Render, and the footer stay on screen. The sentence shrinks before a line row does. The pace stays locked while a job runs.

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
