"""Kanal-Effekte: Kill-Filter, Single-Knob-Compressor, FX-Chain (echo/reverb/noise/filter).

Alle pedalboard-basiert (GIL-frei, C++). Fallback: identity passthrough wenn
pedalboard nicht installiert ist.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

import numpy as np

try:
    from pedalboard import (
        Compressor,
        Delay,
        HighpassFilter,
        LadderFilter,
        LowpassFilter,
        PeakFilter,
        Pedalboard,
        Reverb,
    )
    _HAS_PB = True
except Exception:
    _HAS_PB = False


# -----------------------------------------------------------------------
# Kill-Filter (3-Band): -30 dB (kill) .. 0 dB (flat) .. +6 dB (boost)
# Ecler-Warm-Style: bipolar-Knob mit 12-Uhr = flat.
# -----------------------------------------------------------------------

class KillBand:
    """Ein Kill-Band. Value: -1.0 (voll gekillt) .. 0.0 (flat) .. +1.0 (voll geboostet)."""

    KILL_DB = -30.0
    BOOST_DB = 6.0

    def __init__(self, cutoff_hz: float, q: float, sr: int):
        self.sr = sr
        self._value = 0.0
        if _HAS_PB:
            self._filter = PeakFilter(cutoff_frequency_hz=cutoff_hz, gain_db=0.0, q=q)
        else:
            self._filter = None

    @property
    def value(self) -> float:
        return self._value

    def set_value(self, v: float) -> None:
        v = float(np.clip(v, -1.0, 1.0))
        self._value = v
        db = v * self.KILL_DB if v < 0 else v * self.BOOST_DB
        if self._filter is not None:
            self._filter.gain_db = db


class KillSection:
    """3-Band Kill Low/Mid/High. Nutzt PeakFilter mit hoher Bandbreite."""

    F_LOW = 120.0
    F_MID = 1000.0
    F_HIGH = 8000.0

    def __init__(self, sr: int):
        self.sr = sr
        self.low = KillBand(self.F_LOW, q=0.9, sr=sr)
        self.mid = KillBand(self.F_MID, q=0.9, sr=sr)
        self.high = KillBand(self.F_HIGH, q=0.9, sr=sr)
        if _HAS_PB:
            self._chain = Pedalboard([self.low._filter, self.mid._filter, self.high._filter])
        else:
            self._chain = None

    def process(self, x: np.ndarray) -> np.ndarray:
        if self._chain is None:
            return x
        y = self._chain.process(x, self.sr, reset=False)
        if y.dtype != np.float32:
            y = y.astype(np.float32)
        return y


# -----------------------------------------------------------------------
# Single-Knob-Compressor (Macro, User-Vorgabe 2026-08-01)
# Ein Knob 0..1 steuert Ratio + Threshold + Auto-Makeup gekoppelt.
# Kurve (v>0):
#   ratio:      2.0 → 4.0        (moderate Anhebung)
#   threshold:  0 dB → -22 dB    (linear absenken)
#   makeup:     automatisch aus |T| und Ratio geschätzt (Loudness-Kompensation)
#   attack:     22 ms            (kick-freundlich, im Fenster 15-30)
#   release:    80 ms            (kick-freundlich, im Fenster 60-100)
# v == 0 → Bypass.
# -----------------------------------------------------------------------

class OneKnobCompressor:
    """Macro-Compressor. 0.0 = bypass, 1.0 = voll auf (Ratio 4:1, T=-22 dB)."""

    ATTACK_MS = 22.0
    RELEASE_MS = 80.0
    RATIO_MIN = 2.0
    RATIO_MAX = 4.0
    THRESH_MAX_DB = -22.0
    # Anteil des Signals, das im Mittel oberhalb Threshold liegt (heuristisch)
    _MAKEUP_HEADROOM = 0.7

    def __init__(self, sr: int):
        self.sr = sr
        self._value = 0.0
        if _HAS_PB:
            self._comp = Compressor(
                threshold_db=0.0,
                ratio=1.0,
                attack_ms=self.ATTACK_MS,
                release_ms=self.RELEASE_MS,
            )
        else:
            self._comp = None
        self._makeup_lin = 1.0

    @property
    def value(self) -> float:
        return self._value

    def set_value(self, v: float) -> None:
        v = float(np.clip(v, 0.0, 1.0))
        self._value = v
        if self._comp is None:
            return
        ratio = self.RATIO_MIN + v * (self.RATIO_MAX - self.RATIO_MIN)
        threshold_db = v * self.THRESH_MAX_DB
        self._comp.ratio = float(ratio)
        self._comp.threshold_db = float(threshold_db)
        # Auto-Makeup: |T| * (1 - 1/R) ist die max. Reduktion bei 0 dBFS.
        # Wir kompensieren einen Anteil davon (nicht die Peaks, sondern den
        # mittleren Lautheitsverlust) → Signal bleibt gefühlt gleich laut.
        red_max_db = abs(threshold_db) * (1.0 - 1.0 / ratio)
        makeup_db = red_max_db * self._MAKEUP_HEADROOM
        self._makeup_lin = 10.0 ** (makeup_db / 20.0)

    def process(self, x: np.ndarray) -> np.ndarray:
        if self._comp is None or self._value < 1e-4:
            return x
        y = self._comp(x, self.sr, reset=False)
        if y.dtype != np.float32:
            y = y.astype(np.float32)
        if self._makeup_lin != 1.0:
            y = y * np.float32(self._makeup_lin)
        return y


# -----------------------------------------------------------------------
# ChannelFX: Echo / Reverb / Noise / Filter mit Wet-Knob
# Nur der aktive Typ läuft. Filter ist bipolar (LP/HP je nach Vorzeichen).
# Filter-Resonance ist global (siehe GlobalFilterParams).
# -----------------------------------------------------------------------

class FxType(str, Enum):
    NONE = "none"
    ECHO = "echo"
    REVERB = "reverb"
    NOISE = "noise"
    FILTER = "filter"


class GlobalFilterParams:
    """Von aussen shared. resonance 0..1 für alle Filter-FX-Instanzen."""

    def __init__(self):
        self.resonance = 0.3     # 0..1


class ChannelFX:
    """Ein Kanal-FX-Slot. Typ + Wet-Knob (0..1).

    Für 'filter' wird wet-Knob als Cutoff-Sweep interpretiert: 0 = neutral,
    Vorzeichen kommt aus separatem set_filter_direction() (bipolar UI-Knob).
    """

    def __init__(self, sr: int, global_filter: GlobalFilterParams):
        self.sr = sr
        self._global_filter = global_filter
        self._type = FxType.NONE
        self._wet = 0.0
        self._filter_dir = 0.0    # -1..0 = LP-Sweep,  0..+1 = HP-Sweep

        if _HAS_PB:
            self._delay = Delay(delay_seconds=0.375, feedback=0.45, mix=0.0)
            self._reverb = Reverb(room_size=0.6, damping=0.4, wet_level=0.0, dry_level=1.0)
            self._ladder_lp = LadderFilter(mode=LadderFilter.LPF12, cutoff_hz=18000.0, resonance=0.3, drive=1.0)
            self._ladder_hp = LadderFilter(mode=LadderFilter.HPF12, cutoff_hz=20.0, resonance=0.3, drive=1.0)
        else:
            self._delay = None
            self._reverb = None
            self._ladder_lp = None
            self._ladder_hp = None

        # Rauschen: RNG einmalig
        self._rng = np.random.default_rng()

    # ---- Params ----

    def set_type(self, t: str) -> None:
        try:
            self._type = FxType(t)
        except ValueError:
            self._type = FxType.NONE

    def set_wet(self, v: float) -> None:
        self._wet = float(np.clip(v, 0.0, 1.0))
        if self._delay is not None:
            self._delay.mix = self._wet if self._type == FxType.ECHO else 0.0
        if self._reverb is not None:
            self._reverb.wet_level = self._wet if self._type == FxType.REVERB else 0.0
            self._reverb.dry_level = 1.0 - (0.4 * self._wet) if self._type == FxType.REVERB else 1.0

    def set_filter_direction(self, d: float) -> None:
        """-1 = voll LP, 0 = neutral, +1 = voll HP."""
        self._filter_dir = float(np.clip(d, -1.0, 1.0))

    @property
    def type(self) -> str:
        return self._type.value

    @property
    def wet(self) -> float:
        return self._wet

    # ---- Render ----

    def process(self, x: np.ndarray) -> np.ndarray:
        if self._type == FxType.NONE or self._wet < 1e-4:
            return x

        if self._type == FxType.ECHO and self._delay is not None:
            y = self._delay(x, self.sr, reset=False)
            return y.astype(np.float32) if y.dtype != np.float32 else y

        if self._type == FxType.REVERB and self._reverb is not None:
            y = self._reverb(x, self.sr, reset=False)
            return y.astype(np.float32) if y.dtype != np.float32 else y

        if self._type == FxType.NOISE:
            n = self._rng.standard_normal(x.shape).astype(np.float32) * np.float32(self._wet * 0.15)
            return (x + n).astype(np.float32)

        if self._type == FxType.FILTER:
            if self._filter_dir == 0.0:
                return x
            res = float(np.clip(self._global_filter.resonance, 0.0, 1.0))
            # Resonance-Mapping: 0..1 → 0.1..0.9 (LadderFilter Range)
            res_pb = 0.1 + res * 0.8

            if self._filter_dir < 0 and self._ladder_lp is not None:
                # LP-Sweep: dir -1 → 200 Hz,  0 → 18 kHz
                t = -self._filter_dir      # 0..1
                cutoff = 18000.0 * (1.0 - t) + 200.0 * t
                self._ladder_lp.cutoff_hz = float(cutoff)
                self._ladder_lp.resonance = res_pb
                y = self._ladder_lp(x, self.sr, reset=False)
            elif self._filter_dir > 0 and self._ladder_hp is not None:
                # HP-Sweep: dir 0 → 20 Hz, +1 → 6 kHz
                t = self._filter_dir
                cutoff = 20.0 * (1.0 - t) + 6000.0 * t
                self._ladder_hp.cutoff_hz = float(cutoff)
                self._ladder_hp.resonance = res_pb
                y = self._ladder_hp(x, self.sr, reset=False)
            else:
                return x

            # Wet-Blend zwischen dry und filtered
            if y.dtype != np.float32:
                y = y.astype(np.float32)
            w = np.float32(self._wet)
            return (x * (1.0 - w) + y * w).astype(np.float32)

        return x
