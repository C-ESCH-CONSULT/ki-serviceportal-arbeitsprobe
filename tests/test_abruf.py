import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from kommunal_ki.abruf import Abrufer, AbrufVerboten
from kommunal_ki.dienst import Dienst

DATEN = Path(__file__).resolve().parent.parent / "data"
ROBOTS = "User-agent: *\nDisallow: /intern/\nCrawl-delay: 2\n"


class Quelle(BaseHTTPRequestHandler):
    abrufe: list = []

    def do_GET(self):
        Quelle.abrufe.append(self.path)
        inhalte = {"/robots.txt": ROBOTS.encode(), "/kennzahlen.csv": (DATEN / "kennzahlen_2025.csv").read_bytes(),
                   "/intern/kennzahlen.csv": b"geheim"}
        if self.path not in inhalte:
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(inhalte[self.path])

    def log_message(self, *args):
        pass


class AbrufTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Quelle)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.basis = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Quelle.abrufe.clear()
        self.pausen = []
        self.abrufer = Abrufer(mindestabstand_s=0.5, schlafen=self.pausen.append)

    def test_gesperrter_pfad_wird_nicht_abgerufen(self):
        with self.assertRaises(AbrufVerboten):
            self.abrufer.holen(f"{self.basis}/intern/kennzahlen.csv")
        self.assertEqual(Quelle.abrufe, ["/robots.txt"])

    def test_crawl_delay_wird_eingehalten(self):
        self.abrufer.holen(f"{self.basis}/kennzahlen.csv")
        self.abrufer.holen(f"{self.basis}/kennzahlen.csv")
        self.assertEqual(Quelle.abrufe.count("/robots.txt"), 1)
        self.assertEqual(len(self.pausen), 1)
        self.assertGreater(self.pausen[0], 1.5)  # Crawl-delay 2 s statt Mindestabstand 0,5 s

    def test_nicht_erreichbare_robots_txt_sperrt_abruf(self):
        self.assertFalse(self.abrufer.erlaubt("http://127.0.0.1:1/kennzahlen.csv"))

    def test_abruf_und_import(self):
        stand = Dienst().abrufen(f"{self.basis}/kennzahlen.csv", "pflegestatistik", "2025-12-31", self.abrufer)
        self.assertEqual((len(stand.kommunen), stand.anzahl_fehler), (12, 0))


if __name__ == "__main__":
    unittest.main()
