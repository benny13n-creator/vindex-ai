# -*- coding: utf-8 -*-
"""
Z017.13 — FINANSIJE I TARIFE (F6/F7/F8).

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. TRI IZNOSA SE NIKAD NE SMEJU SPOJITI.
       nefakturisano — moj rad koji nije usao ni u jednu fakturu; klijent ga
                       NE duguje jer mu nije ni ispostavljen,
       neizmireno    — izdata faktura koja nije placena; OVO klijent duguje,
       nacrt         — faktura koja nije izdata; ni potrazivanje ni prihod.
     Jedan zbirni broj „dugovanja" bio bi tvrdnja da klijenti duguju novac
     koji nikada nije ni trazen. `test_tri_iznosa_su_odvojena_polja`.

  2. „—" SA SERVERA NIJE NAZIV PREDMETA.
     `/billing/dugovanja` stavlja „—" kad naziv nije procitan. Prikazati to
     kao naziv znacilo bi predmet koji se zove crta.
     `test_crta_nije_naziv_predmeta`.

  3. NEPROCITAN IZVOR SE IMENUJE.
     `nepotpuno` sa servera mora stici do ekrana; inace advokat gleda tacne
     iznose uz neimenovane predmete i ne zna zasto.
     `test_nepotpuno_stize_do_ekrana`.

  4. STOPA NAPLATE NAD NULOM NIJE MERENJE.
     „0% naplaceno" kad nista nije fakturisano nije lose poslovanje nego
     odsustvo posla. `test_stopa_nije_znacajna_bez_fakturisanog`.

  5. TRAKE SE MERE PREMA NAJVECEM STVARNOM MESECU.
     Bez toga bi mesec od 1.000 RSD izgledao kao pun mesec.
     `test_vrh_je_najveci_stvarni_mesec`.

  6. PROPISANI IZNOS I MOJ IZNOS SU DVA PODATKA (F8).
     `aks_iznos` propisuje Advokatska tarifa; `iznos_rsd` je ono sto se
     obracunava. Prikazati samo jedan znacilo bi da advokat ne zna da li
     gleda tarifu ili svoju staru izmenu. `test_aks_i_moj_iznos_su_odvojeni`.

  7. `is_custom` I `source` MORAJU BITI IZRICITI.
     Nepoznata vrednost se NE proglasava mojom odlukom — fail-closed.
     `test_nepoznat_izvor_satnice_nije_moj`, `test_nepoznat_is_custom_nije_moja`.
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


def _js(modul: str, telo: str):
    skripta = textwrap.dedent(f"""
        import * as M from "file:///{V2}/domain/{modul}.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _f(telo):
    return _js("finansije", telo)


def _t(telo):
    return _js("tarife", telo)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


STANJE = {
    "ukupno_stavke": 35000, "neobracunato": 25000, "fakturisano": 12000,
    "naplaceno": 5000, "neizmireno": 7000, "nacrt_iznos": 3000,
    "fakture_ukupno": 3, "fakture_placene": 1, "fakture_izdate": 1,
}


# ── 1. Tri iznosa ────────────────────────────────────────────────────────────
@nodemark
def test_tri_iznosa_su_odvojena_polja():
    r = _f(f"return M.uStanjeNaplate({_j(STANJE)});")
    assert r["nefakturisano"] != r["neizmireno"], r
    assert r["neizmireno"] != r["nacrt"], r
    assert len({r["nefakturisano"], r["neizmireno"], r["nacrt"], r["naplaceno"]}) == 4, r


@nodemark
def test_odsutan_iznos_nije_nula():
    """`Number(null)` je 0 — „ne znam" nije „nema duga"."""
    r = _f("return M.uStanjeNaplate({});")
    for k in ("nefakturisano", "neizmireno", "nacrt", "naplaceno"):
        assert r[k] != "0 RSD", (k, r[k])


@nodemark
def test_prazan_ulaz_ne_ruši_stanje():
    assert _f("return M.uStanjeNaplate(null).fakturaUkupno;") is None


# ── 2. „—" nije naziv ────────────────────────────────────────────────────────
@nodemark
def test_crta_nije_naziv_predmeta():
    r = _f('return M.uNefakturisano({ dugovanja: [{ predmet_id: "p1", '
           'predmet_naziv: "—", stavke: [], ukupno_rsd: 100 }] });')
    g = r["grupe"][0]
    assert g["naziv"] == "", g
    assert g["nazivPoznat"] is False


@nodemark
def test_pravi_naziv_je_poznat():
    r = _f('return M.uNefakturisano({ dugovanja: [{ predmet_id: "p1", '
           'predmet_naziv: "Radni spor", stavke: [], ukupno_rsd: 100 }] });')
    assert r["grupe"][0]["naziv"] == "Radni spor"
    assert r["grupe"][0]["nazivPoznat"] is True


# ── 3. Nepotpuno ─────────────────────────────────────────────────────────────
@nodemark
def test_nepotpuno_stize_do_ekrana():
    r = _f('return M.uNefakturisano({ dugovanja: [], nepotpuno: ["nazivi predmeta"] });')
    assert r["nepotpuno"] == ["nazivi predmeta"], r


@nodemark
def test_bez_nepotpunog_lista_je_prazna():
    r = _f("return M.uNefakturisano({ dugovanja: [] });")
    assert r["nepotpuno"] == []


@nodemark
def test_stavke_grupe_se_prenose():
    r = _f('return M.uNefakturisano({ dugovanja: [{ predmet_id: "p1", '
           'predmet_naziv: "X", ukupno_rsd: 25000, stavke: ['
           '{ id: "e1", opis: "Sastanak", iznos_rsd: 25000, datum: "2026-09-01" }] }],'
           ' ukupno_rsd: 25000, predmeta: 1, stavki: 1 });')
    assert r["predmeta"] == 1 and r["stavki"] == 1
    assert r["grupe"][0]["stavke"][0]["opis"] == "Sastanak"


@nodemark
def test_stavka_bez_opisa_dobija_citljiv_tekst():
    r = _f('return M.uNefakturisano({ dugovanja: [{ predmet_id: "p1", '
           'stavke: [{ id: "e1", iznos_rsd: 10 }] }] });')
    assert r["grupe"][0]["stavke"][0]["opis"] == "Bez opisa"


# ── 4. Stopa naplate ─────────────────────────────────────────────────────────
@nodemark
def test_stopa_nije_znacajna_bez_fakturisanog():
    """„0% naplaceno" nad nulom nije lose poslovanje nego odsustvo posla."""
    r = _f('return M.uGodisnji({ godina: 2026, ukupno_fakturisano: 0, '
           'stopa_naplate_pct: 0, po_mesecima: [] });')
    assert r["stopaZnacajna"] is False


@nodemark
def test_stopa_je_znacajna_kad_ima_fakturisanog():
    r = _f('return M.uGodisnji({ godina: 2026, ukupno_fakturisano: 12000, '
           'stopa_naplate_pct: 41.7, po_mesecima: [] });')
    assert r["stopaZnacajna"] is True
    assert r["stopa"] == 41.7


# ── 5. Vrh za trake ──────────────────────────────────────────────────────────
@nodemark
def test_vrh_je_najveci_stvarni_mesec():
    r = _f('return M.uGodisnji({ po_mesecima: ['
           '{ mesec: "2026-01", uneseno: 1000, naplaceno: 0, stavki: 1 },'
           '{ mesec: "2026-02", uneseno: 50000, naplaceno: 0, stavki: 4 }] });')
    assert r["vrh"] == 50000, r["vrh"]


@nodemark
def test_vrh_uzima_i_naplaceno():
    r = _f('return M.uGodisnji({ po_mesecima: ['
           '{ mesec: "2026-01", uneseno: 1000, naplaceno: 80000, stavki: 1 }] });')
    assert r["vrh"] == 80000


@nodemark
def test_prazna_godina_ne_ruši_vrh():
    r = _f("return M.uGodisnji(null);")
    assert r["vrh"] == 0 and r["meseci"] == []


# ── 6. AKS i moj iznos ───────────────────────────────────────────────────────
STAVKA = {"sifra": "T01", "naziv": "Tužba", "kategorija": "parnica",
          "bodovi": 12, "aks_iznos": 600, "iznos_rsd": 9999, "is_custom": True}


@nodemark
def test_aks_i_moj_iznos_su_odvojeni():
    r = _t(f"return M.uStavkuTarife({_j(STAVKA)});")
    assert r["iznos"] != r["aks"], r
    assert r["aksBroj"] == 600 and r["iznosBroj"] == 9999
    assert r["moja"] is True


@nodemark
def test_bez_izmene_oba_iznosa_postoje():
    r = _t(f"return M.uStavkuTarife({_j(dict(STAVKA, is_custom=False, iznos_rsd=600))});")
    assert r["moja"] is False
    assert r["aks"] == r["iznos"], "AKS iznos mora ostati prisutan i bez izmene"


@nodemark
def test_broj_mojih_izmena():
    r = _t('return M.uStavkeTarife({ stavke: ['
           f'{_j(STAVKA)}, {_j(dict(STAVKA, sifra="T02", is_custom=False))}] }});')
    assert r["mojih"] == 1
    assert len(r["svi"]) == 2


@nodemark
def test_stavka_bez_sifre_se_izostavlja():
    r = _t('return M.uStavkeTarife({ stavke: [{ naziv: "Bez sifre" }] });')
    assert r["svi"] == []


# ── 7. Izricito `is_custom` i `source` ───────────────────────────────────────
@nodemark
def test_nepoznat_is_custom_nije_moja():
    """Fail-closed: nepoznato se ne proglasava mojom odlukom."""
    for v in ("'true'", "1", "null", "undefined"):
        r = _t("return M.uStavkuTarife({ sifra: 'T01', naziv: 'X', "
               f"is_custom: {v} }}).moja;")
        assert r is False, v


@nodemark
def test_nepoznat_izvor_satnice_nije_moj():
    for v in ('""', "'default'", "null", "'nesto'"):
        r = _t(f"return M.uSatnicu({{ tarifa_po_satu: 7500, source: {v} }}).sopstvena;")
        assert r is False, v
    assert _t("return M.uSatnicu({ tarifa_po_satu: 9000, source: 'custom' })"
              ".sopstvena;") is True


@nodemark
def test_satnica_bez_iznosa_nije_nula():
    r = _t("return M.uSatnicu({ source: 'default' });")
    assert r["iznosBroj"] is None
    assert r["iznos"] != "0 RSD"


# ── 8. Provera iznosa pre poziva ─────────────────────────────────────────────
@nodemark
def test_nedostaci_iznosa():
    assert _t('return M.nedostaciIznosa("");') != []
    assert _t('return M.nedostaciIznosa("abc");') != []
    assert _t('return M.nedostaciIznosa("0");') != []
    assert _t('return M.nedostaciIznosa("-5");') != []
    assert _t('return M.nedostaciIznosa("2000000");') != []
    assert _t('return M.nedostaciIznosa("9999");') == []
    assert _t('return M.nedostaciIznosa("9 999");') == []
    assert _t('return M.nedostaciIznosa("1500,50");') == []


@nodemark
def test_naucna_notacija_i_hex_nisu_iznos():
    """`Number("1e5")` je 100000 i `Number("0x10")` je 16 — oboje su konacni
    brojevi, pa bi provera samo kroz `Number.isFinite` propustila iznos koji
    advokat nije uneo. Ovakav unos nastaje nalepljivanjem iz tabele."""
    for lose in ("1e5", "0x10", "+5", "5.", ".5", "1,2,3", "Infinity"):
        g = _t(f'return M.nedostaciIznosa({json.dumps(lose)});')
        assert g != [], f"{lose!r} je prosao kao ispravan iznos"
