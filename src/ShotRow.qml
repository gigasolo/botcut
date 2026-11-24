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
    color: selected ? theme.selected : (rowHover.hovered ? theme.hover : "transparent")

    HoverHandler { id: rowHover }

    readonly property bool selected: index === backend.trayIndex
    readonly property bool exists: backend.trayFileExists(modelData)
    readonly property bool card: baseName(modelData).indexOf("botcut-card-") === 0
    // Read through the list so the row follows a toggle. A card is never B-roll.
    readonly property bool broll: !card && backend.brollFiles.indexOf(modelData) >= 0
    // Another camera on a take a file above it filmed. Found by its sound, or marked by hand.
    readonly property bool angle: !card && !broll && backend.angleFiles.indexOf(modelData) >= 0
    readonly property string title: card ? qsTr("Title card") : baseName(modelData)
    property bool renaming: false
    onSelectedChanged: if (!selected) renaming = false
    function stemOf(path) {
        var name = baseName(path)
        var dot = name.lastIndexOf(".")
        return dot > 0 ? name.substring(0, dot) : name
    }
    readonly property string fact: !exists ? qsTr("File missing")
                                           : broll ? qsTr("B-roll")
                                           : angle ? qsTr("Second camera") : backend.trayFileSize(modelData)

    function baseName(path) {
        var s = String(path)
        var i = s.lastIndexOf("/")
        return i < 0 ? s : s.substring(i + 1)
    }
    function fileUrl(path) {
        if (!path)
            return ""
        if (typeof backend.fileUrl === "function")
            return backend.fileUrl(path)
        var s = String(path)
        if (s.indexOf("file:") === 0)
            return path
        return "file://" + encodeURI(s).replace(/#/g, "%23").replace(/\?/g, "%3F")
    }

    component ShotWord: Rectangle {
        id: wordBox
        property string word
        property string wordObjectName: ""
        signal chosen()
        implicitWidth: wordLabel.implicitWidth + 10
        implicitHeight: 24
        radius: Math.max(0, theme.radius - 2)
        color: wordHover.hovered && enabled ? theme.hover : "transparent"
        HoverHandler { id: wordHover }
        Label {
            id: wordLabel
            objectName: wordBox.wordObjectName
            anchors.centerIn: parent
            text: wordBox.word
            color: theme.foreground
            opacity: wordBox.enabled ? (wordHover.hovered ? 0.95 : 0.62) : 0.38
            font.pixelSize: 13
        }
        MouseArea {
            anchors.fill: parent
            enabled: wordBox.enabled
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: wordBox.chosen()
        }
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
                    sourceSize: Qt.size(128, 72)
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
                visible: !row.renaming
                Layout.fillWidth: true
                text: row.title
                color: row.exists ? theme.foreground : theme.accent
                elide: Text.ElideMiddle
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    enabled: !row.card && row.exists && !backend.busy
                    onClicked: backend.trayIndex = row.index
                    onDoubleClicked: {
                        backend.trayIndex = row.index
                        renameInput.text = row.stemOf(row.modelData)
                        row.renaming = true
                        renameInput.forceActiveFocus()
                        renameInput.selectAll()
                    }
                }
            }
            Rectangle {
                visible: row.renaming
                Layout.fillWidth: true
                height: 26
                radius: Math.max(0, theme.radius - 2)
                color: theme.background
                border.width: 1
                border.color: theme.accent
                TextInput {
                    id: renameInput
                    objectName: "shotRenameInput"
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    verticalAlignment: Text.AlignVCenter
                    color: theme.foreground
                    font.pixelSize: 13
                    selectByMouse: true
                    clip: true
                    onAccepted: {
                        if (text.trim() !== "" && backend.renameTrayFile(row.index, text))
                            row.renaming = false
                    }
                    Keys.onEscapePressed: row.renaming = false
                }
            }
            Label {
                visible: !row.renaming
                text: row.fact
                color: row.exists ? theme.foreground : theme.accent
                opacity: row.exists ? 0.62 : 1
                font.pixelSize: 12
                Layout.minimumWidth: implicitWidth
                Layout.maximumWidth: implicitWidth
            }
        }

        // The words wrap onto a second line when the column is narrow.
        Flow {
            id: actions
            visible: row.selected
            width: parent.width
            spacing: 6
            ShotWord {
                word: qsTr("Move up")
                enabled: row.index > 0 && !backend.busy
                onChosen: {
                    backend.trayIndex = row.index
                    backend.moveTray(-1)
                }
            }
            ShotWord {
                word: qsTr("Move down")
                enabled: row.index < backend.tray.length - 1 && !backend.busy
                onChosen: {
                    backend.trayIndex = row.index
                    backend.moveTray(1)
                }
            }
            ShotWord {
                word: row.renaming ? qsTr("Save name") : qsTr("Rename")
                visible: !row.card && row.exists
                enabled: !backend.busy && (!row.renaming || renameInput.text.trim() !== "")
                onChosen: {
                    backend.trayIndex = row.index
                    if (row.renaming) {
                        if (backend.renameTrayFile(row.index, renameInput.text))
                            row.renaming = false
                    } else {
                        renameInput.text = row.stemOf(row.modelData)
                        row.renaming = true
                        renameInput.forceActiveFocus()
                        renameInput.selectAll()
                    }
                }
            }
            ShotWord {
                word: qsTr("Cancel")
                visible: row.renaming
                enabled: !backend.busy
                onChosen: row.renaming = false
            }
            ShotWord {
                word: qsTr("Remove")
                enabled: !backend.busy
                onChosen: {
                    backend.trayIndex = row.index
                    backend.removeTray()
                }
            }
            // A shot becomes B-roll, and B-roll becomes a shot again. A card is neither.
            // The same take from another camera. The first file is nobody's second camera.
            ShotWord {
                wordObjectName: "angleToggle"
                visible: !row.card && !row.broll && !row.angle && row.index > 0
                word: qsTr("Second camera")
                enabled: !backend.busy
                onChosen: {
                    backend.trayIndex = row.index
                    backend.toggleAngle(row.index)
                }
            }
            ShotWord {
                wordObjectName: "brollToggle"
                visible: !row.card
                word: row.broll || row.angle ? qsTr("Shot") : qsTr("B-roll")
                enabled: !backend.busy
                onChosen: {
                    backend.trayIndex = row.index
                    if (row.angle)
                        backend.toggleAngle(row.index)
                    else
                        backend.toggleBroll(row.index)
                }
            }
        }
    }
}
