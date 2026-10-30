import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Item {
    id: root
    property var host
    anchors.fill: parent
    visible: host && host.settingsOpen
    z: 35

    function focusKey() {
        keyField.forceActiveFocus()
    }

    Material.theme: Material.Dark
    Material.accent: theme.accent
    Material.roundedScale: theme.radius

    Rectangle {
        anchors.fill: parent
        color: "#99000000"
    }
    MouseArea { anchors.fill: parent }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(520, parent.width - 48)
        height: Math.min(column.implicitHeight + 48, parent.height - 32)
        radius: theme.radius
        color: "#1c1c1e"
        border.color: "#39393e"
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
                width: parent.width
                text: qsTr("How BotCut cuts")
                color: theme.foreground
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }
            RowLayout {
                width: parent.width
                spacing: 12
                Switch {
                    id: spokenCutsBox
                    objectName: "spokenCutsBox"
                    focusPolicy: Qt.NoFocus
                    enabled: !backend.busy
                    checked: backend.cutMode === "speech"
                    onClicked: backend.cutMode = checked ? "speech" : "assemble"
                }
                Label {
                    Layout.fillWidth: true
                    text: qsTr("Spoken cuts: keeps the lines worth saying. Needs an xAI key.")
                    color: theme.foreground
                    opacity: backend.cutMode === "speech" ? 1 : 0.62
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }
            }
            Label {
                width: parent.width
                text: qsTr("Every shot: joins the shots in order.")
                color: theme.foreground
                opacity: backend.cutMode === "speech" ? 0.62 : 1
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            Label {
                width: parent.width
                text: backend.apiKeySet
                      ? qsTr("Saved on this computer.")
                      : qsTr("Not set. Spoken cuts can't run without it.")
                color: backend.apiKeySet ? theme.foreground : theme.accent
                opacity: backend.apiKeySet ? 0.62 : 1
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            Rectangle {
                width: parent.width
                height: 36
                radius: theme.radius
                color: "#0e0e10"
                border.width: keyField.activeFocus ? 1 : 0
                border.color: theme.accent
                TextInput {
                    id: keyField
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    verticalAlignment: Text.AlignVCenter
                    color: theme.foreground
                    font.pixelSize: 13
                    clip: true
                    selectByMouse: true
                    echoMode: keyReveal.checked ? TextInput.Normal : TextInput.Password
                    enabled: !backend.busy
                }
                Label {
                    anchors.fill: keyField
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    visible: keyField.text === ""
                    text: qsTr("Paste xAI key")
                    color: theme.foreground
                    opacity: 0.38
                    font.pixelSize: 13
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }
            RowLayout {
                width: parent.width
                spacing: 12
                CheckBox {
                    id: keyReveal
                    text: qsTr("Show")
                    focusPolicy: Qt.NoFocus
                    font.pixelSize: 13
                    enabled: !backend.busy
                }
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: qsTr("Save key")
                    enabled: !backend.busy
                    onClicked: {
                        backend.setApiKey(keyField.text)
                        keyField.text = ""
                    }
                }
            }
            CheckBox {
                width: parent.width
                text: qsTr("Fade to black between shots")
                font.pixelSize: 13
                focusPolicy: Qt.NoFocus
                enabled: !backend.busy
                checked: backend.sceneTransition === "dip"
                onClicked: backend.sceneTransition = checked ? "dip" : "off"
            }
            CheckBox {
                width: parent.width
                text: qsTr("Cover a spoken line with another shot's picture")
                font.pixelSize: 13
                focusPolicy: Qt.NoFocus
                enabled: !backend.busy
                checked: backend.broll
                onClicked: backend.broll = checked
            }
            CheckBox {
                width: parent.width
                text: qsTr("Keep that shot's sound under the voice")
                font.pixelSize: 13
                focusPolicy: Qt.NoFocus
                enabled: backend.broll && !backend.busy
                checked: backend.brollMix
                onClicked: backend.brollMix = checked
            }
            RowLayout {
                width: parent.width
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: qsTr("Done")
                    filled: true
                    onClicked: host.closeSettings()
                }
            }
        }
    }
}
