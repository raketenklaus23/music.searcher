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
    property color colA: "#00e0ff"
    property color colB: "#ffb020"

    // FX-Typen (bleibt in-sync mit src/audio/effects.py FxType)
    property var fxTypes: [
        { key: "none",   label: "OFF" },
        { key: "echo",   label: "ECHO" },
        { key: "reverb", label: "REVERB" },
        { key: "noise",  label: "NOISE" },
        { key: "filter", label: "FILTER" }
    ]

    // Channel-Strip Sub-Component (DRY für A + B)
    component ChannelStrip : ColumnLayout {
        id: strip
        spacing: 4
        property color deckColor: "#00e0ff"
        property string sideLabel: "A"
        property var deckModel: null            // backend.player.deckX
        property string fxTypeKey: "none"

        Text {
            text: strip.sideLabel
            color: strip.deckColor
            font.bold: true
            font.pixelSize: 14
            Layout.alignment: Qt.AlignHCenter
        }

        // EQ Block
        Text { text: "EQ"; color: "#5f7185"; font.pixelSize: 8; font.letterSpacing: 2; Layout.alignment: Qt.AlignHCenter }
        Knob {
            Layout.alignment: Qt.AlignHCenter
            width: 60; height: 76
            label: "HIGH"; from: -12; to: 12; value: 0; defaultValue: 0
            bipolar: true; glowColor: strip.deckColor
            onChanged: strip.deckModel.setEqHigh(newValue)
        }
        Knob {
            Layout.alignment: Qt.AlignHCenter
            width: 60; height: 76
            label: "HI-MID"; from: -12; to: 12; value: 0; defaultValue: 0
            bipolar: true; glowColor: strip.deckColor
            onChanged: strip.deckModel.setEqHighMid(newValue)
        }
        Knob {
            Layout.alignment: Qt.AlignHCenter
            width: 60; height: 76
            label: "LO-MID"; from: -12; to: 12; value: 0; defaultValue: 0
            bipolar: true; glowColor: strip.deckColor
            onChanged: strip.deckModel.setEqLowMid(newValue)
        }
        Knob {
            Layout.alignment: Qt.AlignHCenter
            width: 60; height: 76
            label: "LOW"; from: -12; to: 12; value: 0; defaultValue: 0
            bipolar: true; glowColor: strip.deckColor
            onChanged: strip.deckModel.setEqLow(newValue)
        }

        // Kill Block (Ecler Warm)
        Text { text: "KILL"; color: "#5f7185"; font.pixelSize: 8; font.letterSpacing: 2; Layout.alignment: Qt.AlignHCenter }
        Knob {
            Layout.alignment: Qt.AlignHCenter
            width: 54; height: 68
            label: "K-HI"; from: -1; to: 1; value: 0; defaultValue: 0
            bipolar: true; glowColor: "#ef4444"
            onChanged: strip.deckModel.setKillHigh(newValue)
        }
        Knob {
            Layout.alignment: Qt.AlignHCenter
            width: 54; height: 68
            label: "K-MID"; from: -1; to: 1; value: 0; defaultValue: 0
            bipolar: true; glowColor: "#ef4444"
            onChanged: strip.deckModel.setKillMid(newValue)
        }
        Knob {
            Layout.alignment: Qt.AlignHCenter
            width: 54; height: 68
            label: "K-LO"; from: -1; to: 1; value: 0; defaultValue: 0
            bipolar: true; glowColor: "#ef4444"
            onChanged: strip.deckModel.setKillLow(newValue)
        }

        // Compressor (Pioneer A9)
        Text { text: "COMP"; color: "#5f7185"; font.pixelSize: 8; font.letterSpacing: 2; Layout.alignment: Qt.AlignHCenter }
        Knob {
            Layout.alignment: Qt.AlignHCenter
            width: 60; height: 76
            label: "SQUASH"; from: 0; to: 1; value: 0; defaultValue: 0
            bipolar: false; glowColor: "#a855f7"
            onChanged: strip.deckModel.setCompressor(newValue)
        }

        // FX Selector + FX Wet
        Text { text: "FX"; color: "#5f7185"; font.pixelSize: 8; font.letterSpacing: 2; Layout.alignment: Qt.AlignHCenter }
        ComboBox {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 110
            Layout.preferredHeight: 22
            model: mixer.fxTypes.map(function(t) { return t.label })
            currentIndex: 0
            font.pixelSize: 9
            onActivated: {
                strip.fxTypeKey = mixer.fxTypes[currentIndex].key
                strip.deckModel.setFxType(strip.fxTypeKey)
            }
        }
        Knob {
            Layout.alignment: Qt.AlignHCenter
            width: 60; height: 76
            label: strip.fxTypeKey === "filter" ? "SWEEP" : "WET"
            from: strip.fxTypeKey === "filter" ? -1 : 0
            to: 1
            value: 0; defaultValue: 0
            bipolar: strip.fxTypeKey === "filter"
            glowColor: "#22d3ee"
            onChanged: {
                if (strip.fxTypeKey === "filter") {
                    strip.deckModel.setFxFilterDir(newValue)
                    strip.deckModel.setFxWet(Math.abs(newValue))
                } else {
                    strip.deckModel.setFxWet(newValue)
                }
            }
        }

        // Volume (Rotary statt Fader)
        Text { text: "VOLUME"; color: "#5f7185"; font.pixelSize: 8; font.letterSpacing: 2; Layout.alignment: Qt.AlignHCenter }
        Knob {
            Layout.alignment: Qt.AlignHCenter
            width: 68; height: 84
            label: "VOL"; from: 0; to: 1.4; value: 1.0; defaultValue: 1.0
            bipolar: false; glowColor: strip.deckColor
            onChanged: strip.deckModel.setChannelVolume(newValue)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 6

        Text {
            text: "MIXER"
            color: mixer.neonPink
            font.pixelSize: 12
            font.letterSpacing: 3
            font.bold: true
            Layout.alignment: Qt.AlignHCenter
        }

        // Global FX Resonance
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Text {
                text: "FX RESONANCE"
                color: "#5f7185"
                font.pixelSize: 9
                font.letterSpacing: 2
            }
            Slider {
                id: resSlider
                Layout.fillWidth: true
                Layout.preferredHeight: 20
                from: 0.0; to: 1.0
                value: 0.3
                onMoved: backend.player.setGlobalFilterResonance(value)
                background: Rectangle {
                    x: resSlider.leftPadding
                    y: resSlider.topPadding + (resSlider.availableHeight - height) * 0.5
                    width: resSlider.availableWidth
                    height: 4; radius: 2
                    color: "#0f1620"
                    border.width: 1
                    border.color: Qt.rgba(1,1,1,0.06)
                    Rectangle {
                        width: resSlider.visualPosition * parent.width
                        height: parent.height; radius: 2
                        color: "#22d3ee"; opacity: 0.6
                    }
                }
                handle: Rectangle {
                    x: resSlider.leftPadding + resSlider.visualPosition * (resSlider.availableWidth - width)
                    y: resSlider.topPadding + (resSlider.availableHeight - height) * 0.5
                    width: 12; height: 16; radius: 3
                    color: "#22d3ee"
                    border.color: "#0a0e14"
                    border.width: 1
                }
            }
            Text {
                text: resSlider.value.toFixed(2)
                color: "#22d3ee"
                font.pixelSize: 9
                Layout.preferredWidth: 28
            }
        }

        // Zwei Channel-Strips
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.vertical.policy: ScrollBar.AsNeeded
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            RowLayout {
                width: mixer.width - 24
                spacing: 8

                ChannelStrip {
                    Layout.fillWidth: true
                    deckColor: mixer.colA
                    sideLabel: "A"
                    deckModel: backend.player.deckA
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    color: Qt.rgba(1,1,1,0.05)
                }

                ChannelStrip {
                    Layout.fillWidth: true
                    deckColor: mixer.colB
                    sideLabel: "B"
                    deckModel: backend.player.deckB
                }
            }
        }

        // Crossfader
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                text: "CROSSFADER"
                color: "#5f7185"
                font.pixelSize: 9
                font.letterSpacing: 2
                Layout.alignment: Qt.AlignHCenter
            }
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
                    height: 6; radius: 3
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
                Text { text: "A"; color: mixer.colA; font.pixelSize: 10; font.bold: true }
                Item { Layout.fillWidth: true }
                Text { text: "B"; color: mixer.colB; font.pixelSize: 10; font.bold: true }
            }
        }
    }
}
