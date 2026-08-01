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
from .effects import ChannelFX, GlobalFilterParams, KillSection, OneKnobCompressor


class CrossfadeCurve(str, Enum):
    LINEAR = "linear"
    FAST = "fast"
    SHARP = "sharp"


class ChannelStrip:
    """Ein Mixer-Kanal: EQ (4-Band) → Kill (3-Band) → Compressor → FX → Volume.

    Volume (statt Line-Fader) und globaler Filter-Resonance werden von aussen
    vom Mixer verwaltet.
    """

    F_LOW = 100.0
    F_LOWMID = 400.0
    F_HIGHMID = 2500.0
    F_HIGH = 8000.0

    def __init__(self, sr: int, global_filter: GlobalFilterParams):
        self.sr = sr
        self._eq_low_db = 0.0
        self._eq_lowmid_db = 0.0
        self._eq_highmid_db = 0.0
        self._eq_high_db = 0.0
        if _HAS_PEDALBOARD:
            self._eq_chain = Pedalboard([
                LowShelfFilter(cutoff_frequency_hz=self.F_LOW, gain_db=0.0, q=0.7),
                PeakFilter(cutoff_frequency_hz=self.F_LOWMID, gain_db=0.0, q=1.0),
                PeakFilter(cutoff_frequency_hz=self.F_HIGHMID, gain_db=0.0, q=1.0),
                HighShelfFilter(cutoff_frequency_hz=self.F_HIGH, gain_db=0.0, q=0.7),
            ])
        else:
            self._eq_chain = None

        self.kill = KillSection(sr)
        self.compressor = OneKnobCompressor(sr)
        self.fx = ChannelFX(sr, global_filter)
        self._volume = 1.0    # Rotary-Volume 0..1 (1 = Unity)

    # ---- EQ ----

    def set_low(self, db: float) -> None:
        self._eq_low_db = float(np.clip(db, -26.0, 12.0))
        if self._eq_chain is not None:
            self._eq_chain[0].gain_db = self._eq_low_db

    def set_lowmid(self, db: float) -> None:
        self._eq_lowmid_db = float(np.clip(db, -26.0, 12.0))
        if self._eq_chain is not None:
            self._eq_chain[1].gain_db = self._eq_lowmid_db

    def set_highmid(self, db: float) -> None:
        self._eq_highmid_db = float(np.clip(db, -26.0, 12.0))
        if self._eq_chain is not None:
            self._eq_chain[2].gain_db = self._eq_highmid_db

    def set_high(self, db: float) -> None:
        self._eq_high_db = float(np.clip(db, -26.0, 12.0))
        if self._eq_chain is not None:
            self._eq_chain[3].gain_db = self._eq_high_db

    # ---- Kill (3-Band bipolar) ----

    def set_kill_low(self, v: float) -> None:
        self.kill.low.set_value(v)

    def set_kill_mid(self, v: float) -> None:
        self.kill.mid.set_value(v)

    def set_kill_high(self, v: float) -> None:
        self.kill.high.set_value(v)

    # ---- Compressor ----

    def set_compressor(self, v: float) -> None:
        self.compressor.set_value(v)

    # ---- FX ----

    def set_fx_type(self, t: str) -> None:
        self.fx.set_type(t)

    def set_fx_wet(self, v: float) -> None:
        self.fx.set_wet(v)

    def set_fx_filter_dir(self, d: float) -> None:
        self.fx.set_filter_direction(d)

    # ---- Volume (Rotary statt Fader) ----

    def set_volume(self, v: float) -> None:
        """0.0 = mute, 1.0 = Unity, bis 1.4 = +3 dB Headroom."""
        self._volume = float(np.clip(v, 0.0, 1.4))

    @property
    def volume(self) -> float:
        return self._volume

    # ---- Signal-Chain ----

    def process(self, x: np.ndarray) -> np.ndarray:
        y = x
        if self._eq_chain is not None:
            y = self._eq_chain.process(y, self.sr, reset=False)
            if y.dtype != np.float32:
                y = y.astype(np.float32)
        y = self.kill.process(y)
        y = self.compressor.process(y)
        y = self.fx.process(y)
        if self._volume != 1.0:
            y = y * np.float32(self._volume)
        return y


class Mixer:
    """Summiert 2-4 Decks. A/B ueber Crossfader, C/D immer voll aufgemischt
    (wenn `four_deck_mode` an). Jeder Kanal hat seinen eigenen ChannelStrip.
    """

    def __init__(self, deck_a: Deck, deck_b: Deck, sr: int = 48000,
                 deck_c: Optional[Deck] = None, deck_d: Optional[Deck] = None):
        self.deck_a = deck_a
        self.deck_b = deck_b
        self.deck_c = deck_c
        self.deck_d = deck_d
        self.global_filter = GlobalFilterParams()
        self.strip_a = ChannelStrip(sr, self.global_filter)
        self.strip_b = ChannelStrip(sr, self.global_filter)
        self.strip_c = ChannelStrip(sr, self.global_filter) if deck_c else None
        self.strip_d = ChannelStrip(sr, self.global_filter) if deck_d else None
        self.sr = sr
        self._xfader = 0.0     # -1.0 (nur A) .. +1.0 (nur B), 0 = Mitte
        self._curve = CrossfadeCurve.LINEAR
        self._master_gain_db = 0.0
        self._peak_l = 0.0
        self._peak_r = 0.0
        self._four_deck_mode = False
        self._lock = threading.Lock()

    def set_four_deck_mode(self, on: bool) -> None:
        self._four_deck_mode = bool(on)

    @property
    def four_deck_mode(self) -> bool:
        return self._four_deck_mode

    def set_global_filter_resonance(self, v: float) -> None:
        self.global_filter.resonance = float(np.clip(v, 0.0, 1.0))

    @property
    def global_filter_resonance(self) -> float:
        return float(self.global_filter.resonance)

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
        a = self.strip_a.process(self.deck_a.render(frames))
        b = self.strip_b.process(self.deck_b.render(frames))

        g_a, g_b = self._crossfader_gains()
        master = 10.0 ** (self._master_gain_db / 20.0)

        out = a * np.float32(g_a) + b * np.float32(g_b)
        if self._four_deck_mode and self.deck_c is not None and self.strip_c is not None:
            out += self.strip_c.process(self.deck_c.render(frames))
        if self._four_deck_mode and self.deck_d is not None and self.strip_d is not None:
            out += self.strip_d.process(self.deck_d.render(frames))
        out *= np.float32(master)

        self._peak_l = 0.9 * self._peak_l + 0.1 * float(np.max(np.abs(out[:, 0])))
        self._peak_r = 0.9 * self._peak_r + 0.1 * float(np.max(np.abs(out[:, 1])))
        return out
