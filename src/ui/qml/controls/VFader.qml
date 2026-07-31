import QtQuick
import QtQuick.Controls

Slider {
    id: root
    orientation: Qt.Vertical
    from: 0.0
    to: 1.0
    value: 0.75
    property color neon: "#00e0ff"
    property string label: ""

    background: Rectangle {
        x: root.width * 0.5 - width * 0.5
        y: 0
        width: 6
        height: root.availableHeight
        radius: 3
        color: "#0f1620"
        border.width: 1
        border.color: Qt.rgba(1,1,1,0.06)

        Rectangle {
            width: parent.width
            height: parent.height * root.visualPosition
            y: parent.height - height
            color: root.neon
            radius: parent.radius
            opacity: 0.55
        }
    }
    handle: Rectangle {
        x: root.width * 0.5 - width * 0.5
        y: root.visualPosition * (root.availableHeight - height)
        width: 28
        height: 16
        radius: 4
        color: "#2a3a4f"
        border.color: root.neon
        border.width: 1
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.bottom
        anchors.topMargin: 4
        text: root.label
        color: "#8899aa"
        font.pixelSize: 9
        font.letterSpacing: 1
    }
}
