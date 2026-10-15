"""NS2 TASK B: gunicorn radnici na 512 MiB instanci.

Izmereno (NS2 B1, produkciona slika, --memory=512m): 4 radnika ne mogu da miruju
(OOM petlja), 2 radnika padaju na paru OCR poslova, 1 radnik prezivljava.
Zato `gunicorn.conf.py` bez WEB_CONCURRENCY mora dati TACNO jednog radnika,
a postavljena vrednost mora se postovati doslovno (bez tihog sabijanja).
"""
import os
import re
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "gunicorn.conf.py"


def _workers(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("WEB_CONCURRENCY", value)
    return runpy.run_path(str(CONF))["workers"]


def test_bez_web_concurrency_tacno_jedan_radnik(monkeypatch):
    assert _workers(monkeypatch, None) == 1


@pytest.mark.parametrize("value,expected", [("1", 1), ("2", 2), ("4", 4)])
def test_postavljena_vrednost_se_postuje_doslovno(monkeypatch, value, expected):
    assert _workers(monkeypatch, value) == expected


def test_ostatak_konfiguracije_nepromenjen(monkeypatch):
    cfg = runpy.run_path(str(CONF))
    assert cfg["worker_class"] == "uvicorn.workers.UvicornWorker"
    assert cfg["timeout"] == 120
    assert cfg["max_requests"] == 1000 and cfg["max_requests_jitter"] == 100


def test_health_workers_polje_ima_isti_podrazumevani_kao_gunicorn():
    # /health izvestava int(os.getenv("WEB_CONCURRENCY", <d>)); gunicorn.conf.py koristi isti
    # obrazac. Ako se podrazumevane vrednosti razidju, /health laze o broju radnika kad
    # promenljiva nije postavljena (tacno stanje pre NS2: api.py 1, gunicorn 4).
    pat = re.compile(r'getenv\("WEB_CONCURRENCY",\s*(\d+)\)')
    api_d = pat.findall((ROOT / "api.py").read_text(encoding="utf-8"))
    conf_d = pat.findall(CONF.read_text(encoding="utf-8"))
    assert api_d and conf_d
    assert set(api_d) == set(conf_d) == {"1"}
