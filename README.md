# Music Searcher — DJ Suite

Eigenständige Musik-Verwaltung + DJ-Vorproduktion in Python. Flache Library, 2 Decks mit Sync/Key-Match, Auto-Cues, Auto-Loops, offline Stem-Separation, DJ-Set-Analyse und Similar-Tracks-Vorschläge.

## Status

**Phase 1 — Fundament: ✅ fertig**

- SQLite-Library (flach, keine Ordnerhierarchie)
- Drag & Drop Import über QML
- Basis-Analyse offline: BPM, Tonart (Camelot), LUFS, Energy — via `librosa` + `pyloudnorm`
- Background-Job-Queue (QThreadPool), Analyse blockiert die UI nicht
- Flashiges Dark-UI-Grundgerüst mit PySide6 + QML

Nächste Phasen: Decks + Mixer (2), Analyse-Suite (3), Stems + Compression (4), Suggester + Set-Analyse (5), GUI-Polish (6).

## Start

```bash
pip install -r requirements.txt
python main.py
```

Anschließend Musikdateien in die Library ziehen — die Analyse läuft automatisch im Hintergrund.

## Projektstruktur

```
music.searcher/
├── main.py                 # Entry-Point (QApplication + QML)
├── requirements.txt
├── src/
│   ├── core/               # Library, Analyzer, Jobs (später: Cues, Stems, Suggester)
│   ├── audio/              # (Phase 2: Decks, Mixer, Effects)
│   ├── ui/
│   │   ├── bridge.py       # Python <-> QML Bridge
│   │   └── qml/            # QML-UI (Main.qml, LibraryPanel.qml, …)
│   └── db/schema.sql
├── data/                   # SQLite-DB, importierte Musik, Cache, Stems
└── models/                 # Demucs-Modelle (später)
```

## Tech-Stack

| Bereich | Bibliothek |
|---|---|
| GUI | PySide6 (Qt 6) + QML + Qt Quick Effects |
| Analyse | librosa, pyloudnorm |
| Metadaten | mutagen |
| DB | SQLite (stdlib) |
| Playback (Phase 2) | sounddevice, pyrubberband, pedalboard |
| Stems (Phase 4) | Demucs v4 (htdemucs + htdemucs_6s) |

## Roadmap

- [x] Phase 1 — Fundament
- [ ] Phase 2 — Decks + Mixer (Sync, Crossfader, 4-Band-EQ, Key-Match)
- [ ] Phase 3 — Auto-Cues (8) + Auto-Loops (8) + LUFS-Normalisierung
- [ ] Phase 4 — Offline-Stems (Demucs) + Pioneer-A10-Compression + Save-Pushed
- [ ] Phase 5 — DJ-Set-Analyse (60 min → Playlist), Similar-Tracks-Fenster (Jahr+Künstler)
- [ ] Phase 6 — Shader-Polish, physikalische Knobs, Beat-Sync-Animationen
