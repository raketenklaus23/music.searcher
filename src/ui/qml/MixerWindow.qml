import QtQuick
import QtQuick.Controls
import QtQuick.Window

Window {
    id: mw
    title: "Mixer (Floating)"
    width: 720
    height: 900
    minimumWidth: 360
    minimumHeight: 320
    color: "#0a0e14"
    flags: Qt.Window

    function open() { show(); raise(); requestActivate() }

    Mixer {
        anchors.fill: parent
        anchors.margins: 8
        onRequestDetach: mw.close()   // Detach-Button im Floating-Fenster schliesst nur wieder
    }
}
