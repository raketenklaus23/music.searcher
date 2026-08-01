import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: dlg
    title: "LUFS-Normalisieren"
    width: 520
    height: 280
    minimumWidth: 380
    minimumHeight: 220
    modality: Qt.ApplicationModal
    color: "#131a24"
    flags: Qt.Dialog

    property var deckModel: null
    property real target: -14.0
    property string resultText: ""

    function open() { resultText = ""; show(); raise(); requestActivate() }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 14

        Text {
            text: dlg.deckModel && dlg.deckModel.title
                  ? ("Ziel: " + dlg.target.toFixed(1) + " LUFS — Track: " + dlg.deckModel.title)
                  : ("Ziel: " + dlg.target.toFixed(1) + " LUFS")
            color: "#e6f1ff"
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Button {
                text: "Playback-Gain (nicht-destruktiv)"
                Layout.fillWidth: true
                onClicked: {
                    if (!dlg.deckModel) return
                    var r = dlg.deckModel.normalizeLufs("playback_gain", dlg.target)
                    dlg.resultText = r.ok
                        ? ("Gain " + (r.gain_db >= 0 ? "+" : "") + r.gain_db.toFixed(2) + " dB gespeichert")
                        : ("Fehler: " + (r.error || "unbekannt"))
                }
                ToolTip.visible: hovered
                ToolTip.text: "Datei bleibt unverändert. Gain-Offset wird beim Playback angewendet."
            }

            Button {
                text: "Datei umschreiben (destruktiv)"
                Layout.fillWidth: true
                onClicked: {
                    if (!dlg.deckModel) return
                    var r = dlg.deckModel.normalizeLufs("destructive", dlg.target)
                    dlg.resultText = r.ok
                        ? ("Datei umgeschrieben, Gain " + (r.gain_db >= 0 ? "+" : "") + r.gain_db.toFixed(2) + " dB · Backup: .original")
                        : ("Fehler: " + (r.error || "unbekannt"))
                }
                ToolTip.visible: hovered
                ToolTip.text: "Datei wird ersetzt. Backup unter <name>.original."
            }
        }

        Text {
            text: dlg.resultText
            color: dlg.resultText.indexOf("Fehler") === 0 ? "#ff2fbf" : "#00e0ff"
            visible: dlg.resultText.length > 0
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            Button {
                text: "Schliessen"
                onClicked: dlg.close()
            }
        }
    }
}
