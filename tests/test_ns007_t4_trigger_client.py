"""NS007 Task 4 — `scripts/trigger_autonomy_cycle.py` kao PRAVI proces protiv lokalnog HTTP servera.

2xx → 0 i bezbedan sažetak; 401/500/503 → ≠ 0; isteklo vreme → ≠ 0 sa jasnom porukom; nedostaje URL/tajna → ≠ 0 bez
zahteva; http ka udaljenom hostu → odbijeno bez zahteva; tajna se šalje u zaglavlju i NIKAD se ne ispisuje (ni kad
server vrati telo koje je sadrži); sadržaj sažetka bez brojeva se ne ispisuje.
"""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SKRIPTA = Path(__file__).resolve().parent.parent / "scripts" / "trigger_autonomy_cycle.py"
TAJNA = "s3cr3t-NE-SME-U-IZLAZ-" + "x" * 20


@pytest.fixture
def server():
    stanje = {"status": 200, "telo": {}, "spavaj": 0, "zahtevi": []}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            stanje["zahtevi"].append({"put": self.path, "tajna": self.headers.get("X-Autonomy-Secret"),
                                      "duzina": self.headers.get("Content-Length")})
            time.sleep(stanje["spavaj"])
            telo = json.dumps(stanje["telo"]).encode()
            self.send_response(stanje["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(telo)))
            self.end_headers()
            self.wfile.write(telo)

        def log_message(self, *a):
            pass
    s = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{s.server_address[1]}/api/cron/autonomy", stanje
    s.shutdown()


def _pokreni(url=None, tajna=TAJNA, timeout=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("AUTONOMY_")}
    if url is not None:
        env["AUTONOMY_TRIGGER_URL"] = url
    if tajna is not None:
        env["AUTONOMY_CRON_SECRET"] = tajna
    if timeout is not None:
        env["AUTONOMY_TRIGGER_TIMEOUT"] = str(timeout)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, str(SKRIPTA)], env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    return r.returncode, r.stdout + r.stderr


def test_uspeh_bezbedan_sazetak(server):
    url, st = server
    st["telo"] = {"ok": True, "status": "COMPLETED", "prozor": "auto:2026-10-10T03", "run_id": "abc123",
                  "sazetak": {"spremno": 2, "zauzeto": 2, "tajno": "sadržaj predmeta", "bool": True}}
    kod, izlaz = _pokreni(url)
    assert kod == 0 and "COMPLETED" in izlaz and '"spremno": 2' in izlaz
    assert "sadržaj predmeta" not in izlaz, "ispisuju se samo brojevi"
    assert st["zahtevi"] == [{"put": "/api/cron/autonomy", "tajna": TAJNA, "duzina": "0"}]
    assert TAJNA not in izlaz


def test_skipped_je_uspeh(server):
    url, st = server
    st["telo"] = {"ok": True, "status": "SKIPPED", "razlog": "ALREADY_CLAIMED", "prozor": "auto:w"}
    assert _pokreni(url)[0] == 0


@pytest.mark.parametrize("status", [401, 500, 503])
def test_ne_2xx_je_neuspeh(server, status):
    url, st = server
    st["status"], st["telo"] = status, {"ok": False, "status": "FAILED", "detail": TAJNA}
    kod, izlaz = _pokreni(url)
    assert kod == 4 and f"HTTP {status}" in izlaz and TAJNA not in izlaz


def test_isteklo_vreme(server):
    url, st = server
    st["spavaj"] = 3
    kod, izlaz = _pokreni(url, timeout=1)
    assert kod == 3 and "nije odgovorio" in izlaz and TAJNA not in izlaz


def test_nepostojeci_server(server):
    kod, izlaz = _pokreni("http://127.0.0.1:1/api/cron/autonomy", timeout=2)
    assert kod == 3 and TAJNA not in izlaz


@pytest.mark.parametrize("url,tajna,ocekivano", [
    (None, TAJNA, "AUTONOMY_TRIGGER_URL nije podešen"),
    ("https://vindex.rs/api/cron/autonomy", None, "AUTONOMY_CRON_SECRET nije podešen"),
    ("http://vindex.rs/api/cron/autonomy", TAJNA, "samo preko HTTPS"),
    ("https://korisnik:lozinka@vindex.rs/api/cron/autonomy", TAJNA, "korisnika/lozinku"),
    ("ftp://vindex.rs/x", TAJNA, "neispravan"),
])
def test_konfiguracija_bez_zahteva(server, url, tajna, ocekivano):
    _, st = server
    kod, izlaz = _pokreni(url, tajna)
    assert kod == 2 and ocekivano in izlaz and st["zahtevi"] == []
    assert TAJNA not in izlaz
