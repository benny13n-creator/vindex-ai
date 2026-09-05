# -*- coding: utf-8 -*-
"""
Z017.10 — KALENDAR (domen `sastaviKalendar`).

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. KANDIDAT NIJE TERMIN.
     Nepotvrdjen predlog roka se NE SME pojaviti u kalendaru. Advokat koji
     vidi predlog u planu moze da poveruje da je obaveza zakazana i da ne
     preduzme radnju koju je predlog trazio. Kandidati zive u Danas, gde
     postoji kontrola da se o njima odluci.
     `test_kandidat_nije_termin`, `test_potvrdjen_i_kandidat_zajedno`.

  2. ALI KANDIDAT SE PREBROJAVA.
     Predlog koji nestane bez traga je gori od predloga u kalendaru: advokat
     ne bi znao da li odluka ceka na nekoliko rokova ili ni na jednom.
     `test_kandidati_se_prebrojavaju`, `test_bez_kandidata_broj_je_nula`.

  3. RAZRESEN ROK NIJE OBAVEZA.
     `izvrsen` / `otkazan` / `odbijen` ne stoje u planu buducnosti, i vise
     ne cekaju odluku. `test_razreseni_rokovi_ne_ulaze`.

  4. NEIZJAVLJEN ZAPIS SE NE PROGLASAVA ROKOM, NEGO SE SAOPSTAVA.
     Red hronologije bez `vrsta="rok"` nije rok (migracija 129). Fail-closed
     se saopstava kroz `nedokazivo`, i taj broj se NE SME spojiti sa brojem
     predloga — to su dva razlicita razloga odsustva.
     `test_neizjavljen_zapis_je_nedokaziv`, `test_nedokazivo_nije_isto_sto_i_predlog`.

  5. NEMA MREZE PRAZNIH DANA.
     Prikazuju se samo dani koji imaju stavku. Mreza od 30 praznih kvadrata
     nije plan nego ukras. `test_prazni_dani_se_ne_prikazuju`.

  6. PAD JEDNOG IZVORA NE PRAZNI KALENDAR.
     Rocista bez rokova (i obrnuto) i dalje daju plan.
     `test_samo_rocista`, `test_samo_rokovi`.

  7. HRONOLOSKI REDOSLED, VREME UNUTAR DANA.
     `test_redosled_je_hronoloski`, `test_vreme_uredjuje_unutar_dana`.
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

SADA = "new Date(2026, 8, 5)"  # 5. septembar 2026, lokalna ponoc


def _js(telo: str):
    skripta = textwrap.dedent(f"""
        import * as D from "file:///{V2}/domain/danas.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


def _kal(kandidati=None, kalendar=None, sada=SADA):
    """Ceo rezultat + splostena lista opisa i dana, radi tvrdnji o sadrzaju."""
    return _js(
        f"const k = D.sastaviKalendar({{ kandidati: {_j(kandidati or {})}, "
        f"kalendar: {_j(kalendar or {})} }}, {sada});"
        "const opisi = []; const dani = [];"
        "for (const m of k.meseci) for (const d of m.dani) {"
        "  dani.push(d.iso);"
        "  for (const x of d.stavke) opisi.push(x.opis);"
        "}"
        "return { ukupno: k.ukupno, predlozi: k.predlozi, nedokazivo: k.nedokazivo,"
        "         meseci: k.meseci.map(m => m.naziv), dani, opisi };"
    )


def _rok(dogadjaj, datum, stanje="potvrdjen", vrsta="rok"):
    return {"id": dogadjaj, "dogadjaj": dogadjaj, "datum_iso": datum,
            "datum": datum, "vrsta": vrsta, "stanje": stanje,
            "vaznost": "važan", "predmet_id": "p1"}


def _rociste(datum, sud="Osnovni sud", vreme=None):
    r = {"tip": "rociste", "datum": datum, "naziv": sud, "predmet_id": "p1"}
    if vreme:
        r["vreme"] = vreme
    return r


# ── 1. Kandidat nije termin ────────────────────────────────────────────────
@nodemark
def test_kandidat_nije_termin():
    k = _kal({"rokovi": [_rok("PREDLOG", "2026-09-20", stanje="kandidat")]})
    assert k["ukupno"] == 0, "nepotvrdjen predlog se pojavio kao termin"
    assert "PREDLOG" not in k["opisi"]
    assert k["meseci"] == []


@nodemark
def test_potvrdjen_jeste_termin():
    k = _kal({"rokovi": [_rok("ODGOVOR NA TUZBU", "2026-09-20")]})
    assert k["ukupno"] == 1
    assert "ODGOVOR NA TUZBU" in k["opisi"]


@nodemark
def test_potvrdjen_i_kandidat_zajedno():
    """Kljucni test: potvrdjen prolazi, kandidat pada, u ISTOM odgovoru."""
    k = _kal({"rokovi": [
        _rok("POTVRDJEN", "2026-09-20"),
        _rok("KANDIDAT", "2026-09-21", stanje="kandidat"),
    ]})
    assert k["opisi"] == ["POTVRDJEN"], k["opisi"]
    assert k["ukupno"] == 1
    assert k["predlozi"] == 1


@nodemark
def test_odsutno_stanje_nije_potvrdjen():
    """Red bez `stanje` nije dokazano potvrdjen — fail-closed, ne u plan."""
    r = _rok("BEZ STANJA", "2026-09-20")
    r.pop("stanje")
    k = _kal({"rokovi": [r]})
    assert k["ukupno"] == 0, "rok bez izjavljenog stanja je usao u plan"


# ── 2. Kandidati se prebrojavaju ───────────────────────────────────────────
@nodemark
def test_kandidati_se_prebrojavaju():
    k = _kal({"rokovi": [
        _rok("A", "2026-09-20", stanje="kandidat"),
        _rok("B", "2026-09-21", stanje="kandidat"),
        _rok("C", "2026-09-22", stanje="kandidat"),
    ]})
    assert k["ukupno"] == 0
    assert k["predlozi"] == 3, "predlozi su nestali bez traga"


@nodemark
def test_bez_kandidata_broj_je_nula():
    k = _kal({"rokovi": [_rok("A", "2026-09-20")]})
    assert k["predlozi"] == 0


@nodemark
def test_razresen_kandidat_se_ne_broji_kao_predlog():
    """Odbijen predlog vise ne ceka odluku — ne sme da tera advokata u Danas."""
    k = _kal({"rokovi": [_rok("ODBIJEN", "2026-09-20", stanje="odbijen")]})
    assert k["predlozi"] == 0
    assert k["ukupno"] == 0


@nodemark
def test_neizjavljen_kandidat_nije_predlog_nego_nedokaziv():
    """Zapis koji nije izjavljen kao rok ne postaje predlog roka."""
    k = _kal({"rokovi": [
        _rok("ZADATAK", "2026-09-20", stanje="kandidat", vrsta="zadatak"),
    ]})
    assert k["predlozi"] == 0
    assert k["nedokazivo"] == 1


# ── 3. Razreseni rokovi ────────────────────────────────────────────────────
@nodemark
@pytest.mark.parametrize("stanje", ["izvrsen", "otkazan", "odbijen"])
def test_razreseni_rokovi_ne_ulaze(stanje):
    k = _kal({"rokovi": [_rok("RAZRESEN", "2026-09-20", stanje=stanje)]})
    assert k["ukupno"] == 0, f"stanje={stanje} je ostalo u planu"


# ── 4. Neizjavljen zapis ───────────────────────────────────────────────────
@nodemark
def test_neizjavljen_zapis_je_nedokaziv():
    k = _kal({"rokovi": [
        _rok("BEZ VRSTE", "2026-09-20", vrsta=None),
        _rok("DOGADJAJ", "2026-09-21", vrsta="dogadjaj"),
        _rok("PRAVI ROK", "2026-09-22"),
    ]})
    assert k["opisi"] == ["PRAVI ROK"], k["opisi"]
    assert k["nedokazivo"] == 2, "neizjavljeni zapisi nisu saopsteni"


@nodemark
def test_nedokazivo_nije_isto_sto_i_predlog():
    """Dva razlicita fail-closed razloga se NE SMEJU spojiti u jedan broj."""
    k = _kal({"rokovi": [
        _rok("NEIZJAVLJEN", "2026-09-20", vrsta="zadatak"),
        _rok("PREDLOG", "2026-09-21", stanje="kandidat"),
    ]})
    assert k["nedokazivo"] == 1
    assert k["predlozi"] == 1


# ── 5. Nema mreze praznih dana ─────────────────────────────────────────────
@nodemark
def test_prazni_dani_se_ne_prikazuju():
    k = _kal({"rokovi": [
        _rok("A", "2026-09-08"),
        _rok("B", "2026-09-25"),
    ]})
    assert k["dani"] == ["2026-09-08", "2026-09-25"], k["dani"]


@nodemark
def test_vise_stavki_istog_dana_je_jedan_dan():
    k = _kal({"rokovi": [_rok("A", "2026-09-08"), _rok("B", "2026-09-08")]})
    assert k["dani"] == ["2026-09-08"]
    assert k["ukupno"] == 2


@nodemark
def test_meseci_se_razdvajaju():
    k = _kal({"rokovi": [_rok("A", "2026-09-08"), _rok("B", "2026-10-08")]})
    assert len(k["meseci"]) == 2, k["meseci"]
    assert k["meseci"][0] != k["meseci"][1]


# ── 6. Pad jednog izvora ───────────────────────────────────────────────────
@nodemark
def test_samo_rocista():
    """Rokovi nisu stigli — rocista i dalje daju plan, ne prazan ekran."""
    k = _kal(kandidati={}, kalendar={"dogadjaji": [_rociste("2026-09-15")]})
    assert k["ukupno"] == 1
    assert k["dani"] == ["2026-09-15"]


@nodemark
def test_samo_rokovi():
    k = _kal({"rokovi": [_rok("A", "2026-09-15")]}, kalendar={})
    assert k["ukupno"] == 1


@nodemark
def test_oba_prazna_daje_prazan_plan_bez_pada():
    k = _kal({}, {})
    assert k["ukupno"] == 0 and k["meseci"] == []
    assert k["predlozi"] == 0 and k["nedokazivo"] == 0


@nodemark
def test_neocekivan_oblik_ne_rusi_kalendar():
    k = _js(
        "const k = D.sastaviKalendar({ kandidati: {rokovi: 'ne-niz'}, "
        f"kalendar: {{dogadjaji: null}} }}, {SADA});"
        "return { ukupno: k.ukupno, predlozi: k.predlozi, nedokazivo: k.nedokazivo };"
    )
    assert k == {"ukupno": 0, "predlozi": 0, "nedokazivo": 0}


# ── 7. Redosled ────────────────────────────────────────────────────────────
@nodemark
def test_redosled_je_hronoloski():
    k = _kal({"rokovi": [
        _rok("TRECI", "2026-10-01"),
        _rok("PRVI", "2026-09-08"),
        _rok("DRUGI", "2026-09-20"),
    ]})
    assert k["opisi"] == ["PRVI", "DRUGI", "TRECI"], k["opisi"]


@nodemark
def test_vreme_uredjuje_unutar_dana():
    k = _js(
        "const k = D.sastaviKalendar({ kandidati: {}, kalendar: { dogadjaji: ["
        f"{_j(_rociste('2026-09-15', 'Kasno', '14:00'))},"
        f"{_j(_rociste('2026-09-15', 'Rano', '08:30'))}"
        f"] }} }}, {SADA});"
        "return k.meseci[0].dani[0].stavke.map(x => x.vreme);"
    )
    assert k == ["08:30", "14:00"], k


@nodemark
def test_rociste_bez_datuma_se_izostavlja():
    k = _kal(kalendar={"dogadjaji": [{"tip": "rociste", "naziv": "Bez datuma"}]})
    assert k["ukupno"] == 0


@nodemark
def test_ne_rociste_dogadjaji_se_izostavljaju():
    """Kalendarski feed nosi i druge tipove; kalendar prikazuje samo rocista."""
    k = _kal(kalendar={"dogadjaji": [
        {"tip": "sastanak", "datum": "2026-09-15", "naziv": "Sastanak"},
        _rociste("2026-09-16"),
    ]})
    assert k["ukupno"] == 1
