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
    readonly property bool linesOpen: gathering && backend.selects.length > 0
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
    property bool sidebarCollapsed: false
    property int currentLine: -1
    property int linePlayStart: -1
    property int linePlayEnd: -1
    // Shot preview only. Plan playback reuses the markers below and must not pause a shot.
    property bool linePreview: false
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
                                   && !quitConfirmVisible && !editBar.interacting
                                   && !backend.busy

    Material.theme: Material.Dark
    Material.accent: win.accent
    Material.roundedScale: theme.radius
    color: "#0e0e10"

    function fileName(url) {
        var s = url.toString();
        return s === "" ? "" : decodeURIComponent(s.substring(s.lastIndexOf('/') + 1));
    }
    function baseName(path) {
        var s = path.toString();
        var i = s.lastIndexOf("/");
        return i < 0 ? s : s.substring(i + 1);
    }
    function lineReason(reason) {
        if (reason === "unique?")
            return "Not sure";
        if (reason === "restored")
            return "Put back";
        if (reason === "dropped")
            return "Dropped";
        return reason;
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
            if (backend.selects[i].keep)
                n++;
        }
        return n;
    }
    function keptSpan() {
        var total = 0;
        for (var i = 0; i < backend.selects.length; i++) {
            var line = backend.selects[i];
            if (!line.keep)
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
    function shotsStatus() {
        if (statusText !== "")
            return statusText;
        var missing = missingShotCount();
        if (missing > 0) {
            return missing + (missing === 1
                ? " shot can't be found — remove it to continue"
                : " shots can't be found — remove it to continue");
        }
        if (backend.selects.length > 0) {
            var n = keptLineCount();
            return n + (n === 1 ? " line kept" : " lines kept");
        }
        if (backend.tray.length === 0)
            return "No shots yet";
        return backend.tray.length + (backend.tray.length === 1 ? " shot" : " shots");
    }
    function firstMissingShot() {
        for (var i = 0; i < backend.tray.length; i++) {
            if (!backend.trayFileExists(backend.tray[i]))
                return baseName(backend.tray[i]);
        }
        return "";
    }
    // The stub used by layout tests leaves step empty, and the old sentence stays.
    function actionSentence() {
        if (backend.job !== "")
            return backend.jobText !== "" ? backend.jobText : backend.status;
        var step = backend.step;
        if (!step)
            return shotsStatus();
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
            return qsTr("%1 of %2 lines kept. Render makes the movie.")
                    .arg(keptLineCount()).arg(backend.selects.length);
        }
        if (step === "allDropped")
            return qsTr("Every line is dropped. Keep one to render.");
        if (step === "movieUnsaved")
            return qsTr("Your movie is ready. It's only in a temporary folder until you save it.");
        if (step === "trimmed")
            return qsTr("Trimmed by hand. Export writes a new file. Captions and the short wait until then.");
        if (step === "movieSaved")
            return qsTr("Saved.");
        if (step === "empty")
            return qsTr("Add the shots for one movie. You can put them in order after.");
        if (step === "working")
            return backend.jobText !== "" ? backend.jobText : backend.status;
        return shotsStatus();
    }
    function actionNeedsYou() {
        return backend.step === "needsKey" || backend.step === "missingShot"
                || backend.step === "allDropped";
    }
    function statusPercent() {
        var match = /(?:Rendering|Opening) (\d+)%/.exec(backend.status);
        if (!match)
            return -1;
        var n = parseInt(match[1], 10);
        return n >= 0 && n <= 100 ? n : -1;
    }
    function submitRevise() {
        var note = reviseInput.text.replace(/\s+/g, " ").trim()
        if (note === "")
            return
        if (backend.sendRevise(note))
            reviseInput.text = ""
    }
    function makeOpenCard() {
        var sentence = openCardInput.text.replace(/\s+/g, " ").trim()
        if (sentence === "")
            return
        backend.makeCard("open", sentence)
    }
    function makeCloseCard() {
        var sentence = closeCardInput.text.replace(/\s+/g, " ").trim()
        if (sentence === "")
            return
        backend.makeCard("close", sentence)
    }
    function playLine(line) {
        if (!gathering)
            return;
        var clip = line.clip;
        if (clip < 0 || clip >= backend.tray.length)
            return;
        linePlayStart = Math.max(0, Math.round(line.start * 1000));
        linePlayEnd = Math.max(linePlayStart, Math.round(line.end * 1000));
        linePreview = true;
        if (backend.trayIndex !== clip)
            backend.trayIndex = clip;
        ensureAudioOutput();
        movie.player.armLine();
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
        planPlaying = play;
        planArmed = false;
        linePreview = false;
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
    function togglePlay() {
        if (win.gathering) {
            if (!win.previewing)
                return;
            ensureAudioOutput();
            if (movie.player.priming)
                movie.player.finishPriming();
            if (movie.player.playbackState === MediaPlayer.PlayingState)
                movie.player.pause();
            else
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
                return;
            }
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
        enabled: !win.quitConfirmVisible && !win.settingsOpen && (win.hasVideo || win.previewing)
                 && !win.controlFocused
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
            if (win.settingsOpen)
                closeSettings();
            else if (win.quitConfirmVisible)
                win.quitConfirmVisible = false;
            else if (win.helpVisible)
                win.helpVisible = false;
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

    component DialogButton: Rectangle {
        id: dialogButton
        width: dialogButtonLabel.implicitWidth + 28
        height: 34
        radius: 8

        property string text: ""
        property bool primary: false
        signal clicked()

        color: primary ? win.accent : "#2c2c2f"
        border.color: activeFocus ? (primary ? win.accentForeground : win.accent) : "transparent"
        border.width: activeFocus ? 2 : 0

        Keys.onReturnPressed: clicked()
        Keys.onEnterPressed: clicked()
        Keys.onSpacePressed: clicked()

        Label {
            id: dialogButtonLabel
            anchors.centerIn: parent
            text: dialogButton.text
            color: dialogButton.primary ? win.accentForeground : "white"
            font.pixelSize: 13
            font.weight: Font.DemiBold
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: dialogButton.clicked()
        }
    }

    component IconButton: Rectangle {
        id: iconButton
        implicitWidth: 44
        implicitHeight: 44
        radius: 22

        property string iconName: "play"
        property color iconColor: "white"
        property color buttonColor: "#2c2c2f"
        property string tipText: ""
        signal clicked()

        color: buttonColor
        opacity: enabled ? 1 : 0.45

        HoverHandler { id: iconHover }
        ToolTip.visible: iconHover.hovered && tipText !== ""
        ToolTip.text: tipText

        Canvas {
            id: iconCanvas
            anchors.centerIn: parent
            width: 24
            height: 24

            onPaint: {
                var ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                ctx.fillStyle = iconButton.iconColor;
                ctx.strokeStyle = iconButton.iconColor;
                ctx.lineWidth = 2.4;
                ctx.lineCap = "round";
                ctx.lineJoin = "round";

                if (iconButton.iconName === "pause") {
                    ctx.fillRect(7, 5, 4, 14);
                    ctx.fillRect(14, 5, 4, 14);
                } else if (iconButton.iconName === "play") {
                    ctx.beginPath();
                    ctx.moveTo(8, 5);
                    ctx.lineTo(8, 19);
                    ctx.lineTo(19, 12);
                    ctx.closePath();
                    ctx.fill();
                } else if (iconButton.iconName === "download") {
                    ctx.beginPath();
                    ctx.moveTo(12, 4);
                    ctx.lineTo(12, 14);
                    ctx.stroke();

                    ctx.beginPath();
                    ctx.moveTo(7, 10);
                    ctx.lineTo(12, 15);
                    ctx.lineTo(17, 10);
                    ctx.stroke();

                    ctx.beginPath();
                    ctx.moveTo(6, 20);
                    ctx.lineTo(18, 20);
                    ctx.stroke();
                }
            }

            Connections {
                target: iconButton
                function onIconNameChanged() { iconCanvas.requestPaint(); }
                function onIconColorChanged() { iconCanvas.requestPaint(); }
            }
        }

        MouseArea {
            anchors.fill: parent
            enabled: iconButton.enabled
            cursorShape: Qt.PointingHandCursor
            onClicked: iconButton.clicked()
        }
    }

    component WordButton: Rectangle {
        id: wordButton
        implicitWidth: wordButtonLabel.implicitWidth + 28
        implicitHeight: 44
        radius: 8

        property string text: ""
        signal clicked()

        color: "#2c2c2f"
        opacity: enabled ? 1 : 0.45

        Label {
            id: wordButtonLabel
            anchors.centerIn: parent
            text: wordButton.text
            color: "white"
            font.pixelSize: 13
        }
        MouseArea {
            anchors.fill: parent
            enabled: wordButton.enabled
            cursorShape: Qt.PointingHandCursor
            onClicked: wordButton.clicked()
        }
    }

    component NavRow: Rectangle {
        id: navRow
        implicitWidth: 176
        implicitHeight: 36
        radius: 8

        property string text: ""
        property string mark: ""
        property bool active: false
        signal clicked()

        color: active ? "#2a2a2e" : (navHover.hovered && enabled ? "#1c1c1e" : "transparent")
        opacity: enabled ? 1 : 0.45

        HoverHandler {
            id: navHover
            enabled: navRow.enabled
        }
        Rectangle {
            width: 3
            height: 16
            radius: 1.5
            anchors.left: parent.left
            anchors.leftMargin: 4
            anchors.verticalCenter: parent.verticalCenter
            color: win.accent
            visible: navRow.active
        }
        Row {
            id: navLabels
            anchors.verticalCenter: parent.verticalCenter
            x: win.sidebarCollapsed ? (navRow.width - width) / 2 : 16
            spacing: 8
            Label {
                visible: !win.sidebarCollapsed
                text: navRow.text
                color: navRow.active ? "white" : "#d6d6da"
                font.pixelSize: 13
            }
            Label {
                visible: navRow.mark !== ""
                text: navRow.mark
                color: navRow.active ? "white" : "#b8b8bc"
                font.pixelSize: 13
            }
        }
        MouseArea {
            anchors.fill: parent
            enabled: navRow.enabled
            cursorShape: navRow.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: navRow.clicked()
        }
    }

    component RecentRow: Rectangle {
        id: recentRow
        implicitWidth: 176
        implicitHeight: 28
        radius: 6

        property string text: ""
        property string side: ""
        signal clicked()
        signal sideClicked()

        color: recentHover.hovered && enabled ? "#2a2a2e" : "transparent"
        opacity: enabled ? 1 : 0.45

        HoverHandler {
            id: recentHover
            enabled: recentRow.enabled
        }
        Label {
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.right: recentSide.visible ? recentSide.left : parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: recentRow.text
            color: "#b8b8bc"
            font.pixelSize: 12
            elide: Text.ElideRight
        }
        MouseArea {
            anchors.fill: parent
            enabled: recentRow.enabled
            cursorShape: recentRow.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: recentRow.clicked()
        }
        Label {
            id: recentSide
            visible: recentRow.side !== ""
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: recentRow.side
            color: "#7a7a80"
            font.pixelSize: 11
        }
        MouseArea {
            anchors.fill: recentSide
            anchors.margins: -6
            visible: recentSide.visible
            enabled: recentRow.enabled && recentSide.visible
            cursorShape: Qt.PointingHandCursor
            onClicked: recentRow.sideClicked()
        }
    }

    component QuietButton: Item {
        id: quiet
        implicitWidth: quietLabel.implicitWidth
        implicitHeight: 32

        property string text: ""
        property color textColor: "#d6d6da"
        signal clicked()

        opacity: enabled ? 1 : 0.45
        Label {
            id: quietLabel
            anchors.verticalCenter: parent.verticalCenter
            text: quiet.text
            color: quiet.textColor
            font.pixelSize: 13
        }
        MouseArea {
            anchors.fill: parent
            enabled: quiet.enabled
            cursorShape: quiet.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: quiet.clicked()
        }
    }

    component PillButton: Rectangle {
        id: pill
        implicitWidth: pillLabel.implicitWidth + 28
        implicitHeight: 36
        radius: 8

        property string text: ""
        property bool filled: false
        signal clicked()

        color: filled ? win.accent : "transparent"
        opacity: enabled ? 1 : 0.45

        Label {
            id: pillLabel
            anchors.centerIn: parent
            text: pill.text
            color: pill.filled ? win.accentForeground : "#d6d6da"
            font.pixelSize: 13
            font.weight: pill.filled ? Font.DemiBold : Font.Normal
        }
        MouseArea {
            anchors.fill: parent
            enabled: pill.enabled
            cursorShape: pill.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: pill.clicked()
        }
    }

    component DashedOutline: Canvas {
        id: outline
        anchors.fill: parent
        property int corner: 12
        onPaint: {
            var ctx = getContext("2d");
            ctx.clearRect(0, 0, width, height);
            ctx.strokeStyle = "#3a3a3e";
            ctx.lineWidth = 1;
            ctx.setLineDash([5, 4]);
            var r = corner;
            ctx.beginPath();
            ctx.moveTo(r, 0.5);
            ctx.lineTo(width - r, 0.5);
            ctx.arcTo(width - 0.5, 0.5, width - 0.5, r, r);
            ctx.lineTo(width - 0.5, height - r);
            ctx.arcTo(width - 0.5, height - 0.5, width - r, height - 0.5, r);
            ctx.lineTo(r, height - 0.5);
            ctx.arcTo(0.5, height - 0.5, 0.5, height - r, r);
            ctx.lineTo(0.5, r);
            ctx.arcTo(0.5, 0.5, r, 0.5, r);
            ctx.closePath();
            ctx.stroke();
        }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
    }

    Rectangle {
        id: sidebar
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: win.sidebarCollapsed ? 64 : 212
        color: "#1c1c1e"
        clip: true

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: win.sidebarCollapsed ? 8 : 12
            spacing: 4

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                Layout.bottomMargin: 4
                spacing: 8

                Rectangle {
                    Layout.preferredWidth: 20
                    Layout.preferredHeight: 20
                    Layout.alignment: Qt.AlignVCenter
                    radius: 4
                    color: win.accent
                }
                Label {
                    visible: !win.sidebarCollapsed
                    Layout.fillWidth: true
                    text: "BotCut"
                    color: "white"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                Label {
                    Layout.alignment: Qt.AlignVCenter
                    text: win.sidebarCollapsed ? "›" : "‹"
                    color: "#b8b8bc"
                    font.pixelSize: 16
                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -8
                        cursorShape: Qt.PointingHandCursor
                        onClicked: win.sidebarCollapsed = !win.sidebarCollapsed
                    }
                }
            }
            NavRow {
                Layout.fillWidth: true
                text: "Shots"
                active: win.gathering && !win.settingsOpen
                onClicked: {
                    win.settingsOpen = false;
                    win.settingsFromMovie = false;
                    win.helpVisible = false;
                    backend.showShots();
                }
            }
            NavRow {
                Layout.fillWidth: true
                text: "Watch"
                enabled: win.hasVideo
                active: win.hasVideo && !win.gathering && !win.settingsOpen
                onClicked: {
                    win.settingsOpen = false;
                    win.settingsFromMovie = false;
                    win.helpVisible = false;
                    backend.showMovie();
                }
            }
            Label {
                visible: !win.sidebarCollapsed && win.gathering && backend.tray.length === 0
                Layout.fillWidth: true
                Layout.topMargin: 8
                wrapMode: Text.WordWrap
                text: "Drop clips anywhere to start a new cut"
                color: "#7a7a80"
                font.pixelSize: 11
            }
            Flickable {
                id: recentScroll
                visible: !win.sidebarCollapsed
                         && (backend.recentLists.length > 0 || backend.recentCuts.length > 0)
                implicitHeight: 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 0
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentWidth: width
                contentHeight: recentCol.implicitHeight
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 4 }

                Column {
                    id: recentCol
                    width: recentScroll.width
                    Label {
                        visible: backend.recentLists.length > 0
                        width: parent.width
                        leftPadding: 16
                        topPadding: 8
                        bottomPadding: 2
                        text: "Lists"
                        color: "#7a7a80"
                        font.pixelSize: 11
                    }
                    Repeater {
                        model: backend.recentLists
                        RecentRow {
                            required property var modelData
                            width: recentCol.width
                            enabled: !backend.busy
                            text: modelData.name
                            onClicked: {
                                win.settingsOpen = false
                                win.settingsFromMovie = false
                                win.helpVisible = false
                                backend.reopenList(modelData.path)
                            }
                        }
                    }
                    Label {
                        visible: backend.recentCuts.length > 0
                        width: parent.width
                        leftPadding: 16
                        topPadding: 10
                        bottomPadding: 2
                        text: "Cuts"
                        color: "#7a7a80"
                        font.pixelSize: 11
                    }
                    Repeater {
                        model: backend.recentCuts
                        RecentRow {
                            required property var modelData
                            width: recentCol.width
                            enabled: !backend.busy
                            text: modelData.name
                            side: modelData.list ? "List" : ""
                            onClicked: {
                                win.settingsOpen = false
                                win.settingsFromMovie = false
                                win.helpVisible = false
                                backend.watchRecent(modelData.path)
                            }
                            onSideClicked: {
                                win.settingsOpen = false
                                win.settingsFromMovie = false
                                win.helpVisible = false
                                backend.reopenList(modelData.list)
                            }
                        }
                    }
                }
            }
            Item {
                Layout.fillHeight: true
                visible: !recentScroll.visible
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.topMargin: 4
                Layout.bottomMargin: 4
                color: "#2c2c2f"
            }
            NavRow {
                Layout.fillWidth: true
                text: "Help"
                mark: "?"
                active: win.helpVisible
                onClicked: win.helpVisible = !win.helpVisible
            }
            NavRow {
                objectName: "settingsButton"
                Layout.fillWidth: true
                text: "Settings"
                active: win.settingsOpen
                onClicked: {
                    if (win.settingsOpen)
                        closeSettings();
                    else
                        openSettings();
                }
            }
        }
    }

    Rectangle {
        anchors.left: sidebar.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 1
        color: "#2c2c2f"
    }

    Item {
        id: stage
        anchors.left: sidebar.right
        anchors.leftMargin: 1
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom

        DropArea {
            id: dropTarget
            anchors.fill: parent
            enabled: win.gathering && !win.settingsOpen && !backend.busy
            onDropped: (drop) => {
                backend.addDropped(drop.urls);
                drop.accept(Qt.CopyAction);
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            anchors.topMargin: 16
            anchors.bottomMargin: win.gathering ? 112 : 16
            spacing: 12
            visible: !win.settingsOpen

            Item {
                id: emptyWell
                visible: win.gathering && backend.tray.length === 0
                Layout.fillWidth: true
                Layout.fillHeight: true

                Column {
                    anchors.centerIn: parent
                    width: Math.min(560, emptyWell.width)
                    spacing: 16

                    Rectangle {
                        width: parent.width
                        height: Math.min(320, Math.max(220, emptyWell.height - 108))
                        radius: 12
                        color: "#161618"
                        DashedOutline { corner: 12 }

                        Column {
                            anchors.centerIn: parent
                            spacing: 14
                            Label {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "Drop your shots here"
                                color: "#f4f4f5"
                                font.pixelSize: 18
                                font.weight: Font.DemiBold
                            }
                            Label {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "MP4, MOV, or MKV · straight from your phone or camera"
                                color: "#b8b8bc"
                                font.pixelSize: 13
                            }
                            PillButton {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "Add videos"
                                filled: true
                                enabled: !backend.busy
                                onClicked: backend.addVideosDialog()
                            }
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: 10
                        Repeater {
                            model: ["Auto-finds your best lines", "Cuts silence and dead air", "Exports ready to post"]
                            delegate: Rectangle {
                                required property string modelData
                                width: (parent.width - 20) / 3
                                height: 72
                                radius: 8
                                color: "#1c1c1e"
                                Label {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    text: modelData
                                    wrapMode: Text.WordWrap
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    color: "#b8b8bc"
                                    font.pixelSize: 12
                                }
                            }
                        }
                    }
                }
            }

            RowLayout {
                visible: !win.gathering || backend.tray.length > 0
                Layout.fillWidth: true
                Layout.fillHeight: !win.gathering || backend.tray.length > 0
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: !win.linesOpen
                    Layout.preferredWidth: win.linesOpen ? 440 : 0
                    Layout.maximumWidth: win.linesOpen ? 440 : 32768
                    Layout.fillHeight: true
                    spacing: 12

            Item {
                id: screen
                visible: !win.gathering || backend.tray.length > 0
                Layout.fillWidth: true
                // Once lines are open the preview can shrink. It stays fixed before that.
                Layout.fillHeight: !win.gathering || win.linesOpen
                Layout.preferredHeight: win.gathering ? (win.linesOpen ? 240 : 200) : 0
                Layout.maximumHeight: win.gathering ? (win.linesOpen ? 240 : 200) : 10000
                Layout.minimumHeight: win.gathering && backend.tray.length > 0 ? (win.linesOpen ? 180 : 96) : 0

                Rectangle {
                    anchors.centerIn: parent
                    width: win.gathering ? Math.min(parent.width, Math.max(1, parent.height) * 16 / 9) : parent.width
                    height: win.gathering ? Math.min(parent.height, Math.max(1, parent.width) * 9 / 16) : parent.height
                    radius: win.gathering ? 12 : 0
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
                        cursorShape: Qt.PointingHandCursor
                        onClicked: togglePlay()
                    }
                    IconButton {
                        visible: win.gathering && win.previewing && !win.hasVideo
                        z: 2
                        anchors.left: parent.left
                        anchors.bottom: parent.bottom
                        anchors.margins: 12
                        iconName: movie.player.playbackState === MediaPlayer.PlayingState && !movie.player.priming ? "pause" : "play"
                        tipText: movie.player.playbackState === MediaPlayer.PlayingState ? "Pause" : "Play"
                        onClicked: togglePlay()
                    }
                    Rectangle {
                        id: watchChip
                        visible: !win.gathering && win.hasVideo
                        z: 2
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.margins: 12
                        // Words under the playhead. A plain movie, a gap, or an empty line stays one title.
                        readonly property string lineWords: {
                            if (!backend.planCut)
                                return ""
                            // Same block as playback: the end of a block is still that block.
                            var hit = backend.plan.sourceAt(editBar.playheadSec)
                            if (!hit || !hit.ok)
                                return ""
                            var index = hit.index
                            var rows = backend.plan.clips
                            if (!rows || index === undefined || index < 0 || index >= rows.length)
                                return ""
                            var row = rows[index]
                            if (!row || row.text === undefined || row.text === null)
                                return ""
                            return String(row.text).trim()
                        }
                        // Leave the zoom badge its own width, plus the same 12px gap the chip keeps from the edge.
                        readonly property real maxInner: Math.max(0, parent.width - 40
                            - (editBar.zoomed ? zoomChip.implicitWidth + 16 : 0))
                        readonly property real inner: Math.min(maxInner, Math.max(watchTitle.implicitWidth,
                            lineWords !== "" ? watchWords.implicitWidth : 0))
                        width: inner + 16
                        height: watchTitles.implicitHeight + 8
                        radius: 8
                        color: "#00000088"
                        Column {
                            id: watchTitles
                            anchors.centerIn: parent
                            width: watchChip.inner
                            spacing: 0
                            Label {
                                id: watchTitle
                                width: watchTitles.width
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                                text: (backend.roughCut ? "Rough cut" : fileName(backend.source))
                                      + " · " + lineClock(backend.duration)
                                      + (win.unexported ? " (trimmed)" : "")
                                color: "#f4f4f5"
                                font.pixelSize: 12
                            }
                            Label {
                                id: watchWords
                                visible: watchChip.lineWords !== ""
                                width: watchTitles.width
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                                text: watchChip.lineWords
                                color: "#f4f4f5"
                                font.pixelSize: 12
                            }
                        }
                    }
                }

                Label {
                    visible: win.gathering && win.previewing
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.margins: 8
                    text: fileName(backend.previewUrl)
                    color: "#b8b8bc"
                    font.pixelSize: 11
                }

                Rectangle {
                    visible: !win.gathering && editBar.zoomed
                    anchors.right: parent.right
                    anchors.top: parent.top
                    width: zoomChip.implicitWidth + 16
                    height: zoomChip.implicitHeight + 8
                    radius: 8
                    color: "transparent"
                    border.width: 1
                    border.color: win.accent
                    Label {
                        id: zoomChip
                        anchors.centerIn: parent
                        text: "zoomed"
                        color: win.accent
                        font.pixelSize: 12
                    }
                }
            }

            Rectangle {
                visible: win.gathering && backend.tray.length > 0
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                radius: 8
                color: "transparent"
                opacity: backend.busy ? 0.45 : 1
                DashedOutline { corner: 8 }
                Label {
                    anchors.centerIn: parent
                    text: "+  Add videos"
                    color: "#d6d6da"
                    font.pixelSize: 13
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: !backend.busy
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: backend.addVideosDialog()
                }
            }

            ListView {
                id: trayList
                visible: win.gathering && backend.tray.length > 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: win.linesOpen ? 52 : 0
                Layout.preferredHeight: win.linesOpen ? 52 : 200
                clip: true
                spacing: 6
                boundsBehavior: Flickable.StopAtBounds
                model: backend.tray
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Rectangle {
                    required property int index
                    required property string modelData
                    readonly property bool shotHot: shotHover.hovered || index === backend.trayIndex
                    width: trayList.width
                    height: 52
                    radius: 8
                    color: backend.trayFileExists(modelData) ? (index === backend.trayIndex ? "#2a2a2e" : "#1c1c1e") : "#2a1618"
                    border.width: 1
                    border.color: backend.trayFileExists(modelData) ? "#2c2c2f" : "#e07a7a"

                    HoverHandler { id: shotHover }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 8

                        Rectangle {
                            visible: backend.trayFileExists(modelData)
                            Layout.preferredWidth: 64
                            Layout.preferredHeight: 36
                            Layout.alignment: Qt.AlignVCenter
                            radius: 4
                            clip: true
                            color: "#0e0e10"
                            Image {
                                id: shotImage
                                anchors.fill: parent
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                // Reading the revision keeps the picture in the binding,
                                // so a grab that finishes later replaces the placeholder.
                                source: backend.trayThumbRevision >= 0
                                        ? fileUrl(backend.trayThumb(modelData)) : ""
                            }
                            Rectangle {
                                id: shotPulse
                                anchors.fill: parent
                                visible: (backend.trayThumbRevision >= 0 && backend.trayThumbPending(modelData))
                                         || shotImage.status === Image.Loading
                                color: win.accent
                                SequentialAnimation on opacity {
                                    running: shotPulse.visible
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 0.15; to: 0.45; duration: 900 }
                                    NumberAnimation { from: 0.45; to: 0.15; duration: 900 }
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    backend.trayIndex = index;
                                    trayList.positionViewAtIndex(index, ListView.Contain);
                                }
                            }
                        }
                        Label {
                            Layout.fillWidth: true
                            text: baseName(modelData)
                            color: backend.trayFileExists(modelData) ? "#f4f4f5" : "#e07a7a"
                            elide: Text.ElideMiddle
                            font.pixelSize: 13
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    backend.trayIndex = index;
                                    trayList.positionViewAtIndex(index, ListView.Contain);
                                }
                            }
                        }
                        Label {
                            text: backend.trayFileExists(modelData) ? backend.trayFileSize(modelData) : "file not found"
                            color: backend.trayFileExists(modelData) ? "#7a7a80" : "#e07a7a"
                            font.pixelSize: 12
                        }
                        QuietButton {
                            text: "Up"
                            visible: shotHot
                            enabled: index > 0 && !backend.busy
                            onClicked: {
                                backend.trayIndex = index;
                                backend.moveTray(-1);
                                trayList.positionViewAtIndex(backend.trayIndex, ListView.Contain);
                            }
                        }
                        QuietButton {
                            text: "Down"
                            visible: shotHot
                            enabled: index < backend.tray.length - 1 && !backend.busy
                            onClicked: {
                                backend.trayIndex = index;
                                backend.moveTray(1);
                                trayList.positionViewAtIndex(backend.trayIndex, ListView.Contain);
                            }
                        }
                        QuietButton {
                            text: "Remove"
                            enabled: !backend.busy
                            onClicked: {
                                backend.trayIndex = index;
                                backend.removeTray();
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                id: planColumn
                property bool openLine: false
                property bool closeLine: false
                visible: win.gathering && backend.cutMode === "speech" && backend.tray.length > 0
                Layout.fillWidth: true
                spacing: 8

                Label {
                    text: "This movie"
                    color: "#f4f4f5"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                TextArea {
                    id: planIntent
                    enabled: !backend.busy
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    // One line at the floor, two at ease. This gives up height before the line rows do.
                    Layout.minimumHeight: 32
                    Layout.preferredHeight: 52
                    Layout.maximumHeight: 52
                    Layout.verticalStretchFactor: 4
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    clip: true
                    font.pixelSize: 13
                    color: "#f4f4f5"
                    Component.onCompleted: text = backend.intent
                    onTextChanged: {
                        if (backend.busy) {
                            if (text !== backend.intent)
                                text = backend.intent
                            return
                        }
                        if (text !== backend.intent)
                            backend.intent = text
                    }
                    onVisibleChanged: {
                        if (!visible)
                            focus = false
                    }
                    background: Rectangle {
                        color: "#1c1c1e"
                        radius: 8
                        border.width: planIntent.activeFocus ? 1 : 0
                        border.color: win.accent
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    Repeater {
                        model: ["Open", "Measured", "Tight", "Frenzied"]
                        Label {
                            required property string modelData
                            text: modelData
                            color: backend.pace === modelData.toLowerCase() ? win.accent : "#b8b8bc"
                            font.pixelSize: 13
                            opacity: enabled ? 1 : 0.45
                            enabled: !backend.busy
                            Layout.minimumWidth: implicitWidth
                            Layout.maximumWidth: implicitWidth
                            MouseArea {
                                anchors.fill: parent
                                enabled: parent.enabled
                                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: backend.pace = modelData.toLowerCase()
                            }
                        }
                    }
                    Item { Layout.fillWidth: true; Layout.minimumWidth: 8 }
                    QuietButton {
                        text: "Open card"
                        enabled: !backend.busy
                        Layout.minimumWidth: implicitWidth
                        onClicked: {
                            if (planColumn.openLine) {
                                planColumn.openLine = false
                                openCardInput.focus = false
                                return
                            }
                            // Two editor rows push Dip to black under the Open list.
                            planColumn.closeLine = false
                            closeCardInput.focus = false
                            openCardInput.text = backend.intent
                            planColumn.openLine = true
                            openCardInput.forceActiveFocus()
                        }
                    }
                    QuietButton {
                        text: "Close card"
                        enabled: !backend.busy
                        Layout.minimumWidth: implicitWidth
                        onClicked: {
                            if (planColumn.closeLine) {
                                planColumn.closeLine = false
                                closeCardInput.focus = false
                                return
                            }
                            planColumn.openLine = false
                            openCardInput.focus = false
                            closeCardInput.text = backend.intent
                            planColumn.closeLine = true
                            closeCardInput.forceActiveFocus()
                        }
                    }
                }
                RowLayout {
                    visible: planColumn.openLine
                    Layout.fillWidth: true
                    spacing: 8
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        Layout.maximumHeight: 36
                        radius: 8
                        color: "#1c1c1e"
                        opacity: openCardInput.enabled ? 1 : 0.45
                        border.width: openCardInput.activeFocus ? 1 : 0
                        border.color: win.accent
                        TextInput {
                            id: openCardInput
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            verticalAlignment: Text.AlignVCenter
                            color: "#f4f4f5"
                            font.pixelSize: 13
                            clip: true
                            selectByMouse: true
                            enabled: !backend.busy
                            onAccepted: makeOpenCard()
                        }
                    }
                    QuietButton {
                        text: "Make card"
                        enabled: !backend.busy && openCardInput.text.trim() !== ""
                        Layout.minimumWidth: implicitWidth
                        onClicked: makeOpenCard()
                    }
                }
                RowLayout {
                    visible: planColumn.closeLine
                    Layout.fillWidth: true
                    spacing: 8
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        Layout.maximumHeight: 36
                        radius: 8
                        color: "#1c1c1e"
                        opacity: closeCardInput.enabled ? 1 : 0.45
                        border.width: closeCardInput.activeFocus ? 1 : 0
                        border.color: win.accent
                        TextInput {
                            id: closeCardInput
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            verticalAlignment: Text.AlignVCenter
                            color: "#f4f4f5"
                            font.pixelSize: 13
                            clip: true
                            selectByMouse: true
                            enabled: !backend.busy
                            onAccepted: makeCloseCard()
                        }
                    }
                    QuietButton {
                        text: "Make card"
                        enabled: !backend.busy && closeCardInput.text.trim() !== ""
                        Layout.minimumWidth: implicitWidth
                        onClicked: makeCloseCard()
                    }
                }
                CheckBox {
                    Layout.fillWidth: true
                    text: "Dip to black between files"
                    font.pixelSize: 13
                    padding: 0
                    focusPolicy: Qt.NoFocus
                    enabled: !backend.busy
                    checked: backend.sceneTransition === "dip"
                    onClicked: backend.sceneTransition = checked ? "dip" : "off"
                }
            }

                }

            ColumnLayout {
                id: linesColumn
                visible: win.linesOpen
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 220
                Layout.minimumHeight: 36
                spacing: 6
                onVisibleChanged: {
                    if (!visible)
                        reviseInput.focus = false
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Label {
                        text: "Lines"
                        color: "#f4f4f5"
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }
                    Label {
                        text: "kept (" + keptLineCount() + " of " + backend.selects.length + ")"
                        color: "#b8b8bc"
                        font.pixelSize: 13
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        visible: keptSpan() > 0
                        text: lineClock(keptSpan())
                        color: "#7a7a80"
                        font.pixelSize: 12
                        font.family: "monospace"
                    }
                }
                ColumnLayout {
                    visible: backend.reviseNotes.length > 0
                    Layout.fillWidth: true
                    spacing: 2
                    Repeater {
                        model: backend.reviseNotes
                        delegate: Label {
                            required property string modelData
                            Layout.fillWidth: true
                            text: modelData
                            color: "#7a7a80"
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        Layout.maximumHeight: 36
                        radius: 8
                        color: "#1c1c1e"
                        opacity: reviseInput.enabled ? 1 : 0.45
                        border.width: reviseInput.activeFocus ? 1 : 0
                        border.color: win.accent
                        Label {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            visible: reviseInput.text === ""
                            verticalAlignment: Text.AlignVCenter
                            text: "Change this cut"
                            color: "#7a7a80"
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        TextInput {
                            id: reviseInput
                            z: 1
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            verticalAlignment: Text.AlignVCenter
                            color: "#f4f4f5"
                            font.pixelSize: 13
                            clip: true
                            selectByMouse: true
                            enabled: !backend.busy
                            onAccepted: submitRevise()
                        }
                    }
                    QuietButton {
                        text: "Send"
                        enabled: !backend.busy && reviseInput.text.trim() !== ""
                        onClicked: submitRevise()
                    }
                    QuietButton {
                        text: "Revert"
                        visible: backend.canRevert
                        enabled: !backend.busy
                        onClicked: backend.revertRevise()
                    }
                }
                Flickable {
                    id: selectScroll
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentHeight: selectCol.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    Column {
                        id: selectCol
                        width: selectScroll.width
                        spacing: 6

                        Repeater {
                            model: backend.selects
                            delegate: Rectangle {
                                required property int index
                                required property var modelData
                                readonly property bool lineHot: lineHover.hovered || index === win.currentLine
                                readonly property bool covered: {
                                    var rows = backend.covers
                                    if (!rows)
                                        return false
                                    for (var i = 0; i < rows.length; i++) {
                                        if (rows[i].line == modelData.id)
                                            return true
                                    }
                                    return false
                                }
                                // The index is into cuts.json, which a tray move does not rewrite.
                                readonly property string coverName: {
                                    var rows = backend.covers
                                    var files = backend.cutClips
                                    if (!covered || !rows || !files)
                                        return ""
                                    for (var i = 0; i < rows.length; i++) {
                                        if (rows[i].line != modelData.id)
                                            continue
                                        var clip = rows[i].clip
                                        if (clip < 0 || clip >= files.length)
                                            return ""
                                        return baseName(files[clip])
                                    }
                                    return ""
                                }
                                width: selectCol.width
                                height: 40
                                radius: 8
                                color: index === win.currentLine ? "#2a2a2e" : "#1c1c1e"
                                border.width: 1
                                border.color: "#2c2c2f"

                                HoverHandler { id: lineHover }
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: win.currentLine = index
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 10
                                    anchors.rightMargin: 8
                                    spacing: 8
                                    Rectangle {
                                        visible: modelData.still !== undefined && modelData.still !== ""
                                        Layout.preferredWidth: 48
                                        Layout.preferredHeight: 27
                                        radius: 4
                                        clip: true
                                        color: "black"
                                        Image {
                                            anchors.fill: parent
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            source: parent.visible ? fileUrl(modelData.still) : ""
                                        }
                                    }
                                    Label {
                                        text: lineClock(modelData.start)
                                        color: win.accent
                                        font.pixelSize: 12
                                        font.family: "monospace"
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: modelData.text
                                        color: modelData.keep ? "#f4f4f5" : "#e07a7a"
                                        elide: Text.ElideRight
                                        font.pixelSize: 12
                                    }
                                    Label {
                                        visible: lineHot && lineReason(modelData.reason) !== ""
                                        text: lineReason(modelData.reason)
                                        color: "#7a7a80"
                                        font.pixelSize: 11
                                    }
                                    Label {
                                        visible: lineHot && coverName !== ""
                                        text: coverName
                                        color: "#b8b8bc"
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                        Layout.maximumWidth: 140
                                    }
                                    QuietButton {
                                        visible: lineHot && covered
                                        text: "Clear"
                                        enabled: !backend.busy
                                        onClicked: backend.clearCover(modelData.id)
                                    }
                                    QuietButton {
                                        visible: lineHot
                                        text: "Play"
                                        onClicked: playLine(modelData)
                                    }
                                    QuietButton {
                                        visible: lineHot && modelData.keep
                                        text: "Drop"
                                        enabled: !backend.busy
                                        onClicked: backend.dropSelect(modelData.id)
                                    }
                                    QuietButton {
                                        visible: lineHot && !modelData.keep
                                        text: "Restore"
                                        enabled: !backend.busy
                                        onClicked: backend.restoreSelect(modelData.id)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            }

            RowLayout {
                visible: win.hasVideo && !win.gathering
                Layout.fillWidth: true
                spacing: 10

                IconButton {
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 36
                    iconName: movie.player.playbackState === MediaPlayer.PlayingState && !movie.player.priming ? "pause" : "play"
                    tipText: movie.player.playbackState === MediaPlayer.PlayingState ? "Pause" : "Play"
                    enabled: backend.duration > 0
                    onClicked: togglePlay()
                }
                EditBar {
                    id: editBar
                    objectName: "editBar"
                    Layout.fillWidth: true
                    accent: win.accent
                    accentForeground: win.accentForeground
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
                    text: lineClock(editBar.playheadSec) + "  /  " + lineClock(win.timeline.keptDuration)
                    color: "#d6d6da"
                    font.pixelSize: 12
                    font.family: "monospace"
                }
                QuietButton {
                    objectName: "captionsButton"
                    visible: backend.roughCut
                    text: "Captions"
                    enabled: !backend.busy && !(backend.planCut && backend.plan.unexported)
                    onClicked: backend.writeCaptions()
                }
                QuietButton {
                    objectName: "shortButton"
                    visible: backend.roughCut
                    text: "Short"
                    enabled: !backend.busy && !(backend.planCut && backend.plan.unexported)
                    onClicked: backend.makeShort()
                }
                PillButton {
                    visible: backend.job === ""
                            && !(backend.roughCut && !win.looseCut && !win.unexported
                                 && backend.step === "movieSaved")
                    text: win.looseCut ? qsTr("Save…") : qsTr("Export…")
                    filled: win.looseCut || win.unexported || !backend.roughCut
                    enabled: backend.duration > 0 && !backend.busy
                    onClicked: exportVideo()
                }
                QuietButton {
                    visible: backend.job === "" && backend.roughCut && !win.looseCut && !win.unexported
                    text: qsTr("Export another size…")
                    enabled: backend.duration > 0 && !backend.busy
                    onClicked: exportVideo()
                }
                ActionButton {
                    visible: backend.job !== ""
                    text: backend.jobText
                    progress: backend.progress
                    primary: true
                    enabled: false
                }
            }

            Label {
                visible: win.hasVideo && !win.gathering && text !== ""
                Layout.fillWidth: true
                text: backend.step !== "" ? actionSentence()
                      : (win.statusText !== "" ? win.statusText
                         : (win.unexported ? "Trimmed by hand · not yet exported"
                            : (win.looseCut ? "Not yet saved" : "")))
                color: win.noticeText !== "" ? win.accent : "#7a7a80"
                font.pixelSize: 12
                font.family: "monospace"
                elide: Text.ElideMiddle
            }

        }

        RowLayout {
            visible: win.gathering && !win.settingsOpen
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: shotBar.top
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            height: 48
            spacing: 14

            QuietButton {
                Layout.minimumWidth: implicitWidth
                text: "Open list"
                enabled: !backend.busy
                onClicked: backend.openCutListDialog()
            }
            QuietButton {
                Layout.minimumWidth: implicitWidth
                text: "Save list"
                enabled: backend.tray.length > 0
                onClicked: backend.saveCutListDialog()
            }
            QuietButton {
                Layout.minimumWidth: implicitWidth
                text: "Trim one file"
                enabled: !backend.busy
                onClicked: openVideo()
            }
            Item { Layout.fillWidth: true }
        }

        Rectangle {
            id: shotBar
            visible: win.gathering && !win.settingsOpen
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 64
            color: "#1c1c1e"

            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: "#2c2c2f"
            }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 14
                Label {
                    Layout.fillWidth: true
                    text: actionSentence()
                    color: actionNeedsYou() ? win.accent
                            : (backend.step === "" && win.statusText === "" && missingShotCount() > 0
                               ? "#e07a7a" : "#7a7a80")
                    font.pixelSize: 12
                    font.family: "monospace"
                    elide: Text.ElideRight
                }
                ActionButton {
                    visible: backend.step === "needsKey" && backend.job === ""
                    text: qsTr("Keep every shot instead")
                    enabled: !backend.busy
                    onClicked: backend.cutMode = "assemble"
                }
                ActionButton {
                    visible: backend.job !== ""
                    text: backend.jobText
                    progress: backend.progress
                    primary: true
                    enabled: false
                }
                ActionButton {
                    id: cutButton
                    objectName: "cutButton"
                    visible: backend.job === "" && backend.step !== "needsKey" && backend.step !== "missingShot"
                    text: backend.busy ? qsTr("Cutting…") : (backend.selects.length > 0 ? qsTr("Cut again") : qsTr("Cut"))
                    primary: backend.tray.length > 0 && backend.selects.length === 0 && !backend.busy
                    enabled: backend.tray.length > 0 && !backend.busy && !backend.trayMissing
                    onClicked: backend.startCut()
                }
                ActionButton {
                    visible: backend.job === "" && backend.selects.length > 0
                            && backend.step !== "needsKey" && backend.step !== "missingShot"
                    text: backend.busy ? qsTr("Cutting…") : qsTr("Render")
                    primary: !backend.busy && backend.step !== "allDropped"
                    enabled: !backend.busy && backend.step !== "allDropped"
                            && (backend.step !== "lines" || keptLineCount() > 0)
                    onClicked: backend.renderSelects()
                }
                ActionButton {
                    visible: backend.step === "needsKey" && backend.job === ""
                    text: qsTr("Add xAI key…")
                    primary: true
                    enabled: !backend.busy
                    onClicked: {
                        openSettings();
                        keyField.forceActiveFocus();
                    }
                }
            }
        }

        ColumnLayout {
            visible: win.settingsOpen
            anchors.fill: parent
            anchors.margins: 28
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                Layout.maximumWidth: 560
                Item { Layout.fillWidth: true }
                QuietButton {
                    visible: win.settingsFromMovie
                    text: "Back to Watch"
                    onClicked: closeSettings()
                }
                QuietButton {
                    text: "Done"
                    textColor: win.accent
                    onClicked: closeSettings()
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.maximumWidth: 560
                spacing: 10

                Label {
                    text: "Settings"
                    color: "white"
                    font.pixelSize: 22
                    font.weight: Font.DemiBold
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Switch {
                        id: spokenCutsBox
                        objectName: "spokenCutsBox"
                        focusPolicy: Qt.NoFocus
                        enabled: !backend.busy
                        checked: backend.cutMode === "speech"
                        onClicked: backend.cutMode = checked ? "speech" : "assemble"
                    }
                    Label {
                        text: "Spoken cuts"
                        color: "#f4f4f5"
                        font.pixelSize: 14
                        Layout.minimumWidth: implicitWidth
                    }
                }
                Label {
                    visible: backend.cutMode === "speech"
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Finds the lines that match this movie, and drops the rest."
                    color: "#b8b8bc"
                    font.pixelSize: 13
                }
                Label {
                    visible: backend.cutMode === "speech"
                    text: "This movie"
                    color: "#f4f4f5"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }
                TextArea {
                    id: intentField
                    visible: backend.cutMode === "speech"
                    enabled: !backend.busy
                    Layout.fillWidth: true
                    Layout.preferredHeight: 78
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    font.pixelSize: 13
                    color: "#f4f4f5"
                    Component.onCompleted: text = backend.intent
                    onTextChanged: {
                        if (backend.busy) {
                            if (text !== backend.intent)
                                text = backend.intent
                            return
                        }
                        if (text !== backend.intent)
                            backend.intent = text
                    }
                    onVisibleChanged: {
                        if (!visible)
                            focus = false
                    }
                    background: Rectangle {
                        color: "#1c1c1e"
                        radius: 8
                        border.width: intentField.activeFocus ? 1 : 0
                        border.color: win.accent
                    }
                }
                Connections {
                    target: backend
                    function onIntentChanged() {
                        if (intentField.text !== backend.intent)
                            intentField.text = backend.intent
                        if (planIntent.text !== backend.intent)
                            planIntent.text = backend.intent
                    }
                }
                Label {
                    visible: backend.cutMode !== "speech"
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Keeps every file, in this order."
                    color: "#b8b8bc"
                    font.pixelSize: 13
                }
                CheckBox {
                    Layout.fillWidth: true
                    text: "Dip to black between files"
                    font.pixelSize: 13
                    padding: 0
                    focusPolicy: Qt.NoFocus
                    enabled: !backend.busy
                    checked: backend.sceneTransition === "dip"
                    onClicked: backend.sceneTransition = checked ? "dip" : "off"
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Switch {
                        focusPolicy: Qt.NoFocus
                        enabled: !backend.busy
                        checked: backend.broll
                        onClicked: backend.broll = checked
                    }
                    Label {
                        text: "Cut in B-roll"
                        color: "#f4f4f5"
                        font.pixelSize: 14
                        Layout.minimumWidth: implicitWidth
                    }
                }
                CheckBox {
                    Layout.fillWidth: true
                    text: "Mix the clip's sound under the voice"
                    font.pixelSize: 13
                    padding: 0
                    focusPolicy: Qt.NoFocus
                    enabled: backend.broll && !backend.busy
                    checked: backend.brollMix
                    onClicked: backend.brollMix = checked
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Label {
                        text: "xAI key"
                        color: "#7a7a80"
                        font.pixelSize: 13
                    }
                    Rectangle {
                        radius: 8
                        color: "transparent"
                        border.width: 1
                        border.color: backend.cutMode === "speech" && !backend.apiKeySet ? win.accent : "#3a3a3e"
                        width: keyBadge.implicitWidth + 16
                        height: keyBadge.implicitHeight + 8
                        Label {
                            id: keyBadge
                            anchors.centerIn: parent
                            text: backend.cutMode !== "speech" ? "not needed"
                                  : (backend.apiKeySet ? "set" : "not set")
                            color: backend.cutMode === "speech" && !backend.apiKeySet ? win.accent : "#b8b8bc"
                            font.pixelSize: 12
                        }
                    }
                    QuietButton {
                        text: keyField.visible ? "Hide" : "Change"
                        onClicked: {
                            keyField.visible = !keyField.visible;
                            if (!keyField.visible) {
                                keyField.text = "";
                                keyReveal.checked = false;
                            }
                        }
                    }
                }
                TextField {
                    id: keyField
                    visible: false
                    Layout.fillWidth: true
                    placeholderText: "Paste xAI key"
                    echoMode: keyReveal.checked ? TextInput.Normal : TextInput.Password
                    font.pixelSize: 13
                    color: "#f4f4f5"
                    background: Rectangle {
                        color: "#1c1c1e"
                        radius: 8
                        border.width: keyField.activeFocus ? 1 : 0
                        border.color: win.accent
                    }
                }
                RowLayout {
                    visible: keyField.visible
                    Layout.fillWidth: true
                    CheckBox {
                        id: keyReveal
                        text: "Show"
                        focusPolicy: Qt.NoFocus
                    }
                    QuietButton {
                        text: "Apply"
                        onClicked: {
                            backend.setApiKey(keyField.text);
                            keyField.text = "";
                            keyReveal.checked = false;
                            keyField.visible = false;
                        }
                    }
                }
            }
            Item { Layout.fillHeight: true }
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: 8
            radius: 12
            visible: dropTarget.containsDrag
            color: "#00000088"
            border.width: 2
            border.color: win.accent
            z: 20
            Label {
                anchors.centerIn: parent
                text: "Drop to add to shots"
                color: win.accent
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }
        }

        Rectangle {
            visible: win.helpVisible
            anchors.fill: parent
            color: "#000000cc"
            z: 30

            MouseArea {
                anchors.fill: parent
                onClicked: win.helpVisible = false
            }

            Rectangle {
                anchors.centerIn: parent
                width: helpColumn.width + 56
                height: helpColumn.height + 48
                radius: 12
                color: "#1c1c1e"

                MouseArea { anchors.fill: parent }

                Column {
                    id: helpColumn
                    anchors.centerIn: parent
                    spacing: 10

                    Label {
                        text: qsTr("How BotCut works")
                        color: "white"
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        bottomPadding: 8
                    }
                    Label {
                        width: 420
                        wrapMode: Text.WordWrap
                        color: "#d6d6da"
                        font.pixelSize: 13
                        text: qsTr("Add shots and put them in order. Cut finds the lines worth keeping. Drop lines, or tell BotCut what to change, then Render. Watch, trim by hand if you need to, then Save.")
                    }

                    Repeater {
                        model: [
                            { keys: "Space", action: "Play / pause" },
                            { keys: "←  /  →", action: "Move playhead 1s" },
                            { keys: "Shift ←  /  →", action: "Move playhead 5s" },
                            { keys: "Alt ←  /  →", action: "Move playhead 0.2s" },
                            { keys: "[  /  ]", action: "Previous / next clip edge" },
                            { keys: "S", action: "Split the clip at the playhead" },
                            { keys: "X", action: "Remove the clip, or restore the gap" },
                            { keys: "Ctrl Space", action: "Clip start to playhead" },
                            { keys: "Alt Space", action: "Clip end to playhead" },
                            { keys: "Ctrl Z", action: "Undo (Ctrl Shift Z redo)" },
                            { keys: "Z", action: "Zoom to the clip" },
                            { keys: "Ctrl O", action: "Open a video" },
                            { keys: "Ctrl S", action: "Save or export" },
                            { keys: "Q", action: "Quit" },
                            { keys: "?", action: "Show these shortcuts" }
                        ]
                        delegate: Row {
                            width: 420
                            spacing: 18
                            Label {
                                width: 250
                                text: modelData.action
                                color: "#d6d6da"
                                font.pixelSize: 13
                                elide: Text.ElideRight
                            }
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: keyChip.implicitWidth + 16
                                height: keyChip.implicitHeight + 6
                                radius: 6
                                color: "#2a2a2e"
                                Label {
                                    id: keyChip
                                    anchors.centerIn: parent
                                    text: modelData.keys
                                    color: "#d6d6da"
                                    font.pixelSize: 12
                                    font.family: "monospace"
                                }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            visible: win.quitConfirmVisible
            anchors.fill: parent
            color: "#000000cc"
            z: 30
            onVisibleChanged: {
                if (!visible)
                    return;
                if (backend.busy)
                    quitCancelButton.forceActiveFocus();
                else
                    quitExportButton.forceActiveFocus();
            }

            MouseArea {
                anchors.fill: parent
                onClicked: win.quitConfirmVisible = false
            }

            Rectangle {
                anchors.centerIn: parent
                width: quitColumn.width + 64
                height: quitColumn.height + 48
                radius: theme.radius
                color: "#1c1c1e"

                MouseArea { anchors.fill: parent }

                Column {
                    id: quitColumn
                    anchors.centerIn: parent
                    spacing: 8

                    Label {
                        text: backend.busy ? qsTr("Stop the render and quit?")
                                : (win.looseCut ? qsTr("Save your movie before you quit?")
                                   : qsTr("Export your trim before you quit?"))
                        color: "white"
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Label {
                        text: backend.busy
                              ? qsTr("Quitting stops the job and keeps nothing.")
                              : (win.looseCut
                                 ? qsTr("It's only in a temporary folder. Quitting deletes it.")
                                 : qsTr("Your hand trim isn't in a file yet."))
                        color: "#d6d6da"
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                        width: 420
                        bottomPadding: 12
                    }
                    Row {
                        anchors.right: parent.right
                        spacing: 10
                        DialogButton {
                            id: quitCancelButton
                            text: qsTr("Keep working")
                            focus: true
                            KeyNavigation.left: quitExportButton.visible ? quitExportButton : quitQuitButton
                            KeyNavigation.right: quitQuitButton
                            KeyNavigation.tab: quitQuitButton
                            KeyNavigation.backtab: quitExportButton.visible ? quitExportButton : quitQuitButton
                            onClicked: win.quitConfirmVisible = false
                        }
                        DialogButton {
                            id: quitQuitButton
                            text: backend.busy ? qsTr("Stop and quit")
                                    : (win.looseCut ? qsTr("Quit without saving")
                                       : qsTr("Quit without exporting"))
                            focus: true
                            KeyNavigation.left: quitCancelButton
                            KeyNavigation.right: quitExportButton.visible ? quitExportButton : quitCancelButton
                            KeyNavigation.tab: quitExportButton.visible ? quitExportButton : quitCancelButton
                            KeyNavigation.backtab: quitCancelButton
                            onClicked: forceQuit()
                        }
                        DialogButton {
                            id: quitExportButton
                            visible: !backend.busy
                            text: win.looseCut ? qsTr("Save…") : qsTr("Export…")
                            primary: true
                            focus: true
                            KeyNavigation.left: quitQuitButton
                            KeyNavigation.right: quitCancelButton
                            KeyNavigation.tab: quitCancelButton
                            KeyNavigation.backtab: quitQuitButton
                            onClicked: {
                                win.quitConfirmVisible = false;
                                exportVideo();
                            }
                        }
                    }
                }
            }
        }
    }

    Connections {
        target: backend
        function onInfoChanged() {
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
