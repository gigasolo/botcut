import QtQuick
import QtQuick.Shapes

// Play and pause as filled paths. The only icon button. A 36 px disc on
// theme.raised, in the transport bar under the picture.
Item {
    id: root
    implicitWidth: 36
    implicitHeight: 36
    property bool playing: false
    signal clicked()

    opacity: enabled ? 1 : 0.38

    Rectangle {
        anchors.fill: parent
        radius: theme.radius
        color: hit.containsMouse && root.enabled ? theme.hover : theme.raised
    }

    Shape {
        anchors.centerIn: parent
        width: 16
        height: 16
        visible: !root.playing
        ShapePath {
            fillColor: theme.foreground
            strokeColor: "transparent"
            strokeWidth: 0
            startX: 5
            startY: 2
            PathLine { x: 14; y: 8 }
            PathLine { x: 5; y: 14 }
            PathLine { x: 5; y: 2 }
        }
    }

    Shape {
        anchors.centerIn: parent
        width: 16
        height: 16
        visible: root.playing
        ShapePath {
            fillColor: theme.foreground
            strokeColor: "transparent"
            strokeWidth: 0
            startX: 3
            startY: 2
            PathLine { x: 6; y: 2 }
            PathLine { x: 6; y: 14 }
            PathLine { x: 3; y: 14 }
            PathLine { x: 3; y: 2 }
        }
        ShapePath {
            fillColor: theme.foreground
            strokeColor: "transparent"
            strokeWidth: 0
            startX: 10
            startY: 2
            PathLine { x: 13; y: 2 }
            PathLine { x: 13; y: 14 }
            PathLine { x: 10; y: 14 }
            PathLine { x: 10; y: 2 }
        }
    }

    MouseArea {
        id: hit
        anchors.fill: parent
        enabled: root.enabled
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
