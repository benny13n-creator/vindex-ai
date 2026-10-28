# -*- coding: utf-8 -*-
"""G1 — VINDEX_BEZ_BAZE=1 zatvara svaki pristup Supabase-u u procesu lokalnog pravnog pokretača.

Izmereno: run_test_30q/100q i scripts/test_c7a_e2e učitavaju ceo `.env` (produkcioni ključ). `ask_agent` je tada pisao
u `ai_cache` (bez --no-cache i po dizajnu), a `retrieve._log_rag_error` u `security_events` kroz DRUGI klijent
(`api._get_supa`). Nijedan test ne otvara mrežu: klijenti su lažni i svaki dodir je greška."""
import re
from pathlib import Path
from unittest.mock import patch

import pytest

import api
import main
import shared.deps as deps
from app.services import retrieve

KOREN = Path(__file__).resolve().parent.parent


class _Dodir:
    """Lažan klijent: SVAKI pristup je greška testa (dokaz da brana stoji ispred klijenta, ne iza)."""
    dodiri = 0

    def table(self, *a, **k):
        _Dodir.dodiri += 1
        raise AssertionError("pristup bazi pod VINDEX_BEZ_BAZE=1")


@pytest.fixture
def bez_baze(monkeypatch):
    monkeypatch.setenv("VINDEX_BEZ_BAZE", "1")
    monkeypatch.setattr(deps, "_supa", _Dodir())          # već napravljen singleton ne sme da prođe
    monkeypatch.setattr(api, "_supa", _Dodir())
    _Dodir.dodiri = 0
    return monkeypatch


@pytest.mark.parametrize("modul", [deps, api])
def test_oba_klijenta_odbijaju_i_kad_singleton_postoji(bez_baze, modul):
    with pytest.raises(RuntimeError, match="VINDEX_BEZ_BAZE"):
        modul._get_supa()


@pytest.mark.parametrize("modul", [deps, api])
def test_nov_klijent_se_ni_ne_pravi(bez_baze, modul):
    bez_baze.setattr(modul, "_supa", None)
    with patch.object(modul, "create_client", side_effect=AssertionError("create_client pod VINDEX_BEZ_BAZE=1")):
        with pytest.raises(RuntimeError, match="VINDEX_BEZ_BAZE"):
            modul._get_supa()


def test_security_events_upis_iz_pretrage_ne_dodiruje_bazu(bez_baze):
    retrieve._log_rag_error("timeout", "zakoni_rs", "simulirano")       # best-effort: ne sme da pukne
    assert _Dodir.dodiri == 0


def test_kes_bez_bypass_ne_cita_ni_ne_pise_l2(bez_baze):
    bez_baze.delenv("VINDEX_CACHE_BYPASS", raising=False)
    bez_baze.setattr(main, "_CACHE", {})
    main._cache_set("Koliki je rok za žalbu u parničnom postupku?", {"status": "success", "data": "15 dana"})
    main._CACHE.clear()
    assert main._cache_get("Koliki je rok za žalbu u parničnom postupku?") is None
    assert _Dodir.dodiri == 0


def test_bez_zastavice_produkciono_ponasanje_isto(monkeypatch):
    monkeypatch.delenv("VINDEX_BEZ_BAZE", raising=False)
    s = object()
    monkeypatch.setattr(deps, "_supa", s)
    monkeypatch.setattr(api, "_supa", s)
    assert deps._get_supa() is s and api._get_supa() is s


def test_samo_tacno_1_zatvara(monkeypatch):
    monkeypatch.setenv("VINDEX_BEZ_BAZE", "0")
    s = object()
    monkeypatch.setattr(deps, "_supa", s)
    assert deps._get_supa() is s


@pytest.mark.parametrize("skripta", ["run_test_30q.py", "run_test_100q.py", "scripts/test_c7a_e2e.py", "stress_test.py",
                                     "debug_rag.py", "verify_subquery_fix.py"])
def test_pokretaci_postavljaju_zastavicu_posle_env_a_pre_uvoza_toka(skripta):
    """Zastavica (i prazan SENTRY_DSN) se postavlja izričito POSLE učitavanja `.env` — `load_dotenv` bez override-a ih
    ne može pregaziti — i PRE uvoza `main` / `api` / `app.services.retrieve`."""
    s = (KOREN / skripta).read_text(encoding="utf-8")
    zastavica = s.index('os.environ["VINDEX_BEZ_BAZE"] = "1"')
    assert s.index('os.environ["SENTRY_DSN"] = ""') > zastavica
    if "load_dotenv(" in s:
        assert s.index("load_dotenv(") < zastavica
    uvoz = min(m.start() for m in re.finditer(r"^\s*(?:from main import|import main|import api|from app\.services\.retrieve import)", s, re.M))
    assert zastavica < uvoz
    assert "override=True" not in s
