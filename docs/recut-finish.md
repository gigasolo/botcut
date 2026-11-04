# BotCut recut finish

This spec is for the Qt implementer. It covers the visual finish of the window that already exists: a 360 px plan on the left and the picture on the right, with steps Lists, Shots, Lines, and Movie. It changes only the surfaces below. Everything else stays as docs/ux-pilot.md describes it. Where this file and docs/ux-pilot.md disagree, docs/ux-pilot.md wins.

Rules for every surface here:

- Colors are only these tokens: theme.background, theme.surface, theme.raised, theme.selected, theme.hover, theme.line, theme.scrim, theme.foreground at 100, 62, or 38 percent, theme.accent, theme.accentForeground, and black.
- Text opacity sits on the text item itself, never on a parent that also holds text.
- "Busy" means `backend.busy`, which is true while a job runs.
- No new component file. Each change goes in the file named for it.
- This file describes the look and the words. The implementer already has the playback rules. Nothing here adds behavior beyond what is written.
- The step is still called Lines. There is no tab named Sections and no second transcript. The line list is the section list.

## Sample used in this spec

These are the sample lines from docs/ux-pilot.md, with an end time added so that the sentence under the picture can be worked out. A row still shows only the start.

| Start | End | Words | State |
| --- | --- | --- | --- |
| 0:12 | 0:15 | We started in the garage. | kept, selected |
| 0:41 | 0:45 | The first customers were shops on the same street. | kept |
| 1:05 | 1:09 | The first customers were shops on the same street. | dropped |
| 1:28 | 1:31 | Then we opened the second location. | kept, reason "put back" |

The pace is Measured and the fade is on.

Kept span: 3 + 4 + 3 = 10 seconds, so 0:10. Span of every line: 3 + 4 + 4 + 3 = 14 seconds, so 0:14. Kept count: 3. The sentence under the picture is:

> 0:10 kept of 0:14 – 3 lines, measured

The saved rough cut in the examples is `founder-story.mp4`.

---

## 1. Line rows

**File:** src/LineRow.qml. The delegate in src/PlanPane.qml keeps passing `selected`, `marked`, `timeText`, `reasonText`, and `coverText` as it does now.

**Words:** "Drop", "Keep", "Play", and "Remove B-roll" (this last one only when the line has a cover, as now). The reasons stay "unsure", "dropped", and "put back".

**Layout:**

- Each row is one spoken span: its start time, its words, and whether it stays.
- Top row, left to right:
  - The time: monospace, 12 px.
  - The words: 13 px, wrapping, filling the width.
  - **Drop**, or **Keep** when the line is dropped: 13 px, aligned right and to the top of the words.
- The Drop/Keep word keeps the same place whether the row is selected or not, so selecting a row never moves it.
- The Drop/Keep hit area is the word plus 6 px each side and 4 px above and below. On hover it shows a theme.hover rectangle at theme.radius behind the word.
- Under that, the reason and B-roll line is unchanged: 12 px at 62 percent.
- Under that, on the selected row only: **Play**, then **Remove B-roll** when there is a cover. Both are 13 px, start at the row's 12 px left margin, and sit 12 px apart.
- Selecting a row moves the picture to that span, under the existing playback rules.

| State | Row fill | Time | Words | Drop / Keep | Play |
| --- | --- | --- | --- | --- | --- |
| Resting (kept, not selected) | none | theme.foreground 62% | theme.foreground 100% | "Drop", theme.foreground 100% | hidden |
| Selected | theme.selected | theme.foreground 62% | theme.foreground 100% | "Drop" or "Keep", theme.foreground 100% | "Play", theme.foreground 100% |
| Dropped (selected or not) | as above | theme.foreground 38% | theme.foreground 38% | "Keep", theme.foreground 100% | "Play" at 100% if selected |
| Marked on Movie (line under the playhead) | theme.selected, plus the existing 2 px theme.accent bar at the left | as resting or dropped | as resting or dropped | as resting or dropped | hidden |
| Busy | unchanged | unchanged | unchanged | theme.foreground 38%, no hover, arrow cursor | theme.foreground 38%, arrow cursor |

Remove B-roll follows the same rule as Play: 100 percent, or 38 percent while busy. Drop/Keep is visible on every row wherever the line list shows, including Movie while the movie is the plan. The chat at the bottom of the list is unchanged.

## 2. Pace and Fade in the plan

**File:** src/PlanPane.qml. The Settings binding is in src/SettingsDialog.qml.

**Words:**

- "Pace"
- "How much air to leave between lines."
- The existing closed field, which reads one of "Open · keeps long pauses", "Measured · natural pauses", "Tight · trims most pauses", or "Frenzied · cuts every breath".
- "Fade"
- "A short fade between shots."
- A switch with no text of its own.

**Where:**

- **Shots** (stack index 1): under the movie-sentence well, while `backend.cutMode === "speech"`. This is the same condition as the well. The order is: the sentence well, 8 px, the Pace block, 12 px, the Fade block, 8 px, then the shot list.
- **Lines** (stack index 2, while `host.viewStep === "lines"`): fixed above the ListView, so it does not scroll. The order is the Pace block, 12 px, the Fade block, 8 px, then the list. It is hidden on Movie while the movie is the plan.
- The list header on Lines keeps "This movie" and the movie sentence. The header's pace sentence (the `pacePhrase` label at 62 percent) comes out, because the closed Pace field directly above now says it. Then the divider follows as now.

**Pace block:**

- "Pace": 13 px, Font.DemiBold, theme.foreground 100 percent.
- 2 px gap.
- "How much air to leave between lines.": 12 px, theme.foreground 62 percent, wrapping.
- 6 px gap.
- The existing `paceBox`: closed field, open list, hover, focus border, and keys all unchanged. On Lines it is the same field, bound to the same `backend.pace`.

**Fade block:**

- A row. On the left, a column with "Fade" (13 px, Font.DemiBold, 100 percent), a 2 px gap, then "A short fade between shots." (12 px, 62 percent, wrapping).
- On the right, a Switch, vertically centered on that column. It is the same Material Switch as the Spoken cuts switch in SettingsDialog.qml, with `focusPolicy: Qt.NoFocus`.
- The switch is checked when `backend.sceneTransition === "dip"`. Clicking it sets `"dip"` or `"off"`.

**Settings:**

- The "Fade to black between shots" control in SettingsDialog.qml keeps its words and its place. It already binds `backend.sceneTransition`, so it and the plan switch stay in step.
- No other Settings control is drawn in the plan.

| State | Labels | Sentences | Pace field | Fade switch |
| --- | --- | --- | --- | --- |
| Resting | theme.foreground 100% | theme.foreground 62% | theme.surface, text 100%, hover theme.hover | on: theme.accent. off: the switch's own off look, with no new color |
| Selected (field focused or open) | unchanged | unchanged | 1 px theme.accent border. Open list: chosen row text theme.accent, others 100%, hover theme.hover | does not take focus |
| Dropped | does not apply | does not apply | does not apply | does not apply |
| Busy | unchanged | unchanged | text 38%, no hover, closes if open (as now) | `enabled: false`, opacity 0.38 on the Switch item (it holds no text) |

## 3. The sentence under the picture

**File:** src/Main.qml, in the right-hand ColumnLayout. It is the last child, after the "Zoomed to one shot. Z zooms out." label.

**Words:** `<kept> kept of <all> – <n> lines, <pace>`

- `<kept>` is the sum of end minus start over the kept lines. This is `keptSpan()`.
- `<all>` is the same sum over every line.
- Both clocks use `lineClock()` (m:ss).
- `<n>` is the number of kept lines. Use "1 line" when one is kept.
- `<pace>` is the pace name in lower case: "open", "measured", "tight", or "frenzied".
- The dash is an en dash (U+2013) with a space on each side.
- If any line has no start or no end, leave out both clocks and the words between them, so it reads `<n> lines, <pace>`, for example "3 lines, measured".
- Sample: "0:10 kept of 0:14 – 3 lines, measured".

**When:** visible while `backend.selects.length > 0`, on any step. That means:

- On Lines it sits directly under the picture well.
- On Movie it sits under the filmstrip and the zoom line.
- A plain file with no line list never shows it.

It does not go in the footer. The footer stays as it is.

**Look:**

- 13 px, one line, eliding at the right.
- 12 px left and right margins, to line up with the picture well. 12 px bottom margin.
- The clocks are `font.family: "monospace"`. The rest is the system sans.
- Every text item is theme.foreground at 0.62 opacity, with no fill behind it.
- Use either a Row of Labels, each at 0.62, or one Label with `Text.StyledText` that wraps the clocks in a monospace font tag.

| State | Look |
| --- | --- |
| Resting | theme.foreground 62% |
| Selected | does not apply. Selecting a line does not change it |
| Dropped | does not apply. Dropping a line changes the numbers, not the look |
| Busy | unchanged, 62% |

## 4. Cut or Raw beside play

**File:** src/Main.qml.

**Words:** "Cut" or "Raw". Cut is the resting choice. It is a word, not an icon. Play and pause stay the only icon buttons.

**Where:**

- **Lines:** right of the PlayButton that sits over the picture at the bottom left (the one shown while `gathering && previewing && !hasVideo`). Visible only while `viewStep === "lines"`. It is 8 px right of the button and vertically centered on it.
- **Movie:** inside the existing Row over the picture. The order is PlayButton, then the word, then the time chip, with the Row's 8 px spacing. Visible only while `backend.planCut`.
- It is not shown on Shots, and not shown for a plain file with no line list.

**Look:** the same chip as the time chip.

- A Rectangle 28 px tall, as wide as the label plus 16 px, at theme.radius, in theme.raised.
- The label is 13 px system sans, centered, theme.foreground 100 percent.
- On hover the chip is theme.hover and the cursor is a pointing hand.

| State | Chip | Label |
| --- | --- | --- |
| Resting | theme.raised | "Cut", theme.foreground 100% |
| Selected (the other choice) | theme.raised | "Raw", theme.foreground 100% |
| Dropped | does not apply | does not apply |
| Busy | theme.raised, no hover, arrow cursor | theme.foreground 38% |

## 5. Filmstrip gaps while the movie is the plan

**File:** src/EditBar.qml, in the gap Repeater inside `track`.

**Words:** none new. The hint chip, the handles, the playhead, and the "×" stay exactly as they are.

**Look:**

- A kept range keeps its accent frame: a theme.accent border, `frameW` 3, `frameRadius` 8, with theme.accent handles.
- A gap that is a dropped line, only while `root.plan` is true, is that gap's Rectangle drawn in theme.accent with `opacity: 0.24` set on that Rectangle only. Hovered, it is 0.38.
  - It has no border, no radius, no pattern, and no text.
  - It sits on the track's theme.surface, so it reads as the accent washed back.
  - Neither the track, nor the parent Item, nor EditBar gets that opacity.
- Every other gap stays black at the alpha it uses now: 0.784, or 0.565 when hovered.

| State | Kept range | Dropped-line gap | Other gap |
| --- | --- | --- | --- |
| Resting | theme.accent frame and handles | theme.accent, opacity 0.24 on the gap rectangle | black, as now |
| Selected (hovered) | as now | theme.accent, opacity 0.38 on the gap rectangle | black, hover alpha as now |
| Dropped | does not apply | this gap is the dropped state | does not apply |
| Busy | the whole EditBar at 0.45, as now | 0.24 under that 0.45, no hover | as now under 0.45 |

## 6. Footer save ending

**File:** src/ActionBar.qml. The sentence comes from `actionSentence` in src/Main.qml and is unchanged.

| Step | Sentence | Buttons, left to right after Settings and "?" |
| --- | --- | --- |
| Unsaved rough cut (`movieUnsaved`) | "Your movie is ready. It's only in a temporary folder until you save it." | filled **Save…** |
| Saved rough cut (`movieSaved` and `backend.roughCut`) | "Saved as " plus the file name, for example "Saved as founder-story.mp4." | quiet **Show the file**, quiet **Captions**, quiet **Vertical short**, quiet **Export another size…** |
| Hand trim (`trimmed`) | "Trimmed by hand. Export writes a new file. Captions and the short wait until then." | filled **Export…** |

**Show the file:**

- An ActionButton with `filled: false`.
- Visible only on a saved rough cut while no job runs (`!bar.running`).
- It is placed first among the step's buttons.

After a rough cut is saved, nothing in the footer is filled, and the filled button does not become Export…. The quiet buttons use the existing ActionButton look: no fill at rest, theme.hover on hover, label theme.foreground 100 percent.

At 960 px the saved rough cut row fits. The sentence keeps its 240 px minimum and wraps, and the footer grows, as it does now.

| State | Show the file |
| --- | --- |
| Resting | no fill, label theme.foreground 100% |
| Selected (hover) | theme.hover |
| Dropped | does not apply |
| Busy | `enabled: false`, label 38%. While a job runs, it hides with the other buttons, as now |

## 7. Export size label

**File:** src/portalfilepicker.cpp, `PortalFilePicker::exportVideo`. This is the "Quality" choice in the save dialog, which opens from Save… and Export another size….

**Words:**

- The source entry reads the source width, " x ", the source height, then " (original)". For example: "1280 x 720 (original)".
- The smaller entries keep "1080p" and "720p".
- The choice id stays `"original"`.
- The width and height are the ones `Backend::exportDialog` already reads from `m_info`.

The choice still appears only when a smaller size exists, as now. A 1280 x 720 source therefore offers no choice at all. A 3840 x 2160 source reads "3840 x 2160 (original)", "1080p", "720p".

States: the dialog opens only when no job is running, so it has no busy state. It has no selected or dropped look beyond the portal's own.

---

## Leave out

Do not draw or build any of these:

- a waveform, or a zoom control on a waveform
- a threshold
- a minimum-duration slider
- a blips slider
- a tool that splits one recording into separate exported files
- an export to Premiere, Resolve, Final Cut, ScreenFlow, or CapCut
- multi-track, or a mixer
- a second accent, a light theme, web fonts, an icon toolbar, a sidebar, or a right rail

## Copy added or changed

| Surface | Words |
| --- | --- |
| Line row | "Drop" or "Keep" on every row. "Play" on the selected row |
| Plan, Shots and Lines | "Pace", "How much air to leave between lines.", "Fade", "A short fade between shots." |
| Lines list header | The pace sentence leaves the header. The closed Pace field above shows it |
| Under the picture | "0:10 kept of 0:14 – 3 lines, measured" (sample) |
| Beside play | "Cut" or "Raw" |
| Footer, saved rough cut | "Show the file" |
| Export size dialog | "1280 x 720 (original)" in place of "Original" |
