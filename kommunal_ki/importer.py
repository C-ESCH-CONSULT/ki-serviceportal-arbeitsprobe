"""Importer für Kennzahlen-Tabellen mit Prüfregeln und versionierten Datenständen.

Jede Quelle bekommt einen eigenen Importer mit festem Schema. Prüfregeln laufen pro Zeile;
Fehler verwerfen die Zeile, Hinweise werden übernommen und im Datenstand protokolliert.
"""
from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timezone
from typing import Optional

from .models import KENNZAHLEN, KOMMUNE_TYPEN, Befund, Datenstand, Kommune

PFLICHTSPALTEN = ["kommune_id", "name", "typ", *KENNZAHLEN.keys()]

# Ab welcher Veränderung gegenüber dem Vorgänger-Datenstand ein Hinweis erzeugt wird.
SPRUNG_SCHWELLE = 0.30


class SchemaFehler(ValueError):
    """Die Datei passt nicht zum erwarteten Schema und wird insgesamt abgelehnt."""


def _zahl(text: str) -> float:
    return float(text.strip().replace(".", "").replace(",", ".")) if "," in text else float(text.strip())


def inhalt_hash(inhalt: str) -> str:
    return hashlib.sha256(inhalt.encode("utf-8")).hexdigest()


class KennzahlenImporter:
    """Importiert eine Semikolon-getrennte Kennzahlen-Tabelle (deutsches Zahlenformat)."""

    def __init__(self, quelle: str, stichtag: str):
        self.quelle = quelle
        self.stichtag = stichtag

    def importieren(self, inhalt: str, vorgaenger: Optional[Datenstand] = None,
                    jetzt: Optional[datetime] = None) -> Datenstand:
        jetzt = jetzt or datetime.now(timezone.utc)
        h = inhalt_hash(inhalt)
        stand = Datenstand(
            datenstand_id=f"{self.stichtag}-{h[:10]}",
            quelle=self.quelle,
            stichtag=self.stichtag,
            importiert_am=jetzt.isoformat(timespec="seconds"),
            inhalt_hash=h,
            vorgaenger_id=vorgaenger.datenstand_id if vorgaenger else None,
        )
        leser = csv.DictReader(io.StringIO(inhalt), delimiter=";")
        fehlend = [s for s in PFLICHTSPALTEN if s not in (leser.fieldnames or [])]
        if fehlend:
            raise SchemaFehler(f"Pflichtspalten fehlen: {', '.join(fehlend)}")

        for nr, zeile in enumerate(leser, start=2):  # Zeile 1 ist die Kopfzeile
            kommune = self._zeile_pruefen(nr, zeile, stand)
            if kommune is None:
                continue
            if kommune.kommune_id in stand.kommunen:
                stand.befunde.append(Befund(nr, kommune.kommune_id, "eindeutigkeit", "fehler",
                                            "Kommune doppelt enthalten, Zeile verworfen"))
                continue
            stand.kommunen[kommune.kommune_id] = kommune

        if vorgaenger:
            self._mit_vorgaenger_abgleichen(stand, vorgaenger)
        return stand

    def _zeile_pruefen(self, nr: int, zeile: dict, stand: Datenstand) -> Optional[Kommune]:
        kid = (zeile.get("kommune_id") or "").strip() or None
        fehler_vorher = stand.anzahl_fehler

        def melden(regel: str, schwere: str, meldung: str) -> None:
            stand.befunde.append(Befund(nr, kid, regel, schwere, meldung))

        if not kid:
            melden("pflichtfeld", "fehler", "kommune_id fehlt")
        if not (zeile.get("name") or "").strip():
            melden("pflichtfeld", "fehler", "name fehlt")
        typ = (zeile.get("typ") or "").strip()
        if typ not in KOMMUNE_TYPEN:
            melden("wertebereich", "fehler", f"unbekannter Typ '{typ}'")

        werte: dict[str, float] = {}
        for name, kz in KENNZAHLEN.items():
            roh = (zeile.get(name) or "").strip()
            if not roh:
                melden("vollstaendigkeit", "fehler", f"{name} fehlt")
                continue
            try:
                wert = _zahl(roh)
            except ValueError:
                melden("format", "fehler", f"{name}: '{roh}' ist keine Zahl")
                continue
            if kz.ganzzahl and wert != int(wert):
                melden("format", "fehler", f"{name}: ganze Zahl erwartet, '{roh}' erhalten")
                continue
            if not kz.minimum <= wert <= kz.maximum:
                melden("wertebereich", "fehler", f"{name}={wert} liegt außerhalb {kz.minimum}–{kz.maximum}")
                continue
            werte[name] = wert

        # Plausibilität über mehrere Felder
        if "pflegebeduerftige_je_1000" in werte and "anteil_80plus_pct" in werte:
            if werte["pflegebeduerftige_je_1000"] / 10 > werte["anteil_80plus_pct"] * 3:
                melden("plausibilitaet", "hinweis",
                       "Pflegequote ungewöhnlich hoch im Verhältnis zum Anteil 80+")

        if stand.anzahl_fehler > fehler_vorher:
            return None
        return Kommune(kid, zeile["name"].strip(), typ, werte)

    @staticmethod
    def _mit_vorgaenger_abgleichen(stand: Datenstand, vorgaenger: Datenstand) -> None:
        for kid, kommune in stand.kommunen.items():
            alt = vorgaenger.kommunen.get(kid)
            if not alt:
                stand.befunde.append(Befund(0, kid, "abgleich", "hinweis", "neu gegenüber Vorgänger-Datenstand"))
                continue
            for name, wert in kommune.werte.items():
                vorher = alt.werte.get(name)
                if vorher and abs(wert - vorher) / abs(vorher) > SPRUNG_SCHWELLE:
                    stand.befunde.append(Befund(
                        0, kid, "abgleich", "hinweis",
                        f"{name} ändert sich um {abs(wert - vorher) / abs(vorher):.0%} ({vorher} → {wert})"))
        for kid in vorgaenger.kommunen.keys() - stand.kommunen.keys():
            stand.befunde.append(Befund(0, kid, "abgleich", "hinweis", "fehlt im neuen Datenstand"))
