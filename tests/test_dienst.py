import unittest
from pathlib import Path

from kommunal_ki.dienst import Dienst

DATEN = Path(__file__).resolve().parent.parent / "data"


class DienstTest(unittest.TestCase):
    def test_ende_zu_ende(self):
        d = Dienst()
        alt = d.importieren((DATEN / "kennzahlen_2024.csv").read_text(encoding="utf-8"), "pflegestatistik", "2024-12-31")
        neu = d.importieren((DATEN / "kennzahlen_2025.csv").read_text(encoding="utf-8"), "pflegestatistik", "2025-12-31")
        self.assertEqual(neu.vorgaenger_id, alt.datenstand_id)
        # Benchmark auf älterem Datenstand bleibt abrufbar und unverändert
        b_alt = d.benchmark("K09", alt.datenstand_id)
        self.assertEqual(b_alt["datenstand_id"], alt.datenstand_id)
        self.assertEqual(d.benchmark("K09")["datenstand_id"], neu.datenstand_id)
        m = d.massnahmen("K09")
        self.assertTrue(m["vorschlaege"])
        f = d.fragen("Was braucht man für einen Pflegestützpunkt?")
        self.assertTrue(f["beantwortet"])
        self.assertEqual(d.protokoll(1)[0]["aufruf_id"], f["aufruf_id"])

    def test_erneuter_import_gleicher_datei_erzeugt_keinen_neuen_stand(self):
        d = Dienst()
        inhalt = (DATEN / "kennzahlen_2025.csv").read_text(encoding="utf-8")
        d.importieren(inhalt, "pflegestatistik", "2025-12-31")
        d.importieren(inhalt, "pflegestatistik", "2025-12-31")
        self.assertEqual(len(d.speicher.alle()), 1)

    def test_protokollabruf_ist_begrenzt(self):
        d = Dienst()
        d.fragen("Was braucht man für einen Pflegestützpunkt?")
        self.assertEqual(len(d.protokoll(1)), 1)
        for letzte in (0, -1, 501):
            with self.subTest(letzte=letzte), self.assertRaises(ValueError):
                d.protokoll(letzte)


if __name__ == "__main__":
    unittest.main()
