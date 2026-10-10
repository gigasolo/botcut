BotCut is a dark desktop app for one person making a rough cut of a founder or small-business movie. The window is 960×680, minimum 960×640. A sidebar stays up. The main column is where the person drops shot files, puts them in order, and presses Cut. The app transcribes the speech, keeps the useful lines, and plays the movie. They can drop a bad line, render again, watch the cut, trim it by hand, save it, write captions, or cut one vertical short.

This file is the same brief as docs/ux-pilot.md, written without Markdown tables. When they disagree, follow docs/ux-pilot.md.

The person using it is the founder, filming on a phone or a DJI camera and editing on a Linux desktop at night. They want the next movie, not a timeline. Speech is the structure. The order of the files is the order of the story.

What to draw

Draw only these surfaces:

• Shots, where the files are gathered
• Watch, where the movie plays and can be trimmed
• Settings, which covers the main column and leaves the sidebar up
• Help, a shortcut card on the main column
• Close, a small confirm card on the main column

Every control is a text button, a switch, a checkbox, a text field, a list row, or the filmstrip. Play and pause are the only icon buttons. Help in the sidebar shows a "?" beside the word.

What to leave out

Leave out an account row, a media bin, a timeline with tracks, effects, titles, music, color, keyframes, a waveform editor, and a multi-track mixer. Leave out pricing and onboarding. Leave out gradients, glass, blur, and decorative illustration. Leave out icon-only toolbars. Do not show a stored API key, an export folder, a per-file duration, or a total runtime.

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
│ Accent                       │ the Omarchy theme color, fallback #FFD60A          │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Page margin                  │ 16 px                                              │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Footer gap                   │ 6 px                                               │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Sidebar and footer bar       │ #1c1c1e, 212 px, collapsing to 64 px               │
├──────────────────────────────┼────────────────────────────────────────────────────┤
│ Shot row                     │ 52 px tall, 8 px corners                           │
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

Sidebar

The sidebar is on every screen. It is 212 px, #1c1c1e, with a right border. A 20 px accent square, then "BotCut", then a chevron that collapses the sidebar to 64 px and hides the labels. The rows are Shots, Watch, then a gap, then Help and Settings. The active row has a 3 px accent bar. Watch is disabled until a movie is loaded. On an empty tray, under Watch: "Drop clips anywhere to start a new cut". Help shows "?" beside the word. There is no account row.

Screen: Shots, empty

This is the first open. The main column holds a dashed card: "Drop your shots here", "MP4, MOV, or MKV · straight from your phone or camera", and a filled Add videos inside the card. Under the card, three quiet facts: "Auto-finds your best lines", "Cuts silence and dead air", "Exports ready to post".

A row above the footer holds Open list, Save list (disabled), and Trim one file. The footer is a 64 px bar. Left: "No shots yet". Right: Cut, disabled and not filled.

Dropping files is allowed on this screen. While a drag is over the main column, an accent stroke frames that column and the words read "Drop to add to shots".

Screen: Shots, files loaded, before a decide

The preview is a centered 16:9 frame, at most 200 px tall. The file name sits at the bottom right. A play button sits on the frame. Under the preview, Add videos is a dashed row.

Each shot row is 52 px: the file name, the file size, Remove, and, on hover or on the current row, Up and Down. The selected row is #2a2a2e. There is no per-file duration. No Lines block yet.

The footer bar says "4 shots" on the left and a filled Cut on the right. A missing file turns that row red and says "file not found". Cut is then disabled. The footer reads "1 shot can't be found — remove it to continue".

Screen: Shots, after a decide

The preview drops to at most 120 px. The shot list stays above and gets shorter. Lines are the tall list. The heading is "Lines" plus "kept (N of M)". A resting row is the accent time and the words. On hover, or on the current row, the row also shows the reason, Play, and Drop or Restore. Dropped words are #e07a7a.

The footer says "3 lines kept", or the job status while one is running. Cut reads Cut again and is not filled. Render is filled. While work is running, both read Cutting…. If every line is dropped, the status reads "Restore a line to render". Spoken cuts with no key do not start. The status reads "Set an xAI key for spoken cuts."

Screen: Watch

The movie fills the main column. On the picture: "Rough cut · 2:46", plus " (trimmed)" after a hand trim. A zoomed filmstrip shows a "zoomed" chip. It does not name a line number.

The bar is play, the filmstrip, the time "0:12  /  2:46", then Captions, Short, and Save. Captions and Short appear only while the open file is rough_cut.mp4 with a cuts.json beside it. After a hand trim, or after Save, those two are gone and the last button reads Export. Settings and Shots are in the sidebar.

Under the bar: "Not yet saved", or "Trimmed by hand · not yet exported", or the job status. Save copies the movie. Export re-encodes a hand trim.

Screen: Settings

Settings covers the main column. The sidebar stays. Playback is paused. The form is at most 560 px wide.

Top right: Done. If Settings was opened from Watch, Back to Watch sits beside Done.

Spoken cuts is a switch, on by default. On, one line reads "Finds the lines that match this movie, and drops the rest." Then "This movie" and the prompt. Off, those are gone and one line reads "Keeps every file, in this order." Dip to black between files stays. The key row is "xAI key" plus a badge: "not set", "set", or "not needed". "not set" is the accent only when Spoken cuts is on. Change opens an empty field. The stored key is never written into it.

Screen: Help

The scrim covers the main column, not the sidebar. A card, #1c1c1e, 12 px corners. Title "Keyboard shortcuts". Keys sit in neutral chips. Actions are #d6d6da. Use only the shortcuts below.

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

Clicking the scrim closes it. Help in the sidebar toggles it, and so does "?".

Screen: Close

Same scrim and card, on the main column. Two versions. There is no "Don't show again" and no thumbnail.

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
12. Settings opened from Watch, with Back to Watch beside Done.
13. Help card.
14. Close card, "Save this movie?".
15. Close card, "Unexported edit".