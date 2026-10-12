"""LLM-Gateway mit Protokollierung jedes Modellaufrufs.

Alle Aufrufe laufen über ``LLMGateway.aufrufen``. Pro Aufruf werden Anbieter, Modell, Modellversion,
Prompt-ID, Prompt-Version und -Hash, die verwendeten Quellen, der Datenstand sowie Hashes von Eingabe
und Ausgabe protokolliert. Inhalte selbst werden nicht im Protokoll gespeichert (Datensparsamkeit).

Anbieter:
* ``LokalerExtraktiverAnbieter``: läuft ohne Modell, bildet Antworten aus Sätzen der Quellen.
  Gut für Tests und als Rückfallebene.
* ``OpenAIKompatiblerAnbieter``: für selbst gehostete Modelle mit OpenAI-kompatibler Schnittstelle
  (z. B. vLLM oder Ollama im eigenen Rechenzentrum in der EU).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol

from .embeddings import erweitern as _erweitern, tokens
from .prompts import PromptVorlage


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class Quelle:
    nummer: int
    quelle_id: str
    titel: str
    text: str


@dataclass
class Protokolleintrag:
    aufruf_id: str
    zeitpunkt: str
    anbieter: str
    modell: str
    modell_version: str
    prompt_id: str
    prompt_version: str
    prompt_hash: str
    eingabe_hash: str
    ausgabe_hash: str
    quellen: list[str]
    datenstand_id: Optional[str]
    dauer_ms: int
    zweck: str


class Anbieter(Protocol):
    name: str
    modell: str
    modell_version: str

    def erzeugen(self, prompt: str, quellen: list[Quelle], frage: str) -> str: ...


# Wörter, die in Fragen eine Absicht anzeigen, im Text aber meist anders gemeint sind.
NUR_IN_FRAGEN = {"bringt", "bringen"}


class LokalerExtraktiverAnbieter:
    """Bildet eine Antwort aus den passendsten Sätzen der Quellen, jeweils mit Quellenangabe."""

    name = "lokal"
    modell = "extraktiv"
    modell_version = "1.1"

    def __init__(self, max_saetze: int = 2, relative_schwelle: float = 0.6):
        self.max_saetze = max_saetze
        self.relative_schwelle = relative_schwelle

    def erzeugen(self, prompt: str, quellen: list[Quelle], frage: str) -> str:
        original = set(tokens(frage))
        fachbegriffe = _erweitern(original) - original  # z. B. "kosten" zu "bezahlt"
        frage_tokens = original | fachbegriffe
        kandidaten = []
        haupt = quellen[0].quelle_id.split("-")[0] if quellen else None
        for q in quellen:
            titel_tokens = set(tokens(q.titel))
            fremd_abzug = 0.0 if q.quelle_id.split("-")[0] == haupt else 0.6  # bei der passendsten Maßnahme bleiben
            rang_bonus = 0.3 * (len(quellen) - q.nummer)  # besser gefundene Quellen leicht bevorzugen
            for pos, satz in enumerate(re.split(r"(?<=[.!?])\s+", q.text)):
                satz = satz.strip()
                if len(satz) < 25:
                    continue
                satz_tokens = set(tokens(satz)) - NUR_IN_FRAGEN
                direkt = len(original & satz_tokens) + 1.5 * len(fachbegriffe & satz_tokens)
                if direkt == 0:
                    continue
                aehnlich = sum(1 for f in original for t in satz_tokens if f != t and f[:5] == t[:5])
                punkte = (direkt + 0.5 * aehnlich + 0.5 * len(frage_tokens & titel_tokens) + rang_bonus
                          + (0.2 if pos == 0 else 0.0) - fremd_abzug)
                kandidaten.append((punkte, -q.nummer, satz, q.nummer))
        if not kandidaten:
            return "Dazu enthält die Maßnahmensammlung keine Angaben."
        kandidaten.sort(reverse=True)
        beste = kandidaten[0][0]
        gewaehlt, gesehen = [], set()
        for punkte, _, satz, nr in kandidaten:
            if punkte < beste * self.relative_schwelle or satz in gesehen:
                continue
            gesehen.add(satz)
            gewaehlt.append(f"{satz} [{nr}]")
            if len(gewaehlt) == self.max_saetze:
                break
        return " ".join(gewaehlt)


class OpenAIKompatiblerAnbieter:
    """Anbindung an ein selbst gehostetes Modell mit OpenAI-kompatibler Chat-Schnittstelle."""

    name = "selbst-gehostet"

    def __init__(self, basis_url: str, modell: str, modell_version: str, api_schluessel: str = "",
                 zeitlimit_s: float = 30.0):
        self.basis_url = basis_url.rstrip("/")
        self.modell = modell
        self.modell_version = modell_version
        self.api_schluessel = api_schluessel
        self.zeitlimit_s = zeitlimit_s

    def erzeugen(self, prompt: str, quellen: list[Quelle], frage: str) -> str:
        nutzlast = json.dumps({
            "model": self.modell,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        anfrage = urllib.request.Request(
            f"{self.basis_url}/v1/chat/completions", data=nutzlast, method="POST",
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {self.api_schluessel}"} if self.api_schluessel else {})})
        with urllib.request.urlopen(anfrage, timeout=self.zeitlimit_s) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
        return daten["choices"][0]["message"]["content"].strip()


@dataclass
class Protokoll:
    """Speichert Protokolleinträge im Speicher und optional als JSON-Lines-Datei."""

    datei: Optional[Path] = None
    eintraege: list[Protokolleintrag] = field(default_factory=list)

    def schreiben(self, eintrag: Protokolleintrag) -> None:
        self.eintraege.append(eintrag)
        if self.datei:
            self.datei.parent.mkdir(parents=True, exist_ok=True)
            with self.datei.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(eintrag), ensure_ascii=False) + "\n")


class LLMGateway:
    def __init__(self, anbieter: Anbieter, protokoll: Optional[Protokoll] = None):
        self.anbieter = anbieter
        self.protokoll = protokoll or Protokoll()

    def aufrufen(self, vorlage: PromptVorlage, frage: str, quellen: list[Quelle],
                 datenstand_id: Optional[str] = None, zweck: str = "antwort") -> tuple[str, Protokolleintrag]:
        quellen_text = "\n".join(f"[{q.nummer}] {q.titel}: {q.text}" for q in quellen)
        prompt = vorlage.fuellen(quellen=quellen_text, frage=frage)
        start = time.perf_counter()
        ausgabe = self.anbieter.erzeugen(prompt, quellen, frage)
        dauer = int((time.perf_counter() - start) * 1000)
        eintrag = Protokolleintrag(
            aufruf_id=str(uuid.uuid4()),
            zeitpunkt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            anbieter=self.anbieter.name,
            modell=self.anbieter.modell,
            modell_version=self.anbieter.modell_version,
            prompt_id=vorlage.prompt_id,
            prompt_version=vorlage.version,
            prompt_hash=vorlage.hash,
            eingabe_hash=_h(prompt),
            ausgabe_hash=_h(ausgabe),
            quellen=[q.quelle_id for q in quellen],
            datenstand_id=datenstand_id,
            dauer_ms=dauer,
            zweck=zweck,
        )
        self.protokoll.schreiben(eintrag)
        return ausgabe, eintrag
