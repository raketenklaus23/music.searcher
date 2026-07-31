"""Auto-Cues (8 Slots) + Auto-Loops (8 Slots).

Cue-Slot-Priorisierung (Matthias' Vorgabe, Interview 2026-07-31):
  0: Track-Start (erster nicht-stiller Frame, gequantized auf Downbeat)
  1: Erster Downbeat nach Intro
  2: Erster Drop           (grösste Energie-Steigerung)
  3: Zweiter Drop
  4: Break / Vocal-In      (erster Vocal-Region-Start nach Drop 1)
  5: Break / Vocal-Out     (erster Vocal-Region-End nach Vocal-In)
  6: Outro-Start           (grösste Energie-Absenkung im letzten Track-Drittel)
  7: Letzter mixbarer Punkt (Ende - 32 Beats)

Auto-Loops-Vorbelegung mit Standard-Längen (4, 8, 16 Bars) an Break-,
Instrumental- und Outro-Positionen. User kann Länge via UI umschalten
(/2, 4, 8, 16, 32 Bars).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .beatgrid import Beatgrid

try:
    import librosa
    _HAS_LIBROSA = True
except Exception:
    _HAS_LIBROSA = False


# -----------------------------------------------------------------------
# Datenklassen
# -----------------------------------------------------------------------

@dataclass
class CuePoint:
    idx: int
    position_ms: int
    label: str
    color: str
    loop_length_beats: Optional[int] = None  # nur belegt wenn Cue umschaltbarer Loop-Trigger ist


@dataclass
class LoopSlot:
    idx: int
    start_ms: int
    length_ms: int
    beats: int
    label: str


CUE_COLORS = [
    "#4ade80",   # 0 grün — Start
    "#00e0ff",   # 1 cyan — Intro-Ende
    "#ff2fbf",   # 2 pink — Drop 1
    "#ff2fbf",   # 3 pink — Drop 2
    "#ffb020",   # 4 amber — Vocal-In
    "#ffb020",   # 5 amber — Vocal-Out
    "#a855f7",   # 6 lila — Outro-Start
    "#ef4444",   # 7 rot — letzter Mix-Punkt
]


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------

def detect_auto_cues(
    y: np.ndarray,
    sr: int,
    beatgrid: Beatgrid,
    vocal_regions: Optional[list[tuple[int, int, float]]] = None,
) -> list[CuePoint]:
    """Erzeugt bis zu 8 Auto-Cues in fester Slot-Reihenfolge (siehe Modul-Docstring)."""
    if not _HAS_LIBROSA or y.size == 0:
        return []

    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32, copy=False)
    duration_ms = int(len(y) / sr * 1000)

    # RMS-Envelope
    hop = 512
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop).flatten()
    times_ms = (librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop) * 1000.0).astype(int)

    # ---- Slot 0: Track-Start (erster Frame mit RMS > 5% Median) ----
    start_ms = _first_nontrivial_frame_ms(rms, times_ms)

    # ---- Slot 1: erster Downbeat nach Intro ----
    intro_end_ms = _intro_end_ms(rms, times_ms, start_ms, beatgrid)

    # ---- Struktur-Boundaries + Energie-Deltas ----
    boundaries_ms = _structure_boundaries_ms(y, sr, hop)
    drops, dips = _classify_boundaries(boundaries_ms, rms, times_ms)

    # ---- Slot 2/3: die zwei grössten Drops ----
    drop_1_ms = drops[0] if len(drops) >= 1 else None
    drop_2_ms = drops[1] if len(drops) >= 2 else None

    # ---- Slot 4/5: Vocal-In/Out ----
    vocal_in_ms, vocal_out_ms = _vocal_in_out(vocal_regions or [], drop_1_ms or start_ms)

    # ---- Slot 6: Outro-Start (grösster Dip im letzten Drittel) ----
    outro_ms = _outro_start_ms(dips, duration_ms)

    # ---- Slot 7: letzter mixbarer Punkt (Ende - 32 Beats) ----
    last_mix_ms = _last_mix_point_ms(duration_ms, beatgrid)

    raw_positions = [
        start_ms,       # 0
        intro_end_ms,   # 1
        drop_1_ms,      # 2
        drop_2_ms,      # 3
        vocal_in_ms,    # 4
        vocal_out_ms,   # 5
        outro_ms,       # 6
        last_mix_ms,    # 7
    ]
    labels = [
        "START", "INTRO END", "DROP 1", "DROP 2",
        "VOCAL IN", "VOCAL OUT", "OUTRO", "LAST MIX",
    ]

    cues: list[CuePoint] = []
    for idx, (pos, label) in enumerate(zip(raw_positions, labels)):
        if pos is None or pos < 0 or pos >= duration_ms:
            continue
        # Snap auf nächsten Beat (Cue-Points sollten immer beat-aligned sein)
        pos_snapped = _snap_to_nearest_beat_ms(pos, beatgrid)
        cues.append(CuePoint(idx=idx, position_ms=pos_snapped, label=label, color=CUE_COLORS[idx]))
    return cues


def detect_auto_loops(
    y: np.ndarray,
    sr: int,
    beatgrid: Beatgrid,
    vocal_regions: Optional[list[tuple[int, int, float]]] = None,
) -> list[LoopSlot]:
    """Erzeugt bis zu 8 Auto-Loops an strukturell sinnvollen Stellen.

    Standard-Verteilung:
      0-1: 4-Bar-Loops am Break (leise Passagen)
      2-3: 8-Bar-Loops an Instrumental-Passagen (kein Vocal)
      4-5: 16-Bar-Loops an Chorus/Drop
      6:   32-Bar-Loop im ersten Track-Drittel (Intro)
      7:   /2-Bar-Loop kurz vor dem letzten Mix-Punkt (Fill)
    """
    if not _HAS_LIBROSA or y.size == 0:
        return []

    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32, copy=False)
    duration_ms = int(len(y) / sr * 1000)

    hop = 512
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop).flatten()
    times_ms = (librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop) * 1000.0).astype(int)

    boundaries_ms = _structure_boundaries_ms(y, sr, hop)
    drops, dips = _classify_boundaries(boundaries_ms, rms, times_ms)

    # Beat-Länge und Bar-Länge in ms
    beat_ms = 60000.0 / max(1.0, beatgrid.bpm)
    bar_ms = beat_ms * 4.0

    def bars(n: int) -> int:
        return int(round(bar_ms * n))

    loops: list[LoopSlot] = []
    used = set()

    def add(idx: int, start_ms: int, n_bars: float, label: str) -> None:
        if start_ms is None or start_ms in used:
            return
        length = int(round(bar_ms * n_bars))
        beats = int(round(n_bars * 4))
        if start_ms + length >= duration_ms:
            return
        start_snapped = _snap_to_nearest_beat_ms(start_ms, beatgrid)
        loops.append(LoopSlot(idx=idx, start_ms=start_snapped, length_ms=length, beats=beats, label=label))
        used.add(start_ms)

    # Slot 0-1: 4-Bar-Loops an Break-Dips
    for slot, ms in enumerate(dips[:2]):
        add(slot, ms, 4.0, f"BREAK 4B #{slot + 1}")

    # Slot 2-3: 8-Bar-Loops an Instrumental (Boundaries ohne Vocal-Overlap)
    instrum = _instrumental_boundaries_ms(boundaries_ms, vocal_regions or [])
    for i, ms in enumerate(instrum[:2]):
        add(2 + i, ms, 8.0, f"INSTR 8B #{i + 1}")

    # Slot 4-5: 16-Bar-Loops an Drops
    for i, ms in enumerate(drops[:2]):
        add(4 + i, ms, 16.0, f"DROP 16B #{i + 1}")

    # Slot 6: 32-Bar Intro-Loop (an Track-Start + 4 Bars gesnapped)
    intro_start = bars(4)
    if intro_start < duration_ms - bars(32):
        add(6, intro_start, 32.0, "INTRO 32B")

    # Slot 7: /2-Bar Fill vor Last-Mix
    last_mix = _last_mix_point_ms(duration_ms, beatgrid)
    if last_mix and last_mix - bars(1) > 0:
        add(7, last_mix - bars(1), 0.5, "FILL 1/2B")

    return loops


# -----------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------

def _first_nontrivial_frame_ms(rms: np.ndarray, times_ms: np.ndarray) -> int:
    if rms.size == 0:
        return 0
    thresh = 0.05 * float(np.median(rms))
    for i, v in enumerate(rms):
        if v > thresh:
            return int(times_ms[i])
    return 0


def _intro_end_ms(rms: np.ndarray, times_ms: np.ndarray, start_ms: int, beatgrid: Beatgrid) -> int:
    """Erster Downbeat >= 8 Bars nach Track-Start (falls Track lang genug)."""
    beat_ms = 60000.0 / max(1.0, beatgrid.bpm)
    target_ms = start_ms + int(round(beat_ms * 4 * 8))    # 8 Bars nach Start
    # Snappe auf Downbeat: nutze Downbeat als Anker
    return _snap_to_nearest_downbeat_ms(target_ms, beatgrid)


def _structure_boundaries_ms(y: np.ndarray, sr: int, hop: int) -> list[int]:
    """Grob-Struktur via Chroma-Agglomerativ."""
    try:
        hop_s = 1024
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_s)
        k = min(8, max(3, chroma.shape[1] // 200))
        boundaries = librosa.segment.agglomerative(chroma, k=k)
        b_ms = (librosa.frames_to_time(boundaries, sr=sr, hop_length=hop_s) * 1000.0).astype(int)
        return [int(x) for x in b_ms if x > 500]
    except Exception:
        return []


def _classify_boundaries(
    boundaries_ms: list[int],
    rms: np.ndarray,
    times_ms: np.ndarray,
) -> tuple[list[int], list[int]]:
    """Sortiert Boundaries in Drops (Energie steigt) und Dips (fällt)."""
    if not boundaries_ms or rms.size == 0:
        return [], []
    drops: list[tuple[int, float]] = []
    dips: list[tuple[int, float]] = []
    win_ms = 3000
    for b in boundaries_ms:
        # Fenster vor und nach der Grenze
        before_mask = (times_ms >= b - win_ms) & (times_ms < b)
        after_mask = (times_ms >= b) & (times_ms < b + win_ms)
        if not np.any(before_mask) or not np.any(after_mask):
            continue
        e_before = float(np.mean(rms[before_mask]))
        e_after = float(np.mean(rms[after_mask]))
        delta = e_after - e_before
        if delta > 0:
            drops.append((b, delta))
        else:
            dips.append((b, -delta))
    drops.sort(key=lambda x: -x[1])
    dips.sort(key=lambda x: -x[1])
    return [b for b, _ in drops], [b for b, _ in dips]


def _vocal_in_out(
    vocal_regions: list[tuple[int, int, float]],
    after_ms: int,
) -> tuple[Optional[int], Optional[int]]:
    for start, end, _conf in vocal_regions:
        if start >= after_ms:
            return start, end
    return None, None


def _outro_start_ms(dips: list[int], duration_ms: int) -> Optional[int]:
    if not dips:
        return None
    last_third_start = int(duration_ms * 2 / 3)
    candidates = [d for d in dips if d >= last_third_start]
    return candidates[0] if candidates else dips[-1]


def _last_mix_point_ms(duration_ms: int, beatgrid: Beatgrid) -> int:
    beat_ms = 60000.0 / max(1.0, beatgrid.bpm)
    return max(0, duration_ms - int(round(beat_ms * 32)))


def _snap_to_nearest_beat_ms(pos_ms: int, beatgrid: Beatgrid) -> int:
    if not beatgrid.beats_sec:
        return pos_ms
    beats = np.asarray(beatgrid.beats_sec, dtype=np.float64) * 1000.0
    idx = int(np.argmin(np.abs(beats - pos_ms)))
    return int(round(beats[idx]))


def _snap_to_nearest_downbeat_ms(pos_ms: int, beatgrid: Beatgrid, meter: int = 4) -> int:
    if not beatgrid.beats_sec:
        return pos_ms
    beats = np.asarray(beatgrid.beats_sec, dtype=np.float64) * 1000.0
    downbeat_ms = beatgrid.downbeat_ms or int(round(beats[0]))
    # Index des Downbeats im Beat-Array
    db_idx = int(np.argmin(np.abs(beats - downbeat_ms)))
    bar_starts = beats[db_idx :: meter]
    if len(bar_starts) == 0:
        return int(round(beats[0]))
    idx = int(np.argmin(np.abs(bar_starts - pos_ms)))
    return int(round(bar_starts[idx]))


def _instrumental_boundaries_ms(
    boundaries_ms: list[int],
    vocal_regions: list[tuple[int, int, float]],
) -> list[int]:
    """Boundaries an denen keine Vocal-Region aktiv ist."""
    def has_vocal(ms: int) -> bool:
        return any(s <= ms <= e for s, e, _ in vocal_regions)
    return [b for b in boundaries_ms if not has_vocal(b)]
