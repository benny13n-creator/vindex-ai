# -*- coding: utf-8 -*-
"""
BETA-DATA-CONFIDENTIALITY-002 — CROSS-TENANT WRITE.

Tri rute su primale strani ID iz zahteva i upisivale ga bez ijedne provere:

  CONF-008  PUT  /api/users/{id}/role   — `user_roles` je GLOBALNA tabela bez
            `kancelarija_id`, pa je partner jedne kancelarije menjao rolu
            korisniku bilo koje druge. Jedina provera (`role < PARTNER`) je
            pitanje o POZIVAOCU; meta se nije poredila ni sa čim.

  CONF-009  POST /api/zadaci/kreiraj    — `predmet_id` I `dodeljen_uid`
            neprovereni. `workspace.py:129` čita zadatke samo po
            `dodeljen_uid`, pa je napadač ubacivao stavku na tuđu dnevnu tablu.

  CONF-010  POST /api/pitanje, /api/procena — `predmet_id` iz tela zahteva je
            išao pravo u `predmet_istorija`, pa je napadačev tekst (i pun
            GPT-4o nalaz) završavao u tuđem pravnom spisu.

ZAŠTO JE OVO ŽIVA RUPA, A NE PROPUST U DUBINSKOJ ODBRANI

Backend koristi `service_role` ključ (`shared/deps.py:93`), pa je RLS zaobiđen
na svakoj API putanji. Onih 250 `CREATE POLICY` u repou štiti samo pristup iz
pregledača anon-ključem. Za API saobraćaj jedina izolacija je ručno napisan
`.eq("user_id", ...)` u handleru — izostavljen `.eq()` nema ništa ispod sebe.

ZAŠTO LAŽNI SUPABASE STVARNO FILTRIRA

Postojeći testovi u repou grade lance `MagicMock`-ova koji vraćaju unapred
zadatu vrednost. Takav test prolazi i kada se kapija ukloni, jer mock ne zna
šta je `.eq()` značilo. Ovde je `_FakeSupa` mali motor koji `.eq()` primenjuje
nad podacima — pa mutacija (uklonjena kapija) STVARNO obara test.
"""
import asyncio
import os
import sys
from unittest.mock import patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import routers.zadaci as zadaci  # noqa: E402
import klijenti.router as kr  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# LAŽNI SUPABASE KOJI STVARNO FILTRIRA
# ═══════════════════════════════════════════════════════════════════════════

class _Rezultat:
    def __init__(self, data):
        self.data = data


class _Upit:
    def __init__(self, redovi, upisi, ime):
        self._redovi, self._upisi, self._ime = redovi, upisi, ime
        self._uslovi, self._limit = [], None

    def select(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def eq(self, kolona, vrednost):
        self._uslovi.append((kolona, vrednost))
        return self

    def neq(self, kolona, vrednost):
        self._uslovi.append((kolona, ("!=", vrednost)))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _filtrirani(self):
        out = []
        for r in self._redovi:
            ok = True
            for kol, vr in self._uslovi:
                if isinstance(vr, tuple) and vr[0] == "!=":
                    if r.get(kol) == vr[1]:
                        ok = False
                        break
                elif r.get(kol) != vr:
                    ok = False
                    break
            if ok:
                out.append(r)
        return out[: self._limit] if self._limit else out

    def execute(self):
        return _Rezultat(self._filtrirani())

    def maybe_single(self):
        class _S:
            def __init__(_s, red):
                _s._red = red

            def execute(_s):
                return _Rezultat(_s._red)
        f = self._filtrirani()
        return _S(f[0] if f else None)

    def single(self):
        return self.maybe_single()

    # ── strana upisa: beleži se, da test može da dokaže ŠTA je zapisano ──
    def insert(self, red):
        self._upisi.append((self._ime, "insert", red))
        self._redovi.append(red)
        return self

    def upsert(self, red, **k):
        self._upisi.append((self._ime, "upsert", red))
        return self

    def update(self, red):
        self._upisi.append((self._ime, "update", red))
        return self


class _FakeSupa:
    def __init__(self, tabele):
        self.tabele = {k: list(v) for k, v in tabele.items()}
        self.upisi = []

    def table(self, ime):
        return _Upit(self.tabele.setdefault(ime, []), self.upisi, ime)

    def upisi_u(self, ime):
        return [u for u in self.upisi if u[0] == ime]


NAPADAC = "uid-napadac"
ZRTVA = "uid-zrtva"
KOLEGA = "uid-kolega"


def _svet():
    """Dve odvojene kancelarije. Napadač zna ZRTVA-in predmet_id i user_id —
    UUID-evi nisu pogodljivi, ali cure kroz snimke ekrana, URL-ove i tikete."""
    return _FakeSupa({
        "predmeti": [
            {"id": "pred-napadac", "user_id": NAPADAC},
            {"id": "pred-zrtva",   "user_id": ZRTVA},
        ],
        "kancelarije": [
            {"id": "firma-A", "admin_uid": NAPADAC},
            {"id": "firma-B", "admin_uid": ZRTVA},
        ],
        "kancelarija_clanovi": [
            {"id": "c1", "user_id": NAPADAC, "kancelarija_id": "firma-A",
             "status": "ACTIVE", "email": "napadac@a.rs", "uloga": "admin"},
            {"id": "c2", "user_id": KOLEGA, "kancelarija_id": "firma-A",
             "status": "ACTIVE", "email": "kolega@a.rs", "uloga": "saradnik"},
            {"id": "c3", "user_id": ZRTVA, "kancelarija_id": "firma-B",
             "status": "ACTIVE", "email": "zrtva@b.rs", "uloga": "admin"},
            {"id": "c4", "user_id": "uid-bivsi", "kancelarija_id": "firma-A",
             "status": "REMOVED", "email": "bivsi@a.rs", "uloga": "saradnik"},
        ],
        "user_roles": [],
        "zadaci": [],
        "predmet_istorija": [],
    })


# ═══════════════════════════════════════════════════════════════════════════
# CONF-008 — PROMENA ROLE
# ═══════════════════════════════════════════════════════════════════════════

def _pozovi_rolu(supa, caller, target):
    """Zove SAMO kapiju — bez HTTP sloja, da test meri granicu a ne rutiranje."""
    return kr._verify_moze_menjati_rolu(supa, caller, target)


def test_conf008_napadac_ne_moze_menjati_rolu_druge_kancelarije():
    """NAJVAŽNIJI TEST ZA CONF-008."""
    supa = _svet()
    with pytest.raises(HTTPException) as e:
        _pozovi_rolu(supa, NAPADAC, ZRTVA)
    assert e.value.status_code == 404, "mora 404, ne 403 — inače je proročište postojanja"
    assert supa.upisi_u("user_roles") == [], "nijedan upis ne sme da se dogodi"


def test_conf008_pozitivan_slucaj_sopstvena_kancelarija_radi():
    """Popravka ne sme da polomi legitiman tok."""
    supa = _svet()
    clan = _pozovi_rolu(supa, NAPADAC, KOLEGA)
    assert clan["email"] == "kolega@a.rs"


@pytest.mark.parametrize("meta,zasto", [
    ("uid-ne-postoji", "nepostojeći nalog"),
    ("uid-bivsi",      "uklonjen član — REMOVED"),
    (ZRTVA,            "druga kancelarija"),
])
def test_conf008_sva_tri_odbijanja_izgledaju_identicno(meta, zasto):
    """Bez proročišta: napadač ne sme da razlikuje 'ne postoji' od 'postoji ali
    nije tvoj'. Ranije je strani UUID vraćao 200, a nepostojeći 500."""
    supa = _svet()
    with pytest.raises(HTTPException) as e:
        _pozovi_rolu(supa, NAPADAC, meta)
    assert e.value.status_code == 404, zasto
    assert e.value.detail == "Korisnik nije pronađen.", zasto


def test_conf008_samopromena_je_blokirana():
    """Partner ne sme da se zaključa iz sopstvene kancelarije."""
    supa = _svet()
    with pytest.raises(HTTPException) as e:
        _pozovi_rolu(supa, NAPADAC, NAPADAC)
    assert e.value.status_code == 400


def test_conf008_osnivac_nema_zaobilaznicu():
    """Izričito, ne slučajno.

    Osnivači su ranije stizali do ovog upisa samo zato što `_get_role` kratko
    spaja na PARTNER — globalna izmena role bila je nusproizvod prečice za
    čitanje. Mandat traži da ponašanje bude definisano: osnivač mora biti admin
    firme kao i svi drugi.
    """
    supa = _svet()
    with patch.object(kr, "_is_founder", return_value=True):
        with pytest.raises(HTTPException) as e:
            _pozovi_rolu(supa, "uid-osnivac-bez-firme", ZRTVA)
    assert e.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# CONF-009 — ZADACI
# ═══════════════════════════════════════════════════════════════════════════

def _kreiraj_zadatak(supa, uid, predmet_id=None, dodeljen_uid=None):
    payload = zadaci.ZadatakRequest(
        naziv="Test", opis="x", prioritet="normalan",
        predmet_id=predmet_id, dodeljen_uid=dodeljen_uid,
    )
    with patch.object(zadaci, "_get_supa", return_value=supa):
        return asyncio.run(zadaci.kreiraj_zadatak.__wrapped__(
            request=None, payload=payload, user={"user_id": uid, "email": "a@a.rs"},
        ))


def test_conf009_tudji_predmet_id_je_odbijen():
    supa = _svet()
    with pytest.raises(HTTPException) as e:
        _kreiraj_zadatak(supa, NAPADAC, predmet_id="pred-zrtva")
    assert e.value.status_code == 404
    assert supa.upisi_u("zadaci") == [], "zadatak ne sme biti kreiran"


def test_conf009_dodela_na_tudju_tablu_je_odbijena():
    """Ovo niko nije prijavio, a gore je od `predmet_id`.

    `workspace.py:129` čita zadatke ISKLJUČIVO po `dodeljen_uid`. Bez kapije je
    svaki korisnik mogao da ubaci stavku proizvoljnog naslova i roka na tuđu
    kanonsku dnevnu tablu, uz notifikaciju.
    """
    supa = _svet()
    with pytest.raises(HTTPException) as e:
        _kreiraj_zadatak(supa, NAPADAC, dodeljen_uid=ZRTVA)
    assert e.value.status_code == 404
    assert supa.upisi_u("zadaci") == []


def test_conf009_pozitivno_kolega_iz_iste_firme_i_svoj_predmet():
    supa = _svet()
    r = _kreiraj_zadatak(supa, NAPADAC, predmet_id="pred-napadac", dodeljen_uid=KOLEGA)
    assert r["ok"] is True
    upisi = supa.upisi_u("zadaci")
    assert len(upisi) == 1
    assert upisi[0][2]["predmet_id"] == "pred-napadac"


def test_conf009_zadatak_samom_sebi_bez_predmeta_i_dalje_radi():
    """Najčešći stvarni tok — ne sme da postane kolateralna šteta."""
    supa = _svet()
    r = _kreiraj_zadatak(supa, NAPADAC, dodeljen_uid=NAPADAC)
    assert r["ok"] is True


def test_conf009_uklonjen_clan_ne_moze_dobiti_zadatak():
    supa = _svet()
    with pytest.raises(HTTPException) as e:
        _kreiraj_zadatak(supa, NAPADAC, dodeljen_uid="uid-bivsi")
    assert e.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# CONF-010 — PREDMET_ISTORIJA
# ═══════════════════════════════════════════════════════════════════════════

def test_conf010_kapija_odbija_tudji_predmet():
    import api
    supa = _svet()
    with patch.object(api, "_get_supa", return_value=supa):
        assert api._poseduje_predmet(NAPADAC, "pred-napacac-ne-postoji") is False
        assert api._poseduje_predmet(NAPADAC, "pred-zrtva") is False, \
            "tuđi predmet mora biti odbijen — ovo je cela rupa"
        assert api._poseduje_predmet(NAPADAC, "pred-napadac") is True


def test_conf010_kapija_je_fail_closed():
    """Greška u proveri NE sme da znači 'pusti upis'."""
    import api

    class _Puca:
        def table(self, *a, **k):
            raise RuntimeError("baza nedostupna")

    with patch.object(api, "_get_supa", return_value=_Puca()):
        assert api._poseduje_predmet(NAPADAC, "pred-napadac") is False


def test_conf010_prazni_ulazi_ne_prolaze():
    import api
    assert api._poseduje_predmet("", "pred-1") is False
    assert api._poseduje_predmet(NAPADAC, "") is False
    assert api._poseduje_predmet(None, None) is False


# ═══════════════════════════════════════════════════════════════════════════
# NEGATIVNA KONTROLA NAD SAMIM TESTOM
# ═══════════════════════════════════════════════════════════════════════════

def test_lazni_supabase_stvarno_filtrira():
    """Bez ovoga se ostalim testovima ne veruje.

    Ako `_FakeSupa` ignoriše `.eq()`, svi testovi iznad prolaze i sa uklonjenom
    kapijom — tačno mana zbog koje postojeći `MagicMock` testovi u repou nisu
    uhvatili nijedan od ovih devet bagova.
    """
    supa = _svet()
    assert supa.table("predmeti").select("id").eq("id", "pred-zrtva") \
        .eq("user_id", NAPADAC).execute().data == []
    assert supa.table("predmeti").select("id").eq("id", "pred-zrtva") \
        .eq("user_id", ZRTVA).execute().data != []
    assert supa.table("kancelarija_clanovi").select("*") \
        .eq("status", "ACTIVE").eq("kancelarija_id", "firma-A").execute().data
