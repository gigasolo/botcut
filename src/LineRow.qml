import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One spoken span: its start, its words, and one word that flips whether it
// stays. Drop on a kept line, Keep on a dropped one. A dropped line's words
// are quiet and struck through. The selected row also offers Play.
Item {
    id: row
    required property int index
    required property var modelData
    property string timeText: ""
    property string reasonText: ""
    property string coverText: ""
    property string coverStill: ""
    property bool selected: false
    property bool marked: false
    signal picked()
    signal playRequested()

    width: ListView.view ? ListView.view.width : implicitWidth
    height: body.implicitHeight + 20
    readonly property bool dropped: modelData && modelData.keep === false
    readonly property bool unsure: modelData && modelData.reason === "unique?"
    // The user flipped this line. Read off the reason the model already keeps.
    readonly property bool byYou: modelData && (modelData.reason === "dropped" || modelData.reason === "restored")
    // The one line the editor moved to the front. It keeps its place in this list.
    readonly property bool opens: modelData && modelData.hook === true && !dropped
    readonly property bool detailShown: reasonText !== "" || coverText !== "" || selected || opens

    Rectangle {
        id: fill
        anchors.fill: parent
        anchors.bottomMargin: 4
        radius: theme.radius
        color: row.selected || row.marked ? theme.selected
               : (rowHover.hovered ? theme.hover : "transparent")
    }
    HoverHandler { id: rowHover }

    MouseArea {
        anchors.fill: fill
        onClicked: row.picked()
    }

    // A word in the row that acts: Drop, Keep, Play, Remove B-roll. A hover
    // pill behind it, quiet while a job runs.
    component RowWord: Item {
        id: rowWord
        property string word
        signal chosen()
        implicitWidth: wordLabel.implicitWidth + 12
        implicitHeight: 24
        Layout.alignment: Qt.AlignTop
        Rectangle {
            anchors.fill: parent
            radius: Math.max(0, theme.radius - 2)
            color: theme.hover
            visible: wordArea.containsMouse && !backend.busy
        }
        Label {
            id: wordLabel
            anchors.centerIn: parent
            text: rowWord.word
            color: theme.foreground
            opacity: backend.busy ? 0.38 : 1
            font.pixelSize: 13
        }
        MouseArea {
            id: wordArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: backend.busy ? Qt.ArrowCursor : Qt.PointingHandCursor
            onClicked: {
                if (!backend.busy)
                    rowWord.chosen()
            }
        }
    }

    function plainWord(word) {
        return String(word).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }
    // The line's words, with each cut on offer as a link named by its number.
    function markedWords() {
        var line = row.modelData
        var words = String(line.text).split(" ")
        var opens = {}
        var closes = {}
        for (var c = 0; c < line.cuts.length; c++) {
            var cut = line.cuts[c]
            if (cut.from < 0 || cut.through >= words.length || cut.from > cut.through)
                continue
            opens[cut.from] = { number: c, taken: cut.cut === true }
            closes[cut.through] = cut.cut === true
        }
        var out = []
        for (var i = 0; i < words.length; i++) {
            var word = plainWord(words[i])
            if (opens[i] !== undefined)
                word = "<a href=\"" + opens[i].number + "\">" + (opens[i].taken ? "<s>" : "") + word
            if (closes[i] !== undefined)
                word += (closes[i] ? "</s>" : "") + "</a>"
            out.push(word)
        }
        return out.join(" ")
    }

    Column {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 12
        anchors.rightMargin: 8
        anchors.topMargin: 8
        spacing: 4

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
                Layout.topMargin: 4
                Layout.minimumWidth: 36
            }
            Label {
                objectName: "lineWords"
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                Layout.topMargin: 4
                // A kept line with cuts inside it marks them: struck through when
                // taken, underlined when left in. A click on one flips it.
                readonly property bool marked: !row.dropped && row.modelData !== undefined && row.modelData !== null
                                               && row.modelData.cuts !== undefined && row.modelData.cuts.length > 0
                text: marked ? row.markedWords()
                             : (row.modelData && row.modelData.text !== undefined ? row.modelData.text : "")
                textFormat: marked ? Text.StyledText : Text.PlainText
                linkColor: Qt.rgba(theme.foreground.r, theme.foreground.g, theme.foreground.b, 0.5)
                color: theme.foreground
                opacity: row.dropped ? 0.38 : 1
                wrapMode: Text.WordWrap
                font.pixelSize: 13
                font.strikeout: row.dropped
                onLinkActivated: link => {
                    if (!backend.busy && row.modelData)
                        backend.toggleWordCut(row.modelData.id, Number(link))
                }
            }
            // The one control on every row. It reads the state it would leave.
            RowWord {
                objectName: "flipWord"
                word: row.dropped ? qsTr("Keep") : qsTr("Drop")
                onChosen: {
                    if (!row.modelData)
                        return
                    if (row.dropped)
                        backend.restoreSelect(row.modelData.id)
                    else
                        backend.dropSelect(row.modelData.id)
                }
            }
        }

        RowLayout {
            visible: row.detailShown
            width: parent.width
            spacing: 8
            Item { Layout.preferredWidth: 36; Layout.minimumWidth: 36; Layout.preferredHeight: 1 }
            // The beat the run starts on, on the run's first line.
            Rectangle {
                objectName: "coverStill"
                visible: row.coverStill !== ""
                Layout.preferredWidth: 64
                Layout.preferredHeight: 36
                Layout.alignment: Qt.AlignVCenter
                radius: Math.max(0, theme.radius - 2)
                color: theme.raised
                clip: true
                Image {
                    anchors.fill: parent
                    source: row.coverStill
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    sourceSize.width: 128
                }
            }
            Label {
                objectName: "opensLabel"
                visible: row.opens
                Layout.alignment: Qt.AlignVCenter
                text: qsTr("Opens the movie")
                color: theme.accent
                font.pixelSize: 12
            }
            Label {
                visible: row.reasonText !== ""
                Layout.alignment: Qt.AlignVCenter
                text: row.byYou ? qsTr("You · %1").arg(row.reasonText) : row.reasonText
                color: row.unsure ? theme.accent : theme.foreground
                opacity: row.unsure ? 1 : 0.62
                font.pixelSize: 12
            }
            Label {
                visible: row.coverText !== ""
                Layout.alignment: Qt.AlignVCenter
                text: row.coverText
                color: theme.foreground
                opacity: 0.62
                font.pixelSize: 12
                elide: Text.ElideMiddle
                Layout.maximumWidth: 240
            }
            Item { Layout.fillWidth: true }
            RowWord {
                visible: row.selected
                word: qsTr("Play")
                onChosen: row.playRequested()
            }
            RowWord {
                objectName: "putBackWord"
                visible: row.selected && row.opens
                word: qsTr("Put it back")
                onChosen: backend.clearHook()
            }
            RowWord {
                visible: row.selected && row.coverText !== ""
                word: qsTr("Remove B-roll")
                onChosen: {
                    if (row.modelData)
                        backend.clearCover(row.modelData.id)
                }
            }
        }
    }
}
