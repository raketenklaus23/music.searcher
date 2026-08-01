# Music Searcher — DJ Suite

Eigenständige Musik-Verwaltung + DJ-Vorproduktion in Python. Flache Library, 2 Decks mit Sync/Key-Match, Auto-Cues, Auto-Loops, offline Stem-Separation, DJ-Set-Analyse und Similar-Tracks-Vorschläge.

## Status

**Phasen 1–7: ✅ fertig · Phasen 8–10 laufen**

- Phase 1 — Library + Basis-Analyse (BPM/Key/LUFS/Energy)
- Phase 2 — Decks + Mixer + Sync/Key-Match
- Phase 3 — Beatgrid + Quantizer + Vocals + Auto-Cues/Loops + LUFS-Normalize
- Phase 4 — Demucs-Stems + Deck-Playback + A10-Compressor + Save-Pushed
- Phase 5 — Vibe-Suggester + Set-Fingerprint + MusicBrainz/Discogs
- Phase 6 — Waveform-Canvas + Vocal-Overlay + Beat-Ticks + Animationen
- Phase 7 — Editierbare Keyboard-Shortcuts (17 Actions)

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

- [x] Phase 1 — Fundament (Library + Basis-Analyse)
- [x] Phase 2 — Decks + Mixer (Sync, Crossfader, 4-Band-EQ, Key-Match)
- [x] Phase 3 — Auto-Cues (8) + Auto-Loops (8) + LUFS-Normalisierung
- [x] Phase 4 — Offline-Stems (Demucs) + Pioneer-A10-Compression + Save-Pushed
- [x] Phase 5 — DJ-Set-Analyse + Similar-Tracks + Online-Lookup
- [x] Phase 6 — Waveform-Shader, Vocal-Overlay, Beat-Ticks, Animationen
- [x] Phase 7 — Editierbare Keyboard-Shortcuts
- [ ] Phase 8 — Standalone-Build (Windows .exe + macOS .app via PyInstaller)
- [ ] Phase 9 — MIDI-Controller-Mapping (Denon SC Live 4)
- [ ] Phase 10 — 4-Deck-Option (adaptives Layout)

## Standalone-Build

```bash
pip install pyinstaller
# Windows:
scripts\build_windows.bat
# macOS:
./scripts/build_macos.sh
```

Ergebnis: `dist/MusicSearcher/MusicSearcher.exe` bzw. `dist/MusicSearcher.app`.
