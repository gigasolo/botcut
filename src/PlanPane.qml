import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The left column. The recents on the empty home, the shot list on Shots, and
// on Lines and Movie the line list: a heading, one sentence, a search field,
// the filters, every line, and the chat at the bottom. The step control and
// the decisions live elsewhere now; the keys the pace list swallows are still
// read through here.
Item {
    id: root
    property var host
    property var film
    // The inspector holds the one pace field in the window.
    property var decisions

    readonly property bool paceOpen: decisions ? decisions.paceOpen : false
    readonly property bool paceKeys: decisions ? decisions.paceKeys : false
    function closePace() {
        if (decisions)
            decisions.closePace()
    }
    function undoRevise() {
        reviseChat.undo()
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
    function coverText(line) {
        var rows = backend.covers
        var files = backend.cutClips
        if (!line || !rows || !files)
            return ""
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].line != line.id)
                continue
            var clip = rows[i].clip
            if (clip < 0 || clip >= files.length)
                return ""
            var path = String(files[clip])
            var slash = path.lastIndexOf("/")
            var name = slash < 0 ? path : path.substring(slash + 1)
            return qsTr("B-roll: %1").arg(name)
        }
        return ""
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
        if (!row || row.text === undefined || row.text === null)
            return -1
        var words = String(row.text).trim()
        if (words === "")
            return -1
        var selects = backend.selects
        for (var i = 0; i < selects.length; i++) {
            var text = selects[i].text
            if (text !== undefined && text !== null && String(text).trim() === words)
                return i
        }
        return -1
    }

    // The filter and the search only hide rows. Keep never changes here, and
    // the model is never asked.
    readonly property string lineFilter: host ? host.lineFilter : "all"
    readonly property string searchWords: searchField.text.replace(/\s+/g, " ").trim().toLowerCase()
    function rowShown(line) {
        if (!line)
            return false
        var filter = lineFilter
        if (filter === "kept" && line.keep === false)
            return false
        if (filter === "dropped" && line.keep !== false)
            return false
        if (filter === "unsure" && line.reason !== "unique?")
            return false
        if (searchWords !== "") {
            var words = line.text === undefined || line.text === null ? "" : String(line.text)
            if (words.toLowerCase().indexOf(searchWords) < 0)
                return false
        }
        return true
    }
    readonly property int shownCount: {
        var n = 0
        var lines = backend.selects
        for (var i = 0; i < lines.length; i++) {
            if (rowShown(lines[i]))
                n++
        }
        return n
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

    // One filter over the rows: its word, a dot for the state it means, and
    // its count as a monospace label. The current filter is the filled one.
    component FilterChip: Rectangle {
        id: chip
        property string key
        property string label
        property int count: 0
        property bool dotted: false
        property color dot: theme.accent
        property real dotOpacity: 1
        readonly property bool current: root.lineFilter === key
        width: chipRow.implicitWidth + 20
        height: 28
        radius: theme.radius
        color: current ? theme.raised : (chipHover.hovered ? theme.hover : "transparent")
        HoverHandler { id: chipHover }
        Row {
            id: chipRow
            anchors.centerIn: parent
            spacing: 6
            Rectangle {
                visible: chip.dotted
                anchors.verticalCenter: parent.verticalCenter
                width: 6
                height: 6
                radius: 3
                color: chip.dot
                opacity: chip.dotOpacity
            }
            Label {
                anchors.verticalCenter: parent.verticalCenter
                text: chip.label
                color: theme.foreground
                opacity: chip.current ? 1 : 0.62
                font.pixelSize: 12
            }
            Label {
                anchors.verticalCenter: parent.verticalCenter
                text: chip.count
                color: theme.foreground
                opacity: chip.current ? 0.62 : 0.38
                font.pixelSize: 11
                font.family: "monospace"
            }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                if (host)
                    host.lineFilter = chip.key
            }
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
                text: qsTr("Your shots will be listed here.")
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
                Layout.bottomMargin: 4
                text: qsTr("Shots")
                color: theme.foreground
                font.pixelSize: 15
                font.weight: Font.DemiBold
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
                    leftPadding: 10
                    rightPadding: 10
                    text: qsTr("Add shots…")
                    enabled: !backend.busy
                    onClicked: backend.addVideosDialog()
                }
                ActionButton {
                    leftPadding: 10
                    rightPadding: 10
                    text: qsTr("Add a title card…")
                    enabled: !backend.busy
                    onClicked: host.openTitleCard()
                }
                ActionButton {
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
                text: qsTr("Lines")
                color: theme.foreground
                font.pixelSize: 15
                font.weight: Font.DemiBold
            }
            Label {
                Layout.fillWidth: true
                Layout.topMargin: 2
                text: qsTr("BotCut picked these. Flip any line to keep or drop it.")
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            // Search hides rows whose words do not match. Empty shows the filter.
            Rectangle {
                Layout.fillWidth: true
                Layout.topMargin: 12
                Layout.preferredHeight: 32
                radius: theme.radius
                color: theme.raised
                border.width: searchField.activeFocus ? 1 : 0
                border.color: theme.accent
                TextInput {
                    id: searchField
                    anchors.fill: parent
                    leftPadding: 12
                    rightPadding: 12
                    verticalAlignment: Text.AlignVCenter
                    clip: true
                    color: theme.foreground
                    font.pixelSize: 13
                    selectByMouse: true
                    // The window shortcut sees ShortcutOverride first. Claim Escape
                    // only while nothing else wants it, then the handler below runs.
                    Keys.onShortcutOverride: (event) => {
                        if (event.key !== Qt.Key_Escape || root.paceOpen || (host && host.dialogUp))
                            return
                        event.accepted = true
                    }
                    Keys.onEscapePressed: (event) => {
                        if (text === "") {
                            focus = false
                        } else {
                            text = ""
                        }
                        event.accepted = true
                    }
                }
                Label {
                    anchors.fill: searchField
                    anchors.leftMargin: searchField.leftPadding
                    anchors.rightMargin: searchField.rightPadding
                    visible: searchField.text === ""
                    text: qsTr("Search lines")
                    color: theme.foreground
                    opacity: 0.38
                    font.pixelSize: 13
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }

            Flow {
                Layout.fillWidth: true
                Layout.topMargin: 8
                spacing: 6
                FilterChip {
                    key: "all"
                    label: qsTr("All")
                    count: backend.selects.length
                }
                FilterChip {
                    key: "kept"
                    label: qsTr("Kept")
                    count: decisions.keptCount
                    dotted: true
                    dot: theme.accent
                }
                FilterChip {
                    key: "dropped"
                    label: qsTr("Dropped")
                    count: decisions.droppedCount
                    dotted: true
                    dot: theme.foreground
                    dotOpacity: 0.38
                }
                FilterChip {
                    key: "unsure"
                    label: qsTr("Unsure")
                    count: decisions.unsureCount
                    dotted: true
                    dot: theme.accent
                    dotOpacity: 0.38
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.topMargin: 12
                Layout.preferredHeight: 1
                color: theme.line
            }

            ListView {
                id: lineList
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.topMargin: 8
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                // A hidden row is 0 px tall. The 4 px between rows is inside each row.
                spacing: 0
                model: backend.selects
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 4 }
                delegate: LineRow {
                    timeText: root.clockOf(modelData)
                    reasonText: root.reasonText(modelData.reason)
                    coverText: root.coverText(modelData)
                    shown: root.rowShown(modelData)
                    selected: host.viewStep === "lines" && index === host.currentLine
                    marked: host.viewStep === "movie" && index === root.playheadIndex
                    onPicked: {
                        host.currentLine = index
                        host.showLine(modelData)
                    }
                    onPlayRequested: host.playLine(modelData)
                }
                Label {
                    visible: backend.selects.length > 0 && root.shownCount === 0
                    anchors.top: parent.top
                    anchors.topMargin: 8
                    width: parent.width
                    text: root.searchWords !== "" ? qsTr("No line says that.") : qsTr("No lines here.")
                    color: theme.foreground
                    opacity: 0.38
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }

            ReviseChat {
                id: reviseChat
                Layout.fillWidth: true
                Layout.topMargin: 8
                Layout.preferredHeight: implicitHeight
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
