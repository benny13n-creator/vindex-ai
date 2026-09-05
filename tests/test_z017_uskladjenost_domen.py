# -*- coding: utf-8 -*-
"""
Z017 — USKLAĐENOST (digitalna imovina), domen + kapija petog prostora.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. OGRADA JE STALNA, NE USLOVNA.
     Mereno na samim rutama: `POST /web3/*` vraca `{rezultat, modul,
     credits_remaining}` — bez `izvori`, bez `confidence`, bez
     `izvori_neuspeh`. To je merljiva razlika u odnosu na `/api/pitanje`.
     Posledica: poreklo zakljucka se NE MOZE prikazati, pa ograda ne sme da
     zavisi od sadrzaja odgovora. Da je uslovna, „dobar" nalaz bi izgledao
     jednako potkrepljen kao odgovor sa pet clanova zakona.
     `test_ograda_stoji_uz_svaki_nalaz`.

  2. PRAZAN REZULTAT NIJE NALAZ DA JE SVE USKLADJENO.
     `test_prazan_rezultat_je_oznacen_kao_prazan`.

  3. NEIZGRADJENO I NEMA-PRAVO SU DVE RAZLICITE ODLUKE.
     `vidljiviProstori` mora da razlikuje prostor koji ne postoji u ovoj
     verziji od prostora na koji nalog nema pravo — spajanje bi znacilo da
     se buduce pravo ne moze razlikovati od buduce funkcije.
     `test_kapija_i_izgradjenost_su_odvojene`.

  4. PROSTOR BEZ PRAVA SE NE PRIKAZUJE NI KAO ONEMOGUCEN.
     Nema „uskoro", nema sivog teksta. `test_bez_prava_prostor_ne_postoji`.
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


def _js(uvoz: str, telo: str):
    skripta = textwrap.dedent(f"""
        {uvoz}
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _u(telo):
    return _js(f'import * as U from "file:///{V2}/domain/uskladjenost.js";', telo)


def _s(telo):
    return _js(f'import * as S from "file:///{V2}/domain/spaces.js";', telo)


# ═══════════════════════════════════════════════════════════════════════════
# 1 + 2 — ograda i prazan nalaz
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
@pytest.mark.parametrize("odgovor", [
    '{ rezultat: "Aktivnost je usklađena sa ZDI." }',
    '{ rezultat: "Nalaz: postoje ozbiljni nedostaci." }',
    '{ rezultat: { tekst: "Detaljna analiza." }, modul: "compliance_check" }',
    '{ rezultat: "" }',
    "null",
])
def test_ograda_stoji_uz_svaki_nalaz(odgovor):
    """Bez izuzetka: sadrzaj nalaza ne sme da ukine ogradu."""
    n = _u(f"return U.uNalaz({odgovor});")
    assert n["ograda"]["naslov"].strip()
    assert "nije potkrepljen izvorima" in n["ograda"]["naslov"]


@nodemark
def test_ograda_kaze_da_se_ne_sme_koristiti_kao_regulatorno_misljenje():
    t = _u("return U.OGRADA.telo;")
    assert "regulatorno mišljenje" in t
    assert "nadzornom organu" in t


@nodemark
def test_prazan_rezultat_je_oznacen_kao_prazan():
    n = _u('return U.uNalaz({ rezultat: "" });')
    assert n["prazan"] is True
    assert n["telo"] == ""


@nodemark
def test_tekst_se_izvlaci_i_iz_objekta_i_iz_stringa():
    a = _u('return U.uNalaz({ rezultat: "Direktan tekst." }).telo;')
    b = _u('return U.uNalaz({ rezultat: { analiza: "Iz objekta." } }).telo;')
    assert a == "Direktan tekst."
    assert b == "Iz objekta."


# ═══════════════════════════════════════════════════════════════════════════
# Katalog analiza
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_svaka_analiza_ima_pitanje_a_ne_samo_naziv_modula():
    a = _u("return U.ANALIZE.map(x => ({ kljuc:x.kljuc, pitanje:x.pitanje, putanja:x.putanja, najmanje:x.najmanje }));")
    assert len(a) >= 5
    for x in a:
        assert x["pitanje"].endswith("?"), x
        assert x["putanja"].startswith("/web3/"), x
        assert isinstance(x["najmanje"], int) and x["najmanje"] > 0, x


@nodemark
def test_granice_odgovaraju_serverskim():
    """Prepisane doslovno iz routers/web3.py — 422 koji se moze izbeci nije informacija."""
    a = _u("return Object.fromEntries(U.ANALIZE.map(x => [x.putanja, x.najmanje]));")
    assert a["/web3/compliance"] == 30
    assert a["/web3/pretraga"] == 10
    assert a["/web3/whitepaper"] == 100


@nodemark
def test_nepoznat_kljuc_ne_vraca_nasumicnu_analizu():
    assert _u('return U.analizaPoKljucu("nepostojece");') is None
    assert _u('return U.analizaPoKljucu("").kljuc;' if False else 'return U.analizaPoKljucu("");') is None


# ═══════════════════════════════════════════════════════════════════════════
# 3 + 4 — kapija petog prostora
# ═══════════════════════════════════════════════════════════════════════════

SVI = '["danas","predmeti","znanje","kancelarija","uskladjenost"]'


@nodemark
def test_sa_pravom_prostor_postoji():
    k = _s(f"return S.vidljiviProstori({SVI}, () => true).map(p => p.kljuc);")
    assert k[-1] == "uskladjenost"
    assert len(k) == 5


@nodemark
def test_bez_prava_prostor_ne_postoji():
    """Ne kao onemogucen, ne kao „uskoro" — ne postoji."""
    k = _s(f'return S.vidljiviProstori({SVI}, (x) => x !== "uskladjenost").map(p => p.kljuc);')
    assert "uskladjenost" not in k
    assert len(k) == 4


@nodemark
def test_kapija_i_izgradjenost_su_odvojene():
    """
    Prostor koji NIJE izgradjen i prostor na koji nalog NEMA pravo daju isti
    ishod na ekranu, ali su dve razlicite odluke. Test cuva da se jedna ne
    moze zameniti drugom.
    """
    neizgradjen = _s('return S.vidljiviProstori(["danas","predmeti"], () => true).map(p => p.kljuc);')
    bez_prava = _s(f'return S.vidljiviProstori({SVI}, (x) => ["danas","predmeti"].includes(x)).map(p => p.kljuc);')
    assert neizgradjen == ["danas", "predmeti"]
    assert bez_prava == ["danas", "predmeti"]
    # Isti ishod, ali kroz razlicite ulaze — funkcija mora primati oba odvojeno.
    assert neizgradjen == bez_prava


@nodemark
def test_uskladjenost_je_poslednja_u_redosledu():
    k = _s("return S.PROSTORI.map(p => p.kljuc);")
    assert k == ["danas", "predmeti", "znanje", "kancelarija", "uskladjenost"], k
