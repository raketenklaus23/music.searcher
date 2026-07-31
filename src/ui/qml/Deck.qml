import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import "controls"

Rectangle {
    id: deck
    color: "#131a24"
    radius: 12
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, 0.06)

    property var  deckModel: null        // DeckBridge Instanz
    property color neon: "#00e0ff"
    property string sideLabel: "A"

    // Beat-Pulse Animation — Rand-Glow synchron zum Beat
    Rectangle {
        id: pulseRing
        anchors.fill: parent
        radius: parent.radius
        color: "transparent"
        border.width: 2
        border.color: deck.neon
        opacity: 0.0
    }
    SequentialAnimation on opacity {
        id: pulseAnim
        running: false
        NumberAnimation { target: pulseRing; property: "opacity"; from: 0.7; to: 0.0; duration: 220; easing.type: Easing.OutQuad }
    }
    Connections {
        target: deck.deckModel
        function onPositionChanged() {
            // Trigger Pulse an jedem Beat (nur wenn spielend)
            if (deck.deckModel.isPlaying && deck.deckModel.beatInBar >= 1 && deck.deckModel.beatInBar !== deck._lastBeat) {
                deck._lastBeat = deck.deckModel.beatInBar
                pulseAnim.restart()
            }
        }
    }
    property int _lastBeat: 0

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // Header: Side + Titel + BPM/Key
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: deck.sideLabel
                color: deck.neon
                font.pixelSize: 28
                font.bold: true
                font.letterSpacing: 3
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Text {
                    text: (deck.deckModel && deck.deckModel.title) ? deck.deckModel.title : "— kein Track —"
                    color: "#e6f1ff"
                    font.pixelSize: 14
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text {
                    text: (deck.deckModel && deck.deckModel.artist) ? deck.deckModel.artist : ""
                    color: "#8899aa"
                    font.pixelSize: 11
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
            ColumnLayout {
                spacing: 0
                Text {
                    text: deck.deckModel ? deck.deckModel.effectiveBpm.toFixed(1) : "0.0"
                    color: deck.neon
                    font.pixelSize: 22
                    font.bold: true
                    horizontalAlignment: Text.AlignRight
                }
                RowLayout {
                    spacing: 6
                    Text {
                        text: (deck.deckModel && deck.deckModel.bpm > 0) ? "orig " + deck.deckModel.bpm.toFixed(1) : ""
                        color: "#556677"
                        font.pixelSize: 9
                    }
                    Text {
                        text: (deck.deckModel && deck.deckModel.musicalKey) ? deck.deckModel.musicalKey : ""
                        color: "#ff2fbf"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }
        }

        // Waveform-Placeholder (kommt in Phase 3 als Shader)
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 96
            radius: 6
            color: "#0a1018"
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.05)

            // Playhead-Position
            Rectangle {
                visible: deck.deckModel && deck.deckModel.isLoaded
                width: 2
                height: parent.height
                color: deck.neon
                x: {
                    if (!deck.deckModel || deck.deckModel.durationSec <= 0) return 0
                    return (deck.deckModel.positionSec / deck.deckModel.durationSec) * parent.width
                }
            }

            Text {
                anchors.centerIn: parent
                visible: !deck.deckModel || !deck.deckModel.isLoaded
                text: "Track auf Deck ziehen"
                color: "#556677"
                font.pixelSize: 11
                font.letterSpacing: 2
            }

            // Drop-Zone: Track aus Library ziehen (interpretiert als text/plain track_id)
            DropArea {
                anchors.fill: parent
                keys: ["application/x-musicsearcher-trackid"]
                onDropped: (drop) => {
                    var tid = parseInt(drop.getDataAsString("application/x-musicsearcher-trackid"))
                    if (!isNaN(tid) && deck.deckModel) deck.deckModel.loadTrack(tid)
                }
            }

            // Klick zum Seek
            MouseArea {
                anchors.fill: parent
                onClicked: (m) => {
                    if (!deck.deckModel || deck.deckModel.durationSec <= 0) return
                    deck.deckModel.seek(m.x / width * deck.deckModel.durationSec)
                }
            }
        }

        // Transport-Buttons
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            NeonButton {
                text: "CUE"
                neon: "#ffb020"
                onClicked: deck.deckModel && deck.deckModel.cue()
            }
            NeonButton {
                text: deck.deckModel && deck.deckModel.isPlaying ? "PAUSE" : "PLAY"
                active: deck.deckModel && deck.deckModel.isPlaying
                neon: deck.neon
                onClicked: deck.deckModel && deck.deckModel.toggle()
            }
            NeonButton {
                text: "SYNC"
                neon: "#ff2fbf"
                onClicked: deck.deckModel && backend.player.syncTo(deck.deckModel.deckId)
            }
            NeonButton {
                text: deck.deckModel && deck.deckModel.keyLock ? "KEYLOCK ✓" : "KEYLOCK"
                active: deck.deckModel && deck.deckModel.keyLock
                neon: "#a78bfa"
                onClicked: {
                    if (deck.deckModel) deck.deckModel.setKeyLock(!deck.deckModel.keyLock)
                }
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                width: 12; height: 12; radius: 6
                color: deck.deckModel && deck.deckModel.beatInBar === 1 ? "#ff2fbf" :
                       deck.deckModel && deck.deckModel.beatInBar > 0    ? deck.neon : "#333"
                opacity: deck.deckModel && deck.deckModel.beatInBar > 0 ? 1.0 : 0.3
                Behavior on opacity { NumberAnimation { duration: 80 } }
            }
            Text {
                text: deck.deckModel && deck.deckModel.beatInBar > 0
                      ? deck.deckModel.beatInBar + " / 4"
                      : "—"
                color: "#c9d5e1"
                font.pixelSize: 14
                font.bold: true
                Layout.preferredWidth: 40
                horizontalAlignment: Text.AlignRight
            }
        }

        // Tempo/Pitch-Fader
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 70
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text { text: "TEMPO"; color: "#8899aa"; font.pixelSize: 10; font.letterSpacing: 2 }
                Slider {
                    Layout.fillWidth: true
                    from: -0.16     // -16%
                    to: 0.16
                    value: deck.deckModel ? (deck.deckModel.tempoRatio - 1.0) : 0.0
                    onMoved: if (deck.deckModel) deck.deckModel.setTempoRatio(1.0 + value)
                }
                Text {
                    text: {
                        var v = deck.deckModel ? (deck.deckModel.tempoRatio - 1.0) * 100.0 : 0.0
                        return (v >= 0 ? "+" : "") + v.toFixed(2) + " %"
                    }
                    color: "#e6f1ff"
                    font.pixelSize: 10
                }
            }
        }
    }
}
