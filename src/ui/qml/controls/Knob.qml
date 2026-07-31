// Custom rotary knob mit LED-Ring, Neon-Glow, physik-artigem Drag-Feeling.
// Nutzt Item + Canvas + MouseArea. Wert-Range wird von außen via `from`/`to` gesetzt.
import QtQuick
import QtQuick.Effects

Item {
    id: root
    width: 72
    height: 92

    property real from: -1.0
    property real to:   1.0
    property real value: 0.0
    property real defaultValue: 0.0
    property string label: ""
    property string valueFormat: "" // z.B. "%.1f dB"; leer = kein Text
    property color glowColor: "#00e0ff"
    property color ringColor: Qt.rgba(1, 1, 1, 0.06)
    property real startAngle: -135    // Grad, 0 = 3 Uhr
    property real endAngle:   135
    property real sensitivity: 200.0  // Pixel für gesamten Range
    property bool bipolar: false      // true → mittige Nullstellung
    property real snapMid: 0.0        // Wert der als „Mitte" gilt (nur visuell)

    signal changed(real newValue)

    function _clamp(v) { return Math.max(from, Math.min(to, v)) }
    function _angleFor(v) {
        var t = (v - from) / (to - from)
        return startAngle + t * (endAngle - startAngle)
    }
    function _bipolarNormalized() {
        // -1..1 relative zur Mitte (für LED-Ring-Highlight)
        var mid = (from + to) * 0.5
        var half = (to - from) * 0.5
        return (value - mid) / half
    }

    Canvas {
        id: canvas
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        width: parent.width
        height: parent.width
        onPaint: {
            var ctx = getContext("2d");
            ctx.reset()
            var cx = width * 0.5
            var cy = height * 0.5
            var rOuter = width * 0.46
            var rInner = width * 0.34

            // LED-Ring (Track) — dunkel
            ctx.lineWidth = width * 0.08
            ctx.strokeStyle = "rgba(255,255,255,0.06)"
            ctx.beginPath()
            ctx.arc(cx, cy, rOuter, (root.startAngle - 90) * Math.PI / 180,
                                     (root.endAngle - 90) * Math.PI / 180)
            ctx.stroke()

            // LED-Ring aktive Sektion (vom Center bei bipolar, sonst vom Start)
            var actStart, actEnd
            var t = (root.value - root.from) / (root.to - root.from)
            var angA = root.startAngle + t * (root.endAngle - root.startAngle)
            if (root.bipolar) {
                var centerAng = (root.startAngle + root.endAngle) * 0.5
                actStart = Math.min(centerAng, angA)
                actEnd   = Math.max(centerAng, angA)
            } else {
                actStart = root.startAngle
                actEnd = angA
            }
            ctx.strokeStyle = root.glowColor
            ctx.beginPath()
            ctx.arc(cx, cy, rOuter, (actStart - 90) * Math.PI / 180,
                                     (actEnd - 90) * Math.PI / 180)
            ctx.stroke()

            // Knopf-Kreis
            var grad = ctx.createLinearGradient(cx, cy - rInner, cx, cy + rInner)
            grad.addColorStop(0.0, "#22303f")
            grad.addColorStop(1.0, "#0e1620")
            ctx.fillStyle = grad
            ctx.beginPath()
            ctx.arc(cx, cy, rInner, 0, Math.PI * 2)
            ctx.fill()
            ctx.strokeStyle = "rgba(255,255,255,0.08)"
            ctx.lineWidth = 1
            ctx.stroke()

            // Pointer-Linie
            var pa = (angA - 90) * Math.PI / 180
            ctx.strokeStyle = root.glowColor
            ctx.lineWidth = 3
            ctx.lineCap = "round"
            ctx.beginPath()
            ctx.moveTo(cx + Math.cos(pa) * rInner * 0.35,
                       cy + Math.sin(pa) * rInner * 0.35)
            ctx.lineTo(cx + Math.cos(pa) * rInner * 0.95,
                       cy + Math.sin(pa) * rInner * 0.95)
            ctx.stroke()
        }
    }
    // Glow-Overlay via MultiEffect
    MultiEffect {
        source: canvas
        anchors.fill: canvas
        blurEnabled: true
        blurMax: 32
        blur: 0.6
        brightness: 0.15
        opacity: 0.55
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: canvas.bottom
        anchors.topMargin: 2
        text: root.label
        color: "#8899aa"
        font.pixelSize: 10
        font.letterSpacing: 1.5
    }

    Text {
        visible: root.valueFormat.length > 0
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 0
        text: {
            var s = root.valueFormat
            // simples printf-like: nur %.Nf und %d
            if (s.indexOf("%.") >= 0) {
                var m = s.match(/%\.(\d)f/)
                var d = m ? parseInt(m[1]) : 1
                return s.replace(/%\.\d+f/, root.value.toFixed(d))
            }
            if (s.indexOf("%d") >= 0) return s.replace("%d", Math.round(root.value))
            return s
        }
        color: "#e6f1ff"
        font.pixelSize: 10
        z: 5
    }

    onValueChanged: canvas.requestPaint()

    MouseArea {
        anchors.fill: canvas
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        property real startY: 0
        property real startVal: 0
        cursorShape: Qt.SizeVerCursor

        onDoubleClicked: {
            root.value = root.defaultValue
            root.changed(root.value)
        }
        onPressed: (m) => {
            if (m.button === Qt.RightButton) {
                root.value = root.defaultValue
                root.changed(root.value)
                return
            }
            startY = m.y
            startVal = root.value
        }
        onPositionChanged: (m) => {
            if (!(m.buttons & Qt.LeftButton)) return
            var dy = startY - m.y   // hoch = größer
            var delta = (dy / root.sensitivity) * (root.to - root.from)
            root.value = root._clamp(startVal + delta)
            root.changed(root.value)
        }
        onWheel: (w) => {
            var step = (root.to - root.from) * 0.02
            root.value = root._clamp(root.value + (w.angleDelta.y > 0 ? step : -step))
            root.changed(root.value)
        }
    }
}
