import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "controls"

Dialog {
    id: dlg
    title: "Audio-Einstellungen"
    modal: true
    standardButtons: Dialog.Close
    width: 640
    height: 440

    property var devices: []
    property int currentDeviceIndex: -1
    property int samplerate: 48000
    property int blocksize: 256

    function refresh() {
        devices = backend.player.listDevices()
        // markiere aktuelles Device
        var cur = backend.player.currentDeviceLabel
        for (var i = 0; i < devices.length; i++) {
            if (devices[i].label === cur) { currentDeviceIndex = i; break }
        }
        srCombo.currentIndex = srCombo.model.indexOf(backend.player.currentSamplerate)
        bsCombo.currentIndex = bsCombo.model.indexOf(backend.player.currentBlocksize)
    }
    onOpened: refresh()

    contentItem: ColumnLayout {
        spacing: 10

        // ASIO-Warnung wenn kein ASIO im PortAudio-Build ist
        Rectangle {
            visible: {
                for (var i = 0; i < dlg.devices.length; i++)
                    if (dlg.devices[i].hostapi === "ASIO") return false
                return true
            }
            Layout.fillWidth: true
            color: "#3a2a10"
            radius: 6
            border.color: "#ffb020"
            border.width: 1
            padding: 8
            Layout.preferredHeight: 44
            Text {
                anchors.centerIn: parent
                text: "⚠ Kein ASIO im aktuellen sounddevice-Build. WDM-KS Exclusive ist derzeit der beste Low-Latency-Pfad (~5-8 ms). ASIO-Umbau folgt am Projekt-Ende."
                color: "#ffcf80"
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                width: parent.width - 20
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Text { text: "Output-Device"; color: "#8899aa"; font.pixelSize: 11; Layout.preferredWidth: 140 }
            ComboBox {
                id: devCombo
                Layout.fillWidth: true
                model: dlg.devices.map(function(d) { return d.label + "  (low-lat " + d.latencyLowMs + " ms)" })
                currentIndex: dlg.currentDeviceIndex
                onActivated: dlg.currentDeviceIndex = currentIndex
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Text { text: "Samplerate"; color: "#8899aa"; font.pixelSize: 11; Layout.preferredWidth: 140 }
            ComboBox {
                id: srCombo
                Layout.preferredWidth: 160
                model: [44100, 48000, 88200, 96000]
                currentIndex: 1
            }
            Item { Layout.fillWidth: true }
        }

        RowLayout {
            Layout.fillWidth: true
            Text { text: "Buffersize (Frames)"; color: "#8899aa"; font.pixelSize: 11; Layout.preferredWidth: 140 }
            ComboBox {
                id: bsCombo
                Layout.preferredWidth: 160
                model: [64, 128, 256, 512, 1024]
                currentIndex: 2
            }
            Text {
                Layout.fillWidth: true
                text: {
                    var sr = srCombo.model[srCombo.currentIndex] || 48000
                    var bs = bsCombo.model[bsCombo.currentIndex] || 256
                    return "≈ " + (bs / sr * 1000.0).toFixed(2) + " ms Buffer @ " + sr + " Hz"
                }
                color: "#8899aa"
                font.pixelSize: 11
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Qt.rgba(1,1,1,0.05) }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Text { text: "Status"; color: "#8899aa"; font.pixelSize: 11; Layout.preferredWidth: 140 }
            Rectangle {
                width: 10; height: 10; radius: 5
                color: backend.player.engineRunning ? "#4ade80" : "#666"
            }
            Text {
                text: backend.player.engineRunning
                    ? ("Läuft — Latenz " + backend.player.latencyMs.toFixed(1) + " ms · "
                       + backend.player.currentSamplerate + " Hz · Buffer " + backend.player.currentBlocksize)
                    : "Gestoppt"
                color: "#e6f1ff"
                font.pixelSize: 11
            }
            Item { Layout.fillWidth: true }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            NeonButton {
                text: "ENGINE STARTEN"
                neon: "#4ade80"
                onClicked: {
                    if (dlg.currentDeviceIndex < 0 || dlg.currentDeviceIndex >= dlg.devices.length) return
                    var dev = dlg.devices[dlg.currentDeviceIndex].index
                    var sr = srCombo.model[srCombo.currentIndex]
                    var bs = bsCombo.model[bsCombo.currentIndex]
                    backend.player.startEngine(dev, sr, bs)
                }
            }
            NeonButton {
                text: "STOPPEN"
                neon: "#ef4444"
                onClicked: backend.player.stopEngine()
            }
            Item { Layout.fillWidth: true }
            NeonButton {
                text: "REFRESH DEVICES"
                onClicked: dlg.refresh()
            }
        }
    }
}
