"""Background-Job-Queue via QThreadPool. Analyse läuft ohne GUI zu blockieren."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from .analyzer import analyze
from .library import Library


class AnalyzeSignals(QObject):
    started = Signal(int)                     # track_id
    finished = Signal(int, object)            # track_id, AnalysisResult
    failed = Signal(int, str)                 # track_id, error


class AnalyzeJob(QRunnable):
    def __init__(self, track_id: int, path: Path, signals: AnalyzeSignals):
        super().__init__()
        self.track_id = track_id
        self.path = path
        self.signals = signals

    @Slot()
    def run(self) -> None:
        self.signals.started.emit(self.track_id)
        try:
            result = analyze(self.path)
            self.signals.finished.emit(self.track_id, result)
        except Exception as exc:
            self.signals.failed.emit(self.track_id, str(exc))


class JobRunner(QObject):
    """Verteilt Analyse-Jobs auf einen ThreadPool und hält Ergebnisse mit Library synchron."""

    trackAnalyzed = Signal(int)   # UI-Signal wenn ein Track fertig ist
    queueChanged = Signal(int)    # Anzahl offener Jobs

    def __init__(self, library: Library, max_workers: Optional[int] = None):
        super().__init__()
        self.library = library
        self.pool = QThreadPool.globalInstance()
        if max_workers:
            self.pool.setMaxThreadCount(max_workers)
        self.signals = AnalyzeSignals()
        self.signals.started.connect(self._on_started)
        self.signals.finished.connect(self._on_finished)
        self.signals.failed.connect(self._on_failed)
        self._pending = 0

    def enqueue(self, track_id: int, path: Path) -> None:
        self._pending += 1
        self.queueChanged.emit(self._pending)
        job = AnalyzeJob(track_id, Path(path), self.signals)
        self.pool.start(job)

    def enqueue_pending(self) -> int:
        """Analysiere alle Tracks mit status='pending'."""
        count = 0
        for t in self.library.pending_analysis():
            self.enqueue(t.id, Path(t.path))
            count += 1
        return count

    @Slot(int)
    def _on_started(self, track_id: int) -> None:
        self.library.update_status(track_id, "analyzing")

    @Slot(int, object)
    def _on_finished(self, track_id: int, result) -> None:
        self.library.update_analysis(
            track_id,
            bpm=result.bpm,
            key=result.key,
            lufs=result.lufs,
            energy=result.energy,
        )
        # Beatgrid persistieren
        if result.beatgrid is not None:
            self.library.save_beatgrid(
                track_id,
                beats_sec=result.beatgrid.beats_sec,
                downbeat_ms=result.beatgrid.downbeat_ms,
                bpm=result.beatgrid.bpm,
                mode=result.beatgrid.mode.value if hasattr(result.beatgrid.mode, "value") else str(result.beatgrid.mode),
            )
        # Vocal-Regionen
        if result.vocal_regions:
            self.library.replace_vocal_regions(track_id, result.vocal_regions, source="heuristic")
        # Auto-Cues
        for c in result.cues:
            self.library.upsert_cue(
                track_id,
                idx=c.idx,
                position_ms=c.position_ms,
                label=c.label,
                color=c.color,
                source="auto",
                loop_length_beats=c.loop_length_beats,
            )
        # Auto-Loops
        for l in result.loops:
            self.library.upsert_loop(
                track_id,
                idx=l.idx,
                start_ms=l.start_ms,
                length_ms=l.length_ms,
                beats=l.beats,
                label=l.label,
                source="auto",
            )
        self._pending = max(0, self._pending - 1)
        self.queueChanged.emit(self._pending)
        self.trackAnalyzed.emit(track_id)

    @Slot(int, str)
    def _on_failed(self, track_id: int, err: str) -> None:
        self.library.update_status(track_id, "error", err)
        self._pending = max(0, self._pending - 1)
        self.queueChanged.emit(self._pending)
        self.trackAnalyzed.emit(track_id)
