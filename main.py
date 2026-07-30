"""Music Searcher / DJ Suite — Entry-Point.

Startet QApplication, lädt Library + Backend + QML-UI.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType

# lokale Imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.core.library import Library  # noqa: E402
from src.ui.bridge import Backend, LibraryModel  # noqa: E402


class AppBackend(Backend):
    """Erweitert Backend um Convenience-Properties für QML."""

    queueCountChanged = Signal()

    def __init__(self, library: Library):
        super().__init__(library)
        self._queue_count = 0
        self.queueChanged.connect(self._on_queue_change)

    @Slot(int)
    def _on_queue_change(self, n: int) -> None:
        self._queue_count = n
        self.queueCountChanged.emit()

    @Property(int, notify=queueCountChanged)
    def queueCount(self) -> int:
        return self._queue_count


def main() -> int:
    QGuiApplication.setApplicationName("Music Searcher")
    QGuiApplication.setOrganizationName("MMM")
    app = QGuiApplication(sys.argv)

    # Library initialisieren
    library = Library()
    backend = AppBackend(library)

    # QML Engine
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)

    qml_dir = Path(__file__).resolve().parent / "src" / "ui" / "qml"
    engine.addImportPath(str(qml_dir))
    engine.load(QUrl.fromLocalFile(str(qml_dir / "Main.qml")))

    if not engine.rootObjects():
        print("Fehler: QML konnte nicht geladen werden.", file=sys.stderr)
        return 1

    # Beim Start: alle noch offenen Analyse-Jobs re-enqueuen
    backend.reanalyzePending()

    exit_code = app.exec()
    library.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
