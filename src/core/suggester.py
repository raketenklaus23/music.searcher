"""Track-Suggester — Vibe-Vector + Cosine-Similarity, offline.

Nutzt die schon in `tracks` und `beatgrid` gespeicherten Merkmale und
berechnet daraus einen kompakten Vibe-Vector (dimensionsarm, robust):

    [
      bpm_normalized,        # (bpm-60)/140 in ~[0,1]
      energy,                # 0..1
      lufs_normalized,       # (lufs+30)/30 in ~[0,1]
      key_ring_cos,          # cos(2π * ring_index/12)  — Camelot-Zahl
      key_ring_sin,          # sin(2π * ring_index/12)
      is_major,              # 1.0 wenn B (Dur), sonst 0.0
    ]

Camelot-Kompatibilitaet bringt zusaetzlich einen Bonus obendrauf (siehe
`_key_bonus`), damit „passende" Tonarten zueinander gepusht werden.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np

from .keys import compatible_keys, parse_camelot
from .library import Library, Track


VECTOR_LEN = 6


@dataclass
class Suggestion:
    track_id: int
    score: float
    reason: str


def vibe_vector(track: Track) -> Optional[np.ndarray]:
    if track.bpm is None or track.energy is None:
        return None
    bpm_n = float(max(0.0, min(1.0, (track.bpm - 60.0) / 140.0)))
    energy = float(max(0.0, min(1.0, track.energy)))
    lufs = float(track.lufs) if track.lufs is not None else -14.0
    lufs_n = float(max(0.0, min(1.0, (lufs + 30.0) / 30.0)))
    kx, ky, is_major = 0.0, 0.0, 0.0
    if track.key:
        p = parse_camelot(track.key)
        if p is not None:
            n, letter = p
            theta = 2.0 * math.pi * ((n - 1) / 12.0)
            kx = math.cos(theta)
            ky = math.sin(theta)
            is_major = 1.0 if letter == "B" else 0.0
    return np.array([bpm_n, energy, lufs_n, kx, ky, is_major], dtype=np.float32)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _key_bonus(ref: Optional[str], candidate: Optional[str]) -> float:
    if not ref or not candidate:
        return 0.0
    if candidate == ref:
        return 0.15
    if candidate in compatible_keys(ref):
        return 0.08
    return 0.0


def _bpm_penalty(ref_bpm: Optional[float], cand_bpm: Optional[float],
                 half_double_ok: bool = True) -> float:
    if not ref_bpm or not cand_bpm:
        return 0.0
    diff = abs(ref_bpm - cand_bpm)
    if half_double_ok:
        for factor in (2.0, 0.5):
            diff = min(diff, abs(ref_bpm - cand_bpm * factor))
    # 0-2 BPM: neutral, 2-6 BPM: leichter Malus, >6: staerker
    if diff <= 2.0:
        return 0.0
    if diff <= 6.0:
        return -0.05 * (diff - 2.0) / 4.0
    return -0.05 - 0.10 * min(1.0, (diff - 6.0) / 10.0)


def find_similar(
    library: Library,
    ref_track_id: int,
    limit: int = 20,
    bpm_tolerance: Optional[float] = 8.0,
    year_range: Optional[tuple[int, int]] = None,
    artist_filter: Optional[str] = None,
) -> list[Suggestion]:
    """Findet aehnliche Tracks in der Library. `year_range` und `artist_filter`
    sind optional (Suggester-Fenster laesst User beides setzen).
    """
    ref = library.get_track(ref_track_id)
    if ref is None:
        return []
    v_ref = vibe_vector(ref)
    if v_ref is None:
        return []
    scored: list[Suggestion] = []
    for t in library.all_tracks():
        if t.id == ref.id:
            continue
        if year_range and t.year is not None:
            if not (year_range[0] <= t.year <= year_range[1]):
                continue
        if artist_filter and (t.artist or "").lower().find(artist_filter.lower()) < 0:
            continue
        v = vibe_vector(t)
        if v is None:
            continue
        sim = cosine_sim(v_ref, v)
        sim += _key_bonus(ref.key, t.key)
        sim += _bpm_penalty(ref.bpm, t.bpm)
        if bpm_tolerance and ref.bpm and t.bpm:
            if min(abs(ref.bpm - t.bpm), abs(ref.bpm - t.bpm * 2), abs(ref.bpm - t.bpm / 2)) > bpm_tolerance:
                sim -= 0.15
        reason = _describe(ref, t)
        scored.append(Suggestion(track_id=t.id, score=float(sim), reason=reason))
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:limit]


def _describe(ref: Track, cand: Track) -> str:
    parts: list[str] = []
    if ref.key and cand.key:
        if cand.key == ref.key:
            parts.append("Key ident")
        elif cand.key in compatible_keys(ref.key):
            parts.append("Key kompatibel")
    if ref.bpm and cand.bpm:
        d = abs(ref.bpm - cand.bpm)
        if d <= 2.0:
            parts.append("BPM passt")
        elif d <= 6.0:
            parts.append(f"BPM Δ{d:.1f}")
    if ref.energy is not None and cand.energy is not None:
        if abs(ref.energy - cand.energy) < 0.1:
            parts.append("Energy passt")
    return ", ".join(parts) if parts else "Vibe-Match"


# -----------------------------------------------------------------------
# Genre-Playlist-Builder
# -----------------------------------------------------------------------

@dataclass
class GenreCurve:
    """BPM-Kurve fuer ein Set. Beispiel: warm-up → peak → cool-down."""
    length_min: int
    bpm_start: float
    bpm_peak: float
    bpm_end: float


def build_genre_playlist(
    library: Library,
    genres: Iterable[str],
    curve: GenreCurve,
    avg_track_min: float = 4.0,
) -> list[int]:
    """Baut eine Playlist gemaess Genre-Filter + BPM-Kurve."""
    genres_l = {g.lower() for g in genres if g}
    pool: list[Track] = []
    for t in library.all_tracks():
        if not t.bpm:
            continue
        if genres_l and (t.genre or "").lower() not in genres_l:
            continue
        pool.append(t)
    if not pool:
        return []

    slots = max(1, int(round(curve.length_min / avg_track_min)))
    picks: list[int] = []
    used: set[int] = set()

    for i in range(slots):
        # Linear ansteigend bis Mitte, dann absteigend
        frac = i / max(1, slots - 1)
        if frac <= 0.5:
            t_target = curve.bpm_start + (curve.bpm_peak - curve.bpm_start) * (frac * 2)
        else:
            t_target = curve.bpm_peak + (curve.bpm_end - curve.bpm_peak) * ((frac - 0.5) * 2)

        best = None
        best_d = math.inf
        for t in pool:
            if t.id in used:
                continue
            d = abs(t.bpm - t_target)
            if d < best_d:
                best_d = d
                best = t
        if best is None:
            break
        picks.append(best.id)
        used.add(best.id)
    return picks
