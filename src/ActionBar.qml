import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The top bar: BotCut, the file, and the steps as a breadcrumb, with Settings
// and Help on the right. The next action and its sentence live together in the
// action bar at the bottom of the window.
Rectangle {
    id: bar
    property var host
    color: theme.surface
    implicitHeight: 48

    readonly property string fileWord: {
        if (!host)
            return ""
        if (host.hasVideo)
            return host.fileName(backend.source)
        if (host.previewing)
            return host.fileName(backend.previewUrl)
        return ""
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

    // One step of the breadcrumb. The current step is full strength with an
    // accent underline. A reached step is quiet and clickable. A step not yet
    // reached is quieter still and does nothing.
    component Step: Item {
        id: step
        property string word
        property bool current: false
        property bool reached: false
        signal picked()
        readonly property bool live: reached && !current && enabled
        Layout.preferredWidth: stepText.implicitWidth + 16
        Layout.minimumWidth: Layout.preferredWidth
        Layout.preferredHeight: 32
        Layout.alignment: Qt.AlignVCenter
        Rectangle {
            anchors.fill: parent
            radius: Math.max(0, theme.radius - 2)
            color: theme.hover
            visible: stepHover.hovered && step.live
        }
        HoverHandler { id: stepHover; enabled: step.live }
        Label {
            id: stepText
            anchors.centerIn: parent
            text: step.word
            color: theme.foreground
            opacity: !step.enabled ? 0.38 : (step.current ? 1 : (step.reached ? 0.62 : 0.38))
            font.pixelSize: 13
            font.weight: step.current ? Font.DemiBold : Font.Normal
        }
        Rectangle {
            visible: step.current
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            width: stepText.implicitWidth
            height: 2
            color: theme.accent
        }
        MouseArea {
            anchors.fill: parent
            enabled: step.live
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: step.picked()
        }
    }

    component Crumb: Label {
        text: "›"
        color: theme.foreground
        opacity: 0.38
        font.pixelSize: 13
        Layout.alignment: Qt.AlignVCenter
    }

    // A quiet word in the bar: Settings, Help.
    component QuietWord: Item {
        id: quiet
        property string word
        signal clicked()
        Layout.preferredWidth: quietText.implicitWidth + 16
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
            color: theme.foreground
            opacity: quiet.enabled ? 0.62 : 0.38
            font.pixelSize: 13
        }
        MouseArea {
            anchors.fill: parent
            enabled: quiet.enabled
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: quiet.clicked()
        }
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

        // Lists is the way back to the home of the plan. It closes the window's
        // project and keeps the files on disk.
        Step {
            id: homeLink
            objectName: "listsHome"
            visible: backend.tray.length > 0 || (host && host.hasVideo)
            enabled: !backend.busy
            word: qsTr("Lists")
            reached: true
            onPicked: host.closeProject()
        }
        Crumb { visible: homeLink.visible }
        Step {
            objectName: "shotsStep"
            word: qsTr("Shots")
            reached: true
            current: host && host.viewStep === "shots"
            onPicked: bar.pickShots()
        }
        Crumb {}
        Step {
            objectName: "linesStep"
            word: qsTr("Lines")
            reached: backend.selects.length > 0
            current: host && host.viewStep === "lines"
            onPicked: bar.pickLines()
        }
        Crumb {}
        Step {
            objectName: "movieStep"
            word: qsTr("Movie")
            reached: host && host.hasVideo
            current: host && host.viewStep === "movie"
            onPicked: bar.pickMovie()
        }

        Item { Layout.fillWidth: true; Layout.minimumWidth: 0 }

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
    }
}
