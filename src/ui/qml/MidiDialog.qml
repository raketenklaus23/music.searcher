import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: dlg
    title: "MIDI-Controller"
    width: 780
    height: 600
    minimumWidth: 520
    minimumHeight: 380
    modality: Qt.NonModal
    color: "#0f1620"
    flags: Qt.Window

    function open() { show(); raise(); requestActivate(); reload() }

    property var portList: []
    property var bindingList: []
    property string learnTarget: ""

    function reload() {
        portList = backend.midi.listPorts()
        bindingList = backend.midi.bindings()
    }

    Connections {
        target: backend.midi
        function onBindingsChanged() { dlg.bindingList = backend.midi.bindings() }
        function onLearnFinished(b) {
            dlg.learnTarget = ""
            dlg.bindingList = backend.midi.bindings()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "MIDI-CONTROLLER"
                color: "#a78bfa"
                font.pixelSize: 13
                font.letterSpacing: 3
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            Text {
                text: backend.midi.available
                      ? (backend.midi.currentPort ? "verbunden: " + backend.midi.currentPort : "kein Port")
                      : "python-rtmidi fehlt (pip install python-rtmidi)"
                color: backend.midi.available ? "#8899aa" : "#ffb020"
                font.pixelSize: 10
            }
        }

        RowLayout {
            Layout.fillWidth: true
            enabled: backend.midi.available
            ComboBox {
                id: portCombo
                Layout.fillWidth: true
                model: dlg.portList
            }
            Button {
                text: "Verbinden"
                onClicked: backend.midi.openPort(portCombo.currentText)
            }
            Button {
                text: "Trennen"
                onClicked: backend.midi.closePort()
            }
            Button {
                text: "Ports neu suchen"
                onClicked: dlg.reload()
            }
            Button {
                text: "SC Live 4 Default"
                onClicked: backend.midi.resetToDefault()
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
                model: dlg.bindingList
                spacing: 3

                delegate: Rectangle {
                    width: list.width
                    height: 30
                    color: index % 2 === 0 ? "#111a25" : "#0f1720"
                    radius: 4

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 8

                        Rectangle {
                            width: 36; height: 20; radius: 3
                            color: modelData.kind === "note" ? "#00e0ff" : "#ff2fbf"
                            Text {
                                anchors.centerIn: parent
                                text: modelData.kind.toUpperCase()
                                color: "#0a0e14"
                                font.pixelSize: 9
                                font.bold: true
                            }
                        }
                        Text {
                            text: "Ch " + (modelData.channel + 1)
                            color: "#8899aa"
                            font.pixelSize: 10
                            Layout.preferredWidth: 40
                        }
                        Text {
                            text: "#" + modelData.number
                            color: "#c9d5e1"
                            font.pixelSize: 10
                            Layout.preferredWidth: 44
                        }
                        Text {
                            text: modelData.action_id
                                  ? "action: " + modelData.action_id
                                  : ("slot: " + modelData.slot_target + " · " + modelData.scale)
                            color: "#e6f1ff"
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Button {
                            text: dlg.learnTarget === (modelData.action_id || modelData.slot_target)
                                  ? "…lernt"
                                  : "Learn"
                            implicitHeight: 22
                            onClicked: {
                                var tgt = modelData.action_id || modelData.slot_target
                                dlg.learnTarget = tgt
                                backend.midi.startLearn(tgt)
                            }
                        }
                        Button {
                            text: "×"
                            implicitHeight: 22
                            implicitWidth: 26
                            onClicked: {
                                var tgt = modelData.action_id || modelData.slot_target
                                backend.midi.clearBinding(tgt)
                            }
                        }
                    }
                }
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: "Hinweis: mit Learn die naechste Note/CC am Controller senden. "
                      + "Default-Map ist Denon SC Live 4 (Play/Cue/Sync/Crossfader/Tempo-Fader)."
                color: "#8899aa"
                font.pixelSize: 10
                wrapMode: Text.WordWrap
            }
            Button {
                text: "Schliessen"
                onClicked: dlg.close()
            }
        }
    }
}
