"""REST-Schnittstelle (FastAPI), OpenAPI-Dokumentation unter /docs."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from . import __version__
from .dienst import MAX_PROTOKOLLEINTRAEGE, Dienst, gateway_aus_umgebung
from .importer import SchemaFehler

app = FastAPI(
    title="KI-Serviceportal – Prototyp",
    version=__version__,
    description="Datenpipeline, Benchmark, Wissensspeicher mit Quellenangabe und Matching von Bedarfen zu Maßnahmen.",
)


def _dienst_erzeugen() -> Dienst:
    protokoll = Path(os.getenv("PROTOKOLL_DATEI", "protokoll/modellaufrufe.jsonl"))
    gateway = gateway_aus_umgebung(protokoll)
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return Dienst(gateway=gateway)
    from .speicher_postgres import PgVectorIndex, PostgresProtokoll, PostgresSpeicher
    dienst = Dienst(speicher=PostgresSpeicher(dsn), gateway=gateway)
    index = PgVectorIndex(dsn)
    index.einspielen(dienst.wissen.abschnitte, dienst.wissen.embedder.name, dienst.wissen.embedder.version)
    dienst.wissen.index = index
    gateway.protokoll = PostgresProtokoll(dsn, gateway.protokoll)
    return dienst


dienst = _dienst_erzeugen()


class FrageEingabe(BaseModel):
    frage: str = Field(min_length=3, max_length=500)
    prompt_version: Optional[str] = None


@app.get("/gesundheit")
def gesundheit() -> dict:
    return {"status": "ok", "version": __version__, "modell": dienst.gateway.anbieter.modell}


@app.post("/importe", status_code=201)
async def importieren(datei: UploadFile = File(...), quelle: str = Form(...), stichtag: str = Form(...)) -> dict:
    try:
        inhalt = (await datei.read()).decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise HTTPException(422, "Datei ist nicht UTF-8-kodiert") from e
    try:
        stand = dienst.importieren(inhalt, quelle, stichtag)
    except SchemaFehler as e:
        raise HTTPException(422, str(e)) from e
    return {"datenstand_id": stand.datenstand_id, "vorgaenger_id": stand.vorgaenger_id,
            "kommunen": len(stand.kommunen), "fehler": stand.anzahl_fehler, "hinweise": stand.anzahl_hinweise,
            "befunde": [b.__dict__ for b in stand.befunde]}


@app.get("/datenstaende")
def datenstaende() -> list[dict]:
    return [{"datenstand_id": s.datenstand_id, "quelle": s.quelle, "stichtag": s.stichtag,
             "importiert_am": s.importiert_am, "kommunen": len(s.kommunen)} for s in dienst.speicher.alle()]


@app.get("/kommunen/{kommune_id}/benchmark")
def benchmark(kommune_id: str, datenstand_id: Optional[str] = None) -> dict:
    try:
        return dienst.benchmark(kommune_id, datenstand_id)
    except (KeyError, LookupError) as e:
        raise HTTPException(404, f"Nicht gefunden: {e}") from e


@app.get("/kommunen/{kommune_id}/massnahmen")
def massnahmen(kommune_id: str, datenstand_id: Optional[str] = None) -> dict:
    try:
        return dienst.massnahmen(kommune_id, datenstand_id)
    except (KeyError, LookupError) as e:
        raise HTTPException(404, f"Nicht gefunden: {e}") from e


@app.post("/fragen")
def fragen(eingabe: FrageEingabe) -> dict:
    return dienst.fragen(eingabe.frage, eingabe.prompt_version)


@app.get("/protokoll")
def protokoll(letzte: int = Query(50, ge=1, le=MAX_PROTOKOLLEINTRAEGE)) -> list[dict]:
    return dienst.protokoll(letzte)
