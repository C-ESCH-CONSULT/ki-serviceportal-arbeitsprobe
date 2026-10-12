"""Fachlicher Dienst: verbindet Datenstände, Benchmark, Wissensspeicher, Matching und Gateway.

Die API-Schicht ruft nur diesen Dienst auf. Dadurch lässt sich die gesamte Fachlogik ohne
Webserver und ohne Datenbank testen.
"""
from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .benchmark import einordnen
from .gateway import LLMGateway, LokalerExtraktiverAnbieter, OpenAIKompatiblerAnbieter, Protokoll
from .importer import KennzahlenImporter
from .matching import vorschlagen
from .models import Datenstand
from .speicher import DatenstandSpeicher, SpeicherImArbeitsspeicher
from .wissen import Wissensspeicher

DATEN = Path(__file__).resolve().parent.parent / "data"


def gateway_aus_umgebung(protokoll_datei: Optional[Path] = None) -> LLMGateway:
    """Wählt den Modellanbieter über Umgebungsvariablen; ohne Angabe läuft alles lokal."""
    basis_url = os.getenv("LLM_BASIS_URL")
    if basis_url:
        anbieter = OpenAIKompatiblerAnbieter(basis_url, os.getenv("LLM_MODELL", "llama-3.1-8b-instruct"),
                                             os.getenv("LLM_MODELL_VERSION", "unbekannt"),
                                             os.getenv("LLM_API_SCHLUESSEL", ""))
    else:
        anbieter = LokalerExtraktiverAnbieter()
    return LLMGateway(anbieter, Protokoll(protokoll_datei))


class Dienst:
    def __init__(self, speicher: Optional[DatenstandSpeicher] = None, wissen: Optional[Wissensspeicher] = None,
                 gateway: Optional[LLMGateway] = None):
        self.speicher = speicher or SpeicherImArbeitsspeicher()
        self.wissen = wissen or Wissensspeicher().laden(DATEN / "massnahmen")
        self.gateway = gateway or gateway_aus_umgebung()

    # Datenpipeline
    def importieren(self, inhalt: str, quelle: str, stichtag: str) -> Datenstand:
        vorgaenger = self.speicher.aktuell(quelle)
        stand = KennzahlenImporter(quelle, stichtag).importieren(inhalt, vorgaenger)
        self.speicher.speichern(stand)
        return stand

    def _stand(self, datenstand_id: Optional[str]) -> Datenstand:
        stand = self.speicher.holen(datenstand_id) if datenstand_id else self.speicher.aktuell()
        if stand is None:
            raise LookupError("Kein Datenstand vorhanden")
        return stand

    # Benchmark und Matching
    def benchmark(self, kommune_id: str, datenstand_id: Optional[str] = None) -> dict:
        stand = self._stand(datenstand_id)
        return asdict(einordnen(stand, kommune_id))

    def massnahmen(self, kommune_id: str, datenstand_id: Optional[str] = None) -> dict:
        stand = self._stand(datenstand_id)
        ergebnis = einordnen(stand, kommune_id)
        vorschlaege = vorschlagen(ergebnis, stand, self.wissen)
        return {"kommune_id": kommune_id, "datenstand_id": stand.datenstand_id,
                "bedarfe": [asdict(b) for b in ergebnis.bedarfe],
                "vorschlaege": [asdict(v) for v in vorschlaege]}

    # Wissensfragen
    def fragen(self, frage: str, prompt_version: Optional[str] = None) -> dict:
        return asdict(self.wissen.fragen(frage, self.gateway, prompt_version=prompt_version))

    def protokoll(self, letzte: int = 50) -> list[dict]:
        return [asdict(e) for e in self.gateway.protokoll.eintraege[-letzte:]]
