"""Demucs-Stems (offline).

Zwei Modelle wählbar:
  - htdemucs      → 4 Stems (drums, bass, other, vocals)
  - htdemucs_6s   → 6 Stems (drums, bass, other, vocals, guitar, piano)

Wir rufen den `demucs`-CLI-Wrapper via subprocess auf. Das hält den PyTorch-Import
aus dem Haupt-Prozess (kein Startup-Slowdown, kein CUDA-Init bevor gebraucht).
GPU wird automatisch verwendet wenn verfügbar.

Ergebnis-Pfade werden in `stems_meta.stem_paths_json` gespeichert.
Zusätzlich ersetzt der `vocals`-Stem die heuristischen `vocal_regions`
(source='demucs' — precise timing via RMS-Threshold).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np


class StemModel(str, Enum):
    HTDEMUCS = "htdemucs"           # 4 Stems
    HTDEMUCS_6S = "htdemucs_6s"     # 6 Stems


# Stems je Modell (Reihenfolge = Demucs-Output-Ordner)
STEM_NAMES = {
    StemModel.HTDEMUCS: ["drums", "bass", "other", "vocals"],
    StemModel.HTDEMUCS_6S: ["drums", "bass", "other", "vocals", "guitar", "piano"],
}


@dataclass
class StemResult:
    model: StemModel
    stem_paths: dict[str, str]   # stem_name → wav-path
    output_dir: Path


def is_demucs_available() -> bool:
    """True wenn `python -m demucs` importierbar ist."""
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import demucs.separate; print('ok')"],
            capture_output=True, text=True, timeout=8,
        )
        return r.returncode == 0 and "ok" in r.stdout
    except Exception:
        return False


def separate(
    audio_path: Path,
    output_root: Path,
    model: StemModel = StemModel.HTDEMUCS,
    device: Optional[str] = None,       # 'cuda' | 'cpu' | None (auto)
    progress_cb=None,                   # callable(line: str) → optional
) -> StemResult:
    """Ruft Demucs-CLI auf und gibt Stem-Pfade zurück.

    Ordner-Struktur nach Demucs:
        output_root/<model>/<track-stem>/<name>.wav
    """
    audio_path = Path(audio_path)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    args = [
        sys.executable, "-m", "demucs.separate",
        "-n", model.value,
        "-o", str(output_root),
        "--filename", "{track}/{stem}.{ext}",
    ]
    if device:
        args += ["-d", device]
    args.append(str(audio_path))

    # Streaming-Output für Progress
    proc = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if progress_cb:
            progress_cb(line.rstrip())
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"demucs exit code {ret}")

    # Ergebnisordner: output_root/<model>/<track_stem>/
    track_out = output_root / model.value / audio_path.stem
    if not track_out.is_dir():
        raise RuntimeError(f"Erwarteter Demucs-Output nicht gefunden: {track_out}")

    stem_paths: dict[str, str] = {}
    for name in STEM_NAMES[model]:
        wav = track_out / f"{name}.wav"
        if wav.exists():
            stem_paths[name] = str(wav)
    if not stem_paths:
        raise RuntimeError(f"Keine Stem-WAVs im Ausgabe-Ordner: {track_out}")

    return StemResult(model=model, stem_paths=stem_paths, output_dir=track_out)


# -----------------------------------------------------------------------
# Vocal-Regionen aus Vocals-Stem (präzise, ersetzt heuristic)
# -----------------------------------------------------------------------

def vocal_regions_from_stem(
    vocals_wav: Path,
    min_region_ms: int = 800,
    merge_gap_ms: int = 250,
) -> list[tuple[int, int, float]]:
    """Extrahiert Vocal-Regionen aus dem isolierten Vocals-Stem.

    Deutlich präziser als die Heuristik in vocals.py, weil Instrumente bereits
    entfernt sind.
    """
    import soundfile as sf

    y, sr = sf.read(str(vocals_wav), always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    y = y.astype(np.float32, copy=False)

    hop = 512
    n_frames = 1 + (len(y) - 2048) // hop if len(y) >= 2048 else 0
    if n_frames <= 0:
        return []

    # RMS pro Frame
    rms = np.empty(n_frames, dtype=np.float32)
    for i in range(n_frames):
        window = y[i * hop : i * hop + 2048]
        rms[i] = float(np.sqrt(np.mean(window ** 2) + 1e-12))

    frame_ms = int(round(hop / sr * 1000.0))

    # Adaptive Threshold: mittleres Rauschniveau + 3× MAD
    med = float(np.median(rms))
    mad = float(np.median(np.abs(rms - med)) + 1e-9)
    thr = med + 3.0 * mad
    active = rms > thr

    regions: list[tuple[int, int, float]] = []
    i = 0
    n = len(active)
    while i < n:
        if not active[i]:
            i += 1
            continue
        j = i
        while j < n and active[j]:
            j += 1
        start_ms = i * frame_ms
        end_ms = j * frame_ms
        conf = float(np.mean(rms[i:j]) / (np.max(rms) + 1e-9))
        regions.append((start_ms, end_ms, min(1.0, conf)))
        i = j

    # Kurze Lücken zusammenführen
    merged: list[tuple[int, int, float]] = []
    for s, e, c in regions:
        if merged and s - merged[-1][1] <= merge_gap_ms:
            ps, pe, pc = merged[-1]
            merged[-1] = (ps, e, max(pc, c))
        else:
            merged.append((s, e, c))
    return [(s, e, c) for s, e, c in merged if (e - s) >= min_region_ms]


# -----------------------------------------------------------------------
# Cache-Management
# -----------------------------------------------------------------------

def stem_output_path(app_data_dir: Path, track_id: int, model: StemModel) -> Path:
    return app_data_dir / "stems" / str(track_id) / model.value


def remove_stems(app_data_dir: Path, track_id: int, model: Optional[StemModel] = None) -> None:
    base = app_data_dir / "stems" / str(track_id)
    if not base.exists():
        return
    if model:
        target = base / model.value
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    else:
        shutil.rmtree(base, ignore_errors=True)


def stem_paths_to_json(paths: dict[str, str]) -> str:
    return json.dumps(paths, ensure_ascii=False)


def stem_paths_from_json(s: str) -> dict[str, str]:
    try:
        return json.loads(s)
    except Exception:
        return {}
