import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: dlg
    title: "Tastatur-Kuerzel"
    width: 780
    height: 600
    minimumWidth: 520
    minimumHeight: 380
    modality: Qt.NonModal
    color: "#0f1620"
    flags: Qt.Window

    function open() { show(); raise(); requestActivate(); reload() }

    property var actionList: []

    function reload() {
        actionList = backend.actions.listAll()
    }

    Connections {
        target: backend.actions
        function onShortcutsChanged() { dlg.reload() }
        function onRegistryChanged()  { dlg.reload() }
    }
    Component.onCompleted: reload()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "KEY BINDINGS"
                color: "#00e0ff"
                font.pixelSize: 13
                font.letterSpacing: 3
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            Text {
                text: "Zelle klicken → neue Taste druecken · ESC = abbrechen · Del = leer"
                color: "#8899aa"
                font.pixelSize: 10
            }
            Button {
                text: "Alle Defaults"
                onClicked: backend.actions.resetAllShortcuts()
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
                model: dlg.actionList
                spacing: 3

                delegate: Rectangle {
                    width: list.width
                    height: 34
                    color: index % 2 === 0 ? "#111a25" : "#0f1720"
                    radius: 4

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 8

                        Text {
                            text: modelData.category
                            color: "#ff2fbf"
                            font.pixelSize: 10
                            font.letterSpacing: 2
                            Layout.preferredWidth: 90
                        }
                        Text {
                            text: modelData.label
                            color: "#e6f1ff"
                            font.pixelSize: 12
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Rectangle {
                            id: keyCell
                            Layout.preferredWidth: 160
                            Layout.preferredHeight: 26
                            radius: 4
                            color: keyArea.capturing ? "#a78bfa" : "#1c2534"
                            border.width: 1
                            border.color: keyArea.capturing ? "#ff2fbf" : Qt.rgba(1, 1, 1, 0.08)

                            property bool capturing: false

                            Text {
                                anchors.centerIn: parent
                                text: keyArea.capturing
                                      ? "druecke Taste…"
                                      : (modelData.shortcut || "—")
                                color: keyArea.capturing ? "#0a0e14" :
                                       (modelData.shortcut ? "#00e0ff" : "#556677")
                                font.pixelSize: 11
                                font.bold: true
                                font.letterSpacing: 1
                            }

                            MouseArea {
                                id: keyArea
                                anchors.fill: parent
                                property bool capturing: keyCell.capturing
                                onClicked: {
                                    keyCell.capturing = true
                                    keyCatcher.forceActiveFocus()
                                }
                            }

                            Item {
                                id: keyCatcher
                                anchors.fill: parent
                                focus: keyCell.capturing
                                Keys.onPressed: (ev) => {
                                    if (!keyCell.capturing) return
                                    if (ev.key === Qt.Key_Escape) {
                                        keyCell.capturing = false
                                        return
                                    }
                                    if (ev.key === Qt.Key_Delete || ev.key === Qt.Key_Backspace) {
                                        backend.actions.setShortcut(modelData.id, "")
                                        keyCell.capturing = false
                                        return
                                    }
                                    if (ev.key === Qt.Key_Shift || ev.key === Qt.Key_Control ||
                                        ev.key === Qt.Key_Alt   || ev.key === Qt.Key_Meta) return
                                    var mods = []
                                    if (ev.modifiers & Qt.ControlModifier) mods.push("Ctrl")
                                    if (ev.modifiers & Qt.AltModifier)     mods.push("Alt")
                                    if (ev.modifiers & Qt.ShiftModifier)   mods.push("Shift")
                                    if (ev.modifiers & Qt.MetaModifier)    mods.push("Meta")
                                    var name = ev.text && ev.text.length === 1
                                             ? ev.text.toUpperCase()
                                             : dlg.keySpecialName(ev.key)
                                    if (!name) { keyCell.capturing = false; return }
                                    var seq = mods.concat([name]).join("+")
                                    backend.actions.setShortcut(modelData.id, seq)
                                    keyCell.capturing = false
                                    ev.accepted = true
                                }
                            }
                        }
                        Button {
                            text: "↺"
                            implicitHeight: 26
                            implicitWidth: 30
                            onClicked: backend.actions.resetShortcut(modelData.id)
                            ToolTip.visible: hovered
                            ToolTip.text: "Default wiederherstellen"
                        }
                    }
                }
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            Button {
                text: "Schliessen"
                onClicked: dlg.close()
            }
        }
    }

    function keySpecialName(k) {
        switch(k) {
        case Qt.Key_Space:  return "Space"
        case Qt.Key_Return: return "Return"
        case Qt.Key_Enter:  return "Enter"
        case Qt.Key_Tab:    return "Tab"
        case Qt.Key_Left:   return "Left"
        case Qt.Key_Right:  return "Right"
        case Qt.Key_Up:     return "Up"
        case Qt.Key_Down:   return "Down"
        case Qt.Key_F1:     return "F1"
        case Qt.Key_F2:     return "F2"
        case Qt.Key_F3:     return "F3"
        case Qt.Key_F4:     return "F4"
        case Qt.Key_F5:     return "F5"
        case Qt.Key_F6:     return "F6"
        case Qt.Key_F7:     return "F7"
        case Qt.Key_F8:     return "F8"
        case Qt.Key_F9:     return "F9"
        case Qt.Key_F10:    return "F10"
        case Qt.Key_F11:    return "F11"
        case Qt.Key_F12:    return "F12"
        case Qt.Key_Home:   return "Home"
        case Qt.Key_End:    return "End"
        case Qt.Key_PageUp: return "PgUp"
        case Qt.Key_PageDown: return "PgDown"
        }
        return ""
    }
}
