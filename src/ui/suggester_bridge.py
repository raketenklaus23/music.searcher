"""QML-Bridge fuer Suggester + Set-Analyse + Online-Lookup (Phase 5).

Wird von `main.py` als eigenes `backend.suggester`-Objekt exportiert und in
den entsprechenden QML-Dialogen genutzt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ..core.library import Library
from ..core.online_lookup import discogs_search, hybrid_search, musicbrainz_search
from ..core.set_analysis import (
    SetFingerprint,
    analyze_set_file,
    build_playlist_from_fingerprint,
)
from ..core.suggester import GenreCurve, build_genre_playlist, find_similar


def _track_summary(library: Library, track_id: int) -> dict:
    t = library.get_track(track_id)
    if not t:
        return {"id": track_id, "title": "?", "artist": "?"}
    return {
        "id": t.id,
        "title": t.title or Path(t.path).stem,
        "artist": t.artist or "",
        "bpm": round(t.bpm, 1) if t.bpm else 0.0,
        "key": t.key or "",
        "energy": round(t.energy, 2) if t.energy is not None else 0.0,
    }


class _SetAnalyzeJob(QRunnable):
    def __init__(self, bridge: "SuggesterBridge", path: str) -> None:
        super().__init__()
        self.bridge = bridge
        self.path = path

    def run(self) -> None:
        try:
            fp = analyze_set_file(Path(self.path))
            picks = build_playlist_from_fingerprint(self.bridge._library, fp)
            summaries = [_track_summary(self.bridge._library, i) for i in picks]
            self.bridge.setAnalyzed.emit({
                "duration": fp.duration_s,
                "chunks": len(fp.chunks),
                "picks": summaries,
                "bpm_curve": fp.bpm_curve,
                "energy_curve": fp.energy_curve,
            })
        except Exception as exc:
            self.bridge.setAnalyzeFailed.emit(str(exc))


class SuggesterBridge(QObject):
    """API fuer QML: findSimilar, buildGenre, analyzeSet, onlineLookup."""

    setAnalyzed = Signal("QVariant")
    setAnalyzeFailed = Signal(str)
    onlineHits = Signal(str, "QVariant")   # source, list-of-hits

    def __init__(self, library: Library, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._library = library
        self._pool = QThreadPool.globalInstance()

    # ---- Similar Tracks --------------------------------------------------

    @Slot(int, int, float, result="QVariant")
    def findSimilar(self, ref_id: int, limit: int, bpm_tol: float) -> list[dict]:
        tol = bpm_tol if bpm_tol > 0 else None
        results = find_similar(self._library, ref_id, limit=limit, bpm_tolerance=tol)
        out: list[dict] = []
        for s in results:
            summary = _track_summary(self._library, s.track_id)
            summary["score"] = round(s.score, 3)
            summary["reason"] = s.reason
            out.append(summary)
        return out

    # ---- Genre-Playlist --------------------------------------------------

    @Slot("QVariantList", int, float, float, float, float, result="QVariant")
    def buildGenrePlaylist(
        self, genres, length_min, bpm_start, bpm_peak, bpm_end, avg_track_min,
    ) -> list[dict]:
        curve = GenreCurve(
            length_min=int(length_min),
            bpm_start=float(bpm_start),
            bpm_peak=float(bpm_peak),
            bpm_end=float(bpm_end),
        )
        ids = build_genre_playlist(
            self._library,
            [str(g) for g in genres],
            curve,
            avg_track_min=float(avg_track_min) if avg_track_min > 0 else 4.0,
        )
        return [_track_summary(self._library, i) for i in ids]

    # ---- Set-Fingerprint -------------------------------------------------

    @Slot(str)
    def analyzeSet(self, path: str) -> None:
        job = _SetAnalyzeJob(self, path)
        self._pool.start(job)

    # ---- Online-Lookup ---------------------------------------------------

    @Slot(int, str)
    def onlineLookup(self, track_id: int, mode: str) -> None:
        t = self._library.get_track(track_id)
        if not t:
            self.onlineHits.emit(mode, [])
            return
        artist = t.artist or ""
        title = t.title or Path(t.path).stem
        if mode == "musicbrainz":
            hits = musicbrainz_search(self._library, artist, title)
        elif mode == "discogs":
            hits = discogs_search(self._library, artist, title)
        else:
            hits = hybrid_search(self._library, artist, title)
        payload: list[dict] = []
        for h in hits:
            payload.append({
                "source": h.source,
                "title": h.title,
                "artist": h.artist,
                "album": h.album or "",
                "year": h.year or 0,
                "genres": h.genres,
                "styles": h.styles,
                "score": h.score,
            })
        self.onlineHits.emit(mode, payload)

    @Slot(int, str, str, "QVariant", str)
    def applyOnlineHit(
        self, track_id: int, genre: str, album: str, year: Any, source: str,
    ) -> bool:
        """Uebernimmt Genre/Album/Year in die Library (nur nicht-leere Felder)."""
        try:
            year_val = int(year) if year else None
        except (TypeError, ValueError):
            year_val = None
        try:
            self._library._conn.execute(
                """UPDATE tracks
                     SET genre = COALESCE(NULLIF(?, ''), genre),
                         album = COALESCE(NULLIF(?, ''), album),
                         year  = COALESCE(?, year)
                   WHERE id = ?""",
                (genre, album, year_val, track_id),
            )
            self._library._conn.commit()
            return True
        except Exception:
            return False
