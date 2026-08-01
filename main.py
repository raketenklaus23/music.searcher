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
from src.core.stem_jobs import StemRunner  # noqa: E402
from src.ui.actions import Actions, register_default_actions  # noqa: E402
from src.ui.bridge import Backend  # noqa: E402
from src.ui.deck_bridge import PlayerBridge  # noqa: E402
from src.ui.midi_bridge import MidiBridge  # noqa: E402
from src.ui.suggester_bridge import SuggesterBridge  # noqa: E402


class AppBackend(Backend):
    """Erweitert Backend um Convenience-Properties für QML.

    Hält Referenzen auf PlayerBridge und Actions-Registry.
    """

    queueCountChanged = Signal()
    stemQueueChanged = Signal()
    stemJobFinished = Signal(int, str)      # track_id, model

    def __init__(self, library: Library, player: Player):
        super().__init__(library)
        self._player_bridge = PlayerBridge(player, library, self)
        self._actions = Actions(self)
        register_default_actions(self._actions, self._player_bridge)

        self._stem_runner = StemRunner(library, parent=self)
        self._player_bridge._stem_runner_ref = self._stem_runner
        self._stem_runner.stemFinished.connect(self._on_stem_finished)
        self._stem_runner.queueChanged.connect(self._on_stem_queue_change)
        self._stem_queue = 0

        self._suggester = SuggesterBridge(library, parent=self)
        self._midi = MidiBridge(self._actions, self._player_bridge, parent=self)

        self._queue_count = 0
        self.queueChanged.connect(self._on_queue_change)

    @Slot(int)
    def _on_queue_change(self, n: int) -> None:
        self._queue_count = n
        self.queueCountChanged.emit()

    @Slot(int)
    def _on_stem_queue_change(self, n: int) -> None:
        self._stem_queue = n
        self.stemQueueChanged.emit()

    @Slot(int, str)
    def _on_stem_finished(self, track_id: int, model: str) -> None:
        # Falls Track auf einem Deck geladen ist → Stems dort direkt aktivieren
        for deck_id in ("a", "b"):
            deck = self._player_bridge.deckByIdInternal(deck_id)
            if deck._deck.state.track_id == track_id:
                from src.core.stems import stem_paths_from_json
                paths = self._library.get_stems_for_model(track_id, model)
                if paths:
                    deck._deck.load_stems(model, paths)
                    deck.stateChanged.emit()
        self.stemJobFinished.emit(track_id, model)
        # Library-Model refreshen (Stem-Icons in LibraryPanel)
        self._model.update_track(track_id)

    @Property(int, notify=stemQueueChanged)
    def stemQueueCount(self) -> int:
        return self._stem_queue

    @Property(int, notify=queueCountChanged)
    def queueCount(self) -> int:
        return self._queue_count

    @Property("QVariant", constant=True)
    def player(self):
        return self._player_bridge

    @Property("QVariant", constant=True)
    def actions(self):
        return self._actions

    @Property("QVariant", constant=True)
    def suggester(self):
        return self._suggester

    @Property("QVariant", constant=True)
    def midi(self):
        return self._midi


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
