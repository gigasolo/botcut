BotCut is a dark desktop app for one person making a rough cut of a founder or small-business movie. The window is 960×680, minimum 960×640. There is one column. The person drops shot files, puts them in order, and presses Cut. The app transcribes the speech, keeps the useful lines, and plays the movie. They can drop a bad line, render again, watch the cut, trim it by hand, save it, write captions, or cut one vertical short.

The person using it is the founder, filming on a phone or a DJI camera and editing on a Linux desktop at night. They want the next movie, not a timeline. Speech is the structure. The order of the files is the order of the story.

What to draw

Draw only these surfaces:

• Shots, where the files are gathered
• Watch, where the movie plays and can be trimmed
• Settings, which covers the window
• Help, a shortcut card
• Close, a small confirm card

Every control is a text button, a checkbox, a text field, a list row, or the filmstrip. Play and pause are the only icon buttons. The help mark is a "?" circle at the top right.

What to leave out

Leave out a sidebar, a media bin, a timeline with tracks, effects, transitions, titles, music, color, keyframes, a waveform editor, and a multi-track mixer. Leave out account screens, pricing, and onboarding. Leave out gradients, glass, blur, and decorative illustration. Leave out icon-only toolbars.

Visual system

This has to be buildable in Qt Quick. Use flat rectangles, one accent, and the system sans. Status and times use a monospace face.

┌──────────────────────────────┬────────────────────────────────────────────────────┐
│ Role                         │ Value                                              │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Window                       │ #0e0e10                                            │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Raised button and hover chip │ #2c2c2f                                            │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Selected shot row            │ #2a2a2e                                            │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Dialog card                  │ #1c1c1e                                            │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Preview well                 │ black, 12 px corners                               │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Primary text                 │ #f4f4f5                                            │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Secondary text               │ #b8b8bc                                            │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Body on dialogs              │ #d6d6da                                            │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Quiet mark                   │ #7a7a80                                            │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Dropped line or missing file │ #e07a7a                                            │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Accent                       │ #FFD60A, text on it black                          │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Page margin                  │ 16 px                                              │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Footer gap                   │ 6 px                                               │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Shot row                     │ 40 px tall, 6 px corners                           │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Word button                  │ 44 px tall, 8 px corners, horizontal padding 14 px │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Filled button                │ accent fill, black label                           │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Plain button                 │ dark fill, white label                             │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Disabled                     │ 45% opacity                                        │
└──────────────────────────────┴────────────────────────────────────────────────────┘

The accent is the only yellow. It marks the one next action, the playhead, the trim handles, a missing xAI key when spoken cuts are on, and a short notice. It does not wash the whole window.

The window title is "BotCut". With a preview or a movie it becomes "BotCut — " plus the file name.

Sample content

Use these names so every frame feels like the same project.

Shots, in this order:

1. DJI_20261008_091204.MP4, selected
2. DJI_20261008_091418.MP4
3. DJI_20261008_092002.MP4, marked missing on the missing-file frame only
4. interview-founder.mov

Lines, after a decide:

┌──────┬────────────────────────────────────────────────────┬──────────────┬───────────────────────────┐
│ Time │ Words                                              │ Reason shown │ State                     │
├──────┼────────────────────────────────────────────────────┼──────────────┼───────────────────────────┤
│ 0:12 │ We started in the garage.                          │ Not sure     │ kept                      │
├──────┼────────────────────────────────────────────────────┼──────────────┼───────────────────────────┤
│ 0:41 │ The first customers were shops on the same street. │              │ kept                      │
├──────┼────────────────────────────────────────────────────┼──────────────┼───────────────────────────┤
│ 1:05 │ The first customers were shops on the same street. │ Dropped      │ dropped, words in #e07a7a │
├──────┼────────────────────────────────────────────────────┼──────────────┼───────────────────────────┤
│ 1:28 │ Then we opened the second location.                │ Put back     │ kept                      │
└──────┴────────────────────────────────────────────────────┴──────────────┴───────────────────────────┘

The preview still is a person talking in a small shop, 16:9, letterboxed inside a black frame. The movie still is the same person, larger, filling the watch screen.

The movie prompt, shown only in Settings when Spoken cuts is on:

Keep each moment in order. Drop flubs and true retakes. Keep a beat that appears only once.

Screen: Shots, empty

This is the first open. The preview fills the window. Centered in the black frame:

• "Drop shots here" in 18 px primary text
• "Put them in order. Then Cut." in 13 px secondary text

Under the preview, one full-width filled button: Add videos.

The footer is a single row. Open list, Save list (disabled), Trim one file, then a gap, then Cut (disabled, not filled), then Settings. There is no status line. There is no shot list and no Lines block. "?" sits at the top right and does not cover Settings.

Dropping files is allowed on this screen. While a drag is over the window, an accent stroke, 3 px, inset 8 px, with 12 px corners, frames the window. No fill.

Screen: Shots, files loaded, before a decide

The preview shrinks to a centered 16:9 frame, at most 280 px tall. The file name sits in a small black chip at the top left of that frame: DJI_20261008_091204.MP4. A play button sits at the bottom left of the frame. Clicking the picture plays and pauses the selected shot. It does not open a file.

Under the preview, Add videos is full width and no longer filled.

Then the shot list, which takes the leftover height and scrolls. Each row is the file name, elided in the middle, then Up, Down, and Remove. The selected row is #2a2a2e with a white name. The first Up and the last Down are disabled. Clicking the name selects that shot and shows it in the preview.

No Lines block yet.

Footer: Open list, Save list, Trim one file, a gap, Cut filled, Settings. Cut is the only filled control.

A missing file turns that row's name #e07a7a and appends " missing". Cut is then disabled. The status line above the footer reads "A file in the list is missing".

Screen: Shots, after a decide

Same as the loaded screen, plus a Lines block under the list, at most 160 px tall, scrolling. A secondary label says "Lines". Each row is monospace time, the words, the reason, Play, and either Drop or Restore. A kept line shows Drop. A dropped line shows Restore, with the words in #e07a7a. Play previews that line in the small frame and pauses at the end. It does not open the trimmer.

Footer: Cut now reads Cut again and is not filled. Render appears to its left and is filled. While work is running, both read Cutting… and are disabled. The status line above the footer is monospace and shows one of these, one at a time:

• Reading files
• Transcribing 2/4 DJI_20261008_091418.MP4
• Choosing takes
• 3 kept, 1 dropped
• Rendering 42%

If every line is dropped, Render does not encode. The status reads "Restore a line to render".

Spoken cuts with no key do not start. The status reads "Set an xAI key for spoken cuts."

Screen: Watch

The movie fills the top of the window, edge to edge in the column, black around the picture only if the frame requires it. A "Watch the cut" button is not on this screen. That button lives on the small preview, and only when a movie already exists and the person is back on Shots.

Under the picture, one bar, 44 px:

• A 44 px play button. Tooltip "Play" or "Pause".
• A filmstrip that fills the remaining width. Thumbnails run under the clips. Each kept range has an accent frame and a handle on both ends. Gaps are dim. A playhead is an accent line. Hovering a clip shows a small "×" at its top right. Hovering a gap says "Double-click to restore". Dragging a handle shows the time above the bar. Double-click inside a clip splits it. Double-click a gap joins it back.
• Text buttons: Settings, Shots, Captions, Short, Save.

Captions and Short appear only while the open file is the rough cut that still has its cut file beside it. After a hand trim, or after Save has moved playback to the saved movie, those two buttons are gone and the last button reads Export.

Under the bar, a centered monospace line. With nothing else to say it reads 0:12 (1:40). If the filmstrip is zoomed to one clip it reads 0:12 (1:40) · zoomed, with "zoomed" in the accent. During save, captions, or a short, that line is replaced by the status. A notice such as "Saved /home/lon/Videos/interview-founder.mp4" uses the accent for about five seconds, then the time returns.

Save copies the movie. Export re-encodes a hand trim. Both are disabled while busy.

Screen: Settings

Settings replaces the workspace. The picture is not visible. Playback is paused. The form is left aligned, at most 560 px wide, with empty space below it.

Top row: Done. If Settings was opened from Watch, Shots sits beside Done. If it was opened from Shots and a movie exists, Watch the cut sits at the right of that row.

Then:

• Checkbox Spoken cuts, on by default.
• When it is on, a 16 px semibold heading "This movie" and a wrapping text area, about 78 px tall, containing the movie prompt. No placeholder.
• When it is off, the heading and the text area are gone. One secondary line reads "Keeps every file, in this order."
• Checkbox Dip to black between files, on by default.
• A row: "xAI key: not set" or "xAI key: set", then Change. The "not set" label is accent only when Spoken cuts is on. Otherwise it is secondary.
• Change reveals a password field, placeholder "Paste xAI key", a Show checkbox, and Apply. The button then reads Hide. Apply clears the field.

Done returns to the screen Settings was opened from.

Screen: Help

A dim scrim, #000000 at about 80% opacity. A card, #1c1c1e, 12 px corners, centered. Title "Keyboard shortcuts". Two columns. Keys are monospace, accent, right aligned, 110 px. Actions are #d6d6da.

┌─────────────┬─────────────────────────────────────┐
│ Keys        │ Action                              │
├─────────────┼─────────────────────────────────────┤
│ Space       │ Play / pause                        │
├─────────────┼─────────────────────────────────────┤
│ ← / →       │ Move playhead 1s                    │
├─────────────┼─────────────────────────────────────┤
│ Shift ← / → │ Move playhead 5s                    │
├─────────────┼─────────────────────────────────────┤
│ Alt ← / →   │ Move playhead 0.2s                  │
├─────────────┼─────────────────────────────────────┤
│ [ / ]       │ Previous / next clip edge           │
├─────────────┼─────────────────────────────────────┤
│ S           │ Split the clip at the playhead      │
├─────────────┼─────────────────────────────────────┤
│ X           │ Remove the clip, or restore the gap │
├─────────────┼─────────────────────────────────────┤
│ Ctrl Space  │ Clip start to playhead              │
├─────────────┼─────────────────────────────────────┤
│ Alt Space   │ Clip end to playhead                │
├─────────────┼─────────────────────────────────────┤
│ Ctrl Z      │ Undo (Ctrl Shift Z redo)            │
├─────────────┼─────────────────────────────────────┤
│ Z           │ Zoom to the clip                    │
├─────────────┼─────────────────────────────────────┤
│ Ctrl O      │ Open a video                        │
├─────────────┼─────────────────────────────────────┤
│ Ctrl S      │ Save or export                      │
├─────────────┼─────────────────────────────────────┤
│ Q           │ Quit                                │
├─────────────┼─────────────────────────────────────┤
│ ?           │ Show these shortcuts                │
└─────────────┴─────────────────────────────────────┘

Clicking the scrim closes it. "?" toggles it.

Screen: Close

Same scrim and card. Two versions.

Unsaved rough cut. Title "Save this movie?". Body: "This cut is only in a temporary folder. Save it, or it will be lost." Buttons, right aligned: Cancel, Lose it, Save. Save is filled.

Hand trim that has not been exported. Title "Unexported edit". Body: "Your edit hasn't been exported. Quit anyway?" Buttons: Cancel, Quit, Export. Export is filled.

Frame list

Generate these as separate desktop frames, in this order. Keep the chrome identical across them.

1. Shots, empty.
2. Shots, four files, Cut filled.
3. Shots, one file missing, Cut disabled.
4. Shots, drag hovering, accent frame.
5. Shots, four lines, Render filled, Cut again.
6. Shots, rendering, status "Rendering 42%", buttons disabled and reading Cutting….
7. Watch, rough cut, Captions and Short visible, Save.
8. Watch, zoomed filmstrip, time line with "zoomed".
9. Watch, after a hand trim, Export, no Captions or Short.
10. Settings, Spoken cuts on, key not set in accent.
11. Settings, Spoken cuts off, the one-line explanation, key row secondary.
12. Settings opened from Watch, with Shots beside Done.
13. Help card.
14. Close card, "Save this movie?".
15. Close card, "Unexported edit".