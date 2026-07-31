"""Top-Level Audio-Player: verbindet Engine + Mixer + Decks + Sync.

Instanziert einmal beim App-Start. Callback der Engine ruft `mixer.render()`.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .deck import Deck
from .engine import AudioEngine, DeviceInfo, EngineConfig
from .mixer import Mixer
from .sync import SyncController


class Player:
    def __init__(self, samplerate: int = 48000, blocksize: int = 256):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.deck_a = Deck("a", engine_sr=samplerate)
        self.deck_b = Deck("b", engine_sr=samplerate)
        self.mixer = Mixer(self.deck_a, self.deck_b, sr=samplerate)
        self.sync = SyncController(self.deck_a, self.deck_b)
        self.engine = AudioEngine(self._callback, EngineConfig(
            samplerate=samplerate, blocksize=blocksize,
        ))

    def start(self, device_index: Optional[int] = None,
              samplerate: Optional[int] = None,
              blocksize: Optional[int] = None) -> None:
        cfg = EngineConfig(
            device_index=device_index if device_index is not None else self.engine.config.device_index,
            samplerate=samplerate or self.samplerate,
            blocksize=blocksize or self.blocksize,
            channels=2,
            wasapi_exclusive=True,
        )
        self.engine.restart(cfg)
        # ggf. Decks auf neue Engine-Samplerate
        if cfg.samplerate != self.samplerate:
            self.samplerate = cfg.samplerate
            self.deck_a.engine_sr = cfg.samplerate
            self.deck_b.engine_sr = cfg.samplerate

    def stop(self) -> None:
        self.engine.stop()

    def list_devices(self) -> list[DeviceInfo]:
        return AudioEngine.list_output_devices()

    def _callback(self, outdata: np.ndarray, frames: int, time_info, status) -> None:
        buf = self.mixer.render(frames)
        # Sicherheits-Clamp gegen Clipping
        np.clip(buf, -1.0, 1.0, out=buf)
        outdata[:] = buf
