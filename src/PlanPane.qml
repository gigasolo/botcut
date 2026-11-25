import QtCore
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The left column. The recents on the empty home, the shot list on Shots, and
// on Lines and Movie the line list over the chat, with a handle between them
// that remembers where it was dragged. The cut row under the picture holds the
// one pace field; the keys its list swallows are read through here.
Item {
    id: root
    property var host
    property var film
    // The cut row holds the one pace field in the window.
    property var decisions

    Settings {
        id: paneSettings
        category: "layout"
        property var linesSplit
    }

    readonly property bool paceOpen: decisions ? decisions.paceOpen : false
    readonly property bool paceKeys: decisions ? decisions.paceKeys : false
    function closePace() {
        if (decisions)
            decisions.closePace()
    }

    function reasonText(reason) {
        if (reason === "unique?")
            return qsTr("unsure")
        if (reason === "restored")
            return qsTr("put back")
        if (reason === "dropped")
            return qsTr("dropped")
        return reason ? String(reason) : ""
    }
    readonly property var linePositions: {
        var lines = backend.selects
        var map = {}
        if (!lines)
            return map
        for (var p = 0; p < lines.length; p++) {
            if (lines[p] && lines[p].id !== undefined)
                map[Number(lines[p].id)] = p
        }
        return map
    }
    // The run this line is in, and whether the line is its first. Null when none.
    function coverOf(line) {
        return runOf(line, backend.covers)
    }
    // The same for a stretch on a second camera. B-roll over a line is what shows, so it is what is said.
    function angleOf(line) {
        return coverOf(line) ? null : runOf(line, backend.angles)
    }
    function runOf(line, rows) {
        var lines = backend.selects
        if (!line || !rows || rows.length === 0 || !lines)
            return null
        var positions = linePositions
        var at = positions[Number(line.id)]
        if (at === undefined)
            return null
        for (var i = 0; i < rows.length; i++) {
            var cover = rows[i]
            if (!cover)
                continue
            var first = positions[Number(cover.line)]
            if (first === undefined)
                continue
            var last = cover.through === undefined || cover.through === null ? first : positions[Number(cover.through)]
            if (last === undefined || last < first)
                last = first
            if (at < first || at > last)
                continue
            // A dropped line ends the run there, and a run whose first line is dropped is gone.
            var alive = true
            for (var k = first; k <= at; k++) {
                if (!lines[k] || lines[k].keep === false) {
                    alive = false
                    break
                }
            }
            if (!alive)
                return null
            return { cover: cover, first: at === first }
        }
        return null
    }
    function rowOverlay(line) {
        var cover = runOf(line, backend.covers)
        if (cover)
            return { kind: "broll", hit: cover }
        var angle = runOf(line, backend.angles)
        if (angle)
            return { kind: "angle", hit: angle }
        return null
    }
    function coverTextFor(overlay) {
        if (!overlay)
            return ""
        if (overlay.kind === "angle") {
            if (!overlay.hit.first)
                return qsTr("Second camera goes on")
            return overlay.hit.cover.reason ? qsTr("Second camera · %1").arg(String(overlay.hit.cover.reason))
                                            : qsTr("Second camera")
        }
        var hit = overlay.hit
        if (!hit.first)
            return qsTr("B-roll goes on")
        var files = backend.cutClips
        var clip = hit.cover.clip
        if (!files || clip < 0 || clip >= files.length)
            return ""
        var path = String(files[clip])
        var slash = path.lastIndexOf("/")
        var words = qsTr("B-roll: %1").arg(slash < 0 ? path : path.substring(slash + 1))
        var span = Number(hit.cover.end) - Number(hit.cover.start)
        if (isFinite(span) && span > 0)
            words += " · " + qsTr("%1 s").arg(Math.round(span))
        if (hit.cover.reason)
            words += " · " + String(hit.cover.reason)
        return words
    }
    function coverStillFor(overlay) {
        if (!overlay || !overlay.hit.first || !overlay.hit.cover.still)
            return ""
        return host.fileUrl(String(overlay.hit.cover.still))
    }
    function coverText(line) {
        return coverTextFor(rowOverlay(line))
    }
    function coverStill(line) {
        return coverStillFor(rowOverlay(line))
    }
    function clockOf(line) {
        var start = line ? Number(line.start) : 0
        if (!isFinite(start))
            start = 0
        return host.lineClock(start)
    }

    readonly property int playheadIndex: {
        if (!host || host.viewStep !== "movie" || !backend.planCut || !film)
            return -1
        var at = film.playheadSec
        var hit = backend.plan.sourceAt(at)
        if (!hit || !hit.ok)
            return -1
        var rows = backend.plan.clips
        var index = hit.index
        if (!rows || index === undefined || index < 0 || index >= rows.length)
            return -1
        var row = rows[index]
        if (!row)
            return -1
        var selects = backend.selects
        var segClip = row.clip
        var segStart = Number(row.sourceStart)
        var segEnd = Number(row.sourceEnd)
        if (segClip !== undefined && isFinite(segStart) && isFinite(segEnd)) {
            var bestIdx = -1
            var bestOverlap = 0
            for (var j = 0; j < selects.length; j++) {
                var sel = selects[j]
                if (!sel || sel.clip !== segClip)
                    continue
                var overlap = Math.min(segEnd, Number(sel.end)) - Math.max(segStart, Number(sel.start))
                if (overlap > bestOverlap) {
                    bestOverlap = overlap
                    bestIdx = j
                }
            }
            if (bestIdx >= 0)
                return bestIdx
        }
        if (row.text === undefined || row.text === null)
            return -1
        var words = String(row.text).trim()
        if (words === "")
            return -1
        for (var i = 0; i < selects.length; i++) {
            var text = selects[i].text
            if (text !== undefined && text !== null && String(text).trim() === words)
                return i
        }
        return -1
    }

    component RecentLine: Rectangle {
        id: recent
        property string title
        property string side
        signal activated()
        signal sideActivated()
        width: parent ? parent.width : implicitWidth
        height: 28
        radius: theme.radius
        color: recentHover.hovered && enabled ? theme.selected : "transparent"
        HoverHandler { id: recentHover; enabled: recent.enabled }
        Label {
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.right: sideText.visible ? sideText.left : parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: recent.title
            color: theme.foreground
            opacity: recent.enabled ? 0.62 : 0.38
            font.pixelSize: 12
            elide: Text.ElideRight
        }
        MouseArea {
            anchors.fill: parent
            enabled: recent.enabled
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: recent.activated()
        }
        Label {
            id: sideText
            visible: recent.side !== ""
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: recent.side
            color: theme.accent
            opacity: recent.enabled ? 1 : 0.38
            font.pixelSize: 12
        }
        MouseArea {
            anchors.fill: sideText
            anchors.margins: -6
            visible: sideText.visible
            enabled: recent.enabled
            cursorShape: Qt.PointingHandCursor
            onClicked: recent.sideActivated()
        }
    }

    Rectangle {
        anchors.fill: parent
        color: theme.surface
    }

    StackLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        anchors.topMargin: 12
        anchors.bottomMargin: 12
        currentIndex: {
            if (host.viewStep === "movie" && !backend.planCut)
                return 3
            if (host.viewStep === "lines" || (host.viewStep === "movie" && backend.planCut))
                return 2
            return backend.tray.length === 0 ? 0 : 1
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12
            Label {
                Layout.fillWidth: true
                text: qsTr("Pick up where you left off")
                color: theme.foreground
                font.pixelSize: 16
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            Label {
                visible: backend.recentLists.length === 0 && backend.recentCuts.length === 0
                Layout.fillWidth: true
                text: qsTr("Nothing saved yet.")
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            Flickable {
                visible: backend.recentLists.length > 0 || backend.recentCuts.length > 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentHeight: recentCol.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                Column {
                    id: recentCol
                    width: parent.width
                    spacing: 4
                    Label {
                        visible: backend.recentLists.length > 0
                        text: qsTr("Lists")
                        color: theme.foreground
                        opacity: 0.38
                        font.pixelSize: 12
                    }
                    Repeater {
                        model: backend.recentLists
                        RecentLine {
                            required property var modelData
                            width: recentCol.width
                            enabled: !backend.busy
                            title: modelData.name
                            onActivated: backend.reopenList(modelData.path)
                        }
                    }
                    Label {
                        visible: backend.recentCuts.length > 0
                        text: qsTr("Movies")
                        color: theme.foreground
                        opacity: 0.38
                        font.pixelSize: 12
                        topPadding: 8
                    }
                    Repeater {
                        model: backend.recentCuts
                        RecentLine {
                            required property var modelData
                            width: recentCol.width
                            enabled: !backend.busy
                            title: modelData.list
                                  ? modelData.name + " — " + qsTr("Movie, with its list")
                                  : modelData.name
                            side: modelData.list ? qsTr("List") : ""
                            onActivated: backend.watchRecent(modelData.path)
                            onSideActivated: backend.reopenList(modelData.list)
                        }
                    }
                }
            }
        }

        ColumnLayout {
            id: shotsColumn
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            Label {
                Layout.fillWidth: true
                text: qsTr("Shots")
                color: theme.foreground
                font.pixelSize: 15
                font.weight: Font.DemiBold
            }

            Rectangle {
                Layout.fillWidth: true
                height: 32
                radius: theme.radius
                color: theme.background
                border.width: movieTitleField.activeFocus ? 1 : 0
                border.color: theme.accent
                TextInput {
                    id: movieTitleField
                    objectName: "movieTitleField"
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    verticalAlignment: Text.AlignVCenter
                    color: theme.foreground
                    font.pixelSize: 13
                    clip: true
                    selectByMouse: true
                    enabled: !backend.busy
                    text: (backend && backend.movieTitle !== undefined) ? backend.movieTitle : ""
                    onTextEdited: if (backend && backend.movieTitle !== undefined) backend.movieTitle = text
                    onAccepted: {
                        if (backend && backend.movieTitle !== undefined)
                            backend.movieTitle = text
                        focus = false
                    }
                }
                Label {
                    anchors.fill: movieTitleField
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    visible: movieTitleField.text === ""
                    text: qsTr("Movie title (output file name)")
                    color: theme.foreground
                    opacity: 0.38
                    font.pixelSize: 12
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }

            // Live-video title overlay card pinned at the top of the Shots list when set.
            Rectangle {
                id: liveTitleCard
                objectName: "liveTitleCard"
                readonly property string textValue: (backend && backend.liveTitle !== undefined) ? backend.liveTitle : ""
                visible: textValue !== ""
                Layout.fillWidth: true
                height: visible ? (liveTitleRow.implicitHeight + 16) : 0
                radius: theme.radius
                color: theme.selected
                border.width: 1
                border.color: theme.line

                RowLayout {
                    id: liveTitleRow
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8

                    Column {
                        Layout.fillWidth: true
                        spacing: 2
                        Label {
                            width: parent.width
                            text: liveTitleCard.textValue
                            color: theme.foreground
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Label {
                            text: qsTr("Live title · fades over opening 3s")
                            color: theme.accent
                            font.pixelSize: 11
                        }
                    }

                    ActionButton {
                        raised: true
                        text: qsTr("Remove")
                        enabled: !backend.busy
                        onClicked: if (backend && backend.liveTitle !== undefined) backend.liveTitle = ""
                    }
                }
            }

            ListView {
                id: shotList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                spacing: 4
                model: backend.tray
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 4 }
                delegate: ShotRow {}
            }

            // This list's own actions, under its shots.
            Flow {
                Layout.fillWidth: true
                spacing: 4
                ActionButton {
                    raised: true
                    leftPadding: 10
                    rightPadding: 10
                    text: qsTr("Add shots…")
                    enabled: !backend.busy
                    onClicked: backend.addVideosDialog()
                }
                ActionButton {
                    raised: true
                    leftPadding: 10
                    rightPadding: 10
                    text: qsTr("Add a title card…")
                    enabled: !backend.busy
                    onClicked: host.openTitleCard()
                }
                ActionButton {
                    raised: true
                    leftPadding: 10
                    rightPadding: 10
                    text: qsTr("Save list…")
                    enabled: backend.tray.length > 0
                    onClicked: backend.saveCutListDialog()
                }
            }
        }

        ColumnLayout {
            id: linesColumn
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Label {
                Layout.fillWidth: true
                Layout.bottomMargin: 8
                text: qsTr("Lines")
                color: theme.foreground
                font.pixelSize: 15
                font.weight: Font.DemiBold
            }

            // The rows over the chat. Drag the line between them.
            SplitView {
                id: linesSplit
                objectName: "linesSplit"
                Layout.fillWidth: true
                Layout.fillHeight: true
                orientation: Qt.Vertical
                handle: Rectangle {
                    implicitWidth: linesSplit.width
                    implicitHeight: 9
                    color: "transparent"
                    Rectangle {
                        anchors.centerIn: parent
                        width: parent.width
                        height: 1
                        color: SplitHandle.hovered || SplitHandle.pressed ? theme.hover : theme.line
                    }
                }
                Component.onCompleted: {
                    if (paneSettings.linesSplit)
                        linesSplit.restoreState(paneSettings.linesSplit)
                }
                Component.onDestruction: paneSettings.linesSplit = linesSplit.saveState()

                ListView {
                    id: lineList
                    SplitView.fillWidth: true
                    SplitView.fillHeight: true
                    SplitView.minimumHeight: 160
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    // The 4 px between rows is inside each row.
                    spacing: 0
                    model: backend.selects
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 4 }
                    delegate: LineRow {
                        readonly property var overlayInfo: root.rowOverlay(modelData)
                        timeText: root.clockOf(modelData)
                        reasonText: root.reasonText(modelData.reason)
                        coverText: root.coverTextFor(overlayInfo)
                        coverStill: root.coverStillFor(overlayInfo)
                        secondCamera: overlayInfo !== null && overlayInfo.kind === "angle"
                        selected: host.viewStep === "lines" && index === host.currentLine
                        marked: host.viewStep === "movie" && index === root.playheadIndex
                        onPicked: {
                            host.currentLine = index
                            host.showLine(modelData)
                        }
                        onPlayRequested: host.playLine(modelData)
                    }
                }

                ReviseChat {
                    id: reviseChat
                    SplitView.fillWidth: true
                    SplitView.preferredHeight: 240
                    SplitView.minimumHeight: 140
                    host: root.host
                    onApplied: (changed, fromStep) => {
                        lineList.contentY = 0
                        if (!changed || fromStep !== "movie")
                            return
                        host.shotsPinned = false
                        if (host.hasVideo)
                            backend.showShots()
                    }
                }
            }
        }

        Label {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: qsTr("One file, trimmed by hand.")
            color: theme.foreground
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }
    }

    Connections {
        target: host
        function onCurrentLineChanged() {
            if (host.currentLine >= 0)
                lineList.positionViewAtIndex(host.currentLine, ListView.Contain)
        }
    }
}
