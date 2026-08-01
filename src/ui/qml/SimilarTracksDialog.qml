import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: dlg
    title: "Aehnliche Tracks — Vibe-Match"
    width: 840
    height: 600
    minimumWidth: 560
    minimumHeight: 380
    modality: Qt.NonModal
    color: "#0f1620"
    flags: Qt.Window

    property int refTrackId: -1
    property string refTitle: ""
    property var results: []
    property string mode: "offline"

    function open() { show(); raise(); requestActivate() }

    function openFor(trackId, title) {
        dlg.refTrackId = trackId
        dlg.refTitle = title
        dlg.mode = "offline"
        dlg.runSearch()
        dlg.open()
    }

    function runSearch() {
        if (refTrackId < 0) return
        results = backend.suggester.findSimilar(refTrackId, 25, tolSlider.value)
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: "SIMILAR TRACKS · " + dlg.refTitle
                color: "#00e0ff"
                font.pixelSize: 13
                font.letterSpacing: 3
                font.bold: true
                elide: Text.ElideRight
            }
            Button {
                text: "Schliessen"
                onClicked: dlg.close()
            }
        }

        RowLayout {
            spacing: 6
            Layout.fillWidth: true

            Repeater {
                model: [
                    {k: "offline", label: "OFFLINE (Vibe-Vector)"},
                    {k: "hybrid",  label: "HYBRID (Vibe + Online-Genres)"},
                    {k: "online",  label: "ONLINE (MusicBrainz + Discogs)"},
                ]
                Button {
                    text: modelData.label
                    highlighted: dlg.mode === modelData.k
                    onClicked: {
                        dlg.mode = modelData.k
                        dlg.runSearch()
                    }
                }
            }
            Item { Layout.fillWidth: true }
            Text {
                text: "BPM-Toleranz: " + tolSlider.value.toFixed(0)
                color: "#8899aa"
                font.pixelSize: 10
            }
            Slider {
                id: tolSlider
                from: 2; to: 20; value: 8
                Layout.preferredWidth: 140
                onPressedChanged: if (!pressed) dlg.runSearch()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#131a24"
            radius: 8
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.05)

            ListView {
                id: list
                anchors.fill: parent
                anchors.margins: 6
                clip: true
                model: dlg.results
                spacing: 3

                delegate: Rectangle {
                    width: list.width
                    height: 42
                    color: mouseA.containsMouse ? "#1a2434" : "#111a25"
                    radius: 5

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 8

                        Rectangle {
                            width: 40; height: 26; radius: 4
                            color: "#00e0ff"
                            Text {
                                anchors.centerIn: parent
                                text: modelData.score.toFixed(2)
                                color: "#0a0e14"
                                font.pixelSize: 11
                                font.bold: true
                            }
                        }
                        Text {
                            text: modelData.title
                            color: "#e6f1ff"
                            font.pixelSize: 12
                            elide: Text.ElideRight
                            Layout.preferredWidth: 260
                        }
                        Text {
                            text: modelData.artist
                            color: "#8899aa"
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            Layout.preferredWidth: 180
                        }
                        Text {
                            text: modelData.bpm > 0 ? modelData.bpm.toFixed(1) : ""
                            color: "#00e0ff"
                            font.pixelSize: 11
                            Layout.preferredWidth: 44
                        }
                        Text {
                            text: modelData.key
                            color: "#ff2fbf"
                            font.pixelSize: 11
                            Layout.preferredWidth: 44
                        }
                        Text {
                            text: modelData.reason || ""
                            color: "#ffb020"
                            font.pixelSize: 10
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Button {
                            text: "→ A"
                            onClicked: backend.player.deckA.loadTrack(modelData.id)
                        }
                        Button {
                            text: "→ B"
                            onClicked: backend.player.deckB.loadTrack(modelData.id)
                        }
                    }

                    MouseArea {
                        id: mouseA
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.NoButton
                    }
                }

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }

            Text {
                anchors.centerIn: parent
                visible: list.count === 0
                text: "keine Vorschlaege — pruef ob Ref-Track BPM+Energy hat"
                color: "#8899aa"
                font.pixelSize: 12
            }
        }
    }
}
