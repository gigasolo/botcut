# Better cuts

Spoken cuts edit a movie, not only a retake session.

## What a spoken cut does

The shot screen and Settings share one line, **This movie**. The default is: keep each moment in order, drop flubs and true retakes, and keep a beat that appears only once. That line is saved in the shot list as `intent`. The retake prompt is used only when the line says these are repeated takes. Turning Spoken cuts off keeps every file, in order, and does not need a key.

The shot screen also holds the pace: **Open**, **Measured**, **Tight**, or **Frenzied**. That choice is the longest pause the cutter will leave inside a kept line: 0.8, 0.4, 0.28, or 0.1 seconds. **Dip to black between files** sits beside it, and the same checkbox is in Settings.

**Cut** transcribes, asks for keep ids and reasons, and lists every line. It does not start ffmpeg. **Drop** and **Restore** change that list and do not call the model again. **Render** is the encode, and the status reads `Rendering N%`. If every line is dropped, Render refuses until one is restored.

The model may return only utterance ids and a reason. One still from the middle of each line goes with the transcript, and that still is shown on the row. Each keep is padded by 0.25 seconds before and 0.40 seconds after, snapped to silence, and split when a pause inside it is longer than the pace. Neighbors in the same file merge when the gap before padding is under 1 second. The rough cut levels the clips, fades in and out, and dips through black between files unless that setting is off.

The app then plays `rough_cut.mp4`. It does not build `master.mp4`. `botcut-cli review` still can, from the command line.

## Change this cut

Under Lines, one field reads **Change this cut**, with **Send**. Before any note, that is the whole thread. After a note, the last three notes sit above the field, and **Revert** appears.

Send runs `botcut-cli revise` on the current `cuts.json` and the note. The model may return only the movie sentence, the pace, dip on or off, the keep ids and reasons, and whether the next step is nothing, render, captions, or a short. It does not return times, padding, or any join other than dip. An id that is not in the current lines is ignored. A listed id is kept. An unlisted id is dropped. The app writes the sentence, the pace, and Dip to black, and updates the lines. It keeps one snapshot from just before that apply. Revert puts the snapshot back. A second revise replaces the snapshot.

That reply does not start ffmpeg. The status becomes "Ready to render", "Ready for captions", or "Ready for a short". **Render**, **Captions**, and **Short** stay the buttons that encode.

## Open and close cards

**Open card** and **Close card** sit beside the pace. Each opens one line, filled with the movie sentence, and **Make card**. The line stays hidden until then.

Make card builds a 16:9 still from the sentence and holds it for 3 seconds. An open card is inserted at the front of the tray. A close card is inserted at the end. The card is a shot the person can reorder or remove. It is not painted onto a camera file. The footer reads "Making the card…" until that job finishes. One job runs at a time, so Send, Revert, the card buttons, the pace, and the trim handles stay disabled while it runs, the same as the tray.

Spoken cuts skip speech-to-text on a card and do not send it to the keep model. The card is one kept line spanning the shot, reason `card`, showing the sentence. Assemble keeps the file like any other, in tray order.

## Trim the keeps

When the open movie is this cut's plan, Watch shows one block per segment in `cuts.json`, in order. A handle changes that segment's source start or end, clamped inside its own file, with the same 0.1 second minimum. Removing a block drops the segment. A gap restores the range captured when Watch opened. Undo is one gesture.

Playback loads the source under the playhead. It does not play the baked file as the thing being trimmed. An untouched plan still **Save**s by copying `rough_cut.mp4`. Once a handle has moved, the button reads **Export** and re-encodes those segments. **Captions** and **Short** stay disabled until that export. A movie that is not a plan cut still trims as one timeline.

## Left for later

More than one frame per line. Playing the selects straight from the originals, so the encode can wait. Music, color, a free-typed join, and a burned-in title stay out.
