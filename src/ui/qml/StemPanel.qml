import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Kompaktes Panel pro Deck. Zeigt Stem-Zeilen (Vol/Mute/Solo) und
// Separations-Buttons wenn noch keine Stems da sind.

Rectangle {
    id: root
    color: "#0e141d"
    radius: 6
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, 0.05)

    property var deckModel: null
    property color deckColor: "#00e0ff"

    // aktualisiert via stateChanged des Decks
    property var stemList: []
    property bool hasStems: false
    property bool stemMode: false

    function refresh() {
        if (!deckModel) { stemList = []; hasStems = false; stemMode = false; return }
        hasStems = deckModel.hasStems()
        stemMode = deckModel.stemMode()
        stemList = deckModel.stemNames()
    }
    Component.onCompleted: refresh()

    Connections {
        target: root.deckModel
        function onStateChanged() { root.refresh() }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 4

        // Header
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Text {
                text: "STEMS"
                color: root.deckColor
                font.pixelSize: 10
                font.letterSpacing: 2
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            Text {
                visible: root.hasStems
                text: root.stemMode ? "AKTIV" : "OFF"
                color: root.stemMode ? "#4ade80" : "#556677"
                font.pixelSize: 9
                font.bold: true
            }
            Switch {
                visible: root.hasStems
                checked: root.stemMode
                onToggled: if (root.deckModel) root.deckModel.setStemMode(checked)
            }
        }

        // Wenn noch keine Stems → Separations-Buttons
        RowLayout {
            visible: !root.hasStems
            Layout.fillWidth: true
            spacing: 4
            Button {
                Layout.fillWidth: true
                text: "4 STEMS"
                font.pixelSize: 10
                onClicked: if (root.deckModel) root.deckModel.separateStems("htdemucs")
                ToolTip.visible: hovered
                ToolTip.text: "Demucs htdemucs (drums/bass/other/vocals) — kann Minuten dauern"
            }
            Button {
                Layout.fillWidth: true
                text: "6 STEMS"
                font.pixelSize: 10
                onClicked: if (root.deckModel) root.deckModel.separateStems("htdemucs_6s")
                ToolTip.visible: hovered
                ToolTip.text: "Demucs htdemucs_6s (+ guitar + piano) — dauert länger"
            }
        }

        // Stem-Zeilen
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 2
            visible: root.hasStems
            Repeater {
                model: root.stemList
                delegate: RowLayout {
                    id: row
                    Layout.fillWidth: true
                    spacing: 4
                    property string stemName: modelData

                    Text {
                        text: row.stemName.toUpperCase()
                        color: "#c9d5e1"
                        font.pixelSize: 9
                        font.bold: true
                        Layout.preferredWidth: 50
                        elide: Text.ElideRight
                    }
                    Slider {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 16
                        from: 0.0
                        to: 1.4
                        value: root.deckModel ? root.deckModel.stemVolume(row.stemName) : 1.0
                        onMoved: if (root.deckModel) root.deckModel.setStemVolume(row.stemName, value)
                    }
                    Rectangle {
                        Layout.preferredWidth: 20
                        Layout.preferredHeight: 16
                        radius: 3
                        property bool muted: root.deckModel ? root.deckModel.stemMuted(row.stemName) : false
                        color: muted ? "#ef4444" : "#1c2534"
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, muted ? 0.3 : 0.1)
                        Text {
                            anchors.centerIn: parent
                            text: "M"
                            color: parent.muted ? "#0a0e14" : "#556677"
                            font.pixelSize: 9
                            font.bold: true
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: if (root.deckModel) root.deckModel.setStemMuted(row.stemName, !parent.muted)
                        }
                    }
                    Rectangle {
                        Layout.preferredWidth: 20
                        Layout.preferredHeight: 16
                        radius: 3
                        property bool soloed: root.deckModel ? root.deckModel.stemSoloed(row.stemName) : false
                        color: soloed ? "#ffb020" : "#1c2534"
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, soloed ? 0.3 : 0.1)
                        Text {
                            anchors.centerIn: parent
                            text: "S"
                            color: parent.soloed ? "#0a0e14" : "#556677"
                            font.pixelSize: 9
                            font.bold: true
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: if (root.deckModel) root.deckModel.setStemSoloed(row.stemName, !parent.soloed)
                        }
                    }
                }
            }
        }
    }
}
