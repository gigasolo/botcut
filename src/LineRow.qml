import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: row
    required property int index
    required property var modelData
    property string timeText: ""
    property string reasonText: ""
    property string coverText: ""
    property bool selected: false
    property bool marked: false
    signal picked()
    signal playRequested()

    width: ListView.view ? ListView.view.width : implicitWidth
    height: body.implicitHeight + 16
    radius: theme.radius
    color: selected || marked ? "#2a2a2e" : "transparent"
    opacity: modelData && modelData.keep === false ? 0.45 : 1

    Rectangle {
        visible: row.marked
        width: 2
        height: parent.height
        color: theme.accent
    }

    MouseArea {
        anchors.fill: parent
        onClicked: row.picked()
    }

    Column {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 12
        anchors.rightMargin: 8
        anchors.topMargin: 8
        spacing: 4

        RowLayout {
            width: parent.width
            spacing: 8
            Label {
                text: row.timeText
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 12
                font.family: "monospace"
                Layout.alignment: Qt.AlignTop
            }
            Label {
                Layout.fillWidth: true
                text: row.modelData && row.modelData.text !== undefined ? row.modelData.text : ""
                color: theme.foreground
                wrapMode: Text.WordWrap
                font.pixelSize: 13
            }
        }
        Row {
            spacing: 12
            visible: row.reasonText !== "" || row.coverText !== ""
            Label {
                visible: row.reasonText !== ""
                text: row.reasonText
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 12
            }
            Label {
                visible: row.coverText !== ""
                text: row.coverText
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 12
            }
        }
        Row {
            visible: row.selected
            spacing: 12
            Label {
                text: qsTr("Play")
                color: theme.foreground
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: row.playRequested()
                }
            }
            Label {
                text: row.modelData && row.modelData.keep !== false ? qsTr("Drop") : qsTr("Keep")
                color: theme.foreground
                opacity: keepArea.enabled ? 1 : 0.45
                font.pixelSize: 13
                enabled: !backend.busy
                MouseArea {
                    id: keepArea
                    anchors.fill: parent
                    enabled: parent.enabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        if (!row.modelData)
                            return
                        if (row.modelData.keep !== false)
                            backend.dropSelect(row.modelData.id)
                        else
                            backend.restoreSelect(row.modelData.id)
                    }
                }
            }
            Label {
                visible: row.coverText !== ""
                text: qsTr("Remove B-roll")
                color: theme.foreground
                opacity: clearArea.enabled ? 1 : 0.45
                font.pixelSize: 13
                enabled: !backend.busy
                MouseArea {
                    id: clearArea
                    anchors.fill: parent
                    enabled: parent.enabled && parent.visible
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        if (row.modelData)
                            backend.clearCover(row.modelData.id)
                    }
                }
            }
        }
    }
}
