import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One spoken span: its start, its words, why it is where it is, and whether it
// stays. Keep and Drop are both on every row; the one in force is filled. A
// kept row carries the accent at its left edge; a dropped row's words are
// struck through. A filtered-out row is 0 px tall and still in the list.
Item {
    id: row
    required property int index
    required property var modelData
    property string timeText: ""
    property string reasonText: ""
    property string coverText: ""
    property bool selected: false
    property bool marked: false
    property bool shown: true
    signal picked()
    signal playRequested()

    width: ListView.view ? ListView.view.width : implicitWidth
    height: shown ? body.implicitHeight + 20 : 0
    visible: shown
    readonly property bool dropped: modelData && modelData.keep === false
    readonly property bool unsure: modelData && modelData.reason === "unique?"
    // The user flipped this line. Read off the reason the model already keeps.
    readonly property bool byYou: modelData && (modelData.reason === "dropped" || modelData.reason === "restored")

    Rectangle {
        id: fill
        anchors.fill: parent
        anchors.bottomMargin: 4
        radius: theme.radius
        color: row.selected || row.marked ? theme.selected
               : (rowHover.hovered ? theme.hover : "transparent")
    }
    HoverHandler { id: rowHover }

    Rectangle {
        visible: !row.dropped
        width: 2
        height: fill.height
        radius: 1
        color: theme.accent
    }

    MouseArea {
        anchors.fill: fill
        onClicked: row.picked()
    }

    // Keep or Drop. The word in force is filled with the accent and does
    // nothing when clicked. The other one flips the line.
    component KeepWord: Rectangle {
        id: keepWord
        property string word
        property bool active: false
        signal chosen()
        width: keepLabel.implicitWidth + 16
        height: 20
        radius: Math.max(0, theme.radius - 2)
        color: active ? theme.accent
               : (keepArea.containsMouse && !backend.busy ? theme.hover : "transparent")
        Label {
            id: keepLabel
            anchors.centerIn: parent
            text: keepWord.word
            color: keepWord.active ? theme.accentForeground : theme.foreground
            opacity: backend.busy ? 0.38 : (keepWord.active ? 1 : 0.62)
            font.pixelSize: 12
            font.weight: keepWord.active ? Font.DemiBold : Font.Normal
        }
        MouseArea {
            id: keepArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: backend.busy || keepWord.active ? Qt.ArrowCursor : Qt.PointingHandCursor
            onClicked: {
                if (!backend.busy && !keepWord.active)
                    keepWord.chosen()
            }
        }
    }

    Column {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        anchors.topMargin: 8
        spacing: 6

        RowLayout {
            width: parent.width
            spacing: 8
            // One clock column, so the words line up from row to row.
            Label {
                text: row.timeText
                color: theme.foreground
                opacity: row.dropped ? 0.38 : 0.62
                font.pixelSize: 12
                font.family: "monospace"
                Layout.alignment: Qt.AlignTop
                Layout.minimumWidth: 36
            }
            Label {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                text: row.modelData && row.modelData.text !== undefined ? row.modelData.text : ""
                color: theme.foreground
                opacity: row.dropped ? 0.38 : 1
                wrapMode: Text.WordWrap
                font.pixelSize: 13
                font.strikeout: row.dropped
            }
        }

        RowLayout {
            width: parent.width
            spacing: 12
            Label {
                visible: row.reasonText !== ""
                text: row.byYou ? qsTr("You · %1").arg(row.reasonText) : row.reasonText
                color: row.unsure ? theme.accent : theme.foreground
                opacity: 0.62
                font.pixelSize: 12
            }
            Label {
                visible: row.coverText !== ""
                text: row.coverText
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 12
                elide: Text.ElideMiddle
                Layout.maximumWidth: 160
            }
            Label {
                visible: row.selected
                text: qsTr("Play")
                color: theme.foreground
                opacity: backend.busy ? 0.38 : 1
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: backend.busy ? Qt.ArrowCursor : Qt.PointingHandCursor
                    onClicked: {
                        if (!backend.busy)
                            row.playRequested()
                    }
                }
            }
            Label {
                visible: row.selected && row.coverText !== ""
                text: qsTr("Remove B-roll")
                color: theme.foreground
                opacity: backend.busy ? 0.38 : 1
                font.pixelSize: 13
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: backend.busy ? Qt.ArrowCursor : Qt.PointingHandCursor
                    onClicked: {
                        if (backend.busy || !row.modelData)
                            return
                        backend.clearCover(row.modelData.id)
                    }
                }
            }
            Item { Layout.fillWidth: true }
            // The pair sits in the same place whether the row is selected or not.
            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: pairRow.width + 4
                implicitHeight: 24
                radius: theme.radius
                color: theme.background
                Row {
                    id: pairRow
                    x: 2
                    y: 2
                    spacing: 2
                    KeepWord {
                        word: qsTr("Keep")
                        active: !row.dropped
                        onChosen: backend.restoreSelect(row.modelData.id)
                    }
                    KeepWord {
                        word: qsTr("Drop")
                        active: row.dropped
                        onChosen: backend.dropSelect(row.modelData.id)
                    }
                }
            }
        }
    }
}
