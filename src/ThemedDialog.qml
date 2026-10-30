import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material

Dialog {
    id: dialog
    modal: true
    focus: true
    padding: 24
    Material.theme: Material.Dark
    Material.accent: theme.accent
    Material.roundedScale: theme.radius
    Material.elevation: 0
    closePolicy: Popup.NoAutoClose

    background: Rectangle {
        color: theme.surface
        radius: theme.radius
        border.color: theme.line
    }
    Overlay.modal: Rectangle { color: theme.scrim }
    header: Label {
        text: dialog.title
        color: theme.foreground
        font.pixelSize: 22
        font.weight: Font.DemiBold
        padding: 24
        bottomPadding: 0
        elide: Text.ElideRight
    }
}
