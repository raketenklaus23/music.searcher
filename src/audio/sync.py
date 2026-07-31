"""Sync-Logik zwischen 2 Decks — dual-press SYNC/KEY, Master-Handoff, Phrase-Alignment.

Design (siehe memory/sync_and_key_design.md):
  * SYNC 1x = einmaliges BPM-Angleichen, keine kontinuierliche Nachführung
  * SYNC 2x = BeatSync aktiv (kontinuierlich): hält BPM, alignet auf nächsten
    Master-Downbeat auf kürzestem Weg, versucht 16-Bar-Phrase-Schema
  * KEY 1x = KeyLock (Deck-Attribut, im Deck selbst gesetzt)
  * KEY 2x = Key-Match: Slave-Pitch so verschieben dass Tonart Master matcht

Phase-Alignment ohne Beatgrid ist nur ungefähr (basierend auf bpm+playhead).
Sobald Phase 3 Beatgrid liefert, hier nachschärfen.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from ..core.keys import key_distance_semitones
from .deck import Deck


class SyncMode(str, Enum):
    OFF = "off"
    BPM_ONESHOT = "bpm_oneshot"     # 1x SYNC — BPM angleichen, dann Freilauf
    BPM_LOCKED = "bpm_locked"       # 2x SYNC — kontinuierlich mit Phrase-Alignment


class KeyMode(str, Enum):
    OFF = "off"
    LOCK = "lock"                    # 1x KEY — KeyLock (Pitch bleibt bei Tempo-Change)
    MATCH = "match"                  # 2x KEY — Slave.pitch = Master.key kompensiert


class SnapMode(str, Enum):
    HARD = "hard"     # sofort auf Master-Downbeat springen
    SOFT = "soft"     # in 2-4 Beats einnudgen


@dataclass
class SyncStatus:
    master: Optional[str] = None
    slave: Optional[str] = None
    mode: SyncMode = SyncMode.OFF
    snap: SnapMode = SnapMode.HARD
    key_mode: KeyMode = KeyMode.OFF
    phase_error_ms: float = 0.0        # aktuelle Phasen-Abweichung Slave↔Master
    bar_master: int = 0
    beat_master: int = 0
    bar_slave: int = 0
    beat_slave: int = 0
    phrase_offset: int = 0             # 0..15 (aktueller Beat im 16-Bar-Phrase-Schema)


class SyncController:
    def __init__(self, deck_a: Deck, deck_b: Deck):
        self.deck_a = deck_a
        self.deck_b = deck_b
        self._master_override: Optional[str] = None    # None → Auto
        self._auto_master: Optional[str] = None
        self._first_started: Optional[str] = None
        self._status = SyncStatus()

    # ---- Master-Verwaltung -------------------------------------------

    def set_master_override(self, deck_id: Optional[str]) -> None:
        if deck_id in (None, "a", "b"):
            self._master_override = deck_id
            self._recompute_master()

    def notify_deck_started(self, deck_id: str) -> None:
        """Deck ruft das auf wenn Play gedrückt wird — für Auto-Master."""
        if self._first_started is None:
            self._first_started = deck_id
        self._recompute_master()

    def notify_deck_stopped(self, deck_id: str) -> None:
        if self._first_started == deck_id:
            # zurücksetzen auf das gerade laufende
            if self.deck_a.state.playing and not self.deck_b.state.playing:
                self._first_started = "a"
            elif self.deck_b.state.playing and not self.deck_a.state.playing:
                self._first_started = "b"
            else:
                self._first_started = None
        # Master-Handoff: wenn aktueller Master stoppt UND Sync aktiv war,
        # wandert Master-Status auf Slave (siehe User-Vorgabe)
        if self._status.mode != SyncMode.OFF and self._effective_master() == deck_id:
            other = "b" if deck_id == "a" else "a"
            other_deck = self.deck_a if other == "a" else self.deck_b
            if other_deck.state.playing:
                self._master_override = other
                self._status.mode = SyncMode.OFF   # neuer Master läuft frei
        self._recompute_master()

    def _effective_master(self) -> Optional[str]:
        return self._master_override or self._auto_master

    def _recompute_master(self) -> None:
        if self._master_override is not None:
            self._auto_master = self._master_override
            return
        # Auto
        a_play = self.deck_a.state.playing
        b_play = self.deck_b.state.playing
        if a_play and not b_play:
            self._auto_master = "a"
        elif b_play and not a_play:
            self._auto_master = "b"
        elif a_play and b_play:
            self._auto_master = self._first_started or "a"
        else:
            self._auto_master = None

    def _pair(self) -> Optional[tuple[Deck, Deck, str, str]]:
        m = self._effective_master()
        if m is None:
            # fallback: A ist Default-Master wenn nichts läuft
            m = "a"
        s = "b" if m == "a" else "a"
        return (
            self.deck_a if m == "a" else self.deck_b,
            self.deck_b if m == "a" else self.deck_a,
            m, s,
        )

    # ---- BPM-Sync ----------------------------------------------------

    def bpm_oneshot(self, slave_deck_id: str) -> None:
        """1x SYNC gedrückt — passe Slave-BPM einmalig an Master an, kein Locking."""
        self._align_bpm(slave_deck_id)
        self._status.mode = SyncMode.BPM_ONESHOT

    def bpm_lock(self, slave_deck_id: str, snap: SnapMode = SnapMode.HARD) -> None:
        """2x SYNC — kontinuierlicher Sync mit Downbeat-Alignment."""
        self._align_bpm(slave_deck_id)
        self._status.mode = SyncMode.BPM_LOCKED
        self._status.snap = snap
        self._align_phase(slave_deck_id, snap)

    def unsync(self, slave_deck_id: Optional[str] = None) -> None:
        self._status.mode = SyncMode.OFF
        if slave_deck_id is None:
            self.deck_a.set_tempo_ratio(1.0)
            self.deck_b.set_tempo_ratio(1.0)
        else:
            (self.deck_a if slave_deck_id == "a" else self.deck_b).set_tempo_ratio(1.0)

    def _align_bpm(self, slave_deck_id: str) -> None:
        pair = self._pair()
        if pair is None:
            return
        master, slave, m_id, s_id = pair
        # slave_deck_id sollte das aktuelle Slave sein — falls User Sync auf Master drückt,
        # ist der andere der Master
        if slave_deck_id == m_id:
            master, slave = slave, master
            m_id, s_id = s_id, m_id
            # Master-Override umsetzen, damit die Rollen konsistent bleiben
            self._master_override = m_id

        if not master.is_loaded() or not slave.is_loaded():
            return
        m_bpm = master.state.bpm
        s_bpm = slave.state.bpm
        if not m_bpm or not s_bpm:
            return

        # Wähle Verhältnis das am nächsten an 1 liegt (schonendster Stretch)
        candidates = [m_bpm / s_bpm, m_bpm / (s_bpm * 2), m_bpm / (s_bpm / 2)]
        candidates = [r for r in candidates if 0.5 <= r <= 2.0]
        if not candidates:
            return
        best = min(candidates, key=lambda r: abs(math.log(r)))
        slave.set_tempo_ratio(best)

    def _align_phase(self, slave_deck_id: str, snap: SnapMode) -> None:
        """Bringe Slave-Playhead auf nächsten Master-Downbeat (nächstgelegen)."""
        pair = self._pair()
        if pair is None:
            return
        master, slave, m_id, s_id = pair
        if not master.is_loaded() or not slave.is_loaded():
            return
        m_bpm = master.state.bpm
        s_bpm_eff = (slave.state.bpm or 0) * slave.state.tempo_ratio
        if not m_bpm or not s_bpm_eff:
            return

        beat_len_m = 60.0 / m_bpm
        # Master-Beat-Phase (0..1)
        m_pos = master.state.playhead_frames / master.engine_sr
        m_phase = (m_pos / beat_len_m) % 1.0
        # Slave-Beat-Phase (auf gleiches Beat-Grid mit m_bpm)
        s_pos = slave.state.playhead_frames / slave.engine_sr
        s_phase = (s_pos / beat_len_m) % 1.0

        # Delta so wählen dass wir kürzesten Weg gehen (±0.5 Beat)
        delta = m_phase - s_phase
        if delta > 0.5:
            delta -= 1.0
        elif delta < -0.5:
            delta += 1.0

        if snap == SnapMode.HARD:
            new_pos = s_pos + delta * beat_len_m
            new_pos = max(0.0, min(new_pos, slave.state.duration_s - 0.01))
            slave.seek_seconds(new_pos)
        else:
            # Soft-Slide: kurzer Tempo-Puls über 4 Beats
            # (MVP: hier nur Marker setzen; echter Puls kommt in Phase 3)
            _n_beats_glide = 4
            # TODO Phase 3: kontinuierliches Nudging über beat-loop
            new_pos = s_pos + delta * beat_len_m
            slave.seek_seconds(max(0.0, min(new_pos, slave.state.duration_s - 0.01)))

    def tick(self) -> None:
        """Vom UI-Timer regelmäßig aufgerufen: berechnet Phase-Error, hält Sync-Lock."""
        if self._status.mode != SyncMode.BPM_LOCKED:
            self._update_status_metrics()
            return
        pair = self._pair()
        if pair is None:
            return
        master, slave, m_id, s_id = pair
        if not master.state.playing or not slave.state.playing:
            self._update_status_metrics()
            return
        m_bpm = master.state.bpm
        if not m_bpm:
            return
        beat_len_m = 60.0 / m_bpm
        m_pos = master.state.playhead_frames / master.engine_sr
        s_pos = slave.state.playhead_frames / slave.engine_sr
        m_phase = (m_pos / beat_len_m) % 1.0
        s_phase = (s_pos / beat_len_m) % 1.0
        err = m_phase - s_phase
        if err > 0.5:
            err -= 1.0
        elif err < -0.5:
            err += 1.0
        self._status.phase_error_ms = err * beat_len_m * 1000.0

        # Toleranz 2 ms → drift; > 15 ms → sanft resnappen
        if abs(self._status.phase_error_ms) > 15.0:
            slave.seek_seconds(s_pos + err * beat_len_m)

        self._update_status_metrics()

    def _update_status_metrics(self) -> None:
        m = self._effective_master()
        s = "b" if m == "a" else "a"
        self._status.master = m
        self._status.slave = s
        for did in ("a", "b"):
            deck = self.deck_a if did == "a" else self.deck_b
            if deck.state.bpm and deck.state.duration_s > 0:
                pos = deck.state.playhead_frames / deck.engine_sr
                beat_len = 60.0 / deck.state.bpm
                total_beats = int(pos / beat_len)
                bar = total_beats // 4 + 1
                beat = (total_beats % 4) + 1
                if did == "a" and m == "a":
                    self._status.bar_master = bar
                    self._status.beat_master = beat
                    self._status.phrase_offset = total_beats % 16
                elif did == "b" and m == "b":
                    self._status.bar_master = bar
                    self._status.beat_master = beat
                    self._status.phrase_offset = total_beats % 16
                if did == s:
                    self._status.bar_slave = bar
                    self._status.beat_slave = beat

    # ---- Key-Match ---------------------------------------------------

    def key_lock(self, deck_id: str) -> None:
        """1x KEY — KeyLock im Deck aktivieren."""
        deck = self.deck_a if deck_id == "a" else self.deck_b
        deck.set_key_lock(True)
        self._status.key_mode = KeyMode.LOCK

    def key_match(self, slave_deck_id: str) -> None:
        """2x KEY — Slave-Pitch so verschieben dass Slave-Key = Master-Key."""
        pair = self._pair()
        if pair is None:
            return
        master, slave, m_id, s_id = pair
        if slave_deck_id == m_id:
            master, slave = slave, master
        if not master.state.key or not slave.state.key:
            return
        semis = key_distance_semitones(slave.state.key, master.state.key)
        if semis is None:
            return
        slave.set_key_lock(True)
        slave.set_pitch_semitones(float(semis))
        self._status.key_mode = KeyMode.MATCH

    def key_reset(self, deck_id: str) -> None:
        deck = self.deck_a if deck_id == "a" else self.deck_b
        deck.set_pitch_semitones(0.0)
        deck.set_key_lock(False)
        self._status.key_mode = KeyMode.OFF

    # ---- Beat-Position (nur für Beat-Counter, ohne echtes Beatgrid) --

    def beat_position(self, deck_id: str) -> Optional[tuple[int, int, int]]:
        """Liefert (bar, beat_in_bar 1..4, phrase_beat 1..16) — MVP nur bpm-basiert."""
        deck = self.deck_a if deck_id == "a" else self.deck_b
        if not deck.is_loaded() or not deck.state.bpm:
            return None
        pos_s = deck.state.playhead_frames / deck.engine_sr
        beats_per_s = deck.state.bpm / 60.0
        total_beats = int(pos_s * beats_per_s)
        beat_in_bar = (total_beats % 4) + 1
        bar = total_beats // 4 + 1
        phrase_beat = (total_beats % 16) + 1
        return bar, beat_in_bar, phrase_beat

    @property
    def status(self) -> SyncStatus:
        return self._status

    @property
    def master(self) -> Optional[str]:
        return self._effective_master()
