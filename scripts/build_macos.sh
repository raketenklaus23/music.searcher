#!/usr/bin/env bash
# Music Searcher — macOS-Build (PyInstaller .app)
#
# Voraussetzung:
#   python -m pip install pyinstaller
# Ergebnis:
#   dist/MusicSearcher.app

set -e
cd "$(dirname "$0")/.."

echo "=== Music Searcher / DJ Suite — macOS-Build ==="

python -m PyInstaller --clean build.spec

echo ""
echo "Fertig: dist/MusicSearcher.app"
du -sh dist/MusicSearcher.app
