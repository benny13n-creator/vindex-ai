# -*- coding: utf-8 -*-
"""
B2 — NEUSPEO PODUPIT NE SME POSTATI FINANSIJSKA TVRDNJA.

ŠTA JE BILO — mereno nad produkcionom šemom, ne pretpostavljeno

`routers/billing_reports.py` je svaki podupit vodio kroz
`asyncio.gather(..., return_exceptions=True)` pa `... else []`. Neuspeh je
postajao prazna lista, a prazna lista je postajala broj:

    ukupno_naplaceno_rsd: 0   ->  frontend ispisuje podebljano „0 RSD"
    po_klijentu: []           ->  frontend ispisuje „Nema faktura za ovaj period."

I to nije bio redak scenario — podupiti su padali UVEK, jer su imenovali kolone
kojih u šemi nema. Sonda produkcije (PostgREST OpenAPI koren, 2026-08-17):

    fakture          -> NEMA `iznos_rsd`  (iznosi: iznos_bez_pdv/pdv_iznos/iznos_sa_pdv)
    fakture          -> NEMA `klijent_id` (klijent je snimak `klijent_naziv`)
    billing_entries  -> NEMA `klijent_id`
    klijenti         -> kolona je `firma`, ne `naziv_firme`

Devet `select`-ova u fajlu je zbog toga vraćalo 42703 i ceo zahtev je padao.

ZAŠTO OVAJ FAJL IMA SOPSTVENI LAŽNI SUPABASE

`tests/test_billing_reports.py` postoji i ima 33 zelena testa — ali njegov mock
(`_make_supa`) **ignoriše argument `select()`** i vraća fiksne redove bez obzira
koje kolone su tražene. Takav mock ne može da reprodukuje 42703 ni u jednom
slučaju, pa je 33/33 bilo zeleno dok je proizvod u produkciji vraćao nule.

`_SemaSupa` ispod nosi STVARNE skupove kolona i diže 42703 za svaku nepoznatu —
isto što PostgREST radi. Bez toga ovi testovi ne bi merili ništa.

UGOVOR KOJI SE ZAKLJUČAVA

    izvor koji nosi BROJ padne     ->  HTTP 503, nikad 0
    izvor koji nosi OZNAKU padne   ->  200 + `nepotpuno` imenuje grupu
    svi izvori u redu              ->  tačan izveštaj, `nepotpuno` prazno
    veza koja u šemi ne postoji    ->  se ne izmišlja
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "admin@vindex.ai")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402
import api  # noqa: E402
import routers.billing_reports as br  # noqa: E402
from shared.deps import get_current_user  # noqa: E402

FAKE_USER = {"user_id": "uid-001", "email": "a@test.rs", "role": "pro"}

YEAR  = date.today().year
JAN15 = f"{YEAR}-01-15"
MAR10 = f"{YEAR}-03-10"
D90   = (date.today() - timedelta(days=90)).isoformat()
D15   = (date.today() - timedelta(days=15)).isoformat()

# ─── STVARNA PRODUKCIONA ŠEMA ────────────────────────────────────────────────
# Izmereno 2026-08-17 preko PostgREST OpenAPI korena. Ovo NIJE prepis koda —
# ovo je ono što baza kaže o sebi.
SEMA = {
    "fakture": {
        "id", "user_id", "predmet_id", "broj_fakture", "datum_fakture",
        "klijent_naziv", "klijent_adresa", "klijent_pib", "iznos_bez_pdv",
        "pdv_iznos", "iznos_sa_pdv", "status", "napomena", "created_at",
        "updated_at", "is_proforma", "datum_dospeca",
    },
    "billing_entries": {
        "id", "user_id", "predmet_id", "faktura_id", "opis", "tip",
        "tarifa_sifra", "tarifa_naziv", "bodovi", "sati", "iznos_rsd",
        "datum", "obracunato", "created_at", "updated_at",
    },
    "klijenti": {
        "id", "user_id", "ime", "prezime", "firma", "email", "telefon",
        "adresa", "napomena", "tip", "aktivan", "kreirano", "azurirano",
        "status", "deleted_at",
    },
    "predmeti": {
        "id", "user_id", "naziv", "opis", "tip", "status", "created_at",
        "updated_at", "tuzilac", "tuzeni", "rizik", "vrednost_spora",
        "kanban_faza", "case_dna", "broj_predmeta",
    },
    "rocista": {"id", "datum", "sud", "vreme", "predmet_id", "status", "user_id"},
    "predmet_hronologija": {
        "id", "predmet_id", "user_id", "dokument_naziv", "datum", "datum_iso",
        "dogadjaj", "akter", "vaznost", "created_at",
    },
}

# Redovi koji poštuju stvarnu šemu (nijedan izmišljen ključ).
REDOVI = {
    "billing_entries": [
        {"id": "e1", "datum": JAN15, "iznos_rsd": 7500.0,  "obracunato": True,
         "predmet_id": "p1", "tarifa_sifra": "T17", "tarifa_naziv": "Konsultacija",
         "opis": "Savetovanje", "sati": 1.0, "faktura_id": "f1"},
        {"id": "e2", "datum": MAR10, "iznos_rsd": 12000.0, "obracunato": False,
         "predmet_id": "p2", "tarifa_sifra": "T01", "tarifa_naziv": "Tužba",
         "opis": "Izrada tužbe", "sati": 0.0, "faktura_id": None},
    ],
    "fakture": [
        {"id": "f1", "iznos_sa_pdv": 9000.0,  "status": "placena", "datum_fakture": JAN15,
         "klijent_naziv": "Nikola Petrović"},
        {"id": "f2", "iznos_sa_pdv": 14400.0, "status": "izdata",  "datum_fakture": MAR10,
         "klijent_naziv": "Nikolić d.o.o."},
    ],
    "predmeti": [
        {"id": "p1", "naziv": "Tužba Petrović", "tip": "gradjansko", "status": "aktivan"},
        {"id": "p2", "naziv": "Spor Nikolić",   "tip": "radno",      "status": "aktivan"},
    ],
    "rocista": [],
    "predmet_hronologija": [],
    "klijenti": [],
}

AGED = [
    {"id": "a1", "datum": D90, "iznos_rsd": 5000.0, "opis": "Stara",  "predmet_id": "p1"},
    {"id": "a3", "datum": D15, "iznos_rsd": 3000.0, "opis": "Nova",   "predmet_id": "p1"},
]


class SemaGreska(RuntimeError):
    """42703 — isto što PostgREST vrati za nepostojeću kolonu."""


class _SemaSupa:
    """Lažni Supabase koji STVARNO primenjuje skup kolona.

    `select("x, y")` nad tabelom čija šema nema `y` diže 42703, tačno kao
    produkcija. `pada` je skup tabela koje treba da padnu bez obzira na kolone
    (simulacija ispada), da bi se merilo ponašanje na neuspehu.
    """

    def __init__(self, pada: set | None = None, aged: bool = False):
        self.pada = pada or set()
        self.aged = aged
        self.trazeno: list[tuple[str, str]] = []

    def table(self, ime):
        spolja = self

        class _Q:
            def __init__(self):
                self._tab = ime

            def select(self, kolone="*", *a, **k):
                spolja.trazeno.append((ime, kolone))
                if ime in spolja.pada:
                    raise RuntimeError(f"simuliran ispad izvora '{ime}'")
                dozvoljene = SEMA.get(ime)
                if dozvoljene is not None and kolone != "*":
                    for c in [x.strip() for x in kolone.split(",")]:
                        c = c.split("(")[0].strip()
                        if c and c not in dozvoljene:
                            raise SemaGreska(
                                f'42703: column {ime}.{c} does not exist')
                return self

            def eq(self, *a, **k):   return self
            def gte(self, *a, **k):  return self
            def lte(self, *a, **k):  return self
            def lt(self, *a, **k):   return self
            def order(self, *a, **k): return self

            def execute(self):
                if ime == "billing_entries" and spolja.aged:
                    return MagicMock(data=list(AGED))
                return MagicMock(data=list(REDOVI.get(ime, [])))

        return _Q()


def _klijent(pada=None, aged=False):
    supa = _SemaSupa(pada=pada, aged=aged)
    api.app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    return supa, TestClient(api.app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear():
    yield
    api.app.dependency_overrides.pop(get_current_user, None)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SVIH 9 DRIFT-TAČAKA — nijedan `select` ne sme imenovati nepostojeću kolonu
# ═══════════════════════════════════════════════════════════════════════════════

RUTE = [
    ("/billing/report/godisnji", {}),
    ("/billing/report/csv", {}),
    ("/billing/report/zastarele", {}),
    ("/billing/report/po-tipu", {}),
    ("/billing/report/po-klijentu", {}),
    ("/billing/report/mesecni", {}),
]


@pytest.mark.parametrize("ruta,_p", RUTE)
def test_1_nijedan_select_ne_gadja_nepostojecu_kolonu(ruta, _p):
    """Direktna zamena za svih 9 drift-tačaka: šema je sudija, ne kod."""
    supa, c = _klijent()
    with patch.object(br, "_get_supa", return_value=supa):
        r = c.get(ruta)

    assert supa.trazeno, f"{ruta} nije ni dodirnuo bazu — test ne bi merio ništa"
    for tab, kolone in supa.trazeno:
        for col in [x.strip().split("(")[0].strip() for x in kolone.split(",")]:
            if col and SEMA.get(tab) is not None:
                assert col in SEMA[tab], (
                    f"{ruta}: select nad `{tab}` imenuje `{col}` koje u šemi NE POSTOJI")
    assert r.status_code == 200, f"{ruta} -> {r.status_code}: {r.text[:200]}"


def test_1b_stare_drift_kolone_vise_ne_postoje_u_fajlu():
    """Regresiona brava nad izvorom: tačno tri para koji su padali."""
    izvor = open(os.path.join(os.path.dirname(__file__), "..", "routers",
                              "billing_reports.py"), encoding="utf-8").read()
    selectovi = []
    import re
    for m in re.finditer(r'\.table\(\s*"([a-z_0-9]+)"\s*\)\s*\n?\s*\.select\(\s*"([^"]*)"',
                         izvor, re.S):
        selectovi.append((m.group(1), m.group(2)))
    assert selectovi, "nijedan select nije pronađen — regex je zastareo"

    for tab, kolone in selectovi:
        cols = {x.strip() for x in kolone.split(",")}
        if tab == "fakture":
            assert "iznos_rsd" not in cols,  "fakture.iznos_rsd ne postoji u šemi"
            assert "klijent_id" not in cols, "fakture.klijent_id ne postoji u šemi"
        if tab == "billing_entries":
            assert "klijent_id" not in cols, "billing_entries.klijent_id ne postoji u šemi"
        if tab == "klijenti":
            assert "naziv_firme" not in cols, "klijenti.naziv_firme ne postoji (kolona je `firma`)"


# ═══════════════════════════════════════════════════════════════════════════════
# 2-5. NEUSPEH IZVORA KOJI NOSI BROJ  ->  NIKAD NULA
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ruta,pada", [
    ("/billing/report/godisnji",    {"billing_entries"}),
    ("/billing/report/godisnji",    {"fakture"}),
    ("/billing/report/godisnji",    {"billing_entries", "fakture"}),
    ("/billing/report/zastarele",   {"billing_entries"}),
    ("/billing/report/po-tipu",     {"billing_entries"}),
    ("/billing/report/po-klijentu", {"fakture"}),
    ("/billing/report/mesecni",     {"billing_entries"}),
    ("/billing/report/mesecni",     {"fakture"}),
    ("/billing/report/csv",         {"billing_entries"}),
])
def test_2_pao_izvor_broja_daje_503_a_ne_nulu(ruta, pada):
    supa, c = _klijent(pada=pada)
    with patch.object(br, "_get_supa", return_value=supa):
        r = c.get(ruta)

    assert r.status_code == 503, (
        f"{ruta} sa palim izvorom {pada} vratio {r.status_code} — "
        f"telo: {r.text[:200]}")
    telo = r.text
    assert "nije izračunat" in telo or "nije izracunat" in telo


@pytest.mark.parametrize("ruta,polje", [
    ("/billing/report/godisnji",  "ukupno_naplaceno_rsd"),
    ("/billing/report/godisnji",  "ukupno_uneseno_rsd"),
    ("/billing/report/po-tipu",   "ukupno_rsd"),
    ("/billing/report/zastarele", "ukupno_nenaplaceno_rsd"),
    ("/billing/report/mesecni",   "naplaceno_rsd"),
])
def test_3_pao_izvor_nikad_ne_proizvodi_polje_sa_nulom(ruta, polje):
    """Ključna invarijanta B2: ne sme postojati 200 sa nulom iz pale pretrage."""
    supa, c = _klijent(pada={"billing_entries", "fakture"})
    with patch.object(br, "_get_supa", return_value=supa):
        r = c.get(ruta)

    assert r.status_code != 200, f"{ruta} vratio 200 uprkos palom izvoru"
    try:
        telo = r.json()
    except Exception:
        return
    assert polje not in telo, (
        f"{ruta}: polje `{polje}` je isporučeno iz pale pretrage -> {telo}")


def test_4_pao_izvor_ne_daje_lazno_nema_faktura():
    """`po_klijentu: []` frontend ispisuje kao „Nema faktura za ovaj period."."""
    supa, c = _klijent(pada={"fakture"})
    with patch.object(br, "_get_supa", return_value=supa):
        r = c.get("/billing/report/po-klijentu")

    assert r.status_code == 503
    assert "po_klijentu" not in r.text


def test_5_prazna_baza_i_dalje_daje_posten_nula_rezultat():
    """Prazno NIJE greška: bez faktura izveštaj je validan i vraća 0."""
    supa, c = _klijent()
    prazno = {k: [] for k in REDOVI}
    with patch.dict(br.__dict__, {}, clear=False), \
         patch.object(br, "_get_supa", return_value=supa), \
         patch.dict(REDOVI, prazno, clear=False):
        r = c.get("/billing/report/godisnji")

    assert r.status_code == 200
    d = r.json()
    assert d["ukupno_naplaceno_rsd"] == 0
    assert d["nepotpuno"] == [], "prazna baza nije nepotpun izveštaj"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. IZVOR KOJI NOSI OZNAKU  ->  200 + `nepotpuno`, nikad tiho
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ruta", [
    "/billing/report/godisnji",
    "/billing/report/po-tipu",
])
def test_6_pao_dopunski_izvor_se_imenuje(ruta):
    supa, c = _klijent(pada={"predmeti"})
    with patch.object(br, "_get_supa", return_value=supa):
        r = c.get(ruta)

    assert r.status_code == 200, f"{ruta} -> {r.status_code}"
    d = r.json()
    assert d["nepotpuno"], "pao dopunski izvor nije imenovan — tiha degradacija"
    assert "tipovi predmeta" in d["nepotpuno"]


def test_6b_uspesan_izveštaj_ima_prazno_nepotpuno():
    supa, c = _klijent()
    with patch.object(br, "_get_supa", return_value=supa):
        d = c.get("/billing/report/godisnji").json()
    assert d["nepotpuno"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 7. „PO KLIJENTU" NE KORISTI NEPOSTOJEĆU VEZU
# ═══════════════════════════════════════════════════════════════════════════════

def test_7_po_klijentu_grupise_po_nazivu_sa_fakture():
    supa, c = _klijent()
    with patch.object(br, "_get_supa", return_value=supa):
        r = c.get("/billing/report/po-klijentu")

    assert r.status_code == 200
    d = r.json()
    nazivi = {k["naziv"] for k in d["po_klijentu"]}
    assert nazivi == {"Nikola Petrović", "Nikolić d.o.o."}, d["po_klijentu"]
    # Iznosi su iznos_sa_pdv — jedan osnov kroz ceo izveštaj.
    assert d["ukupno_rsd"] == 23400.0
    for k in d["po_klijentu"]:
        assert "klijent_id" not in k, (
            "vraćen `klijent_id` — faktura nema vezu ka `klijenti`, "
            "polje bi tvrdilo vezu koje nema")


def test_7b_po_klijentu_ne_dodiruje_tabelu_klijenti_ni_predmet_klijenti():
    """Dokaz da veza nije izmišljena: te tabele se ne čitaju."""
    supa, c = _klijent()
    with patch.object(br, "_get_supa", return_value=supa):
        c.get("/billing/report/po-klijentu")

    dodirnute = {t for t, _ in supa.trazeno}
    assert "klijenti" not in dodirnute
    assert "predmet_klijenti" not in dodirnute


def test_7c_faktura_bez_naziva_klijenta_ide_u_bez_klijenta():
    supa, c = _klijent()
    bez = [{"id": "f9", "iznos_sa_pdv": 1000.0, "status": "izdata",
            "datum_fakture": JAN15, "klijent_naziv": None}]
    with patch.object(br, "_get_supa", return_value=supa), \
         patch.dict(REDOVI, {"fakture": bez}, clear=False):
        d = c.get("/billing/report/po-klijentu").json()

    assert d["po_klijentu"] == []
    assert d["bez_klijenta"] == 1000.0


def test_7d_top_duznici_je_oznacen_kao_nedostupan_a_ne_prazan():
    """`billing_entries` nema vezu ka klijentu — prazno mora biti IMENOVANO."""
    supa, c = _klijent(aged=True)
    with patch.object(br, "_get_supa", return_value=supa):
        d = c.get("/billing/report/zastarele").json()

    assert d["top_duznici"] == []
    assert d["top_duznici_dostupno"] is False, (
        "prazna lista bez oznake izgleda kao odsustvo dužnika")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. HAPPY PATH — izveštaji i dalje računaju tačno
# ═══════════════════════════════════════════════════════════════════════════════

def test_8_godisnji_racuna_tacno():
    supa, c = _klijent()
    with patch.object(br, "_get_supa", return_value=supa):
        d = c.get("/billing/report/godisnji").json()

    assert d["ukupno_uneseno_rsd"]   == 19500.0     # 7500 + 12000
    assert d["ukupno_naplaceno_rsd"] == 9000.0      # samo `placena`
    assert d["ukupno_fakturisano"]   == 23400.0
    assert d["stopa_naplate_pct"]    == round(9000 / 23400 * 100, 1)
    assert {k["naziv"] for k in d["top_klijenti"]} == {"Nikola Petrović", "Nikolić d.o.o."}
    assert {t["tip"] for t in d["top_tipovi_predmeta"]} == {"gradjansko", "radno"}


def test_8b_csv_export_i_dalje_radi():
    supa, c = _klijent()
    with patch.object(br, "_get_supa", return_value=supa):
        r = c.get("/billing/report/csv")

    assert r.status_code == 200
    telo = r.content.decode("utf-8-sig")
    assert "Datum;Predmet;Klijent" in telo
    assert "Tužba Petrović" in telo
    assert "7500.0" in telo


def test_8c_mesecni_racuna_tacno():
    """Napomena o obimu: `_SemaSupa` NE primenjuje `.gte/.lte` filtere — to radi
    baza. Ovde se zato meri SUMIRANJE i izbor po statusu, ne filtriranje po
    periodu. Očekivanje je pun skup redova, ne mesečni podskup."""
    supa, c = _klijent()
    with patch.object(br, "_get_supa", return_value=supa):
        d = c.get("/billing/report/mesecni?mesec=%d-01" % YEAR).json()

    assert d["fakturisano_rsd"] == 19500.0   # 7500 + 12000
    assert d["naplaceno_rsd"]   == 9000.0    # samo faktura sa `placena`
    assert d["neplaceno_rsd"]   == 10500.0
    assert d["aktivnih_predmeta"] == 2


def test_8d_zastarele_racuna_tacno():
    supa, c = _klijent(aged=True)
    with patch.object(br, "_get_supa", return_value=supa):
        d = c.get("/billing/report/zastarele").json()

    assert d["ukupno_nenaplaceno_rsd"] == 8000.0
    # D90 je TAČNO 90 dana star, a granica u kodu je `elif dana <= 90` —
    # dakle korpa `61_90_dana`, ne `starije_90`. Testira se zatečena granica,
    # ne poželjna.
    assert d["aging"]["61_90_dana"]["iznos"] == 5000.0
    assert d["aging"]["starije_90"]["iznos"] == 0.0
    assert d["aging"]["do_30_dana"]["iznos"] == 3000.0
