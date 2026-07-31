"""QObject-Bridges für Player, Decks, Mixer, AudioSettings."""
from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Optional

from PySide6.QtCore import (
    QObject,
    Property,
    Signal,
    Slot,
    QTimer,
)

from ..audio.mixer import CrossfadeCurve
from ..audio.player import Player
from ..audio.sync import KeyMode, SnapMode, SyncMode
from ..core.keys import all_keys, camelot_to_openkey, compatible_keys, format_key
from ..core.library import Library

_DOUBLE_PRESS_WINDOW_S = 0.32   # innerhalb dieser Zeit gilt der 2. Klick als Double-Press


class DeckBridge(QObject):
    """Ein QML-nutzbares Deck. Nur Params, keine schwere Logik."""

    stateChanged = Signal()
    positionChanged = Signal()

    def __init__(self, player: Player, deck_id: str, library: Library, parent=None):
        super().__init__(parent)
        self._player = player
        self._id = deck_id
        self._library = library
        self._deck = player.deck_a if deck_id == "a" else player.deck_b

        # Dual-Press-Timing
        self._last_sync_press = 0.0
        self._last_key_press = 0.0

        # Poll-Timer für Position/Beat-Counter (30 fps reicht für UI)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    # ---- Slots aus QML: Track/Transport ------------------------------

    @Slot(int)
    def loadTrack(self, track_id: int) -> None:  # noqa: N802
        t = self._library.get_track(track_id)
        if t is None:
            return
        try:
            self._deck.load(Path(t.path), track_id=t.id, bpm=t.bpm, key=t.key)
            self.stateChanged.emit()
        except Exception as exc:
            print(f"[Deck {self._id}] Load failed: {exc}")

    @Slot()
    def play(self) -> None:
        self._deck.play()
        self._player.sync.notify_deck_started(self._id)
        self.stateChanged.emit()

    @Slot()
    def pause(self) -> None:
        self._deck.pause()
        self._player.sync.notify_deck_stopped(self._id)
        self.stateChanged.emit()

    @Slot()
    def toggle(self) -> None:
        if self._deck.state.playing:
            self.pause()
        else:
            self.play()

    @Slot()
    def cue(self) -> None:
        if self._deck.state.playing:
            self._deck.pause()
            self._deck.jump_to_cue()
            self._player.sync.notify_deck_stopped(self._id)
        else:
            self._deck.set_cue()
        self.stateChanged.emit()

    @Slot(float)
    def seek(self, sec: float) -> None:
        self._deck.seek_seconds(sec)

    # ---- Sync mit Dual-Press ----------------------------------------

    @Slot()
    def sync(self) -> None:
        """User-Klick auf SYNC — Dual-Press-Detection.

        1x = einmaliges BPM-Angleichen (kein Lock)
        2x = kontinuierlicher Sync mit Downbeat-Alignment
        """
        now = monotonic()
        if now - self._last_sync_press <= _DOUBLE_PRESS_WINDOW_S:
            self._player.sync.bpm_lock(self._id, SnapMode.HARD)
            self._last_sync_press = 0.0
        else:
            self._player.sync.bpm_oneshot(self._id)
            self._last_sync_press = now
        self.stateChanged.emit()

    @Slot()
    def unsync(self) -> None:
        self._player.sync.unsync(self._id)
        self.stateChanged.emit()

    # ---- Key mit Dual-Press ----------------------------------------

    @Slot()
    def keyPress(self) -> None:  # noqa: N802
        """1x = KeyLock an/aus toggeln; 2x = Key-Match zu Master."""
        now = monotonic()
        if now - self._last_key_press <= _DOUBLE_PRESS_WINDOW_S:
            self._player.sync.key_match(self._id)
            self._last_key_press = 0.0
        else:
            # Toggle KeyLock beim einfachen Press
            if self._deck.state.key_lock and self._deck.state.pitch_semitones == 0.0:
                self._player.sync.key_reset(self._id)
            else:
                self._player.sync.key_lock(self._id)
            self._last_key_press = now
        self.stateChanged.emit()

    # ---- Beatgrid-Fix (Halbtempo/Doppeltempo) -----------------------

    @Slot()
    def halveBpm(self) -> None:  # noqa: N802
        """Kein Time-Stretch — korrigiert die *angenommene* BPM (Beatgrid-Fix)."""
        if self._deck.state.bpm:
            self._deck.state.bpm = self._deck.state.bpm / 2.0
            self.stateChanged.emit()

    @Slot()
    def doubleBpm(self) -> None:  # noqa: N802
        if self._deck.state.bpm:
            self._deck.state.bpm = self._deck.state.bpm * 2.0
            self.stateChanged.emit()

    # ---- Basis-Params ----------------------------------------------

    @Slot(float)
    def setTempoRatio(self, r: float) -> None:  # noqa: N802
        self._deck.set_tempo_ratio(r)
        self.stateChanged.emit()

    @Slot(bool)
    def setKeyLock(self, on: bool) -> None:  # noqa: N802
        self._deck.set_key_lock(on)
        self.stateChanged.emit()

    @Slot(float)
    def setPitchSemitones(self, s: float) -> None:  # noqa: N802
        self._deck.set_pitch_semitones(s)
        self.stateChanged.emit()

    @Slot(float)
    def setGainDb(self, db: float) -> None:  # noqa: N802
        self._deck.set_gain_db(db)

    @Slot(float)
    def setVolume(self, v: float) -> None:  # noqa: N802
        self._deck.set_volume(v)

    @Slot()
    def becomeMaster(self) -> None:  # noqa: N802
        self._player.sync.set_master_override(self._id)
        self.stateChanged.emit()

    # ---- EQ (delegiert an Mixer.strip_*) ----------------------------

    @Slot(float)
    def setEqLow(self, db: float) -> None:  # noqa: N802
        self._strip().set_low(db)

    @Slot(float)
    def setEqLowMid(self, db: float) -> None:  # noqa: N802
        self._strip().set_lowmid(db)

    @Slot(float)
    def setEqHighMid(self, db: float) -> None:  # noqa: N802
        self._strip().set_highmid(db)

    @Slot(float)
    def setEqHigh(self, db: float) -> None:  # noqa: N802
        self._strip().set_high(db)

    def _strip(self):
        return self._player.mixer.strip_a if self._id == "a" else self._player.mixer.strip_b

    # ---- Properties für QML -----------------------------------------

    @Property(str, notify=stateChanged)
    def deckId(self) -> str:
        return self._id

    @Property(str, notify=stateChanged)
    def title(self) -> str:
        if self._deck.state.track_id is None:
            return ""
        t = self._library.get_track(self._deck.state.track_id)
        return (t.title or "") if t else ""

    @Property(str, notify=stateChanged)
    def artist(self) -> str:
        if self._deck.state.track_id is None:
            return ""
        t = self._library.get_track(self._deck.state.track_id)
        return (t.artist or "") if t else ""

    @Property(bool, notify=stateChanged)
    def isPlaying(self) -> bool:
        return self._deck.state.playing

    @Property(bool, notify=stateChanged)
    def isLoaded(self) -> bool:
        return self._deck.is_loaded()

    @Property(bool, notify=stateChanged)
    def isMaster(self) -> bool:
        return self._player.sync.master == self._id

    @Property(float, notify=stateChanged)
    def bpm(self) -> float:
        return float(self._deck.state.bpm or 0.0)

    @Property(float, notify=stateChanged)
    def effectiveBpm(self) -> float:
        return float((self._deck.state.bpm or 0.0) * self._deck.state.tempo_ratio)

    @Property(str, notify=stateChanged)
    def musicalKey(self) -> str:
        return self._deck.state.key or ""

    @Property(float, notify=stateChanged)
    def tempoRatio(self) -> float:
        return self._deck.state.tempo_ratio

    @Property(bool, notify=stateChanged)
    def keyLock(self) -> bool:
        return self._deck.state.key_lock

    @Property(float, notify=stateChanged)
    def pitchSemitones(self) -> float:
        return self._deck.state.pitch_semitones

    @Property(float, notify=positionChanged)
    def positionSec(self) -> float:
        return self._deck.state.playhead_frames / self._deck.engine_sr

    @Property(float, notify=stateChanged)
    def durationSec(self) -> float:
        return self._deck.state.duration_s

    @Property(int, notify=positionChanged)
    def beatInBar(self) -> int:
        p = self._player.sync.beat_position(self._id)
        return p[1] if p else 0

    @Property(int, notify=positionChanged)
    def bar(self) -> int:
        p = self._player.sync.beat_position(self._id)
        return p[0] if p else 0

    @Property(int, notify=positionChanged)
    def phraseBeat(self) -> int:
        """1..16 innerhalb der 16-Bar-Phrase."""
        p = self._player.sync.beat_position(self._id)
        return p[2] if p else 0

    def _on_tick(self) -> None:
        # Sync-Tick, damit Phase-Lock nachjustiert wird
        self._player.sync.tick()
        self.positionChanged.emit()


class PlayerBridge(QObject):
    """Übergreifende Player-Steuerung: Mixer, Sync, Engine-Settings, Key-Notation."""

    engineChanged = Signal()
    devicesChanged = Signal()
    keyNotationChanged = Signal()

    def __init__(self, player: Player, library: Library, parent=None):
        super().__init__(parent)
        self._player = player
        self._library = library
        self._deck_a = DeckBridge(player, "a", library, self)
        self._deck_b = DeckBridge(player, "b", library, self)
        self._key_notation = "camelot"   # oder "openkey"

    # ---- Deck-Zugriff für QML ----

    @Property(QObject, constant=True)
    def deckA(self) -> DeckBridge:
        return self._deck_a

    @Property(QObject, constant=True)
    def deckB(self) -> DeckBridge:
        return self._deck_b

    # ---- Deck-Registry (Python-side, für Action-Registry / Keyboard / MIDI) ----

    def deckIds(self) -> list[str]:  # noqa: N802 — bewusst kein Slot, nur Python
        return ["a", "b"]

    def deckByIdInternal(self, deck_id: str) -> "DeckBridge":  # noqa: N802
        return self._deck_a if deck_id == "a" else self._deck_b

    # ---- Mixer ---------------------------------------------------

    @Slot(float)
    def setCrossfader(self, x: float) -> None:  # noqa: N802
        self._player.mixer.set_crossfader(x)

    @Slot(str)
    def setCrossfadeCurve(self, curve: str) -> None:  # noqa: N802
        try:
            self._player.mixer.set_curve(CrossfadeCurve(curve))
        except ValueError:
            pass

    @Slot(float)
    def setMasterGainDb(self, db: float) -> None:  # noqa: N802
        self._player.mixer.set_master_gain_db(db)

    # ---- Sync / Master ------------------------------------------

    @Slot(str)
    def setMaster(self, deck_id: str) -> None:  # noqa: N802
        self._player.sync.set_master_override(deck_id)
        self._deck_a.stateChanged.emit()
        self._deck_b.stateChanged.emit()

    @Slot()
    def unsyncAll(self) -> None:  # noqa: N802
        self._player.sync.unsync()
        self._deck_a.stateChanged.emit()
        self._deck_b.stateChanged.emit()

    # ---- Key-Notation ------------------------------------------

    @Slot(str)
    def setKeyNotation(self, notation: str) -> None:  # noqa: N802
        if notation in ("camelot", "openkey"):
            self._key_notation = notation
            self.keyNotationChanged.emit()

    @Slot()
    def toggleKeyNotation(self) -> None:  # noqa: N802
        self._key_notation = "openkey" if self._key_notation == "camelot" else "camelot"
        self.keyNotationChanged.emit()

    @Property(str, notify=keyNotationChanged)
    def keyNotation(self) -> str:
        return self._key_notation

    @Slot(str, result=str)
    def formatKey(self, camelot: str) -> str:  # noqa: N802
        return format_key(camelot, self._key_notation)

    @Slot(result=list)
    def keyRow(self) -> list:  # noqa: N802
        return all_keys(self._key_notation)

    @Slot(str, result=list)
    def compatibleKeys(self, camelot: str) -> list:  # noqa: N802
        keys = compatible_keys(camelot)
        if self._key_notation == "openkey":
            keys = [camelot_to_openkey(k) or k for k in keys]
        return keys

    # ---- Engine-Settings ----------------------------------------

    @Slot(result=list)
    def listDevices(self) -> list:  # noqa: N802
        devs = self._player.list_devices()
        return [
            {
                "index": d.index,
                "label": d.label,
                "hostapi": d.hostapi,
                "channels": d.max_output_channels,
                "samplerate": int(d.default_samplerate),
                "latencyLowMs": round(d.default_low_output_latency * 1000.0, 2),
            }
            for d in devs
        ]

    @Slot(int, int, int)
    def startEngine(self, device_index: int, samplerate: int, blocksize: int) -> None:  # noqa: N802
        try:
            self._player.start(device_index=device_index, samplerate=samplerate, blocksize=blocksize)
            self.engineChanged.emit()
        except Exception as exc:
            print(f"[Engine] Start failed: {exc}")

    @Slot()
    def stopEngine(self) -> None:  # noqa: N802
        self._player.stop()
        self.engineChanged.emit()

    @Property(bool, notify=engineChanged)
    def engineRunning(self) -> bool:
        return self._player.engine.is_running

    @Property(float, notify=engineChanged)
    def latencyMs(self) -> float:
        return self._player.engine.current_latency_ms

    @Property(int, notify=engineChanged)
    def currentSamplerate(self) -> int:
        return int(self._player.engine.config.samplerate)

    @Property(int, notify=engineChanged)
    def currentBlocksize(self) -> int:
        return int(self._player.engine.config.blocksize)

    @Property(str, notify=engineChanged)
    def currentDeviceLabel(self) -> str:
        cfg = self._player.engine.config
        if cfg.device_index is None:
            return "—"
        try:
            import sounddevice as sd
            d = sd.query_devices(cfg.device_index)
            ha = sd.query_hostapis(d["hostapi"])["name"]
            return f"[{ha}] {d['name']}"
        except Exception:
            return f"#{cfg.device_index}"
