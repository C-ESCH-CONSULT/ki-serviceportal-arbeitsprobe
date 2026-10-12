"""Gemeinsame Datentypen."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Kennzahl:
    """Definition einer Kennzahl mit Prüfregeln."""

    name: str
    bezeichnung: str
    einheit: str
    minimum: float
    maximum: float
    ganzzahl: bool = False


KENNZAHLEN: dict[str, Kennzahl] = {
    k.name: k
    for k in [
        Kennzahl("einwohner", "Einwohnerinnen und Einwohner", "Personen", 1, 5_000_000, ganzzahl=True),
        Kennzahl("anteil_80plus_pct", "Anteil 80 Jahre und älter", "%", 0, 100),
        Kennzahl("pflegebeduerftige_je_1000", "Pflegebedürftige je 1.000 Einwohner", "je 1.000", 0, 1000),
        Kennzahl("stationaere_plaetze_je_100_80plus", "Stationäre Pflegeplätze je 100 Personen 80+", "je 100", 0, 100),
        Kennzahl("beratungsstellen", "Pflegeberatungsstellen", "Anzahl", 0, 500, ganzzahl=True),
        Kennzahl("ehrenamtliche_je_1000", "Ehrenamtliche in der Nachbarschaftshilfe je 1.000 Einwohner", "je 1.000", 0, 1000),
    ]
}

# Für den Benchmark: Richtung, in der ein Wert ungünstig ist.
UNGUENSTIG_WENN = {
    "anteil_80plus_pct": "hoch",
    "pflegebeduerftige_je_1000": "hoch",
    "stationaere_plaetze_je_100_80plus": "niedrig",
    "beratungsstellen": "niedrig",
    "ehrenamtliche_je_1000": "niedrig",
}

KOMMUNE_TYPEN = {"Kreisstadt", "Kleinstadt", "Landgemeinde"}


@dataclass
class Kommune:
    kommune_id: str
    name: str
    typ: str
    werte: dict[str, float]


@dataclass
class Befund:
    """Ergebnis einer Prüfregel für eine Zeile."""

    zeile: int
    kommune_id: Optional[str]
    regel: str
    schwere: str  # "fehler" verwirft die Zeile, "hinweis" wird übernommen und markiert
    meldung: str


@dataclass
class Datenstand:
    """Versionierter, unveränderlicher Stand einer importierten Quelle."""

    datenstand_id: str
    quelle: str
    stichtag: str
    importiert_am: str
    inhalt_hash: str
    kommunen: dict[str, Kommune] = field(default_factory=dict)
    befunde: list[Befund] = field(default_factory=list)
    vorgaenger_id: Optional[str] = None

    @property
    def anzahl_fehler(self) -> int:
        return sum(1 for b in self.befunde if b.schwere == "fehler")

    @property
    def anzahl_hinweise(self) -> int:
        return sum(1 for b in self.befunde if b.schwere == "hinweis")


@dataclass
class Massnahme:
    massnahme_id: str
    titel: str
    handlungsfeld: str
    indikator: str
    richtung: str
    min_einwohner: int
    text: str
    quelle: str
    typen: tuple[str, ...] = ()  # leer = für alle Kommunentypen geeignet


@dataclass
class Abschnitt:
    """Textabschnitt im Wissensspeicher."""

    abschnitt_id: str
    massnahme_id: str
    titel: str
    text: str
    quelle: str
    vektor: list[float] = field(default_factory=list)
