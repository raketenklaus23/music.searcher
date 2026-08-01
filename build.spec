# PyInstaller-Spec fuer Music Searcher / DJ Suite
# Bau: pyinstaller build.spec
#
# Windows: erzeugt dist/MusicSearcher/MusicSearcher.exe (One-Dir)
# macOS  : erzeugt dist/MusicSearcher.app
#
# Bewusst als One-Dir (nicht --onefile): schneller Start, kleinere Delta-Updates,
# Qt-Ressourcen bleiben findbar.
#
# Vor dem ersten Build:
#   pip install pyinstaller
#   (optional) demucs + torch, wenn Stems mitgebaut werden sollen
from __future__ import annotations

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

BASE = Path(SPECPATH).resolve()

# QML-Ordner + Schema mitschleifen
datas = [
    (str(BASE / "src" / "ui" / "qml"), "src/ui/qml"),
    (str(BASE / "src" / "db" / "schema.sql"), "src/db"),
]

# Optional: SF2/Icons/Beispiele
if (BASE / "models").exists():
    datas.append((str(BASE / "models"), "models"))

# Librosa + PySide6 haben viele optionale Submodule
hiddenimports = []
hiddenimports += collect_submodules("librosa")
hiddenimports += ["numpy", "soundfile", "sounddevice", "pyloudnorm", "mutagen",
                  "pedalboard", "pyrubberband", "platformdirs"]
try:
    datas += collect_data_files("librosa", include_py_files=False)
except Exception:
    pass

block_cipher = None

a = Analysis(
    [str(BASE / "main.py")],
    pathex=[str(BASE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

is_mac = sys.platform == "darwin"

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MusicSearcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="MusicSearcher",
)

if is_mac:
    app = BUNDLE(
        coll,
        name="MusicSearcher.app",
        icon=None,
        bundle_identifier="de.mmm.musicsearcher",
    )
