"""Mixer: Summiert 2 Decks, Crossfader-Kurven, 4-Band-EQ, Master-Gain, LUFS-Peak-Meter.

pedalboard-EQ (nativer C++-Code, GIL-frei) im Audio-Callback ok. Crossfader-
Kurven: Linear (weich), Fast (früh voll auf einer Seite), Sharp (Hard-Cut).
"""
from __future__ import annotations

import threading
from enum import Enum
from typing import Optional

import numpy as np

try:
    from pedalboard import Pedalboard, LowShelfFilter, PeakFilter, HighShelfFilter
    _HAS_PEDALBOARD = True
except Exception:
    _HAS_PEDALBOARD = False

from .deck import Deck


class CrossfadeCurve(str, Enum):
    LINEAR = "linear"
    FAST = "fast"
    SHARP = "sharp"


class ChannelStrip:
    """Ein Mixer-Kanal: 4-Band-EQ + Volume/Gain (Gain sitzt schon im Deck)."""

    # Frequenzen für 4-Band EQ (typisch für DJ-Mixer)
    F_LOW = 100.0
    F_LOWMID = 400.0
    F_HIGHMID = 2500.0
    F_HIGH = 8000.0

    def __init__(self, sr: int = 48000):
        self.sr = sr
        self._eq_low_db = 0.0
        self._eq_lowmid_db = 0.0
        self._eq_highmid_db = 0.0
        self._eq_high_db = 0.0
        if _HAS_PEDALBOARD:
            self._chain = Pedalboard([
                LowShelfFilter(cutoff_frequency_hz=self.F_LOW, gain_db=0.0, q=0.7),
                PeakFilter(cutoff_frequency_hz=self.F_LOWMID, gain_db=0.0, q=1.0),
                PeakFilter(cutoff_frequency_hz=self.F_HIGHMID, gain_db=0.0, q=1.0),
                HighShelfFilter(cutoff_frequency_hz=self.F_HIGH, gain_db=0.0, q=0.7),
            ])
        else:
            self._chain = None

    def set_low(self, db: float) -> None:
        self._eq_low_db = float(np.clip(db, -26.0, 12.0))
        if self._chain is not None:
            self._chain[0].gain_db = self._eq_low_db

    def set_lowmid(self, db: float) -> None:
        self._eq_lowmid_db = float(np.clip(db, -26.0, 12.0))
        if self._chain is not None:
            self._chain[1].gain_db = self._eq_lowmid_db

    def set_highmid(self, db: float) -> None:
        self._eq_highmid_db = float(np.clip(db, -26.0, 12.0))
        if self._chain is not None:
            self._chain[2].gain_db = self._eq_highmid_db

    def set_high(self, db: float) -> None:
        self._eq_high_db = float(np.clip(db, -26.0, 12.0))
        if self._chain is not None:
            self._chain[3].gain_db = self._eq_high_db

    def process(self, x: np.ndarray) -> np.ndarray:
        if self._chain is None:
            return x
        # pedalboard erwartet float32 (samples, channels) und Samplerate
        y = self._chain.process(x, self.sr, reset=False)
        if y.dtype != np.float32:
            y = y.astype(np.float32)
        return y


class Mixer:
    """Summiert 2 Decks mit Crossfader + je Channel-Strip."""

    def __init__(self, deck_a: Deck, deck_b: Deck, sr: int = 48000):
        self.deck_a = deck_a
        self.deck_b = deck_b
        self.strip_a = ChannelStrip(sr)
        self.strip_b = ChannelStrip(sr)
        self.sr = sr
        self._xfader = 0.0     # -1.0 (nur A) .. +1.0 (nur B), 0 = Mitte
        self._curve = CrossfadeCurve.LINEAR
        self._master_gain_db = 0.0
        self._peak_l = 0.0
        self._peak_r = 0.0
        self._lock = threading.Lock()

    # ---- Params -------------------------------------------------------

    def set_crossfader(self, x: float) -> None:
        self._xfader = float(np.clip(x, -1.0, 1.0))

    def set_curve(self, curve: CrossfadeCurve) -> None:
        self._curve = curve

    def set_master_gain_db(self, db: float) -> None:
        self._master_gain_db = float(np.clip(db, -60.0, 6.0))

    @property
    def peak_dbfs(self) -> tuple[float, float]:
        eps = 1e-9
        return (
            20.0 * float(np.log10(self._peak_l + eps)),
            20.0 * float(np.log10(self._peak_r + eps)),
        )

    # ---- Mix ---------------------------------------------------------

    def _crossfader_gains(self) -> tuple[float, float]:
        x = self._xfader        # -1..1
        t = (x + 1.0) * 0.5     # 0..1
        c = self._curve
        if c == CrossfadeCurve.LINEAR:
            g_b = t
            g_a = 1.0 - t
        elif c == CrossfadeCurve.FAST:
            # equal-power (constant loudness) — deutlich weicher
            g_a = float(np.cos(t * np.pi * 0.5))
            g_b = float(np.sin(t * np.pi * 0.5))
        elif c == CrossfadeCurve.SHARP:
            # hard cut in der Mitte
            g_a = 1.0 if t < 0.5 else 0.0
            g_b = 0.0 if t < 0.5 else 1.0
        else:
            g_a = 1.0 - t
            g_b = t
        return g_a, g_b

    def render(self, frames: int) -> np.ndarray:
        a = self.deck_a.render(frames)
        b = self.deck_b.render(frames)
        a = self.strip_a.process(a)
        b = self.strip_b.process(b)

        g_a, g_b = self._crossfader_gains()
        master = 10.0 ** (self._master_gain_db / 20.0)

        out = (a * np.float32(g_a) + b * np.float32(g_b)) * np.float32(master)

        # Peak-Update (billig, nur max abs pro Kanal)
        self._peak_l = 0.9 * self._peak_l + 0.1 * float(np.max(np.abs(out[:, 0])))
        self._peak_r = 0.9 * self._peak_r + 0.1 * float(np.max(np.abs(out[:, 1])))
        return out
