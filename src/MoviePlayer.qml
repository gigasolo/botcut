import QtQuick
import QtMultimedia
import "Format.js" as Format

// The picture player. Moved out of the window without a change in behavior.
Item {
    id: root
    property var host
    property var film
    property var videoItem
    property alias player: player
    property alias playbackDevices: playbackDevices
    property alias audioOutputComponent: audioOutputComponent
    property alias primeFallback: primeFallback

    MediaPlayer {
        id: player
        source: root.host.gathering ? backend.previewUrl : (root.host.planSource !== "" ? root.host.planSource : backend.source)
        videoOutput: root.videoItem
        audioOutput: root.host.audioOutput

        // Render the opening frame on load instead of showing black. Playback
        // starts muted and stops as soon as VideoOutput receives a frame.
        // A line seek waits until this file is loaded, starts playback, then
        // seeks. Seeking a paused FFmpeg player clears the picture and stalls.
        property bool primed: false
        property bool priming: false
        property bool lineSeeked: false
        property bool lineArmed: false
        property int lineToken: 0

        function mediaReady() {
            return mediaStatus === MediaPlayer.LoadedMedia || mediaStatus === MediaPlayer.BufferedMedia;
        }

        function armLine() {
            ++lineToken;
            lineArmed = false;
            lineSeeked = false;
            priming = false;
            primeFallback.stop();
            playLoadedLine();
        }

        function playLoadedLine() {
            if (root.host.linePlayStart < 0 || lineSeeked)
                return;
            priming = false;
            primeFallback.stop();
            if (!mediaReady())
                return;
            primed = true;
            var token = lineToken;
            if (playbackState !== MediaPlayer.PlayingState)
                play();
            if (playbackState === MediaPlayer.PlayingState)
                seekPlayingLine(token);
        }

        function seekPlayingLine(token) {
            if (lineSeeked || token !== lineToken || root.host.linePlayStart < 0 || !mediaReady())
                return;
            lineSeeked = true;
            Qt.callLater(function() {
                if (token !== lineToken || root.host.linePlayStart < 0 || !mediaReady())
                    return;
                position = root.host.linePlayStart;
            });
        }

        function startPriming() {
            if (root.host.linePlayStart >= 0) {
                playLoadedLine();
                return;
            }
            if (primed || priming || source.toString() === "")
                return;
            root.host.ensureAudioOutput();
            primed = true;
            priming = true;
            position = 0;
            play();
            primeFallback.restart();
        }

        function finishPriming() {
            if (!priming)
                return;
            primeFallback.stop();
            pause();
            if (root.host.linePlayStart < 0)
                position = 0;
            priming = false;
        }

        onSourceChanged: {
            primeFallback.stop();
            priming = false;
            primed = false;
            lineSeeked = false;
            lineArmed = false;
            ++lineToken;
        }
        onMediaStatusChanged: {
            if (mediaReady())
                startPriming();
        }
        onPlaybackStateChanged: {
            if (playbackState === MediaPlayer.PlayingState)
                seekPlayingLine(lineToken);
        }
        onPositionChanged: {
            if (root.host.gathering && root.host.linePreview && root.host.linePlayStart >= 0
                    && root.host.linePlayEnd >= root.host.linePlayStart) {
                if (!lineArmed && position + 250 >= root.host.linePlayStart && position < root.host.linePlayEnd)
                    lineArmed = true;
                if (lineArmed && Format.linePlayReachedEnd(position, root.host.linePlayStart, root.host.linePlayEnd,
                        playbackState === MediaPlayer.PlayingState)) {
                    lineArmed = false;
                    root.host.linePreview = false;
                    pause();
                    root.host.linePlayStart = -1;
                    root.host.linePlayEnd = -1;
                    return;
                }
            }
            // The player is on one source file. Its position is not the filmstrip clock.
            if (backend.planCut && !root.host.gathering) {
                if (priming && position > 0) {
                    finishPriming();
                    return;
                }
                if (root.host.linePlayStart >= 0 && root.host.linePlayEnd >= root.host.linePlayStart) {
                    if (!root.host.planArmed && position + 250 >= root.host.linePlayStart && position < root.host.linePlayEnd)
                        root.host.planArmed = true;
                    if (root.host.planPlaying && root.host.planArmed && Format.linePlayReachedEnd(position, root.host.linePlayStart,
                            root.host.linePlayEnd, playbackState === MediaPlayer.PlayingState)) {
                        // The shared display time is also the block that just finished.
                        var nextIndex = root.host.planIndex + 1;
                        root.host.planArmed = false;
                        if (nextIndex < 0 || nextIndex >= backend.plan.clips.length) {
                            pause();
                            root.host.planPlaying = false;
                            root.film.playheadSec = backend.plan.edgeFrom(backend.plan.duration, 1);
                        } else {
                            var sourceStart = backend.plan.edgeTime(nextIndex, true);
                            root.film.playheadSec = backend.plan.displayForSource(nextIndex, sourceStart);
                            root.host.armPlanIndex(nextIndex, sourceStart, true);
                        }
                        return;
                    }
                    if (!root.host.planPlaying && lineSeeked && playbackState === MediaPlayer.PlayingState
                            && Math.abs(position - root.host.linePlayStart) < 400) {
                        root.host.planArmed = true;
                        pause();
                    }
                    if (!root.film.interacting && root.host.planIndex >= 0) {
                        var shown = Math.max(root.host.linePlayStart, Math.min(position, root.host.linePlayEnd)) / 1000;
                        var display = backend.plan.displayForSource(root.host.planIndex, shown);
                        // A paused out-point maps to the next block's start. Keep this block.
                        if (!root.host.planPlaying) {
                            var blockEnd = backend.plan.displayForSource(
                                    root.host.planIndex, backend.plan.edgeTime(root.host.planIndex, false));
                            if (display >= blockEnd - 0.0005)
                                display = backend.plan.playheadForEdge(root.host.planIndex, false);
                        }
                        root.film.playheadSec = display;
                    }
                }
                return;
            }
            if (!root.host.gathering) {
                root.host.linePlayStart = -1;
                root.host.linePlayEnd = -1;
                root.host.linePreview = false;
                lineArmed = false;
            }
            if (priming && position > 0) {
                finishPriming();
                return;
            }
            if (root.host.gathering)
                return;
            // Play only the clips: hop over gaps and stop after the last clip.
            if (playbackState === MediaPlayer.PlayingState) {
                var t = position / 1000, next = root.host.timeline.playableFrom(t);
                // Past the last clip: stop where we are. Seeking to its end
                // could land past the final frame.
                if (next < 0) {
                    pause();
                    root.film.playheadSec = root.host.timeline.edgeFrom(backend.duration, 1);
                    return;
                }
                if (next - t > 0.05) {
                    position = Math.round(next * 1000);
                    return;
                }
            }
            if (!root.film.interacting)
                root.film.playheadSec = position / 1000;
        }
    }

    MediaDevices {
        id: playbackDevices
        onAudioOutputsChanged: root.host.followDefaultOutput()
    }

    Component {
        id: audioOutputComponent
        AudioOutput {
            muted: player.priming
        }
    }

    Timer {
        id: primeFallback
        interval: 250
        repeat: false
        onTriggered: player.finishPriming()
    }
}
