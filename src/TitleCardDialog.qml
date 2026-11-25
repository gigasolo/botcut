import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var host
    property string cardStyle: "live"
    anchors.fill: parent
    visible: host && host.titleCardOpen
    z: 45

    function sentence() {
        return field.text.replace(/\s+/g, " ").trim()
    }
    function place(where) {
        var words = sentence()
        if (words === "" || backend.busy)
            return
        if (root.cardStyle === "live") {
            if (backend && backend.liveTitle !== undefined)
                backend.liveTitle = words
            host.titleCardOpen = false
            return
        }
        backend.makeCard(where, words, root.cardStyle)
        host.titleCardOpen = false
    }

    onVisibleChanged: {
        if (visible) {
            field.text = (backend && backend.movieTitle !== undefined) ? backend.movieTitle : ""
            field.forceActiveFocus()
            field.selectAll()
        }
    }

    Rectangle {
        anchors.fill: parent
        color: theme.scrim
    }
    MouseArea { anchors.fill: parent }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(480, parent.width - 48)
        height: column.implicitHeight + 48
        radius: theme.radius
        color: theme.surface
        border.color: theme.line

        MouseArea { anchors.fill: parent }

        Column {
            id: column
            anchors.centerIn: parent
            width: parent.width - 48
            spacing: 12

            Label {
                width: parent.width
                text: qsTr("Add a title card")
                color: theme.foreground
                font.pixelSize: 22
                font.weight: Font.DemiBold
            }
            Rectangle {
                width: parent.width
                height: 36
                radius: theme.radius
                color: theme.background
                border.width: field.activeFocus ? 1 : 0
                border.color: theme.accent
                opacity: field.enabled ? 1 : 0.45
                TextInput {
                    id: field
                    objectName: "titleCardField"
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    verticalAlignment: Text.AlignVCenter
                    color: theme.foreground
                    font.pixelSize: 13
                    clip: true
                    selectByMouse: true
                    enabled: !backend.busy
                    onAccepted: root.place("open")
                }
                Label {
                    anchors.fill: field
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    visible: field.text === ""
                    text: qsTr("Words on the card")
                    color: theme.foreground
                    opacity: 0.38
                    font.pixelSize: 13
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }
            RowLayout {
                width: parent.width
                spacing: 8
                Label {
                    text: qsTr("Style")
                    color: theme.foreground
                    font.pixelSize: 13
                }
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: qsTr("Live overlay")
                    filled: root.cardStyle === "live"
                    enabled: !backend.busy
                    onClicked: root.cardStyle = "live"
                }
                ActionButton {
                    text: qsTr("Solid")
                    filled: root.cardStyle === "typo"
                    enabled: !backend.busy
                    onClicked: root.cardStyle = "typo"
                }
                ActionButton {
                    text: qsTr("AI art")
                    filled: root.cardStyle === "ai"
                    enabled: !backend.busy
                    onClicked: root.cardStyle = "ai"
                }
            }
            Label {
                width: parent.width
                text: root.cardStyle === "live"
                      ? qsTr("Fades minimal white typography over the first 3 seconds of live video — no silent freeze.")
                      : qsTr("A 3-second static still added as a shot you can move or remove.")
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            RowLayout {
                width: parent.width
                spacing: 8
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: qsTr("Cancel")
                    focusPolicy: Qt.TabFocus
                    onClicked: host.titleCardOpen = false
                }
                ActionButton {
                    text: qsTr("Put it last")
                    focusPolicy: Qt.TabFocus
                    enabled: !backend.busy && root.sentence() !== "" && root.cardStyle !== "live"
                    onClicked: root.place("close")
                }
                ActionButton {
                    text: qsTr("Put it first")
                    filled: true
                    focusPolicy: Qt.TabFocus
                    enabled: !backend.busy && root.sentence() !== ""
                    onClicked: root.place("open")
                }
            }
        }
    }
}
