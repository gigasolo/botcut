# BotCut chrome

This is the chrome as built in the QML after the focus pass. It replaces the earlier top bar with the filled button, the inspector column, the block row, the search and filters, and the status bar with key hints. It records the spacing, the type sizes, the words, and the theme tokens that are actually in `src/Main.qml`, `src/ActionBar.qml`, `src/PlanPane.qml`, `src/LineRow.qml`, `src/CutRow.qml`, `src/ReviseChat.qml`, `src/EditBar.qml`, and `src/PlayButton.qml`.

Where this file and `docs/ux-pilot.md` disagree on chrome, this file wins. Behavior in `docs/recut-finish.md` still wins over both: playback, drop and keep, pace, and the kept sentence do what that file says, wherever this frame puts them.

One rule: the picture, the list, and one next step. The frame is one editor window. A top bar holds the word BotCut, the file, and the steps as a breadcrumb. The left column is the list for the step, with the chat under the lines. The stage is the picture, one transport bar, the cut row, and on Movie the filmstrip. An action bar at the bottom holds this step's sentence and its buttons, together. The column and the chat are resizable by dragging, and the sizes are remembered.

## Tokens

`src/theme.h` is the only color source.

| Role | Token |
| --- | --- |
| Window, the stage, the Cut / Original chip's track | theme.background |
| Top bar, action bar, the left column, the split handle | theme.surface |
| The 1 px lines under the top bar, over the action bar, on the split handle, around the Cut / Original chip and the open pace list | theme.line |
| Play disc, the clock chip, the timeline track, quiet buttons, your chat bubble, the sentence well, the chat field, the closed pace field and its open list, the chosen side of Cut / Original | theme.raised |
| Hover on a quiet button, a step, a line row, a row word's pill, a pace row, the inactive side of Cut / Original | theme.hover |
| Selected line, the line under the playhead on Movie, the selected shot, a hovered recent row | theme.selected |
| The filled button, Apply in the chat, the current step's underline, the timeline playhead, the filmstrip's frames and handles, the chosen pace row's text, a focus border, Send in the chat field, "unsure" on a row, a missing file, a notice, a sentence that needs the person | theme.accent |
| The filled button's label | theme.accentForeground |
| Picture well, and the caption chip over it at 75 percent | black |
| Caption words, filmstrip hint words | white |
| Dialog dim | theme.scrim |

Text is theme.foreground at 100, 62, or 38 percent. The opacity sits on the text item. The only parents that carry an opacity are the play disc (38 percent when it cannot play), the fade switch (38 percent while busy), the split handle's hover mark (38 percent), and the filmstrip (45 percent while busy).

Type is the system sans. Monospace is used only on clocks: the file name in the top bar, the time on a line row, and the transport clock. Nothing puts a typeface in rich text.

Corners are `theme.radius`. A pill inside a row and a step's hover use `theme.radius - 2`, never below 0.

The only icon is play and pause, the existing `PlayButton`. Everything else is a word.

## Type sizes

| Use | Size, weight |
| --- | --- |
| "Pick up where you left off", "Drop the shots for this movie here." | 16, DemiBold / Normal |
| "Lines" and "Shots" column headings | 15 DemiBold |
| The caption over the picture | 14 |
| BotCut, the current step word, the filled button's label, Apply | 13 DemiBold |
| Step words, Settings, Help, quiet buttons, line words, Drop, Keep, Play, Remove B-roll, the shot row's words, the sentence well, the pace field, "Fade", the chat turns, Send, the chat field, the action sentence, the transport clock, Cut, Original | 13 |
| The file name, the time on a row, reasons, the B-roll line, the change line under a bot turn, the chat's own lines (Thinking…, a failure, an undo), recent rows, "Lists" and "Movies" headings | 12 |

## Window

960 × 680 on open, never under 960 × 640. The top bar is 48 px, the action bar at least 56 px and growing when its sentence wraps. The left column opens at 360 px and drags between 300 and 560 px; the stage is never under 320 px. On Lines the column is the rows over the chat, the chat opening at 240 px and never under 140 px, the rows never under 160 px. Both splits are saved under `layout` in the app's settings and restored on the next open. At 960 × 640 on Lines the picture keeps about 400 px of height.

## The top bar

A `theme.surface` band, 48 px, 16 px side margins, 8 px between items, a 1 px `theme.line` under it. Left to right:

- **BotCut** at 13 DemiBold.
- The file name at 12 monospace, 62 percent, eliding in the middle, at most 220 px. The open movie's file, or the shot on the picture while gathering. Nothing on the empty home.
- A stretch, so the steps sit near the middle.
- The breadcrumb: **Lists › Shots › Lines › Movie**. Each step is its word at 13 plus 8 px each side, 32 px tall, with a `›` at 38 percent between. The current step is 100 percent DemiBold with a 2 px `theme.accent` underline as wide as the word. A reached step is 62 percent, `theme.hover` on hover, and clickable. A step not yet reached is 38 percent and does nothing. Lists sits only while a list or a movie is open; clicking it closes the project and keeps the files, and it reads at 38 percent while a job runs. Lines is reached once a line list exists. Movie is reached once a movie is open. There are no counts in the steps.
- A stretch.
- **Settings** and **Help** at 13, 62 percent, 32 px tall, `theme.hover` on hover.

## The left column

A `theme.surface` column with 16 px side margins and 12 px top and bottom, ending in the split handle: a 7 px strip in `theme.surface` with a 1 px `theme.line` at its right edge and a 2 px `theme.foreground` mark at 38 percent while hovered or dragged.

- **Empty**: "Pick up where you left off" at 16 DemiBold, then "Nothing saved yet." at 13, 62 percent, or the recent "Lists" and "Movies" at 12, 38 percent, with 28 px rows at 12, 62 percent, `theme.selected` on hover.
- **Shots**: "Shots" at 15 DemiBold, 4 px, the shot list with 4 px between rows, and under it **Add shots…**, **Add a title card…**, and **Save list…** as quiet buttons that wrap. The shot row is unchanged: its picture, the name, the size or "B-roll" or "File missing", and on the selected row Move up, Move down, Remove, and B-roll or Shot.
- **Lines**, and **Movie** while the movie is the plan: "Lines" at 15 DemiBold, 8 px, then the rows over the chat with a handle between them: a 9 px strip with a 1 px `theme.line` through its middle, `theme.hover` while hovered or dragged.
- A plain file says "One file, trimmed by hand." at 13.

### Line rows

Each row is one spoken span. 12 px left and 8 px right inset, 8 px top, 4 px between its two lines, 8 px under, then 4 px to the next row. `theme.radius` corners. `theme.hover` on hover, `theme.selected` when selected or under the playhead on Movie. No accent bar.

- Top line, 8 px apart: the time at 12 px monospace in a 36 px minimum column, 62 percent (38 when dropped); the words at 13, wrapping, filling the width, 100 percent (38 and struck through when dropped); then the one word that acts, **Drop** on a kept line and **Keep** on a dropped one, at 13, 100 percent, in a 24 px pill that fills `theme.hover` on hover. It is the only control on an unselected row, and it sits in the same place whether the row is selected or not.
- Second line, only when there is something to say, indented past the clock column: the reason ("unsure" in `theme.accent`; "dropped" or "put back" at 62 percent, with "You · " in front when the person did it); on the first line of a B-roll run a 64×36 still from the footage on `theme.raised`, `theme.radius` minus 2, cropped to fit; the B-roll line at 12, 62 percent, eliding past 240 px ("B-roll: file · 11 s · hides the cut" on the first line of a run, "B-roll goes on" under it); a stretch; then on the selected row **Play** and **Remove B-roll** on any line of a run, as the same 24 px pills.
- While busy, Drop, Keep, Play, and Remove B-roll read at 38 percent with an arrow cursor, and nothing flips.
- Clicking a row is the one way to jump to a line. It shows that line's first frame; Play, Enter, or Space plays from there.

### The chat

A transcript over a field. The thread is `backend.chat`, newest at the bottom, scrolled to the end when a turn arrives, 8 px between turns.

- **Your turn**: a `theme.raised` bubble on the right, `theme.radius`, the words at 13 with 12 px sides and 8 px top and bottom, at most 85 percent of the column.
- **The bot's turn**: on the left with no bubble: the model's reply at 13, then the change it would make at 12, 62 percent ("Drops 2 lines. Pace becomes Tight." or "Nothing would change."), 6 px apart.
- **A proposal waiting**: under the latest bot turn, **Apply** filled at 32 px and **Leave it** as a quiet chip, 6 px apart. Only the latest proposal is live. Typing yes, ok, do it, apply, or go ahead in the field applies it too. Any other note is a new question, and the old proposal is dropped.
- **After Apply**: a bot turn "Done." with what changed in the past tense ("Dropped 2 lines. Pace is now Tight."), and **Undo** as a word on that turn while the previous list can come back. Undo adds the window's own line, "Undone. Back to how it was before this note." or "Could not undo. The line list did not save."
- **While the bot works**: "Thinking…" at 62 percent under the thread, the field disabled, the action bar's job button reading "Changing the list". While the change lands it says "Applying…".
- **A failure**: "That change didn't go through. Your note is back in the field." at 12, 62 percent, and the note is back.
- **The field**: `theme.raised`, 36 px, 12 px text inset, 13 px, the placeholder "Ask for a change…" at 38 percent, or "Say yes, or ask for something else" while a proposal waits, a 1 px `theme.accent` border while focused, and **Send** in the accent inside it on the right once there is text. Enter sends.
- The thread belongs to the line list. Cut again and closing the project clear it.

## The stage

The center column, `theme.background`: the picture well, then the transport, the cut row, and on Movie the filmstrip, each 12 px from the left and right edges so they share one width.

- **Picture well**: black, `theme.radius`, 12 px top, left, and right margins, filling the height that is left. Clicking it plays or pauses. On Empty it reads "Drop the shots for this movie here." at 16, then "MP4, MOV, or MKV, straight from your phone or camera." at 13, 62 percent, then a quiet **Trim one file instead…**, 8 px apart, centered. On Lines the current line's words sit over the bottom of the picture: a black chip at 75 percent, `theme.radius`, 16 px up from the bottom, at most 80 percent of the picture's width, the words at 14 in white, centered, wrapping, 12 px each side and 6 px above and below. It is in the window only. The export never carries it.
- 8 px, or 12 px when no transport shows.
- **Transport**: one 36 px row, items 8 px apart, vertically centered. Play is the 36 px `theme.raised` disc with the play or pause path in `theme.foreground`, 38 percent when it cannot play; it shows while a shot is previewing on Shots or Lines, and on Movie. The clock follows: a 28 px `theme.raised` chip at 13 monospace, "0:04 / 0:10". On Lines it is the time into the cut over the kept span; on Movie it is the filmstrip's playhead over the kept duration. On Lines the timeline fills the middle: a 4 px `theme.raised` track with a 2 px `theme.accent` playhead 14 px tall. No blocks, no legend, no ticks. With Cut chosen the track spans the kept lines in order and the playhead moves through them as the cut plays. With Original it spans the source clip. A click or a drag seeks: while playing, playback goes on from there; while paused, the picture shows that frame. On Movie the filmstrip is the only track. On the right, **Cut | Original**: a 28 px `theme.surface` chip with a 1 px `theme.line` border, 2 px of padding, two 24 px words at 13 with 8 px each side; the chosen one is `theme.raised` at 100 percent, the other 62, `theme.hover` on hover, 38 while busy. Cut is the resting choice; Original plays the file straight through. It shows on Lines once lines exist, and on Movie while the plan is the movie.
- 8 px.
- **Cut row**, on Shots for a speech cut once a shot is in, and on Lines: one 36 px row, items 8 px apart. The sentence well fills the width: `theme.raised`, `theme.radius`, 12 px text inset, 13 px, placeholder "What is this movie? One sentence." at 38 percent, a 1 px `theme.accent` border while focused. It is `backend.intent`, edited in place. Return leaves the field. Then the one pace field in the window, bound to `backend.pace`: `theme.raised`, 36 px, wide enough for its longest sentence, `theme.hover` on hover, a 1 px `theme.accent` border while focused or open, text at 100 percent reading "Open · keeps long pauses", "Measured · natural pauses", "Tight · trims most pauses", or "Frenzied · cuts every breath", with a `▾` at 62 percent on its right. Space or Enter opens it. The open list hangs 4 px under the field over whatever is below, on `theme.raised` with a 1 px `theme.line` border, rows 32 px, the chosen row's text `theme.accent`, the others 100 percent, `theme.hover` on hover; Up and Down move, Enter picks, Escape closes. While busy the field reads at 38 percent and closes. Then "Fade" at 13 and the one fade switch, vertically centered, no focus, 38 percent while busy, checked when `backend.sceneTransition` is "dip". It is the same setting as "Fade to black between shots" in Settings. There is no row for cover shots: B-roll is marked on the shot row, and the sound choice is in Settings.
- **Filmstrip**, on Movie: unchanged in look. 76 px tall, `theme.surface` film, `theme.accent` frames and handles, dim black gaps, a dropped line's gap the accent at 24 percent, the white playhead, the `theme.raised` hint chip inside the strip. Clicks still trim. 12 px under it, 4 px when zoomed, with "Zoomed to one shot. Z zooms out." at 13, 62 percent, 12 px under it.

## The action bar

A `theme.surface` band with a 1 px `theme.line` top edge, at least 56 px, growing when the sentence wraps. 16 px side margins, 12 px between items, everything vertically centered.

- The sentence on the left, 13 px at 62 percent, wrapping, 200 px minimum. It turns `theme.accent` at 100 percent for a notice, a missing key, a missing file, or when every line is dropped. On Lines it is the one place the kept count and the kept clock appear.
- This step's quiet buttons, 6 px apart: 32 px `theme.raised` chips, 13 px at 100 percent, `theme.hover` on hover, 38 percent when disabled.
- The filled button: `theme.accent` with its label in `theme.accentForeground` at 13 DemiBold, 36 px tall. `theme.raised` with the label at 38 percent when disabled. While a job runs it is the job's sentence on `theme.raised` with an accent progress wash, disabled, and the quiet buttons hide. Ctrl+Enter and Ctrl+R press it. A saved rough cut has no filled button.

| Step | Sentence | Quiet buttons | Filled |
| --- | --- | --- | --- |
| Empty | Add the shots for one movie. You can put them in order after. | Open a saved list… | Add shots… |
| Shots, no key | Spoken cuts need an xAI key. | Keep every shot instead | Add xAI key… |
| Shots | 4 shots, in this order. Cut finds the lines worth keeping. | | Cut |
| Shots, every shot | Cut joins all 4 shots in this order. | | Cut |
| Shots, a file missing | DJI_20261008_092002.MP4 is missing. Remove it, or put the file back. | | Cut, disabled, not filled |
| Lines | 3 of 4 lines kept, 0:10. Render makes the movie. | Cut again… | Render |
| Lines, all dropped | Every line is dropped. Keep one to render. | Cut again… | Render, disabled, not filled |
| Unsaved rough cut | Your movie is ready. It's only in a temporary folder until you save it. | | Save… |
| Hand trim | Trimmed by hand. Export writes a new file. Captions and the short wait until then. | | Export… |
| Saved rough cut | Saved as founder-story.mp4. | Show the file, Captions, Vertical short, Export another size… | nothing |
| A job | the job's sentence | | the job, disabled, with progress |

## The four frames

**Empty.** The top bar: BotCut, no file, Shots underlined with Lines and Movie at 38 percent, no Lists, Settings, Help. The left column: "Pick up where you left off" and the recent rows. The stage is the black well with the drop words. No transport, no cut row. The action bar: the empty sentence, **Open a saved list…**, and the filled **Add shots…**.

**Shots.** The top bar: the shot's file name, Lists › Shots underlined. The left column: "Shots", the shot list with the selected row on `theme.selected`, then the list's three quiet chips. The stage: the selected shot in the well, a transport with only Play, then the cut row. The action bar: the shots sentence and the filled **Cut**.

**Lines.** The top bar: Lines underlined. The left column: "Lines", the rows with Drop or Keep on every one and Play on the selected one, the handle, then the chat with its turns and the field. The stage: the selected line's frame in the well with its words over it, a transport with Play, the clock, the timeline, and Cut | Original, then the cut row. The action bar: "3 of 4 lines kept, 0:10. Render makes the movie.", **Cut again…**, and the filled **Render**.

**Movie.** The top bar: the movie's file name, Movie underlined. The left column: the line list with the line under the playhead marked, and the chat. The stage: the movie in the well, a transport with Play, "0:12 / 2:46", and Cut | Original, then the filmstrip. No cut row. The action bar follows the save state, with **Show the file** first after a save.

## Left out

No search, no filters, no block row, no legend, no count tiles, no kept-share bar, no Review button, no key hints, no Previous or Next, no Undo in the top bar, no "Key set" word, no counts in the steps, no third column, no cover-shots row. No waveform, threshold, minimum-duration slider, padding slider, blips, volume, mute, fullscreen, fade in from black, fade out to black, a new pace, redo, web fonts, a second accent, multi-track, markers, mixer, or handoff to Premiere, Resolve, Final Cut, ScreenFlow, or CapCut. The caption is never burned into the file. The empty home, the title-card dialog, and the quit confirmation are unchanged. Play and pause are still the only icons. Settings is not restyled.
