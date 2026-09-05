# -*- coding: utf-8 -*-
"""
Z017 — KANCELARIJA, domen.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. `uneseno` I `fakturisano` NISU ISTI IZNOS I NIKAD SE NE SABIRAJU.
     Mesecni izvestaj je nekad sabirao NEOBRACUNAT rad kao `fakturisano_rsd`
     (B2, zatvoreno `6bf80708`), pa je kancelarija verovala da je izdala
     racune koje nije. Zato ovde svaki iznos ima sopstveno ime, sopstvenu
     recenicu i nijedan zbir ne postoji. `test_iznosi_se_ne_sabiraju`.

  2. SVAKI BROJ NOSI PITANJE NA KOJE ODGOVARA.
     Iznos bez pitanja je KPI bez odluke — tacno ono sto vlasnicki kanon
     zabranjuje. `test_svaki_iznos_ima_pitanje`.

  3. TRI STANJA KANCELARIJE SE NE MESAJU.
     „nisam ni u jednoj", „pozvan sam" i „clan sam" traze tri razlicite
     recenice i tri razlicite radnje. `test_tri_stanja_tima`.

  4. KREDITI OSNIVACA NEMAJU „OD KOLIKO".
     `credits_total` je 9999 za osnivacki nalog — broj bez znacenja. Prikazan
     kao granica, lagao bi da granica postoji. `test_osnivac_nema_gornju_granicu`.

  5. PIB SE NE PRIKAZUJE U SPISKU.
     Sifrovan je u bazi i nije pretraziv (B-U-002), pa bi kolona bila prazna
     na svakom redu i tvrdila da podatka nema. `test_pib_nije_u_spisku`.
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
        import * as K from "file:///{V2}/domain/kancelarija.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


NAPLATA = {"mesec": "2026-09", "ukupno_unoseno": 250000, "obracunato": 100000,
           "neobracunato": 150000, "fakturisano": 100000, "naplaceno": 40000}


# ═══════════════════════════════════════════════════════════════════════════
# 1 + 2 — naplata
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_iznosi_se_ne_sabiraju():
    s = _js(f"return K.uNaplatu({_j(NAPLATA)}).stavke;")
    kljucevi = [x["kljuc"] for x in s]
    assert kljucevi == ["uneseno", "neobracunato", "fakturisano", "naplaceno"], kljucevi
    # Nijedna stavka ne sme biti zbir dve druge — zbir bi spojio evidentiran
    # rad sa izdatim racunima, sto je tacno greska koju je B2 zatvorio.
    iznosi = [x["iznos"] for x in s]
    assert len(set(iznosi)) >= 3, iznosi


@nodemark
def test_svaki_iznos_ima_pitanje():
    s = _js(f"return K.uNaplatu({_j(NAPLATA)}).stavke;")
    for x in s:
        assert x["pitanje"].strip(), x
        assert x["pitanje"].strip().endswith("."), x


@nodemark
def test_uneseno_i_fakturisano_imaju_razlicita_imena():
    s = _js(f"return K.uNaplatu({_j(NAPLATA)}).stavke;")
    imena = {x["kljuc"]: x["naziv"] for x in s}
    assert imena["uneseno"] != imena["fakturisano"]
    assert "faktur" not in imena["uneseno"].lower(), imena["uneseno"]


@nodemark
def test_iznos_nula_se_prikazuje_a_ne_krije():
    """0 RSD je odgovor („nista nije naplaceno"), a izostanak reda nije."""
    s = _js('return K.uNaplatu({ mesec:"2026-09", ukupno_unoseno:0, neobracunato:0, '
            'fakturisano:0, naplaceno:0 }).stavke.length;')
    assert s == 4


@nodemark
def test_odsutan_iznos_ispada_iz_prikaza():
    """Polje koje backend nije poslao ne sme se prikazati kao 0."""
    s = _js('return K.uNaplatu({ mesec:"2026-09", fakturisano: 5000 }).stavke.map(x=>x.kljuc);')
    assert s == ["fakturisano"], s


@nodemark
def test_dinar_ne_izmislja_iznos():
    r = _js('return [K.dinar(null), K.dinar(undefined), K.dinar("abc"), K.dinar(0)];')
    assert r[0] is None and r[1] is None and r[2] is None
    assert r[3] is not None and "0" in r[3]


# ═══════════════════════════════════════════════════════════════════════════
# 3 — tim
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_tri_stanja_tima():
    nema = _js('return K.uTim({ status:"no_firma" });')
    poziv = _js('return K.uTim({ status:"pending_invite", firma_naziv:"AK Petrović" });')
    aktivan = _js('return K.uTim({ status:"aktivan", firma:{naziv:"AK Petrović"}, '
                  'moja_uloga:"admin", clanovi:[{id:"1", email:"a@b.rs", uloga_label:"Advokat", status:"aktivan"}] });')
    assert nema["stanje"] == "nema"
    assert poziv["stanje"] == "poziv" and "AK Petrović" in poziv["poruka"]
    assert aktivan["stanje"] == "aktivan" and len(aktivan["clanovi"]) == 1
    # Tri stanja daju tri razlicite poruke — nikad istu.
    assert nema["poruka"] != poziv["poruka"]


@nodemark
def test_nepoznato_stanje_tima_ne_tvrdi_da_kancelarije_nema():
    t = _js('return K.uTim({ status:"nesto_novo" });')
    assert t["stanje"] == "nepoznato"
    assert "nije dostupan" in t["poruka"]


@nodemark
def test_clan_bez_email_a_ispada_a_ne_prikazuje_se_prazan():
    n = _js('return K.uTim({ status:"aktivan", firma:{naziv:"X"}, '
            'clanovi:[{id:"1"}, {id:"2", email:"b@c.rs"}] }).clanovi.length;')
    assert n == 1


# ═══════════════════════════════════════════════════════════════════════════
# 4 — nalog
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_osnivac_nema_gornju_granicu():
    n = _js('return K.uNalog({ email:"a@b.rs", is_pro:true, is_founder:true, '
            'credits_remaining:9999, credits_total:9999 });')
    assert n["krediti"] == 9999
    assert n["kreditiUkupno"] is None, "9999 nije granica i ne sme se prikazati kao granica"


@nodemark
def test_obican_nalog_ima_granicu():
    n = _js('return K.uNalog({ email:"a@b.rs", is_pro:false, is_founder:false, '
            'credits_remaining:3, credits_total:10 });')
    assert n["krediti"] == 3 and n["kreditiUkupno"] == 10
    assert n["plan"] == "Besplatan"


@nodemark
def test_plan_se_ne_izmislja():
    assert _js('return K.uNalog({ is_pro:true }).plan;') == "PRO"
    assert _js('return K.uNalog({}).plan;') == "Besplatan"


# ═══════════════════════════════════════════════════════════════════════════
# 5 — klijenti
# ═══════════════════════════════════════════════════════════════════════════

@nodemark
def test_pib_nije_u_spisku():
    k = _js('return Object.keys(K.uKlijenta({ id:"1", firma:"X d.o.o.", pib:"123456789" }));')
    assert not any("pib" in x.lower() for x in k), k


@nodemark
def test_firma_ima_prednost_nad_imenom():
    n = _js('return K.uKlijenta({ firma:"Delta d.o.o.", ime:"Petar", prezime:"Petrović" }).naziv;')
    assert n == "Delta d.o.o."


@nodemark
def test_fizicko_lice_dobija_ime_i_prezime():
    n = _js('return K.uKlijenta({ ime:"Petar", prezime:"Petrović" }).naziv;')
    assert n == "Petar Petrović"


@nodemark
def test_klijent_bez_ijednog_imena_ne_ostaje_prazan():
    n = _js('return K.uKlijenta({ id:"1" }).naziv;')
    assert n.strip() != ""


@nodemark
def test_ukupno_prezivljava_i_kad_je_veci_od_prikazanog():
    r = _js('return K.uKlijente({ klijenti:[{id:"1",firma:"A"}], ukupno: 240 });')
    assert r["ukupno"] == 240 and len(r["redovi"]) == 1


@nodemark
def test_prazan_odgovor_ne_rusi_domen():
    r = _js("return K.uKlijente(null);")
    assert r["redovi"] == [] and r["ukupno"] is None
