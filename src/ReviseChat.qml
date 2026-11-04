import QtQuick
import QtQuick.Controls

// The field is the chat. One note, one result, no bubbles.
Item {
    id: root
    property var host
    signal applied(bool changed, string fromStep)

    property string pendingNote: ""
    property string chatState: ""
    property string changeText: ""
    property var before: null
    property string sentFrom: ""

    readonly property string shownNote: {
        if (pendingNote !== "")
            return pendingNote
        var notes = backend.reviseNotes
        if (!notes || notes.length === 0)
            return ""
        return String(notes[notes.length - 1])
    }
    readonly property string trimmedField: field.text.replace(/\s+/g, " ").trim()

    implicitWidth: 200
    implicitHeight: chatCol.implicitHeight + 9

    function snapshot() {
        var kept = {}
        var rows = backend.selects
        for (var i = 0; i < rows.length; i++)
            kept[String(rows[i].id)] = rows[i].keep !== false
        return {
            intent: backend.intent,
            pace: backend.pace,
            dip: backend.sceneTransition,
            kept: kept
        }
    }
    function paceWord(pace) {
        if (pace === "measured")
            return qsTr("Measured")
        if (pace === "tight")
            return qsTr("Tight")
        if (pace === "frenzied")
            return qsTr("Frenzied")
        return qsTr("Open")
    }
    function describe(snap) {
        var rows = backend.selects
        var dropped = 0
        var restored = 0
        for (var i = 0; i < rows.length; i++) {
            var id = String(rows[i].id)
            var wasKept = snap.kept[id]
            if (wasKept === undefined)
                continue
            var nowKept = rows[i].keep !== false
            if (wasKept && !nowKept)
                dropped++
            else if (!wasKept && nowKept)
                restored++
        }
        var parts = []
        if (dropped === 1)
            parts.push(qsTr("Dropped 1 line."))
        else if (dropped > 1)
            parts.push(qsTr("Dropped %1 lines.").arg(dropped))
        if (restored === 1)
            parts.push(qsTr("Put back 1 line."))
        else if (restored > 1)
            parts.push(qsTr("Put back %1 lines.").arg(restored))
        if (backend.intent !== snap.intent)
            parts.push(qsTr("New movie sentence."))
        if (backend.pace !== snap.pace)
            parts.push(qsTr("Pace is now %1.").arg(paceWord(backend.pace)))
        if (backend.sceneTransition !== snap.dip) {
            parts.push(backend.sceneTransition === "dip"
                       ? qsTr("Fade to black on.")
                       : qsTr("Fade to black off."))
        }
        if (parts.length === 0)
            return qsTr("Nothing changed. Try saying it another way.")
        return parts.join(" ")
    }
    function send() {
        var note = trimmedField
        if (note === "" || backend.busy)
            return
        var snap = snapshot()
        var from = host ? host.viewStep : ""
        if (!backend.sendRevise(note)) {
            chatState = "failed"
            changeText = qsTr("That change didn't go through. Your note is back in the field.")
            return
        }
        before = snap
        sentFrom = from
        pendingNote = note
        field.text = ""
        chatState = "changing"
        changeText = qsTr("Changing the cut…")
    }
    function undo() {
        backend.revertRevise()
        if (!backend.canRevert) {
            chatState = "undone"
            changeText = qsTr("Undone. Back to how it was before this note.")
        } else {
            chatState = "undoFailed"
            changeText = qsTr("Could not undo. The line list did not save.")
        }
    }
    function notesChanged() {
        var notes = backend.reviseNotes
        if (!notes || notes.length === 0) {
            pendingNote = ""
            chatState = ""
            changeText = ""
            before = null
            sentFrom = ""
            return
        }
        if (chatState !== "changing" || !before)
            return
        var text = describe(before)
        var from = sentFrom
        var changed = text !== qsTr("Nothing changed. Try saying it another way.")
        pendingNote = ""
        chatState = "changed"
        changeText = text
        before = null
        applied(changed, from)
    }
    function busyChanged() {
        if (backend.busy || chatState !== "changing")
            return
        field.text = pendingNote
        field.cursorPosition = field.text.length
        pendingNote = ""
        chatState = "failed"
        changeText = qsTr("That change didn't go through. Your note is back in the field.")
        if (root.visible)
            field.forceActiveFocus()
    }

    Rectangle {
        anchors.top: parent.top
        width: parent.width
        height: 1
        color: theme.raised
    }

    Column {
        id: chatCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: 9
        spacing: 8

        Label {
            visible: root.shownNote !== ""
            width: parent.width
            text: "\u201C" + root.shownNote + "\u201D"
            color: theme.foreground
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }
        Label {
            visible: root.changeText !== ""
            width: parent.width
            text: root.changeText
            color: theme.foreground
            opacity: 0.62
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        Label {
            visible: backend.canRevert && !backend.busy
            text: qsTr("Undo this change")
            color: theme.foreground
            font.pixelSize: 13
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.undo()
            }
        }

        // Three notes to start from. A chip only fills the field. Sending is
        // still the word in the field or Enter.
        Flow {
            width: parent.width
            spacing: 6
            Repeater {
                model: [qsTr("Make it tighter"), qsTr("Drop the pricing part"), qsTr("Under 90 seconds")]
                delegate: Rectangle {
                    id: chip
                    required property string modelData
                    width: chipText.implicitWidth + 16
                    height: 24
                    radius: theme.radius
                    color: chipHover.hovered && chip.enabled ? theme.hover : "transparent"
                    border.width: 1
                    border.color: theme.line
                    enabled: !backend.busy
                    HoverHandler { id: chipHover; enabled: chip.enabled }
                    Label {
                        id: chipText
                        anchors.centerIn: parent
                        text: chip.modelData
                        color: theme.foreground
                        opacity: !chip.enabled ? 0.38 : (chipHover.hovered ? 1 : 0.62)
                        font.pixelSize: 12
                    }
                    MouseArea {
                        anchors.fill: parent
                        enabled: chip.enabled
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            field.text = chip.modelData
                            field.cursorPosition = field.text.length
                            field.forceActiveFocus()
                        }
                    }
                }
            }
        }

        Rectangle {
            width: parent.width
            height: 36
            radius: theme.radius
            color: theme.raised
            border.width: field.activeFocus ? 1 : 0
            border.color: theme.accent

            TextInput {
                id: field
                objectName: "reviseField"
                anchors.fill: parent
                leftPadding: 12
                rightPadding: sendWord.visible ? sendWord.width + 24 : 12
                verticalAlignment: Text.AlignVCenter
                clip: true
                color: theme.foreground
                opacity: enabled ? 1 : 0.38
                font.pixelSize: 13
                selectByMouse: true
                enabled: !backend.busy
                onAccepted: root.send()
            }
            Label {
                anchors.fill: field
                anchors.leftMargin: field.leftPadding
                anchors.rightMargin: field.rightPadding
                visible: field.text === ""
                text: qsTr("Tell BotCut what to change")
                color: theme.foreground
                opacity: 0.38
                font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            Label {
                id: sendWord
                objectName: "reviseSend"
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                visible: root.trimmedField !== "" && !backend.busy
                text: qsTr("Change this cut")
                color: theme.accent
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.send()
                }
            }
        }
    }

    Connections {
        target: backend
        function onReviseNotesChanged() { root.notesChanged() }
        function onBusyChanged() { root.busyChanged() }
    }
}
