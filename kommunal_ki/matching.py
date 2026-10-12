"""Matching von Bedarfen zu Maßnahmen: feste Regeln plus inhaltliche Ähnlichkeit."""
from __future__ import annotations

from dataclasses import dataclass

from .benchmark import BenchmarkErgebnis, Einordnung
from .embeddings import kosinus
from .models import Datenstand
from .wissen import Wissensspeicher

GEWICHT_REGEL = 0.6
GEWICHT_SEMANTIK = 0.4


@dataclass
class Vorschlag:
    massnahme_id: str
    titel: str
    punktzahl: float
    bedarf: str
    begruendung: list[str]
    quellen: list[str]


def _bedarf_text(e: Einordnung) -> str:
    lage = "hoch" if e.abweichung_pct > 0 else "niedrig"
    return f"{e.bezeichnung} ist {lage}: {e.wert} gegenüber Median {e.median_gruppe} der Vergleichsgruppe"


def vorschlagen(ergebnis: BenchmarkErgebnis, stand: Datenstand, wissen: Wissensspeicher,
                max_vorschlaege: int = 5) -> list[Vorschlag]:
    einwohner = stand.kommunen[ergebnis.kommune_id].werte["einwohner"]
    vorschlaege: dict[str, Vorschlag] = {}
    for bedarf in ergebnis.bedarfe:
        richtung = "hoch" if bedarf.abweichung_pct > 0 else "niedrig"
        bedarf_vektor = wissen.embedder.einbetten(_bedarf_text(bedarf))
        for m in wissen.massnahmen.values():
            regeln, regel_punkte = [], 0.0
            if m.indikator == bedarf.kennzahl:
                regel_punkte += 0.7
                regeln.append(f"adressiert die Kennzahl „{bedarf.bezeichnung}“")
            if m.richtung == richtung:
                regel_punkte += 0.3
            if einwohner < m.min_einwohner:
                continue
            if m.typen and ergebnis.vergleichsgruppe not in m.typen:
                continue
            if regel_punkte < 0.7:
                continue
            abschnitte = [a for a in wissen.abschnitte if a.massnahme_id == m.massnahme_id]
            semantik = max(kosinus(bedarf_vektor, a.vektor) for a in abschnitte)
            punktzahl = round(GEWICHT_REGEL * regel_punkte + GEWICHT_SEMANTIK * max(semantik, 0.0), 3)
            begruendung = [
                f"{bedarf.bezeichnung}: {bedarf.wert} (Median der Gruppe {ergebnis.vergleichsgruppe}: "
                f"{bedarf.median_gruppe}, Perzentil {bedarf.perzentil})",
                *regeln,
                *([f"Mindestgröße erfüllt ({int(einwohner)} ≥ {m.min_einwohner} Einwohner)"] if m.min_einwohner else []),
                *([f"geeignet für {', '.join(m.typen)}"] if m.typen else []),
                f"inhaltliche Nähe zum Bedarf {semantik:.2f}",
            ]
            quellen = [f"Datenstand {stand.datenstand_id}", f"Maßnahmensammlung {m.quelle}"]
            alt = vorschlaege.get(m.massnahme_id)
            if not alt or punktzahl > alt.punktzahl:
                vorschlaege[m.massnahme_id] = Vorschlag(m.massnahme_id, m.titel, punktzahl,
                                                         _bedarf_text(bedarf), begruendung, quellen)
    return sorted(vorschlaege.values(), key=lambda v: v.punktzahl, reverse=True)[:max_vorschlaege]
