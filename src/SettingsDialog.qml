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
        height: Math.min(column.implicitHeight + footerRow.implicitHeight + 60, parent.height - 32)
        radius: theme.radius
        color: theme.surface
        border.color: theme.line
        clip: true

        MouseArea { anchors.fill: parent }

        Flickable {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: footerRow.top
            anchors.topMargin: 24
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            anchors.bottomMargin: 12
            contentWidth: width
            contentHeight: column.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 4 }

            Column {
                id: column
                width: parent.width
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
                    onAccepted: root.saveTypedKey()
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
                spacing: 8
                Label {
                    text: qsTr("Zoom")
                    color: theme.foreground
                    font.pixelSize: 13
                }
                Item { Layout.fillWidth: true }
                Repeater {
                    model: [
                        { value: "off", word: qsTr("Off") },
                        { value: "subtle", word: qsTr("Subtle") },
                        { value: "medium", word: qsTr("Medium") },
                        { value: "bold", word: qsTr("Bold") }
                    ]
                    ActionButton {
                        required property var modelData
                        text: modelData.word
                        filled: backend.zoom === modelData.value
                        enabled: !backend.busy
                        onClicked: backend.zoom = modelData.value
                    }
                }
            }
            Label {
                objectName: "zoomNote"
                width: parent.width
                wrapMode: Text.WordWrap
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 12
                text: backend.zoom === "subtle"
                      ? qsTr("Subtle 6% eye-locked shifts on major cuts (8s hold) with a gentle 3% drift on long takes.")
                      : backend.zoom === "bold"
                        ? qsTr("Dynamic 15% eye-locked framing (4.5s hold) with a 7% slow push for punchy social edits.")
                        : backend.zoom !== "off"
                          ? qsTr("Balanced 10% eye-locked framing at cuts (6s hold) and key lines, with a 5% slow push on long takes.")
                          : qsTr("The picture plays as it was shot.")
            }
            RowLayout {
                width: parent.width
                spacing: 6
                Label {
                    text: qsTr("Video type")
                    color: theme.foreground
                    font.pixelSize: 13
                }
                Item { Layout.fillWidth: true }
                Repeater {
                    model: [
                        { value: "internal", word: qsTr("Internal") },
                        { value: "marketing", word: qsTr("Marketing") },
                        { value: "monologue", word: qsTr("Monologue") }
                    ]
                    ActionButton {
                        required property var modelData
                        text: modelData.word
                        filled: backend.preset === modelData.value
                        enabled: !backend.busy
                        onClicked: backend.applyPreset(modelData.value)
                    }
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
                        { value: "landscape", word: qsTr("16:9") },
                        { value: "portrait", word: qsTr("9:16") }
                    ]
                    ActionButton {
                        required property var modelData
                        text: modelData.word
                        filled: backend.aspect === modelData.value
                        enabled: !backend.busy
                        onClicked: backend.aspect = modelData.value
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
                        filled: backend.resolution === modelData.value
                        enabled: !backend.busy
                        onClicked: backend.resolution = modelData.value
                    }
                }
            }
            CheckBox {
                width: parent.width
                text: qsTr("Show speaker picture-in-picture over landscape slides and screens")
                font.pixelSize: 13
                focusPolicy: Qt.NoFocus
                enabled: !backend.busy
                checked: Boolean(backend && backend.pip)
                onClicked: if (backend && backend.pip !== undefined) backend.pip = checked
            }
        }
        }

        RowLayout {
            id: footerRow
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            anchors.bottomMargin: 20
            Item { Layout.fillWidth: true }
            ActionButton {
                text: qsTr("Done")
                filled: true
                focusPolicy: Qt.TabFocus
                onClicked: {
                    // A key left in the field is one the person meant to keep.
                    root.saveTypedKey()
                    host.closeSettings()
                }
            }
        }
    }
}
