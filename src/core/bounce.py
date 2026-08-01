"""Bounce-Modul: offline Compressor-Rendering (A10 „Vinyl-Push").

Modi:
  - NEW_FILE       : rendert in `<file>.pushed.<ext>` (neuer Track in Library)
  - REPLACE        : Original ueberschreiben, Backup als `<file>.original.<ext>`
  - CANCEL         : nichts tun (der Dialog nutzt das)

Wird vom `SavePushedDialog` (QML) aus der DeckBridge angetriggert. Der Deck-eigene
A10-Live-Wert wird als Push-Intensitaet uebernommen (0..1).
"""
from __future__ import annotations

import shutil
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from ..audio.effects import A10Compressor


class SavePushedMode(str, Enum):
    NEW_FILE = "new_file"
    REPLACE = "replace"
    CANCEL = "cancel"


def _pushed_path(src: Path) -> Path:
    return src.with_suffix(".pushed" + src.suffix)


def _backup_path(src: Path) -> Path:
    return src.with_suffix(".original" + src.suffix)


def render_pushed(src: Path, push: float, out: Path,
                  block: int = 65536) -> tuple[bool, Optional[str]]:
    """Rendert `src` durch den A10-Compressor mit Intensitaet `push` (0..1)
    in Datei `out`. Blockweise, damit auch grosse Files gehen.
    """
    src = Path(src)
    out = Path(out)
    try:
        with sf.SoundFile(str(src)) as f_in:
            sr = f_in.samplerate
            ch = f_in.channels
            a10 = A10Compressor(sr)
            a10.set_value(push)
            with sf.SoundFile(
                str(out), mode="w", samplerate=sr, channels=ch, subtype=f_in.subtype,
            ) as f_out:
                while True:
                    data = f_in.read(block, dtype="float32", always_2d=True)
                    if data.size == 0:
                        break
                    y = a10.process(data)
                    f_out.write(y)
        return True, None
    except Exception as exc:
        return False, str(exc)


def save_pushed(
    src: Path,
    push: float,
    mode: SavePushedMode,
) -> tuple[bool, Optional[Path], Optional[str]]:
    """Fuehrt Save-Pushed gemaess `mode` durch.

    Returns: (ok, produced_path, error). `produced_path` ist bei NEW_FILE der
    Pfad der neuen Datei, bei REPLACE der Original-Pfad.
    """
    src = Path(src)
    if not src.exists():
        return False, None, f"Quelle nicht gefunden: {src}"
    if mode == SavePushedMode.CANCEL:
        return False, None, "abgebrochen"
    if push <= 0.0:
        return False, None, "Push-Wert ist 0 — nichts zu tun"

    if mode == SavePushedMode.NEW_FILE:
        out = _pushed_path(src)
        n = 1
        while out.exists():
            out = src.with_suffix(f".pushed{n}" + src.suffix)
            n += 1
        ok, err = render_pushed(src, push, out)
        if not ok:
            return False, None, err
        return True, out, None

    if mode == SavePushedMode.REPLACE:
        bak = _backup_path(src)
        if not bak.exists():
            try:
                shutil.copy2(src, bak)
            except Exception as exc:
                return False, None, f"Backup fehlgeschlagen: {exc}"
        tmp = src.with_suffix(".pushed.tmp" + src.suffix)
        ok, err = render_pushed(src, push, tmp)
        if not ok:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            return False, None, err
        try:
            tmp.replace(src)
        except Exception as exc:
            return False, None, f"Ueberschreiben fehlgeschlagen: {exc}"
        return True, src, None

    return False, None, f"unbekannter Modus: {mode}"
