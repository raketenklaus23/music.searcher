import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: dlg
    title: "Save Pushed — Vinyl-Push speichern"
    width: 520
    height: 320
    minimumWidth: 380
    minimumHeight: 240
    modality: Qt.ApplicationModal
    color: "#131a24"
    flags: Qt.Dialog

    property var deckModel: null

    function open() { resultText.text = ""; show(); raise(); requestActivate() }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        Text {
            text: "SAVE PUSHED"
            color: "#ff2fbf"
            font.pixelSize: 14
            font.letterSpacing: 3
            font.bold: true
        }

        Text {
            text: "Der Track wird offline durch den A10-Compressor mit der aktuellen Push-Intensitaet gerendert."
            color: "#c9d5e1"
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Text {
            text: "Push: " + (dlg.deckModel ? (dlg.deckModel.a10Value * 100).toFixed(0) + " %" : "—")
            color: "#ffb020"
            font.pixelSize: 12
            font.bold: true
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Button {
                Layout.fillWidth: true
                text: "Neue Datei"
                onClicked: {
                    if (!dlg.deckModel) return
                    var r = dlg.deckModel.savePushed("new_file")
                    resultText.text = r.ok
                        ? "Neue Datei erstellt:\n" + r.path
                        : "Fehler: " + (r.error || "unbekannt")
                    if (r.ok) dlg.close()
                }
            }
            Button {
                Layout.fillWidth: true
                text: "Original ersetzen (+ .original-Backup)"
                onClicked: {
                    if (!dlg.deckModel) return
                    var r = dlg.deckModel.savePushed("replace")
                    resultText.text = r.ok
                        ? "Original ersetzt. Backup gespeichert."
                        : "Fehler: " + (r.error || "unbekannt")
                    if (r.ok) dlg.close()
                }
            }
            Button {
                Layout.fillWidth: true
                text: "Abbrechen"
                onClicked: dlg.close()
            }
        }

        Text {
            id: resultText
            text: ""
            color: "#8899aa"
            font.pixelSize: 10
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
