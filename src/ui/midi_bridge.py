"""QML-Bridge fuer MIDI: Port-Liste, Verbinden, Learn-Mode.

Wird von `main.py` konditional gebaut. Wenn `python-rtmidi` fehlt, meldet die
Bridge `available=False` und der Dialog zeigt einen Install-Hinweis.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Property, Signal, Slot

from ..core.midi import MidiBinding, MidiRuntime, load_map, save_map


class MidiBridge(QObject):
    portChanged = Signal()
    bindingsChanged = Signal()
    learnFinished = Signal("QVariant")

    def __init__(self, actions, player_bridge, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._actions = actions
        self._player = player_bridge
        self._runtime = MidiRuntime(
            action_trigger=self._trigger_action,
            slot_dispatch=self._dispatch_slot,
            midi_map=load_map(),
        )

    # ---- Dispatch --------------------------------------------------------

    def _trigger_action(self, action_id: str) -> bool:
        return self._actions.trigger(action_id)

    def _dispatch_slot(self, target: str, value: float) -> None:
        """target-Syntax: 'player.setCrossfader' | 'deckA.setTempoRatio' etc."""
        obj = None
        method = None
        if target.startswith("player."):
            obj = self._player
            method = target.split(".", 1)[1]
        elif target.startswith("deckA."):
            obj = self._player.deckA
            method = target.split(".", 1)[1]
        elif target.startswith("deckB."):
            obj = self._player.deckB
            method = target.split(".", 1)[1]
        if obj is None or not hasattr(obj, method):
            return
        try:
            getattr(obj, method)(float(value))
        except Exception as exc:
            print(f"[MIDI] Dispatch {target}({value}) fehlgeschlagen: {exc}")

    # ---- QML-Slots -------------------------------------------------------

    @Property(bool, constant=True)
    def available(self) -> bool:
        return self._runtime.available

    @Slot(result=list)
    def listPorts(self) -> list[str]:  # noqa: N802
        return self._runtime.list_ports()

    @Slot(str, result=bool)
    def openPort(self, name: str) -> bool:  # noqa: N802
        ok = self._runtime.open_port(name)
        if ok:
            self.portChanged.emit()
        return ok

    @Slot()
    def closePort(self) -> None:  # noqa: N802
        self._runtime.close()
        self.portChanged.emit()

    @Property(str, notify=portChanged)
    def currentPort(self) -> str:
        return self._runtime._port_name or ""

    @Slot(result=list)
    def bindings(self) -> list[dict]:
        return [b.__dict__ for b in self._runtime.midi_map.bindings]

    @Slot(str)
    def startLearn(self, target: str) -> None:  # noqa: N802
        def cb(b: MidiBinding) -> None:
            # bestehendes Binding auf gleichem target ersetzen
            self._runtime.midi_map.bindings = [
                x for x in self._runtime.midi_map.bindings
                if (x.action_id or x.slot_target) != target
            ]
            self._runtime.midi_map.bindings.append(b)
            save_map(self._runtime.midi_map)
            self.bindingsChanged.emit()
            self.learnFinished.emit(b.__dict__)
        self._runtime.start_learn(target, cb)

    @Slot(str)
    def clearBinding(self, target: str) -> None:  # noqa: N802
        self._runtime.midi_map.bindings = [
            x for x in self._runtime.midi_map.bindings
            if (x.action_id or x.slot_target) != target
        ]
        save_map(self._runtime.midi_map)
        self.bindingsChanged.emit()

    @Slot()
    def resetToDefault(self) -> None:  # noqa: N802
        from ..core.midi import default_map_sc_live_4
        self._runtime.midi_map = default_map_sc_live_4()
        save_map(self._runtime.midi_map)
        self.bindingsChanged.emit()
