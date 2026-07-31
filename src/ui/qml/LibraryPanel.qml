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
                Text { text: "TITEL";    color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 320 }
                Text { text: "KÜNSTLER"; color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 220 }
                Text { text: "ALBUM";    color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 200 }
                Text { text: "GENRE";    color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 120 }
                Text { text: "JAHR";     color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 60 }
                Text { text: "BPM";      color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 60 }
                Text { text: "KEY";      color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 60 }
                Text { text: "LUFS";     color: panel.textDim; font.pixelSize: 11; Layout.preferredWidth: 60 }
                Text { text: "STATUS";   color: panel.textDim; font.pixelSize: 11; Layout.fillWidth: true }
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
                    id: row
                    width: list.width
                    height: 34
                    color: rowMouse.containsMouse ? "#1a2434" :
                           (index % 2 === 0 ? "#111a25" : "#0f1720")
                    radius: 4

                    // ---- Drag-Source: ins Deck ziehen ----
                    Drag.active: rowMouse.drag.active
                    Drag.dragType: Drag.Automatic
                    Drag.supportedActions: Qt.CopyAction
                    Drag.mimeData: {
                        "application/x-musicsearcher-trackid": String(trackId)
                    }

                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        drag.target: parent
                        acceptedButtons: Qt.LeftButton | Qt.RightButton

                        onPressed: {
                            row.grabToImage(function(res) {
                                parent.Drag.imageSource = res.url
                            })
                        }
                        onDoubleClicked: {
                            // Doppelklick lädt auf Deck A (falls leer sonst B)
                            if (!backend.player.deckA.isLoaded)
                                backend.player.deckA.loadTrack(trackId)
                            else
                                backend.player.deckB.loadTrack(trackId)
                        }
                        onEntered: {
                            if (musicalKey && musicalKey.length > 0) {
                                keyPopup.keyCode = musicalKey
                                keyPopup.trackTitle = title
                                keyPopup.x = row.width - 260
                                keyPopup.y = row.height
                                keyPopup.open()
                            }
                        }
                        onExited: keyPopup.close()
                    }

                    // Rücksetzen der Position nach Drag-Ende
                    Drag.onDragFinished: {
                        row.x = 0; row.y = 0
                    }

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
                            text: musicalKey ? backend.player.formatKey(musicalKey) : ""
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

    // === Hover-Popup: kompatible Keys ===
    Popup {
        id: keyPopup
        width: 240
        padding: 10
        modal: false
        focus: false
        closePolicy: Popup.NoAutoClose

        property string keyCode: ""
        property string trackTitle: ""

        background: Rectangle {
            color: "#0f1620"
            radius: 6
            border.width: 1
            border.color: "#ff2fbf"
        }

        contentItem: ColumnLayout {
            spacing: 4
            Text {
                text: "Kompatible Keys"
                color: "#ff2fbf"
                font.pixelSize: 11
                font.letterSpacing: 2
                font.bold: true
            }
            Text {
                text: keyPopup.trackTitle
                color: "#8899aa"
                font.pixelSize: 10
                elide: Text.ElideRight
                Layout.preferredWidth: 220
            }
            Text {
                text: "aktuell: " + (keyPopup.keyCode ? backend.player.formatKey(keyPopup.keyCode) : "—")
                color: "#e6f1ff"
                font.pixelSize: 12
                font.bold: true
            }
            Flow {
                Layout.preferredWidth: 220
                spacing: 4
                Repeater {
                    model: keyPopup.keyCode ? backend.player.compatibleKeys(keyPopup.keyCode) : []
                    Rectangle {
                        width: 36; height: 22; radius: 4
                        color: index === 0 ? "#ff2fbf" : "#1c2534"
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, 0.08)
                        Text {
                            anchors.centerIn: parent
                            text: modelData
                            color: index === 0 ? "#0a0e14" : "#e6f1ff"
                            font.pixelSize: 10
                            font.bold: index === 0
                        }
                    }
                }
            }
        }
    }
}
