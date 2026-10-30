import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var host
    property var film

    function pacePhrase(pace) {
        if (pace === "measured")
            return qsTr("Measured \u00B7 natural pauses")
        if (pace === "tight")
            return qsTr("Tight \u00B7 trims most pauses")
        if (pace === "frenzied")
            return qsTr("Frenzied \u00B7 cuts every breath")
        return qsTr("Open \u00B7 keeps long pauses")
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
    function movieClock() {
        var seconds = host.hasVideo ? host.timeline.keptDuration : host.keptSpan()
        return host.lineClock(seconds)
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
    readonly property string lastNote: {
        var notes = backend.reviseNotes
        if (!notes || notes.length === 0)
            return ""
        return String(notes[notes.length - 1])
    }

    function pickShots() {
        host.shotsPinned = true
        if (host.hasVideo)
            backend.showShots()
    }
    function pickLines() {
        if (backend.selects.length === 0)
            return
        host.shotsPinned = false
        if (host.hasVideo)
            backend.showShots()
    }
    function pickMovie() {
        if (!host.hasVideo)
            return
        backend.showMovie()
    }
    function sendNote() {
        var note = reviseInput.text.replace(/\s+/g, " ").trim()
        if (note === "" || backend.busy)
            return
        if (backend.sendRevise(note))
            reviseInput.text = ""
    }

    component StepTab: Item {
        id: step
        property string label
        property bool current: false
        property bool reached: false
        signal picked()
        width: stepLabel.implicitWidth + 4
        height: 36
        opacity: current ? 1 : (reached ? 0.62 : 0.38)
        Label {
            id: stepLabel
            anchors.bottom: underline.top
            anchors.bottomMargin: 4
            anchors.horizontalCenter: parent.horizontalCenter
            text: step.label
            color: theme.foreground
            font.pixelSize: 13
            font.weight: step.current ? Font.DemiBold : Font.Normal
        }
        Rectangle {
            id: underline
            visible: step.current
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            width: stepLabel.implicitWidth
            height: 2
            color: theme.accent
        }
        MouseArea {
            anchors.fill: parent
            enabled: step.reached
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: step.picked()
        }
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
        opacity: enabled ? 1 : 0.45
        HoverHandler { id: recentHover; enabled: recent.enabled }
        Label {
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.right: sideText.visible ? sideText.left : parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: recent.title
            color: theme.foreground
            opacity: 0.62
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

    ColumnLayout {
        id: paneColumn
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        anchors.topMargin: 8
        anchors.bottomMargin: 8
        spacing: 8

        Row {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            spacing: 16
            StepTab {
                objectName: "shotsStep"
                label: backend.tray.length > 0 ? qsTr("Shots %1").arg(backend.tray.length) : qsTr("Shots")
                reached: true
                current: host.viewStep === "shots"
                onPicked: root.pickShots()
            }
            StepTab {
                objectName: "linesStep"
                label: backend.selects.length > 0
                       ? qsTr("Lines %1 of %2").arg(host.keptLineCount()).arg(backend.selects.length)
                       : qsTr("Lines")
                reached: backend.selects.length > 0
                current: host.viewStep === "lines"
                onPicked: root.pickLines()
            }
            StepTab {
                objectName: "movieStep"
                label: qsTr("Movie %1").arg(root.movieClock())
                reached: host.hasVideo
                current: host.viewStep === "movie"
                onPicked: root.pickMovie()
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
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
                                      ? modelData.name + " \u2014 " + qsTr("Movie, with its list")
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
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                Rectangle {
                    visible: backend.cutMode === "speech"
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? 36 : 0
                    radius: theme.radius
                    color: theme.surface
                    border.width: planIntent.activeFocus ? 1 : 0
                    border.color: theme.accent
                    opacity: planIntent.enabled ? 1 : 0.45
                    TextInput {
                        id: planIntent
                        z: 1
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        verticalAlignment: Text.AlignVCenter
                        clip: true
                        color: theme.foreground
                        font.pixelSize: 13
                        selectByMouse: true
                        enabled: !backend.busy
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
                    }
                    Label {
                        anchors.fill: planIntent
                        visible: planIntent.text === ""
                        text: qsTr("What is this movie? One sentence.")
                        color: theme.foreground
                        opacity: 0.38
                        font.pixelSize: 13
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                }

                Column {
                    Layout.fillWidth: true
                    spacing: 4
                    Item {
                        id: paceBox
                        width: parent.width
                        height: paceClosed.implicitHeight + 8
                        enabled: !backend.busy
                        onEnabledChanged: {
                            if (!enabled)
                                paceBox.open = false
                        }
                        property bool open: false
                        Label {
                            id: paceClosed
                            anchors.verticalCenter: parent.verticalCenter
                            text: root.pacePhrase(backend.pace)
                            color: theme.foreground
                            opacity: paceBox.enabled ? 0.62 : 0.38
                            font.pixelSize: 13
                        }
                        MouseArea {
                            anchors.fill: parent
                            enabled: paceBox.enabled
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: {
                                if (backend.busy)
                                    return
                                paceBox.open = !paceBox.open
                            }
                        }
                    }
                    Column {
                        width: parent.width
                        visible: paceBox.open && paceBox.enabled
                        spacing: 4
                        Repeater {
                            model: [
                                { pace: "open", label: qsTr("Open \u00B7 keeps long pauses") },
                                { pace: "measured", label: qsTr("Measured \u00B7 natural pauses") },
                                { pace: "tight", label: qsTr("Tight \u00B7 trims most pauses") },
                                { pace: "frenzied", label: qsTr("Frenzied \u00B7 cuts every breath") }
                            ]
                            delegate: Label {
                                required property var modelData
                                text: modelData.label
                                color: backend.pace === modelData.pace ? theme.accent : theme.foreground
                                opacity: backend.pace === modelData.pace ? 1 : 0.62
                                font.pixelSize: 13
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: !backend.busy
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: {
                                        if (backend.busy)
                                            return
                                        backend.pace = modelData.pace
                                        paceBox.open = false
                                    }
                                }
                            }
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

                Column {
                    Layout.fillWidth: true
                    spacing: 4
                    Row {
                        spacing: 8
                        ActionButton {
                            text: qsTr("Add shots…")
                            enabled: !backend.busy
                            onClicked: backend.addVideosDialog()
                        }
                        ActionButton {
                            text: qsTr("Add a title card…")
                            enabled: !backend.busy
                            onClicked: host.openTitleCard()
                        }
                    }
                    Row {
                        spacing: 8
                        ActionButton {
                            text: qsTr("Open a saved list…")
                            enabled: !backend.busy
                            onClicked: backend.openCutListDialog()
                        }
                        ActionButton {
                            text: qsTr("Save list…")
                            enabled: backend.tray.length > 0
                            onClicked: backend.saveCutListDialog()
                        }
                    }
                }
            }

            ColumnLayout {
                id: linesColumn
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                Item {
                    id: reviseBlock
                    visible: host.viewStep === "lines"
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? reviseCol.implicitHeight : 0
                    Column {
                        id: reviseCol
                        width: parent.width
                        spacing: 8
                        Item {
                            id: reviseRow
                            width: parent.width
                            height: 36
                            Label {
                                id: reviseLabel
                                anchors.verticalCenter: parent.verticalCenter
                                text: qsTr("Change this cut")
                                color: theme.foreground
                                font.pixelSize: 13
                            }
                            Rectangle {
                                anchors.left: reviseInput.left
                                anchors.right: reviseInput.right
                                anchors.verticalCenter: parent.verticalCenter
                                height: 36
                                radius: theme.radius
                                color: theme.surface
                                border.width: reviseInput.activeFocus ? 1 : 0
                                border.color: theme.accent
                                opacity: reviseInput.enabled ? 1 : 0.45
                            }
                            TextInput {
                                id: reviseInput
                                z: 1
                                anchors.left: reviseLabel.right
                                anchors.leftMargin: 12
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                height: 36
                                leftPadding: 8
                                rightPadding: 8
                                verticalAlignment: Text.AlignVCenter
                                color: theme.foreground
                                font.pixelSize: 13
                                clip: true
                                selectByMouse: true
                                enabled: !backend.busy
                                onAccepted: root.sendNote()
                            }
                            Label {
                                anchors.fill: reviseInput
                                anchors.leftMargin: reviseInput.leftPadding
                                anchors.rightMargin: reviseInput.rightPadding
                                visible: reviseInput.text === ""
                                text: qsTr("Tell BotCut what to change, like \"drop the pricing part\"")
                                color: theme.foreground
                                opacity: 0.38
                                font.pixelSize: 13
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                            }
                        }
                        Row {
                            width: parent.width
                            spacing: 12
                            visible: root.lastNote !== "" || backend.canRevert
                            Label {
                                visible: root.lastNote !== ""
                                width: Math.min(implicitWidth, Math.max(0, parent.width - undoChange.width - 12))
                                text: root.lastNote
                                color: theme.foreground
                                opacity: 0.62
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                            Label {
                                id: undoChange
                                visible: backend.canRevert
                                text: qsTr("Undo this change")
                                color: theme.foreground
                                font.pixelSize: 13
                                enabled: !backend.busy
                                opacity: enabled ? 1 : 0.45
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: parent.enabled
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: backend.revertRevise()
                                }
                            }
                        }
                    }
                }

                ListView {
                    id: lineList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    spacing: 4
                    model: backend.selects
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 4 }
                    delegate: LineRow {
                        timeText: root.clockOf(modelData)
                        reasonText: root.reasonText(modelData.reason)
                        coverText: root.coverText(modelData)
                        selected: host.viewStep === "lines" && index === host.currentLine
                        marked: host.viewStep === "movie" && index === root.playheadIndex
                        onPicked: host.currentLine = index
                        onPlayRequested: host.playLine(modelData)
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

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            Item {
                objectName: "settingsButton"
                Layout.preferredWidth: settingsText.implicitWidth + 8
                Layout.fillHeight: true
                Label {
                    id: settingsText
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Settings")
                    color: theme.foreground
                    opacity: 0.62
                    font.pixelSize: 13
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (host.settingsOpen)
                            host.closeSettings()
                        else
                            host.openSettings()
                    }
                }
            }
            Item { Layout.fillWidth: true }
            Item {
                Layout.preferredWidth: 32
                Layout.fillHeight: true
                Label {
                    anchors.centerIn: parent
                    text: "?"
                    color: theme.foreground
                    opacity: 0.62
                    font.pixelSize: 16
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: host.helpVisible = !host.helpVisible
                }
            }
        }
    }

    Connections {
        target: backend
        function onIntentChanged() {
            if (planIntent.text !== backend.intent)
                planIntent.text = backend.intent
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
