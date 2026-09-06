# -*- coding: utf-8 -*-
"""
Vindex V2 — Wave 2 (Priority Stream + Context Rail), domenska kompozicija.

Pokriva ISKLJUČIVO novu, čistu (bez DOM-a, bez mreže) logiku dodatu u
v2/domain/danas.js za Danas Wave 2: `sazetakDana`, `uRadnuStavku`,
`komponujDanas`. Ne dira postojeće `sastavi()`/`sastaviKalendar()` testove
(v. test_z017_kalendar_domen.py) — ovi ostaju netaknuti.

Najvažniji nalaz koji se ovde dokazuje: `komponujDanas` NE mapira backend
bucket (kriticno/danas/za_pregled/predstojece/na_cekanju) 1:1 na UI sekciju
— sve se spaja u DVA korisnička toka (tier1/tier2), fiksnim redosledom, bez
izračunate "AI ocene" (Wave 2 §3/§8/§6 direktive).
"""
import json
import os
import shutil
import subprocess
import textwrap

import pytest

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2 = os.path.join(KOREN, "v2").replace("\\", "/")

node = shutil.which("node")
nodemark = pytest.mark.skipif(node is None, reason="node nije dostupan")


def _js(telo: str):
    skripta = textwrap.dedent(f"""
        import * as S from "file:///{V2}/domain/danas.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


# ── sazetakDana ─────────────────────────────────────────────────────────────

@nodemark
def test_sazetak_dana_nula():
    r = _js('return S.sazetakDana(0, null);')
    assert r == "Danas nema stavki koje zahtevaju hitnu pažnju."


@nodemark
def test_sazetak_dana_jednina():
    assert _js('return S.sazetakDana(1, null);') == "1 stavka traži pažnju danas."


@nodemark
def test_sazetak_dana_mala_mnozina():
    assert _js('return S.sazetakDana(3, null);') == "3 stavke traže pažnju danas."


@nodemark
def test_sazetak_dana_velika_mnozina():
    assert _js('return S.sazetakDana(7, null);') == "7 stavki traži pažnju danas."


@nodemark
def test_sazetak_dana_sa_rocistem():
    r = _js('return S.sazetakDana(2, "11:00");')
    assert r == "2 stavke traže pažnju danas. Ročište u 11:00."


@nodemark
def test_sazetak_dana_nikad_nula_bez_rocista_kad_ima_rociste():
    # Cak i kad nema kriticnih/danas stavki (0), rociste se i dalje javlja.
    r = _js('return S.sazetakDana(0, "09:30");')
    assert r == "Danas nema stavki koje zahtevaju hitnu pažnju. Ročište u 09:30."


# ── uRadnuStavku ────────────────────────────────────────────────────────────

@nodemark
def test_u_radnu_stavku_anchor_mapiranje():
    review = _js('return S.uRadnuStavku({vrsta:"review", naslov:"x", predmet_id:"p1"});')
    zadatak = _js('return S.uRadnuStavku({vrsta:"zadatak", naslov:"x", predmet_id:"p1"});')
    action = _js('return S.uRadnuStavku({vrsta:"case_action", naslov:"x", predmet_id:"p1"});')
    assert review["anchor"] == "spisi"
    assert zadatak["anchor"] == "rokovi"
    assert action["anchor"] is None


@nodemark
def test_u_radnu_stavku_hitno_samo_za_critical():
    kriticno = _js('return S.uRadnuStavku({vrsta:"case_action", naslov:"x", prioritet:"critical"});')
    obicno = _js('return S.uRadnuStavku({vrsta:"case_action", naslov:"x", prioritet:"medium"});')
    assert kriticno["hitno"] is True
    assert obicno["hitno"] is False


@nodemark
def test_u_radnu_stavku_bez_predmeta_nema_predmetid():
    r = _js('return S.uRadnuStavku({vrsta:"zadatak", naslov:"x"});')
    assert r["predmetId"] == ""


# ── komponujDanas ───────────────────────────────────────────────────────────

@nodemark
def test_komponuj_danas_prazan_dan_nema_stavki():
    r = _js('return S.komponujDanas({ pregled: null, workspace: null, workspaceGreska: false });')
    assert r["tier1"] == []
    assert r["tier2"] == []
    assert r["nedostupno"] is False


@nodemark
def test_komponuj_danas_bucket_ne_postaje_sekcija():
    """Kriticno + danas (workspace) + za_pregled + zaProveru (pregled) se SPAJAJU
    u JEDAN tier1 niz, fiksnim redosledom -- nijedan backend bucket ne izlazi
    kao sopstveno imenovano polje u rezultatu (Wave 2 §3/§8)."""
    pregled = _j({"grupe": [], "zaProveru": [
        {"klasa": "provera", "id": "z1", "vrsta": "predlog", "vrstaNaziv": "Predlog roka",
         "opis": "predlog", "predmetId": "p9", "predmet": "P9",
         "vreme": "", "razlika": 2, "grupa": None},
    ]})
    workspace = _j({
        "kriticno": [{"vrsta": "case_action", "id": "a1", "predmet_id": "p1", "naslov": "nedostaje punomoć", "prioritet": "critical", "rok": None}],
        "danas": [{"vrsta": "zadatak", "id": "t1", "predmet_id": "p2", "naslov": "pozvati klijenta", "prioritet": "medium", "rok": None}],
        "za_pregled": [{"vrsta": "review", "id": "r1", "predmet_id": "p3", "naslov": "Pregled potreban: ugovor.pdf", "prioritet": "high", "rok": None}],
        "predstojece": [], "na_cekanju": [], "zavrseno_nedavno": [],
        "provera_potpuna": True,
    })
    r = _js(f'return S.komponujDanas({{ pregled: {pregled}, workspace: {workspace}, workspaceGreska: false }});')
    assert [x["vrsta"] for x in r["tier1"]] == ["case_action", "zadatak", "review", "predlog"]
    assert "kriticno" not in r
    assert "za_pregled" not in r
    assert r["tier1"][0]["hitno"] is True


@nodemark
def test_komponuj_danas_rokovi_hitno_ide_pre_workspace_danas():
    """Propušteno/danas grupe iz `pregled` (postojeći rokovi/ročišta) prethode
    workspace-ovom `danas` bucket-u u tier1 -- fiksan, dokumentovan redosled."""
    pregled = _j({
        "grupe": [{"kljuc": "propusteno", "naziv": "Propušteno",
                   "stavke": [{"klasa": "obaveza", "id": "o1", "vrsta": "rok", "vrstaNaziv": "Rok",
                               "opis": "rok", "predmetId": "p1", "predmet": "P1", "vreme": "",
                               "razlika": -1, "grupa": "propusteno"}]}],
        "zaProveru": [],
    })
    workspace = _j({
        "kriticno": [], "za_pregled": [], "predstojece": [], "na_cekanju": [], "zavrseno_nedavno": [],
        "danas": [{"vrsta": "zadatak", "id": "t1", "predmet_id": "p2", "naslov": "x", "prioritet": "medium", "rok": None}],
        "provera_potpuna": True,
    })
    r = _js(f'return S.komponujDanas({{ pregled: {pregled}, workspace: {workspace}, workspaceGreska: false }});')
    assert [x.get("klasa") or x.get("vrsta") for x in r["tier1"]] == ["obaveza", "zadatak"]


@nodemark
def test_komponuj_danas_workspace_greska_daje_nedostupno():
    r = _js('return S.komponujDanas({ pregled: { grupe: [], zaProveru: [] }, workspace: null, workspaceGreska: true });')
    assert r["nedostupno"] is True


@nodemark
def test_komponuj_danas_provera_potpuna_false_daje_nedostupno():
    workspace = _j({"kriticno": [], "danas": [], "za_pregled": [], "predstojece": [], "na_cekanju": [],
                     "zavrseno_nedavno": [], "provera_potpuna": False})
    r = _js(f'return S.komponujDanas({{ pregled: {{ grupe: [], zaProveru: [] }}, workspace: {workspace}, workspaceGreska: false }});')
    assert r["nedostupno"] is True


@nodemark
def test_komponuj_danas_tier2_kalendarskih_ukupno():
    """Kalendarske (rok/rociste) stavke moraju biti PRVE u tier2 i njihov broj
    se vraca odvojeno -- view.js na tome računa da odluči da li "+N" sme da
    bude veza na Kalendar (Wave 2 §8: Kalendar ne vlasnistvuje zadatke)."""
    pregled = _j({
        "grupe": [{"kljuc": "sutra", "naziv": "Sutra",
                   "stavke": [{"klasa": "obaveza", "id": "o2", "vrsta": "rok", "vrstaNaziv": "Rok",
                               "opis": "rok2", "predmetId": "p1", "predmet": "P1", "vreme": "",
                               "razlika": 1, "grupa": "sutra"}]}],
        "zaProveru": [],
    })
    workspace = _j({"kriticno": [], "danas": [], "za_pregled": [],
                     "predstojece": [{"vrsta": "case_action", "id": "a2", "predmet_id": "p3",
                                      "naslov": "y", "prioritet": "medium", "rok": None}],
                     "na_cekanju": [], "zavrseno_nedavno": [], "provera_potpuna": True})
    r = _js(f'return S.komponujDanas({{ pregled: {pregled}, workspace: {workspace}, workspaceGreska: false }});')
    assert r["tier2KalendarskihUkupno"] == 1
    assert len(r["tier2"]) == 2
    assert r["tier2"][0]["klasa"] == "obaveza"
