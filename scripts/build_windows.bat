@echo off
REM Music Searcher — Windows-Build (PyInstaller One-Dir)
REM
REM Voraussetzung:  pip install pyinstaller
REM Ergebnis:       dist\MusicSearcher\MusicSearcher.exe

setlocal
cd /d "%~dp0\.."

echo === Music Searcher / DJ Suite — Windows-Build ===
echo.

if not exist "build.spec" (
    echo Fehler: build.spec fehlt.
    exit /b 1
)

echo [1/3] pyinstaller (One-Dir)…
python -m PyInstaller --clean build.spec
if errorlevel 1 (
    echo Build fehlgeschlagen.
    exit /b 1
)

echo.
echo [2/3] Copy README + shortcuts-Template
if exist "README.md" copy /y "README.md" "dist\MusicSearcher\README.md" >nul

echo.
echo [3/3] Fertig.
echo Ergebnis: dist\MusicSearcher\MusicSearcher.exe
echo Groesse:
dir /s /-c "dist\MusicSearcher" | find "File(s)"
endlocal
