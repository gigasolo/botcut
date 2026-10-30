import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    property var host
    anchors.fill: parent
    visible: host && host.helpVisible
    z: 36

    Rectangle {
        anchors.fill: parent
        color: theme.scrim
    }
    MouseArea {
        anchors.fill: parent
        onClicked: host.helpVisible = false
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(880, parent.width - 32)
        height: Math.min(column.implicitHeight + 48, parent.height - 32)
        radius: theme.radius
        color: theme.surface
        border.color: theme.line
        clip: true

        MouseArea { anchors.fill: parent }

        Column {
            id: column
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 24
            spacing: 12

            Label {
                text: qsTr("How BotCut works")
                color: theme.foreground
                font.pixelSize: 22
                font.weight: Font.DemiBold
            }
            Label {
                width: parent.width
                wrapMode: Text.WordWrap
                color: theme.foreground
                font.pixelSize: 13
                text: qsTr("Add shots and put them in order.")
            }
            Label {
                width: parent.width
                wrapMode: Text.WordWrap
                color: theme.foreground
                font.pixelSize: 13
                text: qsTr("Cut finds the lines worth keeping.")
            }
            Label {
                width: parent.width
                wrapMode: Text.WordWrap
                color: theme.foreground
                font.pixelSize: 13
                text: qsTr("Drop lines or tell BotCut what to change, then Render.")
            }
            Label {
                width: parent.width
                wrapMode: Text.WordWrap
                color: theme.foreground
                font.pixelSize: 13
                text: qsTr("Watch, trim by hand if you need to, then Save.")
            }

            Row {
                width: parent.width
                spacing: 16
                Column {
                    width: (parent.width - 32) / 3
                    spacing: 4
                    Label {
                        text: qsTr("Shots and lines")
                        color: theme.foreground
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }
                    Repeater {
                        model: [
                            { keys: "Up / Down", action: qsTr("Select") },
                            { keys: "Alt+Up / Alt+Down", action: qsTr("Move") },
                            { keys: "Enter", action: qsTr("Play") },
                            { keys: "X", action: qsTr("Drop or keep") },
                            { keys: "Delete", action: qsTr("Remove") },
                            { keys: "Ctrl+Enter", action: qsTr("Press the filled button") }
                        ]
                        delegate: KeyLine {}
                    }
                }
                Column {
                    width: (parent.width - 32) / 3
                    spacing: 4
                    Label {
                        text: qsTr("Movie")
                        color: theme.foreground
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }
                    Repeater {
                        model: [
                            { keys: "Left / Right", action: qsTr("1 second") },
                            { keys: "Shift+Left / Right", action: qsTr("5 seconds") },
                            { keys: "Alt+Left / Right", action: qsTr("0.2 seconds") },
                            { keys: "[ / ]", action: qsTr("Previous or next edge") },
                            { keys: "S", action: qsTr("Split") },
                            { keys: "X", action: qsTr("Remove or restore") },
                            { keys: "Ctrl / Alt Space", action: qsTr("Set the edges") },
                            { keys: "Ctrl+Z", action: qsTr("Undo") },
                            { keys: "Z", action: qsTr("Zoom") }
                        ]
                        delegate: KeyLine {}
                    }
                }
                Column {
                    width: (parent.width - 32) / 3
                    spacing: 4
                    Label {
                        text: qsTr("Anywhere")
                        color: theme.foreground
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }
                    Repeater {
                        model: [
                            { keys: "Space", action: qsTr("Play or pause") },
                            { keys: "Ctrl+S", action: qsTr("Save or export") },
                            { keys: "Ctrl+O", action: qsTr("Open") },
                            { keys: "?", action: qsTr("Shortcuts") },
                            { keys: "Q", action: qsTr("Quit") }
                        ]
                        delegate: KeyLine {}
                    }
                }
            }

            RowLayout {
                width: parent.width
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: qsTr("Close")
                    filled: true
                    onClicked: host.helpVisible = false
                }
            }
        }
    }

    component KeyLine: Row {
        required property var modelData
        width: parent.width
        spacing: 8
        Label {
            width: Math.min(implicitWidth, parent.width * 0.46)
            text: modelData.keys
            color: theme.foreground
            opacity: 0.62
            font.pixelSize: 12
            elide: Text.ElideRight
        }
        Label {
            width: parent.width - parent.children[0].width - 8
            text: modelData.action
            color: theme.foreground
            font.pixelSize: 12
            elide: Text.ElideRight
        }
    }
}
