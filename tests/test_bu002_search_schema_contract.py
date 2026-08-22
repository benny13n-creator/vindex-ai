# -*- coding: utf-8 -*-
"""B-U-002 — globalna pretraga mora da nađe postojećeg klijenta.

PRE-STATE (dokazano uživo na produkciji `6bf8070`, 2026-08-21):
  klijent kreiran preko `POST /klijenti` → 200, potvrđen u bazi,
  `GET /klijenti` ga prikazuje, a `GET /api/search?q=<ime>` vraća
      {"ukupno": 0, "klijenti": [], "nepotpuno": ["klijenti"]}
  Cela `klijenti` grana pretrage bacala je izuzetak na SVAKI poziv, jer je
  gađala DVE nepostojeće kolone (sondirano nad produkcijom):
      klijenti.naziv_firme → 42703   (kanonska je `firma`)
      klijenti.pib         → 42703   (PIB postoji samo kao `pib_encrypted`)
  Obe su bile i u `.select(...)` i u `.or_(...)` filteru.

KANONSKI DOKAZ ZA `firma`: `GET /klijenti` (klijenti/router.py:331,335) radi
  `.select("id,tip,ime,prezime,firma,...")` i `.or_("ime.ilike…,prezime.ilike…,
  firma.ilike…")` — isti obrazac, kanonsko ime.
KANONSKI DOKAZ ZA `pib`: klijenti/router.py:292,530 upisuju
  `pib_encrypted = encrypt_field(req.pib)`, :456 dekriptuje pri čitanju.
  `ilike` nad šifratom ne može da pogodi otvoren tekst → pretraga po PIB-u
  nije pitanje imena kolone nego proizvodne odluke; kolona je uklonjena i
  NIJE zamenjena drugim identifikatorom.

INVARIJANTE:
  1. Pretraga sme da gađa samo kolone koje postoje u produkciji.
  2. Postojeći klijent se nalazi; nepostojeći se ne prikazuje.
  3. `nepotpuno` se pojavljuje SAMO kad izvor stvarno nije pročitan.
  4. Rezultati su ograničeni na vlasnika.
"""
import asyncio

import pytest
from unittest.mock import patch

import routers.search as S
from tests._schema_fake import Drift42703, napravi_supa

UID_A = "00000000-0000-0000-0000-00000000000a"
UID_B = "00000000-0000-0000-0000-00000000000b"

# ── Kanonska produkciona šema ────────────────────────────────────────────────
# Sondirano nad produkcionom bazom 2026-08-22 (`SELECT <kolona> LIMIT 1`;
# 42703 = ne postoji). Namerno izostavljene: klijenti.naziv_firme,
# klijenti.naziv_kompanije, klijenti.naziv, klijenti.pib, klijenti.tip_lica.
SEMA = {
    "klijenti": {"id", "tip", "ime", "prezime", "firma", "email", "telefon",
                 "status", "aktivan", "deleted_at", "user_id", "pib_encrypted",
                 "jmbg_encrypted", "maticni_broj", "kreirano", "azurirano",
                 "datum_poslednje_aktivnosti"},
    "predmeti": {"id", "naziv", "opis", "tip", "status", "user_id",
                 "updated_at", "created_at", "tuzilac", "tuzeni"},
    "predmet_dokumenti": {"id", "naziv_fajla", "predmet_id", "status",
                          "tekst_sadrzaj", "tip_dokaza", "created_at", "user_id"},
    "billing_entries": {"id", "opis", "iznos_rsd", "predmet_id", "datum", "user_id"},
    "zadaci": {"id", "naziv", "opis", "status", "prioritet", "predmet_id",
               "rok_datum", "kreirao_uid", "dodeljen_uid", "kancelarija_id"},
    "predmet_hronologija": {"id", "predmet_id", "dogadjaj", "datum_iso", "vaznost", "user_id"},
    "predmet_beleske": {"id", "predmet_id", "sadrzaj", "created_at", "user_id", "tip"},
}

MERIDIJAN = {"id": "k1", "user_id": UID_A, "ime": "", "prezime": "",
             "firma": "MERIDIJAN LOGISTIKA DOO", "email": "office@meridijan.rs",
             "status": "aktivan"}
FIZICKO = {"id": "k2", "user_id": UID_A, "ime": "Petar", "prezime": "Petrović",
           "firma": "", "email": "petar@primer.rs", "status": "aktivan"}
TUDJI = {"id": "k9", "user_id": UID_B, "ime": "", "prezime": "",
         "firma": "OMEGA GRADNJA DOO", "email": "info@omega.rs", "status": "aktivan"}

SVI_KLIJENTI = [MERIDIJAN, FIZICKO, TUDJI]


def _lazni_request():
    """`@limiter.limit` zahteva pravi starlette Request (isti obrazac koji već
    koristi tests/test_coi_intake_convergence.py)."""
    from starlette.requests import Request
    return Request({"type": "http", "method": "GET", "path": "/api/search",
                    "headers": [], "query_string": b"",
                    "client": ("127.0.0.1", 0), "server": ("testserver", 80),
                    "scheme": "http", "root_path": "", "app": None})


def _pretrazi(q, uid=UID_A, redovi=None, greske=None, vrste=None, limit=5):
    supa = napravi_supa(SEMA, redovi=redovi if redovi is not None else
                        {"klijenti": SVI_KLIJENTI}, greske=greske)
    with patch.object(S, "_get_supa", return_value=supa):
        rez = asyncio.run(S.global_search(
            request=_lazni_request(), q=q, vrste=vrste, limit=limit,
            user={"user_id": uid}))
    return rez, supa


def _imena(rez):
    return [x["naziv"] for x in (rez.get("klijenti") or [])]


# ── META: lažnjak mora stvarno da puca ───────────────────────────────────────

def test_META_laznjak_hvata_obe_mrtve_kolone():
    """Bez ovoga bi svi testovi ispod prolazili i sa `naziv_firme`/`pib`."""
    s = napravi_supa(SEMA)
    with pytest.raises(Drift42703):
        s.table("klijenti").select("id, naziv_firme")
    with pytest.raises(Drift42703):
        s.table("klijenti").select("id, pib")
    # i u FILTERU, ne samo u select-u -- tamo je pola kvara i bilo
    with pytest.raises(Drift42703):
        s.table("klijenti").or_("naziv_firme.ilike.%x%")
    with pytest.raises(Drift42703):
        s.table("klijenti").ilike("pib", "%x%")
    # kontrola: kanonska imena ne smeju da pucaju
    s.table("klijenti").select("id, ime, prezime, firma, email").or_(
        "ime.ilike.%x%,prezime.ilike.%x%,firma.ilike.%x%,email.ilike.%x%")


# ── 1. Postojeći klijent se NALAZI ───────────────────────────────────────────

def test_1_postojeci_klijent_se_nalazi():
    rez, _ = _pretrazi("MERIDIJAN")
    assert "MERIDIJAN LOGISTIKA DOO" in _imena(rez), rez
    assert rez["ukupno"] >= 1
    assert "nepotpuno" not in rez, "zdrav izvor ne sme da bude prijavljen kao nepotpun"


def test_1b_fizicko_lice_po_imenu_i_prezimenu():
    assert "Petar Petrović" in _imena(_pretrazi("Petrović")[0])
    assert "Petar Petrović" in _imena(_pretrazi("Petar")[0])


def test_1c_po_email_adresi():
    """`email` kolona POSTOJI — ta mogućnost se ne sme izgubiti uz popravku."""
    assert "MERIDIJAN LOGISTIKA DOO" in _imena(_pretrazi("office@meridijan")[0])


# ── 2. Nepostojeći klijent se NE prikazuje ───────────────────────────────────

def test_2_nepostojeci_klijent_se_ne_prikazuje():
    rez, _ = _pretrazi("NEPOSTOJECA FIRMA XYZ")
    assert _imena(rez) == []
    assert "nepotpuno" not in rez, "prazan rezultat NIJE kvar izvora"


def test_2b_soft_deleted_klijent_se_NE_prikazuje():
    """Mereno pre push-a: oživljena grana bi bez filtera NOVO prikazivala
    obrisane klijente — kvar koji ranije nije postojao samo zato što grana
    nikad nije ni radila. Kanonski `GET /klijenti` (klijenti/router.py:334)
    ih krije preko `status != 'soft_deleted'`."""
    obrisan = {"id": "kX", "user_id": UID_A, "ime": "", "prezime": "",
               "firma": "OBRISANA FIRMA DOO", "email": "x@y.rs",
               "status": "soft_deleted"}
    rez, _ = _pretrazi("OBRISANA", redovi={"klijenti": [obrisan]})
    assert _imena(rez) == [], "pretraga vraća soft-deleted klijenta"
    assert "nepotpuno" not in rez


def test_2c_aktivan_klijent_prolazi_kroz_isti_filter():
    """Kontrola: filter ne sme da pojede zdrave redove."""
    aktivan = {"id": "kY", "user_id": UID_A, "ime": "Ana", "prezime": "Anić",
               "firma": "", "email": "ana@primer.rs", "status": "aktivan"}
    assert "Ana Anić" in _imena(_pretrazi("Anić", redovi={"klijenti": [aktivan]})[0])


def test_2d_PRIZNATO_OGRANICENJE_klijent_sa_NULL_statusom_ispada():
    """Ne skriva se — pribija se.

    `NULL <> 'soft_deleted'` je u SQL-u NULL, pa red ispada. Isto važi i za
    kanonski `GET /klijenti`, koji koristi identičan filter. Mereno nad
    produkcijom 2026-08-22: 5 klijenata, svih 5 `status='aktivan'`, NULL: 0 —
    dakle danas ovaj filter ne jede nijedan red. Ako se ikad pojavi red sa
    NULL statusom, OVAJ test pada i pokazuje tačno gde je problem, umesto da
    klijent tiho nestane iz pretrage."""
    bez_statusa = {"id": "kZ", "user_id": UID_A, "ime": "Bez", "prezime": "Statusa",
                   "firma": "", "email": "b@primer.rs", "status": None}
    rez, _ = _pretrazi("Statusa", redovi={"klijenti": [bez_statusa]})
    assert _imena(rez) == [], (
        "ponašanje se promenilo — ako `neq` više ne izbacuje NULL, ovo je "
        "dobra vest, ali ugovor mora da se ažurira svesno, ne slučajno")


# ── 3. Delimičan upit ────────────────────────────────────────────────────────

def test_3_delimican_upit_radi_kao_i_ostali_izvori():
    """`ilike %q%` je postojeći ugovor svih izvora — ne menja se."""
    assert "MERIDIJAN LOGISTIKA DOO" in _imena(_pretrazi("meri")[0])
    assert "MERIDIJAN LOGISTIKA DOO" in _imena(_pretrazi("LOGISTIKA")[0])


# ── 4. Više rezultata + limit ────────────────────────────────────────────────

def test_4_vise_klijenata_i_limit():
    mnogi = [{"id": "m%d" % i, "user_id": UID_A, "ime": "", "prezime": "",
              "firma": "ALFA %02d DOO" % i, "email": "a%d@alfa.rs" % i,
              "status": "aktivan"} for i in range(8)]
    rez, _ = _pretrazi("ALFA", redovi={"klijenti": mnogi}, limit=5)
    assert len(rez["klijenti"]) == 5, "limit se ne poštuje"
    rez2, _ = _pretrazi("ALFA", redovi={"klijenti": mnogi}, limit=10)
    assert len(rez2["klijenti"]) == 8


# ── 5. Prazna baza ───────────────────────────────────────────────────────────

def test_5_prazna_baza_daje_validan_prazan_rezultat():
    rez, _ = _pretrazi("bilo", redovi={})
    assert rez["ukupno"] == 0
    assert rez["klijenti"] == []
    assert "nepotpuno" not in rez


# ── 6./7. Izolacija tenanta ──────────────────────────────────────────────────

def test_6_tenant_A_vidi_svoje():
    assert "MERIDIJAN LOGISTIKA DOO" in _imena(_pretrazi("MERIDIJAN", uid=UID_A)[0])


def test_7_tenant_B_NE_vidi_klijenta_tenanta_A():
    rez, _ = _pretrazi("MERIDIJAN", uid=UID_B)
    assert _imena(rez) == [], "CROSS-TENANT curenje u pretrazi klijenata"
    # `q` je eho korisnikovog upita, ne podatak tenanta A — proverava se SADRŽAJ
    # svih grupa rezultata, ne ceo odgovor.
    rezultati = {k: v for k, v in rez.items() if isinstance(v, list)}
    assert "MERIDIJAN" not in str(rezultati)
    assert "office@meridijan.rs" not in str(rez)


def test_7b_upit_nad_klijentima_nosi_filter_vlasnika():
    """Strukturalna brana: scope se ne sme oslanjati na sreću."""
    _, supa = _pretrazi("MERIDIJAN", uid=UID_A)
    eq_klijenti = [(k, v) for (t, k, v) in supa._dnevnik["eq"] if t == "klijenti"]
    assert ("user_id", UID_A) in eq_klijenti, eq_klijenti


# ── 8. Ostali izvori bez regresije ───────────────────────────────────────────

def test_8_ostali_izvori_i_dalje_rade():
    redovi = {
        "klijenti": SVI_KLIJENTI,
        "predmeti": [{"id": "p1", "user_id": UID_A, "naziv": "MERIDIJAN parnica",
                      "opis": "", "tip": "parnicno", "status": "aktivan"}],
        "billing_entries": [{"id": "b1", "user_id": UID_A, "opis": "MERIDIJAN savet",
                             "iznos_rsd": 1000, "predmet_id": "p1", "datum": "2026-08-01"}],
        "predmet_beleske": [{"id": "n1", "user_id": UID_A, "predmet_id": "p1",
                             "sadrzaj": "MERIDIJAN beleska", "created_at": "2026-08-01"}],
    }
    rez, _ = _pretrazi("MERIDIJAN", redovi=redovi)
    assert len(rez["predmeti"]) == 1
    assert len(rez["billing"]) == 1
    assert len(rez["beleske"]) == 1
    assert len(rez["klijenti"]) == 1
    assert "nepotpuno" not in rez
    assert rez["ukupno"] == 4


def test_8b_svi_izvori_koriste_samo_postojece_kolone():
    """Ceo endpoint prolazi kroz lažnjaka koji validira SVAKO ime kolone."""
    rez, _ = _pretrazi("MERIDIJAN", redovi={"klijenti": SVI_KLIJENTI})
    assert "nepotpuno" not in rez, \
        "neki izvor i dalje gađa nepostojeću kolonu: %s" % rez.get("nepotpuno")


# ── 9. Nevalidan upit ────────────────────────────────────────────────────────

@pytest.mark.parametrize("q", ["", " ", "a", " x "])
def test_9_prekratak_upit_i_dalje_daje_422(q):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ex:
        _pretrazi(q)
    assert ex.value.status_code == 422


# ── 10. `nepotpuno` samo za stvarni pad ──────────────────────────────────────

KVAROVI = {
    "42703_kolona": Drift42703("column klijenti.izmisljena does not exist (42703)"),
    "PGRST205_tabela": Exception("Could not find the table (PGRST205)"),
    "42501_rls": Exception("row-level security policy violated (42501)"),
    "timeout": TimeoutError("connection timeout expired"),
}


@pytest.mark.parametrize("kvar", sorted(KVAROVI))
def test_10_pad_izvora_je_prijavljen_a_ne_predstavljen_kao_prazno(kvar):
    rez, _ = _pretrazi("MERIDIJAN", greske={"klijenti": KVAROVI[kvar]})
    assert rez.get("nepotpuno") == ["klijenti"], kvar
    assert rez["klijenti"] == []


def test_10b_pad_JEDNOG_izvora_ne_gubi_ostale():
    redovi = {"klijenti": SVI_KLIJENTI,
              "predmeti": [{"id": "p1", "user_id": UID_A, "naziv": "MERIDIJAN parnica",
                            "opis": "", "tip": "parnicno", "status": "aktivan"}]}
    rez, _ = _pretrazi("MERIDIJAN", redovi=redovi,
                       greske={"klijenti": KVAROVI["timeout"]})
    assert rez.get("nepotpuno") == ["klijenti"]
    assert len(rez["predmeti"]) == 1, "pad klijenata je odneo i predmete"


def test_10c_pad_i_prazno_daju_RAZLICIT_odgovor():
    pad, _ = _pretrazi("MERIDIJAN", greske={"klijenti": KVAROVI["42501_rls"]})
    prazno, _ = _pretrazi("NEMA NIKOGA")
    assert pad.get("nepotpuno") == ["klijenti"]
    assert "nepotpuno" not in prazno
    assert pad != prazno
