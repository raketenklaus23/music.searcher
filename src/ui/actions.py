"""Central Action-Registry.

Alle User-Aktionen werden hier per String-ID registriert. Ziel: sowohl
Keyboard-Shortcuts (Phase 7) als auch MIDI-Controller (Phase 9) mappen auf
dieselbe Aktions-Ebene. QML kann Aktionen per ID auslösen — das entkoppelt
die UI von konkreten Bridge-Slots.

ID-Konvention:  `<domain>.<target>.<verb>`
    deck.a.play, deck.a.sync, deck.b.keypress, deck.a.bpm_halve
    mixer.crossfader.center, mixer.master.gain_up
    global.master.a, global.notation.toggle
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import QObject, Property, Signal, Slot


@dataclass
class ActionSpec:
    id: str
    label: str
    category: str
    callable: Callable[[], None]
    default_shortcut: Optional[str] = None
    parameterized: bool = False   # nimmt float-Argument (z. B. Fader) → nicht via trigger()
    tags: list[str] = field(default_factory=list)


class Actions(QObject):
    """Registry + QML-Fassade."""

    registryChanged = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._actions: dict[str, ActionSpec] = {}

    def register(
        self,
        action_id: str,
        label: str,
        category: str,
        fn: Callable[[], None],
        default_shortcut: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        if action_id in self._actions:
            raise ValueError(f"Action-ID doppelt registriert: {action_id}")
        self._actions[action_id] = ActionSpec(
            id=action_id,
            label=label,
            category=category,
            callable=fn,
            default_shortcut=default_shortcut,
            tags=tags or [],
        )
        self.registryChanged.emit()

    def unregister(self, action_id: str) -> None:
        self._actions.pop(action_id, None)
        self.registryChanged.emit()

    def get(self, action_id: str) -> Optional[ActionSpec]:
        return self._actions.get(action_id)

    def all(self) -> list[ActionSpec]:
        return list(self._actions.values())

    # ---- QML-Slots ------------------------------------------------

    @Slot(str, result=bool)
    def trigger(self, action_id: str) -> bool:
        spec = self._actions.get(action_id)
        if spec is None:
            print(f"[Actions] Unbekannte Aktion: {action_id}")
            return False
        try:
            spec.callable()
            return True
        except Exception as exc:
            print(f"[Actions] Fehler bei {action_id}: {exc}")
            return False

    @Slot(result=list)
    def listAll(self) -> list:  # noqa: N802
        return [
            {
                "id": a.id,
                "label": a.label,
                "category": a.category,
                "defaultShortcut": a.default_shortcut or "",
                "tags": a.tags,
            }
            for a in self._actions.values()
        ]

    @Slot(str, result=str)
    def labelOf(self, action_id: str) -> str:  # noqa: N802
        spec = self._actions.get(action_id)
        return spec.label if spec else action_id


def register_default_actions(actions: Actions, player_bridge) -> None:
    """Registriert die Standard-Aktionen für die aktuellen Decks + Mixer.

    Wird bei jedem Player-Init aufgerufen. Deck-Anzahl (2 oder später 4)
    kommt aus player_bridge.deckIds().
    """
    for deck_id in player_bridge.deckIds():
        deck = player_bridge.deckByIdInternal(deck_id)
        label_side = deck_id.upper()

        actions.register(
            f"deck.{deck_id}.play_pause",
            f"Deck {label_side}: Play/Pause",
            f"Deck {label_side}",
            deck.toggle,
            default_shortcut={"a": "Space", "b": "Shift+Space"}.get(deck_id),
            tags=["transport"],
        )
        actions.register(
            f"deck.{deck_id}.cue",
            f"Deck {label_side}: Cue",
            f"Deck {label_side}",
            deck.cue,
            default_shortcut={"a": "Q", "b": "P"}.get(deck_id),
            tags=["transport"],
        )
        actions.register(
            f"deck.{deck_id}.sync",
            f"Deck {label_side}: Sync (1x/2x)",
            f"Deck {label_side}",
            deck.sync,
            default_shortcut={"a": "S", "b": "L"}.get(deck_id),
            tags=["sync"],
        )
        actions.register(
            f"deck.{deck_id}.keypress",
            f"Deck {label_side}: Key (1x=Lock, 2x=Match)",
            f"Deck {label_side}",
            deck.keyPress,
            default_shortcut={"a": "K", "b": "M"}.get(deck_id),
            tags=["key"],
        )
        actions.register(
            f"deck.{deck_id}.bpm_halve",
            f"Deck {label_side}: BPM /2",
            f"Deck {label_side}",
            deck.halveBpm,
            default_shortcut={"a": "Ctrl+Left", "b": "Ctrl+Shift+Left"}.get(deck_id),
            tags=["beatgrid"],
        )
        actions.register(
            f"deck.{deck_id}.bpm_double",
            f"Deck {label_side}: BPM x2",
            f"Deck {label_side}",
            deck.doubleBpm,
            default_shortcut={"a": "Ctrl+Right", "b": "Ctrl+Shift+Right"}.get(deck_id),
            tags=["beatgrid"],
        )
        actions.register(
            f"deck.{deck_id}.become_master",
            f"Deck {label_side}: Master",
            f"Deck {label_side}",
            deck.becomeMaster,
            default_shortcut={"a": "F1", "b": "F2"}.get(deck_id),
            tags=["sync"],
        )

    # Global
    actions.register(
        "global.unsync_all",
        "Alle Decks entsyncen",
        "Global",
        player_bridge.unsyncAll,
        default_shortcut="Ctrl+U",
        tags=["sync"],
    )
    actions.register(
        "global.notation_toggle",
        "Key-Notation umschalten (Camelot ↔ Open Key)",
        "Global",
        player_bridge.toggleKeyNotation,
        default_shortcut="Ctrl+K",
        tags=["key"],
    )
    actions.register(
        "mixer.crossfader.center",
        "Crossfader zentrieren",
        "Mixer",
        lambda: player_bridge.setCrossfader(0.0),
        default_shortcut="C",
        tags=["mixer"],
    )
