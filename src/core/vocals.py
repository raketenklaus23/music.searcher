"""Vocal-Region-Erkennung — heuristisch (Phase 3).

Ohne Demucs: HPSS → Harmonic-Track → Vocal-Band-Energie (200-4000 Hz) →
Spectral-Flatness-Gewichtung → adaptive Threshold → zusammenhängende Regionen.

Präzise Vocal-Erkennung folgt in Phase 4 via Demucs-Vocals-Stem
(source='demucs' in DB überschreibt heuristische Regionen).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

try:
    import librosa
    _HAS_LIBROSA = True
except Exception:
    _HAS_LIBROSA = False


MIN_REGION_MS = 1200          # Regions unter 1.2s werden verworfen
MERGE_GAP_MS = 400            # Regions mit weniger Abstand werden zusammengefasst


def detect_vocal_regions(
    y: np.ndarray,
    sr: int,
    min_region_ms: int = MIN_REGION_MS,
    merge_gap_ms: int = MERGE_GAP_MS,
) -> list[tuple[int, int, float]]:
    """Detektiert Vocal-Regionen.

    Args:
        y: mono float32
        sr: Sample-Rate

    Returns:
        [(start_ms, end_ms, confidence), ...] chronologisch, non-overlapping.
    """
    if not _HAS_LIBROSA or y.size == 0:
        return []

    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32, copy=False)

    # Harmonic-percussive separation — Vocals leben im Harmonic-Anteil
    try:
        y_harm, _ = librosa.effects.hpss(y, margin=(1.0, 3.0))
    except Exception:
        y_harm = y

    hop = 512
    n_fft = 2048

    # STFT einmal für alles was folgt
    S = np.abs(librosa.stft(y_harm, n_fft=n_fft, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    # Vocal-Band: 200 Hz .. 4 kHz
    vocal_mask = (freqs >= 200.0) & (freqs <= 4000.0)
    vocal_energy = np.sqrt(np.mean(S[vocal_mask, :] ** 2, axis=0))    # RMS pro Frame

    # Total-Energy (für relative Metrik)
    total_energy = np.sqrt(np.mean(S ** 2, axis=0) + 1e-9)

    # Vocal-Prominenz: Anteil der Energie im Vocal-Band
    vocal_ratio = vocal_energy / (total_energy + 1e-9)

    # Spectral-Flatness → niedrige Flatness = tonaler (Vocals)
    flatness = librosa.feature.spectral_flatness(S=S, hop_length=hop).flatten()
    tonalness = 1.0 - np.clip(flatness, 0.0, 1.0)

    # Kombinierte Vocal-Score-Kurve
    score = vocal_ratio * tonalness

    # Glätten (Median über ~200ms)
    win = max(3, int((0.2 * sr) / hop))
    if win % 2 == 0:
        win += 1
    score_smooth = _median_filter_1d(score, win)

    # Adaptive Threshold: 60. Perzentil oberhalb Rausch-Median
    med = float(np.median(score_smooth))
    mad = float(np.median(np.abs(score_smooth - med)) + 1e-9)
    thr = med + 1.6 * mad

    binary = score_smooth > thr

    # Frames → ms
    frame_ms = int(round(hop / sr * 1000.0))

    regions = _binary_to_regions(binary, frame_ms, score_smooth)
    regions = _merge_close_regions(regions, merge_gap_ms)
    regions = [r for r in regions if (r[1] - r[0]) >= min_region_ms]
    return regions


# -----------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------

def _median_filter_1d(x: np.ndarray, w: int) -> np.ndarray:
    if w < 3:
        return x.copy()
    pad = w // 2
    xp = np.pad(x, pad, mode="edge")
    out = np.empty_like(x)
    for i in range(len(x)):
        out[i] = np.median(xp[i : i + w])
    return out


def _binary_to_regions(binary: np.ndarray, frame_ms: int, score: np.ndarray) -> list[tuple[int, int, float]]:
    regions: list[tuple[int, int, float]] = []
    n = len(binary)
    i = 0
    while i < n:
        if not binary[i]:
            i += 1
            continue
        j = i
        while j < n and binary[j]:
            j += 1
        start_ms = i * frame_ms
        end_ms = j * frame_ms
        conf = float(np.mean(score[i:j]))
        regions.append((start_ms, end_ms, conf))
        i = j
    # Confidence normalisieren auf 0..1
    if regions:
        max_c = max(r[2] for r in regions)
        if max_c > 0:
            regions = [(s, e, min(1.0, c / max_c)) for s, e, c in regions]
    return regions


def _merge_close_regions(
    regions: list[tuple[int, int, float]],
    max_gap_ms: int,
) -> list[tuple[int, int, float]]:
    if not regions:
        return regions
    merged = [regions[0]]
    for start, end, conf in regions[1:]:
        p_start, p_end, p_conf = merged[-1]
        if start - p_end <= max_gap_ms:
            merged[-1] = (p_start, end, max(p_conf, conf))
        else:
            merged.append((start, end, conf))
    return merged
