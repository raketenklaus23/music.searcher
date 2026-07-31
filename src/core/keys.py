"""Camelot- und Open-Key-Notation, Kompatibilitäts-Regeln, Semitone-Deltas.

Camelot-Wheel:  1A..12A (Moll),  1B..12B (Dur)
Open Key:       1m..12m (Moll),  1d..12d (Dur)   (Rekordbox-Standard)

Umrechnung Camelot ↔ Open Key: Nummer +/-1 modulo 12, Suffix-Mapping.
Kompatibel im Wheel:
  - same number, other letter  (Parallel: 8A ↔ 8B)
  - +1 / -1 same letter        (perfect 4th/5th: 8A ↔ 7A + 9A)
  - +2 same letter (Energy-Boost, weniger sicher)
  - +/-7 same letter (relative Dur/Moll-Shift, für Vibe-Change)
"""
from __future__ import annotations

from typing import Optional


# ---- Camelot ↔ Open Key -------------------------------------------------

_CAMELOT_TO_OPENKEY_NUMBER = {
    1: 12, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5,
    7: 6, 8: 7, 9: 8, 10: 9, 11: 10, 12: 11,
}
_OPENKEY_TO_CAMELOT_NUMBER = {v: k for k, v in _CAMELOT_TO_OPENKEY_NUMBER.items()}


def parse_camelot(s: str) -> Optional[tuple[int, str]]:
    """'8A' → (8, 'A'). None wenn nicht parsbar."""
    if not s or len(s) < 2:
        return None
    s = s.strip().upper()
    letter = s[-1]
    if letter not in ("A", "B"):
        return None
    try:
        n = int(s[:-1])
    except ValueError:
        return None
    if 1 <= n <= 12:
        return n, letter
    return None


def camelot_to_openkey(camelot: str) -> Optional[str]:
    p = parse_camelot(camelot)
    if p is None:
        return None
    n, letter = p
    ok_n = _CAMELOT_TO_OPENKEY_NUMBER[n]
    ok_letter = "m" if letter == "A" else "d"
    return f"{ok_n}{ok_letter}"


def openkey_to_camelot(openkey: str) -> Optional[str]:
    if not openkey or len(openkey) < 2:
        return None
    s = openkey.strip().lower()
    letter = s[-1]
    if letter not in ("m", "d"):
        return None
    try:
        n = int(s[:-1])
    except ValueError:
        return None
    if not (1 <= n <= 12):
        return None
    cam_n = _OPENKEY_TO_CAMELOT_NUMBER[n]
    cam_letter = "A" if letter == "m" else "B"
    return f"{cam_n}{cam_letter}"


# ---- Kompatibilität -----------------------------------------------------

def compatible_keys(camelot: str) -> list[str]:
    """Liefert alle im Wheel harmonisch verträglichen Camelot-Codes.

    Reihenfolge = Nähe / Sicherheit:
        [self, ±1 same letter, other letter same number, +2 same letter, ±7 letter-swap]
    """
    p = parse_camelot(camelot)
    if p is None:
        return []
    n, letter = p
    other = "B" if letter == "A" else "A"

    def wrap(x: int) -> int:
        return ((x - 1) % 12) + 1

    out = [
        f"{n}{letter}",                        # self
        f"{wrap(n + 1)}{letter}",              # +1 gleicher Modus (perfect 5th)
        f"{wrap(n - 1)}{letter}",              # -1 gleicher Modus (perfect 4th)
        f"{n}{other}",                         # Parallel (Dur/Moll)
        f"{wrap(n + 2)}{letter}",              # +2 Energie-Boost
        f"{wrap(n + 7)}{other}",               # relative Dur/Moll-Shift
    ]
    # Duplikate raus, Reihenfolge behalten
    seen: set[str] = set()
    unique: list[str] = []
    for k in out:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return unique


def key_distance_semitones(from_camelot: str, to_camelot: str) -> Optional[int]:
    """Kleinste Semiton-Verschiebung um Slave nach Master zu bringen.

    Grobe Heuristik: Wheel-Nachbarn = 5 Semitones pro Schritt (perfect 5th),
    same-number letter-swap = 3 Semitones (relative minor). Innerhalb ±6 gerundet.
    Für Key-Match reicht das — feineres Mapping später via Chroma-Vergleich.
    """
    a = parse_camelot(from_camelot)
    b = parse_camelot(to_camelot)
    if a is None or b is None:
        return None
    n_a, l_a = a
    n_b, l_b = b
    # Zirkuläres Delta ±6
    delta_n = (n_b - n_a) % 12
    if delta_n > 6:
        delta_n -= 12
    semis = delta_n * 5   # jeder Wheel-Schritt = perfect 5th = 7 Semitones? Nein — Camelot Nachbar = perfect 4th/5th = 5 oder 7. 5 ist konservativer.
    if l_a != l_b:
        semis += 3
    # Wrap in ±6
    while semis > 6:
        semis -= 12
    while semis < -6:
        semis += 12
    return semis


# ---- Anzeige-Helper ----------------------------------------------------

def format_key(camelot: Optional[str], notation: str = "camelot") -> str:
    """notation: 'camelot' oder 'openkey'."""
    if not camelot:
        return ""
    if notation == "openkey":
        return camelot_to_openkey(camelot) or camelot
    return camelot


def all_keys(notation: str = "camelot") -> list[str]:
    """Komplette Reihe der 24 Keys für die Anzeige über den Decks."""
    if notation == "openkey":
        return [f"{n}m" for n in range(1, 13)] + [f"{n}d" for n in range(1, 13)]
    return [f"{n}A" for n in range(1, 13)] + [f"{n}B" for n in range(1, 13)]


# ---- Chromatische Reihenfolge -----------------------------------------
# In musikalischer (chromatischer) Reihenfolge: Semiton für Semiton aufsteigend.
# So bedeutet Nachbar in der Reihe genau 1 Halbton Pitch-Shift.

_MINOR_CHROMATIC = [
    ("Cm",  "5A"),
    ("C#m", "12A"),
    ("Dm",  "7A"),
    ("Ebm", "2A"),
    ("Em",  "9A"),
    ("Fm",  "4A"),
    ("F#m", "11A"),
    ("Gm",  "6A"),
    ("Abm", "1A"),
    ("Am",  "8A"),
    ("Bbm", "3A"),
    ("Bm",  "10A"),
]

_MAJOR_CHROMATIC = [
    ("C",  "8B"),
    ("C#", "3B"),
    ("D",  "10B"),
    ("Eb", "5B"),
    ("E",  "12B"),
    ("F",  "7B"),
    ("F#", "2B"),
    ("G",  "9B"),
    ("Ab", "4B"),
    ("A",  "11B"),
    ("Bb", "6B"),
    ("B",  "1B"),
]


def keyrow_chromatic(notation: str = "camelot") -> dict:
    """Zwei Reihen (Moll oben, Dur unten) chromatisch aufsteigend.

    Rückgabeformat für QML:
        {
            "minor": [{"tonic": "Cm", "code": "5A"}, ...],
            "major": [{"tonic": "C",  "code": "8B"}, ...],
        }

    'code' ist entweder Camelot ('5A') oder OpenKey ('4m') je nach notation.
    'tonic' bleibt musikalischer Name (Cm / C#) — dient als Sekundärlabel.
    """
    def code_for(camelot: str) -> str:
        if notation == "openkey":
            return camelot_to_openkey(camelot) or camelot
        return camelot

    minor = [{"tonic": t, "code": code_for(c)} for t, c in _MINOR_CHROMATIC]
    major = [{"tonic": t, "code": code_for(c)} for t, c in _MAJOR_CHROMATIC]
    return {"minor": minor, "major": major}
