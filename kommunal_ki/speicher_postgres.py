"""Ablage der Datenstände in PostgreSQL (Schema siehe db/schema.sql)."""
from __future__ import annotations

import json
from typing import Optional

import psycopg

from .models import Befund, Datenstand, Kommune


class PostgresSpeicher:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _verbindung(self) -> psycopg.Connection:
        return psycopg.connect(self.dsn)

    def speichern(self, stand: Datenstand) -> None:
        with self._verbindung() as con, con.cursor() as cur:
            cur.execute(
                """INSERT INTO datenstand (datenstand_id, quelle, stichtag, importiert_am, inhalt_hash, vorgaenger_id)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (datenstand_id) DO NOTHING""",
                (stand.datenstand_id, stand.quelle, stand.stichtag, stand.importiert_am, stand.inhalt_hash,
                 stand.vorgaenger_id))
            if cur.rowcount == 0:
                return  # identischer Datenstand existiert bereits
            cur.executemany(
                "INSERT INTO kommune_wert (datenstand_id, kommune_id, name, typ, werte) VALUES (%s, %s, %s, %s, %s)",
                [(stand.datenstand_id, k.kommune_id, k.name, k.typ, json.dumps(k.werte)) for k in stand.kommunen.values()])
            cur.executemany(
                """INSERT INTO pruefbefund (datenstand_id, zeile, kommune_id, regel, schwere, meldung)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [(stand.datenstand_id, b.zeile, b.kommune_id, b.regel, b.schwere, b.meldung) for b in stand.befunde])

    def _laden(self, cur: psycopg.Cursor, zeile: tuple) -> Datenstand:
        stand = Datenstand(zeile[0], zeile[1], str(zeile[2]), zeile[3].isoformat(), zeile[4], vorgaenger_id=zeile[5])
        cur.execute("SELECT kommune_id, name, typ, werte FROM kommune_wert WHERE datenstand_id = %s", (stand.datenstand_id,))
        for kid, name, typ, werte in cur.fetchall():
            stand.kommunen[kid] = Kommune(kid, name, typ, werte if isinstance(werte, dict) else json.loads(werte))
        cur.execute("SELECT zeile, kommune_id, regel, schwere, meldung FROM pruefbefund WHERE datenstand_id = %s",
                    (stand.datenstand_id,))
        stand.befunde = [Befund(*z) for z in cur.fetchall()]
        return stand

    _SPALTEN = "datenstand_id, quelle, stichtag, importiert_am, inhalt_hash, vorgaenger_id"

    def holen(self, datenstand_id: str) -> Optional[Datenstand]:
        with self._verbindung() as con, con.cursor() as cur:
            cur.execute(f"SELECT {self._SPALTEN} FROM datenstand WHERE datenstand_id = %s", (datenstand_id,))
            zeile = cur.fetchone()
            return self._laden(cur, zeile) if zeile else None

    def aktuell(self, quelle: Optional[str] = None) -> Optional[Datenstand]:
        with self._verbindung() as con, con.cursor() as cur:
            cur.execute(f"""SELECT {self._SPALTEN} FROM datenstand WHERE (%s::text IS NULL OR quelle = %s)
                            ORDER BY stichtag DESC, importiert_am DESC LIMIT 1""", (quelle, quelle))
            zeile = cur.fetchone()
            return self._laden(cur, zeile) if zeile else None

    def alle(self) -> list[Datenstand]:
        with self._verbindung() as con, con.cursor() as cur:
            cur.execute(f"SELECT {self._SPALTEN} FROM datenstand ORDER BY stichtag, importiert_am")
            return [self._laden(cur, z) for z in cur.fetchall()]


class PgVectorIndex:
    """Vektorsuche über pgvector. Wird vom Wissensspeicher genutzt, wenn eine Datenbank konfiguriert ist."""

    def __init__(self, dsn: str):
        self.dsn = dsn

    @staticmethod
    def _vektor(v: list[float]) -> str:
        return "[" + ",".join(f"{x:.6f}" for x in v) + "]"

    def einspielen(self, abschnitte: list, embedder_name: str, embedder_version: str) -> None:
        with psycopg.connect(self.dsn) as con, con.cursor() as cur:
            cur.executemany(
                """INSERT INTO wissen_abschnitt
                   (abschnitt_id, massnahme_id, titel, text, quelle, embedder, embedder_version, vektor)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                   ON CONFLICT (abschnitt_id) DO UPDATE SET text = EXCLUDED.text, vektor = EXCLUDED.vektor,
                       embedder = EXCLUDED.embedder, embedder_version = EXCLUDED.embedder_version""",
                [(a.abschnitt_id, a.massnahme_id, a.titel, a.text, a.quelle, embedder_name, embedder_version,
                  self._vektor(a.vektor)) for a in abschnitte])

    def suchen(self, vektor: list[float], k: int) -> list[tuple[str, float]]:
        with psycopg.connect(self.dsn) as con, con.cursor() as cur:
            cur.execute("""SELECT abschnitt_id, 1 - (vektor <=> %s::vector) AS aehnlichkeit
                           FROM wissen_abschnitt ORDER BY vektor <=> %s::vector LIMIT %s""",
                        (self._vektor(vektor), self._vektor(vektor), k))
            return [(aid, float(s)) for aid, s in cur.fetchall()]


class PostgresProtokoll:
    """Schreibt jeden Modellaufruf zusätzlich in die Tabelle modellaufruf."""

    def __init__(self, dsn: str, basis):
        self.dsn = dsn
        self.basis = basis  # Protokoll im Arbeitsspeicher bzw. als Datei

    @property
    def eintraege(self):
        return self.basis.eintraege

    def schreiben(self, e) -> None:
        self.basis.schreiben(e)
        with psycopg.connect(self.dsn) as con, con.cursor() as cur:
            cur.execute(
                """INSERT INTO modellaufruf (aufruf_id, zeitpunkt, anbieter, modell, modell_version, prompt_id,
                       prompt_version, prompt_hash, eingabe_hash, ausgabe_hash, quellen, datenstand_id, dauer_ms, zweck)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (e.aufruf_id, e.zeitpunkt, e.anbieter, e.modell, e.modell_version, e.prompt_id, e.prompt_version,
                 e.prompt_hash, e.eingabe_hash, e.ausgabe_hash, e.quellen, e.datenstand_id, e.dauer_ms, e.zweck))
