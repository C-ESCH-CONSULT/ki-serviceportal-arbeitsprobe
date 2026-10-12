"""API-Tests. Werden übersprungen, wenn FastAPI nicht installiert ist."""
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None

DATEN = Path(__file__).resolve().parent.parent / "data"


@unittest.skipIf(TestClient is None, "FastAPI nicht installiert")
class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kommunal_ki.api import app
        cls.client = TestClient(app)

    def test_ablauf(self):
        self.assertEqual(self.client.get("/gesundheit").json()["status"], "ok")
        r = self.client.post("/importe", data={"quelle": "pflegestatistik", "stichtag": "2025-12-31"},
                             files={"datei": ("k.csv", (DATEN / "kennzahlen_2025.csv").read_bytes(), "text/csv")})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["fehler"], 0)
        self.assertEqual(self.client.get("/kommunen/K09/benchmark").json()["vergleichsgruppe"], "Landgemeinde")
        self.assertTrue(self.client.get("/kommunen/K09/massnahmen").json()["vorschlaege"])
        a = self.client.post("/fragen", json={"frage": "Wer bezahlt Pflegekurse für Angehörige?"}).json()
        self.assertTrue(a["beantwortet"])
        self.assertEqual(self.client.get("/protokoll?letzte=1").json()[0]["aufruf_id"], a["aufruf_id"])
        self.assertEqual(self.client.get("/kommunen/XYZ/benchmark").status_code, 404)

    def test_schema_fehler_wird_abgelehnt(self):
        r = self.client.post("/importe", data={"quelle": "x", "stichtag": "2025-12-31"},
                             files={"datei": ("k.csv", b"kommune_id;name\nK1;A\n", "text/csv")})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
