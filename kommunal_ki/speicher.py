"""Ablage für Datenstände. Datenstände sind unveränderlich; neue Importe erzeugen neue Stände."""
from __future__ import annotations

from typing import Optional, Protocol

from .models import Datenstand


class DatenstandSpeicher(Protocol):
    def speichern(self, stand: Datenstand) -> None: ...
    def holen(self, datenstand_id: str) -> Optional[Datenstand]: ...
    def aktuell(self, quelle: Optional[str] = None) -> Optional[Datenstand]: ...
    def alle(self) -> list[Datenstand]: ...


class SpeicherImArbeitsspeicher:
    def __init__(self) -> None:
        self._staende: dict[str, Datenstand] = {}

    def speichern(self, stand: Datenstand) -> None:
        if stand.datenstand_id in self._staende:
            return  # identischer Inhalt wurde bereits importiert
        self._staende[stand.datenstand_id] = stand

    def holen(self, datenstand_id: str) -> Optional[Datenstand]:
        return self._staende.get(datenstand_id)

    def aktuell(self, quelle: Optional[str] = None) -> Optional[Datenstand]:
        kandidaten = [s for s in self._staende.values() if quelle is None or s.quelle == quelle]
        return max(kandidaten, key=lambda s: (s.stichtag, s.importiert_am), default=None)

    def alle(self) -> list[Datenstand]:
        return sorted(self._staende.values(), key=lambda s: (s.stichtag, s.importiert_am))
