"""Benchmark: Einordnung einer Kommune innerhalb ihrer Vergleichsgruppe.

Berechnungen beziehen sich immer auf einen konkreten Datenstand und sind damit reproduzierbar.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .models import KENNZAHLEN, UNGUENSTIG_WENN, Datenstand


@dataclass
class Einordnung:
    kennzahl: str
    bezeichnung: str
    wert: float
    median_gruppe: float
    perzentil: float          # 0 = niedrigster Wert der Gruppe, 100 = höchster
    abweichung_pct: float     # Abweichung vom Median in Prozent
    unguenstig: bool          # liegt im ungünstigsten Viertel der Gruppe


@dataclass
class BenchmarkErgebnis:
    kommune_id: str
    name: str
    vergleichsgruppe: str
    gruppengroesse: int
    datenstand_id: str
    einordnungen: list[Einordnung]

    @property
    def bedarfe(self) -> list[Einordnung]:
        return [e for e in self.einordnungen if e.unguenstig]


def _perzentil(wert: float, werte: list[float]) -> float:
    if len(werte) < 2:
        return 50.0
    kleiner = sum(1 for w in werte if w < wert)
    gleich = sum(1 for w in werte if w == wert)
    return round(100 * (kleiner + 0.5 * (gleich - 1)) / (len(werte) - 1), 1)


def einordnen(stand: Datenstand, kommune_id: str) -> BenchmarkErgebnis:
    kommune = stand.kommunen[kommune_id]
    gruppe = [k for k in stand.kommunen.values() if k.typ == kommune.typ]
    einordnungen = []
    for name, richtung in UNGUENSTIG_WENN.items():
        werte = [k.werte[name] for k in gruppe if name in k.werte]
        wert = kommune.werte[name]
        med = median(werte)
        p = _perzentil(wert, werte)
        unguenstig = len(werte) >= 3 and (p >= 75 if richtung == "hoch" else p <= 25)
        einordnungen.append(Einordnung(
            kennzahl=name,
            bezeichnung=KENNZAHLEN[name].bezeichnung,
            wert=wert,
            median_gruppe=round(med, 2),
            perzentil=p,
            abweichung_pct=round(100 * (wert - med) / med, 1) if med else 0.0,
            unguenstig=unguenstig,
        ))
    return BenchmarkErgebnis(kommune.kommune_id, kommune.name, kommune.typ, len(gruppe),
                             stand.datenstand_id, einordnungen)
