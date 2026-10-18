# -*- coding: utf-8 -*-
"""NS3-N01 — kanarinac izolacije mreže za cron/notifikacione testove, uključujući podprocese.

Incident PR #45: lažni `curl` nije bio izvršan na Linux-u, pa je test pokrenuo PRAVI `curl` ka produkcionom
`send-reminders`. Python-level brana (`conftest.py`) to ne vidi — podproces ima svoj mrežni stek.

Svaki test ovde pokreće pytest u ZASEBNOM procesu sa `tests._ns3_mreza_zabrana` (Python DNS/connect zabrana +
lokalni proksi-sink za podprocese) i čita dnevnik pokušaja. Nijedan zahtev ne napušta loopback: Python ne može
da razreši ime, a `curl` šalje `CONNECT` lokalnom sink-u koji samo beleži i zatvara vezu."""
import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASH, CURL = shutil.which("bash"), shutil.which("curl")

CRON_NOTIF = [
    "tests/test_alerts_email_api_shape.py", "tests/test_alerts_email_cron_contract.py",
    "tests/test_alerts_email_eligibility.py", "tests/test_alerts_email_integration.py",
    "tests/test_alerts_sms_cron_disabled.py", "tests/test_b10_reminder_claim.py",
    "tests/test_cron_daily_dispatcher.py", "tests/test_cron_daily_failclosed_auth.py",
    "tests/test_lz001_reminder_vocabulary.py", "tests/test_ns007_t25_daily_cron_regression.py",
    "tests/test_tenfronts_m01_cron_daily_email.py", "tests/test_tenfronts_m02_email_profil.py",
    "tests/test_tenfronts_m10_primalac.py", "tests/test_vcr002_t04_podsetnici.py",
    "tests/test_wave4_preflight_b_email_cron_auth.py", "tests/test_omega_sprint007_sms_reminder_dedup.py",
]


def _pytest(tmp_path, *ciljevi):
    dnevnik = tmp_path / "mreza.jsonl"
    env = {k: v for k, v in os.environ.items() if not k.upper().endswith("_PROXY")}
    env.update({"NS3_MREZA_DNEVNIK": str(dnevnik), "PYTHONIOENCODING": "utf-8"})
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider",
                        "-p", "tests._ns3_mreza_zabrana", *ciljevi],
                       cwd=KOREN, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=900)
    zapisi = [json.loads(l) for l in dnevnik.read_text(encoding="utf-8").splitlines()] if dnevnik.exists() else []
    return r, zapisi


def _proba(tmp_path, telo):
    f = tmp_path / "test_proba_mreze.py"
    f.write_text(textwrap.dedent(telo), encoding="utf-8")
    return _pytest(tmp_path, str(f), "--rootdir", KOREN)


def test_namerni_beg_iz_pythona_je_odbijen_i_zabelezen(tmp_path):
    r, z = _proba(tmp_path, """
        import socket, urllib.request, pytest
        def test_dns():
            with pytest.raises(OSError):
                socket.getaddrinfo("kanarinac.example.invalid", 443)
        def test_connect_na_ip():
            s = socket.socket()
            with pytest.raises(OSError):
                s.connect(("192.0.2.1", 443))        # TEST-NET-1, nikad rutirano
        def test_urllib_ide_u_sink():
            with pytest.raises(Exception):
                urllib.request.urlopen("http://kanarinac.example.invalid/x", timeout=5)
    """)
    assert r.returncode == 0, r.stdout[-2000:]
    vrste = {(x["vrsta"], x["cilj"].split(" ")[1] if x["vrsta"] == "proksi" else x["cilj"]) for x in z}
    assert ("dns", "kanarinac.example.invalid") in vrste
    assert any(v == "connect" and "192.0.2.1" in c for v, c in vrste)
    assert any(v == "proksi" and "kanarinac.example.invalid" in c for v, c in vrste)


@pytest.mark.skipif(BASH is None or CURL is None, reason="bash/curl nisu dostupni")
def test_pravi_curl_iz_podprocesa_ne_izlazi_van_loopback_a(tmp_path):
    """Scenario incidenta: lažnog `curl`-a nema, PATH nalazi pravi. Zahtev završava u sink-u (zabeležen)."""
    r, z = _proba(tmp_path, """
        import shutil, subprocess
        def test_pravi_curl():
            p = subprocess.run([shutil.which("bash"), "--noprofile", "--norc", "-c",
                                "curl -sS --max-time 10 -X POST https://kanarinac.example.invalid/email-notif/send-reminders"],
                               capture_output=True, text=True)
            assert p.returncode != 0
    """)
    assert r.returncode == 0, r.stdout[-2000:]
    assert any(x["vrsta"] == "proksi" and "CONNECT kanarinac.example.invalid:443" in x["cilj"] for x in z), z


def test_lokalni_servis_radi(tmp_path):
    r, z = _proba(tmp_path, """
        import http.server, shutil, subprocess, threading, urllib.request
        def test_loopback():
            srv = http.server.HTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            url = "http://127.0.0.1:%d/" % srv.server_address[1]
            assert urllib.request.urlopen(url, timeout=5).status == 200
            if shutil.which("curl"):
                p = subprocess.run(["curl", "-s", "-o", "-", "-w", "%{http_code}", url], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
                assert p.stdout.endswith("200")
            srv.shutdown()
    """)
    assert r.returncode == 0, r.stdout[-2000:]
    assert z == []


def test_cron_i_notifikacioni_testovi_bez_ijednog_mreznog_pokusaja(tmp_path):
    r, z = _pytest(tmp_path, *CRON_NOTIF)
    assert r.returncode == 0, r.stdout[-3000:]
    assert " passed" in r.stdout and " failed" not in r.stdout
    assert z == [], "mrežni pokušaji: %s" % sorted({(x["test"], x["vrsta"], x["cilj"]) for x in z})
