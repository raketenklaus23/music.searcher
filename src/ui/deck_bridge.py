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
from ..core.beatgrid import Beatgrid, BeatgridMode, QuantizeGrid, Quantizer
from ..core.keys import (
    all_keys,
    camelot_to_openkey,
    compatible_keys,
    format_key,
    keyrow_chromatic,
)
from ..core.library import Library
from ..core.loudness import (
    DEFAULT_TARGET_LUFS,
    NormalizeMode,
    measure_lufs,
    normalize_destructive,
    normalize_playback_gain,
)
from ..core.stems import STEM_NAMES, StemModel, stem_paths_from_json

_DOUBLE_PRESS_WINDOW_S = 0.32   # innerhalb dieser Zeit gilt der 2. Klick als Double-Press


class DeckBridge(QObject):
    """Ein QML-nutzbares Deck. Nur Params, keine schwere Logik."""

    stateChanged = Signal()
    positionChanged = Signal()

    def __init__(self, player: Player, deck_id: str, library: Library,
                 quantizer: Optional[Quantizer] = None, parent=None):
        super().__init__(parent)
        self._player = player
        self._id = deck_id
        self._library = library
        self._deck = player.deck_a if deck_id == "a" else player.deck_b
        self._quantizer = quantizer or Quantizer(QuantizeGrid.QUARTER)

        # Dual-Press-Timing
        self._last_sync_press = 0.0
        self._last_key_press = 0.0

        # Poll-Timer für Position/Beat-Counter (30 fps reicht für UI)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def _current_beatgrid(self) -> Optional[Beatgrid]:
        tid = self._deck.state.track_id
        if tid is None:
            return None
        bg = self._library.get_beatgrid(tid)
        if bg is None:
            return None
        try:
            mode = BeatgridMode(bg.get("mode") or "beat_match")
        except ValueError:
            mode = BeatgridMode.BEAT_MATCH
        return Beatgrid(
            bpm=float(bg.get("bpm") or self._deck.state.bpm or 120.0),
            beats_sec=list(bg.get("beats_sec") or []),
            downbeat_ms=int(bg.get("downbeat_ms") or 0),
            mode=mode,
        )

    # ---- Slots aus QML: Track/Transport ------------------------------

    @Slot(int)
    def loadTrack(self, track_id: int) -> None:  # noqa: N802
        t = self._library.get_track(track_id)
        if t is None:
            return
        try:
            self._deck.load(Path(t.path), track_id=t.id, bpm=t.bpm, key=t.key)
            # Wenn für diesen Track bereits Stems separiert sind, direkt mitladen
            for row in self._library.get_stems_meta(t.id):
                paths = stem_paths_from_json(row["stem_paths_json"])
                if paths:
                    self._deck.load_stems(row["model"], paths)
                    break   # neueste zuerst
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

    # ---- Kill / Compressor / FX (delegiert an Mixer.strip_*) --------

    @Slot(float)
    def setKillLow(self, v: float) -> None:  # noqa: N802
        self._strip().set_kill_low(v)

    @Slot(float)
    def setKillMid(self, v: float) -> None:  # noqa: N802
        self._strip().set_kill_mid(v)

    @Slot(float)
    def setKillHigh(self, v: float) -> None:  # noqa: N802
        self._strip().set_kill_high(v)

    @Slot(float)
    def setCompressor(self, v: float) -> None:  # noqa: N802
        self._strip().set_compressor(v)

    @Slot(str)
    def setFxType(self, t: str) -> None:  # noqa: N802
        self._strip().set_fx_type(t)

    @Slot(float)
    def setFxWet(self, v: float) -> None:  # noqa: N802
        self._strip().set_fx_wet(v)

    @Slot(float)
    def setFxFilterDir(self, d: float) -> None:  # noqa: N802
        self._strip().set_fx_filter_dir(d)

    @Slot(float)
    def setChannelVolume(self, v: float) -> None:  # noqa: N802
        """Rotary-Volume 0..1.4."""
        self._strip().set_volume(v)

    def _strip(self):
        return self._player.mixer.strip_a if self._id == "a" else self._player.mixer.strip_b

    # ---- Cues (8 Slots) ---------------------------------------------

    @Slot(int)
    def jumpToCue(self, idx: int) -> None:  # noqa: N802
        tid = self._deck.state.track_id
        if tid is None:
            return
        for c in self._library.get_cues(tid):
            if c["idx"] == idx:
                self._deck.seek_seconds(c["position_ms"] / 1000.0)
                self.positionChanged.emit()
                return

    @Slot(int)
    def setCue(self, idx: int) -> None:  # noqa: N802
        """Setzt Cue idx auf aktuelle Playhead-Position (gequantisiert)."""
        tid = self._deck.state.track_id
        if tid is None:
            return
        pos_ms = int(self._deck.state.playhead_frames / self._deck.engine_sr * 1000)
        pos_ms = self._quantizer.snap_ms(pos_ms, self._current_beatgrid())
        self._library.upsert_cue(tid, idx=idx, position_ms=pos_ms, source="manual")
        self.stateChanged.emit()

    @Slot(int)
    def deleteCue(self, idx: int) -> None:  # noqa: N802
        tid = self._deck.state.track_id
        if tid is None:
            return
        self._library.delete_cue(tid, idx)
        self.stateChanged.emit()

    @Slot(result=list)
    def cues(self) -> list:  # noqa: N802
        tid = self._deck.state.track_id
        if tid is None:
            return []
        return self._library.get_cues(tid)

    # ---- Loops (8 Slots) --------------------------------------------

    @Slot(int)
    def triggerLoop(self, idx: int) -> None:  # noqa: N802
        """Aktiviert Loop-Slot idx (springt zum Start, aktiviert Loop)."""
        tid = self._deck.state.track_id
        if tid is None:
            return
        for l in self._library.get_loops(tid):
            if l["idx"] == idx:
                start_s = l["start_ms"] / 1000.0
                end_s = (l["start_ms"] + l["length_ms"]) / 1000.0
                self._deck.set_loop(start_s, end_s, active=True)
                self._deck.seek_seconds(start_s)
                self.stateChanged.emit()
                self.positionChanged.emit()
                return

    @Slot(int, int)
    def setLoopLengthBeats(self, idx: int, beats: int) -> None:  # noqa: N802
        """Ändert Länge von Loop idx auf 'beats' Beats (BPM-basiert)."""
        tid = self._deck.state.track_id
        if tid is None:
            return
        bg = self._current_beatgrid()
        length_ms = self._quantizer.loop_length_ms(beats, bg)
        for l in self._library.get_loops(tid):
            if l["idx"] == idx:
                self._library.upsert_loop(
                    tid, idx=idx, start_ms=l["start_ms"], length_ms=length_ms,
                    beats=beats, label=l.get("label"), source="manual",
                )
                # falls aktiver Loop → sofort übernehmen
                if self._deck.state.loop_active:
                    start_s = l["start_ms"] / 1000.0
                    self._deck.set_loop(start_s, start_s + length_ms / 1000.0, active=True)
                self.stateChanged.emit()
                return

    @Slot()
    def toggleLoop(self) -> None:  # noqa: N802
        st = self._deck.state
        if st.loop_active:
            self._deck.clear_loop()
        elif st.loop_end_s > st.loop_start_s:
            self._deck.set_loop(st.loop_start_s, st.loop_end_s, active=True)
        self.stateChanged.emit()

    @Slot()
    def clearLoop(self) -> None:  # noqa: N802
        self._deck.clear_loop()
        self.stateChanged.emit()

    @Slot(result=list)
    def loops(self) -> list:  # noqa: N802
        tid = self._deck.state.track_id
        if tid is None:
            return []
        return self._library.get_loops(tid)

    @Property(bool, notify=stateChanged)
    def loopActive(self) -> bool:
        return self._deck.state.loop_active

    # ---- LUFS-Normalize (pro Deck) ----------------------------------

    @Slot(str, float, result="QVariantMap")
    def normalizeLufs(self, mode: str, target: float = DEFAULT_TARGET_LUFS) -> dict:  # noqa: N802
        """mode: 'playback_gain' | 'destructive'. Gibt {ok, gain_db, error} zurück."""
        tid = self._deck.state.track_id
        if tid is None:
            return {"ok": False, "gain_db": 0.0, "error": "kein Track geladen"}
        t = self._library.get_track(tid)
        if t is None:
            return {"ok": False, "gain_db": 0.0, "error": "Track nicht in Library"}
        cur_lufs = t.lufs if t.lufs is not None else measure_lufs(Path(t.path))
        if cur_lufs is None:
            return {"ok": False, "gain_db": 0.0, "error": "LUFS-Messung fehlgeschlagen"}
        if mode == NormalizeMode.PLAYBACK_GAIN.value:
            gain = normalize_playback_gain(cur_lufs, target)
            self._library.set_playback_gain_db(tid, gain)
            self._deck.set_gain_db(gain)
            self.stateChanged.emit()
            return {"ok": True, "gain_db": gain, "error": None}
        if mode == NormalizeMode.DESTRUCTIVE.value:
            ok, applied, err = normalize_destructive(Path(t.path), target)
            if ok:
                # Neue LUFS = target, Playback-Gain zurücksetzen
                self._library.update_analysis(tid, lufs=target)
                self._library.set_playback_gain_db(tid, 0.0)
                self._deck.set_gain_db(0.0)
                self.stateChanged.emit()
            return {"ok": ok, "gain_db": applied, "error": err}
        return {"ok": False, "gain_db": 0.0, "error": f"unbekannter Modus: {mode}"}

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

    # ---- Stems (pro Deck, siehe StemPanel.qml) ---------------------

    @Slot(result=bool)
    def hasStems(self) -> bool:  # noqa: N802
        return bool(self._deck._stem_bufs)

    @Slot(result=bool)
    def stemMode(self) -> bool:  # noqa: N802
        return self._deck.state.stem_mode

    @Slot(bool)
    def setStemMode(self, on: bool) -> None:  # noqa: N802
        self._deck.set_stem_mode(on)
        self.stateChanged.emit()

    @Slot(result=list)
    def stemNames(self) -> list:  # noqa: N802
        return list(self._deck.state.stem_names)

    @Slot(str, float)
    def setStemVolume(self, name: str, v: float) -> None:  # noqa: N802
        self._deck.set_stem_volume(name, v)

    @Slot(str, bool)
    def setStemMuted(self, name: str, muted: bool) -> None:  # noqa: N802
        self._deck.set_stem_muted(name, muted)
        self.stateChanged.emit()

    @Slot(str, bool)
    def setStemSoloed(self, name: str, soloed: bool) -> None:  # noqa: N802
        self._deck.set_stem_soloed(name, soloed)
        self.stateChanged.emit()

    @Slot(str, result=float)
    def stemVolume(self, name: str) -> float:  # noqa: N802
        return float(self._deck._stem_volumes.get(name, 1.0))

    @Slot(str, result=bool)
    def stemMuted(self, name: str) -> bool:  # noqa: N802
        return bool(self._deck._stem_muted.get(name, False))

    @Slot(str, result=bool)
    def stemSoloed(self, name: str) -> bool:  # noqa: N802
        return bool(self._deck._stem_soloed.get(name, False))

    @Slot(str)
    def separateStems(self, model: str) -> None:  # noqa: N802
        """Startet Demucs-Separation für den aktuellen Track (nicht-blockierend)."""
        tid = self._deck.state.track_id
        if tid is None:
            return
        try:
            m = StemModel(model)
        except ValueError:
            return
        t = self._library.get_track(tid)
        if t is None:
            return
        # Runner-Referenz vom Parent (PlayerBridge → Backend)
        runner = getattr(self.parent(), "_stem_runner_ref", None)
        if runner is None:
            print("[Deck] Stem-Runner nicht verfügbar")
            return
        runner.enqueue(tid, Path(t.path), m)

    @Slot()
    def clearStems(self) -> None:  # noqa: N802
        self._deck.unload_stems()
        self.stateChanged.emit()

    def _on_tick(self) -> None:
        # Sync-Tick, damit Phase-Lock nachjustiert wird
        self._player.sync.tick()
        self.positionChanged.emit()


class PlayerBridge(QObject):
    """Übergreifende Player-Steuerung: Mixer, Sync, Engine-Settings, Key-Notation."""

    engineChanged = Signal()
    devicesChanged = Signal()
    keyNotationChanged = Signal()
    quantizerChanged = Signal()
    beatgridModeChanged = Signal()

    stemsChanged = Signal(int, str)          # track_id, model — Deck kann neu laden

    def __init__(self, player: Player, library: Library, parent=None):
        super().__init__(parent)
        self._player = player
        self._library = library
        # Persistierten Quantizer laden (Setting-Key: quantizer_grid)
        saved_q = library.get_setting("quantizer_grid", QuantizeGrid.QUARTER.value)
        try:
            initial_grid = QuantizeGrid(saved_q)
        except ValueError:
            initial_grid = QuantizeGrid.QUARTER
        self._quantizer = Quantizer(initial_grid)
        # Beatgrid-Mode (global default für neue Analysen)
        saved_bg = library.get_setting("beatgrid_mode", BeatgridMode.BEAT_MATCH.value)
        try:
            self._beatgrid_mode = BeatgridMode(saved_bg)
        except ValueError:
            self._beatgrid_mode = BeatgridMode.BEAT_MATCH
        # Decks bekommen Referenz auf den Quantizer
        self._deck_a = DeckBridge(player, "a", library, self._quantizer, self)
        self._deck_b = DeckBridge(player, "b", library, self._quantizer, self)
        self._key_notation = "camelot"   # oder "openkey"
        # Stem-Runner-Referenz — wird von AppBackend gesetzt
        self._stem_runner_ref = None

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

    @Slot(float)
    def setGlobalFilterResonance(self, v: float) -> None:  # noqa: N802
        self._player.mixer.set_global_filter_resonance(v)

    @Property(float, constant=False)
    def globalFilterResonance(self) -> float:
        return self._player.mixer.global_filter_resonance

    # ---- Quantizer + Beatgrid-Mode (global) ---------------------

    @Slot(str)
    def setQuantizer(self, grid: str) -> None:  # noqa: N802
        """grid: 'off' | 'downbeat' | '1/4' | '1/8' | '1/16'."""
        try:
            g = QuantizeGrid(grid)
        except ValueError:
            return
        self._quantizer.set_grid(g)
        self._library.set_setting("quantizer_grid", g.value)
        self.quantizerChanged.emit()

    @Property(str, notify=quantizerChanged)
    def quantizerGrid(self) -> str:
        return self._quantizer.grid.value

    @Slot(result=list)
    def quantizerOptions(self) -> list:  # noqa: N802
        return [g.value for g in QuantizeGrid]

    @Slot(str)
    def setBeatgridMode(self, mode: str) -> None:  # noqa: N802
        """mode: 'beat_match' | 'structure_boundaries'."""
        try:
            m = BeatgridMode(mode)
        except ValueError:
            return
        self._beatgrid_mode = m
        self._library.set_setting("beatgrid_mode", m.value)
        self.beatgridModeChanged.emit()

    @Property(str, notify=beatgridModeChanged)
    def beatgridMode(self) -> str:
        return self._beatgrid_mode.value

    @Slot(result=list)
    def beatgridModes(self) -> list:  # noqa: N802
        return [m.value for m in BeatgridMode]

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

    @Slot(result="QVariant")
    def keyRowChromatic(self) -> dict:  # noqa: N802
        """Zwei chromatische Reihen für die Key-Row: {'minor': [...], 'major': [...]}."""
        return keyrow_chromatic(self._key_notation)

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
