import QtQuick
import QtQuick.Controls
import QtQuick.Effects

Button {
    id: root
    property color neon: "#00e0ff"
    property bool active: false
    hoverEnabled: true

    background: Rectangle {
        implicitHeight: 34
        implicitWidth: 80
        radius: 6
        color: root.pressed ? Qt.darker(root.neon, 3.0)
             : root.active   ? Qt.darker(root.neon, 2.2)
             : "#1c2534"
        border.width: 1
        border.color: root.active || root.hovered ? root.neon : Qt.rgba(1,1,1,0.08)

        Behavior on color { ColorAnimation { duration: 100 } }
    }
    contentItem: Text {
        text: root.text
        color: root.active ? "#0a0e14" : (root.hovered ? root.neon : "#c9d5e1")
        font.pixelSize: 11
        font.letterSpacing: 1.5
        font.bold: root.active
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
