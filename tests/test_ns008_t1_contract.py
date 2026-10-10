# -*- coding: utf-8 -*-
"""NS008 Task 1 — kanonski Law Brain ugovor (services/law_brain.py)."""
from datetime import date

import pytest

from services import law_brain as lb

DANAS = date(2026, 10, 10)


def _stavka(**kw):
    base = dict(source_kind="lesson", source_owner="lessons_learned", source_id="L1",
                scope=lb.SCOPE_USER, trust_class=lb.AI_CANDIDATE_LESSON, validity=lb.UNKNOWN)
    base.update(kw)
    return lb.LawBrainItem(**base)


def test_zakljucan_skup_klasa_poverenja():
    assert lb.TRUST_CLASSES == (
        "HUMAN_CONFIRMED_OUTCOME", "LAWYER_VERIFIED_ARTIFACT", "HUMAN_MEMORY_NOTE", "HUMAN_CORRECTION",
        "EXPLICIT_GRAPH_RELATION", "SOURCE_CASE_FACT", "AI_CANDIDATE_LESSON", "AI_WORK_PRODUCT", "UNKNOWN_LEGACY",
    )
    assert not (lb.HUMAN_CLASSES & lb.AI_CLASSES)
    assert lb.UNKNOWN_LEGACY not in lb.HUMAN_CLASSES
    assert lb.SOURCE_CASE_FACT not in lb.HUMAN_CLASSES


@pytest.mark.parametrize("klasa", sorted(lb.AI_CLASSES | {lb.UNKNOWN_LEGACY, lb.SOURCE_CASE_FACT}))
def test_ai_i_nepoznato_nikad_nije_ljudski_provereno(klasa):
    s = _stavka(trust_class=klasa, validity=lb.CURRENT)
    assert s.human_verified is False
    assert s.trusted is False
    assert s.to_dict()["human_verified"] is False


def test_human_verified_se_ne_moze_proslediti():
    with pytest.raises(TypeError):
        lb.LawBrainItem(source_kind="x", source_owner="t", source_id="1", scope=lb.SCOPE_USER,
                        trust_class=lb.AI_WORK_PRODUCT, validity=lb.CURRENT, human_verified=True)


def test_povuceno_ljudsko_znanje_nije_poverljivo():
    s = _stavka(trust_class=lb.HUMAN_MEMORY_NOTE, validity=lb.DEPRECATED)
    assert s.human_verified is True
    assert s.trusted is False


def test_nepoznate_vrednosti_odbijene():
    with pytest.raises(ValueError):
        _stavka(trust_class="VERIFIED")
    with pytest.raises(ValueError):
        _stavka(validity="FRESH")
    with pytest.raises(ValueError):
        _stavka(scope="FIRM")
    with pytest.raises(ValueError):
        _stavka(source_id="")


def test_ljudski_ishod_mora_imati_referencu():
    with pytest.raises(ValueError):
        _stavka(source_kind="outcome", source_owner="outcome_log", trust_class=lb.HUMAN_CONFIRMED_OUTCOME)
    s = _stavka(source_kind="outcome", source_owner="outcome_log", trust_class=lb.HUMAN_CONFIRMED_OUTCOME,
                outcome_ref="O1", validity=lb.CURRENT)
    assert s.to_dict()["outcome_ref"] == "O1"


def test_stabilan_id_i_referenca_na_izvor():
    a = _stavka(excerpt="x")
    b = _stavka(excerpt="drugačiji tekst")
    assert a.id == b.id == "lesson:L1"
    assert a.to_dict()["source_ref"] == {"table": "lessons_learned", "id": "L1"}


def test_izvod_ogranicen_i_jednoredan():
    s = _stavka(excerpt="red1\n\nred2 " + "a" * 2000, title="t" * 500)
    assert "\n" not in s.excerpt
    assert len(s.excerpt) <= lb.EXCERPT_MAX
    assert s.excerpt.endswith("…")
    assert len(s.title) <= 160


def test_validnost_deterministicka_bez_izmisljanja():
    assert lb.validity_from(today=DANAS, has_validity_data=False) == lb.UNKNOWN
    assert lb.validity_from(today=DANAS) == lb.CURRENT
    assert lb.validity_from(today=DANAS, stale=True) == lb.STALE
    assert lb.validity_from(today=DANAS, valid_until="2026-10-09") == lb.STALE
    assert lb.validity_from(today=DANAS, valid_until="2026-10-10") == lb.CURRENT
    assert lb.validity_from(today=DANAS, valid_until="nije-datum", has_validity_data=False) == lb.UNKNOWN
    assert lb.validity_from(today=DANAS, deprecated=True, stale=True) == lb.DEPRECATED


def test_validnost_zahteva_eksplicitan_danas():
    with pytest.raises(TypeError):
        lb.validity_from()


def test_redosled_deterministicki():
    ai = _stavka(source_id="A", trust_class=lb.AI_CANDIDATE_LESSON, validity=lb.CURRENT, updated_at="2026-10-01")
    staro = _stavka(source_id="B", trust_class=lb.HUMAN_MEMORY_NOTE, validity=lb.CURRENT, updated_at="2025-01-01")
    novo = _stavka(source_id="C", trust_class=lb.HUMAN_MEMORY_NOTE, validity=lb.CURRENT, updated_at="2026-01-01")
    zastarelo = _stavka(source_id="D", trust_class=lb.HUMAN_MEMORY_NOTE, validity=lb.STALE, updated_at="2026-09-01")
    ishod = _stavka(source_id="E", source_kind="outcome", source_owner="outcome_log",
                    trust_class=lb.HUMAN_CONFIRMED_OUTCOME, outcome_ref="E", validity=lb.CURRENT)
    ulaz = [ai, staro, zastarelo, novo, ishod]
    ocekivano = ["outcome:E", "lesson:C", "lesson:B", "lesson:D", "lesson:A"]
    assert [x.id for x in lb.order_items(ulaz)] == ocekivano
    assert [x.id for x in lb.order_items(list(reversed(ulaz)))] == ocekivano


def test_to_dict_bez_skrivenih_polja():
    d = _stavka(attrs=(("broj_predmeta", 3),)).to_dict()
    assert set(d) == {"id", "source_kind", "source_owner", "source_ref", "scope", "predmet_id", "title",
                      "excerpt", "trust_class", "human_verified", "validity", "state", "created_at",
                      "updated_at", "lineage", "outcome_ref", "attrs"}
    assert d["attrs"] == {"broj_predmeta": 3}


def test_modul_ne_uvozi_model():
    import inspect
    src = inspect.getsource(lb)
    assert "openai" not in src.lower()
    assert "datetime.now" not in src and "date.today" not in src
