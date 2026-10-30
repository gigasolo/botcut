import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: row
    required property int index
    required property string modelData
    width: ListView.view ? ListView.view.width : implicitWidth
    height: body.implicitHeight + 16
    radius: theme.radius
    color: selected ? theme.selected : "transparent"

    readonly property bool selected: index === backend.trayIndex
    readonly property bool exists: backend.trayFileExists(modelData)
    readonly property string title: {
        var name = baseName(modelData)
        return name.indexOf("botcut-card-") === 0 ? qsTr("Title card") : name
    }
    readonly property string fact: exists ? backend.trayFileSize(modelData) : qsTr("File missing")

    function baseName(path) {
        var s = String(path)
        var i = s.lastIndexOf("/")
        return i < 0 ? s : s.substring(i + 1)
    }
    function fileUrl(path) {
        if (!path)
            return ""
        var s = String(path)
        if (s.indexOf("file:") === 0)
            return path
        return "file://" + encodeURI(path)
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: backend.trayIndex = row.index
    }

    Column {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 8
        spacing: 4

        RowLayout {
            width: parent.width
            spacing: 8

            Rectangle {
                visible: row.exists
                Layout.preferredWidth: 64
                Layout.preferredHeight: 36
                Layout.alignment: Qt.AlignVCenter
                radius: 4
                clip: true
                color: theme.background
                Image {
                    id: shotImage
                    anchors.fill: parent
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    source: backend.trayThumbRevision >= 0 ? row.fileUrl(backend.trayThumb(row.modelData)) : ""
                }
                Rectangle {
                    id: shotPulse
                    anchors.fill: parent
                    visible: (backend.trayThumbRevision >= 0 && backend.trayThumbPending(row.modelData))
                             || shotImage.status === Image.Loading
                    color: theme.accent
                    SequentialAnimation on opacity {
                        running: shotPulse.visible
                        loops: Animation.Infinite
                        NumberAnimation { from: 0.15; to: 0.45; duration: 900 }
                        NumberAnimation { from: 0.45; to: 0.15; duration: 900 }
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                text: row.title
                color: row.exists ? theme.foreground : theme.accent
                elide: Text.ElideMiddle
                font.pixelSize: 13
            }
            Label {
                text: row.fact
                color: row.exists ? theme.foreground : theme.accent
                opacity: row.exists ? 0.62 : 1
                font.pixelSize: 12
                Layout.minimumWidth: implicitWidth
                Layout.maximumWidth: implicitWidth
            }
        }

        Row {
            id: actions
            visible: row.selected
            spacing: 12
            Label {
                text: qsTr("Move up")
                color: theme.foreground
                opacity: upArea.enabled ? 0.62 : 0.38
                font.pixelSize: 13
                enabled: row.index > 0 && !backend.busy
                MouseArea {
                    id: upArea
                    anchors.fill: parent
                    enabled: parent.enabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        backend.trayIndex = row.index
                        backend.moveTray(-1)
                    }
                }
            }
            Label {
                text: qsTr("Move down")
                color: theme.foreground
                opacity: downArea.enabled ? 0.62 : 0.38
                font.pixelSize: 13
                enabled: row.index < backend.tray.length - 1 && !backend.busy
                MouseArea {
                    id: downArea
                    anchors.fill: parent
                    enabled: parent.enabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        backend.trayIndex = row.index
                        backend.moveTray(1)
                    }
                }
            }
            Label {
                text: qsTr("Remove")
                color: theme.foreground
                opacity: removeArea.enabled ? 0.62 : 0.38
                font.pixelSize: 13
                enabled: !backend.busy
                MouseArea {
                    id: removeArea
                    anchors.fill: parent
                    enabled: parent.enabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        backend.trayIndex = row.index
                        backend.removeTray()
                    }
                }
            }
        }
    }
}
