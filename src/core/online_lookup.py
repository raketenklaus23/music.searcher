"""Online-Metadaten-Lookup — MusicBrainz + Discogs, mit SQLite-Cache.

Wird nur beim Import (optional) oder aus dem Suggester-Dialog manuell
angestossen. Rate-Limits werden respektiert (MusicBrainz: 1/s, Discogs: 60/min).

Kein API-Key noetig fuer MusicBrainz. Discogs benoetigt entweder ein
persoenliches Token in `settings` (key='discogs_token') oder ist offline.
"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from .library import Library


MB_URL = "https://musicbrainz.org/ws/2"
DISCOGS_URL = "https://api.discogs.com"
USER_AGENT = "MusicSearcher/0.1 ( matthias.meuser0904@gmail.com )"

_LAST_CALL: dict[str, float] = {"musicbrainz": 0.0, "discogs": 0.0}
_MIN_INTERVAL = {"musicbrainz": 1.05, "discogs": 1.05}


@dataclass
class OnlineHit:
    source: str
    title: str
    artist: str
    album: Optional[str] = None
    year: Optional[int] = None
    genres: list[str] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)
    score: float = 0.0
    extra: dict = field(default_factory=dict)


def _throttle(source: str) -> None:
    now = time.monotonic()
    wait = _MIN_INTERVAL[source] - (now - _LAST_CALL[source])
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL[source] = time.monotonic()


def _http_json(url: str, headers: dict) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _cache_get(library: Library, source: str, key: str) -> Optional[dict]:
    try:
        row = library._conn.execute(
            "SELECT payload FROM online_cache WHERE source = ? AND lookup_key = ?",
            (source, key),
        ).fetchone()
        return json.loads(row["payload"]) if row else None
    except sqlite3.Error:
        return None


def _cache_put(library: Library, source: str, key: str, payload: dict) -> None:
    try:
        library._conn.execute(
            """INSERT INTO online_cache (source, lookup_key, payload)
               VALUES (?, ?, ?)
               ON CONFLICT(source, lookup_key) DO UPDATE SET
                   payload = excluded.payload,
                   fetched_at = CURRENT_TIMESTAMP""",
            (source, key, json.dumps(payload)),
        )
        library._conn.commit()
    except sqlite3.Error:
        pass


def _get_setting(library: Library, key: str) -> Optional[str]:
    try:
        row = library._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None
    except sqlite3.Error:
        return None


# ---- MusicBrainz --------------------------------------------------------

def musicbrainz_search(
    library: Library, artist: str, title: str, use_cache: bool = True,
) -> list[OnlineHit]:
    key = f"{artist.lower().strip()}|{title.lower().strip()}"
    if use_cache:
        cached = _cache_get(library, "musicbrainz", key)
        if cached is not None:
            return [OnlineHit(**h) for h in cached.get("hits", [])]

    _throttle("musicbrainz")
    q = f'recording:"{title}" AND artist:"{artist}"'
    url = f"{MB_URL}/recording/?query={urllib.parse.quote(q)}&fmt=json&limit=5"
    data = _http_json(url, {"User-Agent": USER_AGENT, "Accept": "application/json"})
    hits: list[OnlineHit] = []
    if data and "recordings" in data:
        for rec in data["recordings"][:5]:
            rel_list = rec.get("releases") or []
            first_rel = rel_list[0] if rel_list else {}
            date = first_rel.get("date") or ""
            year = None
            if len(date) >= 4 and date[:4].isdigit():
                year = int(date[:4])
            tags = [t["name"] for t in (rec.get("tags") or []) if "name" in t]
            hit = OnlineHit(
                source="musicbrainz",
                title=rec.get("title", title),
                artist=(rec.get("artist-credit", [{}])[0] or {}).get("name", artist),
                album=first_rel.get("title"),
                year=year,
                genres=tags,
                score=float(rec.get("score", 0)) / 100.0,
                extra={"mbid": rec.get("id")},
            )
            hits.append(hit)
    payload = {"hits": [h.__dict__ for h in hits]}
    _cache_put(library, "musicbrainz", key, payload)
    return hits


# ---- Discogs ------------------------------------------------------------

def discogs_search(
    library: Library, artist: str, title: str, use_cache: bool = True,
) -> list[OnlineHit]:
    key = f"{artist.lower().strip()}|{title.lower().strip()}"
    if use_cache:
        cached = _cache_get(library, "discogs", key)
        if cached is not None:
            return [OnlineHit(**h) for h in cached.get("hits", [])]

    token = _get_setting(library, "discogs_token")
    if not token:
        return []

    _throttle("discogs")
    q = f"{artist} {title}"
    url = (
        f"{DISCOGS_URL}/database/search?q={urllib.parse.quote(q)}"
        f"&type=release&per_page=5&token={urllib.parse.quote(token)}"
    )
    data = _http_json(url, {"User-Agent": USER_AGENT})
    hits: list[OnlineHit] = []
    if data and "results" in data:
        for res in data["results"][:5]:
            year_raw = res.get("year")
            try:
                year = int(year_raw) if year_raw else None
            except (TypeError, ValueError):
                year = None
            hit = OnlineHit(
                source="discogs",
                title=(res.get("title") or title).split(" - ", 1)[-1],
                artist=(res.get("title") or f"{artist} - ?").split(" - ", 1)[0],
                album=res.get("title"),
                year=year,
                genres=res.get("genre") or [],
                styles=res.get("style") or [],
                extra={"discogs_id": res.get("id"), "thumb": res.get("thumb")},
            )
            hits.append(hit)
    payload = {"hits": [h.__dict__ for h in hits]}
    _cache_put(library, "discogs", key, payload)
    return hits


def hybrid_search(library: Library, artist: str, title: str) -> list[OnlineHit]:
    """MusicBrainz + Discogs zusammen, sortiert nach Score."""
    hits = musicbrainz_search(library, artist, title)
    hits += discogs_search(library, artist, title)
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits
