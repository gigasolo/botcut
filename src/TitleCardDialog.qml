import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var host
    anchors.fill: parent
    visible: host && host.titleCardOpen
    z: 45

    function clearField() {
        field.text = ""
    }
    function sentence() {
        return field.text.replace(/\s+/g, " ").trim()
    }
    function place(where) {
        var words = sentence()
        if (words === "" || backend.busy)
            return
        backend.makeCard(where, words)
        host.titleCardOpen = false
    }

    onVisibleChanged: {
        if (visible)
            field.text = ""
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
            Label {
                width: parent.width
                text: qsTr("A still with this sentence, added as a shot you can move or remove.")
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
                    onClicked: host.titleCardOpen = false
                }
                ActionButton {
                    text: qsTr("Put it last")
                    enabled: !backend.busy
                    onClicked: root.place("close")
                }
                ActionButton {
                    text: qsTr("Put it first")
                    filled: true
                    enabled: !backend.busy
                    onClicked: root.place("open")
                }
            }
        }
    }
}
