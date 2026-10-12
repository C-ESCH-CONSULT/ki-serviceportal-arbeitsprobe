"""Wissensspeicher (RAG) für die Maßnahmen- und Methodensammlung.

Maßnahmen liegen als Markdown mit Kopfdaten vor. Sie werden in Abschnitte zerlegt, eingebettet und
über Vektorsuche abgefragt. Jede Antwort nennt ihre Quellen. Liegt kein Abschnitt über der
Mindestähnlichkeit, wird keine inhaltliche Antwort erzeugt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .embeddings import Embedder, HashingEmbedder, erweitern, kosinus, tokens
from .gateway import LLMGateway, Quelle
from .models import Abschnitt, Massnahme
from .prompts import holen

MINDEST_AEHNLICHKEIT = 0.12


def massnahme_lesen(pfad: Path) -> Massnahme:
    roh = pfad.read_text(encoding="utf-8")
    teile = re.match(r"^---\n(.*?)\n---\n(.*)$", roh, re.S)
    if not teile:
        raise ValueError(f"{pfad.name}: Kopfdaten fehlen")
    kopf = dict(z.split(":", 1) for z in teile.group(1).splitlines() if ":" in z)
    kopf = {k.strip(): v.strip() for k, v in kopf.items()}
    for pflicht in ("id", "titel", "handlungsfeld", "indikator", "richtung", "min_einwohner"):
        if pflicht not in kopf:
            raise ValueError(f"{pfad.name}: Feld '{pflicht}' fehlt")
    return Massnahme(kopf["id"], kopf["titel"], kopf["handlungsfeld"], kopf["indikator"], kopf["richtung"],
                     int(kopf["min_einwohner"]), teile.group(2).strip(), pfad.name,
                     tuple(t.strip() for t in kopf.get("typen", "").split(",") if t.strip()))


@dataclass
class Treffer:
    abschnitt: Abschnitt
    aehnlichkeit: float


@dataclass
class Antwort:
    frage: str
    text: str
    quellen: list[dict]
    aufruf_id: str
    beantwortet: bool


@dataclass
class Wissensspeicher:
    embedder: Embedder = field(default_factory=HashingEmbedder)
    massnahmen: dict[str, Massnahme] = field(default_factory=dict)
    abschnitte: list[Abschnitt] = field(default_factory=list)
    index: Optional[object] = None  # externe Vektorsuche, z. B. PgVectorIndex; sonst Suche im Arbeitsspeicher

    def laden(self, ordner: Path) -> "Wissensspeicher":
        for pfad in sorted(ordner.glob("*.md")):
            self.hinzufuegen(massnahme_lesen(pfad))
        return self

    def hinzufuegen(self, m: Massnahme) -> None:
        self.massnahmen[m.massnahme_id] = m
        for i, absatz in enumerate(a.strip() for a in m.text.split("\n\n") if a.strip()):
            text = f"{m.titel}. {absatz}"
            self.abschnitte.append(Abschnitt(f"{m.massnahme_id}-{i + 1}", m.massnahme_id, m.titel, absatz,
                                             m.quelle, self.embedder.einbetten(text)))

    def suchen(self, anfrage: str, k: int = 3) -> list[Treffer]:
        zusatz = erweitern(set(tokens(anfrage))) - set(tokens(anfrage))
        q = self.embedder.einbetten(anfrage + " " + " ".join(sorted(zusatz)))
        if self.index is not None:
            nach_id = {a.abschnitt_id: a for a in self.abschnitte}
            return [Treffer(nach_id[aid], s) for aid, s in self.index.suchen(q, k) if aid in nach_id]
        bewertet = sorted((Treffer(a, kosinus(q, a.vektor)) for a in self.abschnitte),
                          key=lambda t: t.aehnlichkeit, reverse=True)
        return bewertet[:k]

    def fragen(self, frage: str, gateway: LLMGateway, k: int = 3, prompt_version: Optional[str] = None) -> Antwort:
        treffer = [t for t in self.suchen(frage, k) if t.aehnlichkeit >= MINDEST_AEHNLICHKEIT]
        quellen = [Quelle(i + 1, t.abschnitt.abschnitt_id, t.abschnitt.titel, t.abschnitt.text)
                   for i, t in enumerate(treffer)]
        vorlage = holen("antwort_mit_quellen", prompt_version)
        text, eintrag = gateway.aufrufen(vorlage, frage, quellen, zweck="wissensfrage")
        zitiert = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
        return Antwort(
            frage=frage,
            text=text,
            quellen=[{"nummer": q.nummer, "abschnitt_id": q.quelle_id, "titel": q.titel,
                      "datei": self.massnahmen[q.quelle_id.split("-")[0]].quelle,
                      "aehnlichkeit": round(t.aehnlichkeit, 3), "zitiert": q.nummer in zitiert}
                     for q, t in zip(quellen, treffer)],
            aufruf_id=eintrag.aufruf_id,
            beantwortet=bool(zitiert),
        )
