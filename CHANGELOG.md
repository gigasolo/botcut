# Changelog

User-facing changes in this fork. Dates are the days the work landed on `master`.

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
