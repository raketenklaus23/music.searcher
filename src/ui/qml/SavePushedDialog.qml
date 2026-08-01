import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dlg
    modal: true
    title: "Save Pushed — Vinyl-Push speichern"
    standardButtons: Dialog.NoButton
    property var deckModel: null

    anchors.centerIn: parent
    width: 480
    padding: 16

    background: Rectangle {
        color: "#131a24"
        radius: 10
        border.width: 1
        border.color: "#ff2fbf"
    }

    header: Rectangle {
        color: "transparent"
        height: 32
        Text {
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            text: "SAVE PUSHED"
            color: "#ff2fbf"
            font.pixelSize: 14
            font.letterSpacing: 3
            font.bold: true
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

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

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Button {
                Layout.fillWidth: true
                text: "Neue Datei"
                onClicked: {
                    var r = dlg.deckModel.savePushed("new_file")
                    resultText.text = r.ok
                        ? "Neue Datei erstellt:\n" + r.path
                        : "Fehler: " + (r.error || "unbekannt")
                    if (r.ok) dlg.accept()
                }
            }
            Button {
                Layout.fillWidth: true
                text: "Original ersetzen (+ .original-Backup)"
                onClicked: {
                    var r = dlg.deckModel.savePushed("replace")
                    resultText.text = r.ok
                        ? "Original ersetzt. Backup gespeichert."
                        : "Fehler: " + (r.error || "unbekannt")
                    if (r.ok) dlg.accept()
                }
            }
            Button {
                Layout.fillWidth: true
                text: "Abbrechen"
                onClicked: dlg.reject()
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
