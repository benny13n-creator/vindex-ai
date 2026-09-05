# -*- coding: utf-8 -*-
"""
Z017.11 — NAPOMENE (`uNapomene`): jedan tok nad dve tabele.

Legacy `/app` prikazuje DVA odvojena spiska slobodnog teksta na istom
predmetu: „Beleške" (`predmet_beleske`) i „Komentari" (`predmet_komentari`).
Oba su vlasnikova, oba su slobodan tekst o predmetu, nijedno nema polje po
kome bi se razlikovalo — to su dva imena za istu radnju. Vlasnikovo pravilo
je „1 koncept = 1 vlasnik = 1 istina", pa V2 ima JEDAN tok.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. NIJEDAN POSTOJECI ZAPIS NE SME DA NESTANE.
     Spajanje pojmova ne sme da znaci gubitak reda. Legacy komentar mora
     ostati vidljiv u V2. `test_komentar_iz_legacy_tabele_ostaje_vidljiv`,
     `test_oba_izvora_ulaze_u_isti_tok`.

  2. PORREKLO SE NOSI, ALI SE NE PRIKAZUJE.
     `izvor` postoji ISKLJUCIVO zato sto se brisanje razlikuje po putanji.
     Da se prikazuje, vratio bi dva pojma na ekran kroz mala vrata.
     `test_izvor_je_oznacen_radi_brisanja`.

  3. NAJNOVIJA PRVA.
     Napomena se pise da bi se sutra procitala; hronoloski unazad je jedini
     redosled u kome se to vidi. `test_najnovija_je_prva`.

  4. PRAZAN TEKST NIJE NAPOMENA.
     Red bez sadrzaja se ne prikazuje kao prazna stavka.
     `test_prazne_napomene_se_izostavljaju`.

  5. ODSUTAN DATUM NE POSTAJE IZMISLJEN DATUM.
     Zapis bez trenutka ide na kraj i nema datum — ne dobija „danas".
     `test_bez_datuma_ide_na_kraj_i_nema_datum`.
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
        import * as D from "file:///{V2}/domain/dosije.js";
        const rezultat = await (async () => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _j(x):
    return json.dumps(x, ensure_ascii=False)


def _nap(beleske=None, komentari=None):
    return _js(f"return D.uNapomene({{ beleske: {_j(beleske or [])}, "
               f"komentari: {_j(komentari or [])} }});")


BEL = {"id": "b1", "sadrzaj": "Beleska iz predmet_beleske",
       "created_at": "2026-09-01T10:00:00+00:00"}
KOM = {"id": "k1", "tekst": "Komentar iz predmet_komentari",
       "kreirano": "2026-09-03T10:00:00+00:00"}


# ── 1. Nijedan zapis ne nestaje ──────────────────────────────────────────────
@nodemark
def test_komentar_iz_legacy_tabele_ostaje_vidljiv():
    """Spajanje dva pojma NE SME da znaci gubitak reda."""
    n = _nap(komentari=[KOM])
    assert len(n) == 1
    assert n[0]["tekst"] == "Komentar iz predmet_komentari"


@nodemark
def test_beleska_ostaje_vidljiva():
    n = _nap(beleske=[BEL])
    assert [x["tekst"] for x in n] == ["Beleska iz predmet_beleske"]


@nodemark
def test_oba_izvora_ulaze_u_isti_tok():
    n = _nap([BEL], [KOM])
    assert len(n) == 2, n
    tekstovi = [x["tekst"] for x in n]
    assert "Beleska iz predmet_beleske" in tekstovi
    assert "Komentar iz predmet_komentari" in tekstovi


@nodemark
def test_prazan_ulaz_daje_prazan_tok():
    assert _nap() == []
    assert _js("return D.uNapomene();") == []
    assert _js("return D.uNapomene({ beleske: null, komentari: null });") == []


# ── 2. Poreklo se nosi radi brisanja ─────────────────────────────────────────
@nodemark
def test_izvor_je_oznacen_radi_brisanja():
    """Bez tacnog `izvor`-a brisanje bi islo na pogresnu rutu."""
    n = _nap([BEL], [KOM])
    po_id = {x["id"]: x["izvor"] for x in n}
    assert po_id == {"b1": "beleska", "k1": "komentar"}, po_id


@nodemark
def test_izvor_nije_deo_prikaza():
    """`tekst` i `datum` su jedino sto ekran ispisuje — izvor se ne provlaci."""
    n = _nap([BEL], [KOM])
    for x in n:
        assert "beleska" not in x["tekst"].lower() or "predmet_beleske" in x["tekst"]
        assert x["datum"] and "komentar" not in x["datum"].lower()


# ── 3. Redosled ──────────────────────────────────────────────────────────────
@nodemark
def test_najnovija_je_prva():
    n = _nap([BEL], [KOM])  # KOM je 03.09, BEL je 01.09
    assert n[0]["id"] == "k1", [x["id"] for x in n]
    assert n[1]["id"] == "b1"


@nodemark
def test_redosled_ne_zavisi_od_izvora():
    """Starija napomena ostaje starija i kad dolazi iz druge tabele."""
    stari_kom = dict(KOM, kreirano="2026-08-01T10:00:00+00:00")
    n = _nap([BEL], [stari_kom])  # BEL 01.09 noviji od KOM 01.08
    assert [x["id"] for x in n] == ["b1", "k1"], [x["id"] for x in n]


# ── 4. Prazan tekst ──────────────────────────────────────────────────────────
@nodemark
def test_prazne_napomene_se_izostavljaju():
    n = _nap([{"id": "prazna", "sadrzaj": "   ",
               "created_at": "2026-09-04T10:00:00+00:00"}, BEL],
             [{"id": "prazna2", "tekst": "",
               "kreirano": "2026-09-05T10:00:00+00:00"}])
    assert [x["id"] for x in n] == ["b1"], [x["id"] for x in n]


# ── 5. Odsutan datum ─────────────────────────────────────────────────────────
@nodemark
def test_bez_datuma_ide_na_kraj_i_nema_datum():
    """Odsutan trenutak se ne popunjava izmisljenim — samo se ne prikazuje."""
    bez = {"id": "bez", "sadrzaj": "Bez datuma"}
    n = _nap([BEL, bez], [KOM])
    assert n[-1]["id"] == "bez", [x["id"] for x in n]
    # „—" je kanonska oznaka nepoznatog u celom V2 — NE danasnji datum.
    assert n[-1]["datum"] == "—", repr(n[-1]["datum"])
    assert n[-1]["datumPoznat"] is False, "ekran bi dopisao datumsku odrednicu"


@nodemark
def test_poznat_datum_je_oznacen_kao_poznat():
    n = _nap([BEL])
    assert n[0]["datumPoznat"] is True
    assert n[0]["datum"] == "01.09.2026."


@nodemark
def test_sve_bez_datuma_ne_ruši_redosled():
    n = _nap([{"id": "a", "sadrzaj": "A"}, {"id": "b", "sadrzaj": "B"}])
    assert sorted(x["id"] for x in n) == ["a", "b"]


# ── 6. Ugradnja u Dosije ─────────────────────────────────────────────────────
@nodemark
def test_sastaviDosije_spaja_oba_izvora():
    """Ekran cita `d.beleske` — tamo moraju biti OBA izvora, ne samo jedan."""
    r = _js(
        "const d = D.sastaviDosije({ predmet: { id: 'p', naziv: 'X' },"
        f" beleske: [{_j(BEL)}], komentari: [{_j(KOM)}] }}, null);"
        "return { broj: d.brojBelezaka, ids: d.beleske.map(x => x.id) };"
    )
    assert r["broj"] == 2, r
    assert sorted(r["ids"]) == ["b1", "k1"], r


@nodemark
def test_sastaviDosije_bez_komentara_i_dalje_radi():
    r = _js(
        "const d = D.sastaviDosije({ predmet: { id: 'p', naziv: 'X' },"
        f" beleske: [{_j(BEL)}] }}, null);"
        "return { broj: d.brojBelezaka, ids: d.beleske.map(x => x.id) };"
    )
    assert r == {"broj": 1, "ids": ["b1"]}
