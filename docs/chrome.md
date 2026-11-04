# BotCut chrome

This is the chrome as built in the QML after the editor-frame pass. It replaces the previous chrome: the rail card, the plan pane with the step control in it, and the footer with the filled button are gone. It records the spacing, the type sizes, the words, and the theme tokens that are actually in `src/Main.qml`, `src/ActionBar.qml`, `src/PlanPane.qml`, `src/LineRow.qml`, `src/Inspector.qml`, `src/ReviseChat.qml`, `src/EditBar.qml`, and `src/PlayButton.qml`.

Where this file and `docs/ux-pilot.md` disagree on chrome, this file wins. Behavior in `docs/recut-finish.md` still wins over both: playback, drop and keep, pace, and the kept sentence do what that file says, wherever this frame puts them.

The frame is one editor window. A top bar holds the word BotCut, the file, the step, and the one next action. The left column is the line list. The center is the picture, the transport, and the row of blocks or the filmstrip. The decisions sit in a third column when the window is wide enough, and under the picture when it is not. A thin status bar runs under everything.

## Tokens

`src/theme.h` is the only color source. The prototype's pink, its amber, Inter, JetBrains Mono, and Font Awesome did not come along.

| Role | Token |
| --- | --- |
| Window, the center of the stage, the step control's track, the Keep / Drop track, the kept-share bar's track | theme.background |
| Top bar, status bar, the lines column, the wide inspector, the block row card, the Cut / Original chip | theme.surface |
| The 1 px lines under the top bar, over the status bar, between the columns, around the block row and the Cut / Original chip, the chat chips, and under the filters | theme.line |
| Play disc, Previous and Next chips, the clock chip, the current step segment, the current filter, the sentence well, the search field, the chat field, the closed pace field and its open list, the count tiles, the chosen side of Cut / Original | theme.raised |
| Hover on any of those, on a quiet word, a step, a filter, a line row, a chat chip, the inactive Keep or Drop word | theme.hover |
| Selected line, the line under the playhead, a hovered recent row | theme.selected |
| The filled button, the kept bar on a line row, a kept block, the unsure mark, the dropped block and gap at 24 percent, the unsure dot at 38 percent, the Review-unsure control at 12 percent with a 40 percent border, "Key needed", a missing file, a notice, the chosen pace row's text, a focus border, the kept-share bar | theme.accent |
| The filled button's label, the filled Keep or Drop word | theme.accentForeground |
| Picture well, and the caption chip over it at 75 percent | black |
| Caption words, filmstrip hint words | white |
| Dialog dim | theme.scrim |

Text is theme.foreground at 100, 62, or 38 percent. The opacity sits on the text item. The only parents that carry an opacity are the play disc (38 percent when it cannot play, it holds no text), the two switches (38 percent while busy, they hold no text), the dropped block and the dropped gap (24 percent, or 38 hovered, no text), the swatches and dots in legends and filters, and the filmstrip (45 percent while busy, as before).

Type is the system sans. Monospace is used only on clocks and counts, each its own Label with `font.family: "monospace"`: the file name in the top bar, the count beside a step word, the count on a filter, the time on a line row, the number on a count tile, the transport clock, the two clocks in the kept sentence, and the key on a status hint. Nothing puts a typeface in rich text.

Corners are `theme.radius`. Inside a segmented control, the segments use `theme.radius - 2`, never below 0. Blocks are 2 px.

The only icon is play and pause, the existing `PlayButton`. Everything else is a word.

## Type sizes

| Use | Size, weight |
| --- | --- |
| "Pick up where you left off", "Drop the shots for this movie here." | 16, DemiBold / Normal |
| "Lines" and "Shots" column headings | 15 DemiBold |
| The caption over the picture | 14 |
| BotCut, step words, Lists, Undo, Settings, Help, the filled button, Previous, Next, Cut, Original, line words, Play, Remove B-roll, the sentence well, the search field, the chat field, the pace field, "Fade between shots", "Cover lines with other shots", the mix sentence, the kept sentence, "Review N unsure lines", quiet buttons, the transport clock | 13 |
| The current step word, the filled button's label, the filled Keep or Drop word, "Review N unsure lines" | 13 DemiBold |
| Section headings in the inspector (This movie, Pace, Fade, Cover shots, Result) | 12 DemiBold, all capitals, 1 px letter spacing, 62 percent |
| The file name, "Key set" / "Key needed", the column sentence, filter words, the time on a row, reasons, B-roll line, the inactive Keep and Drop words, the Pace and Fade and Cover sentences, the status sentence, chat chips, the change line, recent rows, "Lists" and "Movies" headings, "lines" beside a count, the "Needs two or more shots" note | 12 |
| The number on a count tile | 15 monospace |
| Step counts, filter counts, the "Kept" title on a tile, block row legend, status hints | 11 |

## Window

960 × 680 on open, never under 960 × 640. The top bar is 56 px, the status bar at least 40 px. The lines column is 400 px when the window is at least 1280 px wide and 340 px below that. A 1 px `theme.line` divider separates it from the stage. From 1280 px the inspector is a 280 px column on the right with a 1 px `theme.line` on its left. Below 1280 px there is no third column: the inspector sits under the picture at the picture's width, as up to three short columns 16 px apart. At 960 × 640 the picture keeps about 220 px.

## The top bar

A `theme.surface` band, 56 px, 16 px side margins, 8 px between items, a 1 px `theme.line` under it. Left to right:

- **BotCut** at 13 DemiBold.
- The file name at 12 monospace, 62 percent, eliding in the middle, at most 220 px. The open movie's file, or the shot on the picture while gathering. Nothing on the empty home.
- A stretch, so the step sits near the middle.
- **Lists**: 13 at 62 percent, 38 while a job runs, 4 px each side, 32 px tall, `theme.hover` on hover. It sits only while a list or a movie is open. Clicking it closes the project and keeps the files. It is quieter than the step control.
- 8 px, then the step control: a `theme.background` track, 32 px tall, `theme.radius`, at its natural width. Inside it, 2 px of padding and 2 px between segments: **Shots**, **Lines**, **Movie**. Each segment is its word, 6 px, its count in 11 monospace, plus 8 px each side, 28 px tall. The current step is filled `theme.raised` with its word at 100 percent DemiBold and its count at 62. A reached step is 62 percent, `theme.hover` when hovered, its count at 62. A step not yet reached is 38 percent and does nothing. Lines is reached once a line list exists. Movie is reached once a movie is open.
- The counts: "Shots 4", "Lines 3/4", "Movie 0:10". If the row is tight, Lines drops the "/4" first, then Shots drops its count. Lists and the Movie clock stay whole.
- A stretch.
- **Undo** at 13, 62 percent, only while there is a revise snapshot to undo and no job runs. It calls the chat's undo, so the chat says what happened. There is no Redo.
- **Key set** or **Key needed** at 12, while spoken cuts are on. Set is 62 percent; needed is `theme.accent` at 100. Clicking either opens Settings on the key field. The word is never "connected".
- **Settings** and **Help** at 13, 62 percent, 4 px apart.
- 4 px, then the filled button: `theme.accent` with its label in `theme.accentForeground` at 13 DemiBold, 36 px tall. `theme.raised` with the label at 38 percent when disabled. Its word follows the step, below. While a job runs it is the job's sentence on `theme.raised` with an accent progress wash, disabled. Ctrl+Enter and Ctrl+R press it.

| Step | Filled button |
| --- | --- |
| Empty | **Add shots…** |
| Shots, no key | **Add xAI key…** |
| Shots | **Cut** |
| Shots, a file missing | **Cut**, disabled, not filled |
| Lines | **Render** |
| Lines, all dropped | **Render**, disabled, not filled |
| Unsaved rough cut | **Save…** |
| Saved rough cut | nothing |
| Hand trim | **Export…** |
| A job | the job's sentence, disabled, with progress |

## The lines column

A `theme.surface` column with 16 px side margins and 12 px top and bottom.

- **Empty**: "Pick up where you left off" at 16 DemiBold, then "Your shots will be listed here." at 13, 62 percent, or the recent "Lists" and "Movies" at 12, 38 percent, with 28 px rows at 12, 62 percent, `theme.selected` on hover.
- **Shots**: "Shots" at 15 DemiBold, 4 px, the shot list with 4 px between rows, and under it **Add shots…**, **Add a title card…**, and **Save list…** as quiet buttons that wrap. The shot row is unchanged.
- **Lines**, and **Movie** while the movie is the plan:
  - "Lines" at 15 DemiBold. 2 px. "BotCut picked these. Flip any line to keep or drop it." at 12, 62 percent, wrapping.
  - 12 px. The search field: `theme.raised`, 32 px, 12 px text inset, 13 px, placeholder "Search lines" at 38 percent, a 1 px `theme.accent` border while focused. Escape clears it, then leaves it. It hides rows whose words do not contain the text. Empty shows the filter.
  - 8 px. The filters, wrapping, 6 px apart: **All**, **Kept**, **Dropped**, **Unsure**, each a 28 px chip with its word at 12 and its count at 11 monospace, 10 px each side. Kept has a 6 px `theme.accent` dot, Dropped a `theme.foreground` dot at 38 percent, Unsure an accent dot at 38 percent. The current filter is `theme.raised` with its word at 100 percent and its count at 62; the others are 62 and 38, `theme.hover` on hover. Unsure means the reason is `unique?`. A filter only hides rows. It never changes keep and never asks the model.
  - 12 px, a 1 px `theme.line` rule, 8 px, then the rows. When nothing matches: "No line says that." or "No lines here." at 12, 38 percent.
  - 8 px, then the chat.
- A plain file says "One file, trimmed by hand." at 13.

### Line rows

Each row is one spoken span. 12 px left and right inset, 8 px top, 6 px between its two lines, 8 px under, then 4 px to the next row (inside the row, so a hidden row is 0 px). `theme.radius` corners. `theme.hover` on hover, `theme.selected` when selected or under the playhead. A kept row has a 2 px `theme.accent` bar down its left edge. A row hidden by the filter or the search stays in the list at 0 px.

- Top line, 8 px apart: the time at 12 px monospace in a 36 px minimum column, 62 percent (38 when dropped); the words at 13, wrapping, filling the width, 100 percent (38 and struck through when dropped).
- Second line, 12 px apart: the reason ("unsure" in `theme.accent`, "dropped", "put back", at 12, 62 percent, with "You · " in front when the reason is dropped or put back, read off the reason the model already keeps); the B-roll line at 12, 62 percent, eliding past 160 px; on the selected row **Play** then **Remove B-roll** when there is a cover, at 13; a stretch; then the Keep / Drop pair.
- The pair: a `theme.background` track, 24 px tall, `theme.radius`, with 2 px of padding and 2 px between **Keep** and **Drop**, each its word at 12 plus 8 px each side, 20 px tall, `theme.radius - 2`. The word in force is filled `theme.accent` with its word in `theme.accentForeground` at 100 percent DemiBold and does nothing when clicked. The other is 62 percent, `theme.hover` on hover, and flips the line: Drop sets keep false, Keep restores. Dropping never removes the row. The pair sits in the same place whether the row is selected or not.
- While busy, Keep, Drop, Play, and Remove B-roll read at 38 percent with an arrow cursor, and nothing flips.

### The chat

Unchanged in behavior. A 1 px `theme.raised` rule, 9 px, then 8 px between: the note in quotes at 13, the change line at 12, 62 percent, **Undo this change** at 13, three chips, and the field. The chips are **Make it tighter**, **Drop the pricing part**, **Under 90 seconds**: 24 px, a 1 px `theme.line` border, the words at 12, 62 percent (100 on hover, 38 while busy). A chip only fills the field and focuses it. It never sends. The field is `theme.raised`, 36 px, placeholder "Tell BotCut what to change" at 38 percent, with **Change this cut** in the accent inside it on the right once there is text.

## The stage

The center column: the picture well, then the transport, then the block row or the filmstrip, each 12 px from the left and right edges so they share one width. The stage is `theme.background`.

- **Picture well**: black, `theme.radius`, 12 px top, left, and right margins. Clicking it plays or pauses. On Empty it reads "Drop the shots for this movie here." at 16, then "MP4, MOV, or MKV, straight from your phone or camera." at 13, 62 percent, then a quiet **Trim one file instead…**, 8 px apart, centered. On Lines the current line's words sit over the bottom of the picture: a black chip at 75 percent, `theme.radius`, 16 px up from the bottom, at most 80 percent of the picture's width, the words at 14 in white, centered, wrapping, 12 px each side and 6 px above and below. It is in the window only. The export never carries it.
- 8 px, or 12 px when no transport shows.
- **Transport**: one 36 px row, items 8 px apart, vertically centered. On Lines with lines: **Previous**, Play, **Next**. Previous and Next are 28 px `theme.raised` chips, the word plus 16 px, 13 px at 100 percent, 38 when there is no line that way, `theme.hover` on hover. They move the current line and never start playback. Play is the 36 px `theme.raised` disc with the play or pause path in `theme.foreground`, 38 percent when it cannot play; it shows while a shot is previewing on Shots or Lines, and on Movie. On Movie, the clock follows: a 28 px `theme.raised` chip with "0:12 / 2:46" at 13 monospace. On the right, **Cut | Original**: a 28 px `theme.surface` chip with a 1 px `theme.line` border, 2 px of padding, two 24 px words at 13 with 8 px each side; the chosen one is `theme.raised` at 100 percent, the other 62, `theme.hover` on hover, 38 while busy. Cut is the resting choice; Original plays the file straight through, as Raw did. It shows on Lines once lines exist, and on Movie while the plan is the movie.
- 8 px.
- **Block row**, on Lines: a 56 px `theme.surface` card with a 1 px `theme.line` border and `theme.radius`, 10 px side and 8 px top and bottom padding. Top left, a legend at 11, 62 percent: a 10 × 6 accent swatch and "Kept", the same swatch at 24 percent and "Dropped", a 2 × 8 accent mark and "Unsure". Top right, "Click a block to show that line" at 11, 38 percent. Under it a 22 px track with one block per line that has a finite start and end, in order, each as wide as its share of the spoken time with a 1 px gap. A block is 16 px tall from 6 px down, 2 px corners, `theme.accent` when kept and the same accent at 24 percent (38 hovered) when dropped, which is the filmstrip's dropped-gap wash. An unsure line has a 2 × 4 accent mark above its block's left edge. The current line's block has a 1 px `theme.foreground` outline 2 px outside it. Clicking a block makes that line current and shows its frame. Nothing here trims.
- **Filmstrip**, on Movie: unchanged in look. 76 px tall, `theme.surface` film, `theme.accent` frames and handles, dim black gaps, a dropped line's gap the accent at 24 percent, the white playhead, the `theme.raised` hint chip inside the strip. Clicks still trim. 12 px under it, 4 px when zoomed, with "Zoomed to one shot. Z zooms out." at 13, 62 percent, 12 px under it.

## The inspector

The decisions, in this order: **This movie**, **Pace**, **Fade**, **Cover shots**, **Result**. Each heading is 12 DemiBold in capitals at 62 percent with 8 px under it, and 16 px separates sections. From 1280 px it is a 280 px `theme.surface` column with a 1 px `theme.line` on its left and 16 px padding, scrolling when it is taller than the window. Below 1280 px it sits under the picture on `theme.background`, 12 px in from the sides and 12 px from the bottom, as three columns 16 px apart: the sentence with Pace and Fade, then Cover shots, then Result. A column that has nothing to show is left out, and the inspector is hidden altogether when no section applies, as on the empty home.

- **This movie**, while spoken cuts are on and a shot or a line list exists: the sentence well. A `theme.raised` field, `theme.radius`, at least 36 px and growing as the sentence wraps, 12 px text inset, 13 px, placeholder "What is this movie? One sentence." at 38 percent, a 1 px `theme.accent` border while focused. It is `backend.intent`, edited in place on any step. Return leaves the field.
- **Pace**, on Lines, and on Shots for a speech cut once a shot is in: 4 px, "How much air to leave between lines." at 12, 62 percent, 8 px, then the one pace field in the window, bound to `backend.pace`: `theme.raised`, 36 px, `theme.hover` on hover, a 1 px `theme.accent` border while focused or open, text at 100 percent reading "Open · keeps long pauses", "Measured · natural pauses", "Tight · trims most pauses", or "Frenzied · cuts every breath". Space or Enter opens it. The open list sits directly under the field on `theme.raised`, rows 32 px, the chosen row's text `theme.accent`, the others 100 percent, `theme.hover` on hover. While busy the field reads at 38 percent and closes. Hiding the block closes the list and zeroes its slot. The seconds stay `Backend::maxPause`.
- **Fade**, with Pace: "Fade between shots" at 13, 2 px, "A short fade to black between shots." at 12, 62 percent, and on the right the one fade switch, vertically centered, no focus, 38 percent while busy. Checked when `backend.sceneTransition` is "dip"; clicking sets "dip" or "off". It is the same setting as "Fade to black between shots" in Settings. There is no cross-dissolve and no fade in or out from black.
- **Cover shots**, with Pace: "Cover lines with other shots" at 13, 2 px, "Show another shot's picture while the voice goes on." at 12, 62 percent, a switch on the right bound to `backend.broll`. Under it a check box and "Keep that shot's sound under the voice" at 13, bound to `backend.brollMix`, disabled at 38 percent while cover is off. When the tray has fewer than two shots: "Needs two or more shots. This list has 1." at 12, 38 percent. Settings keeps its own check boxes, in step through the same bindings.
- **Result**, once lines exist:
  - The kept sentence, `pictureSentence`: "0:10 kept of 0:14 – 3 lines, measured". The clocks (`keptClock`, `allClock`) are 13 px monospace, the rest (`sentenceWords`) 13 px sans, every item at 62 percent, no fill. If any line lacks a finite start or end, both clocks and the words between them are left out. No file is ever probed for a duration.
  - 8 px, a 6 px bar: `theme.background` track, `theme.accent` fill for the kept share, only when the clocks show.
  - 8 px, two tiles 8 px apart: `theme.raised`, `theme.radius`, 10 px sides and 8 px top and bottom, "Kept" or "Dropped" at 11, 62 percent, then the count at 15 monospace with "line" or "lines" at 12, 62 percent.
  - 8 px, **Review N unsure lines**, only when some line is unsure: 32 px, `theme.accent` at 12 percent (20 hovered) with a 1 px accent border at 40 percent, the words in `theme.accent` at 13 DemiBold. It only sets the filter to Unsure.
  - 8 px, **Cut again…**, a quiet button, while gathering: opens the existing "Cut again from the shots?" confirmation, which calls the existing cut. It never encodes, and it is disabled while a job runs or a shot is missing.

## The status bar

A `theme.surface` band with a 1 px `theme.line` top edge, at least 40 px, growing when the sentence wraps. 16 px side margins, 8 px between items, everything vertically centered.

- The sentence on the left, 12 px at 62 percent, wrapping, 240 px minimum. It turns `theme.accent` at 100 percent for a notice, a missing key, a missing file, or when every line is dropped.
- This step's quiet tools, 4 px apart: 28 px tall, no fill, `theme.hover` on hover, 13 px at 100 percent, 38 when disabled. Empty: **Open a saved list…**. No key: **Keep every shot instead**. A saved rough cut: **Show the file** first, then **Captions**, **Vertical short**, **Export another size…**. Nothing in the bar is ever filled.
- The keys on the right, 12 px apart, only when the row has room for them: the key at 11 monospace, 62 percent, then its word at 11, 38 percent. On Lines: Space play, ↑ ↓ line, K keep, D drop. On Shots: Space play, Alt ↑ ↓ move, Delete remove. On Movie: Space play, ← → seek, S split, X remove, Z zoom. K and D are aliases of the one toggle, each one way, and work only while the line keys do. X and Backspace still toggle.

The words by step:

| Step | Sentence | Quiet tools |
| --- | --- | --- |
| Empty | "Add the shots for one movie. You can put them in order after." | **Open a saved list…** |
| Shots, no key | "Spoken cuts need an xAI key." | **Keep every shot instead** |
| Shots | "4 shots, in this order. Cut finds the lines worth keeping." or "Cut joins all 4 shots in this order." | |
| Shots, a file missing | "DJI_20261008_092002.MP4 is missing. Remove it, or put the file back." | |
| Lines | "3 of 4 lines kept. Render makes the movie., 0:10" | |
| Lines, all dropped | "Every line is dropped. Keep one to render." | |
| Unsaved rough cut | "Your movie is ready. It's only in a temporary folder until you save it." | |
| Saved rough cut | "Saved as founder-story.mp4." | **Show the file**, **Captions**, **Vertical short**, **Export another size…** |
| Hand trim | "Trimmed by hand. Export writes a new file. Captions and the short wait until then." | |
| A job | the job's sentence | |

## The four frames

**Empty.** The top bar: BotCut, no file, the step control with Shots filled and Lines and Movie at 38 percent, no Lists, Key set or needed, Settings, Help, filled **Add shots…**. The left column: "Pick up where you left off" and the recent rows. The stage is the black well with the drop words. No transport, no inspector. The status bar: the empty sentence and **Open a saved list…**.

**Shots.** The top bar: the shot's file name, Lists, "Shots 4" filled, filled **Cut**. The left column: "Shots", the shot list with the selected row on `theme.selected`, then the list's three quiet buttons. The stage: the selected shot in the well, a transport with only Play. The inspector: This movie, Pace, Fade, Cover shots. The status bar: the shots sentence and the Shots keys.

**Lines.** The top bar: "Lines 3/4" filled, Undo when there is something to undo, filled **Render**. The left column: "Lines", its sentence, the search field, the four filters with counts, the rows with Keep and Drop on every one and Play on the selected one, and the chat with its three chips. The stage: the selected line's frame in the well with its words over it, a transport with Previous, Play, Next, and Cut | Original, then the block row. The inspector: This movie, Pace, Fade, Cover shots, Result with "0:10 kept of 0:14 – 3 lines, measured", the bar, the tiles, Review N unsure lines, and Cut again…. The status bar: the lines sentence and Space play, ↑ ↓ line, K keep, D drop. At 960 × 640 the inspector is three columns under the picture and the picture keeps about 220 px.

**Movie.** The top bar: the movie's file name, "Movie 0:10" filled, and the save state's button: **Save…**, **Export…**, or nothing. The left column: the line list with the line under the playhead marked, and the chat. The stage: the movie in the well, a transport with Play, "0:12 / 2:46", and Cut | Original, then the filmstrip. The inspector: This movie and Result; no Pace, Fade, or Cover shots. The status bar follows the save state, with **Show the file** first after a save, and the Movie keys.

## Left out

No waveform, threshold, minimum-duration slider, padding slider, blips, volume, mute, fullscreen, fade in from black, fade out to black, a new pace, redo, Font Awesome, web fonts, a fixed pink, a second accent, multi-track, markers, mixer, or handoff to Premiere, Resolve, Final Cut, ScreenFlow, or CapCut. The caption is never burned into the file. The empty home, the title-card dialog, and the quit confirmation are unchanged. Play and pause are still the only icons. Settings is not restyled.
