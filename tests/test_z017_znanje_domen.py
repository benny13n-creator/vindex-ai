# -*- coding: utf-8 -*-
"""
Z017 — ZNANJE (pravno istrazivanje), domen.

Ovo je ekran sa najvecim pravnim rizikom u proizvodu: jedino mesto gde tekst
koji je proizveo model moze biti procitan kao tvrdnja o zakonu. Zato ovi
testovi cuvaju tacno one razlike koje se iz koda ne vide:

  1. TRI STANJA SE NIKAD NE SPAJAJU (B-U-003).
     `retrieval_unavailable` (upit nad korpusom PAO), `izvori_neuspeh`
     (deo izvora NIJE proveren) i prazni `izvori` bez ijednog pada
     (provereno, nema pogotka) vode u TRI razlicite recenice. Spajanje bilo
     koja dva znaci da pad pretrage izgleda kao dokazano odsustvo propisa —
     kvar koji je ovaj proizvod vec jednom platio.

  2. PRAZNA LISTA NIJE ODSUTNO POLJE.
     `izvori_neuspeh: []` znaci „provereno, sve je proslo"; odsutno polje
     znaci da backend o tome nista nije rekao. Ne smeju dati isto upozorenje.

  3. SIGURNOST JE REC, NE PROCENAT.
     `test_sigurnost_nikad_nije_broj`.

  4. STATUSNA POTVRDA SE IZVLACI IZ SREDINE ODGOVORA (N3/AUTH-001).
     Backend upisuje „[~] STATUSNA POTVRDA: … doslovan clan nije potvrdjen"
     u sredinu teksta, gde je advokat ne procita. Domen je izvlaci i
     oznacava kao NIJE doslovno — fail-closed na formulaciju poricanja.

  5. IZVOR SE NE UDVOSTRUCUJE.
     Baza vraca `clan: "Član 367"`; naivno spajanje daje „član Član 367".
     Mereno uzivo na produkciji pre popravke. `test_izvor_ne_duplira_clan`.
"""
import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2 = os.path.join(KOREN, "v2").replace("\\", "/")

node = shutil.which("node")
nodemark = pytest.mark.skipif(node is None, reason="node nije dostupan")


def _js(telo: str):
    skripta = textwrap.dedent(f"""
        import * as Z from "file:///{V2}/domain/znanje.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


def _kljucevi(odg):
    return _js(f"return Z.upozorenja({_j(odg)}).map(u => u.kljuc);")


DOBAR = {"odgovor": "Rok je 15 dana.", "confidence": "HIGH",
         "izvori": [{"zakon": "zakon o parnicnom postupku", "clan": "Član 367"}]}


# ═══════════════════════════════════════════════════════════════════════════
# 1 + 2 — tri stanja
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_pad_korpusa_daje_sopstvenu_ogradu():
    k = _kljucevi({"odgovor": "x", "retrieval_unavailable": True, "izvori": []})
    assert "korpus-pao" in k
    # Pad NIJE „nema propisa" — te dve poruke ne smeju stajati zajedno.
    assert "bez-pogotka" not in k


@nodemark
def test_pad_korpusa_kaze_da_odgovor_ne_pociva_na_propisima():
    t = _js('return Z.upozorenja({ retrieval_unavailable: true }).map(u => u.naslov + " " + u.telo).join(" ");')
    assert "ne znači da propis ne" in t or "ne znači da propis" in t
    assert "nije proveren" in t


@nodemark
def test_neproveren_izvor_se_imenuje():
    t = _js('return Z.upozorenja({ izvori_neuspeh: ["zakonski korpus"], izvori: [{zakon:"x"}] })[0];')
    assert t["kljuc"] == "izvor-nije-proveren"
    assert "zakonski korpus" in t["telo"]


@nodemark
def test_prazna_lista_neuspeha_nije_upozorenje():
    """`[]` znaci „provereno, sve je proslo" — ne sme dati istu ogradu kao pad."""
    k = _kljucevi({"odgovor": "x", "izvori_neuspeh": [], "izvori": [{"zakon": "ZPP"}]})
    assert k == []


@nodemark
def test_bez_pogotka_je_treca_recenica():
    k = _kljucevi({"odgovor": "x", "izvori": []})
    assert k == ["bez-pogotka"]
    t = _js('return Z.upozorenja({ izvori: [] })[0].telo;')
    assert "ne sme se citirati kao izvor prava" in t


@nodemark
def test_uredan_odgovor_nema_nijednu_ogradu():
    assert _kljucevi(DOBAR) == []


@nodemark
def test_pad_i_neproveren_izvor_daju_dve_ograde_redom():
    k = _kljucevi({"odgovor": "x", "retrieval_unavailable": True,
                   "izvori_neuspeh": ["dokumenti predmeta"], "izvori": []})
    assert k == ["korpus-pao", "izvor-nije-proveren"], k


# ═══════════════════════════════════════════════════════════════════════════
# 3 — sigurnost
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
@pytest.mark.parametrize("nivo", ["HIGH", "MEDIUM", "LOW"])
def test_sigurnost_nikad_nije_broj(nivo):
    s = _js(f'return Z.sigurnost("{nivo}");')
    assert s and s["naziv"].strip()
    assert not any(c.isdigit() for c in s["naziv"]), s
    assert "%" not in s["naziv"]


@nodemark
def test_nepoznata_sigurnost_se_ne_izmislja():
    assert _js('return Z.sigurnost("VRLO_SIGURNO");') is None
    assert _js('return Z.sigurnost("");') is None


# ═══════════════════════════════════════════════════════════════════════════
# 4 — statusna potvrda
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_statusna_potvrda_o_parafrazi_je_NIJE_doslovno():
    t = ("--- BRZA PROCENA\nPravni osnov: POSTOJI\n\n"
         "[~] STATUSNA POTVRDA: Parafrazirano na osnovu pronadjenih izvora — "
         "doslovan clan nije potvrdjen u bazi.\n")
    p = _js(f"return Z.statusnaPotvrda({_j(t)});")
    assert p is not None
    assert p["doslovno"] is False
    assert "Parafrazirano" in p["poruka"]


@nodemark
def test_statusna_potvrda_o_doslovnom_citatu_je_doslovno():
    t = "[v] STATUSNA POTVRDA: Doslovan tekst člana pronađen u bazi propisa."
    p = _js(f"return Z.statusnaPotvrda({_j(t)});")
    assert p["doslovno"] is True


@nodemark
def test_bez_statusne_potvrde_nema_izmisljanja():
    assert _js('return Z.statusnaPotvrda("Rok je 15 dana.");') is None


# ═══════════════════════════════════════════════════════════════════════════
# 5 — izvori
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_izvor_ne_duplira_clan():
    """Baza vraca „Član 367"; naivno spajanje je davalo „član Član 367"."""
    o = _js('return Z.uIzvor({ zakon:"zakon o parnicnom postupku", clan:"Član 367" }).oznaka;')
    assert o.lower().count("lan 367") == 1, o
    assert "član Član" not in o


@nodemark
def test_izvor_dodaje_rec_clan_kad_je_nema():
    o = _js('return Z.uIzvor({ zakon:"zakon o obligacionim odnosima", clan:"367" }).oznaka;')
    assert o == "Zakon o obligacionim odnosima, član 367", o


@nodemark
def test_izvor_prihvata_skraceni_oblik():
    o = _js('return Z.uIzvor({ zakon:"zpp", clan:"čl. 12" }).oznaka;')
    assert o == "Zpp, čl. 12", o


@nodemark
def test_naziv_zakona_ne_dobija_izmisljenu_dijakritiku():
    """Podici prvo slovo je prikaz; dopisati „č" bilo bi menjanje izvora."""
    z = _js('return Z.uIzvor({ zakon:"zakon o parnicnom postupku", clan:"1" }).zakon;')
    assert z == "Zakon o parnicnom postupku"


@nodemark
def test_izvor_bez_zakona_ispada_a_ne_rusi_ekran():
    n = _js('return Z.izvoriIz({ izvori: [{clan:"367"}, {zakon:"ZPP", clan:"1"}, null] }).length;')
    assert n == 1


# ═══════════════════════════════════════════════════════════════════════════
# Odeljci — struktura koju backend vec ispisuje
# ═══════════════════════════════════════════════════════════════════════════

ODGOVOR = """--- BRZA PROCENA
Pravni osnov: POSTOJI

--- PRAVNI ZAKLJUČAK
Postoji verovatan pravni osnov.

--- CITAT ZAKONA [RAG]
Član 367 Stranka može da izjavi žalbu."""


@nodemark
def test_odeljci_se_prepoznaju_po_naslovu():
    n = _js(f"return Z.odeljci({_j(ODGOVOR)}).map(o => o.naslov);")
    assert n == ["BRZA PROCENA", "PRAVNI ZAKLJUČAK", "CITAT ZAKONA [RAG]"], n


@nodemark
def test_odeljci_ne_gube_tekst():
    d = _js(f"return Z.odeljci({_j(ODGOVOR)}).map(o => o.telo);")
    assert "Postoji verovatan pravni osnov." in d[1]
    assert "Član 367" in d[2]


@nodemark
def test_uvod_pre_prvog_naslova_se_ne_baca():
    t = "Uvodna rečenica.\n\n--- ZAKLJUČAK\nTelo."
    d = _js(f"return Z.odeljci({_j(t)});")
    assert d[0]["naslov"] == ""
    assert "Uvodna rečenica." in d[0]["telo"]


@nodemark
def test_odgovor_bez_naslova_ostaje_jedan_odeljak():
    d = _js('return Z.odeljci("Rok je 15 dana od dostavljanja.");')
    assert len(d) == 1 and d[0]["naslov"] == ""


@nodemark
def test_sastavljen_odgovor_nosi_sve_delove():
    k = _js(f"return Object.keys(Z.sastaviOdgovor({_j(DOBAR)}));")
    for x in ("tekst", "odeljci", "potvrda", "sigurnost", "izvori", "upozorenja", "cinjenice"):
        assert x in k, k


@nodemark
def test_prazan_odgovor_ne_rusi_domen():
    o = _js("return Z.sastaviOdgovor(null);")
    assert o["tekst"] == ""
    assert o["izvori"] == []
    # Prazan odgovor NIJE dokazano odsustvo propisa, ali jeste „nema pogotka".
    assert [u["kljuc"] for u in o["upozorenja"]] == ["bez-pogotka"]


# ═══════════════════════════════════════════════════════════════════════════
# Cinjenice iz dokumenta (B4-M2)
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_cinjenice_iz_dokumenta_prezivljavaju_granicu():
    c = _js('return Z.cinjeniceIzDokumenta({ cinjenice_iz_dokumenta: '
            '[{tekst:"Ugovor navodi rok od 8 dana.", dokument:"Ugovor.pdf"}, "Prost navod"] });')
    assert len(c) == 2
    assert c[0]["izvor"] == "Ugovor.pdf"
    assert c[1]["tekst"] == "Prost navod"


@nodemark
def test_odsutne_cinjenice_nisu_prazna_lista_na_ekranu():
    assert _js("return Z.cinjeniceIzDokumenta({});") == []
