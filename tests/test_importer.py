import unittest
from datetime import datetime, timezone
from pathlib import Path

from kommunal_ki.importer import KennzahlenImporter, SchemaFehler

DATEN = Path(__file__).resolve().parent.parent / "data"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
JETZT = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)


def lesen(pfad: Path) -> str:
    return pfad.read_text(encoding="utf-8")


class ImporterTest(unittest.TestCase):
    def test_gueltige_datei_ohne_befunde(self):
        stand = KennzahlenImporter("pflegestatistik", "2025-12-31").importieren(lesen(DATEN / "kennzahlen_2025.csv"), jetzt=JETZT)
        self.assertEqual(len(stand.kommunen), 12)
        self.assertEqual(stand.anzahl_fehler, 0)
        self.assertEqual(stand.kommunen["K01"].werte["anteil_80plus_pct"], 7.4)

    def test_datenstand_ist_reproduzierbar(self):
        inhalt = lesen(DATEN / "kennzahlen_2025.csv")
        a = KennzahlenImporter("pflegestatistik", "2025-12-31").importieren(inhalt, jetzt=JETZT)
        b = KennzahlenImporter("pflegestatistik", "2025-12-31").importieren(inhalt, jetzt=JETZT)
        self.assertEqual(a.datenstand_id, b.datenstand_id)
        c = KennzahlenImporter("pflegestatistik", "2025-12-31").importieren(inhalt.replace("7,4", "7,5"), jetzt=JETZT)
        self.assertNotEqual(a.datenstand_id, c.datenstand_id)

    def test_pruefregeln_verwerfen_fehlerhafte_zeilen(self):
        stand = KennzahlenImporter("test", "2025-12-31").importieren(lesen(FIXTURES / "kennzahlen_fehlerhaft.csv"), jetzt=JETZT)
        self.assertEqual(sorted(stand.kommunen), ["K01", "K08"])
        regeln = {(b.kommune_id, b.regel) for b in stand.befunde if b.schwere == "fehler"}
        self.assertIn(("K02", "wertebereich"), regeln)      # unbekannter Typ
        self.assertIn(("K03", "wertebereich"), regeln)      # Anteil über 100 %
        self.assertIn(("K04", "vollstaendigkeit"), regeln)  # Wert fehlt
        self.assertIn(("K05", "format"), regeln)            # Kommazahl bei Anzahl
        self.assertIn(("K06", "format"), regeln)            # keine Zahl
        self.assertIn(("K01", "eindeutigkeit"), regeln)     # doppelte Zeile
        self.assertIn(("K07", "pflichtfeld"), regeln)       # Name fehlt

    def test_fehlende_spalte_lehnt_datei_ab(self):
        inhalt = "kommune_id;name;typ\nK01;A;Kreisstadt\n"
        with self.assertRaises(SchemaFehler):
            KennzahlenImporter("test", "2025-12-31").importieren(inhalt)

    def test_abgleich_mit_vorgaenger_meldet_spruenge(self):
        imp = KennzahlenImporter("pflegestatistik", "2025-12-31")
        alt = KennzahlenImporter("pflegestatistik", "2024-12-31").importieren(lesen(DATEN / "kennzahlen_2024.csv"), jetzt=JETZT)
        inhalt = lesen(DATEN / "kennzahlen_2025.csv").replace("K01;Kommune A;Kreisstadt;34120;7,4;52,1;14,2;3",
                                                              "K01;Kommune A;Kreisstadt;34120;7,4;52,1;14,2;6")
        neu = imp.importieren(inhalt, vorgaenger=alt, jetzt=JETZT)
        self.assertEqual(neu.vorgaenger_id, alt.datenstand_id)
        hinweise = [b for b in neu.befunde if b.regel == "abgleich"]
        self.assertTrue(any(b.kommune_id == "K01" and "beratungsstellen" in b.meldung for b in hinweise))
        self.assertIn("K01", neu.kommunen)  # Hinweise verwerfen nichts


if __name__ == "__main__":
    unittest.main()
