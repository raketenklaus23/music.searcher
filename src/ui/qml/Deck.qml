import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import "controls"

Rectangle {
    id: deck
    color: "#131a24"
    radius: 12
    border.width: deck.deckModel && deck.deckModel.isMaster ? 2 : 1
    border.color: deck.deckModel && deck.deckModel.isMaster
                  ? "#ff2fbf"
                  : Qt.rgba(1, 1, 1, 0.06)

    property var  deckModel: null        // DeckBridge Instanz
    property color neon: "#00e0ff"
    property string sideLabel: "A"
    property string deckId: "a"

    // --- Beat-Pulse Ring ---
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

        // === Header: Seite + Titel + BPM + Key ===
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
                    Layout.alignment: Qt.AlignRight
                }
                RowLayout {
                    spacing: 6
                    Layout.alignment: Qt.AlignRight
                    Text {
                        text: (deck.deckModel && deck.deckModel.bpm > 0) ? "orig " + deck.deckModel.bpm.toFixed(1) : ""
                        color: "#556677"
                        font.pixelSize: 9
                    }
                    Text {
                        text: deck.deckModel && deck.deckModel.musicalKey
                              ? backend.player.formatKey(deck.deckModel.musicalKey)
                              : ""
                        color: "#ff2fbf"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }
        }

        // === Waveform-Placeholder (Phase 3: Shader) ===
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 96
            radius: 6
            color: "#0a1018"
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.05)

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

            DropArea {
                anchors.fill: parent
                keys: ["application/x-musicsearcher-trackid"]
                onDropped: (drop) => {
                    var tid = parseInt(drop.getDataAsString("application/x-musicsearcher-trackid"))
                    if (!isNaN(tid) && deck.deckModel) deck.deckModel.loadTrack(tid)
                }
            }

            MouseArea {
                anchors.fill: parent
                onClicked: (m) => {
                    if (!deck.deckModel || deck.deckModel.durationSec <= 0) return
                    deck.deckModel.seek(m.x / width * deck.deckModel.durationSec)
                }
            }
        }

        // === Transport-Zeile ===
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            NeonButton {
                text: "CUE"
                neon: "#ffb020"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".cue")
            }
            NeonButton {
                text: deck.deckModel && deck.deckModel.isPlaying ? "PAUSE" : "PLAY"
                active: deck.deckModel && deck.deckModel.isPlaying
                neon: deck.neon
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".play_pause")
            }
            NeonButton {
                text: "SYNC"
                neon: "#ff2fbf"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".sync")
                ToolTip.visible: hovered
                ToolTip.text: "1x = BPM angleichen · 2x = Sync + Phrase-Lock"
            }
            NeonButton {
                text: deck.deckModel && deck.deckModel.keyLock ? "KEY ✓" : "KEY"
                active: deck.deckModel && deck.deckModel.keyLock
                neon: "#a78bfa"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".keypress")
                ToolTip.visible: hovered
                ToolTip.text: "1x = KeyLock · 2x = Key-Match zu Master"
            }
            NeonButton {
                text: "MASTER"
                active: deck.deckModel && deck.deckModel.isMaster
                neon: "#ff2fbf"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".become_master")
            }

            Item { Layout.fillWidth: true }

            // Beat-Indicator + phrasenweiser Countdown
            ColumnLayout {
                spacing: 2
                RowLayout {
                    spacing: 6
                    Rectangle {
                        width: 12; height: 12; radius: 6
                        color: deck.deckModel && deck.deckModel.beatInBar === 1 ? "#ff2fbf" :
                               deck.deckModel && deck.deckModel.beatInBar > 0    ? deck.neon : "#333"
                        opacity: deck.deckModel && deck.deckModel.beatInBar > 0 ? 1.0 : 0.3
                        Behavior on opacity { NumberAnimation { duration: 80 } }
                    }
                    Text {
                        text: deck.deckModel && deck.deckModel.beatInBar > 0
                              ? deck.deckModel.bar + "." + deck.deckModel.beatInBar
                              : "—"
                        color: "#c9d5e1"
                        font.pixelSize: 14
                        font.bold: true
                    }
                }
                // 16-Bar-Phrase-Balken
                Row {
                    spacing: 2
                    Repeater {
                        model: 16
                        Rectangle {
                            width: 6; height: 6; radius: 1
                            color: deck.deckModel && (deck.deckModel.phraseBeat - 1) === index
                                   ? "#ff2fbf" : Qt.rgba(1, 1, 1, 0.15)
                        }
                    }
                }
            }
        }

        // === Beatgrid-Korrektur ===
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Text {
                text: "BEATGRID"
                color: "#556677"
                font.pixelSize: 10
                font.letterSpacing: 2
            }
            NeonButton {
                text: "BPM /2"
                neon: "#8899aa"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".bpm_halve")
            }
            NeonButton {
                text: "BPM x2"
                neon: "#8899aa"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".bpm_double")
            }
            Item { Layout.fillWidth: true }
        }

        // === Tempo-Fader ===
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { text: "TEMPO"; color: "#8899aa"; font.pixelSize: 10; font.letterSpacing: 2 }
            Slider {
                Layout.fillWidth: true
                from: -0.16
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
