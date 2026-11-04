# BotCut chrome

This is the chrome as built in the QML, after the chrome pass. It records the spacing, the type sizes, the words, and the theme tokens that are actually in `src/Main.qml`, `src/PlanPane.qml`, `src/LineRow.qml`, `src/ActionBar.qml`, and `src/PlayButton.qml`. Where this file and `docs/ux-pilot.md` disagree on chrome, this file wins. Behavior in `docs/recut-finish.md` wins over both.

The window is still one dark Omarchy app. The structure taken from Recut is the grouping: a transport bar over a time picture with one result line, a rail card of named decisions with a segmented control on top, and a footer with one next action. None of Recut's silence tools, its light theme, its waveform, or its sliders came along.

## Tokens

Only the tokens in `src/theme.h`, plus black.

| Role | Token |
| --- | --- |
| Window, the step control's track | theme.background |
| Rail card, footer band | theme.surface |
| Rail card border, footer top line, the line between the plan and the stage | theme.line |
| Play disc, Cut / Raw chip, clock chip, current step segment, fields in the card (sentence well, closed pace field, open pace list), dividers in the lists | theme.raised |
| Hover on the play disc, the chips, a step segment, Lists, a field, a pace row, a quiet button | theme.hover |
| Selected shot, selected line, line under the playhead, hovered recent row | theme.selected |
| Filled button, playhead frames and handles, missing file, missing key, notice, chosen pace row text, focus border | theme.accent |
| Filled button label | theme.accentForeground |
| Picture well | black |
| Dialog dim | theme.scrim |

Text is theme.foreground at 100, 62, or 38 percent. The opacity sits on the text item. The only parents that carry an opacity are the play disc (38 percent when disabled, it holds no text), the Fade switch (38 percent while busy, it holds no text), and the filmstrip (45 percent while busy, as before).

Type is the system sans. Monospace is used only on the clocks: the row time in a line row, the transport clock, and the two clocks in the kept sentence. Qt 6.12 StyledText ignores a font face, so those clocks are separate Labels with `font.family: "monospace"`. Nothing puts a typeface in rich text.

Corners are `theme.radius`. Inside the step control, the segments and the Lists hover use `theme.radius - 2`, never below 0.

## Type sizes

| Use | Size, weight |
| --- | --- |
| "Pick up where you left off", "Drop the shots for this movie here." | 16, DemiBold / Normal |
| Step words, Lists, Pace, Fade, field text, line words, Drop, Keep, Play, buttons, footer sentence, the kept sentence, Cut / Raw, the transport clock | 13 |
| Current step word, Pace, Fade, a filled button's label | 13 DemiBold |
| Row time, the Pace and Fade sentences, reasons, B-roll line, recent rows, "This movie", "Lists" and "Movies" headings, shot size | 12 |
| "?" | 16 |

## Window

960 × 680 on open, never under 960 × 640. The plan is 360 px on the left. A 1 px `theme.line` divider separates it from the stage. The footer runs under both.

## The plan

The pane has a 16 px left and right margin and a 12 px top and bottom margin. Its column has 12 px between the rail card and the list under it.

### The rail card

One `theme.surface` rectangle with a 1 px `theme.line` border and `theme.radius` corners. 12 px padding on every side. 12 px between its rows. Its height is its content. The lists scroll under it, not inside it.

Row one is the way home and the step.

- **Lists**: a 13 px word at 62 percent, 38 percent while a job runs, 4 px of padding each side, 32 px tall, hover `theme.hover`. It sits only while a list or a movie is open. On the empty home it is not shown. Clicking it closes the project and keeps the files.
- 8 px, then the step control: a `theme.background` track, 32 px tall, `theme.radius`, filling the rest of the row. Inside it, 2 px of padding and 2 px between segments, three segments share the width: **Shots**, **Lines**, **Movie**. Each segment is its word plus 8 px each side, 28 px tall. The current step is filled `theme.raised` with its word at 100 percent DemiBold. A reached step is 62 percent, and `theme.hover` when hovered. A step not yet reached is 38 percent and does nothing. Lines is reached once a line list exists. Movie is reached once a movie is open.
- The words carry their counts: "Shots 4", "Lines 3 of 4", "Movie 0:10". If the row is tight, Lines drops the "of 4" first, then Shots drops its count. Lists and the Movie clock stay whole.

Row two, on Shots only, while spoken cuts are on and a shot is in: the movie sentence well. A `theme.raised` field, 36 px tall, 12 px text inset, placeholder "What is this movie? One sentence." at 38 percent, 1 px `theme.accent` border while focused.

Row three, on Shots with spoken cuts and a shot, and on Lines always: the decisions. Hidden on Movie and on the empty home. Hiding it closes the pace list and zeroes the slot.

- **Pace**, 13 DemiBold at 100 percent. 2 px. "How much air to leave between lines." at 12 px, 62 percent, wrapping. 6 px. The pace field: `theme.raised`, 36 px, `theme.hover` on hover, 1 px `theme.accent` border while focused or open, text at 100 percent reading "Open · keeps long pauses", "Measured · natural pauses", "Tight · trims most pauses", or "Frenzied · cuts every breath". Space or Enter opens it. The open list sits directly under the field on `theme.raised`, rows 32 px, the chosen row's text `theme.accent`, the others 100 percent, hover `theme.hover`. While busy the field reads at 38 percent and closes.
- 12 px.
- **Fade**, 13 DemiBold at 100 percent. 2 px. "A short fade between shots." at 12 px, 62 percent. A Material Switch on the right, vertically centered, no focus, 38 percent while busy. Checked when the fade is on. It is the same setting as "Fade to black between shots" in Settings.

One field serves Shots and Lines, bound to `backend.pace`. One switch serves both, bound to `backend.sceneTransition`. There is one pace field in the window.

### Under the card

- **Empty**: "Pick up where you left off" at 16 DemiBold, then "Your shots will be listed here." at 13, 62 percent, or the recent "Lists" and "Movies" at 12, 38 percent, with 28 px rows at 12, 62 percent, `theme.selected` on hover.
- **Shots**: the shot list, 4 px between rows, and under it **Add shots…**, **Add a title card…**, and **Save list…** as quiet buttons. The shot row is unchanged.
- **Lines**: the line list, 4 px between rows. Its header is "This movie" at 12, 38 percent, then the movie sentence at 13, 8 px, a 1 px `theme.raised` rule, 8 px. Under the list, the chat, unchanged: the hint at 12, 38 percent, the note in quotes at 13, the change line at 12, 62 percent, **Undo this change** at 13, and the `theme.surface` field with **Change this cut** in the accent inside it on the right.
- **Movie** while the plan is the movie: the same line list and chat, with the line under the playhead marked. A plain file says "One file, trimmed by hand." at 13.

### Line rows

12 px left and right inset, 8 px top, 4 px between the rows inside. `theme.radius` corners. `theme.selected` fill when selected or marked, a 2 px `theme.accent` bar at the left when marked.

- Top row, 8 px apart: the time at 12 px monospace in a 36 px minimum column so the words line up, 62 percent (38 when dropped); the words at 13, wrapping, filling the width, 100 percent (38 when dropped); **Drop** or **Keep** at 13, 100 percent, top-aligned at the right. Its hit area is the word plus 6 px each side and 4 px above and below, `theme.hover` on hover. It sits in the same place whether the row is selected or not.
- Under that, the reason ("unsure", "dropped", "put back") and the B-roll line at 12, 62 percent.
- On the selected row only: **Play**, then **Remove B-roll** when there is a cover, 13 px, 12 px apart, starting at the row's 12 px inset.
- While busy, Drop, Keep, Play, and Remove B-roll read at 38 percent with an arrow cursor.

## The stage

The right column is one stage: the picture well, then the transport bar, then the filmstrip, then the kept sentence, each 12 px from the left and right edges so they share one width.

- **Picture well**: black, `theme.radius`, 12 px top, left, and right margins. Clicking it plays or pauses. Nothing floats on it any more except the empty state's words. On Empty it reads "Drop the shots for this movie here." at 16, then "MP4, MOV, or MKV, straight from your phone or camera." at 13, 62 percent, then a quiet **Trim one file instead…**, 8 px apart, centered.
- 8 px, or 12 px when no transport shows.
- **Transport**: one 36 px row, items 8 px apart, vertically centered. On the left, Play: a 36 px `theme.raised` disc with the play or pause path in `theme.foreground`, `theme.hover` on hover, 38 percent when it cannot play. It shows while a shot is previewing on Shots or Lines, and on Movie. Then **Cut** or **Raw**: a 28 px `theme.raised` chip, the word plus 16 px, 13 px at 100 percent, `theme.hover` on hover, 38 percent while busy. It shows on Lines once lines exist, and on Movie while the plan is the movie. On the right, the clock: the same chip with "0:12 / 2:46" in 13 px monospace, on Movie only. The bar is not shown on Empty, on Shots with nothing to preview, or on Shots with a movie open.
- 8 px, or 12 px when no filmstrip follows.
- **Filmstrip**: unchanged in look. 76 px tall, `theme.surface` film, `theme.accent` frames and handles, dim black gaps, a dropped line's gap the accent at 24 percent, the white playhead, the `theme.raised` hint chip. 8 px under it when the sentence follows, 12 px otherwise, 4 px when zoomed, with "Zoomed to one shot. Z zooms out." at 13, 62 percent, 8 px under it.
- **The kept sentence**: "0:10 kept of 0:14 – 3 lines, measured". The clocks are 13 px monospace, the rest 13 px sans, every item at 62 percent, no fill. It is 12 px from the left, right, and bottom of the stage. It shows on any step once lines exist, so on Lines it sits under the transport, and on Movie under the filmstrip.

## The footer

A `theme.surface` band with a 1 px `theme.line` top edge, at least 56 px tall, growing when the sentence wraps. 16 px side margins, 8 px between items, everything vertically centered.

- The sentence on the left, 13 px at 62 percent, wrapping, 240 px minimum. It turns `theme.accent` at 100 percent for a notice, a missing key, a missing file, or when every line is dropped.
- **Settings** at 13, 62 percent, then **?** at 16, 62 percent. These are the quietest words in the row.
- This step's quiet buttons: no fill, `theme.hover` on hover, 13 px at 100 percent, 38 percent when disabled.
- The filled button last: `theme.accent` with its label in `theme.accentForeground` at 13 DemiBold. `theme.raised` when disabled, and `theme.raised` with an accent progress wash while a job runs, when it is the only button.

The words by step:

| Step | Sentence | Quiet | Filled |
| --- | --- | --- | --- |
| Empty | "Add the shots for one movie. You can put them in order after." | **Open a saved list…** | **Add shots…** |
| Shots, no key | "Spoken cuts need an xAI key." | **Keep every shot instead** | **Add xAI key…** |
| Shots | "4 shots, in this order. Cut finds the lines worth keeping." or "Cut joins all 4 shots in this order." | | **Cut** |
| Shots, a file missing | "DJI_20261008_092002.MP4 is missing. Remove it, or put the file back." | **Cut**, disabled | |
| Lines | "3 of 4 lines kept. Render makes the movie., 0:10" | **Cut again…** | **Render** |
| Lines, all dropped | "Every line is dropped. Keep one to render." | **Cut again…**, **Render** disabled | |
| Unsaved rough cut | "Your movie is ready. It's only in a temporary folder until you save it." | | **Save…** |
| Saved rough cut | "Saved as founder-story.mp4." | **Show the file**, **Captions**, **Vertical short**, **Export another size…** | nothing |
| Hand trim | "Trimmed by hand. Export writes a new file. Captions and the short wait until then." | | **Export…** |
| A job | the job's sentence | | the job's button, disabled, with progress |

## The four frames

**Empty.** The card holds only the step control, Shots filled, Lines and Movie at 38 percent, no Lists. Under it, "Pick up where you left off" and the recent rows. The stage is the black well with the drop words. No transport. The footer: the empty sentence, Settings, ?, **Open a saved list…**, filled **Add shots…**.

**Shots.** Lists, then the control with "Shots 4" filled. The sentence well, then Pace and Fade, inside the card. Under it the shot list with the selected row on `theme.selected`, then the list's three quiet buttons. The stage: the selected shot in the well, a transport with only Play. The footer: the shots sentence, Settings, ?, filled **Cut**.

**Lines.** Lists, then the control with "Lines 3 of 4" filled. Pace and Fade in the card. Under it "This movie", the movie sentence, the rule, the line rows with Drop or Keep on every row and Play on the selected one, and the chat at the bottom. The stage: the selected line's frame in the well, a transport with Play and **Cut**, then "0:10 kept of 0:14 – 3 lines, measured". The footer: the lines sentence, Settings, ?, **Cut again…**, filled **Render**. At 960 × 640 the card is about 200 px tall, which leaves the current line and the chat on screen.

**Movie.** Lists, then the control with "Movie 0:10" filled. No decisions in the card. Under it, the line list with the line under the playhead marked, and the chat. The stage: the movie in the well, a transport with Play, **Cut**, and "0:12 / 2:46" on the right, the filmstrip, then the kept sentence. The footer follows the save state in the table above.

## Left out

No waveform, threshold, minimum-duration slider, blips slider, zoom on a waveform, skip buttons, light theme, web fonts, icon toolbar, right rail, second accent, multi-track, mixer, or export to Premiere, Resolve, Final Cut, ScreenFlow, or CapCut. Play and pause are still the only icons. Settings is not restyled.
