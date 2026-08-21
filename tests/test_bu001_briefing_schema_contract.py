# -*- coding: utf-8 -*-
"""B-U-001 — jutarnji brifing mora biti usklađen sa PRODUKCIONOM šemom.

PRE-STATE (dokazano uživo na produkciji `6bf8070`, 2026-08-21):
  `GET /api/briefing/daily` → HTTP 500 za SVAKOG korisnika.
  `routers/morning_briefing.py::_generiši_briefing` je tražio tri kolone koje u
  produkcionoj bazi ne postoje:
      predmeti.stranka          → 42703
      predmeti.protivnik        → 42703
      klijenti.naziv_kompanije  → 42703
  Upiti su bili u `asyncio.gather` BEZ `return_exceptions=True`, pa je pad jednog
  izvora rušio ceo brifing. Greška postoji od uvođenja brifinga (`c86f525e`,
  2026-06-28) — dakle endpoint nikada nije radio na produkciji.

ZAŠTO GA NIJEDAN OD 5 POSTOJEĆIH TEST FAJLOVA NIJE UHVATIO:
  svi mock-uju Supabase klijenta lažnjakom koji ignoriše imena kolona i vraća
  šta god test zada. `column X does not exist` u takvom svetu ne može da nastane.
  Zato lažnjak u OVOM fajlu (`_Sema`) validira svaki `.select(...)` protiv skupa
  kolona **sondiranog direktno nad produkcionom bazom** i puca 42703 isto kao
  PostgREST. `test_META_*` dokazuje da lažnjak stvarno puca — bez toga bi svi
  ostali testovi u fajlu bili prazni.

INVARIJANTE:
  1. Brifing sme da traži samo kolone koje postoje u produkciji.
  2. Pad jednog izvora ne sme da obori ceo brifing (nema 500).
  3. FAILED != EMPTY: pao izvor ne sme da proizvede tvrdnju o odsustvu obaveza.
"""
import asyncio
import io
import re

import pytest
from unittest.mock import MagicMock, patch

import routers.morning_briefing as mb

UID = "00000000-0000-0000-0000-000000000001"
TUDJI_UID = "00000000-0000-0000-0000-0000000000ff"

# ── Kanonska produkciona šema ────────────────────────────────────────────────
# Sondirano nad produkcionom bazom 2026-08-21 (`SELECT <kolona> LIMIT 1`;
# 42703 = ne postoji). Ovo NIJE prepisano iz migracija ni iz modela — baza je
# autoritet. Namerno su izostavljene `stranka`, `protivnik`, `stranke`,
# `klijent`, `klijent_id`, `oblast`, `sud` (predmeti) i `naziv_kompanije`,
# `naziv_firme`, `tip_lica` (klijenti) — sve su vraćale 42703.
SEMA = {
    "predmeti": {"id", "naziv", "status", "tuzilac", "tuzeni", "opis", "tip",
                 "updated_at", "created_at", "user_id", "brisanje_zapoceto"},
    "klijenti": {"id", "ime", "prezime", "firma", "tip", "email", "status",
                 "aktivan", "user_id"},
    "rocista": {"id", "sud", "datum", "vreme", "predmet_id", "status", "user_id"},
    "predmet_hronologija": {"id", "predmet_id", "dogadjaj", "datum_iso", "datum",
                            "vaznost", "akter", "user_id"},
    "briefing_istorija": {"user_id", "datum", "ai_briefing", "statistike", "created_at"},
}


class _Drift42703(Exception):
    """Isti oblik greške koji PostgREST vraća za nepostojeću kolonu."""


class _Upit:
    """Lanac filtera; `select()` se validira protiv `SEMA`."""

    def __init__(self, dnevnik, tabela, redovi, greska):
        self._d, self._t, self._r, self._g = dnevnik, tabela, redovi, greska

    def select(self, kolone="*", *a, **k):
        if kolone != "*":
            poznate = SEMA.get(self._t, set())
            for kol in [c.strip() for c in re.split(r",", kolone) if c.strip()]:
                if kol not in poznate:
                    raise _Drift42703(
                        "column %s.%s does not exist (42703)" % (self._t, kol))
        self._d["select"].append((self._t, kolone))
        return self

    def eq(self, kolona, vrednost):
        self._d["eq"].append((self._t, kolona, vrednost))
        return self

    def __getattr__(self, ime):
        def poziv(*a, **k):
            return self
        return poziv

    def execute(self):
        if self._g is not None:
            raise self._g
        m = MagicMock()
        m.data = list(self._r)
        return m


def _supa(redovi=None, greske=None):
    """`redovi`/`greske` su mape tabela → redovi / izuzetak."""
    redovi, greske = redovi or {}, greske or {}
    dnevnik = {"select": [], "eq": [], "tabele": []}
    m = MagicMock()

    def _table(ime):
        dnevnik["tabele"].append(ime)
        return _Upit(dnevnik, ime, redovi.get(ime, []), greske.get(ime))

    m.table.side_effect = _table
    m._dnevnik = dnevnik
    return m


def _brifing(supa, uid=UID):
    """Model je namerno nedostupan — meri se deterministički sastavljen tekst,
    ne odgovor GPT-a (i test ne zove naplativi API)."""
    def _bez_modela(*a, **k):
        raise RuntimeError("model namerno nedostupan u testu")

    with patch.object(mb, "_get_supa", return_value=supa), \
         patch("openai.OpenAI", side_effect=_bez_modela):
        b = asyncio.run(mb._generiši_briefing(uid, supa))
    tekst = " ".join(str(v) for v in b.values() if isinstance(v, str))
    return b, tekst


TVRDNJE_ODSUSTVA = (
    "Nema hitnih rokova u narednih 7 dana.",
    "Nema hitnih obaveza za danas",
    "miran dan",
    "Nema otvorenih akcija u Case Actions ni za jedan predmet.",
)

PREDMET = {"id": "p1", "naziv": "Marković protiv Delta", "status": "aktivan",
           "tuzilac": "Marko Marković", "tuzeni": "Delta DOO",
           "updated_at": "2026-08-20"}


# ── META: lažnjak mora stvarno da puca, inače je ceo fajl prazan ─────────────

def test_META_sema_hvata_nepostojecu_kolonu():
    """Bez ovoga bi svi testovi ispod prolazili i sa pogrešnim imenom kolone."""
    s = _supa()
    with pytest.raises(_Drift42703):
        s.table("predmeti").select("id, stranka")
    with pytest.raises(_Drift42703):
        s.table("klijenti").select("naziv_kompanije")
    # kontrola: kanonska imena NE smeju da pucaju
    s.table("predmeti").select("id, naziv, tuzilac, tuzeni")
    s.table("klijenti").select("firma")


# ── 1. Kanonske kolone ───────────────────────────────────────────────────────

def test_1_brifing_koristi_samo_postojece_kolone():
    """Isti kvar kao na produkciji podigao bi _Drift42703 iz lažnjaka."""
    b, _ = _brifing(_supa(redovi={"predmeti": [PREDMET]}))
    assert b["predmeti_dostupni"] is True
    assert b["rokovi_dostupni"] is True
    assert b["rocista_dostupna"] is True


def test_1b_staticki_nijedno_mrtvo_ime_kolone_nije_ostalo():
    """Statička brana: imena koja produkcija odbija ne smeju biti u modulu."""
    src = io.open("routers/morning_briefing.py", encoding="utf-8").read()
    for mrtvo in ("naziv_kompanije", "p.get('stranka'", 'p.get("stranka"'):
        assert mrtvo not in src, "mrtvo ime kolone %r i dalje u modulu" % mrtvo
    # `stranka`/`protivnik` ne smeju biti u NIJEDNOM select-u
    for select_str in re.findall(r'\.select\(\s*"([^"]+)"', src):
        kolone = {c.strip() for c in select_str.split(",")}
        assert not (kolone & {"stranka", "protivnik", "stranke", "naziv_kompanije"}), \
            "select %r traži kolonu koje nema u produkciji" % select_str


def test_1c_mrtav_upit_nad_klijentima_je_uklonjen():
    """`klijenti_r` se dodeljivao i nikad čitao — a rušio je ceo brifing."""
    s = _supa(redovi={"predmeti": [PREDMET]})
    _brifing(s)
    assert "klijenti" not in s._dnevnik["tabele"], \
        "brifing i dalje čita `klijenti` iako rezultat nigde ne koristi"


# ── 2. Normalno stanje ───────────────────────────────────────────────────────

def test_2_normalan_brifing_broji_stvarne_predmete():
    async def _fake_ctx(pid, uid, supa, include_documents=False):
        return {"readiness": {"value": {"status": "READY"}}, "active_actions": {"value": []}}

    with patch.object(mb, "build_case_context", side_effect=_fake_ctx):
        b, _ = _brifing(_supa(redovi={"predmeti": [PREDMET]}))
    assert b["statistike"]["aktivnih_predmeta"] == 1
    assert b["predmeti_dostupni"] is True


def test_2b_stranke_ulaze_u_kontekst_modela():
    uhvacen = {}

    def _uhvati(client, **kw):
        uhvacen["prompt"] = kw["messages"][0]["content"]
        raise RuntimeError("dalje ne treba")

    async def _fake_ctx(pid, uid, supa, include_documents=False):
        return {"readiness": {"value": {}}, "active_actions": {"value": []}}

    with patch.object(mb, "_pozovi_briefing_sync_api", side_effect=_uhvati), \
         patch.object(mb, "build_case_context", side_effect=_fake_ctx), \
         patch.object(mb, "_get_supa", return_value=None), \
         patch("openai.OpenAI", return_value=MagicMock()):
        asyncio.run(mb._generiši_briefing(UID, _supa(redovi={"predmeti": [PREDMET]})))
    assert "Marko Marković protiv Delta DOO" in uhvacen["prompt"], uhvacen["prompt"][:400]


# ── 3. Legitimno prazno stanje ───────────────────────────────────────────────

def test_3_prazno_stanje_sme_da_tvrdi_odsustvo():
    """Bez ovoga bi „popravka" koja uvek ćuti prolazila kao ispravna."""
    b, tekst = _brifing(_supa())
    assert (b["predmeti_dostupni"], b["rokovi_dostupni"], b["rocista_dostupna"]) == (True, True, True)
    assert b["statistike"]["aktivnih_predmeta"] == 0
    assert "Nema hitnih rokova u narednih 7 dana." in tekst


# ── 4./5. Pad izvora: bez 500 i bez lažnog odsustva ──────────────────────────

KVAROVI = {
    "42703_kolona": _Drift42703("column predmeti.izmisljena does not exist (42703)"),
    "PGRST205_tabela": Exception("Could not find the table (PGRST205)"),
    "42501_rls": Exception("row-level security policy violated (42501)"),
    "timeout": TimeoutError("connection timeout expired"),
}


@pytest.mark.parametrize("kvar", sorted(KVAROVI))
def test_4_pad_predmeta_ne_rusi_brifing(kvar):
    b, tekst = _brifing(_supa(greske={"predmeti": KVAROVI[kvar]}))
    assert b["predmeti_dostupni"] is False, kvar
    assert "Predmeti nisu pročitani iz baze" in tekst, kvar
    assert "Nema otvorenih akcija u Case Actions ni za jedan predmet." not in tekst, \
        "pao upit nad predmetima proizveo tvrdnju o odsustvu akcija (%s)" % kvar


@pytest.mark.parametrize("kvar", sorted(KVAROVI))
def test_5_pad_rocista_ne_tvrdi_odsustvo(kvar):
    b, tekst = _brifing(_supa(greske={"rocista": KVAROVI[kvar]}))
    assert b["rocista_dostupna"] is False, kvar
    for tvrdnja in TVRDNJE_ODSUSTVA[:3]:
        assert tvrdnja not in tekst, \
            "pao upit nad ročištima proizveo tvrdnju %r (%s)" % (tvrdnja, kvar)


def test_5b_pad_rokova_i_dalje_postuje_stari_ugovor():
    """Regresija na BETA-DEADLINE-DOMAIN-001 / DRIFT-002."""
    b, tekst = _brifing(_supa(greske={"predmet_hronologija": KVAROVI["42501_rls"]}))
    assert b["rokovi_dostupni"] is False
    assert "nisu pročitani iz baze" in tekst
    for tvrdnja in TVRDNJE_ODSUSTVA[:3]:
        assert tvrdnja not in tekst


def test_6_pad_jednog_izvora_ne_gubi_ostale():
    """Izolacija ne sme da postane tiho odbacivanje svega ostalog."""
    b, _ = _brifing(_supa(
        redovi={"rocista": [{"id": "r1", "sud": "Osnovni sud u Nišu",
                             "datum": mb.date.today().isoformat(), "vreme": "09:00",
                             "predmet_id": "p1", "status": "zakazano"}]},
        greske={"predmeti": KVAROVI["timeout"]}))
    assert b["predmeti_dostupni"] is False
    assert b["rocista_dostupna"] is True
    assert b["statistike"]["rocista_danas"] == 1, "ročište je izgubljeno zbog tuđeg pada"


def test_7_svi_izvori_padaju_odjednom():
    b, tekst = _brifing(_supa(greske={t: KVAROVI["timeout"]
                                      for t in ("predmeti", "rocista", "predmet_hronologija")}))
    assert (b["predmeti_dostupni"], b["rokovi_dostupni"], b["rocista_dostupna"]) == (False, False, False)
    for tvrdnja in TVRDNJE_ODSUSTVA:
        assert tvrdnja not in tekst, tvrdnja
    assert "nisu dostupni" in tekst


def test_7b_pad_konteksta_predmeta_ne_tvrdi_odsustvo_akcija():
    """„Danas zahteva pažnju" se izvodi iz PRAZNE liste akcija. Ako izgradnja
    konteksta padne, prazna lista nije dokaz da otvorenih akcija nema."""
    async def _pukni(pid, uid, supa, include_documents=False):
        raise RuntimeError("case_context nedostupan")

    with patch.object(mb, "build_case_context", side_effect=_pukni):
        b, tekst = _brifing(_supa(redovi={"predmeti": [PREDMET]}))
    assert b["predmeti_dostupni"] is True, "lista predmeta JESTE pročitana"
    assert b["akcije_dostupne"] is False
    assert "Nema otvorenih akcija u Case Actions ni za jedan predmet." not in tekst
    assert "miran dan" not in tekst


def test_7c_uspesan_kontekst_bez_akcija_SME_da_tvrdi_odsustvo():
    """Kontrola: bez ovoga bi „popravka" koja uvek ćuti prolazila."""
    async def _prazan(pid, uid, supa, include_documents=False):
        return {"readiness": {"value": {}}, "active_actions": {"value": []}}

    with patch.object(mb, "build_case_context", side_effect=_prazan):
        b, tekst = _brifing(_supa(redovi={"predmeti": [PREDMET]}))
    assert b["akcije_dostupne"] is True
    assert "Nema otvorenih akcija u Case Actions ni za jedan predmet." in tekst


# ── 8. Tenant izolacija ──────────────────────────────────────────────────────

def test_8_svaki_upit_je_ogranicen_na_vlasnika():
    # `build_case_context` i sam čita `predmeti` sa `.eq("user_id", uid)`. Bez
    # ovog isključivanja njegov filter maskira nedostatak filtera u SAMOM
    # brifingu — mereno: mutacija „ukloni tenant filter" je preživela.
    async def _fake_ctx(pid, uid, supa, include_documents=False):
        return {"readiness": {"value": {}}, "active_actions": {"value": []}}

    s = _supa(redovi={"predmeti": [PREDMET]})
    with patch.object(mb, "build_case_context", side_effect=_fake_ctx):
        _brifing(s, uid=UID)
    po_tabeli = {}
    for tabela, kolona, vrednost in s._dnevnik["eq"]:
        if kolona == "user_id":
            po_tabeli.setdefault(tabela, set()).add(vrednost)
    for tabela in ("predmeti", "rocista", "predmet_hronologija"):
        assert po_tabeli.get(tabela) == {UID}, \
            "%s nije ograničen na vlasnika: %r" % (tabela, po_tabeli.get(tabela))
    assert TUDJI_UID not in {v for vs in po_tabeli.values() for v in vs}


# ── 9. Autorizacija ostaje identična ─────────────────────────────────────────

def test_9_autorizacija_endpointa_nepromenjena():
    src = io.open("routers/morning_briefing.py", encoding="utf-8").read()
    i = src.index('@router.get("/api/briefing/daily")')
    blok = src[i:i + 400]
    assert 'PermissionService.require("morning_briefing")' in blok
    assert '@limiter.limit("10/minute")' in blok
