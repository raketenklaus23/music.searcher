import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "controls"

Rectangle {
    id: mixer
    color: "#131a24"
    radius: 12
    border.width: 1
    border.color: Qt.rgba(1, 0.184, 0.749, 0.15)

    property color neonPink: "#ff2fbf"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        Text {
            text: "MIXER"
            color: mixer.neonPink
            font.pixelSize: 12
            font.letterSpacing: 3
            font.bold: true
            Layout.alignment: Qt.AlignHCenter
        }

        // Zwei Channel-Strips + Master
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            // ---- Channel A ----
            ColumnLayout {
                spacing: 6
                Text { text: "A"; color: "#00e0ff"; font.bold: true; font.pixelSize: 14; Layout.alignment: Qt.AlignHCenter }
                Knob { label: "HIGH";  from: -12; to: 12; value: 0; defaultValue: 0; bipolar: true; glowColor: "#00e0ff";
                       valueFormat: "%.1f"; onChanged: backend.player.deckA.setEqHigh(newValue) }
                Knob { label: "HI-MID"; from: -12; to: 12; value: 0; defaultValue: 0; bipolar: true; glowColor: "#00e0ff";
                       valueFormat: "%.1f"; onChanged: backend.player.deckA.setEqHighMid(newValue) }
                Knob { label: "LO-MID"; from: -12; to: 12; value: 0; defaultValue: 0; bipolar: true; glowColor: "#00e0ff";
                       valueFormat: "%.1f"; onChanged: backend.player.deckA.setEqLowMid(newValue) }
                Knob { label: "LOW";   from: -12; to: 12; value: 0; defaultValue: 0; bipolar: true; glowColor: "#00e0ff";
                       valueFormat: "%.1f"; onChanged: backend.player.deckA.setEqLow(newValue) }
                Knob { label: "GAIN";  from: -20; to: 12; value: 0; defaultValue: 0; bipolar: true; glowColor: "#ffb020";
                       valueFormat: "%.1f"; onChanged: backend.player.deckA.setGainDb(newValue) }
                VFader {
                    label: "VOL A"
                    neon: "#00e0ff"
                    Layout.preferredHeight: 120
                    Layout.alignment: Qt.AlignHCenter
                    onMoved: backend.player.deckA.setVolume(value)
                }
            }

            // ---- Channel B ----
            ColumnLayout {
                spacing: 6
                Text { text: "B"; color: "#ffb020"; font.bold: true; font.pixelSize: 14; Layout.alignment: Qt.AlignHCenter }
                Knob { label: "HIGH";  from: -12; to: 12; value: 0; defaultValue: 0; bipolar: true; glowColor: "#ffb020";
                       valueFormat: "%.1f"; onChanged: backend.player.deckB.setEqHigh(newValue) }
                Knob { label: "HI-MID"; from: -12; to: 12; value: 0; defaultValue: 0; bipolar: true; glowColor: "#ffb020";
                       valueFormat: "%.1f"; onChanged: backend.player.deckB.setEqHighMid(newValue) }
                Knob { label: "LO-MID"; from: -12; to: 12; value: 0; defaultValue: 0; bipolar: true; glowColor: "#ffb020";
                       valueFormat: "%.1f"; onChanged: backend.player.deckB.setEqLowMid(newValue) }
                Knob { label: "LOW";   from: -12; to: 12; value: 0; defaultValue: 0; bipolar: true; glowColor: "#ffb020";
                       valueFormat: "%.1f"; onChanged: backend.player.deckB.setEqLow(newValue) }
                Knob { label: "GAIN";  from: -20; to: 12; value: 0; defaultValue: 0; bipolar: true; glowColor: "#00e0ff";
                       valueFormat: "%.1f"; onChanged: backend.player.deckB.setGainDb(newValue) }
                VFader {
                    label: "VOL B"
                    neon: "#ffb020"
                    Layout.preferredHeight: 120
                    Layout.alignment: Qt.AlignHCenter
                    onMoved: backend.player.deckB.setVolume(value)
                }
            }
        }

        // Crossfader
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { text: "CROSSFADER"; color: "#8899aa"; font.pixelSize: 10; font.letterSpacing: 2; Layout.alignment: Qt.AlignHCenter }
            Slider {
                id: xfader
                Layout.fillWidth: true
                orientation: Qt.Horizontal
                from: -1.0; to: 1.0; value: 0.0
                onMoved: backend.player.setCrossfader(value)

                background: Rectangle {
                    x: xfader.leftPadding
                    y: xfader.topPadding + (xfader.availableHeight - height) * 0.5
                    width: xfader.availableWidth
                    height: 6
                    radius: 3
                    color: "#0f1620"
                    border.width: 1
                    border.color: Qt.rgba(1,1,1,0.06)
                    Rectangle {
                        anchors.centerIn: parent
                        width: 2; height: parent.height + 4
                        color: mixer.neonPink; opacity: 0.5
                    }
                }
                handle: Rectangle {
                    x: xfader.leftPadding + xfader.visualPosition * (xfader.availableWidth - width)
                    y: xfader.topPadding + (xfader.availableHeight - height) * 0.5
                    width: 26; height: 22; radius: 4
                    color: "#2a3a4f"
                    border.color: mixer.neonPink
                    border.width: 1
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "A"; color: "#00e0ff"; font.pixelSize: 11; font.bold: true }
                Item { Layout.fillWidth: true }
                Text { text: "B"; color: "#ffb020"; font.pixelSize: 11; font.bold: true }
            }
        }
    }
}
