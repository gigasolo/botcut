import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var host
    anchors.fill: parent
    visible: host && host.confirmCutOpen
    z: 46

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
                text: qsTr("Cut again from the shots?")
                color: theme.foreground
                font.pixelSize: 22
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            Label {
                width: parent.width
                text: qsTr("This replaces the list, including lines you kept or dropped by hand.")
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
                    text: qsTr("Keep this list")
                    onClicked: host.confirmCutOpen = false
                }
                ActionButton {
                    text: qsTr("Cut again")
                    filled: true
                    enabled: !backend.busy
                    onClicked: {
                        host.confirmCutOpen = false
                        backend.startCut()
                    }
                }
            }
        }
    }
}
