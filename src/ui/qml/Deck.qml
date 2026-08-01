import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import "controls"

Rectangle {
    id: deck
    color: "#131a24"
    radius: 12
    border.width: deck.deckModel && deck.deckModel.isMaster ? 2 : 1
    border.color: deck.deckModel && deck.deckModel.isMaster
                  ? "#ff2fbf"
                  : Qt.rgba(1, 1, 1, 0.06)
    Behavior on border.color { ColorAnimation { duration: 220 } }
    Behavior on border.width { NumberAnimation { duration: 180 } }

    property var  deckModel: null        // DeckBridge Instanz
    property color neon: "#00e0ff"
    property string sideLabel: "A"
    property string deckId: "a"

    // Cue-/Loop-Slot-Refresh (Deck-State-Änderung triggert Reload)
    property var cueList: []
    property var loopList: []
    property var _cueLoopUpdater: Connections {
        target: deck.deckModel
        function onStateChanged() {
            if (!deck.deckModel) return
            deck.cueList = deck.deckModel.cues()
            deck.loopList = deck.deckModel.loops()
        }
    }
    Component.onCompleted: {
        if (deck.deckModel) {
            deck.cueList = deck.deckModel.cues()
            deck.loopList = deck.deckModel.loops()
        }
    }

    function cueAt(idx) {
        for (var i = 0; i < cueList.length; i++)
            if (cueList[i].idx === idx) return cueList[i]
        return null
    }
    function loopAt(idx) {
        for (var i = 0; i < loopList.length; i++)
            if (loopList[i].idx === idx) return loopList[i]
        return null
    }

    NormalizeDialog {
        id: normDlg
    }
    SavePushedDialog {
        id: pushDlg
    }

    // --- Beat-Pulse Ring ---
    Rectangle {
        id: pulseRing
        anchors.fill: parent
        radius: parent.radius
        color: "transparent"
        border.width: 2
        border.color: deck.neon
        opacity: 0.0
    }
    SequentialAnimation on opacity {
        id: pulseAnim
        running: false
        NumberAnimation { target: pulseRing; property: "opacity"; from: 0.7; to: 0.0; duration: 220; easing.type: Easing.OutQuad }
    }
    Connections {
        target: deck.deckModel
        function onPositionChanged() {
            if (deck.deckModel.isPlaying && deck.deckModel.beatInBar >= 1 && deck.deckModel.beatInBar !== deck._lastBeat) {
                deck._lastBeat = deck.deckModel.beatInBar
                pulseAnim.restart()
            }
        }
    }
    property int _lastBeat: 0

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // === Header: Seite + Titel + BPM + Key ===
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: deck.sideLabel
                color: deck.neon
                font.pixelSize: 28
                font.bold: true
                font.letterSpacing: 3
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Text {
                    text: (deck.deckModel && deck.deckModel.title) ? deck.deckModel.title : "— kein Track —"
                    color: "#e6f1ff"
                    font.pixelSize: 14
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text {
                    text: (deck.deckModel && deck.deckModel.artist) ? deck.deckModel.artist : ""
                    color: "#8899aa"
                    font.pixelSize: 11
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
            ColumnLayout {
                spacing: 0
                Text {
                    text: deck.deckModel ? deck.deckModel.effectiveBpm.toFixed(1) : "0.0"
                    color: deck.neon
                    font.pixelSize: 22
                    font.bold: true
                    horizontalAlignment: Text.AlignRight
                    Layout.alignment: Qt.AlignRight
                }
                RowLayout {
                    spacing: 6
                    Layout.alignment: Qt.AlignRight
                    Text {
                        text: (deck.deckModel && deck.deckModel.bpm > 0) ? "orig " + deck.deckModel.bpm.toFixed(1) : ""
                        color: "#556677"
                        font.pixelSize: 9
                    }
                    Text {
                        text: deck.deckModel && deck.deckModel.musicalKey
                              ? backend.player.formatKey(deck.deckModel.musicalKey)
                              : ""
                        color: "#ff2fbf"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }
        }

        // === Waveform (Peaks + Vocals + Beats) ===
        Rectangle {
            id: waveWrap
            Layout.fillWidth: true
            Layout.preferredHeight: 108
            radius: 6
            color: "#0a1018"
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.05)
            clip: true

            property var peaks: []
            property var vocals: []
            property var beats: []

            function refresh() {
                if (!deck.deckModel || !deck.deckModel.isLoaded) {
                    peaks = []; vocals = []; beats = []
                    canvas.requestPaint()
                    return
                }
                peaks  = deck.deckModel.waveformPeaks(Math.max(200, Math.floor(width)))
                vocals = deck.deckModel.vocalRegions()
                beats  = deck.deckModel.beatTicks(4096)
                canvas.requestPaint()
            }

            Connections {
                target: deck.deckModel
                function onStateChanged() { waveWrap.refresh() }
            }
            onWidthChanged: refresh()
            Component.onCompleted: refresh()

            Canvas {
                id: canvas
                anchors.fill: parent
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var W = width, H = height
                    ctx.fillStyle = "#0a1018"
                    ctx.fillRect(0, 0, W, H)

                    // --- Vocal-Regionen (violett-transparente Band-Overlays) ---
                    if (deck.deckModel && deck.deckModel.durationSec > 0 && waveWrap.vocals.length > 0) {
                        var dur = deck.deckModel.durationSec * 1000.0
                        ctx.fillStyle = Qt.rgba(0.65, 0.45, 0.98, 0.18)
                        for (var i = 0; i < waveWrap.vocals.length; i++) {
                            var v = waveWrap.vocals[i]
                            var x0 = (v.start_ms / dur) * W
                            var x1 = (v.end_ms   / dur) * W
                            ctx.fillRect(x0, 4, Math.max(1, x1 - x0), H - 8)
                        }
                    }

                    // --- Peaks (mirror) ---
                    var P = waveWrap.peaks
                    if (P.length > 0) {
                        var mid = H / 2
                        var stepX = W / P.length
                        var grad = ctx.createLinearGradient(0, 0, 0, H)
                        grad.addColorStop(0.0, deck.neon)
                        grad.addColorStop(0.5, Qt.rgba(0.0, 0.88, 1.0, 0.75))
                        grad.addColorStop(1.0, "#ff2fbf")
                        ctx.strokeStyle = grad
                        ctx.lineWidth = Math.max(1, stepX * 0.9)
                        for (var j = 0; j < P.length; j++) {
                            var amp = P[j] * (mid - 6)
                            var xx = j * stepX + stepX / 2
                            ctx.beginPath()
                            ctx.moveTo(xx, mid - amp)
                            ctx.lineTo(xx, mid + amp)
                            ctx.stroke()
                        }
                    }

                    // --- Beat-Ticks (dünne, transparente Marker) ---
                    if (deck.deckModel && deck.deckModel.durationSec > 0 && waveWrap.beats.length > 0) {
                        var durS = deck.deckModel.durationSec
                        ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.10)
                        ctx.lineWidth = 1
                        for (var k = 0; k < waveWrap.beats.length; k++) {
                            var bx = (waveWrap.beats[k] / durS) * W
                            ctx.beginPath()
                            ctx.moveTo(bx, 0)
                            ctx.lineTo(bx, H)
                            ctx.stroke()
                        }
                    }
                }
            }

            // Playhead (bewegt sich smooth ueber positionChanged)
            Rectangle {
                id: playhead
                visible: deck.deckModel && deck.deckModel.isLoaded
                width: 2
                height: parent.height
                color: deck.neon
                x: {
                    if (!deck.deckModel || deck.deckModel.durationSec <= 0) return 0
                    return (deck.deckModel.positionSec / deck.deckModel.durationSec) * parent.width
                }
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 0
                    width: 8; height: 8; radius: 4
                    color: deck.neon
                }
            }

            Text {
                anchors.centerIn: parent
                visible: !deck.deckModel || !deck.deckModel.isLoaded
                text: "Track auf Deck ziehen"
                color: "#556677"
                font.pixelSize: 11
                font.letterSpacing: 2
            }

            DropArea {
                anchors.fill: parent
                keys: ["application/x-musicsearcher-trackid"]
                onDropped: (drop) => {
                    var tid = parseInt(drop.getDataAsString("application/x-musicsearcher-trackid"))
                    if (!isNaN(tid) && deck.deckModel) deck.deckModel.loadTrack(tid)
                }
            }

            MouseArea {
                anchors.fill: parent
                onClicked: (m) => {
                    if (!deck.deckModel || deck.deckModel.durationSec <= 0) return
                    deck.deckModel.seek(m.x / width * deck.deckModel.durationSec)
                }
            }
        }

        // === Transport-Zeile ===
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            NeonButton {
                text: "CUE"
                neon: "#ffb020"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".cue")
            }
            NeonButton {
                text: deck.deckModel && deck.deckModel.isPlaying ? "PAUSE" : "PLAY"
                active: deck.deckModel && deck.deckModel.isPlaying
                neon: deck.neon
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".play_pause")
            }
            NeonButton {
                text: "SYNC"
                neon: "#ff2fbf"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".sync")
                ToolTip.visible: hovered
                ToolTip.text: "1x = BPM angleichen · 2x = Sync + Phrase-Lock"
            }
            NeonButton {
                text: deck.deckModel && deck.deckModel.keyLock ? "KEY ✓" : "KEY"
                active: deck.deckModel && deck.deckModel.keyLock
                neon: "#a78bfa"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".keypress")
                ToolTip.visible: hovered
                ToolTip.text: "1x = KeyLock · 2x = Key-Match zu Master"
            }
            NeonButton {
                text: "MASTER"
                active: deck.deckModel && deck.deckModel.isMaster
                neon: "#ff2fbf"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".become_master")
            }

            Item { Layout.fillWidth: true }

            // Beat-Indicator + phrasenweiser Countdown
            ColumnLayout {
                spacing: 2
                RowLayout {
                    spacing: 6
                    Rectangle {
                        width: 12; height: 12; radius: 6
                        color: deck.deckModel && deck.deckModel.beatInBar === 1 ? "#ff2fbf" :
                               deck.deckModel && deck.deckModel.beatInBar > 0    ? deck.neon : "#333"
                        opacity: deck.deckModel && deck.deckModel.beatInBar > 0 ? 1.0 : 0.3
                        Behavior on opacity { NumberAnimation { duration: 80 } }
                    }
                    Text {
                        text: deck.deckModel && deck.deckModel.beatInBar > 0
                              ? deck.deckModel.bar + "." + deck.deckModel.beatInBar
                              : "—"
                        color: "#c9d5e1"
                        font.pixelSize: 14
                        font.bold: true
                    }
                }
                // 16-Bar-Phrase-Balken
                Row {
                    spacing: 2
                    Repeater {
                        model: 16
                        Rectangle {
                            width: 6; height: 6; radius: 1
                            color: deck.deckModel && (deck.deckModel.phraseBeat - 1) === index
                                   ? "#ff2fbf" : Qt.rgba(1, 1, 1, 0.15)
                        }
                    }
                }
            }
        }

        // === Beatgrid-Korrektur ===
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Text {
                text: "BEATGRID"
                color: "#556677"
                font.pixelSize: 10
                font.letterSpacing: 2
            }
            NeonButton {
                text: "BPM /2"
                neon: "#8899aa"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".bpm_halve")
            }
            NeonButton {
                text: "BPM x2"
                neon: "#8899aa"
                onClicked: backend.actions.trigger("deck." + deck.deckId + ".bpm_double")
            }
            Item { Layout.fillWidth: true }

            // A10-Push (Live-Vorschau)
            Text { text: "PUSH"; color: "#ff2fbf"; font.pixelSize: 9; font.letterSpacing: 2 }
            Slider {
                Layout.preferredWidth: 100
                from: 0.0; to: 1.0
                value: deck.deckModel ? deck.deckModel.a10Value : 0.0
                onMoved: if (deck.deckModel) deck.deckModel.setA10(value)
                ToolTip.visible: hovered
                ToolTip.text: "A10 Vinyl-Push (Live-Compressor auf Deck)"
            }
            NeonButton {
                text: "SAVE PUSHED"
                neon: "#ff2fbf"
                onClicked: {
                    pushDlg.deckModel = deck.deckModel
                    pushDlg.open()
                }
                ToolTip.visible: hovered
                ToolTip.text: "A10 offline in Datei rendern"
            }

            NeonButton {
                text: "LUFS -14"
                neon: "#4ade80"
                onClicked: {
                    normDlg.deckModel = deck.deckModel
                    normDlg.open()
                }
                ToolTip.visible: hovered
                ToolTip.text: "Normalisieren auf -14 LUFS (playback_gain oder destruktiv)"
            }
        }

        // === Cue-Pads (8) ===
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3
            RowLayout {
                spacing: 4
                Text { text: "CUE"; color: "#8899aa"; font.pixelSize: 10; font.letterSpacing: 2 }
                Item { Layout.fillWidth: true }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 4
                Repeater {
                    model: 8
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 28
                        radius: 4
                        property var cue: deck.cueAt(index)
                        color: cue ? cue.color : "#1c2534"
                        opacity: cue ? 0.9 : 0.4
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, cue ? 0.15 : 0.05)
                        Column {
                            anchors.centerIn: parent
                            spacing: 0
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: (index + 1)
                                color: cue ? "#0a0e14" : "#556677"
                                font.pixelSize: 10
                                font.bold: true
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: cue ? (cue.label || "") : "—"
                                color: cue ? "#0a0e14" : "#556677"
                                font.pixelSize: 8
                                font.letterSpacing: 1
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onClicked: (m) => {
                                if (!deck.deckModel) return
                                if (m.button === Qt.RightButton) {
                                    if (cue) deck.deckModel.deleteCue(index)
                                    else     deck.deckModel.setCue(index)
                                } else {
                                    if (cue) deck.deckModel.jumpToCue(index)
                                    else     deck.deckModel.setCue(index)
                                }
                            }
                        }
                        ToolTip.visible: containsHover
                        ToolTip.text: cue
                            ? "Klick: springen · Rechtsklick: löschen"
                            : "Klick: Cue hier setzen"
                        HoverHandler { id: hh }
                        property bool containsHover: hh.hovered
                    }
                }
            }
        }

        // === Loop-Pads (8) + Loop-Toggle ===
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3
            RowLayout {
                spacing: 4
                Text { text: "LOOP"; color: "#8899aa"; font.pixelSize: 10; font.letterSpacing: 2 }
                Item { Layout.fillWidth: true }
                NeonButton {
                    text: deck.deckModel && deck.deckModel.loopActive ? "LOOP OFF" : "LOOP ON"
                    active: deck.deckModel && deck.deckModel.loopActive
                    neon: "#a78bfa"
                    onClicked: if (deck.deckModel) deck.deckModel.toggleLoop()
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 4
                Repeater {
                    model: 8
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 28
                        radius: 4
                        property var lp: deck.loopAt(index)
                        color: lp ? "#a78bfa" : "#1c2534"
                        opacity: lp ? 0.9 : 0.4
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, lp ? 0.2 : 0.05)
                        Column {
                            anchors.centerIn: parent
                            spacing: 0
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: (index + 1)
                                color: lp ? "#0a0e14" : "#556677"
                                font.pixelSize: 10
                                font.bold: true
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: lp ? (lp.beats + "B") : "—"
                                color: lp ? "#0a0e14" : "#556677"
                                font.pixelSize: 8
                                font.letterSpacing: 1
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: if (lp && deck.deckModel) deck.deckModel.triggerLoop(index)
                        }
                        ToolTip.visible: containsHover
                        ToolTip.text: lp
                            ? ("Loop " + lp.beats + " Beats — " + (lp.label || ""))
                            : "kein Loop-Slot belegt"
                        HoverHandler { id: lhh }
                        property bool containsHover: lhh.hovered
                    }
                }
            }
        }

        // === Tempo-Fader ===
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { text: "TEMPO"; color: "#8899aa"; font.pixelSize: 10; font.letterSpacing: 2 }
            Slider {
                Layout.fillWidth: true
                from: -0.16
                to: 0.16
                value: deck.deckModel ? (deck.deckModel.tempoRatio - 1.0) : 0.0
                onMoved: if (deck.deckModel) deck.deckModel.setTempoRatio(1.0 + value)
            }
            Text {
                text: {
                    var v = deck.deckModel ? (deck.deckModel.tempoRatio - 1.0) * 100.0 : 0.0
                    return (v >= 0 ? "+" : "") + v.toFixed(2) + " %"
                }
                color: "#e6f1ff"
                font.pixelSize: 10
            }
        }

        // === Stem Panel ===
        StemPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: 140
            deckModel: deck.deckModel
            deckColor: deck.neon
        }
    }
}
