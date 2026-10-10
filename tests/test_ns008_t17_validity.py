# -*- coding: utf-8 -*-
"""NS008 Task 17 — važenje institucionalnog znanja: bez lažne svežine.

Validnost CURRENT samo uz pozitivan signal (rok važenja u budućnosti, zlatni šablon, ljudski ishod završenog
predmeta). Odobren rad i potvrđena lekcija bez podatka o važenju → UNKNOWN. Pravna aktuelnost internog rada se
nikad ne tvrdi (nema pouzdanog registra izmena propisa); rad koji se poziva na propis dobija oznaku za proveru.
"""
from datetime import date

import pytest

from services import law_brain as lb

DANAS = date(2026, 10, 10)
PA = {"id": "p1", "user_id": "uid-A", "status": "zatvoren"}


def _art(tekst):
    return lb.artifact_item({"id": "s1", "user_id": "uid-A", "predmet_id": "p1", "tip": "tuzba", "naziv": "Tužba",
                             "tekst": tekst, "status": "approved", "is_lawyer_approved": True,
                             "approved_at": "2020-01-01T00:00:00+00:00", "pinecone_indexed": True}, PA)


def test_odobren_rad_nije_lazno_svez():
    a = _art("Obrazloženje bez propisa.")
    d = a.to_dict()
    assert a.validity == lb.UNKNOWN and a.trusted, "overen (poverljiv), ali važenje nepoznato"
    assert d["attrs"]["pravna_aktuelnost"] == lb.UNKNOWN and d["attrs"]["poziva_se_na_propis"] is False
    assert d["attrs"]["napomena_aktuelnosti"] is None


@pytest.mark.parametrize("tekst", ["Prema članu 154 ZOO.", "čl. 12 st. 1", "Zakon o radu propisuje", "„Sl. glasnik RS“, br. 24/2005"])
def test_rad_koji_se_poziva_na_propis_trazi_proveru(tekst):
    d = _art(tekst).to_dict()
    assert d["attrs"]["poziva_se_na_propis"] is True and d["attrs"]["pravna_aktuelnost"] == lb.UNKNOWN
    assert "proverite da li su u međuvremenu izmenjeni" in d["attrs"]["napomena_aktuelnosti"]
    assert d["validity"] == lb.UNKNOWN, "rad se nikad tiho ne prepisuje niti proglašava zastarelim bez signala"


def test_potvrdjena_lekcija_bez_oznake_nije_vazeca_po_defaultu():
    it = lb.lesson_item({"id": "l1", "user_id": "uid-A", "status_lekcije": "usvojena_praksa", "potvrdio": "uid-A",
                         "potvrdjeno_at": "2024-01-01", "zastarela": False, "lecija": "Član 5 Zakona o radu..."}, "uid-A")
    assert it.validity == lb.UNKNOWN and it.trusted and it.to_dict()["attrs"]["poziva_se_na_propis"] is True


def test_pozitivni_signali_vazenja():
    m = lb.memory_item({"id": "m", "kancelarija_id": "k", "user_id": "u", "entity_type": "sudija", "entity_id": "x",
                        "sadrzaj": "s", "izvor": "manual", "expires_at": "2027-01-01"}, user_id="u", today=DANAS)
    assert m.validity == lb.CURRENT
    m2 = lb.memory_item({"id": "m", "kancelarija_id": "k", "user_id": "u", "entity_type": "sudija", "entity_id": "x",
                         "sadrzaj": "s", "izvor": "manual", "expires_at": "2026-01-01"}, user_id="u", today=DANAS)
    assert m2.validity == lb.STALE
    o = lb.outcome_view(PA, {"id": "o", "predmet_id": "p1", "user_id": "uid-A", "ishod": "pobeda"})["item"]
    assert o.validity == lb.CURRENT, "ishod završenog predmeta je istorijska činjenica"


def test_odbijen_i_zastareo_nikad_kao_vazeci():
    r = lb.artifact_item({"id": "s", "user_id": "uid-A", "predmet_id": "p1", "status": "rejected", "tekst": "t"}, PA)
    assert r.validity == lb.DEPRECATED and not r.trusted
    z = lb.lesson_item({"id": "l", "user_id": "uid-A", "status_lekcije": "usvojena_praksa", "potvrdio": "u",
                        "potvrdjeno_at": "2020-01-01", "zastarela": True}, "uid-A")
    assert z.validity == lb.STALE


def test_redosled_vazece_ispred_nepoznatog_ispred_zastarelog():
    a = lb.LawBrainItem(source_kind="x", source_owner="t", source_id="a", scope=lb.SCOPE_USER,
                        trust_class=lb.HUMAN_MEMORY_NOTE, validity=lb.STALE)
    b = lb.LawBrainItem(source_kind="x", source_owner="t", source_id="b", scope=lb.SCOPE_USER,
                        trust_class=lb.HUMAN_MEMORY_NOTE, validity=lb.UNKNOWN)
    c = lb.LawBrainItem(source_kind="x", source_owner="t", source_id="c", scope=lb.SCOPE_USER,
                        trust_class=lb.HUMAN_MEMORY_NOTE, validity=lb.CURRENT)
    assert [x.source_id for x in lb.order_items([a, b, c])] == ["c", "b", "a"]
