import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

ApplicationWindow {
    id: root
    width: 1600
    height: 950
    minimumWidth: 1280
    minimumHeight: 800
    visible: true
    title: qsTr("Music Searcher — DJ Suite")
    color: "#0a0e14"

    // --- globales Theme ---
    property color neon:      "#00e0ff"
    property color neonPink:  "#ff2fbf"
    property color neonAmber: "#ffb020"
    property color bgDark:    "#0a0e14"
    property color bgPanel:   "#131a24"
    property color bgRaised:  "#1c2534"
    property color text:      "#e6f1ff"
    property color textDim:   "#8899aa"

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#0a0e14" }
            GradientStop { position: 1.0; color: "#050810" }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 10

        // === TOP BAR ===
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            color: root.bgPanel
            radius: 8
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.05)

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16

                Text {
                    text: "MUSIC SEARCHER"
                    color: root.neon
                    font.pixelSize: 16
                    font.letterSpacing: 3
                    font.bold: true
                }
                Text {
                    text: "· DJ SUITE"
                    color: root.textDim
                    font.pixelSize: 14
                    font.letterSpacing: 2
                }
                Item { Layout.fillWidth: true }

                // Notation-Toggle
                Button {
                    text: backend.player.keyNotation === "camelot" ? "Camelot" : "Open Key"
                    onClicked: backend.actions.trigger("global.notation_toggle")
                    ToolTip.visible: hovered
                    ToolTip.text: "Klick: Notation umschalten (Ctrl+K)"
                }

                Text {
                    id: statusText
                    text: "Ready."
                    color: root.textDim
                    font.pixelSize: 12
                }
            }
        }

        // === KEY-REIHE (immer sichtbar, aktueller Track hervorgehoben) ===
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            color: root.bgPanel
            radius: 8
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.05)

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 6

                Text {
                    text: "KEYS"
                    color: root.textDim
                    font.pixelSize: 10
                    font.letterSpacing: 2
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: 4

                    Repeater {
                        // rebuilds when notation toggles
                        model: {
                            backend.player.keyNotation  // dep trigger
                            return backend.player.keyRow()
                        }
                        Rectangle {
                            width: 34; height: 22; radius: 4
                            property string keyCode: modelData
                            property bool isDeckAKey: backend.player.deckA.musicalKey === keyCode ||
                                                      (backend.player.keyNotation === "openkey" &&
                                                       backend.player.formatKey(backend.player.deckA.musicalKey) === keyCode)
                            property bool isDeckBKey: backend.player.deckB.musicalKey === keyCode ||
                                                      (backend.player.keyNotation === "openkey" &&
                                                       backend.player.formatKey(backend.player.deckB.musicalKey) === keyCode)
                            color: isDeckAKey && isDeckBKey ? "#ff2fbf"
                                 : isDeckAKey ? "#00e0ff"
                                 : isDeckBKey ? "#ffb020"
                                 : "#1c2534"
                            border.width: 1
                            border.color: Qt.rgba(1, 1, 1, 0.06)
                            Text {
                                anchors.centerIn: parent
                                text: keyCode
                                color: (parent.isDeckAKey || parent.isDeckBKey) ? "#0a0e14" : "#8899aa"
                                font.pixelSize: 10
                                font.bold: (parent.isDeckAKey || parent.isDeckBKey)
                            }
                        }
                    }
                }
            }
        }

        // === DECK ZONE ===
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 360
            spacing: 10

            Deck {
                id: deckA
                Layout.fillWidth: true
                Layout.fillHeight: true
                deckModel: backend.player.deckA
                deckId: "a"
                sideLabel: "A"
                neon: root.neon
            }

            Mixer {
                Layout.preferredWidth: 260
                Layout.fillHeight: true
            }

            Deck {
                id: deckB
                Layout.fillWidth: true
                Layout.fillHeight: true
                deckModel: backend.player.deckB
                deckId: "b"
                sideLabel: "B"
                neon: root.neonAmber
            }
        }

        // === LIBRARY ===
        LibraryPanel {
            id: libraryPanel
            Layout.fillWidth: true
            Layout.fillHeight: true
        }

        // === BOTTOM BAR ===
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            color: root.bgPanel
            radius: 8

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12

                Text {
                    text: "Jobs in Queue: " + backend.queueCount
                    color: root.textDim
                    font.pixelSize: 11
                }
                Item { width: 16 }
                Text {
                    text: backend.player.engineRunning
                          ? ("Engine: " + backend.player.currentDeviceLabel + " @ "
                             + backend.player.currentSamplerate + " Hz / "
                             + backend.player.currentBlocksize + " frames · "
                             + backend.player.latencyMs.toFixed(1) + " ms")
                          : "Engine: gestoppt"
                    color: backend.player.engineRunning ? root.neon : root.textDim
                    font.pixelSize: 11
                }
                Item { Layout.fillWidth: true }
                Button {
                    text: "Audio-Einstellungen"
                    onClicked: audioDialog.open()
                }
                Text {
                    text: "Phase 2 · Decks + Mixer"
                    color: root.neonPink
                    font.pixelSize: 11
                    font.letterSpacing: 2
                }
            }
        }
    }

    AudioSettings {
        id: audioDialog
    }

    Connections {
        target: backend
        function onStatusMessage(msg) { statusText.text = msg }
    }
}
