"""LUFS-Normalisierung — Ziel -14 LUFS.

Zwei Modi:
  - "playback_gain": nicht-destruktiv, speichert Gain-Offset in tracks.playback_gain_db
                    (Deck wendet Gain live an, Original bleibt unangetastet)
  - "destructive":   schreibt Datei neu (Ziel-LUFS wird tatsächlich eingebrannt),
                    Backup unter <file>.original.<ext> falls überschreiben

Die Wahl trifft der User per Dialog vor jedem Trigger (User-Vorgabe 2026-07-31).
"""
from __future__ import annotations

import shutil
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np


DEFAULT_TARGET_LUFS = -14.0
MAX_GAIN_DB = 12.0        # Sicherheitsdeckel gegen Clipping/Rauschen
MIN_GAIN_DB = -24.0


class NormalizeMode(str, Enum):
    PLAYBACK_GAIN = "playback_gain"
    DESTRUCTIVE = "destructive"


def measure_lufs(path: Path) -> Optional[float]:
    """Integrated LUFS nach EBU R128."""
    try:
        import pyloudnorm as pyln
        import soundfile as sf

        y, sr = sf.read(str(path), always_2d=False)
        meter = pyln.Meter(sr)
        lufs = float(meter.integrated_loudness(y))
        return lufs if np.isfinite(lufs) else None
    except Exception:
        return None


def compute_gain_db(current_lufs: float, target_lufs: float = DEFAULT_TARGET_LUFS) -> float:
    """Wie viel dB muss angehoben/abgesenkt werden um target_lufs zu treffen."""
    gain = float(target_lufs - current_lufs)
    return float(np.clip(gain, MIN_GAIN_DB, MAX_GAIN_DB))


def normalize_playback_gain(
    current_lufs: Optional[float],
    target_lufs: float = DEFAULT_TARGET_LUFS,
) -> float:
    """Ermittelt Gain-dB für nicht-destruktive Normalisierung (Deck-Playback-Offset)."""
    if current_lufs is None or not np.isfinite(current_lufs):
        return 0.0
    return compute_gain_db(current_lufs, target_lufs)


def normalize_destructive(
    path: Path,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    backup: bool = True,
) -> tuple[bool, float, Optional[str]]:
    """Schreibt path so um dass integrated LUFS ≈ target_lufs.

    Returns: (success, applied_gain_db, error_message)
    """
    try:
        import pyloudnorm as pyln
        import soundfile as sf

        y, sr = sf.read(str(path), always_2d=False)
        meter = pyln.Meter(sr)
        cur_lufs = float(meter.integrated_loudness(y))
        if not np.isfinite(cur_lufs):
            return False, 0.0, "LUFS-Messung ergab -inf (Track ggf. stumm)"

        gain_db = compute_gain_db(cur_lufs, target_lufs)
        gain_lin = 10.0 ** (gain_db / 20.0)
        y_new = (y * gain_lin).astype(y.dtype, copy=False)

        # True-Peak-Sanity: wenn Peak > 0.99 → sanft absenken
        peak = float(np.max(np.abs(y_new))) if y_new.size else 0.0
        if peak > 0.99:
            trim = 0.99 / peak
            y_new = (y_new * trim).astype(y.dtype, copy=False)
            gain_db += 20.0 * np.log10(trim)

        if backup:
            bak = path.with_suffix(path.suffix + ".original")
            if not bak.exists():
                shutil.copy2(path, bak)

        sf.write(str(path), y_new, sr)
        return True, float(gain_db), None
    except Exception as exc:
        return False, 0.0, str(exc)
