import QtQuick
import QtQuick.Shapes

// Play and pause as filled paths. The only icon button.
Item {
    id: root
    implicitWidth: 44
    implicitHeight: 44
    property bool playing: false
    signal clicked()

    opacity: enabled ? 1 : 0.45

    Rectangle {
        anchors.fill: parent
        radius: theme.radius
        color: theme.raised
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
        anchors.fill: parent
        enabled: root.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
