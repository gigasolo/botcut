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
    readonly property color accent: backend.themeAccent
    readonly property color accentForeground: backend.themeAccentForeground
    readonly property bool audioOutputReady: audioOutput !== null
    property var audioOutput: null
    property string noticeText: ""
    property bool helpVisible: false
    property bool quitConfirmVisible: false
    property bool settingsOpen: false
    property bool settingsFromMovie: false
    property bool sidebarCollapsed: false
    property int currentLine: -1
    property int linePlayStart: -1
    property int linePlayEnd: -1
    readonly property string statusText: noticeText !== "" ? noticeText : backend.status

    readonly property var timeline: backend.timeline
    // Quitting only warns about unexported cuts. Clips spanning the whole
    // video are never dirty — that's just the source.
    readonly property bool unexported: hasVideo && timeline.unexported
    // A rendered movie with no handle edits lives only in /tmp until it is saved.
    readonly property bool looseCut: backend.renderedUnsaved && !unexported
    // Editing shortcuts go quiet while a dialog is up or a handle is dragged.
    readonly property bool editing: hasVideo && !gathering && !settingsOpen && backend.duration > 0
                                   && !quitConfirmVisible && !editBar.interacting

    Material.theme: Material.Dark
    Material.accent: win.accent
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
    function statusPercent() {
        var match = /(?:Rendering|Opening) (\d+)%/.exec(backend.status);
        if (!match)
            return -1;
        var n = parseInt(match[1], 10);
        return n >= 0 && n <= 100 ? n : -1;
    }
    function playLine(line) {
        if (!gathering)
            return;
        var clip = line.clip;
        if (clip < 0 || clip >= backend.tray.length)
            return;
        linePlayStart = Math.max(0, Math.round(line.start * 1000));
        linePlayEnd = Math.max(linePlayStart, Math.round(line.end * 1000));
        if (backend.trayIndex !== clip)
            backend.trayIndex = clip;
        ensureAudioOutput();
        player.primed = true;
        player.priming = false;
        player.position = linePlayStart;
        player.play();
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
        if (player.playbackState === MediaPlayer.PlayingState)
            player.pause();
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
        if (!win.hasVideo || backend.duration <= 0 || backend.busy)
            return;
        player.pause();
        backend.exportDialog();
    }
    function ensureAudioOutput() {
        if (audioOutput === null && (win.hasVideo || win.previewing))
            audioOutput = audioOutputComponent.createObject(win);
    }
    function releaseAudioOutput() {
        if (audioOutput === null)
            return;
        var oldAudioOutput = audioOutput;
        audioOutput = null;
        oldAudioOutput.destroy();
    }
    function syncPlaybackAudio() {
        if (hasVideo || previewing) {
            ensureAudioOutput();
            return;
        }
        player.stop();
        releaseAudioOutput();
    }
    function togglePlay() {
        if (win.gathering) {
            if (!win.previewing)
                return;
            ensureAudioOutput();
            if (player.priming)
                player.finishPriming();
            if (player.playbackState === MediaPlayer.PlayingState)
                player.pause();
            else
                player.play();
            return;
        }
        if (!win.hasVideo || backend.duration <= 0)
            return;
        ensureAudioOutput();
        if (player.priming)
            player.finishPriming();
        if (player.playbackState === MediaPlayer.PlayingState) {
            player.pause();
            return;
        }
        // Play only the clips: from the playhead if it's in one, else from
        // the next clip, and from the top once past the last.
        var from = timeline.playableFrom(editBar.playheadSec);
        seekTo(from < 0 ? timeline.edgeFrom(0, -1) : from);
        player.play();
    }
    function seekTo(seconds) {
        if (!win.hasVideo || backend.duration <= 0)
            return;
        if (player.priming)
            player.finishPriming();
        var t = Math.max(0, Math.min(seconds, backend.duration));
        editBar.playheadSec = t;
        player.position = Math.round(t * 1000);
    }
    property bool quitting: false
    function requestQuit() {
        if (unexported || looseCut) {
            if (player.playbackState === MediaPlayer.PlayingState)
                player.pause();
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
        player.stop();
        releaseAudioOutput();
        win.close();
        Qt.quit();
    }

    Component.onCompleted: ensureAudioOutput()
    onHasVideoChanged: syncPlaybackAudio()
    onPreviewingChanged: syncPlaybackAudio()
    onClosing: (close) => {
        if (win.quitting)
            return;
        if (win.unexported || win.looseCut) {
            close.accepted = false;
            if (player.playbackState === MediaPlayer.PlayingState)
                player.pause();
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
                 && !keyField.activeFocus && !intentField.activeFocus
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
            player.pause();
            seekTo(timeline.edgeFrom(editBar.playheadSec, -1));
        }
    }

    Shortcut {
        sequence: "]"
        context: Qt.ApplicationShortcut
        enabled: win.editing
        onActivated: {
            player.pause();
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
        enabled: !win.quitConfirmVisible
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

    MediaPlayer {
        id: player
        source: win.gathering ? backend.previewUrl : backend.source
        videoOutput: videoOut
        audioOutput: win.audioOutput

        // Render the opening frame on load instead of showing black. Playback
        // starts muted and stops as soon as VideoOutput receives a frame.
        property bool primed: false
        property bool priming: false

        function startPriming() {
            if (win.linePlayStart >= 0) {
                primed = true;
                priming = false;
                position = win.linePlayStart;
                play();
                return;
            }
            if (primed || priming || source.toString() === "")
                return;
            win.ensureAudioOutput();
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
            position = 0;
            priming = false;
        }

        onSourceChanged: {
            primeFallback.stop();
            priming = false;
            primed = false;
        }
        onMediaStatusChanged: {
            if (mediaStatus === MediaPlayer.LoadedMedia || mediaStatus === MediaPlayer.BufferedMedia)
                startPriming();
        }
        onPositionChanged: {
            if (win.gathering && win.linePlayEnd >= 0
                    && playbackState === MediaPlayer.PlayingState && position >= win.linePlayEnd) {
                pause();
                win.linePlayStart = -1;
                win.linePlayEnd = -1;
                return;
            }
            if (!win.gathering) {
                win.linePlayStart = -1;
                win.linePlayEnd = -1;
            }
            if (priming && position > 0) {
                finishPriming();
                return;
            }
            if (win.gathering)
                return;
            // Play only the clips: hop over gaps and stop after the last clip.
            if (playbackState === MediaPlayer.PlayingState) {
                var t = position / 1000, next = timeline.playableFrom(t);
                // Past the last clip: stop where we are. Seeking to its end
                // could land past the final frame.
                if (next < 0) {
                    pause();
                    editBar.playheadSec = timeline.edgeFrom(backend.duration, 1);
                    return;
                }
                if (next - t > 0.05) {
                    position = Math.round(next * 1000);
                    return;
                }
            }
            if (!editBar.interacting)
                editBar.playheadSec = position / 1000;
        }
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
            Item { Layout.fillHeight: true }
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
            enabled: win.gathering && !win.settingsOpen
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

            Item {
                id: screen
                visible: !win.gathering || backend.tray.length > 0
                Layout.fillWidth: true
                Layout.fillHeight: !win.gathering
                Layout.preferredHeight: win.gathering ? (backend.selects.length > 0 ? 120 : 200) : 0
                Layout.maximumHeight: win.gathering ? (backend.selects.length > 0 ? 120 : 200) : 10000
                Layout.minimumHeight: win.gathering && backend.tray.length > 0 ? 96 : 0

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
                            player.finishPriming();
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
                        iconName: player.playbackState === MediaPlayer.PlayingState && !player.priming ? "pause" : "play"
                        tipText: player.playbackState === MediaPlayer.PlayingState ? "Pause" : "Play"
                        onClicked: togglePlay()
                    }
                    Rectangle {
                        visible: !win.gathering && win.hasVideo
                        z: 2
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.margins: 12
                        width: watchTitle.implicitWidth + 16
                        height: watchTitle.implicitHeight + 8
                        radius: 8
                        color: "#00000088"
                        Label {
                            id: watchTitle
                            anchors.centerIn: parent
                            text: (backend.roughCut ? "Rough cut" : fileName(backend.source))
                                  + " · " + lineClock(backend.duration)
                                  + (win.unexported ? " (trimmed)" : "")
                            color: "#f4f4f5"
                            font.pixelSize: 12
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
                DashedOutline { corner: 8 }
                Label {
                    anchors.centerIn: parent
                    text: "+  Add videos"
                    color: "#d6d6da"
                    font.pixelSize: 13
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.addVideosDialog()
                }
            }

            ListView {
                id: trayList
                visible: win.gathering && backend.tray.length > 0
                Layout.fillWidth: true
                Layout.fillHeight: backend.selects.length === 0
                Layout.minimumHeight: 0
                Layout.preferredHeight: backend.selects.length > 0 ? 116 : 200
                Layout.maximumHeight: backend.selects.length > 0 ? 116 : 10000
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
                        anchors.leftMargin: 12
                        anchors.rightMargin: 8
                        spacing: 8

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
                            enabled: index > 0
                            onClicked: {
                                backend.trayIndex = index;
                                backend.moveTray(-1);
                                trayList.positionViewAtIndex(backend.trayIndex, ListView.Contain);
                            }
                        }
                        QuietButton {
                            text: "Down"
                            visible: shotHot
                            enabled: index < backend.tray.length - 1
                            onClicked: {
                                backend.trayIndex = index;
                                backend.moveTray(1);
                                trayList.positionViewAtIndex(backend.trayIndex, ListView.Contain);
                            }
                        }
                        QuietButton {
                            text: "Remove"
                            onClicked: {
                                backend.trayIndex = index;
                                backend.removeTray();
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                visible: win.gathering && backend.selects.length > 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 36
                spacing: 6

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
                                    QuietButton {
                                        visible: lineHot
                                        text: "Play"
                                        onClicked: playLine(modelData)
                                    }
                                    QuietButton {
                                        visible: lineHot && modelData.keep
                                        text: "Drop"
                                        onClicked: backend.dropSelect(modelData.id)
                                    }
                                    QuietButton {
                                        visible: lineHot && !modelData.keep
                                        text: "Restore"
                                        onClicked: backend.restoreSelect(modelData.id)
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
                    iconName: player.playbackState === MediaPlayer.PlayingState && !player.priming ? "pause" : "play"
                    tipText: player.playbackState === MediaPlayer.PlayingState ? "Pause" : "Play"
                    enabled: backend.duration > 0
                    onClicked: togglePlay()
                }
                EditBar {
                    id: editBar
                    objectName: "editBar"
                    Layout.fillWidth: true
                    accent: win.accent
                    accentForeground: win.accentForeground
                    onScrub: (seconds) => {
                        player.pause();
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
                    enabled: !backend.busy
                    onClicked: backend.writeCaptions()
                }
                QuietButton {
                    objectName: "shortButton"
                    visible: backend.roughCut
                    text: "Short"
                    enabled: !backend.busy
                    onClicked: backend.makeShort()
                }
                PillButton {
                    text: win.looseCut ? "Save" : "Export"
                    filled: true
                    enabled: backend.duration > 0 && !backend.busy
                    onClicked: exportVideo()
                }
            }

            Label {
                visible: win.hasVideo && !win.gathering && text !== ""
                Layout.fillWidth: true
                text: win.statusText !== "" ? win.statusText
                      : (win.unexported ? "Trimmed by hand · not yet exported"
                         : (win.looseCut ? "Not yet saved" : ""))
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
            Rectangle {
                visible: statusPercent() >= 0
                anchors.top: parent.top
                anchors.left: parent.left
                height: 2
                width: parent.width * statusPercent() / 100
                color: win.accent
            }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 14
                Label {
                    Layout.fillWidth: true
                    text: shotsStatus()
                    color: win.statusText === "" && missingShotCount() > 0 ? "#e07a7a" : "#7a7a80"
                    font.pixelSize: 12
                    font.family: "monospace"
                    elide: Text.ElideRight
                }
                PillButton {
                    id: cutButton
                    objectName: "cutButton"
                    Layout.minimumWidth: implicitWidth
                    text: backend.busy ? "Cutting…" : (backend.selects.length > 0 ? "Cut again" : "Cut")
                    filled: backend.tray.length > 0 && backend.selects.length === 0 && !backend.busy
                    enabled: backend.tray.length > 0 && !backend.busy && !backend.trayMissing
                    onClicked: backend.startCut()
                }
                PillButton {
                    visible: backend.selects.length > 0
                    Layout.minimumWidth: implicitWidth
                    text: backend.busy ? "Cutting…" : "Render"
                    filled: !backend.busy
                    enabled: !backend.busy
                    onClicked: backend.renderSelects()
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
                    Layout.fillWidth: true
                    Layout.preferredHeight: 78
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    font.pixelSize: 13
                    color: "#f4f4f5"
                    Component.onCompleted: text = backend.intent
                    onTextChanged: {
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
                    checked: backend.sceneTransition === "dip"
                    onClicked: backend.sceneTransition = checked ? "dip" : "off"
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
                        text: "Keyboard shortcuts"
                        color: "white"
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        bottomPadding: 8
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
                if (visible)
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
                radius: 12
                color: "#1c1c1e"

                MouseArea { anchors.fill: parent }

                Column {
                    id: quitColumn
                    anchors.centerIn: parent
                    spacing: 8

                    Label {
                        text: win.looseCut ? "Save this movie?" : "Unexported edit"
                        color: "white"
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Label {
                        text: win.looseCut
                              ? "This cut is only in a temporary folder. Save it, or it will be lost."
                              : "Your edit hasn't been exported. Quit anyway?"
                        color: "#d6d6da"
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                        width: 360
                        bottomPadding: 12
                    }
                    Row {
                        anchors.right: parent.right
                        spacing: 10
                        DialogButton {
                            id: quitCancelButton
                            text: "Cancel"
                            KeyNavigation.left: quitExportButton
                            KeyNavigation.right: quitQuitButton
                            KeyNavigation.tab: quitQuitButton
                            KeyNavigation.backtab: quitExportButton
                            onClicked: win.quitConfirmVisible = false
                        }
                        DialogButton {
                            id: quitQuitButton
                            text: win.looseCut ? "Lose it" : "Quit"
                            KeyNavigation.left: quitCancelButton
                            KeyNavigation.right: quitExportButton
                            KeyNavigation.tab: quitExportButton
                            KeyNavigation.backtab: quitCancelButton
                            onClicked: forceQuit()
                        }
                        DialogButton {
                            id: quitExportButton
                            text: win.looseCut ? "Save" : "Export"
                            primary: true
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
            primeFallback.stop();
            player.priming = false;
            player.primed = false;
            editBar.zoomed = false;
            editBar.playheadSec = 0;
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
}
