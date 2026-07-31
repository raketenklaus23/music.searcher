"""Beatgrid-Analyse + Quantizer-Utility.

Zwei Downbeat-Modi:
  - beat_match:            erster Downbeat = Beat mit dominantem Bassdrum-Transienten
                           (Onset-Energie in 40-120 Hz-Band peakt)
  - structure_boundaries:  erster Downbeat = erste strukturelle Grenze
                           (librosa.segment.agglomerative)

Quantizer-Modi:
  - off        : keine Snap-Aktion
  - downbeat   : snappe zu Downbeat (Bar-Start)
  - 1/4        : snappe zu Beat (Viertel)
  - 1/8        : snappe zu Achtel-Position (Beat / 2)
  - 1/16       : snappe zu Sechzehntel-Position (Beat / 4)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

try:
    import librosa
    _HAS_LIBROSA = True
except Exception:
    _HAS_LIBROSA = False


class BeatgridMode(str, Enum):
    BEAT_MATCH = "beat_match"
    STRUCTURE_BOUNDARIES = "structure_boundaries"


class QuantizeGrid(str, Enum):
    OFF = "off"
    DOWNBEAT = "downbeat"
    QUARTER = "1/4"
    EIGHTH = "1/8"
    SIXTEENTH = "1/16"


@dataclass
class Beatgrid:
    bpm: float
    beats_sec: list[float]     # alle detektierten Beat-Positionen
    downbeat_ms: int           # erster Downbeat in ms
    mode: BeatgridMode

    def beats_per_bar(self, meter_num: int = 4) -> int:
        return meter_num


# -----------------------------------------------------------------------
# Beatgrid-Detektion
# -----------------------------------------------------------------------

def detect_beatgrid(
    y: np.ndarray,
    sr: int,
    mode: BeatgridMode = BeatgridMode.BEAT_MATCH,
    hint_bpm: Optional[float] = None,
) -> Beatgrid:
    """Erkennt Beats + Downbeat.

    y: mono float32
    sr: Sample-Rate
    hint_bpm: falls schon aus BPM-Analyse bekannt (schneller/robuster)
    """
    if not _HAS_LIBROSA:
        # Fallback: reines 120 BPM Raster
        bpm = float(hint_bpm or 120.0)
        beat_period = 60.0 / bpm
        duration = len(y) / sr
        beats = list(np.arange(0.0, duration, beat_period).astype(float))
        return Beatgrid(bpm=bpm, beats_sec=beats, downbeat_ms=0, mode=mode)

    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32, copy=False)

    if hint_bpm and hint_bpm > 0:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, start_bpm=float(hint_bpm), tightness=200)
    else:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, tightness=100)

    tempo = float(np.atleast_1d(tempo)[0])
    beats_sec = librosa.frames_to_time(beat_frames, sr=sr).astype(float).tolist()

    if not beats_sec:
        # Notfall-Raster
        beat_period = 60.0 / max(1.0, tempo)
        duration = len(y) / sr
        beats_sec = list(np.arange(0.0, duration, beat_period).astype(float))

    downbeat_ms = _find_downbeat(y, sr, beats_sec, mode)

    return Beatgrid(bpm=tempo, beats_sec=beats_sec, downbeat_ms=downbeat_ms, mode=mode)


def _find_downbeat(y: np.ndarray, sr: int, beats_sec: list[float], mode: BeatgridMode) -> int:
    """Bestimmt den ersten Downbeat je nach Modus.

    Ergibt Millisekunden ab Track-Start.
    """
    if not beats_sec:
        return 0

    # ---- Modus: beat_match  (Bassdrum-Transient) --------------------
    if mode == BeatgridMode.BEAT_MATCH:
        # Onset-Envelope aus Low-Band 40..140 Hz (Kick-Bereich).
        # Wir nehmen einfach die Original-Onset-Envelope aber gewichtet mit Bass-Energie.
        hop = 512
        onset_env = librosa.onset.onset_strength(
            y=y, sr=sr, hop_length=hop, fmax=200.0, aggregate=np.mean
        )
        # Zeit-Achse der Envelope
        env_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr, hop_length=hop)
        # Suche in ersten 8 Beats jenen mit höchstem Bass-Onset
        candidates = beats_sec[: min(8, len(beats_sec))]
        best_i, best_val = 0, -1.0
        for i, t in enumerate(candidates):
            j = int(np.argmin(np.abs(env_times - t)))
            v = float(onset_env[j])
            if v > best_val:
                best_val = v
                best_i = i
        return int(round(candidates[best_i] * 1000.0))

    # ---- Modus: structure_boundaries --------------------------------
    if mode == BeatgridMode.STRUCTURE_BOUNDARIES:
        try:
            # Chroma-basierte agglomerative Segmentierung, ersten Boundary-Peak
            hop = 1024
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
            k = min(6, max(2, chroma.shape[1] // 200))
            boundaries = librosa.segment.agglomerative(chroma, k=k)
            b_times = librosa.frames_to_time(boundaries, sr=sr, hop_length=hop)
            # Suche ersten Boundary jenseits 5s (Track-Start ist trivial)
            for t in b_times:
                if t > 5.0:
                    # Auf nächsten Beat snappen
                    nearest = min(beats_sec, key=lambda b: abs(b - t))
                    return int(round(nearest * 1000.0))
        except Exception:
            pass
        # Fallback: erster Beat
        return int(round(beats_sec[0] * 1000.0))

    return int(round(beats_sec[0] * 1000.0))


# -----------------------------------------------------------------------
# Quantizer
# -----------------------------------------------------------------------

class Quantizer:
    """Snapped Positionen (Cue-Setzen, Loop-Start) auf ein Beat-Raster.

    Positionen in Millisekunden, Beatgrid enthält Beats in Sekunden.
    """

    def __init__(self, grid: QuantizeGrid = QuantizeGrid.QUARTER, meter_num: int = 4):
        self.grid = grid
        self.meter_num = meter_num

    def set_grid(self, grid: QuantizeGrid) -> None:
        self.grid = grid

    def snap_ms(self, pos_ms: int, beatgrid: Optional[Beatgrid]) -> int:
        """Snappt pos_ms auf das aktuell eingestellte Raster."""
        if self.grid == QuantizeGrid.OFF or beatgrid is None or not beatgrid.beats_sec:
            return int(pos_ms)

        # Zeit-Positionen in Sekunden
        t = pos_ms / 1000.0
        beats = np.asarray(beatgrid.beats_sec, dtype=np.float64)

        if self.grid == QuantizeGrid.QUARTER:
            # nächstliegender Beat
            idx = int(np.argmin(np.abs(beats - t)))
            return int(round(beats[idx] * 1000.0))

        if self.grid == QuantizeGrid.DOWNBEAT:
            # Downbeat + meter_num Schritte
            downbeat_s = beatgrid.downbeat_ms / 1000.0
            # Index des Downbeats im Beat-Array
            db_idx = int(np.argmin(np.abs(beats - downbeat_s)))
            # sammle Bar-Starts (jeden meter_num-ten Beat ab db_idx)
            bar_starts = beats[db_idx :: max(1, self.meter_num)]
            if len(bar_starts) == 0:
                return int(round(beats[0] * 1000.0))
            idx = int(np.argmin(np.abs(bar_starts - t)))
            return int(round(bar_starts[idx] * 1000.0))

        if self.grid in (QuantizeGrid.EIGHTH, QuantizeGrid.SIXTEENTH):
            # Subteilung des Beat-Intervalls
            div = 2 if self.grid == QuantizeGrid.EIGHTH else 4
            # nächstliegendes Beat-Paar suchen
            idx = int(np.searchsorted(beats, t))
            if idx <= 0:
                return int(round(beats[0] * 1000.0))
            if idx >= len(beats):
                idx = len(beats) - 1
            b0, b1 = beats[idx - 1], beats[min(idx, len(beats) - 1)]
            if b1 <= b0:
                # letzter Beat + extrapolierter Step
                step = 60.0 / max(1.0, beatgrid.bpm) / div
                slots = np.arange(b0, b0 + step * div * 2, step)
            else:
                step = (b1 - b0) / div
                slots = np.arange(b0, b1 + 1e-9, step)
            best = min(slots, key=lambda s: abs(s - t))
            return int(round(best * 1000.0))

        return int(pos_ms)

    def loop_length_ms(self, beats: int, beatgrid: Optional[Beatgrid]) -> int:
        """Berechnet Loop-Länge in ms für 'beats' Beats.

        Bevorzugt aktuelle BPM aus beatgrid; sonst 120 BPM Fallback.
        """
        bpm = float(beatgrid.bpm) if beatgrid and beatgrid.bpm > 0 else 120.0
        beat_ms = 60000.0 / bpm
        return int(round(beat_ms * beats))
