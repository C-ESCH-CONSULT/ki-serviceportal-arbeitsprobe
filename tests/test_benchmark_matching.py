import unittest
from pathlib import Path

from kommunal_ki.benchmark import einordnen
from kommunal_ki.importer import KennzahlenImporter
from kommunal_ki.matching import vorschlagen
from kommunal_ki.wissen import Wissensspeicher

DATEN = Path(__file__).resolve().parent.parent / "data"


class BenchmarkMatchingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stand = KennzahlenImporter("pflegestatistik", "2025-12-31").importieren(
            (DATEN / "kennzahlen_2025.csv").read_text(encoding="utf-8"))
        cls.wissen = Wissensspeicher().laden(DATEN / "massnahmen")

    def test_vergleich_nur_innerhalb_der_gruppe(self):
        e = einordnen(self.stand, "K09")
        self.assertEqual(e.vergleichsgruppe, "Landgemeinde")
        self.assertEqual(e.gruppengroesse, 5)
        self.assertEqual(e.datenstand_id, self.stand.datenstand_id)

    def test_bedarfe_folgen_der_richtung_der_kennzahl(self):
        e = {x.kennzahl: x for x in einordnen(self.stand, "K09").einordnungen}
        self.assertTrue(e["anteil_80plus_pct"].unguenstig)                 # höchster Anteil 80+
        self.assertTrue(e["stationaere_plaetze_je_100_80plus"].unguenstig)  # wenigste Plätze
        self.assertFalse(e["ehrenamtliche_je_1000"].unguenstig)            # im Mittelfeld

    def test_vorschlaege_sind_begruendet_und_belegt(self):
        ergebnis = einordnen(self.stand, "K09")
        vorschlaege = vorschlagen(ergebnis, self.stand, self.wissen)
        self.assertTrue(vorschlaege)
        bedarfs_kennzahlen = {b.kennzahl for b in ergebnis.bedarfe}
        for v in vorschlaege:
            m = self.wissen.massnahmen[v.massnahme_id]
            self.assertIn(m.indikator, bedarfs_kennzahlen)
            self.assertTrue(any("Median" in g for g in v.begruendung))
            self.assertIn(f"Datenstand {self.stand.datenstand_id}", v.quellen)

    def test_harte_regeln_werden_eingehalten(self):
        # M04 (Tagespflege) erst ab 5.000 Einwohnern, M02 nicht für Kreisstädte
        for kid in self.stand.kommunen:
            ergebnis = einordnen(self.stand, kid)
            ids = {v.massnahme_id for v in vorschlagen(ergebnis, self.stand, self.wissen, max_vorschlaege=10)}
            if self.stand.kommunen[kid].werte["einwohner"] < 5000:
                self.assertNotIn("M04", ids, kid)
            if ergebnis.vergleichsgruppe == "Kreisstadt":
                self.assertNotIn("M02", ids, kid)


if __name__ == "__main__":
    unittest.main()
