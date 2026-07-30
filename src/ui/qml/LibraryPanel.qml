import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    color: "#131a24"
    radius: 12
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, 0.05)

    property color neon:    "#00e0ff"
    property color textCol: "#e6f1ff"
    property color textDim: "#8899aa"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "LIBRARY"
                color: panel.neon
                font.pixelSize: 14
                font.letterSpacing: 3
                font.bold: true
            }
            Text {
                text: "· " + backend.libraryModel.rowCount() + " Tracks"
                color: panel.textDim
                font.pixelSize: 12
            }
            Item { Layout.fillWidth: true }
            Button {
                text: "Alle re-analysieren"
                onClicked: backend.reanalyzePending()
            }
        }

        // Header
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            color: "#1c2534"
            radius: 6
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 8
                Text { text: "TITEL";   color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 320 }
                Text { text: "KÜNSTLER"; color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 220 }
                Text { text: "ALBUM";   color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 200 }
                Text { text: "GENRE";   color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 120 }
                Text { text: "JAHR";    color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 60 }
                Text { text: "BPM";     color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 60 }
                Text { text: "KEY";     color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 60 }
                Text { text: "LUFS";    color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 60 }
                Text { text: "STATUS";  color: panel.textDim; font.pixelSize: 11; Layout.fillWidth: true }
            }
        }

        // Drop-Zone + Liste
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#0f1620"
            radius: 8
            border.width: dropArea.containsDrag ? 2 : 1
            border.color: dropArea.containsDrag ? panel.neon : Qt.rgba(1, 1, 1, 0.05)

            ListView {
                id: list
                anchors.fill: parent
                anchors.margins: 6
                clip: true
                model: backend.libraryModel
                spacing: 2

                delegate: Rectangle {
                    width: list.width
                    height: 34
                    color: index % 2 === 0 ? "#111a25" : "#0f1720"
                    radius: 4

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 8

                        Text { text: title;   color: panel.textCol; font.pixelSize: 12; elide: Text.ElideRight; Layout.preferredWidth: 320 }
                        Text { text: artist;  color: panel.textCol; font.pixelSize: 12; elide: Text.ElideRight; Layout.preferredWidth: 220 }
                        Text { text: album;   color: panel.textDim; font.pixelSize: 12; elide: Text.ElideRight; Layout.preferredWidth: 200 }
                        Text { text: genre;   color: panel.textDim; font.pixelSize: 12; elide: Text.ElideRight; Layout.preferredWidth: 120 }
                        Text { text: year > 0 ? year : "";  color: panel.textDim; font.pixelSize: 12; Layout.preferredWidth: 60 }
                        Text {
                            text: bpm > 0 ? bpm.toFixed(1) : ""
                            color: bpm > 0 ? panel.neon : panel.textDim
                            font.pixelSize: 12
                            font.bold: bpm > 0
                            Layout.preferredWidth: 60
                        }
                        Text {
                            text: musicalKey
                            color: musicalKey ? "#ff2fbf" : panel.textDim
                            font.pixelSize: 12
                            font.bold: musicalKey !== ""
                            Layout.preferredWidth: 60
                        }
                        Text {
                            text: lufs !== 0 ? lufs.toFixed(1) : ""
                            color: panel.textDim
                            font.pixelSize: 12
                            Layout.preferredWidth: 60
                        }
                        Text {
                            text: status
                            color: status === "ready" ? "#4ade80" : (status === "error" ? "#ef4444" : "#ffb020")
                            font.pixelSize: 11
                            font.letterSpacing: 1
                            Layout.fillWidth: true
                        }
                    }
                }

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }

            // Overlay-Hinweis wenn leer
            Text {
                anchors.centerIn: parent
                visible: list.count === 0
                text: "Musikdateien hier reinziehen"
                color: panel.textDim
                font.pixelSize: 18
                font.letterSpacing: 2
            }

            DropArea {
                id: dropArea
                anchors.fill: parent
                onDropped: (drop) => {
                    if (drop.hasUrls) {
                        backend.importUrls(drop.urls)
                        drop.acceptProposedAction()
                    }
                }
            }
        }
    }
}
