import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from kommunal_ki.gateway import LLMGateway, LokalerExtraktiverAnbieter, Protokoll
from kommunal_ki.prompts import KEINE_ANGABEN, holen
from kommunal_ki.wissen import Wissensspeicher

DATEN = Path(__file__).resolve().parent.parent / "data"


class FesterAnbieter:
    name, modell, modell_version = "test", "fest", "1"

    def __init__(self, ausgabe="", fehler=None):
        self.ausgabe, self.fehler, self.aufrufe = ausgabe, fehler, 0

    def erzeugen(self, prompt, quellen, frage):
        self.aufrufe += 1
        if self.fehler:
            raise self.fehler
        return self.ausgabe


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

    def test_ohne_grundlage_wird_kein_modell_aufgerufen(self):
        anbieter = FesterAnbieter("Erfundene Antwort. [1]")
        gw = LLMGateway(anbieter)
        a = self.wissen.fragen("Wie beantrage ich einen Reisepass?", gw)
        self.assertEqual(anbieter.aufrufe, 0)
        self.assertEqual((a.text, a.quellen, a.beantwortet), (KEINE_ANGABEN, [], False))
        e = gw.protokoll.eintraege[-1]
        self.assertEqual((e.aufruf_id, e.status, e.quellen), (a.aufruf_id, "keine_grundlage", []))
        self.assertIn(KEINE_ANGABEN, holen("antwort_mit_quellen", "2").text)

    def test_ungueltige_zitate_gelten_nicht_als_antwort(self):
        for ausgabe in ("Die Kosten trägt das Land. [4]", "Nötig sind Räume. [1] Die Kosten trägt das Land. [4]"):
            a = self.wissen.fragen("Was braucht man für einen Pflegestützpunkt?", LLMGateway(FesterAnbieter(ausgabe)))
            with self.subTest(ausgabe=ausgabe):
                self.assertEqual(len(a.quellen), 3)
                self.assertFalse(a.beantwortet)
                self.assertEqual(a.ungueltige_zitate, [4])

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
        self.assertEqual(eintrag["status"], "ok")
        self.assertNotIn("Pflegekurse", json.dumps(eintrag))  # keine Inhalte im Protokoll

    def test_wissensstand_steht_im_protokoll(self):
        gw = self.neues_gateway()
        a = self.wissen.fragen("Wer bezahlt Pflegekurse für Angehörige?", gw)
        self.assertEqual(gw.protokoll.eintraege[-1].datenstand_id, a.datenstand_id)
        self.assertEqual(Wissensspeicher().laden(DATEN / "massnahmen").wissensstand_id, a.datenstand_id)
        geaendert = Wissensspeicher()
        for m in self.wissen.massnahmen.values():
            geaendert.hinzufuegen(replace(m, text=m.text + " Neu.") if m.massnahme_id == "M01" else m)
        self.assertNotEqual(geaendert.wissensstand_id, a.datenstand_id)

    def test_fehlgeschlagener_aufruf_wird_protokolliert(self):
        gw = LLMGateway(FesterAnbieter(fehler=TimeoutError("Zeitlimit überschritten")))
        with self.assertRaises(TimeoutError):
            self.wissen.fragen("Was braucht man für einen Pflegestützpunkt?", gw)
        e = gw.protokoll.eintraege[-1]
        self.assertEqual((e.status, e.fehlerklasse, e.ausgabe_hash), ("fehler", "TimeoutError", ""))
        self.assertTrue(e.quellen)

    def test_prompt_versionen_sind_abrufbar(self):
        v1, v2 = holen("antwort_mit_quellen", "1"), holen("antwort_mit_quellen", "2")
        self.assertNotEqual(v1.hash, v2.hash)
        self.assertEqual(holen("antwort_mit_quellen").version, "2")


if __name__ == "__main__":
    unittest.main()
