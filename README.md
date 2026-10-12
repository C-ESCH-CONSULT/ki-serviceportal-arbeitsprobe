# KI-Serviceportal – Arbeitsprobe

Christopher Eschenweck · ESCH-CONSULT · info@esch-consult.de

Diese Arbeitsprobe zeigt in kleinem Maßstab die Bausteine, die ein KI-gestütztes Serviceportal für Kommunen braucht: Kennzahlen aus öffentlichen Quellen importieren und prüfen, Kommunen vergleichen, eine Maßnahmensammlung mit Quellenangabe befragen und passende Maßnahmen zu erkannten Bedarfen vorschlagen. Jeder Modellaufruf wird nachvollziehbar protokolliert.

Die Daten sind **synthetische Beispieldaten**. Ihre Struktur ist an amtliche Pflegestatistiken angelehnt, die Werte sind erfunden.

## Schnellstart

Ohne Installation, nur mit Python 3.11 oder neuer:

```bash
python -m kommunal_ki                 # Import, Benchmark, Matching und eine Wissensfrage
python -m kommunal_ki --kommune K07 --frage "Wer bezahlt Pflegekurse für Angehörige?"
python -m unittest discover -s tests  # Tests (API-Tests laufen, sobald FastAPI installiert ist)
```

Mit Datenbank und API:

```bash
docker compose up --build
# OpenAPI-Dokumentation: http://localhost:8000/docs
curl -F datei=@data/kennzahlen_2025.csv -F quelle=pflegestatistik -F stichtag=2025-12-31 http://localhost:8000/importe
curl http://localhost:8000/kommunen/K09/massnahmen
curl -H "Content-Type: application/json" -d '{"frage":"Was braucht man für einen Pflegestützpunkt?"}' http://localhost:8000/fragen
curl http://localhost:8000/protokoll
```

## Was die Arbeitsprobe zeigt

| Anforderung | Umsetzung | Datei |
| --- | --- | --- |
| Importer für öffentliche Quellen mit Qualitätsprüfung | Festes Schema je Quelle, Prüfregeln für Pflichtfelder, Format (deutsches Zahlenformat; Mehrdeutiges wie `3.58` wird als Fehler gemeldet statt still umgedeutet), Wertebereich, Eindeutigkeit und Plausibilität. Fehler verwerfen die Zeile, Hinweise werden markiert. | `kommunal_ki/importer.py` |
| Regelmäßige Aktualisierung, nachvollziehbare Datenstände | Jeder Import erzeugt einen unveränderlichen Datenstand mit Inhalts-Hash und Verweis auf den Vorgänger. Sprünge über 30 % gegenüber dem Vorgänger werden gemeldet. | `importer.py`, `speicher.py` |
| Benchmark der Kommunen | Einordnung innerhalb der Vergleichsgruppe (Kreisstadt, Kleinstadt, Landgemeinde) mit Median und Perzentil, immer bezogen auf einen Datenstand. | `benchmark.py` |
| Sprachmodelle über ein Gateway | Alle Aufrufe laufen über `LLMGateway`. Protokolliert werden Anbieter, Modell, Modellversion, Prompt-ID, Prompt-Version und -Hash, Quellen, Datenstand sowie Hashes von Ein- und Ausgabe, aber keine Inhalte. Fehlgeschlagene Aufrufe werden ebenfalls protokolliert (Status und Fehlerklasse), bevor der Fehler weitergereicht wird. | `gateway.py` |
| Versionierung von Prompts | Prompt-Vorlagen sind versioniert und per Hash eindeutig. Ältere Versionen bleiben abrufbar. | `prompts.py` |
| RAG-Wissensspeicher | Maßnahmen als Markdown mit Kopfdaten, Abschnitte mit Einbettung, Suche über pgvector (oder im Arbeitsspeicher). Jede Antwort nennt ihre Quellen; ohne ausreichende Grundlage gibt es keine inhaltliche Antwort. Wie ein Datenstand bekommt die Maßnahmensammlung eine Inhalts-ID (`massnahmen-…`), die bei jeder Wissensfrage als Datenstand im Protokoll steht. | `wissen.py`, `db/schema.sql` |
| Matching von Bedarfen zu Maßnahmen | Feste Regeln (Kennzahl, Richtung, Mindestgröße, Kommunentyp) plus inhaltliche Ähnlichkeit. Jeder Vorschlag nennt Kennzahlen, Regeln und Quellen. | `matching.py` |
| Selbst gehostete Modelle, Datenschutz | Ohne Konfiguration läuft alles lokal ohne externe Dienste. Über `LLM_BASIS_URL` lässt sich ein selbst gehostetes Modell mit OpenAI-kompatibler Schnittstelle anbinden, etwa vLLM oder Ollama im eigenen Rechenzentrum. | `gateway.py`, `dienst.py` |
| Offene Schnittstelle, automatisierte Tests | REST-API mit OpenAPI-Dokumentation, Tests für Import, Benchmark, Matching, Wissensfragen und API, CI mit Code-Prüfung und Integrationstest gegen PostgreSQL mit pgvector. | `api.py`, `tests/`, `.github/workflows/ci.yml` |

## Qualität der Antworten absichern

`data/testset_wissensfragen.json` enthält feste Fragen mit erwarteter Maßnahme und Begriffen, die in der Antwort vorkommen müssen. `data/testset_ohne_antwort.json` enthält Fragen, auf die das System keine inhaltliche Antwort geben darf. Beide laufen bei jeder Änderung in der CI. So fällt sofort auf, wenn eine neue Prompt-Version, ein anderes Modell oder geänderte Daten die Antwortqualität verschlechtern.

## Aufbau

```
kommunal_ki/
  importer.py           Importer und Prüfregeln
  speicher.py           Datenstände im Arbeitsspeicher
  speicher_postgres.py  Datenstände, pgvector-Suche und Aufrufprotokoll in PostgreSQL
  benchmark.py          Einordnung in die Vergleichsgruppe
  wissen.py             Wissensspeicher mit Quellenangabe
  matching.py           Bedarfe zu Maßnahmen
  gateway.py            LLM-Gateway mit Protokoll
  prompts.py            versionierte Prompt-Vorlagen
  embeddings.py         Einbettungen (lokal, austauschbar)
  dienst.py             Fachlogik, von API und Kommandozeile genutzt
  api.py                REST-API (FastAPI)
data/                   Beispieldaten, Maßnahmensammlung, Testsets
db/schema.sql           Datenbankschema
tests/                  automatisierte Tests
```

## Bewusste Vereinfachungen

* Die Einbettungen nutzen ein lokales Hashing-Verfahren ohne Modell-Download. Für den Produktivbetrieb wird über dieselbe Schnittstelle ein selbst gehostetes Embedding-Modell angebunden.
* Der lokale Antwortgeber bildet Antworten aus Sätzen der Quellen. Er dient als Rückfallebene und für reproduzierbare Tests; für ausformulierte Antworten wird ein Sprachmodell über das Gateway angebunden.
* Authentifizierung, Mandantentrennung und Betrieb hinter einem Reverse Proxy sind nicht Teil dieser Arbeitsprobe.
