"""Deck-Engine — Playback eines einzelnen Tracks mit Tempo/Pitch/KeyLock.

MVP-Ansatz für niedrige Latenz und Stabilität:
  * Kompletter Track wird beim Load in Float32-RAM-Buffer dekodiert (Stereo).
  * Tempo-Änderung = variable Read-Speed (Linear-Interp). Ändert klassisch auch die Pitch.
  * KeyLock: pedalboard.PitchShift kompensiert die Pitch-Änderung (in Semitones).
  * Key-Match: zusätzlicher Semitone-Offset via PitchShift, um Zieltonart zu erreichen.
  * Cue-Point / Loop / Playhead.

Alle heißen Operationen (mix, interp, EQ) sind vektorisiert und laufen im
Audio-Callback via `render(frames) -> np.ndarray[frames, 2]`.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

try:
    from pedalboard import Pedalboard, PitchShift
    _HAS_PEDALBOARD = True
except Exception:
    _HAS_PEDALBOARD = False


@dataclass
class DeckState:
    track_id: Optional[int] = None
    track_path: Optional[str] = None
    duration_s: float = 0.0
    source_sr: int = 44100
    engine_sr: int = 48000
    bpm: Optional[float] = None
    key: Optional[str] = None
    playing: bool = False
    playhead_frames: float = 0.0        # in ENGINE-Samples (float für Sub-Sample-Präzision)
    cue_point_s: float = 0.0
    loop_start_s: float = 0.0
    loop_end_s: float = 0.0
    loop_active: bool = False
    tempo_ratio: float = 1.0            # 1.0 = original, 1.05 = +5%
    key_lock: bool = True
    pitch_semitones: float = 0.0        # zusätzliche Key-Match-Verschiebung
    gain_db: float = 0.0
    volume: float = 1.0                 # channel fader 0..1
    stem_mode: bool = False             # True → Stems statt Haupt-Buffer mixen
    stem_model: Optional[str] = None    # htdemucs | htdemucs_6s
    stem_names: list = field(default_factory=list)  # z. B. ['drums','bass','other','vocals']


class Deck:
    """Ein einzelnes DJ-Deck. Thread-sicher für Steuerung aus dem GUI-Thread."""

    def __init__(self, deck_id: str, engine_sr: int = 48000):
        self.deck_id = deck_id
        self.engine_sr = engine_sr
        self._state = DeckState(engine_sr=engine_sr)
        # Buffer: shape (N, 2) float32, bereits auf engine_sr resampled
        self._buf: Optional[np.ndarray] = None
        self._buf_len = 0
        self._lock = threading.Lock()
        # Pedalboard PitchShift für KeyLock — created per load
        self._pitchshift = None
        # Stem-Playback: gleich lange Buffer pro Stem, plus Vol/Mute/Solo
        self._stem_bufs: dict[str, np.ndarray] = {}
        self._stem_volumes: dict[str, float] = {}
        self._stem_muted: dict[str, bool] = {}
        self._stem_soloed: dict[str, bool] = {}

    # ---- Load & Params ------------------------------------------------

    def load(self, path: Path, track_id: Optional[int] = None,
             bpm: Optional[float] = None, key: Optional[str] = None) -> None:
        """Lädt Datei in RAM, resamplet auf engine_sr, stereoisiert."""
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]

        if sr != self.engine_sr:
            data = _resample_linear(data, sr, self.engine_sr)

        with self._lock:
            self._buf = np.ascontiguousarray(data, dtype=np.float32)
            self._buf_len = self._buf.shape[0]
            self._state.track_id = track_id
            self._state.track_path = str(path)
            self._state.source_sr = sr
            self._state.duration_s = self._buf_len / self.engine_sr
            self._state.bpm = bpm
            self._state.key = key
            self._state.playing = False
            self._state.playhead_frames = 0.0
            self._state.cue_point_s = 0.0
            self._state.loop_active = False

        if _HAS_PEDALBOARD:
            self._pitchshift = Pedalboard([PitchShift(semitones=0.0)])

    def unload(self) -> None:
        with self._lock:
            self._buf = None
            self._buf_len = 0
            self._stem_bufs.clear()
            self._stem_volumes.clear()
            self._stem_muted.clear()
            self._stem_soloed.clear()
            self._state = DeckState(engine_sr=self.engine_sr)

    # ---- Stems -------------------------------------------------------

    def load_stems(self, model: str, stem_paths: dict[str, str]) -> None:
        """Lädt Stem-WAVs, resamplet, stereoisiert und aktiviert Stem-Mode.
        Alle Stems müssen dieselbe Länge haben (Demucs-Konvention).
        """
        loaded: dict[str, np.ndarray] = {}
        max_len = 0
        for name, path in stem_paths.items():
            try:
                data, sr = sf.read(str(path), dtype="float32", always_2d=True)
            except Exception:
                continue
            if data.shape[1] == 1:
                data = np.repeat(data, 2, axis=1)
            elif data.shape[1] > 2:
                data = data[:, :2]
            if sr != self.engine_sr:
                data = _resample_linear(data, sr, self.engine_sr)
            loaded[name] = np.ascontiguousarray(data, dtype=np.float32)
            max_len = max(max_len, loaded[name].shape[0])
        if not loaded:
            return
        # gleiche Länge sicherstellen (padding, falls Demucs leicht abweicht)
        for name, arr in list(loaded.items()):
            if arr.shape[0] < max_len:
                pad = np.zeros((max_len - arr.shape[0], 2), dtype=np.float32)
                loaded[name] = np.vstack([arr, pad])
        with self._lock:
            self._stem_bufs = loaded
            self._stem_volumes = {n: 1.0 for n in loaded}
            self._stem_muted = {n: False for n in loaded}
            self._stem_soloed = {n: False for n in loaded}
            self._state.stem_mode = True
            self._state.stem_model = model
            self._state.stem_names = list(loaded.keys())

    def unload_stems(self) -> None:
        with self._lock:
            self._stem_bufs.clear()
            self._stem_volumes.clear()
            self._stem_muted.clear()
            self._stem_soloed.clear()
            self._state.stem_mode = False
            self._state.stem_model = None
            self._state.stem_names = []

    def set_stem_mode(self, on: bool) -> None:
        with self._lock:
            if on and not self._stem_bufs:
                return
            self._state.stem_mode = bool(on)

    def set_stem_volume(self, stem: str, v: float) -> None:
        if stem in self._stem_volumes:
            self._stem_volumes[stem] = float(np.clip(v, 0.0, 1.4))

    def set_stem_muted(self, stem: str, muted: bool) -> None:
        if stem in self._stem_muted:
            self._stem_muted[stem] = bool(muted)

    def set_stem_soloed(self, stem: str, soloed: bool) -> None:
        if stem in self._stem_soloed:
            self._stem_soloed[stem] = bool(soloed)

    @property
    def state(self) -> DeckState:
        return self._state

    def is_loaded(self) -> bool:
        return self._buf is not None and self._buf_len > 0

    # ---- Transport ---------------------------------------------------

    def play(self) -> None:
        with self._lock:
            if self._buf is None:
                return
            self._state.playing = True

    def pause(self) -> None:
        with self._lock:
            self._state.playing = False

    def toggle(self) -> None:
        with self._lock:
            if self._buf is not None:
                self._state.playing = not self._state.playing

    def seek_seconds(self, sec: float) -> None:
        with self._lock:
            self._state.playhead_frames = max(0.0, min(sec * self.engine_sr, self._buf_len - 1))

    def set_cue(self, sec: Optional[float] = None) -> None:
        """Setze Cue an aktuelle Position (default) oder an gegebene Sekunde."""
        with self._lock:
            if sec is None:
                self._state.cue_point_s = self._state.playhead_frames / self.engine_sr
            else:
                self._state.cue_point_s = max(0.0, sec)

    def jump_to_cue(self) -> None:
        with self._lock:
            self._state.playhead_frames = self._state.cue_point_s * self.engine_sr

    def set_loop(self, start_s: float, end_s: float, active: bool = True) -> None:
        with self._lock:
            self._state.loop_start_s = max(0.0, start_s)
            self._state.loop_end_s = max(start_s + 0.01, end_s)
            self._state.loop_active = active

    def clear_loop(self) -> None:
        with self._lock:
            self._state.loop_active = False

    # ---- Sound-Params (thread-safe scalar sets) -----------------------

    def set_tempo_ratio(self, ratio: float) -> None:
        self._state.tempo_ratio = float(max(0.5, min(2.0, ratio)))
        self._update_pitchshift()

    def set_key_lock(self, on: bool) -> None:
        self._state.key_lock = bool(on)
        self._update_pitchshift()

    def set_pitch_semitones(self, semis: float) -> None:
        self._state.pitch_semitones = float(max(-12.0, min(12.0, semis)))
        self._update_pitchshift()

    def set_gain_db(self, db: float) -> None:
        self._state.gain_db = float(max(-60.0, min(12.0, db)))

    def set_volume(self, v: float) -> None:
        self._state.volume = float(max(0.0, min(1.0, v)))

    def _update_pitchshift(self) -> None:
        if self._pitchshift is None:
            return
        # KeyLock: kompensiere Tempo-Pitch-Change (Semitones = 12 * log2(ratio))
        comp = 0.0
        if self._state.key_lock and self._state.tempo_ratio != 1.0:
            comp = -12.0 * float(np.log2(self._state.tempo_ratio))
        total = comp + self._state.pitch_semitones
        try:
            self._pitchshift[0].semitones = float(np.clip(total, -12.0, 12.0))
        except Exception:
            pass

    # ---- Playback ----------------------------------------------------

    def render(self, frames: int) -> np.ndarray:
        """Liefert `frames` Samples Stereo als (frames, 2) float32."""
        out = np.zeros((frames, 2), dtype=np.float32)
        if self._buf is None or not self._state.playing:
            return out

        ratio = self._state.tempo_ratio
        buf = self._buf
        buf_len = self._buf_len

        pos = self._state.playhead_frames
        loop_active = self._state.loop_active
        loop_start = self._state.loop_start_s * self.engine_sr
        loop_end = self._state.loop_end_s * self.engine_sr

        # Variable Read-Speed via Linear-Interp
        idx = pos + np.arange(frames, dtype=np.float64) * ratio
        if loop_active and loop_end > loop_start:
            span = loop_end - loop_start
            idx = loop_start + (idx - loop_start) % span
        # Clipping am Ende
        idx = np.clip(idx, 0.0, buf_len - 1.0001)
        i0 = idx.astype(np.int64)
        i1 = i0 + 1
        frac = (idx - i0).astype(np.float32).reshape(-1, 1)

        if self._state.stem_mode and self._stem_bufs:
            # Solo-Logik: wenn eines auf solo, andere stumm
            any_solo = any(self._stem_soloed.values())
            mix = np.zeros_like(out)
            for name, sbuf in self._stem_bufs.items():
                if self._stem_muted.get(name):
                    continue
                if any_solo and not self._stem_soloed.get(name):
                    continue
                if sbuf.shape[0] <= i1[-1]:
                    continue
                vol = self._stem_volumes.get(name, 1.0)
                if vol <= 0.0:
                    continue
                mix += (sbuf[i0] * (1.0 - frac) + sbuf[i1] * frac) * np.float32(vol)
            out[:] = mix
        else:
            # Interpolierte Samples (Standard)
            out[:] = buf[i0] * (1.0 - frac) + buf[i1] * frac

        # Playhead vorschieben
        new_pos = pos + frames * ratio
        if loop_active and loop_end > loop_start:
            new_pos = loop_start + (new_pos - loop_start) % (loop_end - loop_start)
        elif new_pos >= buf_len - 1:
            new_pos = float(buf_len - 1)
            self._state.playing = False
        self._state.playhead_frames = new_pos

        # KeyLock / Pitch Shift (nach dem Tempo-Read)
        if self._pitchshift is not None and (
            self._state.key_lock and self._state.tempo_ratio != 1.0
            or self._state.pitch_semitones != 0.0
        ):
            try:
                # pedalboard erwartet shape (channels, samples) oder (samples, channels)? — .process nimmt (samples, channels)
                out = self._pitchshift.process(out, self.engine_sr, reset=False)
                if out.dtype != np.float32:
                    out = out.astype(np.float32)
                if out.shape[0] != frames:
                    # Länge normalisieren (PitchShift kann leicht abweichen)
                    if out.shape[0] > frames:
                        out = out[:frames]
                    else:
                        pad = np.zeros((frames - out.shape[0], 2), dtype=np.float32)
                        out = np.vstack([out, pad])
            except Exception:
                pass

        # Gain + Volume
        gain_lin = 10.0 ** (self._state.gain_db / 20.0) * self._state.volume
        if gain_lin != 1.0:
            out *= np.float32(gain_lin)

        return out


def _resample_linear(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Einfache Linear-Interpolation. Beim Load ist Qualität ok; für höhere
    Ansprüche später auf soxr/scipy.signal.resample_poly umstellen."""
    if sr_in == sr_out:
        return x
    n_in = x.shape[0]
    n_out = int(round(n_in * sr_out / sr_in))
    idx = np.linspace(0.0, n_in - 1, n_out, dtype=np.float64)
    i0 = idx.astype(np.int64)
    i1 = np.minimum(i0 + 1, n_in - 1)
    frac = (idx - i0).astype(np.float32).reshape(-1, 1)
    out = x[i0] * (1.0 - frac) + x[i1] * frac
    return out.astype(np.float32)
