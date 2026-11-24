import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The chat about this line list. Your turns on the right, the bot's on the
// left. A bot turn is the model's reply and the change it would make. Nothing
// moves until Apply, or a typed yes. The thread itself is backend.chat; the
// lines this file adds (Thinking…, a failure, an undo) are the window's own.
Item {
    id: root
    property var host
    signal applied(bool changed, string fromStep)

    // "proposing" while the model thinks, "applying" while the change lands.
    property string chatState: ""
    property string pendingNote: ""
    property int chatCountBeforeSend: 0
    property string sentFrom: ""
    // One transient line under the thread: a failure, or what undo did.
    property string localText: ""
    property var keptBefore: null

    readonly property string trimmedField: field.text.replace(/\s+/g, " ").trim()
    readonly property string failedText: qsTr("That change didn't go through. Your note is back in the field.")
    readonly property int lastTurn: backend.chat ? backend.chat.length - 1 : -1
    readonly property string lastRole: {
        var turns = backend.chat
        if (!turns || turns.length === 0)
            return ""
        return String(turns[turns.length - 1].role || "")
    }
    readonly property string lastChange: {
        var turns = backend.chat
        if (!turns || turns.length === 0)
            return ""
        return String(turns[turns.length - 1].change || "")
    }

    implicitWidth: 200
    implicitHeight: 240

    // Short answers that mean "go ahead" while a proposal waits.
    function accepts(text) {
        var plain = text.toLowerCase().replace(/[.!,]/g, "").replace(/\s+/g, " ").trim()
        var whole = ["yes", "y", "ok", "okay", "do it", "apply", "apply it", "go ahead", "go",
                     "sure", "yep", "yeah", "please", "make it so"]
        if (whole.indexOf(plain) >= 0)
            return true
        // "Yes, do it." and "ok go ahead" say yes. "yes but shorter" is a new note.
        var words = plain.split(" ")
        var first = ["yes", "ok", "okay", "sure", "yep", "yeah"]
        if (first.indexOf(words[0]) < 0 || words.length > 4)
            return false
        return words.indexOf("but") < 0 && words.indexOf("not") < 0 && words.indexOf("no") < 0
    }
    function snapshotKept() {
        var kept = {}
        var rows = backend.selects
        for (var i = 0; i < rows.length; i++)
            kept[String(rows[i].id)] = rows[i].keep !== false
        return { kept: kept, intent: backend.intent, pace: backend.pace, dip: backend.sceneTransition }
    }
    function changedSince(snap) {
        if (!snap)
            return true
        if (backend.intent !== snap.intent || backend.pace !== snap.pace || backend.sceneTransition !== snap.dip)
            return true
        var rows = backend.selects
        for (var i = 0; i < rows.length; i++) {
            var was = snap.kept[String(rows[i].id)]
            if (was !== undefined && was !== (rows[i].keep !== false))
                return true
        }
        return false
    }
    function send() {
        var note = trimmedField
        if (note === "" || backend.busy)
            return
        if (backend.proposalPending && accepts(note)) {
            field.text = ""
            apply()
            return
        }
        var from = host ? host.viewStep : ""
        localText = ""
        var countBefore = backend.chat ? backend.chat.length : 0
        if (!backend.sendRevise(note)) {
            localText = failedText
            return
        }
        chatCountBeforeSend = countBefore
        sentFrom = from
        pendingNote = note
        field.text = ""
        chatState = "proposing"
    }
    function apply() {
        if (backend.busy || !backend.proposalPending)
            return
        localText = ""
        keptBefore = snapshotKept()
        sentFrom = host ? host.viewStep : ""
        if (!backend.applyProposal()) {
            localText = failedText
            return
        }
        chatState = "applying"
    }
    function leave() {
        if (backend.busy)
            return
        localText = ""
        backend.dismissProposal()
    }
    function undo() {
        backend.revertRevise()
        if (!backend.canRevert)
            localText = qsTr("Undone. Back to how it was before this note.")
        else
            localText = qsTr("Could not undo. The line list did not save.")
    }
    function busyChanged() {
        if (backend.busy)
            return
        if (chatState === "proposing") {
            chatState = ""
            var countNow = backend.chat ? backend.chat.length : 0
            if (lastRole === "bot" && countNow > chatCountBeforeSend) {
                pendingNote = ""
                return
            }
            // No reply came. The note goes back where it was typed.
            field.text = pendingNote
            field.cursorPosition = field.text.length
            pendingNote = ""
            localText = failedText
            if (root.visible)
                field.forceActiveFocus()
            return
        }
        if (chatState === "applying") {
            chatState = ""
            if (backend.proposalPending) {
                localText = failedText
                return
            }
            applied(changedSince(keptBefore), sentFrom)
            keptBefore = null
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        ListView {
            id: thread
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 8
            boundsBehavior: Flickable.StopAtBounds
            model: backend.chat
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 4 }
            onCountChanged: Qt.callLater(function() { thread.positionViewAtEnd() })
            footer: Item {
                width: thread.width
                height: footerCol.implicitHeight > 0 ? footerCol.implicitHeight + 8 : 0
                Column {
                    id: footerCol
                    width: parent.width
                    spacing: 8
                    Label {
                        visible: root.chatState !== "" && backend.busy
                        width: parent.width
                        text: root.chatState === "applying" ? qsTr("Applying…") : qsTr("Thinking…")
                        color: theme.foreground
                        opacity: 0.62
                        font.pixelSize: 13
                    }
                    Label {
                        visible: root.localText !== ""
                        width: parent.width
                        text: root.localText
                        color: theme.foreground
                        opacity: 0.62
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    // The few spots in this cut worth a look. A click goes to the line.
                    Column {
                        objectName: "reviewSpots"
                        visible: backend.review.length > 0 && !backend.busy && !backend.proposalPending
                        width: parent.width
                        spacing: 4
                        Label {
                            text: backend.review.length === 1 ? qsTr("One spot worth a look")
                                                                : qsTr("%1 spots worth a look").arg(backend.review.length)
                            color: theme.foreground
                            opacity: 0.62
                            font.pixelSize: 12
                        }
                        Repeater {
                            model: backend.review
                            Label {
                                id: spot
                                required property var modelData
                                readonly property var ids: modelData.ids || []
                                readonly property bool goes: ids.length > 0
                                width: parent.width
                                text: goes ? qsTr("Line %1 · %2").arg(root.host ? root.host.lineNumber(ids[0]) : ids[0])
                                                                 .arg(String(modelData.text))
                                           : String(modelData.text)
                                color: theme.foreground
                                opacity: goes && spotArea.containsMouse ? 1 : 0.8
                                font.pixelSize: 13
                                font.underline: goes && spotArea.containsMouse
                                wrapMode: Text.WordWrap
                                MouseArea {
                                    id: spotArea
                                    anchors.fill: parent
                                    enabled: spot.goes
                                    hoverEnabled: true
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: root.host.showSpot(spot.ids[0])
                                }
                            }
                        }
                    }
                }
            }
            delegate: Item {
                id: turn
                required property int index
                required property var modelData
                readonly property bool mine: String(modelData.role) === "you"
                readonly property bool last: index === root.lastTurn
                readonly property string words: String(modelData.text || "")
                readonly property string change: String(modelData.change || "")
                width: thread.width
                height: mine ? bubble.height : botCol.implicitHeight

                // Your turn: a raised bubble on the right.
                Rectangle {
                    id: bubble
                    visible: turn.mine
                    anchors.right: parent.right
                    width: Math.min(bubbleText.implicitWidth + 24, Math.round(thread.width * 0.85))
                    height: bubbleText.implicitHeight + 16
                    radius: theme.radius
                    color: theme.raised
                    Label {
                        id: bubbleText
                        anchors.fill: parent
                        anchors.margins: 8
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        text: turn.words
                        color: theme.foreground
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                    }
                }

                // The bot's turn: its reply, the change, and the way to say yes.
                Column {
                    id: botCol
                    visible: !turn.mine
                    width: parent.width
                    spacing: 6
                    Label {
                        width: parent.width
                        text: turn.words
                        color: theme.foreground
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                    }
                    Label {
                        visible: turn.change !== ""
                        width: parent.width
                        text: turn.change
                        color: theme.foreground
                        opacity: 0.62
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    Row {
                        visible: turn.last && backend.proposalPending
                        spacing: 6
                        ActionButton {
                            objectName: "applyProposal"
                            text: qsTr("Apply")
                            filled: true
                            implicitHeight: 32
                            enabled: !backend.busy
                            onClicked: root.apply()
                        }
                        ActionButton {
                            text: qsTr("Leave it")
                            raised: true
                            enabled: !backend.busy
                            onClicked: root.leave()
                        }
                    }
                    Label {
                        visible: turn.last && !backend.proposalPending && backend.canRevert && !backend.busy
                        text: qsTr("Undo")
                        color: theme.foreground
                        font.pixelSize: 13
                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -4
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.undo()
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            Layout.minimumHeight: 36
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
                text: backend.proposalPending ? qsTr("Say yes, or ask for something else")
                                              : qsTr("Ask for a change…")
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
                text: qsTr("Send")
                color: theme.accent
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -6
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.send()
                }
            }
        }
    }

    onLocalTextChanged: Qt.callLater(function() { thread.positionViewAtEnd() })

    Connections {
        target: backend
        function onBusyChanged() { root.busyChanged() }
        function onChatChanged() {
            if (backend.chat.length === 0)
                root.localText = ""
            Qt.callLater(function() { thread.positionViewAtEnd() })
        }
    }
}
