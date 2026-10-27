"""V1 (2026-10-27): VINDEX_CACHE_BYPASS=1 mora da preskoči i UPIS u ai_cache, ne samo čitanje.

Lokalni pokretač pravnih pitanja postavio je VINDEX_CACHE_BYPASS=1 i učitao .env sa produkcionim Supabase
ključem; `_cache_get` je preskočio čitanje, ali `_cache_set` je bezuslovno pozvao `_supa_cache_set` i upisao
red u produkcioni ai_cache (POST /rest/v1/ai_cache 201). Isti obrazac imaju run_test_30q/100q i stress skripte.
"""
from unittest.mock import patch

import main

PITANJE = "Koliki je rok za žalbu u parničnom postupku?"
REZULTAT = {"status": "success", "data": "15 dana"}


def _upisi(monkeypatch, bypass):
    if bypass is None:
        monkeypatch.delenv("VINDEX_CACHE_BYPASS", raising=False)
    else:
        monkeypatch.setenv("VINDEX_CACHE_BYPASS", bypass)
    monkeypatch.setattr(main, "_CACHE", {})
    upisano = []
    with patch.object(main, "_supa_cache_set", side_effect=lambda k, r: upisano.append(k)), \
         patch.object(main, "_supa_cache_get", side_effect=AssertionError("L2 čitanje pod bypass-om")) as g:
        main._cache_set(PITANJE, REZULTAT)
        if bypass == "1":
            assert main._cache_get(PITANJE) is None
            g.assert_not_called()
    return upisano


def test_bypass_ne_upisuje_u_deljeni_kes(monkeypatch):
    assert _upisi(monkeypatch, "1") == []
    assert main._CACHE == {}, "ni L1: bypass znači da keš ne postoji za ovo pokretanje"


def test_bez_bypass_upis_ostaje_kao_pre(monkeypatch):
    assert _upisi(monkeypatch, None) == [main._cache_kljuc(PITANJE)]


def test_samo_tacno_1_ukljucuje_bypass(monkeypatch):
    # isto pravilo kao čitanje (`== "1"`): druga vrednost ne menja produkciono ponašanje
    assert _upisi(monkeypatch, "0") == [main._cache_kljuc(PITANJE)]
