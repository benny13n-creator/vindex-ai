# -*- coding: utf-8 -*-
"""
Z017.1 — SUDSKA PRAKSA (domen).

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. NEDOVRSEN CITAT SE ODSECA, NE POPUNJAVA.
     Backend salje `citat_format` sastavljen unapred; kada odluci nedostaje
     datum, dobija se „Ustavni sud, Уж-1/2021, od ." — mereno uzivo na 10 od
     10 prikazanih odluka. Rep se uklanja; datum se NIKAD ne dopunjuje.
     Izmisljen datum u citatu presude je najgora greska ovog ekrana.
     `test_nedovrsen_citat_se_odseca`.

  2. ODLUKA BEZ BROJA SE NE MOZE CITIRATI.
     Prikazuje se, ali se oznacava — advokat ne sme da je prepise u podnesak
     misleci da je potpuna. `test_odluka_bez_broja_nije_citljiva`.

  3. PRAZAN FILTER SE NE SALJE.
     Backend odbija prazan `matter`/`court` sa 400. Korisnik ne sme da dobije
     gresku koju nije napravio. `test_prazan_filter_se_ne_salje`.

  4. PRETRAGA BEZ IJEDNOG KRITERIJUMA NIJE PRETRAGA.
     Vratila bi korpus u proizvoljnom redosledu — to nije odgovor ni na sta.
     `test_bez_kriterijuma_se_ne_pretrazuje`.

  5. SKOR SE NE PRIKAZUJE.
     Kosinusna slicnost prema upitu ne govori nista o pravnoj vrednosti
     presude; broj pored citata bi se citao kao ocena.
     `test_skor_ne_izlazi_iz_domena`.
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
        import * as P from "file:///{V2}/domain/praksa.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
# 1 — citat
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_nedovrsen_citat_se_odseca():
    r = _js('return ["Ustavni sud Srbije, Уж-16492/2021, od .", '
            '"Vrhovni sud, Rev 1/2020, od 01.02.2020.", "Sud, br. 5, od", "  "]'
            '.map(c => P.ocistiCitat(c));')
    assert r[0] == "Ustavni sud Srbije, Уж-16492/2021"
    assert r[1] == "Vrhovni sud, Rev 1/2020, od 01.02.2020.", "pun citat se NE dira"
    assert r[2] == "Sud, br. 5"
    assert r[3] == ""


@nodemark
def test_datum_se_nikad_ne_izmislja():
    o = _js('return P.uOdluku({ decision_number:"Уж-1/2021", court:"Ustavni sud", '
            'citat_format:"Ustavni sud, Уж-1/2021, od ." });')
    assert o["citat"] == "Ustavni sud, Уж-1/2021"
    assert o["datum"] == ""
    # Nijedna cifra godine se ne sme pojaviti iz vazduha.
    assert "202" not in o["citat"].split("Уж-1/2021")[-1]


@nodemark
def test_citat_se_sastavlja_kad_ga_server_ne_posalje():
    o = _js('return P.uOdluku({ decision_number:"Rev 1", court:"Vrhovni sud", '
            'decision_date:"2020-02-01" });')
    assert o["citat"] == "Vrhovni sud, Rev 1, od 01.02.2020."


@nodemark
def test_citat_sadrzi_samo_delove_koji_postoje():
    o = _js('return P.uOdluku({ decision_number:"Rev 1" });')
    assert o["citat"] == "Rev 1"
    assert "nepoznat" not in o["citat"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# 2 — citljivost
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_odluka_bez_broja_nije_citljiva():
    assert _js('return P.uOdluku({ court:"Vrhovni sud" }).citljiva;') is False
    assert _js('return P.uOdluku({ decision_number:"Rev 1" }).citljiva;') is True


# ═══════════════════════════════════════════════════════════════════════════
# 3 + 4 — upit
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_prazan_filter_se_ne_salje():
    t = _js('return P.uUpit({ upit:"šteta", oblast:"", sud:"" });')
    assert "matter" not in t
    assert "court" not in t
    assert t["query"] == "šteta"


@nodemark
def test_nepoznata_oblast_se_ne_salje():
    """Backend prima tacno cetiri vrednosti; peta bi dala 400."""
    t = _js('return P.uUpit({ upit:"x", oblast:"Izmišljena" });')
    assert "matter" not in t


@nodemark
def test_poznata_oblast_prolazi():
    t = _js('return P.uUpit({ upit:"x", oblast:"Građanska" });')
    assert t["matter"] == "Građanska"


@nodemark
def test_bez_kriterijuma_se_ne_pretrazuje():
    g = _js('return P.nedostaciUpita({ upit:"   ", oblast:"" });')
    assert len(g) == 1


@nodemark
def test_sama_oblast_je_dovoljan_kriterijum():
    assert _js('return P.nedostaciUpita({ oblast:"Krivična" });') == []


@nodemark
def test_besmislena_godina_se_ne_salje():
    t = _js('return P.uUpit({ upit:"x", odGodine:"abc", doGodine:12 });')
    assert "year_from" not in t and "year_to" not in t


# ═══════════════════════════════════════════════════════════════════════════
# 5 — granice prikaza
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_skor_ne_izlazi_iz_domena():
    k = _js('return Object.keys(P.uOdluku({ decision_number:"Rev 1", score: 0.93 }));')
    assert "score" not in k
    assert not any("skor" in x.lower() for x in k), k


@nodemark
def test_prazan_rezultat_nije_greska():
    r = _js('return P.uRezultat({ decisions: [], total: 0 });')
    assert r["odluke"] == []
    assert r["ukupno"] == 0


@nodemark
def test_odsutan_odgovor_ne_rusi_domen():
    r = _js("return P.uRezultat(null);")
    assert r["odluke"] == [] and r["ukupno"] == 0


@nodemark
def test_ukupno_prezivljava_stranicenje():
    r = _js('return P.uRezultat({ decisions:[{decision_number:"a"}], total: 251, page: 1, limit: 10 });')
    assert r["ukupno"] == 251
    assert len(r["odluke"]) == 1
