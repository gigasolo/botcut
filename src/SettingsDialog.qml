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
    // An empty field saves nothing. Forgetting a key is its own button.
    function saveTypedKey() {
        if (keyField.text.trim() === "")
            return
        backend.setApiKey(keyField.text)
        keyField.text = ""
        backend.checkApiKey()
    }

    Material.theme: Material.Dark
    Material.accent: theme.accent
    Material.roundedScale: theme.radius

    Rectangle {
        anchors.fill: parent
        color: theme.scrim
    }
    MouseArea { anchors.fill: parent }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(520, parent.width - 48)
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
                objectName: "keyNote"
                // What xAI said about the key comes before where it is kept.
                readonly property bool problem: backend.job !== "key"
                                                && (backend.lastError !== "" || !backend.apiKeySet)
                text: backend.job === "key"
                      ? qsTr("Checking the key with xAI…")
                      : backend.lastError !== ""
                        ? backend.lastError
                        : backend.apiKeySet
                          ? qsTr("Saved on this computer.")
                          : qsTr("Not set. Spoken cuts can't run without it.")
                color: problem ? theme.accent : theme.foreground
                opacity: problem ? 1 : 0.62
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            Rectangle {
                width: parent.width
                height: 36
                radius: theme.radius
                color: theme.background
                border.width: keyField.activeFocus ? 1 : 0
                border.color: theme.accent
                TextInput {
                    id: keyField
                    objectName: "keyField"
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
                    objectName: "forgetKeyButton"
                    text: qsTr("Forget key")
                    visible: backend.apiKeySet
                    enabled: !backend.busy
                    onClicked: {
                        backend.setApiKey("")
                        keyField.text = ""
                    }
                }
                ActionButton {
                    objectName: "saveKeyButton"
                    text: qsTr("Save key")
                    enabled: !backend.busy && keyField.text.trim() !== ""
                    onClicked: root.saveTypedKey()
                }
            }
            CheckBox {
                width: parent.width
                text: qsTr("Keep a B-roll shot's sound under the voice")
                font.pixelSize: 13
                focusPolicy: Qt.NoFocus
                enabled: !backend.busy
                checked: backend.brollMix
                onClicked: backend.brollMix = checked
            }
            RowLayout {
                width: parent.width
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: qsTr("Done")
                    filled: true
                    onClicked: {
                        // A key left in the field is one the person meant to keep.
                        root.saveTypedKey()
                        host.closeSettings()
                    }
                }
            }
        }
    }
}
