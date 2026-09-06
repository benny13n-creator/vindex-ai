# -*- coding: utf-8 -*-
"""
Z017.15 — SABLONI DOKUMENATA (D4).

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. NEPOPUNJENO POLJE NE NESTAJE — ULAZI U DOKUMENT KAO VIDLJIVA RUPA.
     Backend na mesto praznog polja upisuje „[POLJE — NIJE UNETO]" i taj
     tekst ostaje U DOKUMENTU. To je namerno (bolje rupa nego izmisljen
     podatak), ali advokat mora znati koja polja nedostaju PRE nego sto
     potrosi naplativ poziv. `test_nepopunjena_imenuje_polja`.

  2. NATPIS NIJE PODATAK.
     Kljucevi sa servera su ASCII imena promenljivih (`cinjenice`). Prevod u
     „Činjenice" je ISKLJUCIVO natpis — nijedan podatak se ne menja niti
     dodaje. Nepoznat kljuc pada na opste pravilo, ne na prazan natpis.
     `test_poznat_kljuc_dobija_srpski_natpis`, `test_nepoznat_kljuc_ne_nestaje`.

  3. SABLON BEZ `id` SE NE MOZE NARUCITI.
     Prazna stavka u spisku je kontrola koja pada tek posle klika.
     `test_sablon_bez_id_se_izostavlja`.

  4. CUVANJE TRAZI PREDMET.
     Dokument bez predmeta nema gde da se sacuva; server bi vratio 422.
     `test_cuvanje_trazi_predmet`.

  5. DATUM I IZNOS SE PREPOZNAJU IZ KLJUCA.
     Obrazac tada nudi biranje datuma umesto slobodnog teksta — advokat ne
     kuca „12/3/26" u polje koje ocekuje drugaciji oblik.
     `test_datum_i_iznos_se_prepoznaju`.
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
        import * as S from "file:///{V2}/domain/sabloni.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


SABLON = {
    "id": "tuzba-opstinska", "naziv": "Tužba — Opštinski sud", "tip": "tuzba",
    "opis": "Tužba za novčano potraživanje",
    "polja": ["ime_tuzitelja", "adresa_tuzenog", "cinjenice",
              "vrednost_spora_rsd", "datum"],
}


# ── 1. Rupe ──────────────────────────────────────────────────────────────────
@nodemark
def test_nepopunjena_imenuje_polja():
    r = _js(f"return S.nepopunjena({_j(SABLON)}, "
            '{ ime_tuzitelja: "Petar" });')
    assert "Ime tužioca" not in r, r
    assert "Adresa tuženog" in r and "Činjenice" in r, r
    assert len(r) == 4, r


@nodemark
def test_popunjena_polja_nisu_rupe():
    v = {k: "x" for k in SABLON["polja"]}
    assert _js(f"return S.nepopunjena({_j(SABLON)}, {_j(v)});") == []


@nodemark
def test_beline_ne_racunaju_kao_popunjeno():
    """Razmak u polju bi u dokumentu i dalje bio rupa."""
    r = _js(f"return S.nepopunjena({_j(SABLON)}, "
            '{ ime_tuzitelja: "   " });')
    assert "Ime tužioca" in r, r


@nodemark
def test_bez_sablona_nema_rupa():
    assert _js("return S.nepopunjena(null, {});") == []
    assert _js(f"return S.nepopunjena({_j(SABLON)}, null).length;") == 5


# ── 2. Natpisi ───────────────────────────────────────────────────────────────
@nodemark
def test_poznat_kljuc_dobija_srpski_natpis():
    assert _js('return S.nazivPolja("cinjenice");') == "Činjenice"
    assert _js('return S.nazivPolja("jmbg_vlastodavca");') == "JMBG vlastodavca"
    assert _js('return S.nazivPolja("vrednost_spora_rsd");') == "Vrednost spora (RSD)"


@nodemark
def test_nepoznat_kljuc_ne_nestaje():
    """Spisak natpisa ne mora biti potpun — nepoznat kljuc mora ostati citljiv."""
    assert _js('return S.nazivPolja("neko_novo_polje");') == "Neko novo polje"
    assert _js('return S.nazivPolja("x");') == "X"


@nodemark
def test_prazan_kljuc_daje_prazan_natpis():
    assert _js("return S.nazivPolja(null);") == ""
    assert _js('return S.nazivPolja("");') == ""


# ── 3. Katalog ───────────────────────────────────────────────────────────────
@nodemark
def test_sablon_se_prenosi_sa_poljima():
    r = _js(f"return S.uSablone({{ sabloni: [{_j(SABLON)}] }});")
    assert len(r) == 1
    assert r[0]["polja"] == SABLON["polja"]
    assert r[0]["naziv"] == SABLON["naziv"]


@nodemark
def test_sablon_bez_id_se_izostavlja():
    r = _js('return S.uSablone({ sabloni: ['
            '{ naziv: "Bez id" }, { id: "a" }, { id: "b", naziv: "B" }] });')
    assert [x["id"] for x in r] == ["b"], r


@nodemark
def test_neispravan_katalog_daje_prazno():
    assert _js("return S.uSablone(null);") == []
    assert _js('return S.uSablone({ sabloni: "ne-niz" });') == []


@nodemark
def test_polja_koja_nisu_niz_ne_ruse():
    r = _js('return S.uSablone({ sabloni: [{ id: "a", naziv: "A", polja: "x" }] });')
    assert r[0]["polja"] == []


# ── 4. Provere pre poziva ────────────────────────────────────────────────────
@nodemark
def test_generisanje_trazi_sablon():
    assert _js("return S.nedostaciGenerisanja({});") != []
    assert _js('return S.nedostaciGenerisanja({ sablonId: "a" });') == []


@nodemark
def test_cuvanje_trazi_predmet():
    g = _js('return S.nedostaciCuvanja({ naziv: "X", sadrzaj: "dovoljno dugacak tekst" });')
    assert g != []
    assert "predmet" in g[0].lower(), g


@nodemark
def test_cuvanje_trazi_naziv_i_sadrzaj():
    assert _js('return S.nedostaciCuvanja({ predmetId: "p", sadrzaj: "dugacak tekst" });') != []
    assert _js('return S.nedostaciCuvanja({ predmetId: "p", naziv: "X", sadrzaj: "kratko" });') != []
    assert _js('return S.nedostaciCuvanja({ predmetId: "p", naziv: "X", '
               'sadrzaj: "tekst duzi od deset znakova" });') == []


@nodemark
def test_predugacak_naziv_se_odbija():
    g = _js('return S.nedostaciCuvanja({ predmetId: "p", naziv: "x".repeat(201), '
            'sadrzaj: "tekst duzi od deset znakova" });')
    assert g != [], "naziv preko 200 bi server odbio"


# ── 5. Vrsta polja ───────────────────────────────────────────────────────────
@nodemark
def test_datum_i_iznos_se_prepoznaju():
    assert _js('return S.jeDatum("datum");') is True
    assert _js('return S.jeDatum("datum_presude");') is True
    assert _js('return S.jeDatum("ime_tuzitelja");') is False
    assert _js('return S.jeIznos("vrednost_spora_rsd");') is True
    assert _js('return S.jeIznos("iznos_rsd");') is True
    assert _js('return S.jeIznos("cinjenice");') is False
