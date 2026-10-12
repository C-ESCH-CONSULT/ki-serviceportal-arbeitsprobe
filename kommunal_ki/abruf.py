"""Abruf öffentlicher Quellen unter Beachtung von robots.txt und einem Mindestabstand je Host."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "kommunal-ki/0.1 (+https://github.com/C-ESCH-CONSULT/ki-serviceportal-arbeitsprobe)"


class AbrufVerboten(PermissionError):
    """robots.txt untersagt den Abruf."""


class Abrufer:
    def __init__(self, user_agent: str = USER_AGENT, mindestabstand_s: float = 1.0, zeitlimit_s: float = 30.0,
                 schlafen: Callable[[float], None] = time.sleep):
        self.user_agent = user_agent
        self.mindestabstand_s = mindestabstand_s
        self.zeitlimit_s = zeitlimit_s
        self.schlafen = schlafen
        self._robots: dict[str, RobotFileParser] = {}
        self._letzter_abruf: dict[str, float] = {}

    def _laden(self, url: str) -> bytes:
        anfrage = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(anfrage, timeout=self.zeitlimit_s) as antwort:
            return antwort.read()

    def _regeln(self, host: str) -> RobotFileParser:
        if host not in self._robots:
            regeln = RobotFileParser(f"{host}/robots.txt")
            try:
                regeln.parse(self._laden(regeln.url).decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as e:
                # Wie RFC 9309: fehlende robots.txt erlaubt alles, Serverfehler oder Zugriffsschutz nichts.
                if e.code in (401, 403) or e.code >= 500:
                    regeln.disallow_all = True
                else:
                    regeln.allow_all = True
            except urllib.error.URLError:
                regeln.disallow_all = True
            self._robots[host] = regeln
        return self._robots[host]

    def erlaubt(self, url: str) -> bool:
        teile = urlsplit(url)
        return self._regeln(f"{teile.scheme}://{teile.netloc}").can_fetch(self.user_agent, url)

    def holen(self, url: str) -> str:
        teile = urlsplit(url)
        host = f"{teile.scheme}://{teile.netloc}"
        if not self.erlaubt(url):
            raise AbrufVerboten(url)
        abstand = max(self.mindestabstand_s, self._regeln(host).crawl_delay(self.user_agent) or 0)
        if host in self._letzter_abruf:
            rest = self._letzter_abruf[host] + abstand - time.monotonic()
            if rest > 0:
                self.schlafen(rest)
        try:
            return self._laden(url).decode("utf-8-sig")
        finally:
            self._letzter_abruf[host] = time.monotonic()
