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

    // --- Hintergrund: animierter Verlauf + subtiles Grid ---
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
                Text {
                    id: statusText
                    text: "Ready."
                    color: root.textDim
                    font.pixelSize: 12
                }
            }
        }

        // === DECK ZONE (oben) — Placeholder für Phase 2 ===
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 340
            spacing: 10

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: root.bgPanel
                radius: 12
                border.width: 1
                border.color: Qt.rgba(0, 0.88, 1, 0.15)
                Text {
                    anchors.centerIn: parent
                    text: "DECK A · kommt in Phase 2"
                    color: root.textDim
                    font.pixelSize: 20
                    font.letterSpacing: 2
                }
            }

            Rectangle {
                Layout.preferredWidth: 240
                Layout.fillHeight: true
                color: root.bgPanel
                radius: 12
                border.width: 1
                border.color: Qt.rgba(1, 0.184, 0.749, 0.15)
                Text {
                    anchors.centerIn: parent
                    text: "MIXER"
                    color: root.neonPink
                    font.pixelSize: 18
                    font.letterSpacing: 3
                    font.bold: true
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: root.bgPanel
                radius: 12
                border.width: 1
                border.color: Qt.rgba(1, 0.69, 0.125, 0.15)
                Text {
                    anchors.centerIn: parent
                    text: "DECK B · kommt in Phase 2"
                    color: root.textDim
                    font.pixelSize: 20
                    font.letterSpacing: 2
                }
            }
        }

        // === LIBRARY (unten) ===
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
                Item { Layout.fillWidth: true }
                Text {
                    text: "Phase 1 · Fundament"
                    color: root.neon
                    font.pixelSize: 11
                    font.letterSpacing: 2
                }
            }
        }
    }

    Connections {
        target: backend
        function onStatusMessage(msg) { statusText.text = msg }
    }
}
