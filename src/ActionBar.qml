import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The top bar: BotCut, the file, Lists and the step, Undo, the key, Settings,
// Help, and the one filled button that is the next action. A theme.surface
// band over the workspace with a theme.line under it.
Rectangle {
    id: bar
    property var host
    color: theme.surface
    implicitHeight: 56

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

    // The filled button's word follows the step. A saved rough cut has none.
    readonly property string filledText: {
        if (step === "empty")
            return qsTr("Add shots…")
        if (step === "needsKey")
            return qsTr("Add xAI key…")
        if (step === "shotsReady" || step === "missingShot")
            return qsTr("Cut")
        if (step === "lines" || step === "allDropped")
            return qsTr("Render")
        if (step === "movieUnsaved")
            return qsTr("Save…")
        if (step === "trimmed" || (step === "movieSaved" && !backend.roughCut))
            return qsTr("Export…")
        return ""
    }
    readonly property bool filledEnabled: {
        if (backend.busy || step === "missingShot" || step === "allDropped")
            return false
        if (step === "shotsReady")
            return backend.tray.length > 0 && !backend.trayMissing
        if (step === "lines")
            return host && host.keptLineCount() > 0
        if (step === "trimmed" || step === "movieSaved")
            return (backend.planCut ? backend.plan.duration : backend.duration) > 0
        return true
    }

    readonly property string fileWord: {
        if (!host)
            return ""
        if (host.hasVideo)
            return host.fileName(backend.source)
        if (host.previewing)
            return host.fileName(backend.previewUrl)
        return ""
    }

    readonly property string shotsCount: backend.tray.length > 0 ? String(backend.tray.length) : ""
    readonly property string linesFullCount: backend.selects.length > 0 && host
            ? host.keptLineCount() + "/" + backend.selects.length : ""
    readonly property string linesShortCount: backend.selects.length > 0 && host
            ? String(host.keptLineCount()) : ""
    readonly property string movieCount: {
        if (!host)
            return ""
        var seconds = host.hasVideo ? host.timeline.keptDuration : host.keptSpan()
        return host.lineClock(seconds)
    }

    // Each segment is its word, 6 px, its count, plus 8 px each side. The
    // control pads 2 px around its segments and 2 px between them. Lists adds
    // its word, 4 px each side, and the 8 px gap before the control.
    function segmentWidth(wordMetrics, countMetrics) {
        var w = wordMetrics.width + 16
        if (countMetrics && countMetrics.text !== "")
            w += 6 + countMetrics.width
        return w
    }
    function stepRowWidth(shortLines, shortShots) {
        var w = 8
        w += segmentWidth(shotsWordMetrics, shortShots ? null : shotsCountMetrics)
        w += segmentWidth(linesWordMetrics, shortLines ? linesShortMetrics : linesFullMetrics)
        w += segmentWidth(movieWordMetrics, movieCountMetrics)
        if (homeLink.visible)
            w += homeLink.wordWidth + 16
        return w
    }
    // What is left for the step once the brand, the tools, and the gaps have theirs.
    readonly property real stepRoom: width - 32 - brand.implicitWidth - 8 - rightTools.implicitWidth - 24
    readonly property bool linesNeedShort: stepRowWidth(false, false) > stepRoom
    readonly property bool shotsNeedShort: linesNeedShort && stepRowWidth(true, false) > stepRoom

    TextMetrics {
        id: shotsWordMetrics
        font.pixelSize: 13
        font.weight: Font.DemiBold
        text: qsTr("Shots")
    }
    TextMetrics {
        id: shotsCountMetrics
        font.pixelSize: 11
        font.family: "monospace"
        text: bar.shotsCount
    }
    TextMetrics {
        id: linesWordMetrics
        font.pixelSize: 13
        font.weight: Font.DemiBold
        text: qsTr("Lines")
    }
    TextMetrics {
        id: linesFullMetrics
        font.pixelSize: 11
        font.family: "monospace"
        text: bar.linesFullCount
    }
    TextMetrics {
        id: linesShortMetrics
        font.pixelSize: 11
        font.family: "monospace"
        text: bar.linesShortCount
    }
    TextMetrics {
        id: movieWordMetrics
        font.pixelSize: 13
        font.weight: Font.DemiBold
        text: qsTr("Movie")
    }
    TextMetrics {
        id: movieCountMetrics
        font.pixelSize: 11
        font.family: "monospace"
        text: bar.movieCount
    }

    // One step of the segmented control. The current step is the filled one,
    // a reached step is quiet, and a step not yet reached is quieter still.
    // The count beside the word is its own monospace label.
    component Segment: Rectangle {
        id: step
        property string word
        property string count: ""
        property bool current: false
        property bool reached: false
        signal picked()
        Layout.minimumWidth: implicitWidth
        Layout.preferredWidth: implicitWidth
        implicitWidth: stepRow.implicitWidth + 16
        implicitHeight: 28
        radius: Math.max(0, theme.radius - 2)
        color: current ? theme.raised : (stepHover.hovered && reached ? theme.hover : "transparent")
        HoverHandler { id: stepHover; enabled: step.reached && !step.current }
        Row {
            id: stepRow
            anchors.centerIn: parent
            spacing: 6
            Label {
                anchors.verticalCenter: parent.verticalCenter
                text: step.word
                color: theme.foreground
                opacity: step.current ? 1 : (step.reached ? 0.62 : 0.38)
                font.pixelSize: 13
                font.weight: step.current ? Font.DemiBold : Font.Normal
            }
            Label {
                visible: step.count !== ""
                anchors.verticalCenter: parent.verticalCenter
                text: step.count
                color: theme.foreground
                opacity: step.reached ? 0.62 : 0.38
                font.pixelSize: 11
                font.family: "monospace"
            }
        }
        MouseArea {
            anchors.fill: parent
            enabled: step.reached
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: step.picked()
        }
    }

    // A quiet word in the bar: Lists, Undo, Settings, Help.
    component QuietWord: Item {
        id: quiet
        property string word
        property real wordSize: 13
        property color wordColor: theme.foreground
        property real wordOpacity: 0.62
        readonly property real wordWidth: quietText.implicitWidth
        signal clicked()
        Layout.preferredWidth: quietText.implicitWidth + 8
        Layout.minimumWidth: Layout.preferredWidth
        Layout.preferredHeight: 32
        Layout.alignment: Qt.AlignVCenter
        Rectangle {
            anchors.fill: parent
            radius: Math.max(0, theme.radius - 2)
            color: theme.hover
            visible: quietHover.hovered && quiet.enabled
        }
        HoverHandler { id: quietHover; enabled: quiet.enabled }
        Label {
            id: quietText
            anchors.centerIn: parent
            text: quiet.word
            color: quiet.wordColor
            opacity: quiet.enabled ? quiet.wordOpacity : 0.38
            font.pixelSize: quiet.wordSize
        }
        MouseArea {
            anchors.fill: parent
            enabled: quiet.enabled
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: quiet.clicked()
        }
    }

    function pickShots() {
        host.shotsPinned = true
        if (host.hasVideo)
            backend.showShots()
    }
    function pickLines() {
        if (backend.selects.length === 0)
            return
        host.shotsPinned = false
        if (host.hasVideo)
            backend.showShots()
    }
    function pickMovie() {
        if (!host.hasVideo)
            return
        backend.showMovie()
    }

    Rectangle {
        anchors.bottom: parent.bottom
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
            id: brand
            text: "BotCut"
            color: theme.foreground
            font.pixelSize: 13
            font.weight: Font.DemiBold
            Layout.alignment: Qt.AlignVCenter
        }
        Label {
            visible: bar.fileWord !== ""
            text: bar.fileWord
            color: theme.foreground
            opacity: 0.62
            font.pixelSize: 12
            font.family: "monospace"
            elide: Text.ElideMiddle
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.maximumWidth: Math.max(0, Math.min(implicitWidth, 220))
            Layout.alignment: Qt.AlignVCenter
        }

        Item { Layout.fillWidth: true; Layout.minimumWidth: 0 }

        // The way back to the home of the plan. Only the window closes, not the files.
        QuietWord {
            id: homeLink
            objectName: "listsHome"
            visible: backend.tray.length > 0 || (host && host.hasVideo)
            enabled: !backend.busy
            word: qsTr("Lists")
            onClicked: host.closeProject()
        }

        // Shots, Lines, and Movie as one segmented control. Words and counts.
        Rectangle {
            id: stepControl
            Layout.preferredWidth: stepSegments.implicitWidth + 4
            Layout.minimumWidth: Layout.preferredWidth
            Layout.preferredHeight: 32
            Layout.minimumHeight: 32
            Layout.alignment: Qt.AlignVCenter
            radius: theme.radius
            color: theme.background

            RowLayout {
                id: stepSegments
                anchors.fill: parent
                anchors.margins: 2
                spacing: 2
                Segment {
                    objectName: "shotsStep"
                    word: qsTr("Shots")
                    count: bar.shotsNeedShort ? "" : bar.shotsCount
                    reached: true
                    current: host && host.viewStep === "shots"
                    onPicked: bar.pickShots()
                }
                Segment {
                    objectName: "linesStep"
                    word: qsTr("Lines")
                    count: bar.linesNeedShort ? bar.linesShortCount : bar.linesFullCount
                    reached: backend.selects.length > 0
                    current: host && host.viewStep === "lines"
                    onPicked: bar.pickLines()
                }
                Segment {
                    objectName: "movieStep"
                    word: qsTr("Movie")
                    count: bar.movieCount
                    reached: host && host.hasVideo
                    current: host && host.viewStep === "movie"
                    onPicked: bar.pickMovie()
                }
            }
        }

        Item { Layout.fillWidth: true; Layout.minimumWidth: 0 }

        RowLayout {
            id: rightTools
            spacing: 4
            Layout.alignment: Qt.AlignVCenter

            // The one revise snapshot. Hidden when there is nothing to undo. No redo.
            QuietWord {
                visible: backend.canRevert && !backend.busy
                word: qsTr("Undo")
                onClicked: host.undoRevise()
            }
            // Whether spoken cuts can run. A quiet word, never "connected".
            QuietWord {
                visible: backend.cutMode === "speech"
                word: backend.apiKeySet ? qsTr("Key set") : qsTr("Key needed")
                wordSize: 12
                wordColor: backend.apiKeySet ? theme.foreground : theme.accent
                wordOpacity: backend.apiKeySet ? 0.62 : 1
                onClicked: {
                    host.openSettings()
                    Qt.callLater(function() { host.focusApiKey() })
                }
            }
            QuietWord {
                objectName: "settingsButton"
                word: qsTr("Settings")
                onClicked: {
                    if (host.settingsOpen)
                        host.closeSettings()
                    else
                        host.openSettings()
                }
            }
            QuietWord {
                word: qsTr("Help")
                onClicked: host.helpVisible = !host.helpVisible
            }
            Item {
                visible: filledButton.visible || jobButton.visible
                Layout.preferredWidth: 4
                Layout.minimumWidth: 4
            }
            ActionButton {
                id: filledButton
                objectName: "cutButton"
                text: bar.filledText
                filled: bar.step !== "missingShot" && bar.step !== "allDropped"
                visible: !bar.running && bar.filledText !== ""
                enabled: bar.filledEnabled
                Layout.minimumWidth: implicitWidth
                Layout.maximumWidth: implicitWidth
                Layout.alignment: Qt.AlignVCenter
                onClicked: bar.activateFilled()
            }
            ActionButton {
                id: jobButton
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
}
