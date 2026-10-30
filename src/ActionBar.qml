import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: bar
    property var host
    color: theme.background
    implicitHeight: 56

    readonly property string step: host ? host.displayStep : ""
    readonly property bool running: backend.job !== ""
    readonly property bool movieStep: step === "movieSaved" || step === "movieUnsaved" || step === "trimmed"

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
        color: "#2c2c2f"
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        spacing: 8

        Label {
            Layout.fillWidth: true
            Layout.minimumWidth: 24
            text: host ? host.actionSentence : ""
            color: host && (host.actionNeedsYou || host.noticeText !== "") ? theme.accent : theme.foreground
            opacity: host && (host.noticeText !== "" || host.actionNeedsYou) ? 1 : 0.62
            font.pixelSize: 13
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }

        ActionButton {
            text: qsTr("Open a saved list…")
            visible: !bar.running && bar.step === "empty"
            enabled: !backend.busy
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            onClicked: backend.openCutListDialog()
        }
        ActionButton {
            text: qsTr("Keep every shot instead")
            visible: !bar.running && bar.step === "needsKey"
            enabled: !backend.busy
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
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
            onClicked: {
                if (backend.selects.length > 0)
                    host.confirmCutOpen = true
                else
                    backend.startCut()
            }
        }
        ActionButton {
            objectName: "captionsButton"
            text: qsTr("Captions")
            visible: !bar.running && backend.roughCut && bar.movieStep
            enabled: !backend.busy && !(backend.planCut && backend.plan.unexported)
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            onClicked: backend.writeCaptions()
        }
        ActionButton {
            objectName: "shortButton"
            text: qsTr("Vertical short")
            visible: !bar.running && backend.roughCut && bar.movieStep
            enabled: !backend.busy && !(backend.planCut && backend.plan.unexported)
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            onClicked: backend.makeShort()
        }
        ActionButton {
            text: qsTr("Export another size…")
            visible: !bar.running && bar.step === "movieSaved" && backend.roughCut
                     && host && !host.looseCut && !host.unexported
            enabled: !backend.busy && (backend.planCut ? backend.plan.duration : backend.duration) > 0
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
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
            onClicked: backend.renderSelects()
        }
        ActionButton {
            text: qsTr("Add shots…")
            filled: true
            visible: !bar.running && bar.step === "empty"
            enabled: !backend.busy
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
            onClicked: backend.addVideosDialog()
        }
        ActionButton {
            text: qsTr("Add xAI key…")
            filled: true
            visible: !bar.running && bar.step === "needsKey"
            enabled: !backend.busy
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
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
            onClicked: host.exportVideo()
        }
        ActionButton {
            visible: bar.running
            text: backend.jobText
            progress: backend.progress
            enabled: false
            Layout.minimumWidth: implicitWidth
            Layout.maximumWidth: implicitWidth
        }
    }
}
