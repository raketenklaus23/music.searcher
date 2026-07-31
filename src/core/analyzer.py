"""Audio-Analyse: BPM, Tonart (Camelot), LUFS, Energy — offline via librosa + pyloudnorm.

Die Key-Detection nutzt Krumhansl-Schmuckler auf Chroma-Features (kein essentia,
weil essentia unter Windows tricky ist). Camelot-Notation (z.B. 8A / 5B) für
Kompatibilität mit typischen DJ-Workflows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .beatgrid import Beatgrid, BeatgridMode, detect_beatgrid
from .cues import CuePoint, LoopSlot, detect_auto_cues, detect_auto_loops
from .vocals import detect_vocal_regions


@dataclass
class AnalysisResult:
    bpm: Optional[float]
    key: Optional[str]         # Camelot z.B. "8A"
    key_name: Optional[str]    # z.B. "A minor"
    lufs: Optional[float]
    energy: Optional[float]    # 0..1
    duration_s: Optional[float]
    beats: Optional[np.ndarray]  # in Sekunden
    beatgrid: Optional[Beatgrid] = None
    vocal_regions: list[tuple[int, int, float]] = field(default_factory=list)
    cues: list[CuePoint] = field(default_factory=list)
    loops: list[LoopSlot] = field(default_factory=list)


# ---- Krumhansl-Schmuckler Profile (aus Musikpsychologie-Literatur) ----------
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)

_PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Camelot-Wheel Mapping: (mode, key_index) -> "8A" etc.
# A = minor, B = major
_CAMELOT = {
    ("major", 0): "8B",   # C
    ("major", 1): "3B",   # C#/Db
    ("major", 2): "10B",  # D
    ("major", 3): "5B",   # D#/Eb
    ("major", 4): "12B",  # E
    ("major", 5): "7B",   # F
    ("major", 6): "2B",   # F#/Gb
    ("major", 7): "9B",   # G
    ("major", 8): "4B",   # G#/Ab
    ("major", 9): "11B",  # A
    ("major", 10): "6B",  # A#/Bb
    ("major", 11): "1B",  # B
    ("minor", 0): "5A",   # C
    ("minor", 1): "12A",  # C#/Db
    ("minor", 2): "7A",   # D
    ("minor", 3): "2A",   # D#/Eb
    ("minor", 4): "9A",   # E
    ("minor", 5): "4A",   # F
    ("minor", 6): "11A",  # F#/Gb
    ("minor", 7): "6A",   # G
    ("minor", 8): "1A",   # G#/Ab
    ("minor", 9): "8A",   # A
    ("minor", 10): "3A",  # A#/Bb
    ("minor", 11): "10A", # B
}


def analyze(
    path: Path,
    sr: int = 22050,
    beatgrid_mode: BeatgridMode = BeatgridMode.BEAT_MATCH,
) -> AnalysisResult:
    """Führt komplette Phase-3-Analyse einer Audiodatei durch:
    BPM → Key → LUFS → Beatgrid → Vocals → Auto-Cues → Auto-Loops.
    """
    import librosa
    import pyloudnorm as pyln
    import soundfile as sf

    y, orig_sr = librosa.load(str(path), sr=sr, mono=True)
    duration = float(len(y) / sr)

    # BPM + Beats
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    bpm = float(tempo) if tempo else None
    if bpm and (bpm < 70 or bpm > 200):
        while bpm < 70:
            bpm *= 2
        while bpm > 200:
            bpm /= 2

    # Key via Chroma + Krumhansl-Schmuckler
    key_camelot, key_name = _detect_key(y, sr)

    # LUFS (integrated)
    lufs: Optional[float] = None
    try:
        y_full, sr_full = sf.read(str(path), always_2d=False)
        meter = pyln.Meter(sr_full)
        lufs = float(meter.integrated_loudness(y_full))
        if not np.isfinite(lufs):
            lufs = None
    except Exception:
        lufs = None

    # Energy (RMS 0..1, grob)
    rms = float(np.sqrt(np.mean(y ** 2)))
    energy = float(np.clip(rms * 5.0, 0.0, 1.0))

    # Beatgrid (BPM als Hint — schneller/robuster)
    beatgrid = detect_beatgrid(y, sr, mode=beatgrid_mode, hint_bpm=bpm)

    # Vocal-Regionen (heuristisch)
    vocal_regions = detect_vocal_regions(y, sr)

    # Auto-Cues + Auto-Loops
    cues = detect_auto_cues(y, sr, beatgrid, vocal_regions)
    loops = detect_auto_loops(y, sr, beatgrid, vocal_regions)

    return AnalysisResult(
        bpm=bpm,
        key=key_camelot,
        key_name=key_name,
        lufs=lufs,
        energy=energy,
        duration_s=duration,
        beats=beats,
        beatgrid=beatgrid,
        vocal_regions=vocal_regions,
        cues=cues,
        loops=loops,
    )


def _detect_key(y: np.ndarray, sr: int) -> tuple[Optional[str], Optional[str]]:
    import librosa

    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=2048)
        mean_chroma = chroma.mean(axis=1)
        if mean_chroma.sum() == 0:
            return None, None

        best_score = -np.inf
        best_key = 0
        best_mode = "major"
        for i in range(12):
            rot = np.roll(mean_chroma, -i)
            maj_score = float(np.corrcoef(rot, _MAJOR_PROFILE)[0, 1])
            min_score = float(np.corrcoef(rot, _MINOR_PROFILE)[0, 1])
            if maj_score > best_score:
                best_score = maj_score
                best_key = i
                best_mode = "major"
            if min_score > best_score:
                best_score = min_score
                best_key = i
                best_mode = "minor"

        camelot = _CAMELOT[(best_mode, best_key)]
        key_name = f"{_PITCH_NAMES[best_key]} {'major' if best_mode == 'major' else 'minor'}"
        return camelot, key_name
    except Exception:
        return None, None
