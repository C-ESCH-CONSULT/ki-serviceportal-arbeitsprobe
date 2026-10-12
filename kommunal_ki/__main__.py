"""Kommandozeilen-Demo ohne Server und Datenbank: python -m kommunal_ki"""
from __future__ import annotations

import argparse

from .dienst import DATEN, Dienst


def main() -> None:
    p = argparse.ArgumentParser(description="KI-Serviceportal – Prototyp")
    p.add_argument("--kommune", default="K09", help="Kommune für Benchmark und Matching")
    p.add_argument("--frage", default="Was braucht man für einen Pflegestützpunkt?")
    a = p.parse_args()

    d = Dienst()
    for datei, stichtag in [("kennzahlen_2024.csv", "2024-12-31"), ("kennzahlen_2025.csv", "2025-12-31")]:
        s = d.importieren((DATEN / datei).read_text(encoding="utf-8"), "pflegestatistik", stichtag)
        print(f"Import {datei}: Datenstand {s.datenstand_id}, {len(s.kommunen)} Kommunen, "
              f"{s.anzahl_fehler} Fehler, {s.anzahl_hinweise} Hinweise")

    b = d.benchmark(a.kommune)
    print(f"\nBenchmark {b['name']} (Vergleichsgruppe {b['vergleichsgruppe']}, n={b['gruppengroesse']}, "
          f"Datenstand {b['datenstand_id']})")
    for e in b["einordnungen"]:
        markierung = "  ← Bedarf" if e["unguenstig"] else ""
        print(f"  {e['bezeichnung']}: {e['wert']} (Median {e['median_gruppe']}, Perzentil {e['perzentil']}){markierung}")

    m = d.massnahmen(a.kommune)
    print("\nVorgeschlagene Maßnahmen")
    for v in m["vorschlaege"]:
        print(f"  {v['massnahme_id']} {v['titel']} (Punktzahl {v['punktzahl']})")
        for g in v["begruendung"]:
            print(f"     · {g}")

    f = d.fragen(a.frage)
    print(f"\nFrage: {f['frage']}\nAntwort: {f['text']}")
    for q in f["quellen"]:
        print(f"  [{q['nummer']}] {q['titel']} ({q['datei']}, Abschnitt {q['abschnitt_id']}, Ähnlichkeit {q['aehnlichkeit']})")
    e = d.protokoll(1)[0]
    print(f"\nProtokoll: Aufruf {e['aufruf_id']} ({e['status']}), Modell {e['modell']} {e['modell_version']}, "
          f"Prompt {e['prompt_id']} v{e['prompt_version']} ({e['prompt_hash']}), Datenstand {e['datenstand_id']}, "
          f"Quellen {', '.join(e['quellen']) or 'keine'}")


if __name__ == "__main__":
    main()
