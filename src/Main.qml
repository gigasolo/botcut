import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import QtMultimedia
import "Format.js" as Format

ApplicationWindow {
    id: win
    width: 960
    height: 680
    minimumWidth: 960
    minimumHeight: 640
    visible: true
    title: {
        if (backend.source.toString() !== "")
            return "BotCut — " + fileName(backend.source);
        if (previewing)
            return "BotCut — " + fileName(backend.previewUrl);
        return "BotCut";
    }
    readonly property bool hasVideo: backend.source.toString() !== ""
    readonly property bool gathering: backend.gathering
    readonly property bool previewing: gathering && backend.previewUrl.toString() !== ""
    readonly property color accent: theme.accent
    readonly property color accentForeground: theme.accentForeground
    readonly property bool controlFocused: activeFocusItem
            && (activeFocusItem instanceof TextInput
                || activeFocusItem instanceof TextEdit
                || activeFocusItem instanceof TextArea
                || activeFocusItem instanceof AbstractButton
                || activeFocusItem instanceof ComboBox
                || activeFocusItem instanceof Slider)
    readonly property bool audioOutputReady: audioOutput !== null
    property var audioOutput: null
    // So the first device signal does not reopen a stream already on this default.
    property string playbackDeviceId: ""
    property string noticeText: ""
    property bool helpVisible: false
    property bool quitConfirmVisible: false
    property bool settingsOpen: false
    property bool settingsFromMovie: false
    property bool shotsPinned: false
    property bool titleCardOpen: false
    property bool confirmCutOpen: false
    property string leaveTarget: ""
    onQuitConfirmVisibleChanged: {
        if (!quitConfirmVisible)
            leaveTarget = "";
    }
    // Three columns from 1280 px. Below that the decisions sit under the picture.
    readonly property bool wideInspector: width >= 1280
    // Which rows the line list shows: all, kept, dropped, or unsure. Hides rows only.
    property string lineFilter: "all"
    property int currentLine: -1
    property int lastSelectCount: 0
    readonly property int selectCount: backend.selects.length
    onSelectCountChanged: {
        if (selectCount > 0 && lastSelectCount === 0) {
            shotsPinned = false;
            currentLine = 0;
        } else if (currentLine >= selectCount) {
            currentLine = selectCount > 0 ? 0 : -1;
        }
        if (selectCount === 0)
            lineFilter = "all";
        lastSelectCount = selectCount;
    }
    // The current line's words, shown over the picture. Never in the file.
    readonly property string currentLineText: {
        if (currentLine < 0 || currentLine >= backend.selects.length)
            return "";
        var line = backend.selects[currentLine];
        if (!line || line.text === undefined || line.text === null)
            return "";
        return String(line.text);
    }
    // The keys the status bar names, by what is on screen. Only keys the app has.
    readonly property var keyHints: {
        if (viewStep === "movie" && hasVideo) {
            return [["Space", qsTr("play")], ["← →", qsTr("seek")], ["S", qsTr("split")],
                    ["X", qsTr("remove")], ["Z", qsTr("zoom")]];
        }
        if (viewStep === "lines")
            return [["Space", qsTr("play")], ["↑ ↓", qsTr("line")], ["K", qsTr("keep")], ["D", qsTr("drop")]];
        if (backend.tray.length > 0)
            return [["Space", qsTr("play")], ["Alt ↑ ↓", qsTr("move")], ["Delete", qsTr("remove")]];
        return [];
    }
    // The picture stays put. The pane follows the work, unless Shots was pinned.
    readonly property string viewStep: {
        if (hasVideo && !gathering)
            return "movie";
        if (backend.selects.length > 0 && !shotsPinned)
            return "lines";
        return "shots";
    }
    // The stub used by layout tests leaves step empty. Infer the same order as Backend::computeStep.
    readonly property string displayStep: {
        if (backend.busy)
            return "working";
        if (backend.step !== "")
            return backend.step;
        if (!gathering && hasVideo) {
            if (backend.planCut ? backend.plan.unexported : timeline.unexported)
                return "trimmed";
            if (looseCut)
                return "movieUnsaved";
            return "movieSaved";
        }
        if (backend.tray.length === 0)
            return "empty";
        if (missingShotCount() > 0)
            return "missingShot";
        if (backend.selects.length > 0)
            return keptLineCount() > 0 ? "lines" : "allDropped";
        if (backend.cutMode === "speech" && !backend.apiKeySet)
            return "needsKey";
        return "shotsReady";
    }
    readonly property string actionSentence: {
        if (backend.job !== "")
            return backend.jobText !== "" ? backend.jobText : backend.status;
        if (noticeText !== "")
            return noticeText;
        var step = displayStep;
        if (step === "needsKey")
            return qsTr("Spoken cuts need an xAI key.");
        if (step === "missingShot")
            return qsTr("%1 is missing. Remove it, or put the file back.").arg(firstMissingShot());
        if (step === "shotsReady") {
            var count = backend.tray.length;
            if (backend.cutMode !== "speech")
                return qsTr("Cut joins all %1 shots in this order.").arg(count);
            return qsTr("%1 shots, in this order. Cut finds the lines worth keeping.").arg(count);
        }
        if (step === "lines") {
            var sentence = qsTr("%1 of %2 lines kept. Render makes the movie.")
                    .arg(keptLineCount()).arg(backend.selects.length);
            var span = keptSpan();
            if (span > 0)
                sentence += ", " + lineClock(span);
            return sentence;
        }
        if (step === "allDropped")
            return qsTr("Every line is dropped. Keep one to render.");
        if (step === "movieUnsaved")
            return qsTr("Your movie is ready. It's only in a temporary folder until you save it.");
        if (step === "trimmed")
            return qsTr("Trimmed by hand. Export writes a new file. Captions and the short wait until then.");
        if (step === "movieSaved")
            return qsTr("Saved as %1.").arg(fileName(backend.source));
        if (step === "empty")
            return qsTr("Add the shots for one movie. You can put them in order after.");
        if (step === "working")
            return backend.jobText !== "" ? backend.jobText : backend.status;
        return "";
    }
    readonly property bool actionNeedsYou: displayStep === "needsKey" || displayStep === "missingShot"
                                           || displayStep === "allDropped"
    readonly property bool dialogUp: settingsOpen || helpVisible || titleCardOpen
                                     || confirmCutOpen || quitConfirmVisible
    readonly property bool lineKeys: viewStep === "lines" && !controlFocused && !dialogUp
                                     && !backend.busy && !editing && !planPane.paceKeys
    readonly property bool shotKeys: viewStep === "shots" && !controlFocused && !dialogUp
                                     && !backend.busy && !editing
    property int linePlayStart: -1
    property int linePlayEnd: -1
    // Shot preview only. Plan playback reuses the markers below and must not pause a shot.
    property bool linePreview: false
    // Show one frame at linePlayStart, then pause. Play leaves this false.
    property bool lineHold: false
    // Cut is the resting preview. Raw plays the file straight through.
    property bool cutPreview: true
    // A cut chain stops on cutUntilMs, not on linePlayEnd. That range is the
    // one-line preview and the plan segment, and sharing it stops the other mode.
    property bool cutChain: false
    property int cutLine: -1
    property int cutUntilMs: -1
    // Plan playback reuses the line seek. These stay clear for an ordinary movie.
    property bool planArmed: false
    property bool planPlaying: false
    property int planIndex: -1
    property string planSource: ""
    readonly property string statusText: noticeText !== "" ? noticeText : backend.status

    readonly property var timeline: backend.planCut ? backend.plan : backend.timeline
    // Quitting only warns about unexported cuts. Clips spanning the whole
    // video are never dirty — that's just the source.
    readonly property bool unexported: hasVideo && timeline.unexported
    // A rendered movie with no handle edits lives only in /tmp until it is saved.
    readonly property bool looseCut: backend.renderedUnsaved && !unexported
    // Editing shortcuts go quiet while a dialog is up, a handle is dragged, or a job is running.
    readonly property bool editing: hasVideo && !gathering && !settingsOpen
                                   && (backend.planCut ? backend.plan.duration : backend.duration) > 0
                                   && !quitConfirmVisible && !helpVisible && !titleCardOpen
                                   && !confirmCutOpen && !editBar.interacting
                                   && !backend.busy

    Material.theme: Material.Dark
    Material.accent: win.accent
    Material.roundedScale: theme.radius
    color: theme.background

    function fileName(url) {
        var s = url.toString();
        return s === "" ? "" : decodeURIComponent(s.substring(s.lastIndexOf('/') + 1));
    }
    function baseName(path) {
        var s = path.toString();
        var i = s.lastIndexOf("/");
        return i < 0 ? s : s.substring(i + 1);
    }
    function fileUrl(path) {
        if (!path)
            return "";
        if (String(path).indexOf("file:") === 0)
            return path;
        return "file://" + encodeURI(path);
    }
    function lineClock(seconds) {
        var whole = Math.max(0, Math.floor(seconds));
        var mins = Math.floor(whole / 60);
        var secs = whole % 60;
        return mins + ":" + (secs < 10 ? "0" : "") + secs;
    }
    function keptLineCount() {
        var n = 0;
        for (var i = 0; i < backend.selects.length; i++) {
            var line = backend.selects[i];
            if (line && line.keep !== false)
                n++;
        }
        return n;
    }
    function keptSpan() {
        var total = 0;
        for (var i = 0; i < backend.selects.length; i++) {
            var line = backend.selects[i];
            if (!line || line.keep === false)
                continue;
            var start = Number(line.start);
            var end = Number(line.end);
            if (!isFinite(start) || !isFinite(end))
                continue;
            total += Math.max(0, end - start);
        }
        return total;
    }
    function missingShotCount() {
        var n = 0;
        for (var i = 0; i < backend.tray.length; i++) {
            if (!backend.trayFileExists(backend.tray[i]))
                n++;
        }
        return n;
    }
    function firstMissingShot() {
        for (var i = 0; i < backend.tray.length; i++) {
            if (!backend.trayFileExists(backend.tray[i]))
                return baseName(backend.tray[i]);
        }
        return "";
    }
    function keptLine(line) {
        if (!line || line.keep === false)
            return false;
        return isFinite(Number(line.start)) && isFinite(Number(line.end));
    }
    function clearCutChain() {
        cutChain = false;
        cutLine = -1;
        cutUntilMs = -1;
    }
    function endCutChain() {
        clearCutChain();
        linePlayStart = -1;
        linePlayEnd = -1;
        linePreview = false;
        lineHold = false;
        planPlaying = false;
        planArmed = false;
        if (movie.player.playbackState === MediaPlayer.PlayingState)
            movie.player.pause();
    }
    function playLine(line, playThrough) {
        if (!gathering || !line)
            return;
        var clip = line.clip;
        if (clip < 0 || clip >= backend.tray.length)
            return;
        if (playThrough === undefined)
            playThrough = true;
        // One line, not the chain. The chain's end must not keep running.
        clearCutChain();
        linePlayStart = Math.max(0, Math.round(line.start * 1000));
        linePlayEnd = Math.max(linePlayStart, Math.round(line.end * 1000));
        linePreview = playThrough;
        lineHold = !playThrough;
        if (backend.trayIndex !== clip)
            backend.trayIndex = clip;
        ensureAudioOutput();
        movie.player.armLine();
    }
    // Play, then seek, then pause. A seek while paused clears the picture.
    function showLine(line) {
        if (!line || line.start === undefined || line.start === null)
            return;
        var start = Number(line.start);
        if (!isFinite(start))
            return;
        playLine(line, false);
    }
    // Load the source under a plan-filmstrip time and seek to that source range.
    function armPlan(displayTime, play) {
        if (!backend.planCut)
            return;
        showPlanHit(backend.plan.sourceAt(displayTime), play);
    }
    // The segment under a handle, while its display range overlaps a neighbor.
    function armPlanIndex(index, sourceTime, play) {
        if (!backend.planCut)
            return;
        showPlanHit(backend.plan.sourceFor(index, sourceTime), play);
    }
    function showPlanHit(hit, play) {
        clearCutChain();
        planPlaying = play;
        planArmed = false;
        linePreview = false;
        lineHold = false;
        if (!hit.ok) {
            planPlaying = false;
            planArmed = false;
            linePlayStart = -1;
            linePlayEnd = -1;
            movie.player.pause();
            return;
        }
        linePlayStart = Math.max(0, Math.round(hit.source * 1000));
        linePlayEnd = Math.max(linePlayStart, Math.round(hit.end * 1000));
        planIndex = hit.index;
        var url = fileUrl(hit.path);
        ensureAudioOutput();
        if (movie.player.priming)
            movie.player.finishPriming();
        if (planSource !== url) {
            planSource = url;
            movie.player.armLine();
            return;
        }
        if (play) {
            if (movie.player.playbackState !== MediaPlayer.PlayingState)
                movie.player.play();
            movie.player.position = linePlayStart;
        } else {
            movie.player.pause();
            movie.player.position = linePlayStart;
        }
    }
    function showNotice(text) {
        noticeText = text;
        noticeTimer.restart();
    }
    function openVideo() {
        backend.openVideoDialog();
    }
    function openSettings() {
        settingsFromMovie = hasVideo && !gathering;
        if (movie.player.playbackState === MediaPlayer.PlayingState)
            movie.player.pause();
        settingsOpen = true;
    }
    function closeSettings() {
        var returnToMovie = settingsFromMovie && hasVideo;
        settingsOpen = false;
        settingsFromMovie = false;
        if (returnToMovie)
            backend.showMovie();
    }
    // Back to the recent lists. The files on disk stay where they are.
    function closeProjectNow() {
        movie.player.stop();
        planPlaying = false;
        shotsPinned = false;
        currentLine = -1;
        backend.closeProject();
    }
    function closeProject() {
        if (backend.busy)
            return;
        if (unexported) {
            leaveTarget = "lists";
            if (movie.player.playbackState === MediaPlayer.PlayingState)
                movie.player.pause();
            quitConfirmVisible = true;
            return;
        }
        closeProjectNow();
    }
    function openTitleCard() {
        titleCardOpen = true;
    }
    function focusApiKey() {
        settingsDialog.focusKey();
    }
    function moveLine(delta) {
        if (backend.selects.length === 0)
            return;
        var next = currentLine + delta;
        if (next < 0)
            next = 0;
        if (next >= backend.selects.length)
            next = backend.selects.length - 1;
        if (next === currentLine)
            return;
        currentLine = next;
        showLine(backend.selects[next]);
    }
    function toggleCurrentLine() {
        if (backend.busy || currentLine < 0 || currentLine >= backend.selects.length)
            return;
        var line = backend.selects[currentLine];
        if (!line)
            return;
        if (line.keep !== false)
            backend.dropSelect(line.id);
        else
            backend.restoreSelect(line.id);
    }
    // K and D are the one toggle, each way. A line already there stays there.
    function keepCurrentLine() {
        if (backend.busy || currentLine < 0 || currentLine >= backend.selects.length)
            return;
        var line = backend.selects[currentLine];
        if (line && line.keep === false)
            backend.restoreSelect(line.id);
    }
    function dropCurrentLine() {
        if (backend.busy || currentLine < 0 || currentLine >= backend.selects.length)
            return;
        var line = backend.selects[currentLine];
        if (line && line.keep !== false)
            backend.dropSelect(line.id);
    }
    function playCurrentLine() {
        if (currentLine < 0 || currentLine >= backend.selects.length)
            return;
        playLine(backend.selects[currentLine]);
    }
    // The one revise snapshot, through the chat so it can say what happened.
    function undoRevise() {
        if (backend.busy || !backend.canRevert)
            return;
        planPane.undoRevise();
    }
    function nudgeShot(delta) {
        if (backend.busy || backend.tray.length === 0)
            return;
        var index = backend.trayIndex;
        if (index < 0)
            index = 0;
        var next = index + delta;
        if (next < 0 || next >= backend.tray.length)
            return;
        backend.trayIndex = index;
        backend.moveTray(delta);
    }
    function removeCurrentShot() {
        if (backend.busy || backend.tray.length === 0)
            return;
        if (backend.trayIndex < 0)
            backend.trayIndex = 0;
        backend.removeTray();
    }
    function exportVideo() {
        if (!win.hasVideo || backend.busy)
            return;
        if (backend.planCut) {
            if (backend.plan.duration <= 0)
                return;
        } else if (backend.duration <= 0) {
            return;
        }
        movie.player.pause();
        planPlaying = false;
        if (backend.planCut && backend.plan.unexported)
            backend.exportPlan();
        else
            backend.exportDialog();
    }
    function ensureAudioOutput() {
        if (audioOutput === null && (win.hasVideo || win.previewing)) {
            audioOutput = movie.audioOutputComponent.createObject(win);
            rememberDefaultOutput();
        }
    }
    function releaseAudioOutput() {
        if (audioOutput === null)
            return;
        var oldAudioOutput = audioOutput;
        audioOutput = null;
        oldAudioOutput.destroy();
    }
    // QByteArray ids arrive as an ArrayBuffer. An empty device must not throw.
    function currentOutputId() {
        try {
            var device = movie.playbackDevices.defaultAudioOutput;
            if (!device)
                return "";
            var raw = device.id;
            if (raw === undefined || raw === null || raw === "")
                return "";
            if (typeof raw === "string")
                return raw;
            if (typeof raw.byteLength !== "number" || raw.byteLength === 0
                    || typeof Uint8Array !== "function")
                return "";
            var bytes = new Uint8Array(raw);
            var text = "";
            for (var i = 0; i < bytes.length; ++i)
                text += String.fromCharCode(bytes[i]);
            return text;
        } catch (e) {
            return "";
        }
    }
    function rememberDefaultOutput() {
        var id = currentOutputId();
        if (id !== "")
            playbackDeviceId = id;
    }
    // PipeWire keeps the stream on the node it opened on. A new default does not move it.
    function followDefaultOutput() {
        var id = currentOutputId();
        if (id === "" || id === playbackDeviceId)
            return;
        playbackDeviceId = id;
        if (audioOutput === null)
            return;
        var wasPlaying = movie.player.playbackState === MediaPlayer.PlayingState && !movie.player.priming;
        var at = movie.player.position;
        audioOutput.device = movie.playbackDevices.defaultAudioOutput;
        if (!wasPlaying)
            return;
        // Seek only after play. A seek on a paused FFmpeg player clears the picture.
        movie.player.pause();
        movie.player.play();
        Qt.callLater(function() {
            if (movie.player.playbackState === MediaPlayer.PlayingState)
                movie.player.position = at;
        });
    }
    function syncPlaybackAudio() {
        if (hasVideo || previewing) {
            ensureAudioOutput();
            return;
        }
        movie.player.stop();
        releaseAudioOutput();
    }
    // Display time of this source second on the plan block for the line's clip.
    // The packed out-point is the next block's start, so park inside this one.
    function planTimeForLine(line, sourceSec) {
        if (!backend.planCut || !line)
            return -1;
        var clip = Number(line.clip);
        var source = Number(sourceSec);
        if (!isFinite(clip) || !isFinite(source))
            return -1;
        var blocks = backend.plan.clips;
        if (!blocks)
            return -1;
        var best = -1;
        var bestDist = 0;
        var bestSource = source;
        var bestEnd = 0;
        for (var i = 0; i < blocks.length; ++i) {
            var seg = backend.plan.sourceFor(i, source);
            if (!seg || !seg.ok || Number(seg.clip) !== clip)
                continue;
            var clamped = Number(seg.source);
            var dist = Math.abs(clamped - source);
            if (best < 0 || dist < bestDist) {
                best = i;
                bestDist = dist;
                bestSource = clamped;
                bestEnd = Number(seg.end);
            }
        }
        if (best < 0)
            return -1;
        planIndex = best;
        if (source >= bestEnd)
            return backend.plan.playheadForEdge(best, false);
        return backend.plan.displayForSource(best, bestSource);
    }
    function playCutFrom(index) {
        var lines = backend.selects;
        if (!lines || index < 0 || index >= lines.length || !keptLine(lines[index]))
            return false;
        var line = lines[index];
        var start = Number(line.start);
        var end = Number(line.end);
        var clip = Number(line.clip);
        var path = "";
        if (gathering) {
            if (!isFinite(clip) || clip < 0 || clip >= backend.tray.length)
                return false;
        } else {
            // cuts.json paths stay in clip-index order when the tray is reordered.
            if (isFinite(clip) && clip >= 0 && backend.cutClips && clip < backend.cutClips.length)
                path = String(backend.cutClips[clip] || "");
            if (!path && isFinite(clip) && clip >= 0 && clip < backend.tray.length)
                path = String(backend.tray[clip] || "");
            if (!path)
                return false;
        }
        var jump = Format.nextKeptAir(lines, index, backend.maxPause);
        var air = 0;
        if (jump && isFinite(Number(jump.air)) && Number(jump.air) > 0)
            air = Number(jump.air);
        // No linePlayEnd. That marker is a plan segment and a one-line preview.
        cutChain = true;
        cutLine = index;
        linePreview = false;
        lineHold = false;
        planPlaying = false;
        planArmed = false;
        linePlayEnd = -1;
        linePlayStart = Math.max(0, Math.round(start * 1000));
        cutUntilMs = Math.max(linePlayStart, Math.round((end + air) * 1000));
        ensureAudioOutput();
        if (movie.player.priming)
            movie.player.finishPriming();
        if (gathering) {
            if (backend.trayIndex !== clip)
                backend.trayIndex = clip;
            movie.player.armLine();
            return true;
        }
        var shown = planTimeForLine(line, start);
        if (shown >= 0)
            editBar.playheadSec = shown;
        var url = fileUrl(path);
        if (planSource !== url)
            planSource = url;
        movie.player.armLine();
        return true;
    }
    function beginCut(plan) {
        var lines = backend.selects;
        var index = -1;
        // A resolved block stays on that clip. The first kept line is only
        // for a playhead with no block under it and none after it.
        var anchored = false;
        if (plan) {
            if (backend.planCut) {
                var hit = backend.plan.sourceAt(editBar.playheadSec);
                if (!hit || !hit.ok) {
                    var nextAt = backend.plan.playableFrom(editBar.playheadSec);
                    if (nextAt >= 0)
                        hit = backend.plan.sourceAt(nextAt);
                }
                if (hit && hit.ok && hit.clip !== undefined) {
                    anchored = true;
                    var clip = Number(hit.clip);
                    var source = Number(hit.source);
                    if (isFinite(clip) && isFinite(source)) {
                        var best = -1;
                        var bestDist = 0;
                        for (var p = 0; p < lines.length; ++p) {
                            var under = lines[p];
                            if (!keptLine(under) || Number(under.clip) !== clip)
                                continue;
                            var lineStart = Number(under.start);
                            var lineEnd = Number(under.end);
                            // The block is padded past the stored line. Distance
                            // zero is that line; the pad is the part outside it.
                            var dist = 0;
                            if (source < lineStart)
                                dist = lineStart - source;
                            else if (source > lineEnd)
                                dist = source - lineEnd;
                            if (best < 0 || dist < bestDist) {
                                best = p;
                                bestDist = dist;
                            }
                        }
                        index = best;
                    }
                }
            }
        } else {
            var current = currentLine;
            if (current >= 0 && current < lines.length && keptLine(lines[current]))
                index = current;
            else {
                var start = current >= 0 ? current + 1 : 0;
                for (var i = start; i < lines.length; ++i) {
                    if (keptLine(lines[i])) {
                        index = i;
                        break;
                    }
                }
            }
        }
        if (index < 0 && !anchored) {
            for (var n = 0; n < lines.length; ++n) {
                if (keptLine(lines[n])) {
                    index = n;
                    break;
                }
            }
        }
        if (index < 0)
            return false;
        return playCutFrom(index);
    }
    function togglePlay() {
        if (win.gathering) {
            if (!win.previewing)
                return;
            ensureAudioOutput();
            if (movie.player.priming)
                movie.player.finishPriming();
            if (movie.player.playbackState === MediaPlayer.PlayingState) {
                movie.player.pause();
                if (cutChain)
                    endCutChain();
                return;
            }
            if (viewStep === "lines" && backend.selects.length > 0) {
                if (cutPreview) {
                    beginCut(false);
                } else {
                    // A leftover line end, plan end, or cut end would pause Raw.
                    endCutChain();
                    linePlayStart = 0;
                    linePlayEnd = -1;
                    linePreview = false;
                    lineHold = false;
                    movie.player.armLine();
                }
                return;
            }
            movie.player.play();
            return;
        }
        if (backend.planCut) {
            if (backend.plan.duration <= 0)
                return;
            ensureAudioOutput();
            if (movie.player.priming)
                movie.player.finishPriming();
            if (movie.player.playbackState === MediaPlayer.PlayingState) {
                movie.player.pause();
                planPlaying = false;
                if (cutChain)
                    endCutChain();
                return;
            }
            if (!cutPreview) {
                // The file under the playhead, from that source time. No segment
                // end, so playback does not hop to the next file.
                endCutChain();
                var rawHit = backend.plan.sourceAt(editBar.playheadSec);
                if (!rawHit || !rawHit.ok) {
                    var rawFrom = backend.plan.playableFrom(editBar.playheadSec);
                    if (rawFrom >= 0)
                        rawHit = backend.plan.sourceAt(rawFrom);
                }
                if (rawHit && rawHit.ok) {
                    var rawSource = Number(rawHit.source);
                    planIndex = rawHit.index;
                    linePlayEnd = -1;
                    linePlayStart = isFinite(rawSource) ? Math.max(0, Math.round(rawSource * 1000)) : 0;
                    if (isFinite(rawSource))
                        editBar.playheadSec = backend.plan.displayForSource(rawHit.index, rawSource);
                    var rawUrl = fileUrl(rawHit.path);
                    ensureAudioOutput();
                    if (movie.player.priming)
                        movie.player.finishPriming();
                    if (planSource !== rawUrl)
                        planSource = rawUrl;
                    movie.player.armLine();
                    return;
                }
                if (movie.player.playbackState !== MediaPlayer.PlayingState)
                    movie.player.play();
                return;
            }
            if (beginCut(true))
                return;
            var planFrom = backend.plan.playableFrom(editBar.playheadSec);
            armPlan(planFrom < 0 ? backend.plan.edgeFrom(0, -1) : planFrom, true);
            return;
        }
        if (!win.hasVideo || backend.duration <= 0)
            return;
        ensureAudioOutput();
        if (movie.player.priming)
            movie.player.finishPriming();
        if (movie.player.playbackState === MediaPlayer.PlayingState) {
            movie.player.pause();
            return;
        }
        // Play only the clips: from the playhead if it's in one, else from
        // the next clip, and from the top once past the last.
        var from = timeline.playableFrom(editBar.playheadSec);
        seekTo(from < 0 ? timeline.edgeFrom(0, -1) : from);
        movie.player.play();
    }
    function seekTo(seconds) {
        if (backend.planCut) {
            if (backend.plan.duration <= 0)
                return;
            if (movie.player.priming)
                movie.player.finishPriming();
            var planTime = Math.max(0, Math.min(seconds, backend.plan.duration));
            editBar.playheadSec = planTime;
            var keepPlaying = planPlaying && movie.player.playbackState === MediaPlayer.PlayingState;
            armPlan(planTime, keepPlaying);
            return;
        }
        if (!win.hasVideo || backend.duration <= 0)
            return;
        if (movie.player.priming)
            movie.player.finishPriming();
        var t = Math.max(0, Math.min(seconds, backend.duration));
        editBar.playheadSec = t;
        movie.player.position = Math.round(t * 1000);
    }
    property bool quitting: false
    function requestQuit() {
        // A running job is neither an unsaved movie nor a hand trim, and it
        // used to quit with no ask. Ask first, and let that win over Save/Export.
        if (backend.busy || unexported || looseCut) {
            if (movie.player.playbackState === MediaPlayer.PlayingState)
                movie.player.pause();
            quitConfirmVisible = true;
            return;
        }
        forceQuit();
    }
    // Closing the window is what reliably ends the app (quitOnLastWindowClosed);
    // Qt.quit() alone has proven ignorable in a live session, so it's only the
    // backstop. The quitting flag stops onClosing from re-asking on the way out.
    function forceQuit() {
        quitting = true;
        movie.player.stop();
        releaseAudioOutput();
        win.close();
        Qt.quit();
    }

    Component.onCompleted: {
        rememberDefaultOutput();
        ensureAudioOutput();
        lastSelectCount = selectCount;
        if (selectCount > 0 && currentLine < 0)
            currentLine = 0;
        if (backend.tray.length > 0 && backend.trayIndex < 0)
            backend.trayIndex = 0;
    }
    onHasVideoChanged: syncPlaybackAudio()
    onPreviewingChanged: syncPlaybackAudio()
    onClosing: (close) => {
        if (win.quitting)
            return;
        if (backend.busy || win.unexported || win.looseCut) {
            close.accepted = false;
            if (movie.player.playbackState === MediaPlayer.PlayingState)
                movie.player.pause();
            win.quitConfirmVisible = true;
            return;
        }
        forceQuit();
    }

    // The playback and editing shortcuts go quiet while the quit confirmation is
    // up — a disabled Shortcut also stops swallowing its key, which lets the
    // dialog's own keyboard navigation receive the arrows, Space and Enter.
    Shortcut {
        sequence: "Space"
        context: Qt.ApplicationShortcut
        enabled: !win.dialogUp && (win.hasVideo || win.previewing) && !win.controlFocused
                 && !planPane.paceKeys
        onActivated: togglePlay()
    }

    Shortcut {
        sequence: "Left"
        context: Qt.ApplicationShortcut
        enabled: win.editing
        onActivated: seekTo(editBar.playheadSec - 1)
    }

    Shortcut {
        sequence: "Right"
        context: Qt.ApplicationShortcut
        enabled: win.editing
        onActivated: seekTo(editBar.playheadSec + 1)
    }

    Shortcut {
        sequence: "Shift+Left"
        context: Qt.ApplicationShortcut
        enabled: win.editing
        onActivated: seekTo(editBar.playheadSec - 5)
    }

    Shortcut {
        sequence: "Shift+Right"
        context: Qt.ApplicationShortcut
        enabled: win.editing
        onActivated: seekTo(editBar.playheadSec + 5)
    }

    Shortcut {
        sequence: "Alt+Left"
        context: Qt.ApplicationShortcut
        enabled: win.editing
        onActivated: seekTo(editBar.playheadSec - 0.2)
    }

    Shortcut {
        sequence: "Alt+Right"
        context: Qt.ApplicationShortcut
        enabled: win.editing
        onActivated: seekTo(editBar.playheadSec + 0.2)
    }

    Shortcut {
        sequence: "["
        context: Qt.ApplicationShortcut
        enabled: win.editing
        onActivated: {
            movie.player.pause();
            seekTo(timeline.edgeFrom(editBar.playheadSec, -1));
        }
    }

    Shortcut {
        sequence: "]"
        context: Qt.ApplicationShortcut
        enabled: win.editing
        onActivated: {
            movie.player.pause();
            seekTo(timeline.edgeFrom(editBar.playheadSec, 1));
        }
    }

    Shortcut {
        sequence: "S"
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.editing
        onActivated: timeline.split(editBar.playheadSec)
    }

    Shortcut {
        sequences: ["X", "Delete", "Backspace"]
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.editing
        onActivated: timeline.removeOrRestoreAt(editBar.playheadSec)
    }

    Shortcut {
        sequence: "Ctrl+Space"
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.editing
        onActivated: timeline.trimTo(editBar.playheadSec, true)
    }

    Shortcut {
        sequence: "Alt+Space"
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.editing
        onActivated: timeline.trimTo(editBar.playheadSec, false)
    }

    Shortcut {
        sequence: "Z"
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.editing
        onActivated: editBar.toggleZoom()
    }

    Shortcut {
        sequence: "Ctrl+Z"
        context: Qt.ApplicationShortcut
        enabled: win.editing && timeline.canUndo
        onActivated: timeline.undo()
    }

    Shortcut {
        sequences: ["Ctrl+Shift+Z", "Ctrl+Y"]
        context: Qt.ApplicationShortcut
        enabled: win.editing && timeline.canRedo
        onActivated: timeline.redo()
    }

    Shortcut {
        sequence: "Ctrl+S"
        context: Qt.ApplicationShortcut
        enabled: win.hasVideo && backend.duration > 0 && !backend.busy
        onActivated: {
            win.quitConfirmVisible = false;
            exportVideo();
        }
    }

    Shortcut {
        sequence: "Ctrl+O"
        context: Qt.ApplicationShortcut
        enabled: !win.quitConfirmVisible && !backend.busy
        onActivated: openVideo()
    }

    Shortcut {
        sequence: "Q"
        context: Qt.ApplicationShortcut
        onActivated: {
            if (!win.quitConfirmVisible)
                requestQuit();
        }
    }

    Shortcut {
        sequence: "?"
        context: Qt.ApplicationShortcut
        onActivated: {
            if (!win.quitConfirmVisible)
                win.helpVisible = !win.helpVisible;
        }
    }

    Shortcut {
        sequence: "Escape"
        context: Qt.ApplicationShortcut
        onActivated: {
            if (planPane.paceOpen) {
                planPane.closePace();
                return;
            }
            if (win.settingsOpen)
                closeSettings();
            else if (win.titleCardOpen)
                win.titleCardOpen = false;
            else if (win.confirmCutOpen)
                win.confirmCutOpen = false;
            else if (win.quitConfirmVisible)
                win.quitConfirmVisible = false;
            else if (win.helpVisible)
                win.helpVisible = false;
        }
    }

    Shortcut {
        sequence: "Up"
        context: Qt.ApplicationShortcut
        enabled: win.lineKeys
        onActivated: moveLine(-1)
    }
    Shortcut {
        sequence: "Down"
        context: Qt.ApplicationShortcut
        enabled: win.lineKeys
        onActivated: moveLine(1)
    }
    Shortcut {
        sequences: ["Return", "Enter"]
        context: Qt.ApplicationShortcut
        enabled: win.lineKeys
        onActivated: playCurrentLine()
    }
    Shortcut {
        sequences: ["X", "Backspace"]
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.lineKeys
        onActivated: toggleCurrentLine()
    }
    Shortcut {
        sequence: "K"
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.lineKeys
        onActivated: keepCurrentLine()
    }
    Shortcut {
        sequence: "D"
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.lineKeys
        onActivated: dropCurrentLine()
    }
    Shortcut {
        sequence: "Alt+Up"
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.shotKeys && !planPane.paceOpen
        onActivated: nudgeShot(-1)
    }
    Shortcut {
        sequence: "Alt+Down"
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.shotKeys && !planPane.paceOpen
        onActivated: nudgeShot(1)
    }
    Shortcut {
        sequence: "Delete"
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: win.shotKeys
        onActivated: removeCurrentShot()
    }
    Shortcut {
        sequences: ["Ctrl+Return", "Ctrl+Enter", "Ctrl+R"]
        context: Qt.ApplicationShortcut
        enabled: !win.dialogUp && !backend.busy && backend.job === "" && !win.controlFocused
        onActivated: actionBar.activateFilled()
    }


    // One side of the Cut | Original pair. The chosen side is filled.
    component ModeWord: Rectangle {
        id: modeWord
        property string word
        property bool active: false
        signal picked()
        implicitWidth: modeLabel.implicitWidth + 16
        implicitHeight: 24
        radius: Math.max(0, theme.radius - 2)
        color: active ? theme.raised : (modeHit.containsMouse && !backend.busy ? theme.hover : "transparent")
        Label {
            id: modeLabel
            anchors.centerIn: parent
            text: modeWord.word
            color: theme.foreground
            opacity: backend.busy ? 0.38 : (modeWord.active ? 1 : 0.62)
            font.pixelSize: 13
        }
        MouseArea {
            id: modeHit
            anchors.fill: parent
            hoverEnabled: !backend.busy
            cursorShape: backend.busy || modeWord.active ? Qt.ArrowCursor : Qt.PointingHandCursor
            onClicked: {
                if (!backend.busy && !modeWord.active)
                    modeWord.picked()
            }
        }
    }

    // Cut or Original, two words on one chip in the transport bar. Not an icon.
    // Cut is the resting choice. Original plays the file straight through.
    component PreviewModeWord: Rectangle {
        objectName: "cutRawChip"
        implicitWidth: modeRow.width + 4
        implicitHeight: 28
        radius: theme.radius
        color: theme.surface
        border.width: 1
        border.color: theme.line
        Row {
            id: modeRow
            x: 2
            y: 2
            spacing: 2
            ModeWord {
                word: qsTr("Cut")
                active: win.cutPreview
                onPicked: win.cutPreview = true
            }
            ModeWord {
                word: qsTr("Original")
                active: !win.cutPreview
                onPicked: win.cutPreview = false
            }
        }
    }

    // A word on a chip in the transport bar: Previous, Next.
    component WordChip: Rectangle {
        id: wordChip
        property string word
        signal clicked()
        Layout.alignment: Qt.AlignVCenter
        implicitWidth: chipWord.implicitWidth + 16
        implicitHeight: 28
        radius: theme.radius
        color: chipHit.containsMouse && wordChip.enabled ? theme.hover : theme.raised
        Label {
            id: chipWord
            anchors.centerIn: parent
            text: wordChip.word
            color: theme.foreground
            opacity: wordChip.enabled ? 1 : 0.38
            font.pixelSize: 13
        }
        MouseArea {
            id: chipHit
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: wordChip.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: wordChip.clicked()
        }
    }

    MoviePlayer {
        id: movie
        host: win
        film: editBar
        videoItem: videoOut
    }

    Timer {
        id: noticeTimer
        interval: 5000
        repeat: false
        onTriggered: win.noticeText = ""
    }

    Item {
        anchors.fill: parent

        DropArea {
            id: dropTarget
            anchors.fill: parent
            enabled: win.gathering && !win.dialogUp && !backend.busy
            onDropped: (drop) => {
                backend.addDropped(drop.urls);
                drop.accept(Qt.CopyAction);
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // The top bar: BotCut, the file, the step, and the one next action.
            ActionBar {
                id: actionBar
                Layout.fillWidth: true
                Layout.preferredHeight: actionBar.implicitHeight
                host: win
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                // The lines column. About 400 px with three columns, narrower below that.
                PlanPane {
                    id: planPane
                    Layout.preferredWidth: win.wideInspector ? 400 : 340
                    Layout.minimumWidth: Layout.preferredWidth
                    Layout.maximumWidth: Layout.preferredWidth
                    Layout.fillHeight: true
                    host: win
                    film: editBar
                    decisions: inspector
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    color: theme.line
                }

                // The stage and the decisions: side by side from 1280 px, and
                // the decisions under the picture below that.
                GridLayout {
                    id: workspace
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    columns: win.wideInspector ? 2 : 1
                    columnSpacing: 0
                    rowSpacing: 0

                    // The stage: the picture, then one transport bar, then the
                    // block row that jumps or the filmstrip that trims, each at
                    // the picture well's width.
                    ColumnLayout {
                        id: stage
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 0

                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.leftMargin: 12
                            Layout.rightMargin: 12
                            Layout.topMargin: 12
                            Layout.bottomMargin: transport.visible ? 8 : 12

                            Rectangle {
                                anchors.fill: parent
                                radius: theme.radius
                                color: "black"
                                clip: true

                                VideoOutput {
                                    id: videoOut
                                    anchors.fill: parent
                                }
                                Connections {
                                    target: videoOut.videoSink
                                    function onVideoFrameChanged(frame) {
                                        movie.player.finishPriming();
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    z: 1
                                    enabled: win.hasVideo || win.previewing
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: togglePlay()
                                }
                                Column {
                                    visible: win.gathering && backend.tray.length === 0
                                    z: 2
                                    anchors.centerIn: parent
                                    width: Math.min(440, parent.width - 48)
                                    spacing: 8
                                    Label {
                                        width: parent.width
                                        horizontalAlignment: Text.AlignHCenter
                                        wrapMode: Text.WordWrap
                                        text: qsTr("Drop the shots for this movie here.")
                                        color: theme.foreground
                                        font.pixelSize: 16
                                    }
                                    Label {
                                        width: parent.width
                                        horizontalAlignment: Text.AlignHCenter
                                        wrapMode: Text.WordWrap
                                        text: qsTr("MP4, MOV, or MKV, straight from your phone or camera.")
                                        color: theme.foreground
                                        opacity: 0.62
                                        font.pixelSize: 13
                                    }
                                    ActionButton {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: qsTr("Trim one file instead…")
                                        enabled: !backend.busy
                                        onClicked: openVideo()
                                    }
                                }
                                // The current line's words, over the picture. In
                                // the window only. The export never carries them.
                                Rectangle {
                                    visible: win.viewStep === "lines" && captionLabel.text !== ""
                                    z: 2
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 16
                                    width: Math.min(captionLabel.implicitWidth + 24, Math.round(parent.width * 0.8))
                                    height: captionLabel.implicitHeight + 12
                                    radius: theme.radius
                                    color: Qt.rgba(0, 0, 0, 0.75)
                                    Label {
                                        id: captionLabel
                                        anchors.fill: parent
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 12
                                        anchors.topMargin: 6
                                        anchors.bottomMargin: 6
                                        text: win.currentLineText
                                        color: "white"
                                        font.pixelSize: 14
                                        horizontalAlignment: Text.AlignHCenter
                                        wrapMode: Text.WordWrap
                                    }
                                }
                            }
                        }

                        // The transport: Previous, play, Next, the clock, and Cut
                        // or Original, in one bar under the picture. In the window
                        // only. Export never sees it.
                        RowLayout {
                            id: transport
                            // The rules live here. Item.visible is effective, so reading a
                            // child's visible back would latch the bar hidden.
                            readonly property bool playShown: win.hasVideo ? !win.gathering : win.previewing
                            readonly property bool stepShown: win.viewStep === "lines" && backend.selects.length > 0
                            readonly property bool modeShown: stepShown
                                                              || (win.hasVideo && !win.gathering && backend.planCut)
                            readonly property bool clockShown: win.hasVideo && !win.gathering
                            visible: playShown || modeShown || clockShown
                            Layout.fillWidth: true
                            Layout.leftMargin: 12
                            Layout.rightMargin: 12
                            Layout.bottomMargin: blockRow.visible || editBar.visible ? 8 : 12
                            Layout.preferredHeight: 36
                            Layout.minimumHeight: 36
                            spacing: 8

                            // Previous and Next move the current line. They never start playback.
                            WordChip {
                                visible: transport.stepShown
                                word: qsTr("Previous")
                                enabled: win.currentLine > 0
                                onClicked: moveLine(-1)
                            }
                            PlayButton {
                                id: playButton
                                // The shot preview while gathering, or the open movie.
                                visible: transport.playShown
                                enabled: win.gathering || backend.duration > 0
                                Layout.alignment: Qt.AlignVCenter
                                playing: movie.player.playbackState === MediaPlayer.PlayingState
                                         && !movie.player.priming
                                onClicked: togglePlay()
                            }
                            WordChip {
                                visible: transport.stepShown
                                word: qsTr("Next")
                                enabled: win.currentLine >= 0 && win.currentLine < backend.selects.length - 1
                                onClicked: moveLine(1)
                            }
                            Rectangle {
                                id: movieClockChip
                                visible: transport.clockShown
                                Layout.alignment: Qt.AlignVCenter
                                implicitWidth: movieClock.implicitWidth + 16
                                implicitHeight: 28
                                radius: theme.radius
                                color: theme.raised
                                Label {
                                    id: movieClock
                                    anchors.centerIn: parent
                                    text: lineClock(editBar.playheadSec) + " / " + lineClock(win.timeline.keptDuration)
                                    color: theme.foreground
                                    font.pixelSize: 13
                                    font.family: "monospace"
                                }
                            }
                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 1
                            }
                            PreviewModeWord {
                                id: modeChip
                                // Lines, and the movie while the plan is the movie.
                                // Not Shots, and not a plain file with no line list.
                                visible: transport.modeShown
                                Layout.alignment: Qt.AlignVCenter
                            }
                        }

                        // One block per line that has a start and an end, in order,
                        // each as wide as its share of the spoken time. Kept is the
                        // accent, dropped the washed accent the filmstrip uses for a
                        // dropped gap, unsure a thin accent mark above the block.
                        // A click shows that line. Nothing here trims.
                        Rectangle {
                            id: blockRow
                            visible: win.viewStep === "lines" && blocks.length > 0
                            Layout.fillWidth: true
                            Layout.leftMargin: 12
                            Layout.rightMargin: 12
                            Layout.bottomMargin: editBar.visible ? 8 : 12
                            Layout.preferredHeight: 56
                            Layout.minimumHeight: 56
                            radius: theme.radius
                            color: theme.surface
                            border.width: 1
                            border.color: theme.line

                            readonly property var blocks: {
                                var out = [];
                                var at = 0;
                                var lines = backend.selects;
                                for (var i = 0; i < lines.length; i++) {
                                    var line = lines[i];
                                    if (!line)
                                        continue;
                                    var start = Number(line.start);
                                    var end = Number(line.end);
                                    if (!isFinite(start) || !isFinite(end))
                                        continue;
                                    var len = Math.max(0, end - start);
                                    out.push({ index: i, at: at, len: len,
                                               kept: line.keep !== false,
                                               unsure: line.reason === "unique?" });
                                    at += len;
                                }
                                return out;
                            }
                            readonly property real total: blocks.length > 0
                                    ? blocks[blocks.length - 1].at + blocks[blocks.length - 1].len : 0

                            Row {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.leftMargin: 10
                                anchors.topMargin: 8
                                spacing: 12
                                Row {
                                    spacing: 5
                                    Rectangle {
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 10
                                        height: 6
                                        radius: 1
                                        color: theme.accent
                                    }
                                    Label {
                                        text: qsTr("Kept")
                                        color: theme.foreground
                                        opacity: 0.62
                                        font.pixelSize: 11
                                    }
                                }
                                Row {
                                    spacing: 5
                                    Rectangle {
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 10
                                        height: 6
                                        radius: 1
                                        color: theme.accent
                                        opacity: 0.24
                                    }
                                    Label {
                                        text: qsTr("Dropped")
                                        color: theme.foreground
                                        opacity: 0.62
                                        font.pixelSize: 11
                                    }
                                }
                                Row {
                                    spacing: 5
                                    Rectangle {
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 2
                                        height: 8
                                        color: theme.accent
                                    }
                                    Label {
                                        text: qsTr("Unsure")
                                        color: theme.foreground
                                        opacity: 0.62
                                        font.pixelSize: 11
                                    }
                                }
                            }
                            Label {
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.rightMargin: 10
                                anchors.topMargin: 8
                                width: Math.max(0, parent.width / 2 - 20)
                                horizontalAlignment: Text.AlignRight
                                text: qsTr("Click a block to show that line")
                                color: theme.foreground
                                opacity: 0.38
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                            Item {
                                id: blockTrack
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                anchors.bottomMargin: 8
                                height: 22
                                Repeater {
                                    model: blockRow.blocks
                                    delegate: Item {
                                        id: block
                                        required property var modelData
                                        readonly property real fromX: blockRow.total > 0
                                                ? Math.round(modelData.at / blockRow.total * blockTrack.width) : 0
                                        readonly property real toX: blockRow.total > 0
                                                ? Math.round((modelData.at + modelData.len) / blockRow.total * blockTrack.width) : 0
                                        x: fromX
                                        width: Math.max(2, toX - fromX - 1)
                                        height: blockTrack.height
                                        Rectangle {
                                            anchors.fill: parent
                                            anchors.topMargin: 6
                                            radius: 2
                                            color: theme.accent
                                            opacity: block.modelData.kept ? 1
                                                     : (blockHit.containsMouse && !backend.busy ? 0.38 : 0.24)
                                        }
                                        Rectangle {
                                            visible: block.modelData.unsure
                                            x: 0
                                            y: 0
                                            width: 2
                                            height: 4
                                            color: theme.accent
                                        }
                                        Rectangle {
                                            visible: block.modelData.index === win.currentLine
                                            anchors.fill: parent
                                            anchors.topMargin: 4
                                            anchors.leftMargin: -2
                                            anchors.rightMargin: -2
                                            anchors.bottomMargin: -2
                                            radius: 3
                                            color: "transparent"
                                            border.width: 1
                                            border.color: theme.foreground
                                        }
                                        MouseArea {
                                            id: blockHit
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                win.currentLine = block.modelData.index;
                                                win.showLine(backend.selects[block.modelData.index]);
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        EditBar {
                            id: editBar
                            objectName: "editBar"
                            visible: win.hasVideo && !win.gathering
                            Layout.fillWidth: true
                            Layout.preferredHeight: implicitHeight
                            Layout.leftMargin: 12
                            Layout.rightMargin: 12
                            Layout.bottomMargin: editBar.zoomed ? 4 : 12
                            onScrub: (seconds, segment, source) => {
                                movie.player.pause();
                                if (backend.planCut && segment >= 0) {
                                    planPlaying = false;
                                    armPlanIndex(segment, source, false);
                                    return;
                                }
                                seekTo(seconds);
                            }
                        }

                        Label {
                            visible: editBar.visible && editBar.zoomed
                            Layout.fillWidth: true
                            Layout.leftMargin: 12
                            Layout.rightMargin: 12
                            Layout.bottomMargin: 12
                            text: qsTr("Zoomed to one shot. Z zooms out.")
                            color: theme.foreground
                            opacity: 0.62
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                    }

                    // The decisions. A 280 px column on the right from 1280 px;
                    // three short columns under the picture below that. Hidden
                    // when nothing applies, as on the empty home.
                    Inspector {
                        id: inspector
                        host: win
                        wide: win.wideInspector
                        visible: hasContent
                        Layout.fillWidth: !win.wideInspector
                        Layout.fillHeight: win.wideInspector
                        Layout.preferredWidth: win.wideInspector ? 280 : 100
                        Layout.minimumWidth: win.wideInspector ? 280 : 0
                        Layout.maximumWidth: win.wideInspector ? 280 : 100000
                        Layout.preferredHeight: implicitHeight
                        Layout.minimumHeight: win.wideInspector ? 0 : implicitHeight
                        Layout.leftMargin: win.wideInspector ? 0 : 12
                        Layout.rightMargin: win.wideInspector ? 0 : 12
                        Layout.bottomMargin: win.wideInspector ? 0 : 12
                    }
                }
            }

            // The status bar: the sentence, this step's quiet tools, and the keys.
            Rectangle {
                id: statusBar
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(40, statusSentence.implicitHeight + 12)
                Layout.minimumHeight: Layout.preferredHeight
                color: theme.surface

                Rectangle {
                    anchors.top: parent.top
                    width: parent.width
                    height: 1
                    color: theme.line
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    spacing: 8

                    Label {
                        id: statusSentence
                        Layout.fillWidth: true
                        Layout.minimumWidth: 240
                        Layout.alignment: Qt.AlignVCenter
                        text: win.actionSentence
                        color: win.actionNeedsYou || win.noticeText !== "" ? theme.accent : theme.foreground
                        opacity: win.noticeText !== "" || win.actionNeedsYou ? 1 : 0.62
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        verticalAlignment: Text.AlignVCenter
                    }

                    // This step's quiet tools. Show the file comes first after a save.
                    RowLayout {
                        id: quietTools
                        spacing: 4
                        Layout.alignment: Qt.AlignVCenter

                        ActionButton {
                            text: qsTr("Open a saved list\u2026")
                            visible: !actionBar.running && win.displayStep === "empty"
                            enabled: !backend.busy
                            implicitHeight: 28
                            topPadding: 4
                            bottomPadding: 4
                            Layout.minimumWidth: implicitWidth
                            Layout.maximumWidth: implicitWidth
                            onClicked: backend.openCutListDialog()
                        }
                        ActionButton {
                            text: qsTr("Keep every shot instead")
                            visible: !actionBar.running && win.displayStep === "needsKey"
                            enabled: !backend.busy
                            implicitHeight: 28
                            topPadding: 4
                            bottomPadding: 4
                            Layout.minimumWidth: implicitWidth
                            Layout.maximumWidth: implicitWidth
                            onClicked: backend.cutMode = "assemble"
                        }
                        ActionButton {
                            objectName: "showFileButton"
                            text: qsTr("Show the file")
                            filled: false
                            visible: !actionBar.running && win.displayStep === "movieSaved" && backend.roughCut
                            enabled: !backend.busy
                            implicitHeight: 28
                            topPadding: 4
                            bottomPadding: 4
                            Layout.minimumWidth: implicitWidth
                            Layout.maximumWidth: implicitWidth
                            onClicked: backend.showFile()
                        }
                        ActionButton {
                            objectName: "captionsButton"
                            text: qsTr("Captions")
                            visible: !actionBar.running && win.displayStep === "movieSaved" && backend.roughCut
                            enabled: !backend.busy && !(backend.planCut && backend.plan.unexported)
                            implicitHeight: 28
                            topPadding: 4
                            bottomPadding: 4
                            Layout.minimumWidth: implicitWidth
                            Layout.maximumWidth: implicitWidth
                            onClicked: backend.writeCaptions()
                        }
                        ActionButton {
                            objectName: "shortButton"
                            text: qsTr("Vertical short")
                            visible: !actionBar.running && win.displayStep === "movieSaved" && backend.roughCut
                            enabled: !backend.busy && !(backend.planCut && backend.plan.unexported)
                            implicitHeight: 28
                            topPadding: 4
                            bottomPadding: 4
                            Layout.minimumWidth: implicitWidth
                            Layout.maximumWidth: implicitWidth
                            onClicked: backend.makeShort()
                        }
                        ActionButton {
                            text: qsTr("Export another size\u2026")
                            visible: !actionBar.running && win.displayStep === "movieSaved" && backend.roughCut
                                     && !win.looseCut && !win.unexported
                            enabled: !backend.busy && (backend.planCut ? backend.plan.duration : backend.duration) > 0
                            implicitHeight: 28
                            topPadding: 4
                            bottomPadding: 4
                            Layout.minimumWidth: implicitWidth
                            Layout.maximumWidth: implicitWidth
                            onClicked: exportVideo()
                        }
                    }

                    // The keys this screen answers to. Only when the row has room.
                    Row {
                        id: keyHintRow
                        visible: win.keyHints.length > 0
                                 && statusBar.width - 288 - quietTools.implicitWidth >= 320
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 12
                        Repeater {
                            model: win.keyHints
                            delegate: Row {
                                required property var modelData
                                spacing: 4
                                Label {
                                    text: modelData[0]
                                    color: theme.foreground
                                    opacity: 0.62
                                    font.pixelSize: 11
                                    font.family: "monospace"
                                }
                                Label {
                                    text: modelData[1]
                                    color: theme.foreground
                                    opacity: 0.38
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                }
            }
        }

        SettingsDialog {
            id: settingsDialog
            host: win
        }
        HelpDialog { host: win }
        TitleCardDialog { host: win }
        ConfirmDialog { host: win }
        QuitDialog { host: win }
    }

    Connections {
        target: backend
        function onInfoChanged() {
            win.clearCutChain();
            win.noticeText = "";
            noticeTimer.stop();
            movie.primeFallback.stop();
            movie.player.priming = false;
            movie.player.primed = false;
            editBar.zoomed = false;
            editBar.playheadSec = 0;
            if (backend.planCut)
                win.armPlan(0, false);
            else {
                win.planPlaying = false;
                win.planArmed = false;
                win.planIndex = -1;
                win.planSource = "";
                win.linePlayStart = -1;
                win.linePlayEnd = -1;
                win.linePreview = false;
                win.lineHold = false;
            }
        }
        function onGatheringChanged() {
            if (backend.gathering || !backend.planCut || !win.hasVideo)
                return;
            // Back on Watch. The filmstrip time is the picture, not the head of the file.
            win.armPlan(editBar.playheadSec, false);
        }
        function onExportDone(path) {
            win.showNotice("Saved " + path);
        }
        function onExportFailed(message) {
            win.showNotice("Export failed: " + message);
        }
        function onLoadError(message) {
            win.showNotice("Cannot open video: " + message);
        }
    }

    Connections {
        target: backend.planCut ? backend.plan : null
        function onCommitted() {
            if (!backend.planCut || editBar.interacting || win.gathering)
                return;
            var t = editBar.playheadSec;
            if (backend.plan.duration > 0)
                t = Math.max(0, Math.min(t, backend.plan.duration));
            editBar.playheadSec = t;
            win.armPlan(t, false);
        }
    }
}
