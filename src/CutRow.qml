import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The decisions for this cut in one row under the picture: the movie sentence,
// the pace, and the fade. On Shots once a shot is in and spoken cuts are on,
// and on Lines. There is one pace field and one fade switch in the window.
Item {
    id: root
    property var host

    implicitHeight: 36

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
    // The keys the list and its field take: Space and Enter open the field,
    // and the arrows and Enter walk the open list.
    readonly property bool paceKeys: paceOpen || (paceClosed.activeFocus && paceClosed.visible)
    function closePace() {
        paceBox.open = false
    }

    // The sentence shows while spoken cuts choose the lines.
    readonly property bool movieShown: backend.cutMode === "speech"
                                       && (backend.tray.length > 0 || backend.selects.length > 0)
    // Lines, and Shots for a speech cut once a shot is in. Never on Movie.
    readonly property bool paceShown: {
        if (!host || host.viewStep === "movie")
            return false
        if (host.viewStep === "lines")
            return true
        return backend.tray.length > 0 && backend.cutMode === "speech"
    }
    // The row shows wherever the pace does. The sentence well only joins it
    // while spoken cuts choose the lines.
    readonly property bool hasContent: paceShown
    onPaceShownChanged: {
        if (!paceShown)
            closePace()
    }

    RowLayout {
        anchors.fill: parent
        spacing: 8

        // What this movie is. One sentence, edited in place.
        Rectangle {
            visible: root.movieShown
            Layout.fillWidth: true
            Layout.minimumWidth: 160
            Layout.preferredHeight: 36
            Layout.alignment: Qt.AlignVCenter
            radius: theme.radius
            color: theme.raised
            border.width: planIntent.activeFocus ? 1 : 0
            border.color: theme.accent
            clip: true
            TextInput {
                id: planIntent
                objectName: "intentField"
                anchors.fill: parent
                leftPadding: 12
                rightPadding: 12
                verticalAlignment: Text.AlignVCenter
                clip: true
                color: theme.foreground
                opacity: enabled ? 1 : 0.38
                font.pixelSize: 13
                selectByMouse: true
                enabled: !backend.busy
                Component.onCompleted: {
                    text = backend.intent
                    cursorPosition = 0
                }
                // Resting, the field shows the start of the sentence, not its end.
                onActiveFocusChanged: {
                    if (!activeFocus)
                        cursorPosition = 0
                }
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
                // One sentence. Return leaves the field.
                onAccepted: focus = false
            }
            Label {
                anchors.fill: planIntent
                anchors.leftMargin: planIntent.leftPadding
                anchors.rightMargin: planIntent.rightPadding
                visible: planIntent.text === ""
                text: qsTr("What is this movie? One sentence.")
                color: theme.foreground
                opacity: 0.38
                font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
        }

        Item { visible: !root.movieShown; Layout.fillWidth: true; Layout.preferredHeight: 1 }

        // The pace: a closed field, and its four sentences in a list above it.
        Item {
            id: paceBox
            objectName: "paceField"
            property bool open: false
            Layout.preferredWidth: paceWidth.width + 40
            Layout.minimumWidth: Layout.preferredWidth
            Layout.preferredHeight: 36
            Layout.alignment: Qt.AlignVCenter
            onOpenChanged: {
                if (!open) {
                    // Focus leaves the field with the list, so Space plays again.
                    if (paceClosed.activeFocus)
                        paceClosed.focus = false
                    return
                }
                var at = paceMenu.paces.indexOf(backend.pace)
                paceMenu.cursor = at < 0 ? 0 : at
                paceRows.forceActiveFocus()
            }
            TextMetrics {
                id: paceWidth
                font.pixelSize: 13
                text: qsTr("Frenzied \u00B7 cuts every breath")
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
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 28
                    verticalAlignment: Text.AlignVCenter
                    text: root.pacePhrase(backend.pace)
                    color: theme.foreground
                    opacity: backend.busy ? 0.38 : 1
                    font.pixelSize: 13
                    elide: Text.ElideRight
                    enabled: !backend.busy
                }
                Label {
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: "\u25BE"
                    color: theme.foreground
                    opacity: backend.busy ? 0.38 : 0.62
                    font.pixelSize: 13
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

            // The list hangs above the field, over the picture, in the window's
            // overlay so it is never under the action bar or clipped by the row.
            Popup {
                id: paceMenu
                parent: paceClosed
                x: 0
                y: -(height + 4)
                width: paceClosed.width
                visible: paceBox.open
                modal: false
                dim: false
                focus: true
                padding: 0
                // No fade. A closed list is gone at once, and keys reach it as soon as it opens.
                enter: Transition {}
                exit: Transition {}
                closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                property int cursor: 0
                property var paces: ["open", "measured", "tight", "frenzied"]
                function pick() {
                    backend.pace = paces[cursor]
                    paceBox.open = false
                }
                // The popup hands focus back to the field as it closes. Let it go
                // once that is done, so Space plays instead of reopening the list.
                onClosed: {
                    paceBox.open = false
                    Qt.callLater(function() {
                        if (paceClosed.activeFocus)
                            paceClosed.focus = false
                    })
                }
                onOpened: paceRows.forceActiveFocus()
                background: Rectangle {
                    radius: theme.radius
                    color: theme.raised
                    border.width: 1
                    border.color: theme.line
                }
                contentItem: Column {
                    id: paceRows
                    focus: true
                    Repeater {
                        model: paceMenu.paces
                        delegate: Rectangle {
                            required property string modelData
                            required property int index
                            width: paceRows.width
                            height: 32
                            radius: theme.radius
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
                    Keys.onUpPressed: (event) => {
                        paceMenu.cursor = Math.max(0, paceMenu.cursor - 1)
                        event.accepted = true
                    }
                    Keys.onDownPressed: (event) => {
                        paceMenu.cursor = Math.min(paceMenu.paces.length - 1, paceMenu.cursor + 1)
                        event.accepted = true
                    }
                    Keys.onReturnPressed: (event) => { paceMenu.pick(); event.accepted = true }
                    Keys.onEnterPressed: (event) => { paceMenu.pick(); event.accepted = true }
                    Keys.onEscapePressed: (event) => {
                        paceBox.open = false
                        event.accepted = true
                    }
                }
            }
        }

        // The fade. The same setting as "Fade to black between shots" in Settings.
        Label {
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: 4
            text: qsTr("Fade")
            color: theme.foreground
            font.pixelSize: 13
        }
        Switch {
            id: planFadeSwitch
            objectName: "planFadeSwitch"
            focusPolicy: Qt.NoFocus
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: -4
            enabled: !backend.busy
            opacity: backend.busy ? 0.38 : 1
            checked: backend.sceneTransition === "dip"
            onClicked: backend.sceneTransition = checked ? "dip" : "off"
        }
    }

    Connections {
        target: backend
        function onIntentChanged() {
            if (planIntent.text !== backend.intent) {
                planIntent.text = backend.intent
                if (!planIntent.activeFocus)
                    planIntent.cursorPosition = 0
            }
        }
        function onBusyChanged() {
            if (backend.busy)
                paceBox.open = false
        }
    }
}
