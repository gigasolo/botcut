import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The footer: one sentence, Settings and "?", this step's quiet tools, and one
// filled button that is the next action. A theme.surface band under the stage.
Rectangle {
    id: bar
    property var host
    color: theme.surface
    implicitHeight: Math.max(56, sentence.implicitHeight + 20)

    readonly property string step: host ? host.displayStep : ""
    readonly property bool running: backend.job !== ""

    function activateFilled() {
        if (!host || backend.busy || running)
            return
        if (step === "empty") {
            backend.addVideosDialog()
            return
        }
        if (step === "needsKey") {
            host.openSettings()
            Qt.callLater(function() { host.focusApiKey() })
            return
        }
        if (step === "shotsReady") {
            if (backend.tray.length > 0 && !backend.trayMissing)
                backend.startCut()
            return
        }
        if (step === "lines" && host.keptLineCount() > 0)
            backend.renderSelects()
        else if (step === "movieUnsaved" || step === "trimmed"
                 || (step === "movieSaved" && !backend.roughCut))
            host.exportVideo()
    }

    Rectangle {
        anchors.top: parent.top
        width: parent.width
        height: 1
        color: theme.line
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        spacing: 8

        Label {
            id: sentence
            Layout.fillWidth: true
            Layout.minimumWidth: 240
            Layout.alignment: Qt.AlignVCenter
            text: host ? host.actionSentence : ""
            color: host && (host.actionNeedsYou || host.noticeText !== "") ? theme.accent : theme.foreground
            opacity: host && (host.noticeText !== "" || host.actionNeedsYou) ? 1 : 0.62
            font.pixelSize: 13
            wrapMode: Text.WordWrap
            verticalAlignment: Text.AlignVCenter
        }

        Item {
            objectName: "settingsButton"
            Layout.preferredWidth: settingsText.implicitWidth + 16
            Layout.minimumWidth: Layout.preferredWidth
            Layout.preferredHeight: 36
            Layout.alignment: Qt.AlignVCenter
            Label {
                id: settingsText
                anchors.centerIn: parent
                text: qsTr("Settings")
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 13
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (host.settingsOpen)
                        host.closeSettings()
                    else
                        host.openSettings()
                }
            }
        }
        Item {
            Layout.preferredWidth: 32
            Layout.minimumWidth: 32
            Layout.preferredHeight: 36
            Layout.alignment: Qt.AlignVCenter
            Label {
                anchors.centerIn: parent
                text: "?"
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 16
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: host.helpVisible = !host.helpVisible
            }
        }

        ActionButton {
            text: qsTr("Open a saved list…")
            visible: !bar.running && bar.step === "empty"
            enabled: !backend.busy
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: backend.openCutListDialog()
        }
        ActionButton {
            text: qsTr("Keep every shot instead")
            visible: !bar.running && bar.step === "needsKey"
            enabled: !backend.busy
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: backend.cutMode = "assemble"
        }
        ActionButton {
            id: cutButton
            objectName: "cutButton"
            text: backend.selects.length > 0 ? qsTr("Cut again…") : qsTr("Cut")
            filled: bar.step === "shotsReady"
            visible: !bar.running && (bar.step === "shotsReady" || bar.step === "lines"
                                       || bar.step === "allDropped")
            enabled: backend.tray.length > 0 && !backend.busy && !backend.trayMissing
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: {
                if (backend.selects.length > 0)
                    host.confirmCutOpen = true
                else
                    backend.startCut()
            }
        }
        ActionButton {
            objectName: "showFileButton"
            text: qsTr("Show the file")
            filled: false
            visible: !bar.running && bar.step === "movieSaved" && backend.roughCut
            enabled: !backend.busy
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: backend.showFile()
        }
        ActionButton {
            objectName: "captionsButton"
            text: qsTr("Captions")
            visible: !bar.running && bar.step === "movieSaved" && backend.roughCut
            enabled: !backend.busy && !(backend.planCut && backend.plan.unexported)
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: backend.writeCaptions()
        }
        ActionButton {
            objectName: "shortButton"
            text: qsTr("Vertical short")
            visible: !bar.running && bar.step === "movieSaved" && backend.roughCut
            enabled: !backend.busy && !(backend.planCut && backend.plan.unexported)
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: backend.makeShort()
        }
        ActionButton {
            text: qsTr("Export another size…")
            visible: !bar.running && bar.step === "movieSaved" && backend.roughCut
                     && host && !host.looseCut && !host.unexported
            enabled: !backend.busy && (backend.planCut ? backend.plan.duration : backend.duration) > 0
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: host.exportVideo()
        }
        ActionButton {
            text: qsTr("Render")
            filled: bar.step === "lines" && host && host.keptLineCount() > 0 && !backend.busy
            visible: !bar.running && (bar.step === "lines" || bar.step === "allDropped")
            enabled: !backend.busy && bar.step !== "allDropped"
                     && (bar.step !== "lines" || (host && host.keptLineCount() > 0))
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: backend.renderSelects()
        }
        ActionButton {
            text: qsTr("Add shots…")
            filled: true
            visible: !bar.running && bar.step === "empty"
            enabled: !backend.busy
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: backend.addVideosDialog()
        }
        ActionButton {
            text: qsTr("Add xAI key…")
            filled: true
            visible: !bar.running && bar.step === "needsKey"
            enabled: !backend.busy
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: {
                host.openSettings()
                Qt.callLater(function() { host.focusApiKey() })
            }
        }
        ActionButton {
            text: qsTr("Save…")
            filled: true
            visible: !bar.running && bar.step === "movieUnsaved"
            enabled: !backend.busy
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: host.exportVideo()
        }
        ActionButton {
            text: qsTr("Export…")
            filled: true
            visible: !bar.running && (bar.step === "trimmed"
                                       || (bar.step === "movieSaved" && !backend.roughCut))
            enabled: !backend.busy && (backend.planCut ? backend.plan.duration : backend.duration) > 0
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
            onClicked: host.exportVideo()
        }
        ActionButton {
            visible: bar.running
            text: backend.jobText
            progress: backend.progress
            enabled: false
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.alignment: Qt.AlignVCenter
        }
    }
}
