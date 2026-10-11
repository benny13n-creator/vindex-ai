"""NS007 Task 24 — proba postavljanja raspoređivača BEZ Render-a.

PRAVI proces okidača (`scripts/trigger_autonomy_cycle.py`) → PRAVI HTTP → PRAVI uvicorn sa `api.app` (lažna baza u istom
procesu, tests/ns007_uvicorn_proba.py) → atomski prozor → kanonski radnik → rezultat.
  • ispravna tajna → izlaz 0, COMPLETED sa sažetkom; drugi okidač u istom satu → izlaz 0, SKIPPED;
  • pogrešna tajna → 401 → izlaz 4; nedostaje tajna → izlaz 2 bez zahteva;
  • ciklus traje duže od isteka okidača → izlaz 3 („nije odgovorio");
  • ciklus pada → 500 → izlaz 4;
  • tajna nikad u izlazu okidača.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

KOREN = Path(__file__).resolve().parent.parent
TAJNA = "proba-tajna-" + "q" * 30


def _slobodan_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _server(*opcije):
    port = _slobodan_port()
    env = {**os.environ, "AUTONOMY_CRON_SECRET": TAJNA, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.Popen([sys.executable, str(KOREN / "tests" / "ns007_uvicorn_proba.py"), str(port), *opcije],
                         cwd=str(KOREN), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    kraj = time.time() + 60
    while time.time() < kraj:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return p, port
        except OSError:
            if p.poll() is not None:
                raise RuntimeError("server nije podignut: " + (p.stderr.read() or "")[-1500:])
            time.sleep(0.3)
    p.kill()
    raise RuntimeError("server se nije podigao na vreme")


def _okidac(port, tajna=TAJNA, timeout=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("AUTONOMY_")}
    env.update({"AUTONOMY_TRIGGER_URL": f"http://127.0.0.1:{port}/api/cron/autonomy", "PYTHONIOENCODING": "utf-8"})
    if tajna is not None:
        env["AUTONOMY_CRON_SECRET"] = tajna
    if timeout is not None:
        env["AUTONOMY_TRIGGER_TIMEOUT"] = str(timeout)
    r = subprocess.run([sys.executable, str(KOREN / "scripts" / "trigger_autonomy_cycle.py")], env=env, capture_output=True,
                       text=True, encoding="utf-8", timeout=120)
    return r.returncode, r.stdout + r.stderr


@pytest.fixture
def server():
    procesi = []

    def podigni(*opcije):
        p, port = _server(*opcije)
        procesi.append(p)
        return port
    yield podigni
    for p in procesi:
        p.kill()
        p.wait(timeout=10)


def test_ispravna_tajna_ciklus_pa_skipped(server):
    port = server()
    kod, izlaz = _okidac(port)
    assert kod == 0 and '"status": "COMPLETED"' in izlaz and '"spremno": 1' in izlaz, izlaz
    kod2, izlaz2 = _okidac(port)
    assert kod2 == 0 and '"status": "SKIPPED"' in izlaz2 and "ALREADY_CLAIMED" in izlaz2
    assert TAJNA not in izlaz + izlaz2


def test_pogresna_i_nedostajuca_tajna(server):
    port = server()
    kod, izlaz = _okidac(port, tajna="pogresna-tajna-" + "z" * 30)
    assert kod == 4 and "HTTP 401" in izlaz
    kod2, izlaz2 = _okidac(port, tajna=None)
    assert kod2 == 2 and "AUTONOMY_CRON_SECRET nije podešen" in izlaz2
    kod3, izlaz3 = _okidac(port)                                       # posle odbijenih: prozor je i dalje slobodan
    assert kod3 == 0 and '"status": "COMPLETED"' in izlaz3


def test_istek_vremena_okidaca(server):
    port = server("--spor")
    kod, izlaz = _okidac(port, timeout=2)
    assert kod == 3 and "nije odgovorio" in izlaz and TAJNA not in izlaz


def test_pad_ciklusa_je_ne_2xx(server):
    port = server("--pad")
    kod, izlaz = _okidac(port)
    assert kod == 4 and "HTTP 500" in izlaz and '"status": "FAILED"' in izlaz
