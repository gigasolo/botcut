import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material

Button {
    id: button
    property bool filled: false
    // 0..1 fills the button while a job runs. -1 is an ordinary button.
    property real progress: -1

    padding: 14
    topPadding: 8
    bottomPadding: 8
    font.pixelSize: 13
    font.weight: button.filled || button.progress >= 0 ? Font.DemiBold : Font.Normal
    focusPolicy: Qt.NoFocus
    implicitHeight: 36
    Material.accent: theme.accent
    Material.roundedScale: theme.radius

    readonly property color foreground: button.progress >= 0 ? theme.foreground
            : button.filled ? theme.accentForeground : theme.foreground

    contentItem: Text {
        text: button.text
        font: button.font
        color: button.foreground
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        opacity: button.enabled ? 1 : 0.4
    }
    background: Rectangle {
        radius: theme.radius
        clip: true
        color: button.progress >= 0 ? theme.raised
                : button.filled ? theme.accent
                : button.hovered && button.enabled ? theme.hover : "transparent"
        opacity: button.enabled ? 1 : 0.45
        border.width: button.activeFocus ? 2 : 0
        border.color: theme.accent
        Rectangle {
            visible: button.progress >= 0
            width: parent.width * Math.max(0, Math.min(1, button.progress))
            height: parent.height
            color: theme.accent
            opacity: 0.55
        }
    }
    HoverHandler { cursorShape: button.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
}
