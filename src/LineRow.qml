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
    color: selected || marked ? theme.selected : "transparent"
    readonly property bool dropped: modelData && modelData.keep === false

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
        anchors.rightMargin: 12
        anchors.topMargin: 8
        spacing: 4

        RowLayout {
            width: parent.width
            spacing: 8
            // One clock column, so the words line up from row to row.
            Label {
                text: row.timeText
                color: theme.foreground
                opacity: row.dropped ? 0.38 : 0.62
                font.pixelSize: 12
                font.family: "monospace"
                Layout.alignment: Qt.AlignTop
                Layout.minimumWidth: 36
            }
            Label {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                text: row.modelData && row.modelData.text !== undefined ? row.modelData.text : ""
                color: theme.foreground
                opacity: row.dropped ? 0.38 : 1
                wrapMode: Text.WordWrap
                font.pixelSize: 13
            }
            Label {
                Layout.alignment: Qt.AlignTop
                text: row.modelData && row.modelData.keep !== false ? qsTr("Drop") : qsTr("Keep")
                color: theme.foreground
                opacity: backend.busy ? 0.38 : 1
                font.pixelSize: 13
                Rectangle {
                    z: -1
                    anchors.fill: parent
                    anchors.leftMargin: -6
                    anchors.rightMargin: -6
                    anchors.topMargin: -4
                    anchors.bottomMargin: -4
                    radius: theme.radius
                    color: theme.hover
                    visible: keepArea.containsMouse && !backend.busy
                }
                MouseArea {
                    id: keepArea
                    anchors.fill: parent
                    anchors.leftMargin: -6
                    anchors.rightMargin: -6
                    anchors.topMargin: -4
                    anchors.bottomMargin: -4
                    hoverEnabled: true
                    cursorShape: backend.busy ? Qt.ArrowCursor : Qt.PointingHandCursor
                    onClicked: {
                        if (backend.busy || !row.modelData)
                            return
                        if (row.modelData.keep !== false)
                            backend.dropSelect(row.modelData.id)
                        else
                            backend.restoreSelect(row.modelData.id)
                    }
                }
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
                opacity: backend.busy ? 0.38 : 1
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: backend.busy ? Qt.ArrowCursor : Qt.PointingHandCursor
                    onClicked: {
                        if (!backend.busy)
                            row.playRequested()
                    }
                }
            }
            Label {
                visible: row.coverText !== ""
                text: qsTr("Remove B-roll")
                color: theme.foreground
                opacity: backend.busy ? 0.38 : 1
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: backend.busy ? Qt.ArrowCursor : Qt.PointingHandCursor
                    onClicked: {
                        if (backend.busy || !row.modelData)
                            return
                        backend.clearCover(row.modelData.id)
                    }
                }
            }
        }
    }
}
