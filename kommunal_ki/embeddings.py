"""Einbettungen für die Vektorsuche. Standard ist ein Hashing-Embedder ohne Modell-Download."""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

DIMENSION = 512

_STOPPWOERTER = set("""
der die das den dem des ein eine einer eines einem einen und oder für mit von zu zur zum im in an am auf
aus bei ist sind wird werden kann können sich als auch nicht nur so wie wo was wer es sie er wir ihr
""".split())


# Fachbegriffe, die in Fragen und Texten unterschiedlich formuliert werden.
BEGRIFFSGRUPPEN = [
    {"braucht", "benötigt", "benötigen", "voraussetzung", "erforderlich", "nötig", "notwendig", "brauchen"},
    {"bezahlt", "bezahlen", "kosten", "tragen", "trägt", "finanziert", "finanzierung", "abgerechnet"},
    {"wirkung", "bringt", "nutzen", "effekt", "wirkt"},
    {"beraten", "beratung", "berät", "sprechstunden", "sprechstunde"},
    {"ehrenamt", "ehrenamtliche", "ehrenamtlichen", "helfende", "helferinnen"},
]


def erweitern(woerter: set[str]) -> set[str]:
    """Ergänzt Wörter um gleichbedeutende Fachbegriffe."""
    erweitert = set(woerter)
    for gruppe in BEGRIFFSGRUPPEN:
        if woerter & gruppe:
            erweitert |= gruppe
    return erweitert


class Embedder(Protocol):
    name: str
    version: str

    def einbetten(self, text: str) -> list[float]: ...


def tokens(text: str) -> list[str]:
    woerter = re.findall(r"[a-zäöüß0-9]+", text.lower())
    return [w for w in woerter if w not in _STOPPWOERTER and len(w) > 2]


class HashingEmbedder:
    name = "hashing-ngram"
    version = "1"

    def __init__(self, dimension: int = DIMENSION):
        self.dimension = dimension

    def _index(self, merkmal: str) -> tuple[int, float]:
        h = hashlib.blake2b(merkmal.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % self.dimension
        vorzeichen = 1.0 if h[4] & 1 else -1.0
        return idx, vorzeichen

    def einbetten(self, text: str) -> list[float]:
        vek = [0.0] * self.dimension
        for wort in tokens(text):
            idx, s = self._index("w:" + wort)
            vek[idx] += 2.0 * s
            stamm = wort[:6]  # grobe Stammform, fängt Flexion ab
            idx, s = self._index("s:" + stamm)
            vek[idx] += 1.5 * s
            gepolstert = f"#{wort}#"
            for i in range(len(gepolstert) - 3):
                idx, s = self._index("g:" + gepolstert[i:i + 4])
                vek[idx] += 0.5 * s
        norm = math.sqrt(sum(v * v for v in vek)) or 1.0
        return [v / norm for v in vek]


def kosinus(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
