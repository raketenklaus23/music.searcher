"""Library-Verwaltung: SQLite CRUD, Import (flach), Metadaten-Extraktion.

Die Library ist bewusst flach — beim Import werden Files entweder nach
`data/music/` kopiert (Default) oder in-place referenziert (Setting).
Playlists/Folder entstehen erst *aus* der flachen Library heraus.
"""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import mutagen

try:
    from platformdirs import user_data_dir
    _APP_DATA = Path(user_data_dir("MusicSearcher", "MMM"))
except ImportError:
    # Fallback wenn platformdirs (noch) nicht installiert ist
    _APP_DATA = Path(__file__).resolve().parents[2] / "data"

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
DEFAULT_DB_PATH = _APP_DATA / "library.db"
DEFAULT_MUSIC_DIR = _APP_DATA / "music"
DEFAULT_CACHE_DIR = _APP_DATA / "cache"
DEFAULT_STEMS_DIR = _APP_DATA / "stems"

SUPPORTED_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}


@dataclass
class Track:
    id: int
    path: str
    title: Optional[str]
    artist: Optional[str]
    album: Optional[str]
    year: Optional[int]
    genre: Optional[str]
    duration_ms: Optional[int]
    bpm: Optional[float]
    key: Optional[str]
    lufs: Optional[float]
    status: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Track":
        return cls(
            id=row["id"],
            path=row["path"],
            title=row["title"],
            artist=row["artist"],
            album=row["album"],
            year=row["year"],
            genre=row["genre"],
            duration_ms=row["duration_ms"],
            bpm=row["bpm"],
            key=row["key"],
            lufs=row["lufs"],
            status=row["status"],
        )


class Library:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH, music_dir: Path = DEFAULT_MUSIC_DIR):
        self.db_path = db_path
        self.music_dir = music_dir
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        self._conn.executescript(sql)
        self._conn.commit()

    # ---- Import ---------------------------------------------------------

    def import_file(self, src: Path, copy: bool = True) -> Optional[int]:
        """Fügt eine Datei zur Library hinzu. Gibt track_id zurück, oder None wenn schon vorhanden."""
        src = Path(src)
        if src.suffix.lower() not in SUPPORTED_EXTS:
            return None
        if not src.is_file():
            return None

        if copy:
            dest = self._unique_dest(self.music_dir / src.name)
            shutil.copy2(src, dest)
            target = dest
        else:
            target = src

        meta = self._read_metadata(target)
        try:
            cur = self._conn.execute(
                """
                INSERT INTO tracks (path, title, artist, album, year, genre,
                                    duration_ms, sample_rate, channels, bitrate, filesize, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    str(target),
                    meta.get("title"),
                    meta.get("artist"),
                    meta.get("album"),
                    meta.get("year"),
                    meta.get("genre"),
                    meta.get("duration_ms"),
                    meta.get("sample_rate"),
                    meta.get("channels"),
                    meta.get("bitrate"),
                    meta.get("filesize"),
                ),
            )
            self._conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            # bereits vorhanden (path UNIQUE)
            return None

    def import_paths(self, paths: Iterable[Path], copy: bool = True) -> list[int]:
        """Importiert eine Liste von Pfaden (auch Ordner, rekursiv)."""
        ids: list[int] = []
        for p in paths:
            p = Path(p)
            if p.is_dir():
                for f in p.rglob("*"):
                    if f.suffix.lower() in SUPPORTED_EXTS:
                        tid = self.import_file(f, copy=copy)
                        if tid is not None:
                            ids.append(tid)
            else:
                tid = self.import_file(p, copy=copy)
                if tid is not None:
                    ids.append(tid)
        return ids

    def _unique_dest(self, dest: Path) -> Path:
        if not dest.exists():
            return dest
        stem, suf = dest.stem, dest.suffix
        n = 1
        while True:
            candidate = dest.with_name(f"{stem} ({n}){suf}")
            if not candidate.exists():
                return candidate
            n += 1

    def _read_metadata(self, path: Path) -> dict:
        info: dict = {"filesize": path.stat().st_size}
        try:
            audio = mutagen.File(path, easy=True)
            if audio is None:
                return info
            info["title"] = self._first(audio.get("title")) or path.stem
            info["artist"] = self._first(audio.get("artist"))
            info["album"] = self._first(audio.get("album"))
            info["genre"] = self._first(audio.get("genre"))
            date = self._first(audio.get("date")) or self._first(audio.get("year"))
            if date:
                try:
                    info["year"] = int(str(date)[:4])
                except ValueError:
                    pass
            if audio.info is not None:
                info["duration_ms"] = int(getattr(audio.info, "length", 0) * 1000)
                info["sample_rate"] = getattr(audio.info, "sample_rate", None)
                info["channels"] = getattr(audio.info, "channels", None)
                info["bitrate"] = getattr(audio.info, "bitrate", None)
        except Exception:
            info.setdefault("title", path.stem)
        return info

    @staticmethod
    def _first(val):
        if val is None:
            return None
        if isinstance(val, list) and val:
            return str(val[0])
        return str(val)

    # ---- Queries --------------------------------------------------------

    def all_tracks(self) -> list[Track]:
        cur = self._conn.execute("SELECT * FROM tracks ORDER BY imported_at DESC")
        return [Track.from_row(r) for r in cur.fetchall()]

    def get_track(self, track_id: int) -> Optional[Track]:
        cur = self._conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        row = cur.fetchone()
        return Track.from_row(row) if row else None

    def pending_analysis(self) -> list[Track]:
        cur = self._conn.execute("SELECT * FROM tracks WHERE status = 'pending'")
        return [Track.from_row(r) for r in cur.fetchall()]

    # ---- Updates --------------------------------------------------------

    def update_status(self, track_id: int, status: str, error_msg: Optional[str] = None) -> None:
        self._conn.execute(
            "UPDATE tracks SET status = ?, error_msg = ? WHERE id = ?",
            (status, error_msg, track_id),
        )
        self._conn.commit()

    def update_analysis(
        self,
        track_id: int,
        bpm: Optional[float] = None,
        key: Optional[str] = None,
        lufs: Optional[float] = None,
        energy: Optional[float] = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE tracks
               SET bpm = COALESCE(?, bpm),
                   key = COALESCE(?, key),
                   lufs = COALESCE(?, lufs),
                   energy = COALESCE(?, energy),
                   status = 'ready',
                   analyzed_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (bpm, key, lufs, energy, track_id),
        )
        self._conn.commit()

    def delete_track(self, track_id: int, delete_file: bool = False) -> None:
        if delete_file:
            row = self._conn.execute("SELECT path FROM tracks WHERE id = ?", (track_id,)).fetchone()
            if row:
                p = Path(row["path"])
                if p.exists() and p.is_relative_to(self.music_dir):
                    p.unlink(missing_ok=True)
        self._conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
