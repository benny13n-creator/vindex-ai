# -*- coding: utf-8 -*-
"""
Governance Wave 4 — životni ciklus patch-a i istinitost zastavice.

CENTRALNO PITANJE SPRINTA

„Može li AI zahtev ili odgovor zaobići governance sloj a da sistem to ne zna?"

Do Wave 4 odgovor je bio **DA**, i to ne hipotetički:

`shared/ai_client.py` je na neuspeh uvoza SDK klasa logovao grešku i postavljao
`_guard_patched = True`, pa se vraćao. Aplikacija bi se podigla bez ijednog
prompt guard-a, bez Response Firewall-a, bez provenance-a i bez timeout-a — a
jedina promenljiva koja opisuje stanje tvrdila bi da je patch primenjen. Wave 2
je izmerio da tu zastavicu **niko ne čita** van internog idempotency check-a,
pa nijedan health check to nije mogao da razlikuje.

Jedna promenljiva je nosila dve različite tvrdnje: „pokušano" i „aktivno".

ŠTA JE PROMENJENO

  `_guard_patched`  → i dalje znači „ne pokušavaj ponovo" (idempotencija)
  `_guard_active`   → NOVA, nosi istinu: kontrole se stvarno izvršavaju
  `governance_status()` → jedina javna tvrdnja
  `/api/version.governance` → izlaže je spolja

Misija je izričito tražila: „Ako pronađeš bilo kakav `_guard_patched = True` pre
stvarnog uspeha patch-a, dokaži posledicu testom. Ne prihvataj 'u praksi se to
neće desiti'." Ovaj fajl je taj dokaz.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def svez_modul(monkeypatch):
    """Sveža kopija `shared.ai_client` sa resetovanim globalnim stanjem.

    VRAĆA I SDK METODE, NE SAMO ZASTAVICE — i to nije opreznost nego ispravka
    stvarnog kvara koji je ovaj fajl proizveo.

    `_patch_prompt_guard` je idempotentan preko `_guard_patched`. Prva verzija
    ovog fixture-a resetovala je samo zastavice, pa je ponovni poziv patch-ovao
    VEĆ PATCH-OVANE klase: `_orig_create` bi postao već-obavijen `_guarded_create`,
    a wrapper bi se ugnezdio u samog sebe. Efekat se prelivao na kasnije testove
    u istoj sesiji i oborio je dva nevezana testa u
    `tests/test_uploaded_doc_api.py` — koji su do tada bili zeleni.

    Zato se snima i vraća kompletno stanje: zastavice, sačuvani originali, i
    same metode na SDK klasama.
    """
    import shared.ai_client as ac
    from openai.resources.chat.completions.completions import (
        AsyncCompletions, Completions,
    )
    from openai.resources.embeddings import AsyncEmbeddings, Embeddings

    snimak = {
        "zastavice": (ac._guard_patched, ac._guard_active, ac._guard_failure_reason),
        "originali": (ac._orig_create, ac._orig_acreate, ac._orig_embed, ac._orig_aembed),
        "metode": (
            Completions.create, AsyncCompletions.create,
            Embeddings.create, AsyncEmbeddings.create,
        ),
    }

    ac._guard_patched = False
    ac._guard_active = False
    ac._guard_failure_reason = None
    yield ac

    ac._guard_patched, ac._guard_active, ac._guard_failure_reason = snimak["zastavice"]
    ac._orig_create, ac._orig_acreate, ac._orig_embed, ac._orig_aembed = snimak["originali"]
    (Completions.create, AsyncCompletions.create,
     Embeddings.create, AsyncEmbeddings.create) = snimak["metode"]


# ─── 1. ISTINITOST ZASTAVICE ────────────────────────────────────────────────

def test_a_pre_patcha_governance_nije_aktivan(svez_modul):
    s = svez_modul.governance_status()
    assert s["attempted"] is False
    assert s["active"] is False


def test_b_posle_uspesnog_patcha_je_aktivan(svez_modul):
    svez_modul._patch_prompt_guard()
    s = svez_modul.governance_status()
    assert s["attempted"] is True
    assert s["active"] is True, "uspešan patch se ne prijavljuje kao aktivan"
    assert s["failure_reason"] is None


def test_c_NEUSPEH_PATCHA_NE_SME_da_izgleda_kao_uspeh(svez_modul, monkeypatch):
    """Srž Wave 4.

    Simulira se tačno ono što je ranije proizvodilo tihu rupu: uvoz SDK klasa
    pukne. Pre popravke bi `_guard_patched` bio True i ništa ne bi odalo da
    kontrole ne rade.
    """
    import builtins
    pravi_import = builtins.__import__

    def _pukni(ime, *a, **k):
        if ime == "openai.resources.chat.completions.completions":
            raise ImportError("simulirani pad SDK-a")
        return pravi_import(ime, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _pukni)
    svez_modul._patch_prompt_guard()

    s = svez_modul.governance_status()
    assert s["attempted"] is True, "idempotencija je izgubljena — patch bi se ponavljao"
    assert s["active"] is False, (
        "NEUSPEH PATCH-a SE PRIJAVLJUJE KAO USPEH. Aplikacija radi bez prompt "
        "guard-a i bez Response Firewall-a, a status tvrdi da je sve u redu — "
        "tačno rupa zbog koje Wave 4 postoji."
    )
    assert s["failure_reason"], "neuspeh bez razloga se ne može dijagnostikovati"
    assert "import" in s["failure_reason"].lower()


def test_d_idempotencija_je_ocuvana(svez_modul):
    """Drugi poziv ne sme ponovo da patch-uje (dvostruko obavijanje)."""
    svez_modul._patch_prompt_guard()
    prvi = svez_modul.governance_status()
    svez_modul._patch_prompt_guard()
    assert svez_modul.governance_status() == prvi


# ─── 2. IZLAGANJE — zastavica koju niko ne čita ne postoji ─────────────────

def test_e_api_version_objavljuje_stvarno_stanje():
    """Wave 2 je izmerio da `_guard_patched` niko ne čita van samog modula.

    Istinita zastavica koju nijedan endpoint ne izlaže i dalje bi bila
    nevidljiva na produkciji. Ovo dokazuje da je vidljiva.
    """
    import api
    odgovor = api.api_version()
    assert "governance" in odgovor, "/api/version ne objavljuje stanje governance-a"
    gov = odgovor["governance"]
    for kljuc in ("attempted", "active", "failure_reason"):
        assert kljuc in gov, f"nedostaje `{kljuc}`"
    assert gov["active"] is True, (
        "u test procesu je patch primenjen (conftest uvozi api), pa `active` "
        "mora biti True — ako nije, ili patch ne radi ili status laže"
    )


def test_f_status_ne_izlaze_nista_osetljivo():
    """`/api/version` je javan. Status sme da nosi zastavice i ime klase greške,
    nikad putanje, ključeve ni sadržaj."""
    import shared.ai_client as ac
    s = ac.governance_status()
    tekst = repr(s).lower()
    for zabranjeno in ("sk-", "api_key", "supabase", "password", "token", "c:\\", "/home/"):
        assert zabranjeno not in tekst, f"status izlaže `{zabranjeno}`"


# ─── 3. NEGATIVNA KONTROLA ──────────────────────────────────────────────────

def test_ng_status_stvarno_razlikuje_dva_stanja(svez_modul, monkeypatch):
    """Bez ovoga bi `test_c` prolazio i da `active` uvek vraća False.

    Meri se OBA smera u istom testu, nad istim svežim modulom.
    """
    assert svez_modul.governance_status()["active"] is False
    svez_modul._patch_prompt_guard()
    assert svez_modul.governance_status()["active"] is True


def test_ng_zastavice_nisu_ista_promenljiva(svez_modul, monkeypatch):
    """Dokaz da razdvajanje nije kozmetičko.

    Posle simuliranog neuspeha jedna mora biti True (pokušano), druga False
    (nije aktivno). Da su ista promenljiva, ovo je nemoguće.
    """
    import builtins
    pravi = builtins.__import__

    def _pukni(ime, *a, **k):
        if ime == "openai.resources.chat.completions.completions":
            raise ImportError("pad")
        return pravi(ime, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _pukni)
    svez_modul._patch_prompt_guard()
    s = svez_modul.governance_status()
    assert s["attempted"] != s["active"], (
        "`attempted` i `active` imaju istu vrednost posle neuspeha — "
        "razdvajanje je poništeno i rupa je vraćena"
    )
