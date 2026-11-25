import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Item {
    id: root
    property var host
    property string chosenAspect: (backend && backend.aspect) ? backend.aspect : "source"
    property string chosenResolution: (backend && backend.resolution) ? backend.resolution : "source"
    anchors.fill: parent
    visible: host && host.exportOpen
    z: 35

    onVisibleChanged: {
        if (visible && backend) {
            chosenAspect = backend.aspect || "source"
            chosenResolution = backend.resolution || "source"
            titleField.text = backend.movieTitle || ""
        }
    }

    Material.theme: Material.Dark
    Material.accent: theme.accent
    Material.roundedScale: theme.radius

    Rectangle {
        anchors.fill: parent
        color: theme.scrim
    }
    MouseArea {
        anchors.fill: parent
        onClicked: if (host) host.exportOpen = false
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(520, parent.width - 48)
        height: column.implicitHeight + 48
        radius: theme.radius
        color: theme.surface
        border.color: theme.line

        MouseArea { anchors.fill: parent }

        Column {
            id: column
            anchors.fill: parent
            anchors.margins: 24
            spacing: 14

            Label {
                width: parent.width
                text: qsTr("Re-render from originals")
                color: theme.foreground
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }
            Label {
                width: parent.width
                text: qsTr("Renders a new file beside this movie directly from your source clips at the format and resolution you pick.")
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            RowLayout {
                width: parent.width
                spacing: 8
                Rectangle {
                    Layout.fillWidth: true
                    height: 34
                    radius: theme.radius
                    color: theme.background
                    border.width: titleField.activeFocus ? 1 : 0
                    border.color: theme.accent
                    TextInput {
                        id: titleField
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        verticalAlignment: Text.AlignVCenter
                        color: theme.foreground
                        font.pixelSize: 13
                        clip: true
                        selectByMouse: true
                        enabled: !backend.busy
                        onAccepted: if (text.trim() !== "") backend.renameMovie(text)
                    }
                    Label {
                        anchors.fill: titleField
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        visible: titleField.text === ""
                        text: qsTr("Movie title (for filename & thumbnail)")
                        color: theme.foreground
                        opacity: 0.38
                        font.pixelSize: 13
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                }
                ActionButton {
                    text: qsTr("Rename")
                    enabled: !backend.busy && titleField.text.trim() !== ""
                    onClicked: backend.renameMovie(titleField.text)
                }
            }
            RowLayout {
                width: parent.width
                spacing: 8
                Label {
                    text: qsTr("Format")
                    color: theme.foreground
                    font.pixelSize: 13
                }
                Item { Layout.fillWidth: true }
                Repeater {
                    model: [
                        { value: "source", word: qsTr("Auto") },
                        { value: "landscape", word: qsTr("Landscape 16:9") },
                        { value: "portrait", word: qsTr("Portrait 9:16") }
                    ]
                    ActionButton {
                        required property var modelData
                        text: modelData.word
                        filled: root.chosenAspect === modelData.value
                        enabled: !backend.busy
                        onClicked: root.chosenAspect = modelData.value
                    }
                }
            }
            RowLayout {
                width: parent.width
                spacing: 6
                Label {
                    text: qsTr("Resolution")
                    color: theme.foreground
                    font.pixelSize: 13
                }
                Item { Layout.fillWidth: true }
                Repeater {
                    model: [
                        { value: "source", word: qsTr("Source") },
                        { value: "2160p", word: qsTr("4K") },
                        { value: "1440p", word: qsTr("1440p") },
                        { value: "1080p", word: qsTr("1080p") },
                        { value: "720p", word: qsTr("720p") }
                    ]
                    ActionButton {
                        required property var modelData
                        text: modelData.word
                        filled: root.chosenResolution === modelData.value
                        enabled: !backend.busy
                        onClicked: root.chosenResolution = modelData.value
                    }
                }
            }
            RowLayout {
                width: parent.width
                spacing: 8
                ActionButton {
                    text: qsTr("Photo thumbnail")
                    enabled: !backend.busy
                    onClicked: {
                        if (host)
                            host.exportOpen = false
                        backend.makePhotoThumb(titleField.text, root.chosenAspect === "portrait" ? "portrait" : "landscape")
                    }
                }
                ActionButton {
                    text: qsTr("Ship pack")
                    enabled: !backend.busy
                    onClicked: {
                        if (host)
                            host.exportOpen = false
                        backend.makeShipPack(titleField.text, root.chosenResolution === "source" ? "1080p" : root.chosenResolution, true)
                    }
                }
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: qsTr("Cancel")
                    onClicked: if (host) host.exportOpen = false
                }
                ActionButton {
                    objectName: "rerenderGoButton"
                    text: qsTr("Re-render")
                    filled: true
                    enabled: !backend.busy
                    onClicked: {
                        if (host)
                            host.exportOpen = false
                        backend.rerenderExport(root.chosenResolution, root.chosenAspect)
                    }
                }
            }
        }
    }
}
