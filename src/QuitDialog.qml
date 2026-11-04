import QtQuick
import QtQuick.Controls

// Not a Dialog or Popup. Arrow keys must reach these buttons while trim is quiet.
Item {
    id: root
    property var host
    anchors.fill: parent
    visible: host && host.quitConfirmVisible
    z: 50

    onVisibleChanged: {
        if (!visible)
            return
        if (backend.busy)
            quitCancelButton.forceActiveFocus()
        else
            quitExportButton.forceActiveFocus()
    }

    component DialogButton: Rectangle {
        id: dialogButton
        width: dialogButtonLabel.implicitWidth + 28
        height: 34
        radius: 8

        property string text: ""
        property bool primary: false
        signal clicked()

        color: primary ? theme.accent : theme.raised
        border.color: activeFocus ? (primary ? theme.accentForeground : theme.accent) : "transparent"
        border.width: activeFocus ? 2 : 0

        Keys.onReturnPressed: clicked()
        Keys.onEnterPressed: clicked()
        Keys.onSpacePressed: clicked()

        Label {
            id: dialogButtonLabel
            anchors.centerIn: parent
            text: dialogButton.text
            color: dialogButton.primary ? theme.accentForeground : theme.foreground
            font.pixelSize: 13
            font.weight: Font.DemiBold
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: dialogButton.clicked()
        }
    }

    Rectangle {
        anchors.fill: parent
        color: theme.scrim
    }

    MouseArea {
        anchors.fill: parent
        onClicked: host.quitConfirmVisible = false
    }

    Rectangle {
        anchors.centerIn: parent
        width: quitColumn.width + 64
        height: quitColumn.height + 48
        radius: theme.radius
        color: theme.surface

        MouseArea { anchors.fill: parent }

        Column {
            id: quitColumn
            anchors.centerIn: parent
            spacing: 8

            Label {
                text: backend.busy ? qsTr("Stop the render and quit?")
                        : (host.leaveTarget === "lists"
                           ? qsTr("Export your trim before you go to Lists?")
                           : (host.looseCut ? qsTr("Save your movie before you quit?")
                              : qsTr("Export your trim before you quit?")))
                color: theme.foreground
                font.pixelSize: 16
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
                width: 420
            }
            Label {
                text: backend.busy
                      ? qsTr("Quitting stops the job and keeps nothing.")
                      : (host.looseCut
                         ? qsTr("It's only in a temporary folder. Quitting deletes it.")
                         : qsTr("Your hand trim isn't in a file yet."))
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                width: 420
                bottomPadding: 12
            }
            Row {
                anchors.right: parent.right
                spacing: 10
                DialogButton {
                    id: quitCancelButton
                    text: qsTr("Keep working")
                    focus: true
                    KeyNavigation.left: quitExportButton.visible ? quitExportButton : quitQuitButton
                    KeyNavigation.right: quitQuitButton
                    KeyNavigation.tab: quitQuitButton
                    KeyNavigation.backtab: quitExportButton.visible ? quitExportButton : quitQuitButton
                    onClicked: host.quitConfirmVisible = false
                }
                DialogButton {
                    id: quitQuitButton
                    text: backend.busy ? qsTr("Stop and quit")
                            : (host.leaveTarget === "lists" ? qsTr("Go to Lists without exporting")
                               : (host.looseCut ? qsTr("Quit without saving")
                                  : qsTr("Quit without exporting")))
                    focus: true
                    KeyNavigation.left: quitCancelButton
                    KeyNavigation.right: quitExportButton.visible ? quitExportButton : quitCancelButton
                    KeyNavigation.tab: quitExportButton.visible ? quitExportButton : quitCancelButton
                    KeyNavigation.backtab: quitCancelButton
                    onClicked: {
                        var toLists = host.leaveTarget === "lists"
                        host.quitConfirmVisible = false
                        if (toLists)
                            host.closeProjectNow()
                        else
                            host.forceQuit()
                    }
                }
                DialogButton {
                    id: quitExportButton
                    visible: !backend.busy
                    text: host.looseCut ? qsTr("Save…") : qsTr("Export…")
                    primary: true
                    focus: true
                    KeyNavigation.left: quitQuitButton
                    KeyNavigation.right: quitCancelButton
                    KeyNavigation.tab: quitCancelButton
                    KeyNavigation.backtab: quitQuitButton
                    onClicked: {
                        host.quitConfirmVisible = false
                        host.exportVideo()
                    }
                }
            }
        }
    }
}
