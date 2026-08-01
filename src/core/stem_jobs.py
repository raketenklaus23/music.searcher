"""Background-Jobs für Demucs-Stem-Separation.

Läuft im QThreadPool, damit die GUI nicht blockiert. Nach Abschluss:
  * Stem-Pfade in Library persistieren (stems_meta)
  * Vocal-Regionen präzise aus vocals-Stem berechnen und in DB ersetzen
    (source='demucs' — löst die heuristischen aus Phase 3 ab)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from .library import DEFAULT_STEMS_DIR, Library
from .stems import (
    StemModel,
    StemResult,
    is_demucs_available,
    separate,
    stem_output_path,
    stem_paths_to_json,
    vocal_regions_from_stem,
)


class StemSignals(QObject):
    started = Signal(int, str)                 # track_id, model
    progress = Signal(int, str, str)           # track_id, model, line
    finished = Signal(int, str, object)        # track_id, model, StemResult
    failed = Signal(int, str, str)             # track_id, model, error


class SeparateJob(QRunnable):
    def __init__(self, track_id: int, path: Path, model: StemModel,
                 output_root: Path, signals: StemSignals):
        super().__init__()
        self.track_id = track_id
        self.path = path
        self.model = model
        self.output_root = output_root
        self.signals = signals

    @Slot()
    def run(self) -> None:
        self.signals.started.emit(self.track_id, self.model.value)
        try:
            def cb(line: str) -> None:
                self.signals.progress.emit(self.track_id, self.model.value, line)
            result = separate(self.path, self.output_root, self.model, progress_cb=cb)
            self.signals.finished.emit(self.track_id, self.model.value, result)
        except Exception as exc:
            self.signals.failed.emit(self.track_id, self.model.value, str(exc))


class StemRunner(QObject):
    """Verteilt Demucs-Jobs und synchronisiert Library."""

    stemStarted = Signal(int, str)
    stemProgress = Signal(int, str, str)
    stemFinished = Signal(int, str)
    stemFailed = Signal(int, str, str)
    queueChanged = Signal(int)

    def __init__(self, library: Library, output_root: Optional[Path] = None,
                 max_workers: int = 1, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.library = library
        # Demucs braucht viel RAM/GPU — nie parallel
        self.output_root = output_root or DEFAULT_STEMS_DIR
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max_workers)
        self.signals = StemSignals()
        self.signals.started.connect(self._on_started)
        self.signals.progress.connect(self._on_progress)
        self.signals.finished.connect(self._on_finished)
        self.signals.failed.connect(self._on_failed)
        self._pending = 0

    def is_available(self) -> bool:
        return is_demucs_available()

    def enqueue(self, track_id: int, path: Path, model: StemModel) -> None:
        # Ausgabepfad pro Track fest (überschreiben ok, Demucs ist deterministisch)
        out = stem_output_path(self.output_root.parent, track_id, model).parent
        out.mkdir(parents=True, exist_ok=True)
        self._pending += 1
        self.queueChanged.emit(self._pending)
        job = SeparateJob(track_id, Path(path), model, out, self.signals)
        self.pool.start(job)

    @Slot(int, str)
    def _on_started(self, track_id: int, model: str) -> None:
        self.stemStarted.emit(track_id, model)

    @Slot(int, str, str)
    def _on_progress(self, track_id: int, model: str, line: str) -> None:
        self.stemProgress.emit(track_id, model, line)

    @Slot(int, str, object)
    def _on_finished(self, track_id: int, model: str, result: StemResult) -> None:
        self.library.upsert_stems_meta(track_id, model, stem_paths_to_json(result.stem_paths))
        # Präzise Vocal-Regions ersetzen
        vocals_wav = result.stem_paths.get("vocals")
        if vocals_wav:
            try:
                regions = vocal_regions_from_stem(Path(vocals_wav))
                if regions:
                    self.library.replace_vocal_regions(track_id, regions, source="demucs")
            except Exception as exc:
                print(f"[Stems] Vocal-Region-Extract failed für Track {track_id}: {exc}")
        self._pending = max(0, self._pending - 1)
        self.queueChanged.emit(self._pending)
        self.stemFinished.emit(track_id, model)

    @Slot(int, str, str)
    def _on_failed(self, track_id: int, model: str, err: str) -> None:
        self._pending = max(0, self._pending - 1)
        self.queueChanged.emit(self._pending)
        self.stemFailed.emit(track_id, model, err)
