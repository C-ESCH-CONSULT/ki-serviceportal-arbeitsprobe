import json
import tempfile
import unittest
from pathlib import Path

from kommunal_ki.gateway import LLMGateway, LokalerExtraktiverAnbieter, Protokoll
from kommunal_ki.prompts import holen
from kommunal_ki.wissen import Wissensspeicher

DATEN = Path(__file__).resolve().parent.parent / "data"


class WissenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wissen = Wissensspeicher().laden(DATEN / "massnahmen")

    def neues_gateway(self, datei=None):
        return LLMGateway(LokalerExtraktiverAnbieter(), Protokoll(datei))

    def test_testset_trefferquote(self):
        """Festes Testset: die erwartete Maßnahme muss unter den ersten drei Treffern sein."""
        testset = json.loads((DATEN / "testset_wissensfragen.json").read_text(encoding="utf-8"))
        treffer = sum(any(t.abschnitt.massnahme_id == f["erwartete_massnahme"] for t in self.wissen.suchen(f["frage"], 3))
                      for f in testset)
        self.assertGreaterEqual(treffer / len(testset), 0.9, f"Trefferquote {treffer}/{len(testset)}")

    def test_testset_antwortinhalte(self):
        testset = json.loads((DATEN / "testset_wissensfragen.json").read_text(encoding="utf-8"))
        gw = self.neues_gateway()
        for f in testset:
            a = self.wissen.fragen(f["frage"], gw)
            with self.subTest(frage=f["frage"]):
                self.assertTrue(a.beantwortet)
                for wort in f["muss_enthalten"]:
                    self.assertIn(wort, a.text)

    def test_jede_aussage_hat_eine_quelle(self):
        gw = self.neues_gateway()
        a = self.wissen.fragen("Was braucht man für einen Pflegestützpunkt?", gw)
        saetze = [s for s in a.text.split("] ") if s.strip()]
        self.assertTrue(all("[" in s for s in saetze))
        self.assertTrue(any(q["zitiert"] for q in a.quellen))

    def test_keine_antwort_ohne_grundlage(self):
        gw = self.neues_gateway()
        for frage in json.loads((DATEN / "testset_ohne_antwort.json").read_text(encoding="utf-8")):
            a = self.wissen.fragen(frage, gw)
            with self.subTest(frage=frage):
                self.assertFalse(a.beantwortet)
                self.assertIn("keine Angaben", a.text)

    def test_protokoll_enthaelt_versionen_und_quellen(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "protokoll.jsonl"
            gw = self.neues_gateway(datei)
            a = self.wissen.fragen("Wer bezahlt Pflegekurse für Angehörige?", gw)
            eintrag = json.loads(datei.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(eintrag["aufruf_id"], a.aufruf_id)
        self.assertEqual(eintrag["prompt_id"], "antwort_mit_quellen")
        self.assertEqual(eintrag["prompt_version"], holen("antwort_mit_quellen").version)
        self.assertEqual(eintrag["prompt_hash"], holen("antwort_mit_quellen").hash)
        self.assertEqual(eintrag["modell_version"], LokalerExtraktiverAnbieter.modell_version)
        self.assertEqual(eintrag["quellen"], [q["abschnitt_id"] for q in a.quellen])
        self.assertNotIn("Pflegekurse", json.dumps(eintrag))  # keine Inhalte im Protokoll

    def test_prompt_versionen_sind_abrufbar(self):
        v1, v2 = holen("antwort_mit_quellen", "1"), holen("antwort_mit_quellen", "2")
        self.assertNotEqual(v1.hash, v2.hash)
        self.assertEqual(holen("antwort_mit_quellen").version, "2")


if __name__ == "__main__":
    unittest.main()
