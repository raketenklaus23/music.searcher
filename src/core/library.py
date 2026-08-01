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
    energy: Optional[float]
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
            energy=row["energy"] if "energy" in row.keys() else None,
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
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """Idempotente Migrations für bestehende DBs."""
        self._add_column_if_missing("tracks", "playback_gain_db", "REAL DEFAULT 0.0")
        self._add_column_if_missing("cues", "loop_length_beats", "INTEGER")
        self._add_column_if_missing("beatgrid", "mode", "TEXT DEFAULT 'beat_match'")

    def _add_column_if_missing(self, table: str, column: str, ddl: str) -> None:
        cur = self._conn.execute(f"PRAGMA table_info({table})")
        cols = {r["name"] for r in cur.fetchall()}
        if column not in cols:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

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

    # ---- Playback-Gain (LUFS-Normalize, non-destruktiv) --------------

    def set_playback_gain_db(self, track_id: int, db: float) -> None:
        self._conn.execute(
            "UPDATE tracks SET playback_gain_db = ? WHERE id = ?",
            (float(db), track_id),
        )
        self._conn.commit()

    def get_playback_gain_db(self, track_id: int) -> float:
        row = self._conn.execute(
            "SELECT playback_gain_db FROM tracks WHERE id = ?", (track_id,)
        ).fetchone()
        return float(row["playback_gain_db"]) if row and row["playback_gain_db"] is not None else 0.0

    # ---- Cues --------------------------------------------------------

    def upsert_cue(
        self,
        track_id: int,
        idx: int,
        position_ms: int,
        label: Optional[str] = None,
        color: Optional[str] = None,
        source: str = "auto",
        loop_length_beats: Optional[int] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO cues (track_id, idx, position_ms, label, color, source, loop_length_beats)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id, idx) DO UPDATE SET
                position_ms = excluded.position_ms,
                label       = excluded.label,
                color       = excluded.color,
                source      = excluded.source,
                loop_length_beats = excluded.loop_length_beats
            """,
            (track_id, idx, int(position_ms), label, color, source, loop_length_beats),
        )
        self._conn.commit()

    def delete_cue(self, track_id: int, idx: int) -> None:
        self._conn.execute("DELETE FROM cues WHERE track_id = ? AND idx = ?", (track_id, idx))
        self._conn.commit()

    def get_cues(self, track_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT idx, position_ms, label, color, source, loop_length_beats "
            "FROM cues WHERE track_id = ? ORDER BY idx",
            (track_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    # ---- Loops -------------------------------------------------------

    def upsert_loop(
        self,
        track_id: int,
        idx: int,
        start_ms: int,
        length_ms: int,
        beats: Optional[int] = None,
        label: Optional[str] = None,
        source: str = "auto",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO loops (track_id, idx, start_ms, length_ms, beats, label, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id, idx) DO UPDATE SET
                start_ms  = excluded.start_ms,
                length_ms = excluded.length_ms,
                beats     = excluded.beats,
                label     = excluded.label,
                source    = excluded.source
            """,
            (track_id, idx, int(start_ms), int(length_ms), beats, label, source),
        )
        self._conn.commit()

    def get_loops(self, track_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT idx, start_ms, length_ms, beats, label, source "
            "FROM loops WHERE track_id = ? ORDER BY idx",
            (track_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    # ---- Beatgrid ----------------------------------------------------

    def save_beatgrid(
        self,
        track_id: int,
        beats_sec: list[float],
        downbeat_ms: Optional[int] = None,
        bpm: Optional[float] = None,
        mode: str = "beat_match",
    ) -> None:
        import numpy as np
        blob = np.asarray(beats_sec, dtype=np.float32).tobytes()
        self._conn.execute(
            """
            INSERT INTO beatgrid (track_id, beats_blob, downbeat_ms, bpm, mode)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(track_id) DO UPDATE SET
                beats_blob  = excluded.beats_blob,
                downbeat_ms = excluded.downbeat_ms,
                bpm         = excluded.bpm,
                mode        = excluded.mode
            """,
            (track_id, blob, downbeat_ms, bpm, mode),
        )
        self._conn.commit()

    def get_beatgrid(self, track_id: int) -> Optional[dict]:
        import numpy as np
        row = self._conn.execute("SELECT * FROM beatgrid WHERE track_id = ?", (track_id,)).fetchone()
        if row is None:
            return None
        beats = np.frombuffer(row["beats_blob"], dtype=np.float32).tolist() if row["beats_blob"] else []
        return {
            "beats_sec": beats,
            "downbeat_ms": row["downbeat_ms"],
            "bpm": row["bpm"],
            "mode": row["mode"] if "mode" in row.keys() else "beat_match",
        }

    # ---- Vocal-Regionen ----------------------------------------------

    def replace_vocal_regions(
        self,
        track_id: int,
        regions: list[tuple[int, int, float]],
        source: str = "heuristic",
    ) -> None:
        """regions: [(start_ms, end_ms, confidence), ...]"""
        self._conn.execute("DELETE FROM vocal_regions WHERE track_id = ?", (track_id,))
        self._conn.executemany(
            "INSERT INTO vocal_regions (track_id, start_ms, end_ms, confidence, source) "
            "VALUES (?, ?, ?, ?, ?)",
            [(track_id, int(s), int(e), float(c), source) for s, e, c in regions],
        )
        self._conn.commit()

    def get_vocal_regions(self, track_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT start_ms, end_ms, confidence, source FROM vocal_regions "
            "WHERE track_id = ? ORDER BY start_ms",
            (track_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    # ---- Stems-Meta -------------------------------------------------

    def upsert_stems_meta(
        self,
        track_id: int,
        model: str,
        stem_paths_json: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO stems_meta (track_id, model, stem_paths_json)
            VALUES (?, ?, ?)
            ON CONFLICT(track_id, model) DO UPDATE SET
                stem_paths_json = excluded.stem_paths_json,
                created_at      = CURRENT_TIMESTAMP
            """,
            (track_id, model, stem_paths_json),
        )
        self._conn.commit()

    def get_stems_meta(self, track_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT model, stem_paths_json, created_at FROM stems_meta "
            "WHERE track_id = ? ORDER BY created_at DESC",
            (track_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_stems_for_model(self, track_id: int, model: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT stem_paths_json FROM stems_meta WHERE track_id = ? AND model = ?",
            (track_id, model),
        ).fetchone()
        if row is None:
            return None
        try:
            import json
            return json.loads(row["stem_paths_json"])
        except Exception:
            return None

    def delete_stems_meta(self, track_id: int, model: Optional[str] = None) -> None:
        if model:
            self._conn.execute(
                "DELETE FROM stems_meta WHERE track_id = ? AND model = ?",
                (track_id, model),
            )
        else:
            self._conn.execute("DELETE FROM stems_meta WHERE track_id = ?", (track_id,))
        self._conn.commit()

    # ---- Settings (Quantizer, Beatgrid-Mode global) ------------------

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
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
