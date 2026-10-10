# Better cuts

Spoken cuts edit a movie, not only a retake session. The three changes below are in the app.

## What a spoken cut does

Settings holds one line, **This movie**. The default is: keep each moment in order, drop flubs and true retakes, and keep a beat that appears only once. That line is saved in the shot list as `intent`. The retake prompt is used only when the line says these are repeated takes. Turning Spoken cuts off keeps every file, in order, and does not need a key.

**Cut** transcribes, asks for keep ids and reasons, and lists every line. It does not start ffmpeg. **Drop** and **Restore** change that list and do not call the model again. **Render** is the encode, and the status reads `Rendering N%`. If every line is dropped, Render refuses until one is restored.

The model may return only utterance ids and a reason. One still from the middle of each line goes with the transcript, and that still is shown on the row. Each keep is padded by 0.25 seconds before and 0.40 seconds after, snapped to silence, and split when a pause inside it is longer than 0.8 seconds. Neighbors in the same file merge when the gap before padding is under 1 second. The rough cut levels the clips, fades in and out, and dips through black between files unless that setting is off.

The app then plays `rough_cut.mp4`. It does not build `master.mp4`. `botcut-cli review` still can, from the command line.

## Left for later

More than one frame per line. Playing the selects straight from the originals, so the encode can wait. Music and color stay out.
