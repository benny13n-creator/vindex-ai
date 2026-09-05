# -*- coding: utf-8 -*-
"""
Z017.1 — NAPLATA (domen): evidentiran rad, tajmer, fakture.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. TRI IZNOSA SE NIKAD NE SABIRAJU (B2, `6bf80708`).
     `uneseno` / `obracunato` / `neobracunato` su tri razlicite cinjenice.
     Mesecni izvestaj je nekad sabirao NEOBRACUNAT rad kao `fakturisano_rsd`,
     pa je kancelarija verovala da je izdala racune koje nije.
     `test_tri_iznosa_su_odvojena`.

  2. FAKTURA SE PRAVI SAMO OD NEOBRACUNATOG RADA.
     Ponuditi vec fakturisan unos znacilo bi ponuditi dvostruko naplacivanje
     istog posla klijentu. `test_fakturisan_unos_ne_ulazi_u_novu_fakturu`.

  3. NEPOZNATO STANJE TAJMERA NIJE „NE RADI".
     Ako poziv padne, ekran NE sme da ponudi „Pokreni" — pokretanje drugog
     tajmera preko postojeceg izgubilo bi prvo merenje.
     `test_nepoznat_tajmer_nije_zaustavljen`.

  4. ODSUTAN IZNOS NIJE NULA.
     `Number(null)` je 0; iznos koji backend nije poslao ne sme se prikazati
     kao „0 RSD". `test_odsutan_iznos_nije_nula`.

  5. SAMO „PLACENA" ZNACI DA JE NOVAC STIGAO.
     Sve ostalo je i dalje potrazivanje. `test_samo_placena_je_naplacena`.
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
        import * as N from "file:///{V2}/domain/naplata.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


UNOSI = {
    "entries": [
        {"id": "e1", "opis": "Sastav tužbe", "iznos_rsd": 24000, "obracunato": False,
         "datum": "2026-09-01"},
        {"id": "e2", "opis": "Ročište", "iznos_rsd": 12000, "obracunato": True,
         "datum": "2026-09-02"},
    ],
    "ukupno_rsd": 36000, "obracunato_rsd": 12000, "neobracunato_rsd": 24000,
    "ukupno_h": 3.5,
}


# ═══════════════════════════════════════════════════════════════════════════
# 1 + 2 — iznosi i faktura
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_tri_iznosa_su_odvojena():
    u = _js(f"return N.uUnose({_j(UNOSI)});")
    assert u["ukupno"] == "36.000 RSD"
    assert u["obracunato"] == "12.000 RSD"
    assert u["neobracunato"] == "24.000 RSD"
    # Nijedan od tri nije zbir druga dva prikazan kao jedan broj.
    assert len({u["ukupno"], u["obracunato"], u["neobracunato"]}) == 3


@nodemark
def test_fakturisan_unos_ne_ulazi_u_novu_fakturu():
    z = _js(f"return N.uUnose({_j(UNOSI)}).zaFakturu.map(x => x.id);")
    assert z == ["e1"], z


@nodemark
def test_unos_bez_iznosa_ne_ulazi_u_fakturu():
    """Stavka bez iznosa ne moze biti stavka racuna."""
    z = _js('return N.uUnose({ entries: [{id:"a", opis:"x", obracunato:false},'
            '{id:"b", opis:"y", iznos_rsd:0, obracunato:false},'
            '{id:"c", opis:"z", iznos_rsd:100, obracunato:false}] }).zaFakturu.map(x=>x.id);')
    assert z == ["c"], z


@nodemark
def test_obracunato_je_izricito_polje():
    """Odsutno `obracunato` znaci NIJE obracunato — ali se cita, ne pogadja."""
    r = _js('return [N.uUnos({obracunato:true}).obracunato, N.uUnos({}).obracunato];')
    assert r == [True, False]


# ═══════════════════════════════════════════════════════════════════════════
# 3 — tajmer
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_nepoznat_tajmer_nije_zaustavljen():
    t = _js("return N.uTajmer(null);")
    assert t["poznato"] is False
    assert t["radi"] is False


@nodemark
def test_aktivan_tajmer_nosi_predmet():
    t = _js('return N.uTajmer({ aktivan:true, timer:{ predmet_id:"p1", opis:"Rad" } });')
    assert t["poznato"] is True and t["radi"] is True
    assert t["predmetId"] == "p1"


@nodemark
def test_neaktivan_tajmer_je_poznato_stanje():
    t = _js('return N.uTajmer({ aktivan:false, timer:null });')
    assert t["poznato"] is True and t["radi"] is False


@nodemark
def test_aktivan_mora_biti_bas_true():
    for lazno in ("true", 1, "da"):
        t = _js(f"return N.uTajmer({{ aktivan: {_j(lazno)} }});")
        assert t["radi"] is False, lazno


@nodemark
def test_trajanje_se_cita_kao_vreme_a_ne_decimala():
    r = _js("return [N.trajanje(0), N.trajanje(90), N.trajanje(3600), N.trajanje(5430), N.trajanje(null)];")
    assert r[0] == "0 min"
    assert r[1] == "1 min"
    assert r[2] == "1 h"
    assert r[3] == "1 h 30 min"
    assert r[4] == ""


# ═══════════════════════════════════════════════════════════════════════════
# 4 + 5 — iznosi i fakture
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_odsutan_iznos_nije_nula():
    r = _js('return [N.dinar(null), N.dinar(undefined), N.dinar(""), N.dinar("abc"), N.dinar(0)];')
    assert r[:4] == [None, None, None, None]
    assert r[4] is not None and "0" in r[4]


@nodemark
def test_zbirovi_koje_server_nije_poslao_ne_postaju_nula():
    u = _js('return N.uUnose({ entries: [] });')
    assert u["ukupno"] is None
    assert u["neobracunato"] is None


@nodemark
def test_samo_placena_je_naplacena():
    r = _js('return ["placena","poslata","nacrt","storno"].map(s => N.uFakturu({status:s}).placena);')
    assert r == [True, False, False, False]


@nodemark
def test_faktura_bez_broja_ne_ostaje_prazna():
    f = _js('return N.uFakturu({ klijent_naziv:"X" }).broj;')
    assert f.strip() != ""


@nodemark
def test_prazan_odgovor_ne_rusi_domen():
    assert _js("return N.uFakture(null);") == []
    assert _js("return N.uUnose(null).svi;") == []


# ═══════════════════════════════════════════════════════════════════════════
# Unos rada — granice
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_nedostaci_unosa_imenuju_svaki_problem():
    g = _js('return N.nedostaciUnosa({ predmetId:"", opis:"", iznos:"" });')
    assert len(g) == 3


@nodemark
def test_ispravan_unos_nema_nedostataka():
    g = _js('return N.nedostaciUnosa({ predmetId:"p1", opis:"Rad", iznos:"24.000,00" });')
    assert g == []


@nodemark
def test_iznos_se_cita_i_sa_tackama_i_sa_zarezom():
    t = _js('return N.uTeloUnosa({ predmetId:"p1", opis:"Rad", iznos:"24.000,50" });')
    assert t["iznos_rsd"] == 24000.5


@nodemark
def test_nula_i_negativan_iznos_se_odbijaju():
    assert len(_js('return N.nedostaciUnosa({ predmetId:"p", opis:"x", iznos:"0" });')) == 1
    assert len(_js('return N.nedostaciUnosa({ predmetId:"p", opis:"x", iznos:"-5" });')) == 1
