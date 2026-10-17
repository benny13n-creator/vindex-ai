# -*- coding: utf-8 -*-
"""TENFRONTS-M06 (KEYSTONE-003) — neuspeh AI klasifikacije u pozadini mora ostaviti trajan trag.

Posle prelaska na outbox (`emit_durable` → `services/case_evolution`), izuzetak posledice postaje trajan red
`case_evolution_consequences.status='failed'`. Preostali slučaj: AI klasifikacija padne, ali fallback ipak
upiše `klasifikovan_at` — posledica je `completed`. Zastavica `_klasifikacija_greska` se trajno čuva samo u
`ai_tags` reda, a za dokument kome je advokat izabrao vrstu (QA-02 oznaka) uslovni upis `ai_tags` NAMERNO
ne dira — tada neuspeh nije zabeležen nigde osim u logu. `result_ref` posledice (trajno u
`case_evolution_consequences` i u `audit_immutable` metapodacima) mora da ga razlikuje od uspeha.

Stvarni QA-02 harness: stvarna `klasifikuj_i_sacuvaj` i stvarna posledica nad lažnom bazom; AI je zamenjen."""
import pytest

from tests.test_qa02_rucna_vrsta import (  # noqa: F401  (ok je fixture)
    OZNAKA, _ai_klasifikacija, _dok_predmeta, _ispravi, _posao, _prikaci, _spreman, _tagovi, ok)

AI_PAO = {"tip_dokaza": "ostalo", "pravni_elementi": [], "ai_tags": {"_klasifikacija_greska": True},
          "kljucne_cinjenice": []}


def _ai_pada(monkeypatch):
    import routers.evidence as ev
    monkeypatch.setattr(ev, "_klasifikuj_dokument", lambda naziv, tekst: dict(AI_PAO, ai_tags=dict(AI_PAO["ai_tags"])))


def test_uspesna_klasifikacija_result_ref_je_id_dokumenta(ok):
    k, b = ok
    jid = _spreman(k)
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    assert _ai_klasifikacija(b, red["id"]) == red["id"]


def test_ai_pao_bez_ljudske_vrste_trag_u_redu_i_u_result_ref(ok, monkeypatch):
    k, b = ok
    jid = _spreman(k)
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    _ai_pada(monkeypatch)
    ref = _ai_klasifikacija(b, red["id"])
    red = _dok_predmeta(b, jid)
    assert _tagovi(red).get("_klasifikacija_greska") is True
    assert ref != red["id"] and red["id"] in ref and "ai_klasifikacija_neuspesna" in ref


def test_ai_pao_sa_ljudskom_vrstom_neuspeh_je_trajno_zabelezen(ok, monkeypatch):
    k, b = ok
    jid = _spreman(k)
    assert _ispravi(k, _posao(k, jid)["dokument"]["document_id"], "appeal", "lawsuit").status_code == 200
    _prikaci(k, jid)
    red = _dok_predmeta(b, jid)
    _ai_pada(monkeypatch)
    ref = _ai_klasifikacija(b, red["id"])
    red = _dok_predmeta(b, jid)
    # QA-02 invarijanta: ljudska vrsta i oznaka ostaju, AI ai_tags se ne upisuje
    assert red["tip_dokaza"] == "appeal" and _tagovi(red)[OZNAKA]["tip"] == "appeal"
    assert "_klasifikacija_greska" not in _tagovi(red)
    # ...zato je result_ref jedini trajan trag neuspeha
    assert "ai_klasifikacija_neuspesna" in ref and red["id"] in ref
    assert red["klasifikovan_at"]                       # dokument se ne klasifikuje ponovo automatski


def test_result_ref_ide_u_trajni_zapis_posledice_i_audit():
    """`handle_case_changed` prosleđuje povratnu vrednost izvršioca u `_mark_completed` i u audit — bez
    izmene te petlje (proverava se da veza postoji, ne pretpostavlja)."""
    import inspect
    from services import case_evolution as ce
    src = inspect.getsource(ce.handle_case_changed)
    assert "result_ref = await c.executor(event)" in src
    assert "await _mark_completed(event.event_id, c.name, result_ref)" in src
    assert '"result_ref": result_ref' in src
