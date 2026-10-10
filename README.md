# BotCut

A fork of [Omacut](https://github.com/omacom/omacut) by David Heinemeier Hansson (MIT), extended with AI rough cuts from `botcut-cli`. Original copyright and license retained in `LICENSE`.

A dead-simple video trimmer, with a shot tray that can rough-cut several videos before you trim. Open a video, trim either end, split it into clips and cut ranges out of the middle, preview the result, and export. On Omarchy, the interface follows your theme's accent color.

Built using **Qt Quick (QML)** UI with the Material style — the same Qt stack Quickshell builds on — and **ffmpeg** for the cut. The C++ side compiles to a single executable; the QML is embedded in it via Qt resources.

<img width="3227" height="3227" alt="screenshot-2026-06-23_15-20-40" src="https://github.com/user-attachments/assets/c76047c8-618f-4c1c-91f9-e7024c4f953b" />

## Editing

The timeline shows your video as one or more clips, each framed with a handle at both ends. Whatever falls outside every clip is cut. Playback plays the clips in order and skips the gaps.

- **Double-click a clip** to split it there.
- **Drag a handle** to trim that clip. Dragging the handles at a split apart removes the part between them.
- **Double-click a gap**, or the line between two touching clips, to join them again.
- **Hover a clip** and click its **×** to remove it.

Handles catch on neighbouring clips and the playhead.

## Hotkeys

- *Space*: Start/stop video playback.
- *Left/Right*: Move the playhead by 1 second.
- *Shift+Left/Right*: Move the playhead by 5 seconds.
- *Alt+Left/Right*: Move the playhead by 0.2 seconds.
- *[ / ]*: Jump to the previous / next clip edge.
- *S*: Split the clip at the playhead.
- *X, Delete*: Remove the clip under the playhead; in a gap, restore it.
- *Ctrl+Space*: Move the start of the clip under the playhead to the playhead.
- *Alt+Space*: Move the end of the clip under the playhead to the playhead.
- *Ctrl+Z / Ctrl+Shift+Z*: Undo / redo.
- *Z*: Zoom to the clip under the playhead for fine tuning (Z again zooms back out).
- *Ctrl+O*: Open a new file to trim.
- *Ctrl+S*: Save or export the current movie.
- *Q*: Quit (asks first if the edit hasn't been exported).
- *?*: Show the hotkeys in the app.

## Several videos

With no movie open, the sidebar is on Shots. Drop videos or a folder onto the main column, or press **Add videos**. Files added together are ordered oldest first, from the file's creation time. The selected file plays in the preview. **Up** and **Down** show on the current row. **Remove** takes a file out. A missing file is marked, and **Cut** stays off until you remove it.

**Spoken cuts** is on by default. **Cut** transcribes the shots and lists the lines it would keep. **Drop** or **Restore** a line, then **Render** encodes `rough_cut.mp4`. It needs an xAI key. **Settings** stores that key in the keyring and never shows it again. Turning Spoken cuts off keeps every file, in this order, and does not call the model.

**Save list** writes the order, the cut mode, the movie line, and any lines. **Open list**, or dropping that file, puts them back. **Trim one file**, or Ctrl+O, opens one video in the trimmer.

Watch plays the rough cut. **Save** copies an unedited cut into the place you pick. **Export** re-encodes a hand trim. **Captions** and **Short** stay on the bar only while that rough cut and its `cuts.json` are still the open file. The same jobs on the command line are `botcut-cli run`, `render`, `captions`, and `short`. See `cli/README.md`.

**Settings** also holds the one-line movie prompt and **Dip to black between files**. Help, in the sidebar, lists the shortcuts above.

## Keep-lists

`botcut file.keep.json` opens that video with the keep ranges already laid out as clips. Ctrl+Z once restores the full source.

```json
{"source": "master.mp4", "keep": [{"start": 1.25, "end": 4.8, "label": "optional, ignored"}]}
```

Times are seconds in the source. A relative `source` resolves against the directory that contains the JSON file. Labels are ignored.

## Install

Install this fork next to stock Omacut with `./bin/install`. The Arch package name is `botcut`.

## Requirements

- `xdg-desktop-portal` and a portal backend for the file picker
- `ffmpeg` and `ffprobe` on your PATH (used at runtime)
- `libsecret`, so the xAI key can be stored in the keyring

Exports are always written as MP4 files, regardless of the input video's container. The export dialog offers Original/1080p/720p quality — never upscaling, and always preserving the aspect ratio.

## Build

Uses Qt's own build tool, `qmake6` (no cmake needed):

```bash
./bin/build
```

This produces a single `botcut` binary in `build/`.

Requirements:

- A C++17 compiler and Qt6: `qt6-base`, `qt6-declarative` (Qt Quick + Controls),
  `qt6-multimedia`
- `libsecret`

## Test

```bash
./bin/test
```

## Package

Build and install the local Arch package:

```bash
./bin/install
```

This runs `./bin/build`, then `makepkg -fsi` from `pkgbuild/` so same-version local packages are rebuilt and reinstalled. Extra arguments are passed through to `makepkg`, for example `./bin/install --clean`. The package installs the binary, desktop entry, app icon, and MIT license. Local package outputs such as `pkgbuild/pkg/`, `pkgbuild/src/`, and `*.pkg.tar.*` are ignored.

## License

MIT. See `LICENSE`.
