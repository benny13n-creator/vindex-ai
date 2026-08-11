# -*- coding: utf-8 -*-
"""
Wave 9 — kanonski kontekst predmeta u preostalih 8 strategija endpointa.

ŠTA JE BIO DEFEKT

P0-D/P0-D2 su dokazali i užičili kontekst predmeta SAMO za `/kompletna-analiza`.
Preostalih 8 endpointa istog fajla (`/red-team`, `/litigation`, `/sudija`,
`/due-diligence`, `/revizor`, `/witness`, `/sudija-v2`, `/v2/analiza`) nisu
imali `predmet_id` ni na jednom request modelu. Advokat koji predmet vodi u
sistemu — sa uploadovanim dokumentima, rokovima i izračunatim rizikom — dobijao
je Red Team analizu izgrađenu isključivo nad pasusom koji je nalepio u polje.

Najoštriji pojedinačan slučaj je `/witness`: `strategija._WITNESS_SYSTEM` traži
od modela „neslaganja sa poznatim činjenicama", a model nije imao NIJEDNU
poznatu činjenicu. Taj deo prompta bio je neizvršiv — mogao je da nađe samo
kontradikcije unutar samog iskaza.

METOD

Sve se dokazuje IZVRŠAVANJEM, ne čitanjem izvora:

  * Sloj rute — pravi FastAPI `TestClient` uz `dependency_overrides`, po
    obrascu iz `tests/test_copilot_ambient.py:173-190`. Sync funkcija modula se
    zamenjuje hvatačem koji pamti `case_context_blok` koji joj je STVARNO
    prosleđen. Grep po izvoru bi prijavio zeleno i da vrednost nikad ne stigne.
  * Sloj prompta — presreće se `strategija._pozovi_strategija_api`, jedina
    tačka kroz koju prolaze svi GPT pozivi, i čita se DOSLOVAN tekst poslat
    modelu. Isti obrazac kao `tests/test_p0d_case_context_integrity.py:70-97`.

PONOVO UPOTREBLJENO, NE PREPISANO

  `_VlasnickiUpit`            ← tests/test_p0d_ownership_and_render.py:127
  `_lazni_build_case_context` ← tests/test_p0d2_user_path_binding.py:88
  ALFA/BETA markeri i id-evi  ← tests/test_p0d2_user_path_binding.py:52-58

Mock konteksta vraća SADRŽAJ PO ID-U. Da vraća fiksan kontekst, testovi izolacije
(E) ne bi dokazivali ništa o rutiranju — prolazili bi i da backend ignoriše
`predmet_id` i uvek dovuče isti predmet.

`tests/conftest.py:86-138` blokira DNS ka naplativim hostovima, pa promašen mock
ne može da potroši novac — pao bi glasno.
"""
import io
import json
import os
import sys
import time as _time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import strategija  # noqa: E402
import routers.strategija as rs  # noqa: E402

# Ponovna upotreba, ne prepisivanje — v. docstring iznad.
from test_p0d_ownership_and_render import _VlasnickiUpit  # noqa: E402
from test_p0d2_user_path_binding import (  # noqa: E402
    ALFA_ID,
    BETA_ID,
    ALFA_DOKUMENT,
    BETA_DOKUMENT,
    _lazni_build_case_context,
    _UID as UID_VLASNIK,
    _UID_DRUGI as UID_TUDJI,
)

# Predmet koji pripada DRUGOM korisniku. `_lazni_build_case_context` ga ne zna —
# i ne sme ni da bude pitan za njega, jer kapija stoji ispred.
TUDJI_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
NEPOSTOJECI_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

_PREDMETI = {ALFA_ID: UID_VLASNIK, BETA_ID: UID_VLASNIK, TUDJI_ID: UID_TUDJI}

# Dovoljno dug za SVE module: `/due-diligence`, `/revizor` i `/sudija-v2`
# traže ≥100 karaktera, ostali ≥50.
_TEKST = (
    "Stranka tvrdi da je ugovor raskinut 15.07.2026. zbog kašnjenja u isporuci robe. "
    "Protivna strana osporava osnovanost raskida i tvrdi da je rok produžen usmenim "
    "dogovorom. Vrednost spora je 4.200.000 dinara, postupak je u prvom stepenu."
)


# ═══════════════════════════════════════════════════════════════════════════
# Tabela modula pod testom
# ═══════════════════════════════════════════════════════════════════════════
#
# `/v2/analiza` NIJE ovde: on nema sync funkciju u `strategija.py` (prompt gradi
# inline u ruti) i drugačijeg je oblika tela zahteva. Pokriven je zasebnom
# sekcijom niže — istim slovima testova (A–E), da pokrivenost ostane potpuna.

# Putanje su BEZ `/api` prefiksa — router se uključuje sa `prefix="/strategija"`
# i ničim više (`api.py:677`), a frontend ga zove kao `BASE_URL + '/strategija/…'`
# (`static/vindex.js:2961`). Prvi nacrt ovog fajla je gađao `/api/strategija/…`
# i dobijao Starlette-ov 404 „Not Found" — koji je oblikom nerazlučiv od našeg
# 404 „Predmet nije pronađen". Test C bi tako prolazio ZELENO nad nepostojećom
# rutom, ne dokazujući ništa o vlasništvu. Zato `test_ng_rute_postoje` ispod.
_MODULI = [
    # (putanja,                    ime sync funkcije,            modul u odgovoru)
    ("/strategija/red-team",      "red_team_analiza_sync",      "red_team"),
    ("/strategija/litigation",    "litigation_simulator_sync",  "litigation"),
    ("/strategija/sudija",        "ai_judge_mode_sync",         "sudija"),
    ("/strategija/due-diligence", "due_diligence_analiza_sync", "due_diligence"),
    ("/strategija/revizor",       "pravni_revizor_sync",        "revizor"),
    ("/strategija/witness",       "witness_analyzer_sync",      "witness"),
    ("/strategija/sudija-v2",     "ai_judge_v2_sync",           "sudija_v2"),
]

_IDS = [m[2] for m in _MODULI]


class _HvatacSync:
    """Zamena za sync funkciju modula — pamti tačno šta joj je prosleđeno.

    Ovo je srž metoda testova A/B/C/E. Provera „`predmet_id` je u telu zahteva"
    ili „`case_context_blok=` postoji u izvoru" prolazila bi i kad vrednost
    nikad ne stigne do rezonovanja. Hvatač meri stvarni poziv.
    """

    def __init__(self, ime: str):
        self.ime = ime
        self.pozivi = []

    def __call__(self, *args, **kwargs):
        self.pozivi.append({"args": args, "kwargs": kwargs})
        if self.ime == "ai_judge_v2_sync":
            return {"tuzilac": "T", "branilac": "B", "presuda": "P"}
        return "REZULTAT ANALIZE"

    @property
    def blokovi(self):
        """`case_context_blok` iz svakog poziva. `KeyError` bi značio da je
        parametar prosleđen pozicijski — što je sintaksno nemoguće, i test
        `test_s_case_context_blok_je_KEYWORD_ONLY` to zaključava."""
        return [p["kwargs"].get("case_context_blok") for p in self.pozivi]

    def assert_not_called(self):
        assert not self.pozivi, (
            f"{self.ime} JESTE pozvana iako je zahtev morao biti odbijen — "
            f"AI posao je obavljen i plaćen provajderu"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Fixture-i
# ═══════════════════════════════════════════════════════════════════════════

import api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from shared.deps import get_current_user as _shared_get_current_user  # noqa: E402
import shared.feature_registry as _fr  # noqa: E402

_KORISNIK = {"user_id": UID_VLASNIK, "email": "advokat@test.rs"}
_PROFIL = {
    "credits_remaining": 100, "is_pro": True,
    "subscription_type": "professional", "addons": [], "subscription_expires_at": None,
}


def _supa_vlasnistvo():
    """Supabase mock koji STVARNO sprovodi i `id` i `user_id` filter.

    Nasleđuje `_VlasnickiUpit` (`test_p0d_ownership_and_render.py:127`) — jedini
    mock u repou koji `user_id` ne no-op-uje. Razlika je samo u tome što ovaj
    poznaje VIŠE redova: testovi izolacije traže dva predmeta istog vlasnika
    plus jedan tuđi, a original nosi tačno jedan red.
    """

    class _ViseRedova(_VlasnickiUpit):
        def __init__(self):
            super().__init__(None)

        def execute(self):
            pid = self._f.get("id")
            vlasnik = _PREDMETI.get(pid)
            ok = vlasnik is not None and vlasnik == self._f.get("user_id")
            return MagicMock(data={"id": pid, "user_id": vlasnik} if ok else None)

    supa = MagicMock()
    supa.table.side_effect = lambda ime: _ViseRedova()
    return supa


class _BrojacKonteksta:
    """Omotač oko `_lazni_build_case_context` koji broji pozive.

    Postoji zbog testa C: 404 nije dovoljan dokaz. Mora se dokazati da za tuđ
    `predmet_id` graditelj konteksta NIJE ni pokrenut — `shared/case_context.py:158`
    lansira svih 7 upita ODJEDNOM, pre svoje interne provere vlasništva, pa bi
    tuđi redovi prošli kroz memoriju procesa i pored ispravnog 404-a.
    """

    def __init__(self):
        self.pozivi = []

    async def __call__(self, predmet_id, uid, supa, include_documents=True):
        self.pozivi.append((predmet_id, uid))
        return await _lazni_build_case_context(predmet_id, uid, supa, include_documents)


@pytest.fixture
def brojac_konteksta():
    return _BrojacKonteksta()


@pytest.fixture(autouse=True)
def _okruzenje(brojac_konteksta):
    """Sve što ruta dodiruje osim logike koja se testira.

    Rate limiter se GASI, ne zaobilazi: `@limiter.limit("5/minute")` (odnosno
    `3/minute` na `/sudija-v2`) računa po IP-u, a TestClient uvek dolazi sa
    istog. Bez ovoga bi šesti test u fajlu dobio 429 i pao iz razloga koji nema
    veze sa kontekstom predmeta. `enabled=False` je ugrađen slowapi prekidač
    (`Limiter.__init__:76`), ne zaobilaženje provere.

    `_fetch_praksa_ctx` / `_fetch_zakon_ctx` MORAJU biti mockovani: oni idu na
    Pinecone, a mrežna brana iz `conftest.py` diže `BaseException` koja probija
    njihov fail-soft `except Exception`.
    """
    # Wave 9 — gasi se limiter koji RUTA STVARNO KORISTI, ne onaj koji
    # `shared.rate` trenutno izlaže. Odbrana u dubinu uz popravku u
    # `tests/test_sec005_failopen_limiter.py`.
    #
    # `routers/strategija.py` je uradio `from shared.rate import limiter` pri
    # svom uvozu, pa `@limiter.limit("5/minute")` drži referencu na TU instancu.
    # Ako je neko u međuvremenu uradio `importlib.reload(shared.rate)`,
    # `shared.rate.limiter` je nova instanca, a rute i dalje broje kroz staru —
    # gašenje preko `shared.rate` bi tiho promašilo cilj.
    #
    # `api.app.state.limiter` je treća, posebna instanca (`api.py:554`), koju
    # `SlowAPIMiddleware` koristi za podrazumevani `60/hour` limit. I ona mora
    # da se ugasi, inače je bafer zajednički za ceo suite.
    _limiteri = []
    for _kandidat in (getattr(rs, "limiter", None),
                      getattr(api.app.state, "limiter", None)):
        if _kandidat is not None and _kandidat not in _limiteri:
            _limiteri.append(_kandidat)
    assert _limiteri, "nijedan limiter nije pronađen — provera bi bila prazna"

    _stare_vrednosti = [(_l, _l.enabled) for _l in _limiteri]
    for _l in _limiteri:
        _l.enabled = False

    _stari_cache = dict(_fr._CACHE)
    _stari_ts = _fr._CACHE_LOADED_AT
    _stari_deps_ts = _fr._DEPS_CACHE_LOADED_AT
    _fr._CACHE["strategija"] = {
        "feature_key": "strategija", "aktivno": True, "status": "ACTIVE",
        "addon": None, "minimum_plan": None, "krediti": 1,
        "dnevni_limit": None, "mesecni_limit": None, "cooldown_seconds": None,
        "ai_model": "gpt-4o", "estimated_cost_usd": 0.05, "credit_multiplier": 6,
    }
    _fr._CACHE_LOADED_AT = _time.monotonic()
    _fr._DEPS_CACHE_LOADED_AT = _time.monotonic()

    api.app.dependency_overrides[_shared_get_current_user] = lambda: _KORISNIK

    with patch("shared.permissions._ensure_profile", return_value=_PROFIL), \
         patch("routers.copilot_ambient._get_supa", return_value=_supa_vlasnistvo()), \
         patch("routers.strategija._get_supa", return_value=MagicMock()), \
         patch("shared.case_context.build_case_context", new=brojac_konteksta), \
         patch("routers.strategija._audit", new=AsyncMock()), \
         patch("routers.strategija._audit_strategija_durably", new=MagicMock()), \
         patch("routers.strategija._fetch_praksa_ctx", new=AsyncMock(return_value="")), \
         patch("routers.strategija._fetch_zakon_ctx", new=AsyncMock(return_value="")), \
         patch("routers.strategija.log_cost_to_db", new=AsyncMock()), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=42)) as _consume:
        yield _consume

    api.app.dependency_overrides.pop(_shared_get_current_user, None)
    _fr._CACHE.clear()
    _fr._CACHE.update(_stari_cache)
    _fr._CACHE_LOADED_AT = _stari_ts
    _fr._DEPS_CACHE_LOADED_AT = _stari_deps_ts
    for _l, _v in _stare_vrednosti:
        _l.enabled = _v


@pytest.fixture(scope="module")
def client():
    return TestClient(api.app, raise_server_exceptions=True)


def _posalji(client, putanja, ime_fn, predmet_id=..., **extra):
    """Jedan poziv endpointa sa presretnutom sync funkcijom.

    `predmet_id=...` (Ellipsis) znači „polje se uopšte ne šalje" — to je stara
    putanja koju test B mora dokazati nepromenjenom. `None` se šalje eksplicitno.
    """
    telo = {"tekst": _TEKST}
    if predmet_id is not ...:
        telo["predmet_id"] = predmet_id
    telo.update(extra)

    h = _HvatacSync(ime_fn)
    with patch.object(rs, ime_fn, new=h):
        resp = client.post(putanja, json=telo)
    return resp, h


# ═══════════════════════════════════════════════════════════════════════════
# A. POZITIVAN — kontekst STIŽE do rezonovanja
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("putanja,ime_fn,modul", _MODULI, ids=_IDS)
def test_a_sopstveni_predmet_id_dovodi_kanonski_kontekst(client, putanja, ime_fn, modul):
    """Srž Wave 9.

    Ne proverava da `predmet_id` postoji u telu zahteva — proverava da sadržaj
    TOG predmeta stvarno stigne do funkcije koja gradi prompt, i da odgovor to
    pošteno prijavi.
    """
    resp, h = _posalji(client, putanja, ime_fn, predmet_id=ALFA_ID)

    assert resp.status_code == 200, resp.text
    assert len(h.pozivi) == 1, f"{ime_fn} nije pozvana tačno jednom"

    blok = h.blokovi[0]
    assert blok, f"{ime_fn} je dobila prazan kontekst uprkos validnom predmet_id-u"
    assert ALFA_DOKUMENT in blok, (
        f"dokument predmeta ALFA nije stigao do {ime_fn} — analiza i dalje "
        f"rezonuje samo nad nalepljenim tekstom"
    )

    adv = resp.json()["_ai_advisory"]
    assert adv["kontekst_predmeta"] == "kanonski"
    assert adv["predmet_id"] == ALFA_ID
    assert adv["modul"] == modul
    assert "praćenim predmetom" in adv["napomena"]


def _posalji_do_prompta(client, putanja, predmet_id=...):
    """Kao `_posalji`, ali BEZ zamene sync funkcije — ona se stvarno izvršava.

    Presreće se tek `strategija._pozovi_strategija_api`, pa se meri DOSLOVAN
    tekst poslat modelu. Time jedan test pokriva ceo lanac: ruta → kapija →
    `build_case_context` → serijalizacija → sync funkcija → prompt.
    """
    telo = {"tekst": _TEKST}
    if predmet_id is not ...:
        telo["predmet_id"] = predmet_id
    h = _HvatacPrompta()
    with patch("strategija._pozovi_strategija_api", side_effect=h):
        resp = client.post(putanja, json=telo)
    return resp, h


@pytest.mark.parametrize("putanja,ime_fn,modul", _MODULI, ids=_IDS)
def test_a2_kontekst_stize_do_DOSLOVNOG_prompta(client, putanja, ime_fn, modul):
    """Rupa koju je mutacija M2 otkrila u prvoj verziji ovog fajla.

    `test_a` meri na granici sync funkcije — dokazuje da blok STIGNE do nje.
    Mutacija koja blok primi i tiho baci (`_uz_kontekst_predmeta` vrati ulaz
    nepromenjen) prolazila je `test_a` ZELENO: parametar je i dalje bio
    prosleđen, samo bez ijednog efekta.

    Ovde se sync funkcija ne zamenjuje — izvršava se stvarno, a meri se šta je
    otišlo modelu. „Prosleđeno" i „upotrebljeno" su dva različita tvrđenja i
    traže dva različita merenja.
    """
    resp, h = _posalji_do_prompta(client, putanja, predmet_id=ALFA_ID)

    assert resp.status_code == 200, resp.text
    assert h.pozivi, "nijedan GPT poziv nije napravljen"
    for i, poruka in enumerate(h.user_poruke, start=1):
        assert ALFA_DOKUMENT in poruka, (
            f"{ime_fn}: GPT poziv #{i} ne sadrži dokument predmeta — blok je "
            f"prosleđen, ali nije upotrebljen"
        )


@pytest.mark.parametrize("putanja,ime_fn,modul", _MODULI, ids=_IDS)
def test_a3_bez_predmeta_prompt_ne_sadrzi_nicij_kontekst(client, putanja, ime_fn, modul):
    """Negativna strana istog merenja — inače bi `test_a2` prolazio i da se
    kontekst dodaje bezuslovno, iz keša ili iz pogrešnog predmeta."""
    resp, h = _posalji_do_prompta(client, putanja)
    assert resp.status_code == 200, resp.text
    for poruka in h.user_poruke:
        assert ALFA_DOKUMENT not in poruka and BETA_DOKUMENT not in poruka


# ═══════════════════════════════════════════════════════════════════════════
# B. REGRESIJA — bez predmet_id ponašanje je nepromenjeno
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("putanja,ime_fn,modul", _MODULI, ids=_IDS)
def test_b_bez_predmet_id_radi_tacno_kao_pre(client, putanja, ime_fn, modul):
    """100% današnjeg saobraćaja ide ovom granom — ne sme se pomeriti."""
    resp, h = _posalji(client, putanja, ime_fn)   # polje se uopšte ne šalje

    assert resp.status_code == 200, resp.text
    assert len(h.pozivi) == 1
    assert not h.blokovi[0], "kontekst je izgrađen iako predmet nije prosleđen"

    adv = resp.json()["_ai_advisory"]
    assert adv["kontekst_predmeta"] == "samo_opis"
    assert adv["predmet_id"] is None
    assert "nije provera protiv" in adv["napomena"]


@pytest.mark.parametrize("putanja,ime_fn,modul", _MODULI, ids=_IDS)
def test_b2_bez_predmet_id_ne_dodiruje_bazu(client, brojac_konteksta, putanja, ime_fn, modul):
    """Stara putanja ne sme dobiti ni kapiju ni upit u bazu.

    Bez ovoga bi „radi kao pre" moglo značiti „daje isti odgovor, ali uz sedam
    novih upita po pozivu".
    """
    resp, _ = _posalji(client, putanja, ime_fn)
    assert resp.status_code == 200
    assert brojac_konteksta.pozivi == [], (
        "graditelj konteksta je pokrenut iako predmet_id nije prosleđen"
    )


# ═══════════════════════════════════════════════════════════════════════════
# C. NEGATIVAN / CROSS-TENANT — najvažnija sekcija
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("putanja,ime_fn,modul", _MODULI, ids=_IDS)
def test_c_tudji_predmet_id_daje_404_bez_posla_i_bez_naplate(
    client, _okruzenje, brojac_konteksta, putanja, ime_fn, modul
):
    """Tuđ `predmet_id` mora biti odbijen PRE nego što se išta uradi.

    Tri odvojene tvrdnje, jer 404 sam po sebi ne dokazuje nijednu od druge dve:
      1. HTTP 404 — advokat dobija jasan signal, ne tihu punu analizu.
      2. Sync funkcija NIJE pozvana — nijedan GPT poziv nije plaćen provajderu.
      3. `build_case_context` NIJE pozvan — `shared/case_context.py:158` lansira
         svih 7 upita pre sopstvene provere vlasništva, pa bi tuđi redovi prošli
         kroz memoriju procesa i pored ispravnog statusnog koda.
    """
    consume = _okruzenje
    resp, h = _posalji(client, putanja, ime_fn, predmet_id=TUDJI_ID)

    assert resp.status_code == 404, (
        f"tuđ predmet_id nije odbijen (status {resp.status_code}) — advokat bi "
        f"dobio punu, naplaćenu analizu bez signala da je id odbijen"
    )
    h.assert_not_called()
    assert brojac_konteksta.pozivi == [], (
        f"graditelj konteksta je pokrenut nad tuđim predmetom: {brojac_konteksta.pozivi}"
    )
    consume.assert_not_awaited()


@pytest.mark.parametrize("putanja,ime_fn,modul", _MODULI, ids=_IDS)
def test_c2_tudji_sadrzaj_ne_procuri_ni_u_jedan_prompt(client, putanja, ime_fn, modul):
    """Pozitivna kontrola uz test C: ni pri odbijanju ni pri prolazu tuđi
    marker ne sme se pojaviti u onome što se šalje modelu."""
    _, h_tudji = _posalji(client, putanja, ime_fn, predmet_id=TUDJI_ID)
    assert h_tudji.pozivi == []

    _, h_svoj = _posalji(client, putanja, ime_fn, predmet_id=ALFA_ID)
    for blok in h_svoj.blokovi:
        assert BETA_DOKUMENT not in (blok or ""), "sadržaj drugog predmeta je procureo"


# ═══════════════════════════════════════════════════════════════════════════
# D. NEISPRAVAN ULAZ — bez 500, bez tuđeg konteksta
# ═══════════════════════════════════════════════════════════════════════════

# Prazan string i `None` su FALSY — ruta ih tretira kao „predmet nije prosleđen"
# i vraća 200 sa osiromašenim, ali pošteno označenim kontekstom. Sve ostalo je
# neki id koji kapija ne prepoznaje → 404. Nijedan ulaz ne sme dati 500.
_LOSI_ULAZI = [
    (None, 200),
    ("", 200),
    ("   ", 404),
    ("nije-uuid", 404),
    ("'; DROP TABLE predmeti;--", 404),
    ("../../etc/passwd", 404),
    (NEPOSTOJECI_ID, 404),
]


@pytest.mark.parametrize("putanja,ime_fn,modul", _MODULI, ids=_IDS)
@pytest.mark.parametrize("los_id,ocekivano", _LOSI_ULAZI)
def test_d_neispravan_predmet_id_ne_obara_i_ne_vezuje_tudji_kontekst(
    client, putanja, ime_fn, modul, los_id, ocekivano
):
    """Analiza ne sme pući — ali ni tiho tvrditi da je utemeljena."""
    resp, h = _posalji(client, putanja, ime_fn, predmet_id=los_id)

    assert resp.status_code != 500, f"neispravan predmet_id {los_id!r} je oborio rutu"
    assert resp.status_code == ocekivano, resp.text

    if ocekivano == 200:
        assert not h.blokovi[0], f"{los_id!r} je proizveo kontekst"
        adv = resp.json()["_ai_advisory"]
        assert adv["kontekst_predmeta"] == "samo_opis"
        assert adv["predmet_id"] is None, (
            "odgovor prijavljuje predmet_id iako kontekst nije izgrađen — to bi "
            "advokatu reklo da je AI video spis koji nije video"
        )
    else:
        h.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# E. IZOLACIJA A/B
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("putanja,ime_fn,modul", _MODULI, ids=_IDS)
def test_e_predmet_a_i_predmet_b_daju_razlicit_kontekst(client, putanja, ime_fn, modul):
    """Dokaz da `predmet_id` STVARNO rutira izbor konteksta.

    Da ruta vezuje pogrešan predmet (npr. uvek prvi, ili keširan od prethodnog
    poziva), oba bloka bila bi ista i ovaj test bi pao — testovi A/B/C to ne bi
    primetili, jer svaki gleda samo jedan predmet.
    """
    _, h_alfa = _posalji(client, putanja, ime_fn, predmet_id=ALFA_ID)
    _, h_beta = _posalji(client, putanja, ime_fn, predmet_id=BETA_ID)

    blok_a, blok_b = h_alfa.blokovi[0], h_beta.blokovi[0]
    assert blok_a and blok_b
    assert blok_a != blok_b, "dva različita predmeta dala su identičan kontekst"

    assert ALFA_DOKUMENT in blok_a and BETA_DOKUMENT not in blok_a, (
        "kontekst predmeta B je procureo u poziv za predmet A"
    )
    assert BETA_DOKUMENT in blok_b and ALFA_DOKUMENT not in blok_b, (
        "kontekst predmeta A je procureo u poziv za predmet B"
    )


@pytest.mark.parametrize("putanja,ime_fn,modul", _MODULI, ids=_IDS)
def test_e2_odgovor_prijavljuje_bas_trazeni_predmet(client, putanja, ime_fn, modul):
    """Poreklo u odgovoru mora pratiti isti predmet koji je stvarno korišćen."""
    resp_a, _ = _posalji(client, putanja, ime_fn, predmet_id=ALFA_ID)
    resp_b, _ = _posalji(client, putanja, ime_fn, predmet_id=BETA_ID)
    assert resp_a.json()["_ai_advisory"]["predmet_id"] == ALFA_ID
    assert resp_b.json()["_ai_advisory"]["predmet_id"] == BETA_ID


# ═══════════════════════════════════════════════════════════════════════════
# /v2/analiza — isti testovi A–E, drugačiji oblik
# ═══════════════════════════════════════════════════════════════════════════
#
# Ovaj endpoint nema sync funkciju u `strategija.py`: prompt gradi inline i zove
# `_pozovi_strategija_v2_api`. Zato se hvata na tom nivou — i to je jače merenje
# od ostalih, jer se čita DOSLOVAN tekst poslat modelu, ne međuparametar.


class _HvatacV2:
    def __init__(self):
        self.pozivi = []

    async def __call__(self, oai, **kwargs):
        poruke = kwargs.get("messages") or []
        self.pozivi.append({
            "system": next((p["content"] for p in poruke if p["role"] == "system"), ""),
            "user": next((p["content"] for p in poruke if p["role"] == "user"), ""),
        })
        m = MagicMock()
        m.usage = None
        m.choices = [MagicMock(message=MagicMock(
            content=json.dumps({"procena_uspeha": {"procenat": 50}})
        ))]
        return m


def _posalji_v2(client, predmet_id=...):
    telo = {"opis_predmeta": _TEKST}
    if predmet_id is not ...:
        telo["predmet_id"] = predmet_id
    h = _HvatacV2()
    with patch.object(rs, "_pozovi_strategija_v2_api", new=h):
        resp = client.post("/strategija/v2/analiza", json=telo)
    return resp, h


def test_v2_a_kontekst_stize_u_doslovan_prompt(client):
    resp, h = _posalji_v2(client, predmet_id=ALFA_ID)
    assert resp.status_code == 200, resp.text
    assert len(h.pozivi) == 1
    assert ALFA_DOKUMENT in h.pozivi[0]["user"], "kontekst predmeta nije u promptu"

    adv = resp.json()["_ai_advisory"]
    assert adv["kontekst_predmeta"] == "kanonski"
    assert adv["predmet_id"] == ALFA_ID


def test_v2_a2_sistemski_prompt_povlaci_netacnu_tvrdnju(client):
    """`_V2_SYSTEM` modelu bezuslovno tvrdi „ti nemaš pristup stvarnom predmetu,
    dokazima niti sudskoj praksi specifičnoj za ovaj slučaj".

    Kad kanonski kontekst JESTE prosleđen, ta rečenica je netačna — a netačna
    instrukcija je gora od nikakve: model bi umanjivao nalaze pozivajući se na
    podatke koje je upravo dobio. Ispravka sme da postoji SAMO kad kontekst
    stvarno postoji, inače je ona sama laž u suprotnom smeru.
    """
    _, h_sa = _posalji_v2(client, predmet_id=ALFA_ID)
    _, h_bez = _posalji_v2(client)

    assert "ISPRAVKA GORNJE NAPOMENE" in h_sa.pozivi[0]["system"]
    assert "ISPRAVKA GORNJE NAPOMENE" not in h_bez.pozivi[0]["system"], (
        "sistemski prompt tvrdi da je predmet dostavljen iako nije"
    )
    # Ograda o procentu važi u OBA slučaja i ne sme otpasti uz ispravku.
    for h in (h_sa, h_bez):
        assert "subjektivna" in h.pozivi[0]["system"]


def test_v2_b_bez_predmet_id_prompt_je_bajt_identican(client):
    """Regresija stare putanje, merena doslovnim tekstom."""
    resp, h = _posalji_v2(client)
    assert resp.status_code == 200
    assert h.pozivi[0]["system"] == rs._V2_SYSTEM, "sistemski prompt se promenio"
    assert h.pozivi[0]["user"] == f"Opis predmeta:\n{_TEKST}", "korisnički prompt se promenio"

    adv = resp.json()["_ai_advisory"]
    assert adv["kontekst_predmeta"] == "samo_opis"
    assert adv["predmet_id"] is None


def test_v2_c_tudji_predmet_id_daje_404_bez_poziva_i_naplate(client, _okruzenje, brojac_konteksta):
    consume = _okruzenje
    resp, h = _posalji_v2(client, predmet_id=TUDJI_ID)
    assert resp.status_code == 404
    assert h.pozivi == [], "GPT poziv je izvršen uprkos odbijenom predmet_id-u"
    assert brojac_konteksta.pozivi == []
    consume.assert_not_awaited()


@pytest.mark.parametrize("los_id,ocekivano", _LOSI_ULAZI)
def test_v2_d_neispravan_ulaz(client, los_id, ocekivano):
    resp, h = _posalji_v2(client, predmet_id=los_id)
    assert resp.status_code != 500
    assert resp.status_code == ocekivano, resp.text
    if ocekivano == 200:
        assert ALFA_DOKUMENT not in h.pozivi[0]["user"]
        assert BETA_DOKUMENT not in h.pozivi[0]["user"]


def test_v2_e_izolacija_a_b(client):
    _, h_a = _posalji_v2(client, predmet_id=ALFA_ID)
    _, h_b = _posalji_v2(client, predmet_id=BETA_ID)
    ua, ub = h_a.pozivi[0]["user"], h_b.pozivi[0]["user"]
    assert ALFA_DOKUMENT in ua and BETA_DOKUMENT not in ua
    assert BETA_DOKUMENT in ub and ALFA_DOKUMENT not in ub


# ═══════════════════════════════════════════════════════════════════════════
# SLOJ PROMPTA — blok stvarno ulazi u tekst poslat modelu
# ═══════════════════════════════════════════════════════════════════════════
#
# Testovi A–E dokazuju da blok stigne do sync funkcije. To NIJE isto što i „blok
# je u promptu": funkcija ga je mogla primiti i baciti. Mutacija M2 je tačno taj
# scenario. Ovde se meri doslovan tekst poslat modelu.

M_KANONSKI = "KANONSKI-MARKER-WAVE9-5507"
_BLOK = f"[IZVEDENO IZ BAZE — izračunao sistem, nije iskaz stranke]\n- {M_KANONSKI}"

# (ime funkcije, pozicijski argumenti, očekivan broj GPT poziva)
_SYNC_POZIVI = [
    ("red_team_analiza_sync",      (_TEKST, "sk-test", "", "gradjansko"), 1),
    ("litigation_simulator_sync",  (_TEKST, "sk-test", ""),               1),
    ("ai_judge_mode_sync",         (_TEKST, "sk-test", ""),               1),
    ("due_diligence_analiza_sync", (_TEKST, "sk-test", ""),               1),
    ("pravni_revizor_sync",        (_TEKST, "sk-test"),                   1),
    ("witness_analyzer_sync",      (_TEKST, "sk-test"),                   1),
    # Tri kruga: tužilac → branilac → presuda. Broj je namerno eksplicitan —
    # baš je ova funkcija ranije preživela `replace_all` nesreću iz P0-D.
    ("ai_judge_v2_sync",           (_TEKST, "sk-test"),                   3),
]
_SYNC_IDS = [p[0] for p in _SYNC_POZIVI]


class _HvatacPrompta:
    """Presreće `strategija._pozovi_strategija_api` — jedina tačka kroz koju
    prolaze svi GPT pozivi ovog modula. Obrazac iz
    `tests/test_p0d_case_context_integrity.py:70`."""

    def __init__(self):
        self.pozivi = []

    def __call__(self, client, **kwargs):
        poruke = kwargs.get("messages") or []
        self.pozivi.append({
            "system": next((p["content"] for p in poruke if p["role"] == "system"), ""),
            "user": next((p["content"] for p in poruke if p["role"] == "user"), ""),
        })
        m = MagicMock()
        m.usage = None
        m.choices = [MagicMock(message=MagicMock(content="ODGOVOR"))]
        return m

    @property
    def user_poruke(self):
        return [p["user"] for p in self.pozivi]


def _pokreni_sync(ime, args, **kwargs):
    h = _HvatacPrompta()
    with patch("strategija._pozovi_strategija_api", side_effect=h):
        getattr(strategija, ime)(*args, **kwargs)
    return h


@pytest.mark.parametrize("ime,args,broj", _SYNC_POZIVI, ids=_SYNC_IDS)
def test_p_blok_ulazi_u_SVAKI_gpt_poziv(ime, args, broj):
    """Kod `ai_judge_v2_sync` ovo znači sva tri kruga debate.

    Krug u kome sudija donosi presudu bez konteksta predmeta bio bi tiši i gori
    kvar od potpunog izostanka: dva učesnika bi videla spis, a onaj koji odlučuje
    ne bi.
    """
    h = _pokreni_sync(ime, args, case_context_blok=_BLOK)
    assert len(h.pozivi) == broj, f"{ime}: očekivano {broj} GPT poziva, viđeno {len(h.pozivi)}"
    for i, poruka in enumerate(h.user_poruke, start=1):
        assert M_KANONSKI in poruka, f"{ime}: GPT poziv #{i} ne vidi kontekst predmeta"


@pytest.mark.parametrize("ime,args,broj", _SYNC_POZIVI, ids=_SYNC_IDS)
@pytest.mark.parametrize("prazno", [None, "", "   ", "\n\n"])
def test_p2_prazan_blok_daje_BAJT_IDENTICAN_prompt(ime, args, broj, prazno):
    """Najjača moguća formulacija „radi tačno kao pre".

    Ne „slično" i ne „i dalje 200" — DOSLOVNO isti niz karaktera poslat modelu.
    Prazan blok ne sme proizvesti ni oznaku, ni prazan red, ni naslov bez
    sadržaja (model bi ga popunio pretpostavkom).
    """
    bez = _pokreni_sync(ime, args)
    sa_praznim = _pokreni_sync(ime, args, case_context_blok=prazno)
    assert bez.user_poruke == sa_praznim.user_poruke, (
        f"{ime}: prazan kontekst ({prazno!r}) je promenio prompt"
    )


def test_p3_poreklo_ostaje_razlucivo(ime="due_diligence_analiza_sync"):
    """Dokument koji se recenzira i spis predmeta ne smeju se stopiti.

    Kod modula čiji je primarni subjekt DOKUMENT (`due-diligence`, `revizor`,
    `witness`), blok nosi izričit uvod da nije predmet analize. Bez toga model
    ume da počne da recenzira dokumente iz spisa umesto onog koji mu je dat.
    """
    h = _pokreni_sync(ime, (_TEKST, "sk-test", ""), case_context_blok=_BLOK)
    poruka = h.user_poruke[0]
    assert "nije predmet ove analize" in poruka
    # Oznaka mora stajati PRE svog sadržaja, inače ne označava ništa.
    assert poruka.index("nije predmet ove analize") < poruka.index(M_KANONSKI)
    # Advokatov tekst ostaje prvi — blok se dodaje, ne umeće u sredinu.
    assert poruka.index(_TEKST[:40]) < poruka.index(M_KANONSKI)


def test_p4_kod_predmet_primarnih_modula_nema_dopunskog_uvoda():
    """Razlika u klasifikaciji mora biti vidljiva u samom promptu.

    Kod Red Team-a predmet JESTE subjekt analize — reći modelu „ovo nije predmet
    ove analize" bilo bi netačno i oslabilo bi upravo ono zbog čega je kontekst
    dovučen.
    """
    h = _pokreni_sync("red_team_analiza_sync", (_TEKST, "sk-test", "", "gradjansko"),
                      case_context_blok=_BLOK)
    poruka = h.user_poruke[0]
    assert M_KANONSKI in poruka
    assert "nije predmet ove analize" not in poruka


# ═══════════════════════════════════════════════════════════════════════════
# SIGNATURA — zaštita od tihog loma u produkciji
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ime,args,broj", _SYNC_POZIVI, ids=_SYNC_IDS)
def test_s_case_context_blok_je_KEYWORD_ONLY(ime, args, broj):
    """Isti razlog kao `test_p0d_case_context_integrity.py::test_j`.

    Sve ove funkcije se zovu kroz `asyncio.to_thread` sa POZICIJSKIM prvim
    argumentima, iz rute obavijene širokim `except Exception`. Da je novi
    parametar pozicioni, stari poziv bi mu tiho vezao pogrešnu vrednost i otkazao
    bi NEVIDLJIVO u produkciji. `*` čini takvo vezivanje sintaksno nemogućim.
    """
    import inspect
    p = inspect.signature(getattr(strategija, ime)).parameters
    assert "case_context_blok" in p, f"{ime} ne prima kontekst predmeta"
    assert p["case_context_blok"].kind == p["case_context_blok"].KEYWORD_ONLY
    assert p["case_context_blok"].default is None, "novi parametar mora biti opcion"


@pytest.mark.parametrize("ime,args,broj", _SYNC_POZIVI, ids=_SYNC_IDS)
def test_s2_pozicijsko_prosledjivanje_je_NEMOGUCE(ime, args, broj):
    """Diskriminišući dokaz da `*` stvarno štiti, a ne samo dokumentuje nameru."""
    with pytest.raises(TypeError):
        getattr(strategija, ime)(*args, "kontekst-kao-pozicijski")


@pytest.mark.parametrize("ime,args,broj", _SYNC_POZIVI, ids=_SYNC_IDS)
def test_s3_stari_pozicijski_poziv_i_dalje_radi(ime, args, broj):
    """Kompatibilnost unazad, dokazana izvršavanjem a ne čitanjem potpisa."""
    h = _pokreni_sync(ime, args)
    assert len(h.pozivi) == broj


def test_s4_svi_zahtevni_modeli_nose_predmet_id():
    """Ugovor prema frontendu — polje mora postojati i biti OPCIONO."""
    for model in (rs.StrategijaRequest, rs.StrategijaV2Request, rs.OrkestratorRequest):
        polje = model.model_fields.get("predmet_id")
        assert polje is not None, f"{model.__name__} nema predmet_id"
        assert not polje.is_required(), f"{model.__name__}.predmet_id nije opciono"


# ═══════════════════════════════════════════════════════════════════════════
# NEGATIVNE KONTROLE
# ═══════════════════════════════════════════════════════════════════════════

def test_ng_rute_postoje_pod_tacnim_putanjama():
    """Rupa koju je prvi nacrt ovog fajla stvarno imao.

    Testovi su gađali `/api/strategija/…`, a router je uključen bez `/api`
    prefiksa. Starlette je vraćao 404 „Not Found" — statusnim kodom NERAZLUČIV
    od našeg 404 „Predmet nije pronađen". Ceo test C je time prolazio zeleno nad
    rutom koja ne postoji, ne dokazujući ništa o vlasničkoj kapiji.

    Zato se putanje iz `_MODULI` porede sa stvarnom tabelom ruta aplikacije.
    """
    stvarne = {getattr(r, "path", "") for r in api.app.routes}
    for putanja, _, _ in _MODULI:
        assert putanja in stvarne, f"{putanja} ne postoji u tabeli ruta"
    assert "/strategija/v2/analiza" in stvarne


def test_ng_odbijanje_je_NASE_a_ne_starlette_ovo(client):
    """Drugo pola iste zaštite: 404 mora nositi našu poruku.

    Poređenje putanja iznad dokazuje da ruta postoji; ovo dokazuje da 404 u testu
    C dolazi iz vlasničke kapije, a ne iz rutera.
    """
    resp, _ = _posalji(client, "/strategija/red-team", "red_team_analiza_sync",
                       predmet_id=TUDJI_ID)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Predmet nije pronađen.", (
        f"404 ne dolazi iz vlasničke kapije nego odnekud drugde: {resp.text}"
    )


def test_ng_hvatac_stvarno_hvata(client):
    """Ako bi mock promašio, ceo fajl bi prolazio prazno."""
    _, h = _posalji(client, "/strategija/red-team", "red_team_analiza_sync",
                    predmet_id=ALFA_ID)
    assert len(h.pozivi) == 1
    assert h.pozivi[0]["args"][0] == _TEKST, "hvatač ne vidi stvarne argumente"


def test_ng_mock_vlasnistva_stvarno_odbija(client):
    """Bez ovoga bi test C prolazio i da kapija odbija baš sve.

    Provera je obostrana: isti mock mora pustiti svoj predmet i odbiti tuđi.
    """
    ok, _ = _posalji(client, "/strategija/red-team", "red_team_analiza_sync",
                     predmet_id=ALFA_ID)
    ne, _ = _posalji(client, "/strategija/red-team", "red_team_analiza_sync",
                     predmet_id=TUDJI_ID)
    assert ok.status_code == 200 and ne.status_code == 404


def test_ng_mock_konteksta_razlikuje_predmete():
    """Da `_lazni_build_case_context` vraća fiksan kontekst, testovi E ne bi
    dokazivali ništa o rutiranju po `predmet_id`-u."""
    import asyncio
    a = asyncio.run(_lazni_build_case_context(ALFA_ID, UID_VLASNIK, None))
    b = asyncio.run(_lazni_build_case_context(BETA_ID, UID_VLASNIK, None))
    assert a != b
    assert ALFA_DOKUMENT in json.dumps(a, ensure_ascii=False)
    assert BETA_DOKUMENT in json.dumps(b, ensure_ascii=False)


def test_ng_naplata_se_stvarno_desava_na_uspehu(client, _okruzenje):
    """Test C tvrdi „naplata nije izvršena". Ta tvrdnja vredi samo ako se
    naplata na uspešnoj putanji STVARNO dešava — inače `assert_not_awaited`
    prolazi trivijalno."""
    consume = _okruzenje
    resp, _ = _posalji(client, "/strategija/red-team", "red_team_analiza_sync",
                       predmet_id=ALFA_ID)
    assert resp.status_code == 200
    consume.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════
# NEDEFINISANA IMENA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("modul", ["strategija.py", "routers/strategija.py"])
def test_n_nema_nedefinisanih_imena(modul):
    """Razred greške koji je P0-D zamalo isporučio, i koji `py_compile` NE vidi.

    `replace_all` nad `f"Predmet:\\n\\n{opis_predmeta}"` tada je pogodio i
    `ai_judge_v2_sync` — funkciju koja tu promenljivu nema — što bi bio
    `NameError` na živoj putanji AI Sudije. Wave 9 dira tačno iste f-stringove,
    pa provera ostaje obavezna.

    Proverava se ISKLJUČIVO F821. Neiskorišćeni importi i slična higijena se
    namerno ne diraju — to bi bilo šire čišćenje van obima.
    """
    pyflakes = pytest.importorskip("pyflakes.api")
    reporter = pytest.importorskip("pyflakes.reporter")

    putanja = os.path.join(os.path.dirname(__file__), "..", *modul.split("/"))
    out, err = io.StringIO(), io.StringIO()
    pyflakes.checkPath(putanja, reporter.Reporter(out, err))

    nedefinisana = [r for r in out.getvalue().splitlines() if "undefined name" in r]
    assert not nedefinisana, "nedefinisana imena:\n  " + "\n  ".join(nedefinisana)
