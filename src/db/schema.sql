-- Music Searcher / DJ Suite — Datenbank-Schema
-- SQLite (WAL Mode empfohlen für nebenläufige Analyse-Jobs)

CREATE TABLE IF NOT EXISTS tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT NOT NULL UNIQUE,
    title           TEXT,
    artist          TEXT,
    album           TEXT,
    year            INTEGER,
    genre           TEXT,
    duration_ms     INTEGER,
    bpm             REAL,
    key             TEXT,             -- z.B. "8A" (Camelot) oder "Am"
    lufs            REAL,
    energy          REAL,             -- 0..1 grober Energie-Wert
    sample_rate     INTEGER,
    channels        INTEGER,
    bitrate         INTEGER,
    filesize        INTEGER,
    comp_pushed     INTEGER DEFAULT 0,      -- 0/1: ist das eine gepushte Version
    parent_track_id INTEGER,                -- optional: verweist auf Original wenn gepushte Version
    playback_gain_db REAL DEFAULT 0.0,     -- Gain-Offset für LUFS-Normalize (non-destruktiv)
    status          TEXT DEFAULT 'pending', -- pending | analyzing | ready | error
    error_msg       TEXT,
    imported_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    analyzed_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist);
CREATE INDEX IF NOT EXISTS idx_tracks_genre  ON tracks(genre);
CREATE INDEX IF NOT EXISTS idx_tracks_bpm    ON tracks(bpm);
CREATE INDEX IF NOT EXISTS idx_tracks_key    ON tracks(key);
CREATE INDEX IF NOT EXISTS idx_tracks_year   ON tracks(year);
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);

CREATE TABLE IF NOT EXISTS cues (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id          INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    idx               INTEGER NOT NULL,       -- 0..7
    position_ms       INTEGER NOT NULL,
    label             TEXT,
    color             TEXT,
    source            TEXT DEFAULT 'auto',    -- auto | manual
    -- Loop-Cue-Vorbereitung: wenn != NULL wird dieser Cue als Loop-Trigger behandelt
    loop_length_beats INTEGER,
    UNIQUE(track_id, idx)
);

CREATE TABLE IF NOT EXISTS loops (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id    INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,       -- 0..7
    start_ms    INTEGER NOT NULL,
    length_ms   INTEGER NOT NULL,
    beats       INTEGER,                -- 4/8/16 etc.
    label       TEXT,
    source      TEXT DEFAULT 'auto',
    UNIQUE(track_id, idx)
);

CREATE TABLE IF NOT EXISTS playlists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    kind        TEXT DEFAULT 'manual',  -- manual | genre | set-derived | folder
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    meta_json   TEXT                    -- freie Metadaten (z.B. Set-Fingerprint)
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id    INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, track_id)
);

CREATE TABLE IF NOT EXISTS features (
    track_id     INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    mfcc_blob    BLOB,       -- np.float32 array (13, N) serialisiert
    chroma_blob  BLOB,       -- np.float32 array (12, N)
    tempogram    BLOB,
    danceability REAL,
    groove       REAL,
    vibe_vector  BLOB        -- reduzierter Feature-Vektor für Similarity
);

CREATE TABLE IF NOT EXISTS beatgrid (
    track_id     INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    beats_blob   BLOB,       -- np.float32 array in Sekunden
    downbeat_ms  INTEGER,    -- erster Downbeat in ms
    bpm          REAL,
    mode         TEXT DEFAULT 'beat_match'  -- beat_match | structure_boundaries
);

-- Vocal-Regionen (heuristisch in Phase 3, präzise via Demucs in Phase 4)
CREATE TABLE IF NOT EXISTS vocal_regions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id    INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    start_ms    INTEGER NOT NULL,
    end_ms      INTEGER NOT NULL,
    confidence  REAL,                        -- 0..1
    source      TEXT DEFAULT 'heuristic'     -- heuristic | demucs
);
CREATE INDEX IF NOT EXISTS idx_vocal_regions_track ON vocal_regions(track_id);

CREATE TABLE IF NOT EXISTS stems_meta (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id    INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    model       TEXT NOT NULL,          -- htdemucs | htdemucs_6s
    stem_paths_json TEXT NOT NULL,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(track_id, model)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
