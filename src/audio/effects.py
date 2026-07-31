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
# Single-Knob-Compressor (Pioneer-A9-Style)
# Ein Knob 0..1 steuert threshold/ratio/makeup gekoppelt.
# -----------------------------------------------------------------------

class OneKnobCompressor:
    """0.0 = aus (bypass), 1.0 = max Squash + Makeup."""

    def __init__(self, sr: int):
        self.sr = sr
        self._value = 0.0
        if _HAS_PB:
            self._comp = Compressor(
                threshold_db=0.0,
                ratio=1.0,
                attack_ms=8.0,
                release_ms=120.0,
            )
        else:
            self._comp = None

    @property
    def value(self) -> float:
        return self._value

    def set_value(self, v: float) -> None:
        v = float(np.clip(v, 0.0, 1.0))
        self._value = v
        if self._comp is None:
            return
        # Kopplung:
        #   threshold:   0 dB -> -22 dB
        #   ratio:       1.0  ->  5.0
        #   (makeup wird extern per Gain-Multiplikator gemacht)
        self._comp.threshold_db = float(0.0 - v * 22.0)
        self._comp.ratio = float(1.0 + v * 4.0)

    def process(self, x: np.ndarray) -> np.ndarray:
        if self._comp is None or self._value < 1e-4:
            return x
        y = self._comp(x, self.sr, reset=False)
        # Makeup: bis +6 dB abhängig von Value
        makeup = 10.0 ** ((self._value * 6.0) / 20.0)
        if y.dtype != np.float32:
            y = y.astype(np.float32)
        return y * np.float32(makeup)


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
