"""Set-Analyse — Fingerprint eines 60-min-Sets aus BPM/Key/Energy-Kurven.

Idee: DJ laedt eine Set-Recording (WAV/MP3) oder eine Playlist als Referenz.
Wir extrahieren pro 30s-Chunk (BPM, Key, Energy) und matchen dann Tracks aus
der Library, die in derselben Ecke wohnen. Ergebnis: neue Playlist, die dem
Vibe des Referenz-Sets folgt.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import soundfile as sf

from .analyzer import _detect_key
from .keys import parse_camelot
from .library import Library
from .suggester import vibe_vector


CHUNK_SEC = 30.0
HOP_SEC = 15.0


@dataclass
class SetChunk:
    t_start: float
    bpm: float
    key: Optional[str]
    energy: float


@dataclass
class SetFingerprint:
    duration_s: float
    chunks: list[SetChunk]

    @property
    def bpm_curve(self) -> list[float]:
        return [c.bpm for c in self.chunks]

    @property
    def energy_curve(self) -> list[float]:
        return [c.energy for c in self.chunks]

    def bpm_range(self) -> tuple[float, float, float]:
        arr = np.array(self.bpm_curve, dtype=np.float32)
        return float(arr.min()), float(np.median(arr)), float(arr.max())


def analyze_set_file(path: Path) -> SetFingerprint:
    """Analysiert eine Audio-Datei blockweise: 30s-Fenster, 15s-Hop."""
    path = Path(path)
    with sf.SoundFile(str(path)) as f:
        sr = f.samplerate
        total_samples = len(f)
    duration = total_samples / sr

    chunks: list[SetChunk] = []
    chunk_samples = int(CHUNK_SEC * sr)
    hop_samples = int(HOP_SEC * sr)
    t = 0.0
    idx = 0
    while idx + chunk_samples <= total_samples:
        y, _ = librosa.load(
            str(path), sr=sr, mono=True,
            offset=idx / sr, duration=CHUNK_SEC,
        )
        if len(y) < sr:
            break
        try:
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            bpm = float(np.asarray(tempo).flatten()[0])
        except Exception:
            bpm = 0.0
        try:
            camelot, _ = _detect_key(y, sr)
            key = camelot
        except Exception:
            key = None
        rms = float(np.sqrt(np.mean(y * y)))
        energy = float(min(1.0, max(0.0, rms * 4.0)))
        chunks.append(SetChunk(t_start=t, bpm=bpm, key=key, energy=energy))
        t += HOP_SEC
        idx += hop_samples
    return SetFingerprint(duration_s=duration, chunks=chunks)


def match_library_to_fingerprint(
    library: Library,
    fp: SetFingerprint,
    per_slot: int = 3,
) -> list[list[int]]:
    """Sucht fuer jedes Chunk-Fenster die besten Library-Kandidaten.

    Returns: Liste (pro Slot) mit je bis zu `per_slot` track_ids.
    """
    tracks = [t for t in library.all_tracks() if t.bpm and t.energy is not None]
    result: list[list[int]] = []
    for chunk in fp.chunks:
        v_ref = _chunk_vector(chunk)
        scored: list[tuple[float, int]] = []
        for t in tracks:
            v = vibe_vector(t)
            if v is None:
                continue
            sim = float(np.dot(v_ref, v) / (np.linalg.norm(v_ref) * np.linalg.norm(v) + 1e-9))
            scored.append((sim, t.id))
        scored.sort(reverse=True)
        result.append([tid for _, tid in scored[:per_slot]])
    return result


def _chunk_vector(chunk: SetChunk) -> np.ndarray:
    import math
    bpm_n = max(0.0, min(1.0, (chunk.bpm - 60.0) / 140.0))
    energy = max(0.0, min(1.0, chunk.energy))
    lufs_n = 0.5
    kx, ky, is_major = 0.0, 0.0, 0.0
    if chunk.key:
        p = parse_camelot(chunk.key)
        if p is not None:
            n, letter = p
            theta = 2.0 * math.pi * ((n - 1) / 12.0)
            kx = math.cos(theta)
            ky = math.sin(theta)
            is_major = 1.0 if letter == "B" else 0.0
    return np.array([bpm_n, energy, lufs_n, kx, ky, is_major], dtype=np.float32)


def build_playlist_from_fingerprint(
    library: Library,
    fp: SetFingerprint,
    slot_seconds: float = 240.0,
) -> list[int]:
    """Baut EINE Playlist aus dem Fingerprint (best match pro Slot, no dups)."""
    matches = match_library_to_fingerprint(library, fp, per_slot=5)
    used: set[int] = set()
    picks: list[int] = []
    for slot in matches:
        for tid in slot:
            if tid not in used:
                picks.append(tid)
                used.add(tid)
                break
    return picks
