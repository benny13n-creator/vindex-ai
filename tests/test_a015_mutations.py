# -*- coding: utf-8 -*-
"""A015 §17 — MUTACIJE M1–M20 nad projekcionim slojem.

Obrazac je svuda isti: **(1)** dokaz da je mutacija stvarno promenila ponašanje,
**(2)** dokaz da kanonski put daje ispravan rezultat. Bez drugog koraka „ubijena
mutacija" ne znači ništa.

Gde mutacija nije izvodiva zbog arhitekture, to je izričito označeno kao
NEPREDSTAVLJIVA i objašnjeno — nikad prijavljeno kao ubijena.
"""
import asyncio
import os
import sys
import uuid
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import services.v2_projection as proj  # noqa: E402
from services.v2_projection import je_v2_kljuc, projekcioni_kljuc, u_akcije  # noqa: E402
from shared.contradiction_identity import contradiction_dedupe_key  # noqa: E402
from shared.issue_v2 import MIN_TVRDNJI, STATUSI_OTVORENI  # noqa: E402

from test_a015_v2_projection import D1, D2, I1, I2, K1, K2, K3, _k  # noqa: E402

# Tri spora nad ISTIM parom dokumenata i ISTOM relacijom — A005 oblik.
SPOROVI = [
    _k(K1, issue_id=I1, label="razlika u datumu", dokumenti=(D1, D2), claims=("c1", "c4")),
    _k(K2, issue_id=I2, label="razlika u iznosu", dokumenti=(D1, D2), claims=("c2", "c5")),
    _k(K3, issue_id="aaaa0003-0000-4000-8000-000000000003", label="razlika u razlogu",
       dokumenti=(D1, D2), claims=("c3", "c6")),
]
LEGACY_LOK = {"lokacija_1": "DOK-01 str.1", "lokacija_2": "DOK-02 str.1"}


def _sazmi(kljucevi):
    """Tacna operacija sa `services/case_evolution.py:1052`."""
    return {k: k for k in kljucevi}


# ═══════════════════════════════════════════════════════════════════════════
# M1 / M6 / M7 — identitet iz pogrešnog entiteta
# ═══════════════════════════════════════════════════════════════════════════

def test_M1_projekcija_bez_contradiction_id_je_ubijena():
    """MUTANT: kljuc iz necega drugog -> `u_akciju` mora da pukne bez id-a."""
    with pytest.raises(ValueError):
        proj.u_akciju({"issue_id": I1, "issue_label": "bez id-a"})
    assert proj.u_akciju(_k(K1))["dedupe_key"] == projekcioni_kljuc(K1)


def test_M6_issue_id_umesto_contradiction_id_je_ubijen():
    """Dve kontradikcije iste sporne tacke (razlicit `relation_type`)."""
    a = _k(K1, issue_id=I1, rel="cinjenica_cinjenica")
    b = _k(K2, issue_id=I1, rel="cinjenica_norma")
    mut = {f"{proj.PREFIKS}{x['issue_id']}" for x in (a, b)}
    assert len(mut) == 1, "mutacija nije primenjena"

    kanon = {x["dedupe_key"] for x in u_akcije([a, b])}
    assert len(kanon) == 2


def test_M7_identitet_tvrdnje_kao_identitet_kontradikcije_je_ubijen():
    """Ista tvrdnja moze biti clan vise spornih tacaka (A012 J16)."""
    a = _k(K1, claims=("c1", "c2"))
    b = _k(K2, claims=("c1", "c3"))
    mut = {tuple(sorted(x["claim_ids"]))[0] for x in (a, b)}
    assert len(mut) == 1, "mutacija nije primenjena — obe dele c1"

    kanon = {x["dedupe_key"] for x in u_akcije([a, b])}
    assert len(kanon) == 2


# ═══════════════════════════════════════════════════════════════════════════
# M2 / M3 / M8 / M9 / M20 — identitet iz dokumenata ili teksta
# ═══════════════════════════════════════════════════════════════════════════

def test_M2_M9_identitet_iz_para_dokumenata_je_ubijen():
    mut = {tuple(sorted(s["dokument_ids"])) for s in SPOROVI}
    assert len(mut) == 1, "mutacija nije primenjena — sva tri dele isti par"

    kanon = {a["dedupe_key"] for a in u_akcije(SPOROVI)}
    assert len(kanon) == 3


def test_M3_identitet_iz_opisa_je_ubijen():
    isti_opis = [_k(K1, label="Dokumenti se ne slazu."),
                 _k(K2, label="Dokumenti se ne slazu.")]
    mut = {s["issue_label"] for s in isti_opis}
    assert len(mut) == 1, "mutacija nije primenjena"

    assert len({a["dedupe_key"] for a in u_akcije(isti_opis)}) == 2


def test_M8_M20_razdvajanje_tema_je_ubijeno():
    """Sva tri spora dele dokumente I relaciju; razlikuju se samo po TEMI."""
    assert len({s["relation_type"] for s in SPOROVI}) == 1
    assert len({tuple(sorted(s["dokument_ids"])) for s in SPOROVI}) == 1
    assert len({a["dedupe_key"] for a in u_akcije(SPOROVI)}) == 3


# ═══════════════════════════════════════════════════════════════════════════
# M4 / M13 — sažimanje po dedupe_key
# ═══════════════════════════════════════════════════════════════════════════

def test_M4_M13_dict_sazimanje_po_legacy_kljucu_je_ubijeno():
    """Tacan kvar sa `case_evolution.py:1052`, izmeren sa oba kljuca."""
    legacy = [contradiction_dedupe_key(LEGACY_LOK) for _ in SPOROVI]
    assert len(_sazmi(legacy)) == 1, "mutacija nije primenjena — legacy spaja 3 u 1"

    v2 = [a["dedupe_key"] for a in u_akcije(SPOROVI)]
    assert len(_sazmi(v2)) == 3, "V2 kljucevi se sazimaju — silent loss"


def test_M13b_sazimanje_ne_gubi_ni_kad_su_pomesane_legacy_i_V2_akcije():
    """U prelaznom periodu tabela nosi obe vrste kljuceva."""
    legacy_akcija = contradiction_dedupe_key(LEGACY_LOK)
    svi = [legacy_akcija] + [a["dedupe_key"] for a in u_akcije(SPOROVI)]
    sazeto = _sazmi(svi)
    assert len([k for k in sazeto if je_v2_kljuc(k)]) == 3
    assert len(sazeto) == 4


# ═══════════════════════════════════════════════════════════════════════════
# M5 — sudar obaveštenja
# ═══════════════════════════════════════════════════════════════════════════

def test_M5_kljuc_obavestenja_iz_legacy_kljuca_je_ubijen():
    """`idx_notifications_open_dedupe` je `(user_id, dedupe_key)` BEZ `predmet_id`
    (A013 GAP-4, reprodukovano uzivo kao `23505`). Legacy kljuc se ponavlja
    izmedju predmeta jer je heš oznaka `DOK-NN`; V2 kljuc je UUID."""
    mut_a = contradiction_dedupe_key(LEGACY_LOK)
    mut_b = contradiction_dedupe_key(LEGACY_LOK)
    assert mut_a == mut_b, "mutacija nije primenjena — legacy kolidira"

    v2_a = projekcioni_kljuc("cccc0001-0000-4000-8000-000000000001")
    v2_b = projekcioni_kljuc("cccc0002-0000-4000-8000-000000000002")
    assert v2_a != v2_b

    korenska = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(korenska, "migrations", "101_notifications_dedupe_key.sql"),
              encoding="utf-8", errors="ignore") as f:
        m101 = f.read()
    assert "notifications(user_id, dedupe_key)" in m101
    assert "notifications(predmet_id" not in m101, (
        "opseg obavestenja je promenjen — GAP-4 treba ponovo izmeriti")


# ═══════════════════════════════════════════════════════════════════════════
# M14 / M18 — nedeterminizam
# ═══════════════════════════════════════════════════════════════════════════

def test_M14_nasumican_UUID_u_projekciji_je_ubijen():
    def _mutant(_):
        return f"{proj.PREFIKS}{uuid.uuid4()}"

    assert len({_mutant(K1) for _ in range(10)}) == 10, "mutacija nije primenjena"
    assert len({projekcioni_kljuc(K1) for _ in range(10)}) == 1


def test_M18_nedeterministican_redosled_je_ubijen():
    obrnuto = list(reversed(SPOROVI))
    mut_a = [s["id"] for s in SPOROVI]
    mut_b = [s["id"] for s in obrnuto]
    assert mut_a != mut_b, "mutacija nije primenjena"

    assert [a["dedupe_key"] for a in u_akcije(SPOROVI)] == \
           [a["dedupe_key"] for a in u_akcije(obrnuto)]


# ═══════════════════════════════════════════════════════════════════════════
# M15 — uklonjen V2 marker
# ═══════════════════════════════════════════════════════════════════════════

def test_M15_uklonjen_V2_marker_je_ubijen():
    a = proj.u_akciju(_k(K1))
    mut = {k: v for k, v in a["dokaz"].items() if k not in ("source_type", "source_id")}
    assert "source_id" not in mut, "mutacija nije primenjena"

    assert a["dokaz"]["source_type"] == proj.IZVOR_TIP
    assert a["dokaz"]["source_id"] == K1
    assert je_v2_kljuc(a["dedupe_key"]), "i kljuc sam mora biti prepoznatljiv"


# ═══════════════════════════════════════════════════════════════════════════
# M17 — tihi fallback na legacy identitet
# ═══════════════════════════════════════════════════════════════════════════

def test_M17_tihi_fallback_na_legacy_identitet_je_NEPREDSTAVLJIV():
    """Projekcija ne uvozi legacy identitet — fallback nema odakle da nastane."""
    put = os.path.join(os.path.dirname(__file__), "..", "services", "v2_projection.py")
    izvor = open(put, encoding="utf-8").read()
    kod = "\n".join(l.split("#")[0] for l in izvor.split('"""', 2)[-1].splitlines())
    for zabranjeno in ("contradiction_dedupe_key", "_stable_key", "lokacija", "opis"):
        assert zabranjeno not in kod, f"projekcija dodiruje legacy identitet: {zabranjeno}"


def test_M17b_Rule3_ne_mesa_identitete():
    """`_compute_target_actions` sme da vrati ILI V2 ILI legacy kontradikcije,
    nikad obe — inace bi isti spor dobio dve akcije sa dva kljuca."""
    put = os.path.join(os.path.dirname(__file__), "..", "services", "case_evolution.py")
    izvor = open(put, encoding="utf-8").read()
    poc = izvor.index("_v2_akcije = await v2_akcije_za_predmet")
    blok = izvor[poc:poc + 220]
    assert "if _v2_akcije:" in blok
    assert "return actions" in blok, "V2 grana mora prekinuti pre legacy petlje"


# ═══════════════════════════════════════════════════════════════════════════
# M10 / M11 / M12 / M19 — nosilac je nizvodni/uzvodni sloj
# ═══════════════════════════════════════════════════════════════════════════

def test_M10_M11_M12_nosilac_je_domen_i_SQL_a_ne_projekcija():
    """Projekcija ne moze da propusti tudji/nulti/jedan claim jer uopste ne
    odlucuje o clanstvu — ona projektuje ono sto je VEC perzistirano, a
    persistence to odbija u tri sloja (A014 katalog, A012 domen, SQL GUARD 2).

    Ovde se brani jedino sto projekcija moze da pokvari: da pocne da cita van
    opsega predmeta."""
    put = os.path.join(os.path.dirname(__file__), "..", "services", "v2_projection.py")
    izvor = open(put, encoding="utf-8").read()
    kod = "\n".join(l.split("#")[0] for l in izvor.split('"""', 2)[-1].splitlines())
    assert '.eq("predmet_id", predmet_id)' in kod, "citanje nije ograniceno na predmet"
    assert MIN_TVRDNJI == 2


def test_M19_zastita_od_trke_je_NEPREDSTAVLJIVA_u_projekciji():
    """Projekcija je cista transformacija bez upisa — trke nema.
    Nosilac je parcijalni UNIQUE indeks u bazi (A012, mutacija M4 ubijena uzivo)."""
    put = os.path.join(os.path.dirname(__file__), "..", "services", "v2_projection.py")
    izvor = open(put, encoding="utf-8").read()
    kod = "\n".join(l.split("#")[0] for l in izvor.split('"""', 2)[-1].splitlines())
    for w in (".insert(", ".update(", ".upsert(", ".delete(", ".rpc("):
        assert w not in kod


# ═══════════════════════════════════════════════════════════════════════════
# M16 — REVIEW_REQUIRED kao OPEN
# ═══════════════════════════════════════════════════════════════════════════

def test_M16_REVIEW_REQUIRED_kao_OPEN_je_ubijen():
    """Odluka B (A014/A015 §12): `REVIEW_REQUIRED` se NE perzistira i NE ulazi u
    authoritative projekciju. Mutant bi ga upisao kao OPEN i time tvrdio
    kontinuitet koji domen nije utvrdio.

    Prva verzija ovog testa merila je izvorni tekst u prozoru od 400 znakova i
    padala je zato sto je prozor prelazio u sledeci blok. Zamenjena je merenjem
    PONASANJA -- jace, i ne zavisi od rasporeda linija."""
    from test_a013_v2_persistence_adapter import (C1, C2, C3, FF, PREDMET, SVI_DOKAZI,
                                                  UID, FakeSupa, _p, _pokreni)

    postojeca = ([{"id": "I1", "predmet_id": PREDMET, "status": "DISCOVERED"}],
                 [{"id": "k1", "issue_id": "I1"}],
                 [{"contradiction_id": "k1", "dokaz_id": C1, "removed_at": None},
                  {"contradiction_id": "k1", "dokaz_id": C2, "removed_at": None}])
    supa = FakeSupa(dokazi=SVI_DOKAZI, issues=postojeca[0],
                    kontradikcije=postojeca[1], clanovi=postojeca[2])

    # `{C1,C2}` vs `{C1,C3}` -- presek bez sadrzavanja -> REVIEW_REQUIRED
    r = _pokreni(supa, [_p([C1, C3])])
    assert r[0]["odluka"] == "REVIEW_REQUIRED", "domen nije dao ocekivani ishod"
    assert r[0]["persisted"] is False
    assert supa.rpc_pozivi == [], "REVIEW_REQUIRED je zavrsio kao upis (verovatno kao OPEN)"

    # A projekcija cita iskljucivo `state='OPEN'` iz baze, pa ni slucajno
    # upisan REVIEW_REQUIRED red ne bi postao akcija.
    put = os.path.join(os.path.dirname(__file__), "..", "services", "v2_projection.py")
    pkod = open(put, encoding="utf-8").read()
    assert '.eq("state", "OPEN")' in pkod
