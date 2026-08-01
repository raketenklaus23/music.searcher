import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Rectangle {
    id: panel
    color: "#131a24"
    radius: 12
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, 0.05)

    property color neon:     "#00e0ff"
    property color neonPink: "#ff2fbf"
    property color amber:    "#ffb020"

    property var setPicks: []
    property var genrePicks: []
    property string setStatus: "bereit"

    Connections {
        target: backend.suggester
        function onSetAnalyzed(payload) {
            panel.setPicks = payload.picks
            panel.setStatus = "OK · " + Math.round(payload.duration) + "s · "
                              + payload.chunks + " Fenster"
        }
        function onSetAnalyzeFailed(err) {
            panel.setStatus = "Fehler: " + err
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 10

        // ---- Header ---------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "SUGGESTER"
                color: panel.neon
                font.pixelSize: 14
                font.letterSpacing: 3
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            Text {
                text: "Phase 5 · Vibe-Match · Set-Drop · Genre-Kurve"
                color: panel.neonPink
                font.pixelSize: 10
                font.letterSpacing: 2
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            // ==== Set-Drop ================================================
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "#0f1620"
                radius: 8
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.05)

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "SET-DROP"
                            color: panel.amber
                            font.pixelSize: 11
                            font.letterSpacing: 3
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            text: panel.setStatus
                            color: "#8899aa"
                            font.pixelSize: 10
                        }
                    }

                    Text {
                        text: "Ref-Set (WAV/MP3) hier reinziehen — oder Datei waehlen"
                        color: "#8899aa"
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Button {
                        text: "Set-Datei waehlen…"
                        Layout.fillWidth: true
                        onClicked: fileDlg.open()
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: "#0a0e14"
                        radius: 6
                        border.width: dropSet.containsDrag ? 2 : 1
                        border.color: dropSet.containsDrag ? panel.amber : Qt.rgba(1, 1, 1, 0.05)

                        ListView {
                            id: setList
                            anchors.fill: parent
                            anchors.margins: 6
                            clip: true
                            model: panel.setPicks
                            spacing: 2

                            delegate: Rectangle {
                                width: setList.width
                                height: 28
                                color: index % 2 === 0 ? "#111a25" : "#0f1720"
                                radius: 4
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 8
                                    anchors.rightMargin: 8
                                    Text { text: (index+1) + "."; color: panel.amber; font.pixelSize: 10; Layout.preferredWidth: 24 }
                                    Text { text: modelData.title; color: "#e6f1ff"; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: modelData.bpm > 0 ? modelData.bpm.toFixed(1) : ""; color: panel.neon; font.pixelSize: 10; Layout.preferredWidth: 44 }
                                    Button { text: "A"; onClicked: backend.player.deckA.loadTrack(modelData.id); implicitHeight: 22; implicitWidth: 26 }
                                    Button { text: "B"; onClicked: backend.player.deckB.loadTrack(modelData.id); implicitHeight: 22; implicitWidth: 26 }
                                }
                            }
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        }

                        Text {
                            anchors.centerIn: parent
                            visible: setList.count === 0
                            text: "keine Picks"
                            color: "#8899aa"
                            font.pixelSize: 10
                        }

                        DropArea {
                            id: dropSet
                            anchors.fill: parent
                            onDropped: (drop) => {
                                if (drop.hasUrls && drop.urls.length > 0) {
                                    var u = drop.urls[0].toString().replace("file:///", "")
                                    panel.setStatus = "analysiere…"
                                    backend.suggester.analyzeSet(u)
                                    drop.acceptProposedAction()
                                }
                            }
                        }
                    }
                }
            }

            // ==== Genre-Playlist ==========================================
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "#0f1620"
                radius: 8
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.05)

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    Text {
                        text: "GENRE-PLAYLIST (BPM-KURVE)"
                        color: panel.neonPink
                        font.pixelSize: 11
                        font.letterSpacing: 3
                        font.bold: true
                    }

                    GridLayout {
                        columns: 2
                        columnSpacing: 8
                        rowSpacing: 4
                        Layout.fillWidth: true

                        Text { text: "Genres (Komma):"; color: "#8899aa"; font.pixelSize: 10 }
                        TextField { id: fGenres; text: "House, Deep House, Techno"; Layout.fillWidth: true }

                        Text { text: "Dauer (min):"; color: "#8899aa"; font.pixelSize: 10 }
                        SpinBox { id: fLen; from: 30; to: 240; value: 60 }

                        Text { text: "BPM Start:"; color: "#8899aa"; font.pixelSize: 10 }
                        SpinBox { id: fStart; from: 60; to: 200; value: 118 }

                        Text { text: "BPM Peak:"; color: "#8899aa"; font.pixelSize: 10 }
                        SpinBox { id: fPeak; from: 60; to: 200; value: 128 }

                        Text { text: "BPM End:"; color: "#8899aa"; font.pixelSize: 10 }
                        SpinBox { id: fEnd; from: 60; to: 200; value: 122 }
                    }

                    Button {
                        text: "Playlist bauen"
                        Layout.fillWidth: true
                        onClicked: {
                            var gs = fGenres.text.split(",").map(function(s){return s.trim()}).filter(function(s){return s.length > 0})
                            panel.genrePicks = backend.suggester.buildGenrePlaylist(
                                gs, fLen.value, fStart.value, fPeak.value, fEnd.value, 4.0
                            )
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: "#0a0e14"
                        radius: 6
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, 0.05)

                        ListView {
                            id: genreList
                            anchors.fill: parent
                            anchors.margins: 6
                            clip: true
                            model: panel.genrePicks
                            spacing: 2

                            delegate: Rectangle {
                                width: genreList.width
                                height: 28
                                color: index % 2 === 0 ? "#111a25" : "#0f1720"
                                radius: 4
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 8
                                    anchors.rightMargin: 8
                                    Text { text: (index+1) + "."; color: panel.neonPink; font.pixelSize: 10; Layout.preferredWidth: 24 }
                                    Text { text: modelData.title; color: "#e6f1ff"; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: modelData.bpm > 0 ? modelData.bpm.toFixed(1) : ""; color: panel.neon; font.pixelSize: 10; Layout.preferredWidth: 44 }
                                    Button { text: "A"; onClicked: backend.player.deckA.loadTrack(modelData.id); implicitHeight: 22; implicitWidth: 26 }
                                    Button { text: "B"; onClicked: backend.player.deckB.loadTrack(modelData.id); implicitHeight: 22; implicitWidth: 26 }
                                }
                            }
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        }
                    }
                }
            }
        }
    }

    FileDialog {
        id: fileDlg
        nameFilters: ["Audio (*.wav *.mp3 *.flac *.m4a *.aac)"]
        onAccepted: {
            var u = selectedFile.toString().replace("file:///", "")
            panel.setStatus = "analysiere…"
            backend.suggester.analyzeSet(u)
        }
    }
}
