BotCut is a dark desktop app for one person making a rough cut of a founder or small-business movie. The window opens at 960×680 and does not go below 960×640. There is no sidebar. One plan pane, 360 px wide, sits on the left. The picture fills the rest. The steps along the top of the plan are Shots, Lines, and Movie. Settings, Help, a title card, quit, and cut-again are dialogs over that same window.

This file is the same brief as docs/ux-pilot.md, written without Markdown tables. When they disagree, follow docs/ux-pilot.md.

The person using it is the founder, filming on a phone or a DJI camera and editing on a Linux desktop at night. They want the next movie, not a timeline. Speech is the structure. The order of the files is the order of the story.

The words on screen are shot, line, movie, and trim. Three sentences stay as they are because they are already on screen: "File missing", "Trim one file instead…", and "One file, trimmed by hand."

What to draw

Draw only these surfaces:

• Empty, before any shot is added
• Shots, with files in the list
• Lines, after a cut, the first line selected
• Movie, with the filmstrip under the picture
• Settings, a dialog
• Help, a dialog
• Title card, a dialog
• Quit, a dialog
• Cut again, a dialog

Every control is a text button, a switch, a checkbox, a text field, a list row, or the filmstrip. Play and pause are the only icon buttons. Help is a "?" in the footer, next to the word Settings.

What to leave out

Leave out an account row, a sidebar, a media bin, a timeline with tracks, effects, music, color, keyframes, a waveform editor, a multi-track mixer, and lower-thirds. Leave out a zoom control in the chrome. Leave out pricing and onboarding. Leave out gradients, glass, blur, decorative illustration, icon-only toolbars, and web fonts. Do not show a stored API key, an export folder, a per-file duration, or a total runtime. One Omarchy accent. Do not invent a second accent.

Also leave out a waveform, a threshold, a minimum-duration slider, a blips slider, a zoom control on a waveform, a tool that splits one recording into separate exported files, an export to Premiere, Resolve, Final Cut, ScreenFlow, or CapCut, multi-track, and a mixer. Leave out a light theme and a right rail.

Visual system

This has to be buildable in Qt Quick. Use flat rectangles, one accent, and the system sans. Status and times use a monospace face. theme.radius is the corner radius of the window, the cards, the rows, and the buttons. Text uses theme.foreground at full strength, at 62 percent, or at 38 percent, and that opacity sits on the text item itself, never on a parent that also holds text.

The window background is theme.background. Cards, the film well, and the sentence wells are theme.surface. Dividers, quiet buttons, the progress track, the play button disc, and the trim hint chip are theme.raised. A selected shot, a selected line, and a hovered recent row are theme.selected. A hovered word button is theme.hover. Card borders are theme.line. Every dialog sits on one scrim, theme.scrim. The accent is the Omarchy theme color. A filled button uses that accent and theme.accentForeground for its label. The picture well is black.

The page margin is 16 px. The footer is at least 56 px tall and grows when its sentence wraps: one sentence on the left, then the buttons for this step. One of those buttons is filled. That filled button is the next action. Text is full strength, 62 percent, or 38 percent. A running job's button stays disabled, and its label and track stay full strength. The filmstrip while a job runs stays at 45 percent.

The accent marks the filled button, the playhead, the trim handles, a missing file, a missing xAI key, and a short notice. Washed back, it also marks a dropped line's gap on the filmstrip. It does not wash the window.

The window title is "BotCut". With a preview or a movie it becomes "BotCut — " plus the file name.

Sample content

Use these names so every frame feels like the same project.

Shots, in this order:

1. DJI_20261008_091204.MP4, selected
2. DJI_20261008_091418.MP4
3. DJI_20261008_092002.MP4, marked missing only on a missing-file frame
4. interview-founder.mov

Lines, after a cut:

• 0:12, ending 0:15, "We started in the garage.", kept, and selected
• 0:41, ending 0:45, "The first customers were shops on the same street.", kept
• 1:05, ending 1:09, the same sentence again, reason "dropped"
• 1:28, ending 1:31, "Then we opened the second location.", reason "put back", kept

A row shows only the start time. The end is there so the sentence under the picture can be worked out. The pace is Measured and the fade is on. With these lines, the sentence under the picture reads "0:10 kept of 0:14 – 3 lines, measured".

The saved movie is founder-story.mp4.

The picture is a person talking in a small shop, 16:9, inside the black well. On Movie the same person is larger.

The movie sentence, on the shot list while spoken cuts are on, and not repeated as a second field in Settings:

Keep each moment in order. Drop flubs and true retakes. Keep a beat that appears only once.

The plan

Lists, when a project is open, sits at the left of the step row. It is the way back to the recent lists and movies. Shots, Lines, and Movie follow it. A step that has not been reached is quiet. Lines becomes reachable once a line list exists. Movie becomes reachable once a movie is open. If the row is tight, Lines drops the "of M" first, then Shots drops its count. Lists and Movie m:ss stay whole. Settings and "?" sit in the footer, beside the step's buttons. There is no account row and no collapsing column.

The picture is the other column. While shots are gathered and no dialog is open, a file dropped on the picture is added to the list. Files added together are ordered oldest first.

Empty

This is the first open. The plan says "Pick up where you left off" and, when nothing has been saved, "Your shots will be listed here." Saved lists and movies, when they exist, are named under "Lists" and "Movies".

The picture says "Drop the shots for this movie here." Under that: "MP4, MOV, or MKV, straight from your phone or camera." Then a quiet button, "Trim one file instead…".

The footer sentence is "Add the shots for one movie. You can put them in order after." Beside it: "Open a saved list…" and a filled "Add shots…".

Shots

Once a file is in the list, the plan shows the shot list instead of the recent page. While spoken cuts are on, a well at the top holds the movie sentence. Its empty placeholder is "What is this movie? One sentence." Under that is the pace. First comes the word "Pace", then "How much air to leave between lines." at 62 percent, then the pace field, a surface field the same shape as the sentence. Closed, it reads "Open · keeps long pauses", "Measured · natural pauses", "Tight · trims most pauses", or "Frenzied · cuts every breath". Space or Enter on that field opens it. Opening it shows those four sentences in a list directly under the field. The chosen one is the accent. The others are full strength.

Under the pace is the fade. First comes the word "Fade", then "A short fade between shots." at 62 percent, with a switch at the right that is on when the fade is on. It is the same setting as "Fade to black between shots" in Settings, and the two stay in step. No other Settings control is drawn in the plan.

Each shot row is the file name and the file size. A missing file says "File missing" in the accent, and the name is the accent too. The selected row is theme.selected and shows "Move up", "Move down", and "Remove". The first Move up and the last Move down are quiet. There is no per-file duration. A small picture from the file sits on the row when one exists.

Under the list: "Add shots…", "Add a title card…", and "Save list…". Save list stays off until there is a shot. "Open a saved list…" is on the empty footer, not under the shot list.

The footer, with spoken cuts and a key, reads "4 shots, in this order. Cut finds the lines worth keeping." The filled button is "Cut". With spoken cuts off it reads "Cut joins all 4 shots in this order." A missing file disables Cut. The sentence names the file: "DJI_20261008_092002.MP4 is missing. Remove it, or put the file back." With no key, the sentence is "Spoken cuts need an xAI key." The buttons are "Keep every shot instead" and a filled "Add xAI key…".

The selected shot plays in the picture. Play and pause sit on that picture. They do not open a file.

Lines

The plan switches to the line list. The step is still called Lines. There is no tab named Sections and no second transcript. The line list is the section list. Above the list, the same Pace and Fade as on Shots repeat: "Pace", "How much air to leave between lines.", the closed pace field, then "Fade", "A short fade between shots.", and the switch. The list starts with "This movie" and the movie sentence. The closed pace field above already shows the pace sentence, so the list does not repeat it. At the bottom, the field is the chat. There is no label beside it. The empty field says "Tell BotCut what to change". Above an empty field: Like "drop the pricing part" or "make it tighter". "Change this cut" sits inside the field, on the right, and only once there is something to send. Sending that note does not encode. The note then sits above the field in quotes, and a line under it says what changed: lines dropped or put back, a new movie sentence, a new pace, or the fade. "Undo this change" is its own line when the previous list can come back. The same chat is on Movie when the movie is the plan. A change that actually changes the cut returns to Lines. One that changes nothing stays on Movie.

Each line is one spoken span: the time, the words, and whether it stays. "Drop", or "Keep" when the line was dropped, is on every line, selected or not, at the right of the words. Selecting a line moves the picture to that span. The selected line also shows "Play". A reason, when there is one, reads "unsure", "dropped", or "put back". A dropped line's time and words are at 38 percent. Play, Drop, Keep, and Remove B-roll stay full strength unless a job is running. Play shows that line in the picture, then pauses at the end. It does not open the trim.

Next to play on the picture, a word reads "Cut", or "Raw". Cut is the resting choice. It is a word on a theme.raised chip, not an icon. Play and pause stay the only icon buttons.

Once lines exist, one quiet sentence sits under the picture, not in the footer. With the sample lines it reads "0:10 kept of 0:14 – 3 lines, measured". The first clock is the kept span. The second is the span of every line. The count is how many lines are kept. The last word is the pace name: open, measured, tight, or frenzied. If a line has no start or end, the clocks are left out and the sentence keeps the count and the pace, for example "3 lines, measured". The times are monospace. The sentence is theme.foreground at 62 percent.

The footer reads "3 of 4 lines kept. Render makes the movie." and the kept time when the line times are known. "Cut again…" is quiet. "Render" is filled. If every line is dropped, Render stays off and the sentence is "Every line is dropped. Keep one to render."

Cut again opens the confirm dialog. It does not start until that dialog says so.

Movie

The picture fills the right column. Under it: play and pause, the filmstrip, and the time, for example "0:12 / 2:46". While the movie is the plan, the word "Cut" or "Raw" sits next to play, the same word as on Lines. A plain file with no line list does not show it. The filmstrip is the trim. Each kept range has an accent frame and a handle on both ends. Gaps are dim. While the movie is the plan, a gap that is a dropped line is the accent washed back: flat, with no new color. Other gaps stay dim. While lines exist, the quiet sentence from Lines sits under the filmstrip. The playhead is a white line. Hovering a clip offers a small "×" when another clip would remain. A hint chip uses theme.raised and says "Double-click to split", "Double-click to join", or "Double-click to restore". Z zooms the filmstrip to the clip under the playhead. The only extra line is "Zoomed to one shot. Z zooms out." There is no zoom control in the chrome.

When the open movie is one file, the plan says "One file, trimmed by hand." When the movie is the plan, the line list stays up and the line under the playhead is marked. A handle then edits that range in its own file. Playback loads the source under the playhead. It does not trim a baked file by scrubbing it.

The footer follows the movie. An unsaved rough cut says "Your movie is ready. It's only in a temporary folder until you save it." The filled button is "Save…". A hand trim says "Trimmed by hand. Export writes a new file. Captions and the short wait until then." The filled button is "Export…". A saved rough cut says "Saved as " plus the file name, for example "Saved as founder-story.mp4.". It offers a quiet text button, "Show the file", then "Captions", "Vertical short", and "Export another size…". Nothing is filled after that save. The filled button does not become Export…. The export size dialog names the source size as original, for example "1280 x 720 (original)". Captions and Vertical short wait until a trimmed plan has been exported. Opening a different video clears them.

While a job runs, the sentence and the button both show the job, and the other buttons hide. The footer grows if that sentence wraps. The button is disabled and fills with progress when the job reports a percent, and its words stay full strength. One job runs at a time. "Opening…" is the open. "Changing…" is a change to the line list, and the button reads "Changing the list". "Cutting…" is the read. Other jobs keep their own sentences, such as "Reading shots", "Choosing lines", "Making the title card", and "Rendering 42%".

Settings

Settings is a dialog on theme.scrim. The card is theme.surface with a theme.line border. The picture is paused. The title is "How BotCut cuts".

A switch, on by default, reads "Spoken cuts: keeps the lines worth saying. Needs an xAI key." Under it: "Every shot: joins the shots in order." The active choice is full strength. The other is at 62 percent.

The key line is "Saved on this computer." or, in the accent, "Not set. Spoken cuts can't run without it." The field starts empty. Its placeholder is "Paste xAI key". "Show" reveals what was typed. "Save key" stores it and clears the field. The stored key is never written back into the field.

Then three checkboxes. "Fade to black between shots", on by default. It is the same setting as the Fade switch in the plan, and the two stay in step. "Cover a spoken line with another shot's picture", off by default. "Keep that shot's sound under the voice", on by default, and only available while the cover is on. "Done" is filled and closes the dialog.

Help

The same scrim and card. The title is "How BotCut works". Four lines: "Add shots and put them in order." "Cut finds the lines worth keeping." "Drop lines or tell BotCut what to change, then Render." "Watch, trim by hand if you need to, then Save."

Then three columns of shortcuts, and only these.

Shots and lines: Up / Down selects. Alt+Up / Alt+Down moves. Enter plays. X drops or keeps. Delete removes. Ctrl+Enter presses the filled button.

Movie: Left / Right is 1 second. Shift+Left / Right is 5 seconds. Alt+Left / Right is 0.2 seconds. [ / ] is the previous or next edge. S splits. X removes or restores. Ctrl / Alt Space sets the edges. Ctrl+Z undoes. Z zooms.

Anywhere: Space plays or pauses. Ctrl+S saves or exports. Ctrl+O opens. ? shows these shortcuts. Q quits.

"Close" is filled. Clicking the scrim also closes Help, and so does "?".

Title card

The same scrim and card. The title is "Add a title card". The field starts empty. The placeholder is "Words on the card". Under it: "A still with this sentence, added as a shot you can move or remove." The buttons are "Cancel", "Put it last", and a filled "Put it first". Nothing is added until one of those two place buttons is pressed, and not when the field is empty.

Quit

The same scrim and card. Three versions. There is no "Don't show again" and no thumbnail.

A job is running. Title "Stop the render and quit?". Body "Quitting stops the job and keeps nothing." Buttons: "Keep working" and "Stop and quit".

An unsaved movie. Title "Save your movie before you quit?". Body "It's only in a temporary folder. Quitting deletes it." Buttons: "Keep working", "Quit without saving", and a filled "Save…".

A hand trim that has not been exported. Title "Export your trim before you quit?". Body "Your hand trim isn't in a file yet." Buttons: "Keep working", "Quit without exporting", and a filled "Export…".

Going back to Lists with that same hand trim asks first. Title "Export your trim before you go to Lists?". The body stays "Your hand trim isn't in a file yet." Buttons: "Keep working", "Go to Lists without exporting", and a filled "Export…". Export does not leave for Lists. An unsaved rendered movie does not ask, because it is already under Movies.

The filled button uses the accent. The quiet buttons use theme.raised.

Cut again

The same scrim and card, opened from "Cut again…" once a line list exists. Title "Cut again from the shots?". Body "This replaces the list, including lines you kept or dropped by hand." Buttons: "Keep this list" and a filled "Cut again".

Frame list

Generate these as separate desktop frames, in this order. Keep the chrome identical across them. Do not draw a sidebar.

1. Empty shots.
2. Shots, with files, the pace sentence, and Cut filled.
3. Lines, the first line selected, Render filled, the chat field at the bottom of the plan.
4. Movie, play, the filmstrip, and the time.
5. Settings dialog.
6. Help dialog.
7. Title card dialog, the field empty.
8. Quit dialog.
9. Cut again dialog.
