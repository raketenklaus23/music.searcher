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

                // Quantizer (global)
                Text { text: "QUANT"; color: root.textDim; font.pixelSize: 10; font.letterSpacing: 2 }
                ComboBox {
                    id: quantCombo
                    Layout.preferredWidth: 96
                    model: ["off", "downbeat", "1/4", "1/8", "1/16"]
                    currentIndex: Math.max(0, model.indexOf(backend.player.quantizerGrid))
                    onActivated: backend.player.setQuantizer(model[currentIndex])
                    ToolTip.visible: hovered
                    ToolTip.text: "Snap für Cue-Setzen + Loop-Start"
                }

                // Beatgrid-Mode (global default für neue Analysen)
                Text { text: "GRID"; color: root.textDim; font.pixelSize: 10; font.letterSpacing: 2 }
                ComboBox {
                    id: beatgridCombo
                    Layout.preferredWidth: 150
                    model: ["beat_match", "structure_boundaries"]
                    currentIndex: Math.max(0, model.indexOf(backend.player.beatgridMode))
                    onActivated: backend.player.setBeatgridMode(model[currentIndex])
                    ToolTip.visible: hovered
                    ToolTip.text: "beat_match = Bassdrum-Transient · structure_boundaries = Segmentgrenzen"
                }

                // Notation-Toggle
                Button {
                    text: backend.player.keyNotation === "camelot" ? "Camelot" : "Open Key"
                    onClicked: backend.actions.trigger("global.notation_toggle")
                    ToolTip.visible: hovered
                    ToolTip.text: "Klick: Notation umschalten (Ctrl+K)"
                }

                // 4-Deck-Toggle
                Button {
                    text: backend.player.fourDeckMode ? "4-DECK" : "2-DECK"
                    checkable: true
                    checked: backend.player.fourDeckMode
                    onClicked: backend.player.setFourDeckMode(!backend.player.fourDeckMode)
                    ToolTip.visible: hovered
                    ToolTip.text: "Umschalten zwischen 2- und 4-Deck-Layout"
                }

                Text {
                    id: statusText
                    text: "Ready."
                    color: root.textDim
                    font.pixelSize: 12
                }
            }
        }

        // === KEY-REIHE (chromatisch, 2 Reihen: Moll oben, Dur unten) ===
        Rectangle {
            id: keyRowPanel
            Layout.fillWidth: true
            Layout.preferredHeight: 84
            color: root.bgPanel
            radius: 8
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.05)

            // Datenmodell wird neu gebaut, wenn Notation togglet
            property var keyData: {
                backend.player.keyNotation  // dep trigger
                return backend.player.keyRowChromatic()
            }

            // Aktuelle Deck-Keys — im aktiven Notations-Format (Camelot oder OpenKey)
            property string deckACode: backend.player.deckA.musicalKey
                ? backend.player.formatKey(backend.player.deckA.musicalKey)
                : ""
            property string deckBCode: backend.player.deckB.musicalKey
                ? backend.player.formatKey(backend.player.deckB.musicalKey)
                : ""

            component KeyCell : Rectangle {
                property var item: ({tonic: "", code: ""})
                property bool isA: keyRowPanel.deckACode !== "" && keyRowPanel.deckACode === item.code
                property bool isB: keyRowPanel.deckBCode !== "" && keyRowPanel.deckBCode === item.code
                Layout.fillWidth: true
                Layout.preferredHeight: 30
                radius: 4
                color: isA && isB ? "#ff2fbf"
                     : isA ? "#00e0ff"
                     : isB ? "#ffb020"
                     : "#1c2534"
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.06)

                Column {
                    anchors.centerIn: parent
                    spacing: 1
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: item.tonic
                        color: (isA || isB) ? "#0a0e14" : "#e6f1ff"
                        font.pixelSize: 11
                        font.bold: true
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: item.code
                        color: (isA || isB) ? "#0a0e14" : "#8899aa"
                        font.pixelSize: 8
                        font.letterSpacing: 1
                    }
                }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 4

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        text: "MOLL"
                        color: root.neon
                        font.pixelSize: 9
                        font.letterSpacing: 2
                        font.bold: true
                        Layout.preferredWidth: 40
                    }
                    Repeater {
                        model: keyRowPanel.keyData.minor
                        KeyCell { item: modelData }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        text: "DUR"
                        color: root.neonAmber
                        font.pixelSize: 9
                        font.letterSpacing: 2
                        font.bold: true
                        Layout.preferredWidth: 40
                    }
                    Repeater {
                        model: keyRowPanel.keyData.major
                        KeyCell { item: modelData }
                    }
                }
            }
        }

        // === DECK ZONE (adaptiv: 2- oder 4-Deck) ===
        property bool fourDeck: backend.player.fourDeckMode

        ColumnLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: fourDeck ? 780 : 520
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10

                Deck {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    deckModel: backend.player.deckA
                    deckId: "a"
                    sideLabel: "A"
                    neon: root.neon
                }
                Mixer {
                    Layout.preferredWidth: 340
                    Layout.fillHeight: true
                }
                Deck {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    deckModel: backend.player.deckB
                    deckId: "b"
                    sideLabel: "B"
                    neon: root.neonAmber
                }
            }

            // Zweite Reihe nur bei 4-Deck-Modus
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10
                visible: fourDeck

                Deck {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    deckModel: backend.player.deckC
                    deckId: "c"
                    sideLabel: "C"
                    neon: "#a78bfa"
                }
                Rectangle {
                    Layout.preferredWidth: 340
                    Layout.fillHeight: true
                    color: "transparent"
                }
                Deck {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    deckModel: backend.player.deckD
                    deckId: "d"
                    sideLabel: "D"
                    neon: "#4ade80"
                }
            }
        }

        // === LIBRARY + SUGGESTER ===
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            LibraryPanel {
                id: libraryPanel
                Layout.fillWidth: true
                Layout.fillHeight: true
                onRequestSimilar: (id, name) => similarDlg.openFor(id, name)
            }

            SuggesterPanel {
                id: suggesterPanel
                Layout.preferredWidth: 520
                Layout.fillHeight: true
            }
        }

        SimilarTracksDialog {
            id: similarDlg
        }
        KeyBindingsDialog {
            id: keyBindingsDlg
        }

        // Globale Shortcut-Registry aus Actions
        property var _shortcutList: backend.actions.listAll()
        Connections {
            target: backend.actions
            function onShortcutsChanged() { root._shortcutList = backend.actions.listAll() }
            function onRegistryChanged()  { root._shortcutList = backend.actions.listAll() }
        }
        Repeater {
            model: root._shortcutList
            Shortcut {
                sequence: modelData.shortcut || ""
                enabled: modelData.shortcut && modelData.shortcut.length > 0
                context: Qt.ApplicationShortcut
                onActivated: backend.actions.trigger(modelData.id)
            }
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
                    text: "Jobs: " + backend.queueCount
                          + (backend.stemQueueCount > 0
                             ? " · Stems: " + backend.stemQueueCount
                             : "")
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
                    text: "MIDI"
                    onClicked: midiDialog.open()
                }
                Button {
                    text: "Tastatur"
                    onClicked: keyBindingsDlg.open()
                }
                Button {
                    text: "Audio-Einstellungen"
                    onClicked: audioDialog.open()
                }
                Text {
                    text: "Phase 5 · Suggester + Set-Drop"
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
    MidiDialog {
        id: midiDialog
    }

    Connections {
        target: backend
        function onStatusMessage(msg) { statusText.text = msg }
    }
}
