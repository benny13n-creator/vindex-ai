# -*- coding: utf-8 -*-
"""
Wave 11 — tenant izolacija na IZVORU, merena po BROJU IZVRŠENIH UPITA.

ŠTA JE OSTALO OTVORENO POSLE WAVE 7

`tests/test_wave7_ab_forensics.py::test_d_tudji_predmet_ne_curi_ni_delimicno`
dokazuje da tuđi atributi ne dospevaju u ODGOVOR. Njegov sopstveni docstring
priznaje šta ostaje: „`build_case_context` lansira svih 7 upita pre svoje
interne provere, pa tuđi redovi prođu kroz memoriju procesa."

To je bio tačan opis izmerenog stanja: od 7 upita u `_fetch_raw` samo je onaj
nad `predmeti` nosio `.eq("user_id", uid)`; ostalih 6 (`predmet_dokumenti`,
`predmet_dokazi`, `rocista`, `case_actions`, `predmet_hronologija`,
`predmet_komentari`) filtriralo je ISKLJUČIVO po `predmet_id`. Za tuđ
`predmet_id` tuđi nazivi fajlova, datumi ročišta i tekst komentara stvarno su
se dovlačili iz baze.

ZAŠTO SE MERI BROJ UPITA, A NE SADRŽAJ ODGOVORA

Tvrdnja o sadržaju odgovora prolazila bi i pre popravke — ugovor `:403`
(`{"error": "predmet_not_found"}`) već je sekao izlaz. Jedina tvrdnja koja
razlikuje popravljen od nepopravljenog koda jeste da se upit nad tuđim
podacima NE IZVRŠI. Zato lažna baza broji svaki `supa.table(...)` poziv, a
tvrdnje su nad tim brojačem.

LAŽNA BAZA

Ponovo se koristi `_Upit` iz `tests/test_wave7_ab_forensics.py` — jedini
lažnjak u repou koji STVARNO primenjuje svaki `.eq()` filter. `_FakeQuery` iz
`tests/test_tau002_case_context.py:38-47` eksplicitno no-op-uje sve osim `id`
(i sam to priznaje u docstring-u), pa bi sa njim svaka vlasnička tvrdnja
prolazila lažno.

POZITIVNA KONTROLA NIJE UKRAS

Bez `test_vlasnik_*` testova ispod, „nijedan upit se ne izvršava" prolazilo bi
i da su SVI upiti ugašeni. Zato se rezultat za vlasnika poredi sa zlatnim
otiskom snimljenim PRE izmene (`_ZLATNI_OTISAK_*`) — bajt-identičnost, ne
„izgleda razumno".
"""
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from unittest.mock import MagicMock  # noqa: E402

from test_wave7_ab_forensics import _Upit  # noqa: E402

from shared.case_context import build_case_context  # noqa: E402

# ─── Identiteti i markeri ───────────────────────────────────────────────────
ALFA_ID = "aaaaaaaa-0000-4000-8000-00000000000a"
BETA_ID = "bbbbbbbb-0000-4000-8000-00000000000b"
NEPOSTOJECI_ID = "cccccccc-0000-4000-8000-00000000000c"
UID_A = "11111111-0000-4000-8000-000000000001"
UID_B = "22222222-0000-4000-8000-000000000002"

BETA_DOK = "beta-otkaz.pdf"
BETA_KOMENTAR = "W11_BETA_KOMENTAR_TAJNA"

# Šest tabela koje su pre popravke bile filtrirane SAMO po `predmet_id`.
TABELE_SA_PODACIMA = (
    "predmet_dokumenti",
    "predmet_dokazi",
    "rocista",
    "case_actions",
    "predmet_hronologija",
    "predmet_komentari",
)


# ─── Lažna baza koja filtrira I broji ───────────────────────────────────────

def napravi_bazu():
    """Dva izolovana predmeta različitih vlasnika + brojač izvršenih upita.

    Datumi ročišta su namerno daleko u prošlosti/budućnosti: `proslo` iz
    `_label_past_vs_upcoming` i `kriticni_rokovi` iz `risk_engine`-a računaju
    se u odnosu na DANAS, pa bi bliski datumi učinili zlatni otisak
    nestabilnim od dana do dana.

    `case_actions` redovi NEMAJU `user_id` — to nije previd nego verna slika
    šeme (`migrations/099_case_actions.sql:14-48`; ni pisac
    `services/case_evolution.py:1037-1048` ne upisuje tu kolonu).
    """
    tabele = {
        "predmeti": [
            {"id": ALFA_ID, "user_id": UID_A, "naziv": "Spor Alfa",
             "tip_postupka": "privredni", "sud": "Privredni sud", "status": "aktivan",
             "stranka": "DOO Alfa", "protivnik": "DOO Kontra-Alfa", "klijent_id": "kl-a",
             "vrednost_spora": 4200000,
             "case_dna": {
                 "pravna_teorija": "Raskid ugovora zbog docnje u isporuci",
                 "snaga_predmeta_procent": 62,
                 "najslabija_tacka": "Usmeni dogovor o produženju roka nije dokumentovan",
                 "kontradikcije": [],
                 "_verifikacija": {"odluka": "PRIHVACENO"},
             }},
            {"id": BETA_ID, "user_id": UID_B, "naziv": "Spor Beta",
             "tip_postupka": "radni", "sud": "Osnovni sud", "status": "aktivan",
             "stranka": "DOO Beta", "protivnik": "DOO Kontra-Beta", "klijent_id": "kl-b",
             "vrednost_spora": 900000, "case_dna": None},
        ],
        "predmet_dokumenti": [
            {"id": "doc-a1", "predmet_id": ALFA_ID, "user_id": UID_A,
             "naziv_fajla": "alfa-ugovor.pdf", "redni_broj": 1, "tip_dokaza": "ugovor",
             "status": "spreman", "created_at": "2026-08-01T00:00:00Z",
             "tekst_sadrzaj": "Član 7 ugovora određuje rok isporuke od 30 dana."},
            {"id": "doc-a2", "predmet_id": ALFA_ID, "user_id": UID_A,
             "naziv_fajla": "alfa-opomena.pdf", "redni_broj": 2, "tip_dokaza": "dopis",
             "status": "spreman", "created_at": "2026-08-02T00:00:00Z",
             "tekst_sadrzaj": "Opomena pred tužbu upućena dana 2026-07-20."},
            {"id": "doc-b1", "predmet_id": BETA_ID, "user_id": UID_B,
             "naziv_fajla": BETA_DOK, "redni_broj": 1, "tip_dokaza": "resenje",
             "status": "spreman", "created_at": "2026-08-01T00:00:00Z",
             "tekst_sadrzaj": "Rešenje o otkazu ugovora o radu."},
        ],
        "predmet_dokazi": [
            {"id": "dz-a1", "predmet_id": ALFA_ID, "user_id": UID_A, "snaga": "jaka",
             "kategorija": "dokaz", "pravni_element": "docnja", "deleted_at": None},
            {"id": "dz-a2", "predmet_id": ALFA_ID, "user_id": UID_A, "snaga": "slaba",
             "kategorija": "svedok", "pravni_element": "usmeni dogovor", "deleted_at": None},
            {"id": "dz-b1", "predmet_id": BETA_ID, "user_id": UID_B, "snaga": "srednja",
             "kategorija": "dokaz", "pravni_element": "otkaz", "deleted_at": None},
        ],
        "rocista": [
            {"id": "ro-a1", "predmet_id": ALFA_ID, "user_id": UID_A, "sud": "Privredni sud",
             "datum": "2020-01-15", "status": "odrzano"},
            {"id": "ro-a2", "predmet_id": ALFA_ID, "user_id": UID_A, "sud": "Privredni sud",
             "datum": "2099-06-01", "status": "zakazano"},
            {"id": "ro-b1", "predmet_id": BETA_ID, "user_id": UID_B, "sud": "Osnovni sud",
             "datum": "2099-07-01", "status": "zakazano"},
        ],
        "case_actions": [
            {"id": "ca-a1", "predmet_id": ALFA_ID, "tip": "PRIBAVITI_DOKAZ",
             "razlog": "Nedostaje pisani trag o produženju roka", "dokaz": {},
             "prioritet": "high", "rok": "2099-05-01", "dedupe_key": "alfa-1",
             "status": "open"},
            {"id": "ca-b1", "predmet_id": BETA_ID, "tip": "PLANIRATI_ROKOVE",
             "razlog": "Rok za tužbu", "dokaz": {}, "prioritet": "critical",
             "rok": "2099-05-01", "dedupe_key": "beta-1", "status": "open"},
        ],
        "predmet_hronologija": [
            {"id": "hr-a1", "predmet_id": ALFA_ID, "user_id": UID_A,
             "dogadjaj": "Predmet otvoren", "datum_iso": "2026-07-01", "vaznost": "važan"},
            {"id": "hr-b1", "predmet_id": BETA_ID, "user_id": UID_B,
             "dogadjaj": "Otkaz uručen", "datum_iso": "2026-07-05", "vaznost": "kritičan"},
        ],
        "predmet_komentari": [
            {"id": "km-a1", "predmet_id": ALFA_ID, "user_id": UID_A,
             "tekst": "Proveriti isporuku", "created_at": "2026-08-03T00:00:00Z"},
            {"id": "km-b1", "predmet_id": BETA_ID, "user_id": UID_B,
             "tekst": BETA_KOMENTAR, "created_at": "2026-08-03T00:00:00Z"},
        ],
    }

    brojac: dict[str, int] = {}

    def _tabela(ime):
        brojac[ime] = brojac.get(ime, 0) + 1
        return _Upit(tabele.get(ime, []))

    supa = MagicMock()
    supa.table.side_effect = _tabela
    return supa, brojac


def normalizuj(o):
    """Sklanja jedina dva vremenski zavisna polja iz `context_field`/
    `audit_metadata` — sve ostalo mora biti identično od poziva do poziva."""
    if isinstance(o, dict):
        return {k: ("<TS>" if k in ("timestamp", "generated_at") else normalizuj(v))
                for k, v in o.items()}
    if isinstance(o, list):
        return [normalizuj(x) for x in o]
    return o


def otisak(rezultat: dict) -> str:
    return hashlib.sha256(
        json.dumps(normalizuj(rezultat), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# ─── Zlatni otisci ──────────────────────────────────────────────────────────
#
# Snimljeni pokretanjem `build_case_context(ALFA_ID, UID_A, ...)` nad OVOM
# istom lažnom bazom, sa NEIZMENJENIM `shared/case_context.py` (pre Wave 11
# zakrpe). Ako ijedan izvor ispadne iz konteksta, ili ijedno polje promeni
# oblik, otisak se razlikuje — zato je ovo istovremeno i dokaz nepromenjenog
# ponašanja i pozitivna kontrola nad samim testom.
#
# TASK 004A — otisci su PREBAZIRANI, tehnika i namera su NEPROMENJENE.
#
# Namena ovih testova je pozitivna kontrola nad testom izolacije („da nisu SVI
# upiti ugašeni"), a ne javni izlazni ugovor. Otisak je alat, ne tvrdnja.
#
# Fixture (`predmet_dokazi`, ~linija 125) nosi `snaga` bez `izvor_snage` --
# dakle po F4 ugovoru dve NEPROCENJENE tvrdnje. Provenance se NAMERNO ne
# dodaje: ovi testovi mere izolaciju, ne semantiku dokaza, pa im je legacy
# oblik reda verniji od izmišljene procene.
#
# Šta se promenilo u izlazu (posledica TASK-a 004, ne regresija):
#     snaga_dokaza   Jaka  -> Nije procenjeno       health_score  70 -> 30
#     snaga_pct        50  -> 0                     nivo       Nizak -> Visok
#     snaga_detalji  {j1,s0,sl1} -> {0,0,0}
#     + broj_tvrdnji=2, broj_procenjenih=0, pokrivenost=EVIDENCE_UNASSESSED
#     + problem „2 tvrdnji u spisu nije procenjeno"
#
# Zadržati stare otiske značilo bi zahtevati `Jaka`/50/70 za dva reda BEZ
# ijedne procene -- tačno grešku koju su gate-ovi 006-009 dokazali.
#
# Otisci pre TASK-a 004 (za reviziju):
#   sa dokumentima : ed4d7764a772d5775378d84da5608ee516c56e34295b26a984828cf418ee0730
#   bez dokumenata : 87ac0884f65400cf005f45b1bccb57516062f8c831e24e267cbdadbf51ad91f1
_ZLATNI_OTISAK_SA_DOKUMENTIMA = "2fde822dba3c6d10ea00347d131f5e7c8b7a3b8836243025d98c2f4f92740360"
_ZLATNI_OTISAK_BEZ_DOKUMENATA = "aa52b66cb8f4f527d316f27da409f3e6ab9f91b421aafe63a8478da903070389"


# ─── 1. SRŽ: tuđi upiti se NE IZVRŠAVAJU ────────────────────────────────────

@pytest.mark.asyncio
async def test_tudji_predmet_ne_izvrsava_nijedan_upit_nad_podacima():
    """Jedina tvrdnja koja razlikuje popravljen od nepopravljenog koda.

    Meri se BROJAČ izvršenih upita po tabeli, ne sadržaj odgovora — sadržaj je
    i pre popravke bio čist zahvaljujući `:403` ugovoru.
    """
    supa, brojac = napravi_bazu()
    await build_case_context(BETA_ID, UID_A, supa, include_documents=True)

    assert brojac.get("predmeti") == 1, "vlasnički upit se mora izvršiti tačno jednom"
    for tabela in TABELE_SA_PODACIMA:
        assert brojac.get(tabela, 0) == 0, (
            f"upit nad `{tabela}` je IZVRŠEN za tuđ predmet — redovi drugog "
            f"korisnika su prošli kroz memoriju procesa (brojač={brojac.get(tabela)})"
        )


@pytest.mark.asyncio
async def test_nepostojeci_predmet_takodje_ne_lansira_upite():
    """Isti zaključak, druga grana: nepostojeći ID ne sme platiti 7 upita."""
    supa, brojac = napravi_bazu()
    await build_case_context(NEPOSTOJECI_ID, UID_A, supa)
    assert brojac.get("predmeti") == 1
    assert sum(brojac.get(t, 0) for t in TABELE_SA_PODACIMA) == 0


@pytest.mark.asyncio
async def test_ugovor_za_tudji_predmet_je_nepromenjen():
    """Povratna vrednost mora ostati TAČNO ista kao pre zakrpe — zakrpa je o
    tome ŠTA se izvrši, ne o tome šta se vrati."""
    supa, _ = napravi_bazu()
    r = await build_case_context(BETA_ID, UID_A, supa)
    assert r["error"] == "predmet_not_found"
    assert r["predmet_id"] == BETA_ID
    assert "contract_version" in r
    # nijedan izvedeni ključ ne sme se pojaviti u error-odgovoru
    assert "case_identity" not in r and "relevant_documents" not in r
    # i nijedan tuđi atribut ne sme biti nigde u serijalizaciji
    tekst = json.dumps(r, ensure_ascii=False)
    for tajna in (BETA_DOK, BETA_KOMENTAR, "Osnovni sud", "DOO Beta"):
        assert tajna not in tekst, f"tuđi atribut procureo u odgovor: {tajna}"


# ─── 2. POZITIVNA KONTROLA: vlasnik dobija SVE, bajt-identično ─────────────

@pytest.mark.asyncio
async def test_vlasnik_dobija_bajt_identican_rezultat():
    """Bez ovoga bi test #1 prolazio i da su SVI upiti ugašeni.

    Poredi se sa otiskom snimljenim pre zakrpe nad istom lažnom bazom.
    """
    supa, _ = napravi_bazu()
    r = await build_case_context(ALFA_ID, UID_A, supa, include_documents=True)
    assert otisak(r) == _ZLATNI_OTISAK_SA_DOKUMENTIMA, (
        "rezultat za VLASNIKA se razlikuje od stanja pre Wave 11 zakrpe — "
        "izolacija ne sme promeniti ponašanje legitimnog vlasnika"
    )


@pytest.mark.asyncio
async def test_vlasnik_ima_sve_izvore_prisutne():
    """Čitljiva pozitivna kontrola pored otiska: svih 6 izvora podataka mora
    stvarno stići u kontekst (otisak bi pao i tiho, ovo kaže ŠTA je palo)."""
    supa, brojac = napravi_bazu()
    r = await build_case_context(ALFA_ID, UID_A, supa, include_documents=True)

    assert "error" not in r
    assert r["case_identity"]["value"]["naziv"] == "Spor Alfa"
    assert len(r["relevant_documents"]["value"]["included"]) == 2          # predmet_dokumenti
    assert r["relevant_documents"]["value"]["included"][0]["excerpt"]      # 2. faza fetch-a
    assert r["evidence_graph"]["value"]["ukupno_dokaza"] == 2              # predmet_dokazi
    assert len(r["deadlines"]["value"]) == 2                              # rocista
    assert len(r["active_actions"]["value"]) == 1                         # case_actions
    assert r["top_open_action"]["value"]["dedupe_key"] == "alfa-1"
    assert len(r["timeline"]["value"]) == 1                               # predmet_hronologija
    assert r["key_facts"]["value"]["snaga_predmeta_procent"] == 62         # case_dna

    # svih 6 tabela je STVARNO upitano (+1 za 2. fazu teksta dokumenata)
    assert brojac["predmeti"] == 1
    assert brojac["predmet_dokumenti"] == 2
    for tabela in ("predmet_dokazi", "rocista", "case_actions",
                   "predmet_hronologija", "predmet_komentari"):
        assert brojac[tabela] == 1, f"`{tabela}` nije upitana za vlasnika"


@pytest.mark.asyncio
async def test_vlasnik_ne_vidi_nista_od_drugog_predmeta():
    """A/B kontrola nad istom bazom — test koji bi prošao i da su predmeti
    zamenjeni nije test izolacije."""
    supa, _ = napravi_bazu()
    r = await build_case_context(ALFA_ID, UID_A, supa, include_documents=True)
    tekst = json.dumps(r, ensure_ascii=False)
    for tajna in (BETA_DOK, BETA_KOMENTAR, "Otkaz uručen", "beta-1", "DOO Beta"):
        assert tajna not in tekst, f"Betin podatak u Alfinom kontekstu: {tajna}"


# ─── 3. `include_documents=False` putanja ───────────────────────────────────

@pytest.mark.asyncio
async def test_lightweight_putanja_i_dalje_radi():
    """`morning_briefing.py`/`cio.py`/`case_commander.py` zovu ovu putanju u
    petlji preko svih predmeta — mora ostati i funkcionalna i jeftina."""
    supa, brojac = napravi_bazu()
    r = await build_case_context(ALFA_ID, UID_A, supa, include_documents=False)

    assert otisak(r) == _ZLATNI_OTISAK_BEZ_DOKUMENATA, (
        "lightweight putanja se razlikuje od stanja pre Wave 11 zakrpe"
    )
    assert r["relevant_documents"]["value"]["fetched_this_call"] is False
    assert r["relevant_documents"]["value"]["included"] == []
    assert r["readiness"]["value"]["status"]          # jeftina polja netaknuta
    assert len(r["deadlines"]["value"]) == 2
    assert brojac.get("predmet_dokumenti", 0) == 0, "lightweight putanja je ipak dohvatila dokumente"
    assert brojac["predmeti"] == 1


@pytest.mark.asyncio
async def test_lightweight_putanja_za_tudji_predmet_takodje_ne_lansira_upite():
    supa, brojac = napravi_bazu()
    r = await build_case_context(BETA_ID, UID_A, supa, include_documents=False)
    assert r["error"] == "predmet_not_found"
    assert sum(brojac.get(t, 0) for t in TABELE_SA_PODACIMA) == 0


# ─── 4. NEGATIVNE KONTROLE NAD SAMIM HARNESS-om ─────────────────────────────

def test_ng_lazna_baza_stvarno_primenjuje_user_id():
    """Ako `_Upit` ne bi filtrirao po `user_id`, ceo fajl bi lažno prolazio."""
    supa, _ = napravi_bazu()
    moj = supa.table("predmeti").select("*").eq("id", ALFA_ID).eq("user_id", UID_A).maybe_single().execute()
    tudji = supa.table("predmeti").select("*").eq("id", ALFA_ID).eq("user_id", UID_B).maybe_single().execute()
    assert moj.data is not None
    assert tudji.data is None, "lažna baza IGNORIŠE user_id — sve tvrdnje bi bile bezvredne"


def test_ng_brojac_stvarno_broji():
    """Ako brojač ne bi rastao, „nula upita" bi bila trivijalno tačna."""
    supa, brojac = napravi_bazu()
    supa.table("rocista")
    supa.table("rocista")
    supa.table("case_actions")
    assert brojac == {"rocista": 2, "case_actions": 1}


def test_ng_beta_podaci_stvarno_postoje_u_bazi():
    """Da tuđi redovi uopšte postoje — inače bi „nula tuđih upita" bila
    tačna iz pogrešnog razloga (prazna tabela)."""
    supa, _ = napravi_bazu()
    for tabela in TABELE_SA_PODACIMA:
        redovi = supa.table(tabela).select("*").eq("predmet_id", BETA_ID).execute().data
        assert redovi, f"fixture nema nijedan Betin red u `{tabela}`"
