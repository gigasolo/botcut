import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The decisions for this movie: the sentence, pace, fade, cover shots, and the
// result. A third column from 1280 px wide, and three short columns under the
// picture below that. There is one pace field and one fade switch in the
// window, whatever the width, so they live here and nowhere else.
Item {
    id: root
    property var host
    property bool wide: false

    implicitWidth: 280
    implicitHeight: grid.implicitHeight + (wide ? 32 : 0)

    readonly property color accentColor: theme.accent

    function pacePhrase(pace) {
        if (pace === "measured")
            return qsTr("Measured · natural pauses")
        if (pace === "tight")
            return qsTr("Tight · trims most pauses")
        if (pace === "frenzied")
            return qsTr("Frenzied · cuts every breath")
        return qsTr("Open · keeps long pauses")
    }

    readonly property bool paceOpen: paceBox.open
    readonly property bool paceKeys: paceOpen || paceClosed.activeFocus
    function closePace() {
        paceBox.open = false
    }

    // The sentence shows while spoken cuts choose the lines: on Shots once a
    // shot is in, and wherever a line list exists.
    readonly property bool movieShown: backend.cutMode === "speech"
                                       && (backend.tray.length > 0 || backend.selects.length > 0)
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
    readonly property bool resultShown: backend.selects.length > 0
    readonly property bool hasContent: movieShown || paceShown || resultShown

    readonly property int keptCount: host ? host.keptLineCount() : 0
    readonly property int droppedCount: Math.max(0, backend.selects.length - keptCount)
    readonly property int unsureCount: {
        var n = 0
        var lines = backend.selects
        for (var i = 0; i < lines.length; i++) {
            if (lines[i] && lines[i].reason === "unique?")
                n++
        }
        return n
    }

    // One section's name. Small capitals at 62 percent, so the controls under it read first.
    component SectionHeading: Label {
        Layout.fillWidth: true
        color: theme.foreground
        opacity: 0.62
        font.pixelSize: 12
        font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 1
        elide: Text.ElideRight
    }

    // A count of lines. The number is its own monospace label.
    component CountTile: Rectangle {
        id: tile
        property string title
        property int count: 0
        Layout.fillWidth: true
        Layout.preferredWidth: 100
        Layout.minimumWidth: 0
        implicitHeight: tileCol.implicitHeight + 16
        radius: theme.radius
        color: theme.raised
        Column {
            id: tileCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 8
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            spacing: 2
            Label {
                width: parent.width
                text: tile.title
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 11
                elide: Text.ElideRight
            }
            Row {
                spacing: 4
                Label {
                    id: tileCount
                    text: tile.count
                    color: theme.foreground
                    font.pixelSize: 15
                    font.family: "monospace"
                }
                Label {
                    anchors.verticalCenter: tileCount.verticalCenter
                    text: tile.count === 1 ? qsTr("line") : qsTr("lines")
                    color: theme.foreground
                    opacity: 0.62
                    font.pixelSize: 12
                }
            }
        }
    }

    Rectangle {
        visible: root.wide
        anchors.fill: parent
        color: theme.surface
        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 1
            color: theme.line
        }
    }

    Flickable {
        id: flick
        anchors.fill: parent
        anchors.leftMargin: root.wide ? 1 : 0
        contentWidth: width
        contentHeight: grid.implicitHeight + (root.wide ? 32 : 0)
        clip: root.wide
        interactive: root.wide && contentHeight > height
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {
            policy: root.wide ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
            width: 4
        }

        GridLayout {
            id: grid
            x: root.wide ? 16 : 0
            y: root.wide ? 16 : 0
            width: flick.width - (root.wide ? 32 : 0)
            columns: root.wide ? 1
                     : Math.max(1, (colA.visible ? 1 : 0) + (colB.visible ? 1 : 0) + (colC.visible ? 1 : 0))
            columnSpacing: 16
            rowSpacing: 16

            // The sentence, then pace and fade.
            ColumnLayout {
                id: colA
                visible: root.movieShown || root.paceShown
                Layout.fillWidth: true
                Layout.preferredWidth: 100
                Layout.minimumWidth: 0
                Layout.alignment: Qt.AlignTop
                spacing: 16

                ColumnLayout {
                    visible: root.movieShown
                    Layout.fillWidth: true
                    spacing: 8

                    SectionHeading { text: qsTr("This movie") }

                    // What this movie is. One sentence, edited in place.
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(36, planIntent.implicitHeight + 18)
                        radius: theme.radius
                        color: theme.raised
                        border.width: planIntent.activeFocus ? 1 : 0
                        border.color: theme.accent
                        TextEdit {
                            id: planIntent
                            z: 1
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            anchors.topMargin: 9
                            wrapMode: Text.WordWrap
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
                            // One sentence. Return leaves the field instead of adding a line.
                            Keys.onReturnPressed: (event) => {
                                focus = false
                                event.accepted = true
                            }
                            Keys.onEnterPressed: (event) => {
                                focus = false
                                event.accepted = true
                            }
                        }
                        Label {
                            anchors.fill: planIntent
                            visible: planIntent.text === ""
                            text: qsTr("What is this movie? One sentence.")
                            color: theme.foreground
                            opacity: 0.38
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                    }
                }

                // Pace and Fade: a name, one sentence, and the control.
                Item {
                    id: paceSlot
                    visible: root.paceShown
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.paceShown ? paceFade.implicitHeight : 0

                    ColumnLayout {
                        id: paceFade
                        width: parent ? parent.width : 0
                        height: implicitHeight
                        spacing: 16

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0

                            SectionHeading { text: qsTr("Pace") }
                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 4
                                Layout.minimumHeight: 4
                                Layout.maximumHeight: 4
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
                                Layout.preferredHeight: 8
                                Layout.minimumHeight: 8
                                Layout.maximumHeight: 8
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

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            SectionHeading { text: qsTr("Fade") }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 12

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                    spacing: 2
                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("Fade between shots")
                                        color: theme.foreground
                                        font.pixelSize: 13
                                        wrapMode: Text.WordWrap
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("A short fade to black between shots.")
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

            // Cover shots. The same two settings as in Settings, kept in step
            // by the bindings. The mix needs cover on.
            ColumnLayout {
                id: colB
                visible: root.paceShown
                Layout.fillWidth: true
                Layout.preferredWidth: 100
                Layout.minimumWidth: 0
                Layout.alignment: Qt.AlignTop
                spacing: 8

                SectionHeading { text: qsTr("Cover shots") }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 2
                        Label {
                            Layout.fillWidth: true
                            text: qsTr("Cover lines with other shots")
                            color: theme.foreground
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                        }
                        Label {
                            Layout.fillWidth: true
                            text: qsTr("Show another shot's picture while the voice goes on.")
                            color: theme.foreground
                            opacity: 0.62
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }
                    }
                    Switch {
                        focusPolicy: Qt.NoFocus
                        Layout.alignment: Qt.AlignVCenter
                        enabled: !backend.busy
                        opacity: backend.busy ? 0.38 : 1
                        checked: backend.broll
                        onClicked: backend.broll = checked
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    enabled: backend.broll && !backend.busy
                    CheckBox {
                        id: mixBox
                        focusPolicy: Qt.NoFocus
                        Layout.alignment: Qt.AlignVCenter
                        padding: 0
                        checked: backend.brollMix
                        onClicked: backend.brollMix = checked
                    }
                    Label {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        text: qsTr("Keep that shot's sound under the voice")
                        color: theme.foreground
                        opacity: mixBox.enabled ? 1 : 0.38
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                        MouseArea {
                            anchors.fill: parent
                            enabled: mixBox.enabled
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: {
                                mixBox.toggle()
                                backend.brollMix = mixBox.checked
                            }
                        }
                    }
                }
                Label {
                    visible: backend.tray.length < 2
                    Layout.fillWidth: true
                    text: qsTr("Needs two or more shots. This list has %1.").arg(backend.tray.length)
                    color: theme.foreground
                    opacity: 0.38
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }

            // The result: the kept sentence, its share, the counts, and the
            // two ways back into the list.
            ColumnLayout {
                id: colC
                visible: root.resultShown
                Layout.fillWidth: true
                Layout.preferredWidth: 100
                Layout.minimumWidth: 0
                Layout.alignment: Qt.AlignTop
                spacing: 8

                SectionHeading { text: qsTr("Result") }

                RowLayout {
                    id: pictureSentence
                    objectName: "pictureSentence"
                    Layout.fillWidth: true
                    spacing: 0

                    // Qt 6.12 StyledText ignores font face, so the clocks are their own items.
                    // No clock when any line lacks a start or an end. Files are never probed.
                    readonly property bool clocks: {
                        var lines = backend.selects
                        for (var i = 0; i < lines.length; i++) {
                            var line = lines[i]
                            var start = line ? Number(line.start) : NaN
                            var end = line ? Number(line.end) : NaN
                            if (!isFinite(start) || !isFinite(end))
                                return false
                        }
                        return true
                    }
                    readonly property real allSeconds: {
                        if (!clocks)
                            return 0
                        var total = 0
                        var lines = backend.selects
                        for (var i = 0; i < lines.length; i++) {
                            var line = lines[i]
                            total += Math.max(0, Number(line.end) - Number(line.start))
                        }
                        return total
                    }
                    readonly property real keptSeconds: host ? host.keptSpan() : 0
                    readonly property string lineWords: {
                        var n = root.keptCount
                        var count = n === 1 ? qsTr("1 line") : qsTr("%1 lines").arg(n)
                        return qsTr("%1, %2").arg(count).arg(backend.pace)
                    }

                    Label {
                        objectName: "keptClock"
                        visible: pictureSentence.clocks
                        text: host ? host.lineClock(pictureSentence.keptSeconds) : ""
                        color: theme.foreground
                        opacity: 0.62
                        font.pixelSize: 13
                        font.family: "monospace"
                    }
                    Label {
                        visible: pictureSentence.clocks
                        text: qsTr(" kept of ")
                        color: theme.foreground
                        opacity: 0.62
                        font.pixelSize: 13
                    }
                    Label {
                        objectName: "allClock"
                        visible: pictureSentence.clocks
                        text: host ? host.lineClock(pictureSentence.allSeconds) : ""
                        color: theme.foreground
                        opacity: 0.62
                        font.pixelSize: 13
                        font.family: "monospace"
                    }
                    Label {
                        objectName: "sentenceWords"
                        text: pictureSentence.clocks
                              ? qsTr(" – %1").arg(pictureSentence.lineWords)
                              : pictureSentence.lineWords
                        Layout.fillWidth: true
                        color: theme.foreground
                        opacity: 0.62
                        font.pixelSize: 13
                        elide: Text.ElideRight
                    }
                }

                // The kept share of every line, as a thin bar.
                Rectangle {
                    visible: pictureSentence.clocks && pictureSentence.allSeconds > 0
                    Layout.fillWidth: true
                    Layout.preferredHeight: 6
                    radius: 3
                    color: theme.background
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(1,
                                   pictureSentence.keptSeconds / Math.max(0.001, pictureSentence.allSeconds)))
                        height: parent.height
                        radius: 3
                        color: theme.accent
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    CountTile { title: qsTr("Kept"); count: root.keptCount }
                    CountTile { title: qsTr("Dropped"); count: root.droppedCount }
                }

                // Only sets the list's filter. Nothing about a line changes.
                Rectangle {
                    visible: root.unsureCount > 0
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32
                    radius: theme.radius
                    color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b,
                                   reviewHover.hovered ? 0.2 : 0.12)
                    border.width: 1
                    border.color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.4)
                    HoverHandler { id: reviewHover }
                    Label {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        text: root.unsureCount === 1 ? qsTr("Review 1 unsure line")
                                                     : qsTr("Review %1 unsure lines").arg(root.unsureCount)
                        color: theme.accent
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (host)
                                host.lineFilter = "unsure"
                        }
                    }
                }

                // The existing re-cut, behind its confirmation. Never while a job runs.
                ActionButton {
                    visible: host && host.gathering
                    Layout.fillWidth: true
                    text: qsTr("Cut again…")
                    enabled: !backend.busy && backend.tray.length > 0 && !backend.trayMissing
                    onClicked: host.confirmCutOpen = true
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
        function onBusyChanged() {
            if (backend.busy)
                paceBox.open = false
        }
    }
}
