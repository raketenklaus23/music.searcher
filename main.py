"""Music Searcher / DJ Suite — Entry-Point.

Startet QApplication, lädt Library + Player + Backend + QML-UI.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Property, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

# lokale Imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.audio.player import Player  # noqa: E402
from src.core.library import Library  # noqa: E402
from src.ui.actions import Actions, register_default_actions  # noqa: E402
from src.ui.bridge import Backend  # noqa: E402
from src.ui.deck_bridge import PlayerBridge  # noqa: E402


class AppBackend(Backend):
    """Erweitert Backend um Convenience-Properties für QML.

    Hält Referenzen auf PlayerBridge und Actions-Registry.
    """

    queueCountChanged = Signal()

    def __init__(self, library: Library, player: Player):
        super().__init__(library)
        self._player_bridge = PlayerBridge(player, library, self)
        self._actions = Actions(self)
        register_default_actions(self._actions, self._player_bridge)

        self._queue_count = 0
        self.queueChanged.connect(self._on_queue_change)

    @Slot(int)
    def _on_queue_change(self, n: int) -> None:
        self._queue_count = n
        self.queueCountChanged.emit()

    @Property(int, notify=queueCountChanged)
    def queueCount(self) -> int:
        return self._queue_count

    @Property("QVariant", constant=True)
    def player(self):
        return self._player_bridge

    @Property("QVariant", constant=True)
    def actions(self):
        return self._actions


def main() -> int:
    QGuiApplication.setApplicationName("Music Searcher")
    QGuiApplication.setOrganizationName("MMM")
    # Basic-Style erlaubt volle Customization von Controls (Buttons, Slider, etc.)
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication(sys.argv)

    library = Library()
    player = Player()

    backend = AppBackend(library, player)

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
    player.stop()
    library.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
