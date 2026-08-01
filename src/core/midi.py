"""MIDI-Controller-Bridge (Phase 9).

Basiert auf `python-rtmidi` (import lazy — nicht Pflicht im Fundament).
Ein Controller-Mapping ordnet MIDI-Nachrichten (Note, CC) den Action-IDs aus
`Actions` zu. Parameter-Slider (Fader/Knob) koennen zusaetzlich auf
`float`-Slots im PlayerBridge/DeckBridge gemappt werden — der Wert wird
0..127 → 0..1 (oder 0..1 bipolar) normalisiert.

Default-Map: Denon SC Live 4 (Phase 9.1 wird konkretisiert). Aktuell wird ein
neutrales Default-Set geliefert (Note-On → Play/Cue/Sync, CC → Crossfader,
Master-Gain), das der User via `midi_map.json` ueberschreiben kann.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from platformdirs import user_data_dir
    _CFG_DIR = Path(user_data_dir("MusicSearcher", "MMM"))
except ImportError:
    _CFG_DIR = Path(__file__).resolve().parents[2] / "data"

MIDI_MAP_FILE = _CFG_DIR / "midi_map.json"


# ---- Datenmodell -------------------------------------------------------

@dataclass
class MidiBinding:
    """Eine MIDI-Nachricht (Note/CC + Channel) triggert entweder eine Action
    oder ruft einen parametrisierten Slot mit dem normierten Wert auf.
    """
    kind: str            # "note" | "cc"
    channel: int         # 0..15
    number: int          # Note-Nr oder CC-Nr
    action_id: Optional[str] = None    # aus Actions-Registry
    slot_target: Optional[str] = None  # "player.setCrossfader" o.ae.
    scale: str = "unit"                # "unit" (0..1) | "bipolar" (-1..1) | "raw" (0..127)


@dataclass
class MidiMap:
    device_name: str = ""
    bindings: list[MidiBinding] = field(default_factory=list)


# ---- Default: Denon SC Live 4 (Grob-Skizze) ----------------------------
# Die endgueltige Map wird beim ersten Hardware-Kontakt mit dem SC Live 4
# eingemessen (Learn-Mode). Diese Defaults sind sinnvolle Startwerte.

def default_map_sc_live_4() -> MidiMap:
    return MidiMap(
        device_name="Denon DJ SC Live 4",
        bindings=[
            # Deck A: Play, Cue, Sync
            MidiBinding("note", 0, 0x3B, action_id="deck.a.play_pause"),
            MidiBinding("note", 0, 0x3A, action_id="deck.a.cue"),
            MidiBinding("note", 0, 0x40, action_id="deck.a.sync"),
            # Deck B: Play, Cue, Sync
            MidiBinding("note", 1, 0x3B, action_id="deck.b.play_pause"),
            MidiBinding("note", 1, 0x3A, action_id="deck.b.cue"),
            MidiBinding("note", 1, 0x40, action_id="deck.b.sync"),
            # Crossfader (CC 0x0C, channel 0)
            MidiBinding("cc", 0, 0x0C, slot_target="player.setCrossfader", scale="bipolar"),
            # Master Gain (CC 0x0D)
            MidiBinding("cc", 0, 0x0D, slot_target="player.setMasterGain", scale="unit"),
            # Deck A Tempo-Fader (CC 0x08, ch 0)
            MidiBinding("cc", 0, 0x08, slot_target="deckA.setTempoRatio", scale="bipolar"),
            # Deck B Tempo-Fader (CC 0x08, ch 1)
            MidiBinding("cc", 1, 0x08, slot_target="deckB.setTempoRatio", scale="bipolar"),
        ],
    )


def load_map() -> MidiMap:
    if MIDI_MAP_FILE.exists():
        try:
            data = json.loads(MIDI_MAP_FILE.read_text(encoding="utf-8"))
            bindings = [MidiBinding(**b) for b in data.get("bindings", [])]
            return MidiMap(device_name=data.get("device_name", ""), bindings=bindings)
        except Exception as exc:
            print(f"[MIDI] midi_map.json fehlerhaft: {exc} — nutze Default")
    return default_map_sc_live_4()


def save_map(m: MidiMap) -> None:
    try:
        MIDI_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        MIDI_MAP_FILE.write_text(
            json.dumps({
                "device_name": m.device_name,
                "bindings": [b.__dict__ for b in m.bindings],
            }, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[MIDI] midi_map.json speichern fehlgeschlagen: {exc}")


# ---- Runtime -----------------------------------------------------------

class MidiRuntime:
    """Haelt eine offene rtmidi-Input-Verbindung + dispatched Messages.

    Wird von `main.py` optional aktiviert — wenn `python-rtmidi` nicht
    installiert ist, wird ein No-Op-Runtime zurueckgegeben.
    """

    def __init__(
        self,
        action_trigger: Callable[[str], bool],
        slot_dispatch: Callable[[str, float], None],
        midi_map: Optional[MidiMap] = None,
    ) -> None:
        self.action_trigger = action_trigger
        self.slot_dispatch = slot_dispatch
        self.midi_map = midi_map or load_map()
        self._midi_in: Any = None
        self._port_name: Optional[str] = None
        self._available = self._probe()
        self._learn_target: Optional[str] = None
        self._on_learn: Optional[Callable[[MidiBinding], None]] = None

    def _probe(self) -> bool:
        try:
            import rtmidi   # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def available(self) -> bool:
        return self._available

    def list_ports(self) -> list[str]:
        if not self._available:
            return []
        import rtmidi
        m = rtmidi.MidiIn()
        try:
            return list(m.get_ports())
        finally:
            del m

    def open_port(self, name_or_index: str | int) -> bool:
        if not self._available:
            return False
        import rtmidi
        m = rtmidi.MidiIn()
        try:
            ports = m.get_ports()
            idx = -1
            if isinstance(name_or_index, int):
                idx = int(name_or_index)
            else:
                for i, p in enumerate(ports):
                    if str(name_or_index).lower() in p.lower():
                        idx = i
                        break
            if idx < 0 or idx >= len(ports):
                return False
            m.open_port(idx)
            m.set_callback(self._on_message)
            self._midi_in = m
            self._port_name = ports[idx]
            return True
        except Exception as exc:
            print(f"[MIDI] Port oeffnen fehlgeschlagen: {exc}")
            return False

    def close(self) -> None:
        if self._midi_in is not None:
            try:
                self._midi_in.close_port()
            except Exception:
                pass
            self._midi_in = None
            self._port_name = None

    def start_learn(self, target: str, cb: Callable[[MidiBinding], None]) -> None:
        """Naechste eingehende MIDI-Nachricht wird `target` (Action-ID oder
        Slot) zugeordnet. Der Callback erhaelt das neue Binding."""
        self._learn_target = target
        self._on_learn = cb

    def _on_message(self, event, _data=None) -> None:  # rtmidi-Callback
        msg, _ts = event
        if not msg:
            return
        status = msg[0]
        kind = None
        channel = status & 0x0F
        if 0x90 <= status <= 0x9F and len(msg) >= 2 and msg[2] > 0:
            kind, number, value = "note", msg[1], msg[2]
        elif 0xB0 <= status <= 0xBF and len(msg) >= 3:
            kind, number, value = "cc", msg[1], msg[2]
        else:
            return

        if self._learn_target is not None and self._on_learn is not None:
            b = MidiBinding(kind=kind, channel=channel, number=number,
                            action_id=self._learn_target if "." in self._learn_target else None,
                            slot_target=self._learn_target if "." not in self._learn_target else None)
            self._on_learn(b)
            self._learn_target = None
            self._on_learn = None
            return

        for b in self.midi_map.bindings:
            if b.kind != kind or b.channel != channel or b.number != number:
                continue
            if b.action_id:
                self.action_trigger(b.action_id)
                return
            if b.slot_target:
                v = _scale(value, b.scale)
                self.slot_dispatch(b.slot_target, v)
                return


def _scale(v: int, mode: str) -> float:
    v = max(0, min(127, int(v)))
    if mode == "raw":
        return float(v)
    if mode == "bipolar":
        return (v / 127.0) * 2.0 - 1.0
    return v / 127.0
