"""Low-Latency Audio-Engine.

Design-Prinzipien:
  * ASIO first (falls im PortAudio-Build enthalten), sonst WDM-KS Exclusive,
    dann WASAPI Exclusive, dann WASAPI Shared. MME/DirectSound nur Notnagel.
  * Callback ist strikt lock-free: KEIN Python-I/O, KEIN Logging, KEIN sqlite,
    KEINE dict-Allokation im Callback. Nur NumPy-Vektoroperationen + pedalboard.
  * Sample-Clock (Callback-`time.outputBufferDacTime`) ist Master.
  * User kann Device/SampleRate/Buffersize im Settings ändern → Engine startet
    nur bei diesen Änderungen neu.

Wenn der Nutzer echte ASIO-Latenz will (nicht im PyPI-Build): entweder
`sounddevice-asio` builden oder ASIO4ALL/Hersteller-ASIO installieren und
sounddevice gegen ein ASIO-fähiges PortAudio linken. Falls nicht möglich,
liefert WDM-KS Exclusive ~5-8 ms Roundtrip auf halbwegs modernen Interfaces.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

# Bevorzugungs-Reihenfolge der HostAPIs (Substring-Match auf `sd.query_hostapis()`).
_HOSTAPI_PRIORITY = ("ASIO", "WDM-KS", "WASAPI", "DirectSound", "MME")

# Standard-Buffergrößen. 128 @ 48k ≈ 2.7 ms; unter Windows ohne ASIO oft
# WDM-KS 256 (~5 ms) das erreichbare Minimum.
DEFAULT_BLOCKSIZE = 256
DEFAULT_SAMPLERATE = 48000
DEFAULT_CHANNELS = 2


@dataclass
class HostAPIInfo:
    index: int
    name: str
    priority: int          # 0 = beste
    default_output: int


@dataclass
class DeviceInfo:
    index: int
    name: str
    hostapi: str
    hostapi_index: int
    max_output_channels: int
    default_samplerate: float
    default_low_output_latency: float
    default_high_output_latency: float

    @property
    def label(self) -> str:
        return f"[{self.hostapi}] {self.name}"


@dataclass
class EngineConfig:
    device_index: Optional[int] = None    # None → beste automatische Wahl
    samplerate: int = DEFAULT_SAMPLERATE
    blocksize: int = DEFAULT_BLOCKSIZE
    channels: int = DEFAULT_CHANNELS
    # WASAPI exclusive-Modus (falls WASAPI gewählt). Muss bei ASIO/WDM-KS None sein.
    wasapi_exclusive: bool = True


# Callback-Signatur: outdata (shape [frames, channels], float32), frames, time_info, status → None
CallbackFn = Callable[[np.ndarray, int, object, object], None]


class AudioEngine:
    """Wrapper um sounddevice.OutputStream mit Fallback-Kaskade & Hot-Reload."""

    def __init__(self, callback: CallbackFn, config: Optional[EngineConfig] = None):
        self._user_callback = callback
        self._config = config or EngineConfig()
        self._stream: Optional[sd.OutputStream] = None
        self._lock = threading.Lock()
        self._underruns = 0
        self._last_status_str: str = ""

    # ---- Enumeration ---------------------------------------------------

    @staticmethod
    def list_hostapis() -> list[HostAPIInfo]:
        out: list[HostAPIInfo] = []
        for i, ha in enumerate(sd.query_hostapis()):
            name = ha["name"]
            priority = next(
                (p for p, key in enumerate(_HOSTAPI_PRIORITY) if key.lower() in name.lower()),
                len(_HOSTAPI_PRIORITY),
            )
            out.append(HostAPIInfo(
                index=i,
                name=name,
                priority=priority,
                default_output=ha["default_output_device"],
            ))
        out.sort(key=lambda h: h.priority)
        return out

    @staticmethod
    def list_output_devices() -> list[DeviceInfo]:
        infos: list[DeviceInfo] = []
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] <= 0:
                continue
            ha = sd.query_hostapis(d["hostapi"])
            infos.append(DeviceInfo(
                index=i,
                name=d["name"],
                hostapi=ha["name"],
                hostapi_index=d["hostapi"],
                max_output_channels=d["max_output_channels"],
                default_samplerate=d["default_samplerate"],
                default_low_output_latency=d.get("default_low_output_latency", 0.0),
                default_high_output_latency=d.get("default_high_output_latency", 0.0),
            ))
        # Sortiere nach HostAPI-Priorität, dann alphabetisch
        prio_map = {h.name: h.priority for h in AudioEngine.list_hostapis()}
        infos.sort(key=lambda d: (prio_map.get(d.hostapi, 99), d.name))
        return infos

    @staticmethod
    def pick_best_device() -> Optional[DeviceInfo]:
        """Wählt automatisch das Output-Device mit bester (=niedrigster Prio) HostAPI."""
        devs = AudioEngine.list_output_devices()
        if not devs:
            return None
        # Für den besten HostAPI: nimm dessen Default-Output, sonst erstes passendes
        best_hostapi = devs[0].hostapi_index
        default_idx = sd.query_hostapis(best_hostapi)["default_output_device"]
        for d in devs:
            if d.index == default_idx:
                return d
        return devs[0]

    # ---- Stream-Lifecycle ---------------------------------------------

    def start(self) -> None:
        with self._lock:
            self._stop_locked()
            self._open_locked()

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def restart(self, config: Optional[EngineConfig] = None) -> None:
        with self._lock:
            if config is not None:
                self._config = config
            self._stop_locked()
            self._open_locked()

    @property
    def config(self) -> EngineConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._stream is not None and self._stream.active

    @property
    def current_latency_ms(self) -> float:
        if self._stream is None:
            return 0.0
        # sounddevice OutputStream.latency ist float (Sekunden)
        lat = self._stream.latency
        if isinstance(lat, (tuple, list)):
            lat = lat[0]
        return float(lat) * 1000.0

    @property
    def underruns(self) -> int:
        return self._underruns

    @property
    def last_status(self) -> str:
        return self._last_status_str

    # ---- Internal -----------------------------------------------------

    def _stop_locked(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _open_locked(self) -> None:
        cfg = self._config
        device = cfg.device_index if cfg.device_index is not None else self._auto_device_index()
        extra: Optional[object] = self._extra_settings_for(device, cfg)

        # Erster Versuch mit gewünschten Settings, dann Fallback-Kaskade bei Fehler.
        for attempt in self._fallback_configs(device, cfg, extra):
            dev_idx, blocksize, sr, exsettings = attempt
            try:
                self._stream = sd.OutputStream(
                    device=dev_idx,
                    samplerate=sr,
                    blocksize=blocksize,
                    channels=cfg.channels,
                    dtype="float32",
                    latency="low",
                    callback=self._pa_callback,
                    extra_settings=exsettings,
                )
                self._stream.start()
                # Merke effektiv verwendete Werte
                self._config = EngineConfig(
                    device_index=dev_idx,
                    samplerate=int(self._stream.samplerate),
                    blocksize=self._stream.blocksize or blocksize,
                    channels=cfg.channels,
                    wasapi_exclusive=cfg.wasapi_exclusive,
                )
                self._underruns = 0
                self._last_status_str = ""
                return
            except Exception as exc:
                self._last_status_str = f"Fallback: {exc}"
                self._stream = None
                continue

        raise RuntimeError(f"Kein Audio-Device konnte geöffnet werden. Letzter Status: {self._last_status_str}")

    def _auto_device_index(self) -> int:
        best = self.pick_best_device()
        if best is None:
            raise RuntimeError("Kein Output-Device gefunden.")
        return best.index

    def _extra_settings_for(self, device_index: int, cfg: EngineConfig) -> Optional[object]:
        try:
            d = sd.query_devices(device_index)
            ha_name = sd.query_hostapis(d["hostapi"])["name"]
        except Exception:
            return None
        if "WASAPI" in ha_name and cfg.wasapi_exclusive:
            try:
                return sd.WasapiSettings(exclusive=True)
            except Exception:
                return None
        if "ASIO" in ha_name:
            try:
                return sd.AsioSettings(channel_selectors=list(range(cfg.channels)))
            except Exception:
                return None
        return None

    def _fallback_configs(self, device: int, cfg: EngineConfig, extra: Optional[object]):
        """Iteriert Kandidaten: (device, blocksize, samplerate, extra_settings)."""
        # 1) genau wie gewünscht
        yield device, cfg.blocksize, cfg.samplerate, extra
        # 2) blocksize auto (0) — PortAudio bestimmt selbst
        yield device, 0, cfg.samplerate, extra
        # 3) Device-Default-Samplerate
        try:
            d_sr = int(sd.query_devices(device)["default_samplerate"])
            if d_sr and d_sr != cfg.samplerate:
                yield device, cfg.blocksize, d_sr, extra
                yield device, 0, d_sr, extra
        except Exception:
            pass
        # 4) ohne extra_settings (WASAPI exclusive → shared)
        if extra is not None:
            yield device, cfg.blocksize, cfg.samplerate, None
            yield device, 0, cfg.samplerate, None
        # 5) System-Default
        try:
            yield None, cfg.blocksize, cfg.samplerate, None
            yield None, 0, cfg.samplerate, None
        except Exception:
            pass

    # PortAudio-Callback (auf Audio-Thread; MUSS billig sein)
    def _pa_callback(self, outdata, frames, time_info, status) -> None:
        if status:
            # sd.CallbackFlags → Truthy bei Under-/Overrun. Zähler nur bei tatsächlichem Underflow.
            if getattr(status, "output_underflow", False):
                self._underruns += 1
            self._last_status_str = str(status)
        try:
            self._user_callback(outdata, frames, time_info, status)
        except Exception as exc:
            # Nie den PortAudio-Thread crashen lassen — mit Stille auffüllen.
            outdata.fill(0.0)
            self._last_status_str = f"Callback-Fehler: {exc}"
