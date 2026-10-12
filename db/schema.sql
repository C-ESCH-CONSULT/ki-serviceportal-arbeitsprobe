-- Schema für Datenstände, Prüfbefunde, Wissensspeicher und Protokoll der Modellaufrufe.
-- Wird beim ersten Start des Datenbank-Containers automatisch ausgeführt.

CREATE EXTENSION IF NOT EXISTS vector;

-- Unveränderliche Datenstände: jeder Import erzeugt einen neuen Stand.
CREATE TABLE IF NOT EXISTS datenstand (
    datenstand_id  text PRIMARY KEY,
    quelle         text        NOT NULL,
    stichtag       date        NOT NULL,
    importiert_am  timestamptz NOT NULL,
    inhalt_hash    text        NOT NULL,
    vorgaenger_id  text REFERENCES datenstand (datenstand_id)
);

CREATE TABLE IF NOT EXISTS kommune_wert (
    datenstand_id text  NOT NULL REFERENCES datenstand (datenstand_id),
    kommune_id    text  NOT NULL,
    name          text  NOT NULL,
    typ           text  NOT NULL,
    werte         jsonb NOT NULL,
    PRIMARY KEY (datenstand_id, kommune_id)
);

CREATE TABLE IF NOT EXISTS pruefbefund (
    id            bigserial PRIMARY KEY,
    datenstand_id text NOT NULL REFERENCES datenstand (datenstand_id),
    zeile         int  NOT NULL,
    kommune_id    text,
    regel         text NOT NULL,
    schwere       text NOT NULL CHECK (schwere IN ('fehler', 'hinweis')),
    meldung       text NOT NULL
);

CREATE TABLE IF NOT EXISTS wissen_abschnitt (
    abschnitt_id   text PRIMARY KEY,
    massnahme_id   text NOT NULL,
    titel          text NOT NULL,
    text           text NOT NULL,
    quelle         text NOT NULL,
    embedder       text NOT NULL,
    embedder_version text NOT NULL,
    vektor         vector(512) NOT NULL
);
CREATE INDEX IF NOT EXISTS wissen_abschnitt_vektor_idx
    ON wissen_abschnitt USING hnsw (vektor vector_cosine_ops);

-- Protokoll der Modellaufrufe: nur Hashes und Metadaten, keine Inhalte.
CREATE TABLE IF NOT EXISTS modellaufruf (
    aufruf_id      uuid PRIMARY KEY,
    zeitpunkt      timestamptz NOT NULL,
    anbieter       text NOT NULL,
    modell         text NOT NULL,
    modell_version text NOT NULL,
    prompt_id      text NOT NULL,
    prompt_version text NOT NULL,
    prompt_hash    text NOT NULL,
    eingabe_hash   text NOT NULL,
    ausgabe_hash   text NOT NULL,
    quellen        text[] NOT NULL,
    datenstand_id  text,
    dauer_ms       int  NOT NULL,
    zweck          text NOT NULL,
    status         text NOT NULL CHECK (status IN ('ok', 'fehler', 'keine_grundlage')),
    fehlerklasse   text
);
