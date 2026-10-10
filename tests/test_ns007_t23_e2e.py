"""NS007 Task 23 — „Dok spavate" od kraja do kraja, kroz PRAVU rutu `/api/cron/autonomy` (scenario = tests/ns007_demo.py).

A: ročište sutra → pre ciklusa 0 → ciklus → priprema READY (Workspace, detalj sa izvorima iz baze) → ponovljen ciklus bez
   novog proizvoda i bez nove naplate → prihvatanje = ACCEPTED, 0 spoljnih upisa.
B: proverena nova odluka → PRECEDENT_IMPACT READY sa tačnim izvorom i doslovnim izvodom.
C: neproverena (izmišljena) odluka → nijedan proizvod.
UI deo (Danas „Vindex je pripremio", Pregled predmeta, detalj): frontend-v2-ng/tests/live-pripremljeno.mjs nad stvarnim
odgovorima istog ciklusa, i snimci: frontend-v2-ng/tests/ns007-demo.mjs.
"""
import pytest

from tests import ns007_demo
from tests import ns007_korpus as kor


@pytest.fixture(scope="module")
def tok():
    return ns007_demo.pokreni(stampaj=lambda *a: None)


def test_A_vindex_priprema_pre_nego_sto_advokat_pita(tok):
    k = tok["koraci"]
    assert k["pre"] == 0, "pre ciklusa nema pripremljenog rada"
    assert k["c1"]["status"] == "COMPLETED" and k["c1"]["sazetak"]["spremno"] == 1
    d = k["hp_detalj"]
    assert d["status"] == "READY_FOR_REVIEW" and d["quality_state"] == "AI_PREPARED_FOR_REVIEW"
    assert d["content_json"]["rociste"]["sud"] == "Osnovni sud u Beogradu" and d["content_json"]["rociste"]["vreme"] == "10:00"
    assert d["content_json"]["kljucne_cinjenice"] and d["source_refs"]


def test_A_ponovljen_ciklus_bez_duplikata_i_bez_naplate(tok):
    k = tok["koraci"]
    assert k["c2"]["status"] == "COMPLETED" and k["c2"]["sazetak"]["planirano"] == 0 and k["c2"]["sazetak"]["duplikata"] == 1
    assert k["drugi_pozivi"] == 0


def test_A_prihvatanje_bez_spoljnog_efekta(tok):
    k = tok["koraci"]
    assert k["prihvatanje"]["status"] == "ACCEPTED"
    assert k["spoljni_posle_odluke"] == [] and k["spoljni_ukupno"] == []


def test_B_utemeljena_praksa_sa_tacnim_izvorom(tok):
    k = tok["koraci"]
    d = k["pi_detalj"]
    z = d["content_json"]["izvor"]
    assert (z["broj"], z["sud"], z["datum"], z["provereno"]) == (kor.ODLUKA, "Vrhovni sud", "2023-05-10", True)
    u = d["content_json"]["ai"]["uticaj"][0]
    assert u["izvod_proveren"] and u["izvod_iz_odluke"].lower() in kor.TEKST_OBRAZLOZENJE.lower()


def test_C_neproverena_odluka_bez_proizvoda(tok):
    radovi = tok["koraci"]["svi_radovi"]
    assert {r[2] for r in radovi if r[0] == "PRECEDENT_IMPACT"} == {kor.ODLUKA}
    assert not any("7777" in r[2] for r in radovi)
    assert sorted(tok["pozivi"]) == ["praksa", "ročište"], "ukupno tačno 2 poziva modela za 2 pripremljena rada"
