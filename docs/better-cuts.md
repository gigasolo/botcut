# Better cuts

Spoken cuts still edit a retake session. A finished movie needs a stated intent, a chance to fix the selects before the long encode, and joins that do not click.

## What the cut decides today

Spoken cuts send Grok a transcript and one instruction: these are takes of one video, keep the last clean reading of a repeated line, drop flubs, and never drop unique content. The model may return only utterance ids. The app pads each keep by 0.15 s before and 0.25 s after, snaps those edges to silence, and splits a pause longer than 0.8 s. All files, in order skips that and pastes every file from start to end.

That instruction matches a demo where the same line is said three times. On the ride, four different moments went in, one file was dropped entirely, and lines the checker marked `unique?` stayed out. The model was never told "this is a ride, keep the beats in order." It never sees the picture, so a silent look or a blur is invisible. The reasons it returns are stored on the segments and ignored by the trimmer.

You meet the cut only after a 4K encode of the rough cut, a second pass that builds `master.mp4`, and a third encode on Export.

## The three to build

### 1. Say what the movie is

Add one line on the tray, saved in the shot list as `intent`. The speech prompt uses that line. The default is: keep each moment in order, drop flubs and true retakes, and keep a beat that appears only once.

The old retake sentence is used only when the intent says these are repeated takes of one script. All files, in order is unchanged and still needs no key.

Old lists still open. A missing `intent` means the new default. The file still holds version, mode, files, and now this one string. No API key.

### 2. Confirm the selects before the encode

Split the speech run in two. The first step transcribes, asks for keep ids and reasons, and writes `cuts.json` without starting ffmpeg. The tray lists every line as kept or dropped, with the reason. Restore puts a dropped line back with reason `restored` and does not call the model again. Render starts after that confirmation and is the step that prints `Rendering N%`.

This is where a whole file dropped by mistake gets fixed in seconds, before the 4K encode. `unique?` becomes a row with a button. Assemble still renders immediately, because it keeps every file.

### 3. Make the joins watchable

In the rough-cut encode, crossfade the audio for about 40 ms at each join, and leave a breath of air on the edges instead of clipping the sentence with the fixed 0.15 / 0.25 s pad. Bring the clips to one loudness so a cut does not jump. The model is not involved. Frame sampling, music, and color wait.

The trimmer still opens on the master so handles and Ctrl+Z keep working. Export stays the file you save.

## Left for later

A few frames per line, so a silent shot or a blur can change a keep. Playing the selects straight from the originals so the master encode can wait. Those are the next step after these three, because the intent and the confirm step fix the wrong movie first.
