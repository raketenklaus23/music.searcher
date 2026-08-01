"""Python <-> QML Bridge: Library-Model, Job-Runner, Settings.

Wir nutzen ein einfaches QAbstractListModel für die Library, damit QML per
Delegate direkt drauf zugreifen kann. Drag&Drop nimmt QUrl-Listen entgegen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    Signal,
    Slot,
    Property,
    QByteArray,
    QUrl,
)

from ..core.jobs import JobRunner
from ..core.library import Library


class LibraryModel(QAbstractListModel):
    IdRole = Qt.UserRole + 1
    TitleRole = Qt.UserRole + 2
    ArtistRole = Qt.UserRole + 3
    AlbumRole = Qt.UserRole + 4
    YearRole = Qt.UserRole + 5
    GenreRole = Qt.UserRole + 6
    DurationRole = Qt.UserRole + 7
    BpmRole = Qt.UserRole + 8
    KeyRole = Qt.UserRole + 9
    LufsRole = Qt.UserRole + 10
    StatusRole = Qt.UserRole + 11
    PathRole = Qt.UserRole + 12

    def __init__(self, library: Library, parent: QObject | None = None):
        super().__init__(parent)
        self.library = library
        self._rows: list[Any] = []
        self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        self._rows = self.library.all_tracks()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: D401
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        t = self._rows[index.row()]
        if role == self.IdRole:
            return t.id
        if role == self.TitleRole:
            return t.title or ""
        if role == self.ArtistRole:
            return t.artist or ""
        if role == self.AlbumRole:
            return t.album or ""
        if role == self.YearRole:
            return t.year or 0
        if role == self.GenreRole:
            return t.genre or ""
        if role == self.DurationRole:
            return t.duration_ms or 0
        if role == self.BpmRole:
            return round(t.bpm, 1) if t.bpm else 0.0
        if role == self.KeyRole:
            return t.key or ""
        if role == self.LufsRole:
            return round(t.lufs, 1) if t.lufs is not None else 0.0
        if role == self.StatusRole:
            return t.status
        if role == self.PathRole:
            return t.path
        return None

    def roleNames(self) -> dict:  # noqa: D401
        return {
            self.IdRole: QByteArray(b"trackId"),
            self.TitleRole: QByteArray(b"title"),
            self.ArtistRole: QByteArray(b"artist"),
            self.AlbumRole: QByteArray(b"album"),
            self.YearRole: QByteArray(b"year"),
            self.GenreRole: QByteArray(b"genre"),
            self.DurationRole: QByteArray(b"durationMs"),
            self.BpmRole: QByteArray(b"bpm"),
            self.KeyRole: QByteArray(b"musicalKey"),
            self.LufsRole: QByteArray(b"lufs"),
            self.StatusRole: QByteArray(b"status"),
            self.PathRole: QByteArray(b"path"),
        }

    def update_track(self, track_id: int) -> None:
        for i, t in enumerate(self._rows):
            if t.id == track_id:
                fresh = self.library.get_track(track_id)
                if fresh is not None:
                    self._rows[i] = fresh
                    idx = self.index(i, 0)
                    self.dataChanged.emit(idx, idx)
                return


class Backend(QObject):
    """Fassade für QML — kapselt Library, Model, Jobs."""

    trackImported = Signal(int)
    queueChanged = Signal(int)
    statusMessage = Signal(str)

    def __init__(self, library: Library, parent: QObject | None = None):
        super().__init__(parent)
        self._library = library
        self._model = LibraryModel(library, self)
        self._jobs = JobRunner(library)
        self._jobs.trackAnalyzed.connect(self._on_analyzed)
        self._jobs.queueChanged.connect(self.queueChanged)

    @Property(QObject, constant=True)
    def libraryModel(self) -> LibraryModel:  # noqa: N802 (QML style)
        return self._model

    def _urls_to_paths(self, urls: list) -> list[Path]:
        paths: list[Path] = []
        for u in urls:
            if isinstance(u, QUrl):
                p = Path(u.toLocalFile())
            else:
                s = str(u)
                if s.startswith("file:///"):
                    s = QUrl(s).toLocalFile()
                p = Path(s)
            if p.exists():
                paths.append(p)
        return paths

    @Slot(list)
    def importUrls(self, urls: list) -> None:  # noqa: N802
        """Drag&Drop-Handler: bekommt Liste von QUrl."""
        paths = self._urls_to_paths(urls)
        if not paths:
            return
        ids = self._library.import_paths(paths, copy=True)
        self._model.refresh()
        for tid in ids:
            self.trackImported.emit(tid)
            t = self._library.get_track(tid)
            if t is not None:
                self._jobs.enqueue(tid, Path(t.path))
        self.statusMessage.emit(f"{len(ids)} Track(s) importiert, Analyse läuft…")

    @Slot(list, str)
    def importUrlsToDeck(self, urls: list, deck_id: str) -> None:  # noqa: N802
        """Import + sofort ersten Track auf angegebenes Deck laden."""
        paths = self._urls_to_paths(urls)
        if not paths:
            return
        ids = self._library.import_paths(paths, copy=True)
        if not ids:
            return
        self._model.refresh()
        for tid in ids:
            self.trackImported.emit(tid)
            t = self._library.get_track(tid)
            if t is not None:
                self._jobs.enqueue(tid, Path(t.path))
        deck = getattr(self._player_bridge, f"deck{deck_id.upper()}", None)
        if deck is not None:
            deck.loadTrack(ids[0])
        self.statusMessage.emit(
            f"{len(ids)} Track(s) importiert, Deck {deck_id.upper()} geladen."
        )

    @Slot()
    def reanalyzePending(self) -> None:  # noqa: N802
        n = self._jobs.enqueue_pending()
        self.statusMessage.emit(f"Analyse für {n} Track(s) gestartet.")

    @Slot(int)
    def deleteTrack(self, track_id: int) -> None:  # noqa: N802
        self._library.delete_track(track_id, delete_file=False)
        self._model.refresh()

    def _on_analyzed(self, track_id: int) -> None:
        self._model.update_track(track_id)
