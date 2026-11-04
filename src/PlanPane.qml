import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var host
    property var film

    function pacePhrase(pace) {
        if (pace === "measured")
            return qsTr("Measured · natural pauses")
        if (pace === "tight")
            return qsTr("Tight · trims most pauses")
        if (pace === "frenzied")
            return qsTr("Frenzied · cuts every breath")
        return qsTr("Open · keeps long pauses")
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
    readonly property bool paceOpen: paceBox.open
    readonly property bool paceKeys: paceOpen || paceClosed.activeFocus
    function closePace() {
        paceBox.open = false
    }
    // Lines, and Shots for a speech cut once a shot is in. Hidden while the
    // movie is the plan and on the empty home. Item.visible is effective, so
    // the slot binds this rule and never its own visible.
    readonly property bool paceShown: {
        if (!host || host.viewStep === "movie")
            return false
        if (host.viewStep === "lines")
            return true
        return backend.tray.length > 0 && backend.cutMode === "speech"
    }
    // A hidden list would leave paceKeys true, and Space would stay swallowed.
    // Layout ignores an invisible item, so clear the height it already gave the slot.
    onPaceShownChanged: {
        if (paceShown)
            return
        closePace()
        paceSlot.height = 0
    }
    readonly property string shotsFullLabel: backend.tray.length > 0
            ? qsTr("Shots %1").arg(backend.tray.length) : qsTr("Shots")
    readonly property string linesFullLabel: backend.selects.length > 0
            ? qsTr("Lines %1 of %2").arg(host.keptLineCount()).arg(backend.selects.length)
            : qsTr("Lines")
    readonly property string linesShortLabel: backend.selects.length > 0
            ? qsTr("Lines %1").arg(host.keptLineCount()) : qsTr("Lines")
    readonly property string movieFullLabel: qsTr("Movie %1").arg(movieClock())
    // Each segment is its word plus 8 px each side. The control pads 2 px around
    // its segments and 2 px between them. Lists adds its word, 4 px each side,
    // and the 8 px gap before the control.
    function stepRowWidth(shortLines, shortShots) {
        var w = 8
        w += (shortShots ? shotsShortMetrics.width : shotsFullMetrics.width) + 16
        w += (shortLines ? linesShortMetrics.width : linesFullMetrics.width) + 16
        w += movieMetrics.width + 16
        if (homeLink.visible)
            w += homeText.implicitWidth + 16
        return w
    }
    readonly property real stepRoom: paneColumn.width - 24
    readonly property bool linesNeedShort: stepRowWidth(false, false) > stepRoom
    readonly property bool shotsNeedShort: linesNeedShort && stepRowWidth(true, false) > stepRoom

    TextMetrics {
        id: shotsFullMetrics
        font.pixelSize: 13
        font.weight: Font.DemiBold
        text: root.shotsFullLabel
    }
    TextMetrics {
        id: shotsShortMetrics
        font.pixelSize: 13
        font.weight: Font.DemiBold
        text: qsTr("Shots")
    }
    TextMetrics {
        id: linesFullMetrics
        font.pixelSize: 13
        font.weight: Font.DemiBold
        text: root.linesFullLabel
    }
    TextMetrics {
        id: linesShortMetrics
        font.pixelSize: 13
        font.weight: Font.DemiBold
        text: root.linesShortLabel
    }
    TextMetrics {
        id: movieMetrics
        font.pixelSize: 13
        font.weight: Font.DemiBold
        text: root.movieFullLabel
    }

    // One step of the segmented control. The current step is the filled one,
    // a reached step is quiet, and a step not yet reached is quieter still.
    component Segment: Rectangle {
        id: step
        property string label
        property bool current: false
        property bool reached: false
        signal picked()
        Layout.fillWidth: true
        Layout.minimumWidth: implicitWidth
        implicitWidth: stepLabel.implicitWidth + 16
        implicitHeight: 28
        radius: Math.max(0, theme.radius - 2)
        color: current ? theme.raised : (stepHover.hovered && reached ? theme.hover : "transparent")
        HoverHandler { id: stepHover; enabled: step.reached && !step.current }
        Label {
            id: stepLabel
            anchors.centerIn: parent
            text: step.label
            color: theme.foreground
            opacity: step.current ? 1 : (step.reached ? 0.62 : 0.38)
            font.pixelSize: 13
            font.weight: step.current ? Font.DemiBold : Font.Normal
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

    ColumnLayout {
        id: paneColumn
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        anchors.topMargin: 12
        anchors.bottomMargin: 12
        spacing: 12

        // The rail card: the way home, the step, and the decisions for this
        // step. The lists scroll under it.
        Rectangle {
            id: railCard
            Layout.fillWidth: true
            Layout.preferredHeight: cardColumn.implicitHeight + 24
            radius: theme.radius
            color: theme.surface
            border.width: 1
            border.color: theme.line

            ColumnLayout {
                id: cardColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 12
                spacing: 12

                RowLayout {
                    id: stepRow
                    Layout.fillWidth: true
                    spacing: 8

                    // The way back to the home of the plan. Only the window closes, not the files.
                    Item {
                        id: homeLink
                        objectName: "listsHome"
                        visible: backend.tray.length > 0 || host.hasVideo
                        enabled: !backend.busy
                        Layout.preferredWidth: homeText.implicitWidth + 8
                        Layout.minimumWidth: Layout.preferredWidth
                        Layout.preferredHeight: 32
                        Layout.alignment: Qt.AlignVCenter
                        Rectangle {
                            anchors.fill: parent
                            radius: Math.max(0, theme.radius - 2)
                            color: theme.hover
                            visible: homeHover.hovered && homeLink.enabled
                        }
                        HoverHandler { id: homeHover; enabled: homeLink.enabled }
                        Label {
                            id: homeText
                            anchors.centerIn: parent
                            text: qsTr("Lists")
                            color: theme.foreground
                            opacity: homeLink.enabled ? 0.62 : 0.38
                            font.pixelSize: 13
                        }
                        MouseArea {
                            anchors.fill: parent
                            enabled: homeLink.enabled
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: host.closeProject()
                        }
                    }

                    // Shots, Lines, and Movie as one segmented control. Words only.
                    Rectangle {
                        id: stepControl
                        Layout.fillWidth: true
                        Layout.preferredHeight: 32
                        Layout.minimumHeight: 32
                        radius: theme.radius
                        color: theme.background

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 2
                            spacing: 2
                            Segment {
                                objectName: "shotsStep"
                                label: root.shotsNeedShort ? qsTr("Shots") : root.shotsFullLabel
                                reached: true
                                current: host.viewStep === "shots"
                                onPicked: root.pickShots()
                            }
                            Segment {
                                objectName: "linesStep"
                                label: root.linesNeedShort ? root.linesShortLabel : root.linesFullLabel
                                reached: backend.selects.length > 0
                                current: host.viewStep === "lines"
                                onPicked: root.pickLines()
                            }
                            Segment {
                                objectName: "movieStep"
                                label: root.movieFullLabel
                                reached: host.hasVideo
                                current: host.viewStep === "movie"
                                onPicked: root.pickMovie()
                            }
                        }
                    }
                }

                // What this movie is, while spoken cuts choose the lines.
                Rectangle {
                    visible: host.viewStep === "shots" && backend.tray.length > 0
                             && backend.cutMode === "speech"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    radius: theme.radius
                    color: theme.raised
                    border.width: planIntent.activeFocus ? 1 : 0
                    border.color: theme.accent
                    TextInput {
                        id: planIntent
                        z: 1
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        verticalAlignment: Text.AlignVCenter
                        clip: true
                        color: theme.foreground
                        opacity: enabled ? 1 : 0.38
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

                // Pace and Fade: a name, one sentence, and the control. One
                // field serves Shots and Lines, so it keeps one open state.
                Item {
                    id: paceSlot
                    visible: root.paceShown
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.paceShown ? paceFade.implicitHeight : 0

                    ColumnLayout {
                        id: paceFade
                        width: parent ? parent.width : 0
                        height: implicitHeight
                        spacing: 12

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0

                            Label {
                                Layout.fillWidth: true
                                text: qsTr("Pace")
                                color: theme.foreground
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 2
                                Layout.minimumHeight: 2
                                Layout.maximumHeight: 2
                            }
                            Label {
                                Layout.fillWidth: true
                                text: qsTr("How much air to leave between lines.")
                                color: theme.foreground
                                opacity: 0.62
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                            }
                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 6
                                Layout.minimumHeight: 6
                                Layout.maximumHeight: 6
                            }

                            Item {
                                id: paceBox
                                objectName: "paceField"
                                property bool open: false
                                Layout.fillWidth: true
                                implicitHeight: 36 + (open ? paceMenu.height : 0)
                                Layout.preferredHeight: implicitHeight
                                onOpenChanged: {
                                    if (!open)
                                        return
                                    var at = paceMenu.paces.indexOf(backend.pace)
                                    paceMenu.cursor = at < 0 ? 0 : at
                                    paceMenu.forceActiveFocus()
                                }

                                Rectangle {
                                    id: paceClosed
                                    width: parent.width
                                    height: 36
                                    radius: theme.radius
                                    color: paceHover.hovered && !backend.busy ? theme.hover : theme.raised
                                    border.width: paceBox.open || activeFocus ? 1 : 0
                                    border.color: theme.accent
                                    activeFocusOnTab: true
                                    HoverHandler { id: paceHover; enabled: !backend.busy }
                                    Label {
                                        id: paceClosedText
                                        anchors.fill: parent
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 12
                                        verticalAlignment: Text.AlignVCenter
                                        text: root.pacePhrase(backend.pace)
                                        color: theme.foreground
                                        opacity: backend.busy ? 0.38 : 1
                                        font.pixelSize: 13
                                        elide: Text.ElideRight
                                        enabled: !backend.busy
                                    }
                                    MouseArea {
                                        objectName: "paceHit"
                                        anchors.fill: parent
                                        enabled: !backend.busy
                                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                        onClicked: {
                                            paceClosed.forceActiveFocus()
                                            paceBox.open = !paceBox.open
                                        }
                                    }
                                    Keys.onPressed: (event) => {
                                        if (backend.busy || paceBox.open)
                                            return
                                        if (event.key === Qt.Key_Space || event.key === Qt.Key_Return
                                                || event.key === Qt.Key_Enter) {
                                            paceBox.open = true
                                            event.accepted = true
                                        }
                                    }
                                }

                                Rectangle {
                                    id: paceMenu
                                    y: 36
                                    visible: paceBox.open
                                    width: parent.width
                                    height: paceRows.implicitHeight
                                    radius: theme.radius
                                    color: theme.raised
                                    focus: true
                                    property int cursor: 0
                                    property var paces: ["open", "measured", "tight", "frenzied"]
                                    function pick() {
                                        backend.pace = paces[cursor]
                                        paceBox.open = false
                                    }
                                    Column {
                                        id: paceRows
                                        width: parent.width
                                        Repeater {
                                            model: paceMenu.paces
                                            delegate: Rectangle {
                                                required property string modelData
                                                required property int index
                                                width: parent.width
                                                height: 32
                                                color: paceRowHover.hovered ? theme.hover : "transparent"
                                                HoverHandler { id: paceRowHover }
                                                Label {
                                                    anchors.left: parent.left
                                                    anchors.leftMargin: 12
                                                    anchors.right: parent.right
                                                    anchors.rightMargin: 12
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    text: root.pacePhrase(modelData)
                                                    color: index === paceMenu.cursor ? theme.accent : theme.foreground
                                                    font.pixelSize: 13
                                                    elide: Text.ElideRight
                                                }
                                                MouseArea {
                                                    anchors.fill: parent
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: {
                                                        backend.pace = modelData
                                                        paceBox.open = false
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    Keys.onUpPressed: (event) => {
                                        cursor = Math.max(0, cursor - 1)
                                        event.accepted = true
                                    }
                                    Keys.onDownPressed: (event) => {
                                        cursor = Math.min(paces.length - 1, cursor + 1)
                                        event.accepted = true
                                    }
                                    Keys.onReturnPressed: (event) => { pick(); event.accepted = true }
                                    Keys.onEnterPressed: (event) => { pick(); event.accepted = true }
                                    Keys.onEscapePressed: (event) => {
                                        paceBox.open = false
                                        event.accepted = true
                                    }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignVCenter
                                spacing: 0
                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("Fade")
                                    color: theme.foreground
                                    font.pixelSize: 13
                                    font.weight: Font.DemiBold
                                }
                                Item {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 2
                                    Layout.minimumHeight: 2
                                    Layout.maximumHeight: 2
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("A short fade between shots.")
                                    color: theme.foreground
                                    opacity: 0.62
                                    font.pixelSize: 12
                                    wrapMode: Text.WordWrap
                                }
                            }
                            Switch {
                                id: planFadeSwitch
                                objectName: "planFadeSwitch"
                                focusPolicy: Qt.NoFocus
                                Layout.alignment: Qt.AlignVCenter
                                enabled: !backend.busy
                                opacity: backend.busy ? 0.38 : 1
                                checked: backend.sceneTransition === "dip"
                                onClicked: backend.sceneTransition = checked ? "dip" : "off"
                            }
                        }
                    }
                }
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
                Row {
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
                spacing: 8

                ListView {
                    id: lineList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    spacing: 4
                    model: backend.selects
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 4 }
                    header: Column {
                        width: lineList.width
                        spacing: 0
                        Label {
                            text: qsTr("This movie")
                            color: theme.foreground
                            opacity: 0.38
                            font.pixelSize: 12
                        }
                        Label {
                            visible: backend.intent !== ""
                            width: parent.width
                            topPadding: 4
                            text: backend.intent
                            color: theme.foreground
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                        }
                        Item { width: 1; height: 8 }
                        Rectangle {
                            width: parent.width
                            height: 1
                            color: theme.raised
                        }
                        Item { width: 1; height: 8 }
                    }
                    delegate: LineRow {
                        timeText: root.clockOf(modelData)
                        reasonText: root.reasonText(modelData.reason)
                        coverText: root.coverText(modelData)
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
                    Layout.fillWidth: true
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
    }

    Connections {
        target: backend
        function onIntentChanged() {
            if (planIntent.text !== backend.intent)
                planIntent.text = backend.intent
        }
        function onBusyChanged() {
            if (backend.busy)
                paceBox.open = false
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
