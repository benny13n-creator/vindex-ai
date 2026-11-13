"""MIR-03: author, proposition, and cited source must agree before staging."""

import hashlib
import json
from pathlib import Path

import pytest

from shared import procesno_stanje as ps
from shared.mir03_source_fidelity import NepouzdanIzvor, proveri
from tests import mir001_golden_case as gc


RAW = Path(__file__).with_name("fixtures") / "beta_mir03_adviser_9f16_live.json"
RAW_SHA256 = "a7f5f059ae10cc6a643325f0251ad2e2db53c0e51d9c65641199165d36183ea7"


@pytest.fixture
def spis():
    dokumenti = [
        {"id": f"sinteticki-{dok['oznaka']}", "oznaka": dok["oznaka"], "tekst": gc.tekst(dok),
         "predmet_id": "sinteticki-spis", "user_id": "sinteticki-vlasnik"}
        for dok in gc.DOKUMENTI
    ]
    izvori = {
        dok["oznaka"]: {"tekst": dok["tekst"], "vrsta": ps.vrsta_dokumenta(dok["tekst"])}
        for dok in dokumenti
    }
    stanje = ps.utvrdi(dokumenti, predmet_id="sinteticki-spis", user_id="sinteticki-vlasnik")
    return izvori, stanje


def test_n1_exact_archived_provider_response_is_rejected(spis):
    raw = RAW.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RAW_SHA256
    odgovor = json.loads(raw)
    tekst = "\n".join([odgovor["tekst_za_sud"], *odgovor["napomene_za_advokata"]])
    assert "tvrdnjom tuženog da nosaci solarnih panela nisu oštetili hidroizolaciju krova" in tekst
    with pytest.raises(NepouzdanIzvor):
        proveri(tekst, *spis)


@pytest.mark.parametrize("tekst", [
    pytest.param("Tuženi u DOK-03 tvrdi da hidroizolacija krova nije oštećena nosačima solarnih panela.",
                 id="N2-passive-reordered"),
    pytest.param("Hidroizolaciju krova nisu oštetili nosači solarnih panela, tvrdio je tuženi.",
                 id="N2-postposed-speaker"),
    pytest.param("U DOK-05 sud je utvrdio da nosači solarnih panela nisu oštetili hidroizolaciju krova.",
                 id="N3-expert-is-not-court"),
    pytest.param("Tužilac u DOK-02 tvrdi da su solarni paneli uzrok prokišnjavanja.",
                 id="N4-defendants-claim-is-not-plaintiffs"),
    pytest.param("Tuženi u DOK-03 (DOK-02) tvrdi da su solarni paneli uzrok prokišnjavanja.",
                 id="N4-extra-valid-label-does-not-repair-explicit-wrong-source"),
    pytest.param("Tuženi u DOK-02 poriče da su solarni paneli uzrok prokišnjavanja.",
                 id="opposing-speech-act-cannot-borrow-matching-words"),
    pytest.param("Tuženi u DOK-02 ne tvrdi da su solarni paneli uzrok prokišnjavanja.",
                 id="negated-speech-act-cannot-borrow-matching-words"),
    pytest.param("Tužilac u DOK-03 tvrdi da je hidroizolaciju zamenio 20.04.2026. godine.",
                 id="N5-real-label-invented-attribution"),
    pytest.param("Hidroizolacija krova zamenjena je 20.04.2026. godine (DOK-03).",
                 id="N5-real-label-invented-fact"),
    pytest.param("U vezi sa DOK-03, hidroizolacija je zamenjena 20.04.2026. godine.",
                 id="N5-source-introduction-does-not-exempt-asserted-fact"),
    pytest.param("Veštak u DOK-05 navodi da je uzrok prokišnjavanja neodgovarajuće izvedena hidroizolacija; "
                 "tuženi u DOK-03 tvrdi da nosači solarnih panela nisu oštetili hidroizolaciju krova.",
                 id="N7-valid-clause-cannot-cover-unsupported-clause"),
    pytest.param("Veštak u DOK-05 navodi da je uzrok prokišnjavanja neodgovarajuće izvedena hidroizolacija; "
                 "veštak u DOK-05 navodi da su nosači solarnih panela oštetili hidroizolaciju krova.",
                 id="N7-shared-source-does-not-cover-conflicting-clause"),
    pytest.param("Veštak u nalazu DOK-05 navodi da je uzrok prokišnjavanja neodgovarajuće izvedena hidroizolacija, "
                 "a hidroizolacija je zamenjena 20.04.2026. godine.",
                 id="N7-uncited-assertion-beside-supported-claim"),
    pytest.param("Veštak u nalazu DOK-05 navodi da je uzrok prokišnjavanja neodgovarajuće izvedena hidroizolacija. "
                 "Hidroizolacija je zamenjena 20.04.2026. godine.",
                 id="N7-separate-sentence-in-same-paragraph"),
    pytest.param("Veštak u nalazu DOK-05 navodi da je uzrok prokišnjavanja neodgovarajuće izvedena hidroizolacija. "
                 "Poštovani sude. Hidroizolacija je zamenjena 20.04.2026. godine.",
                 id="N7-neutral-sentence-does-not-reset-paragraph-evidence"),
    pytest.param("Tuženi u DOK-02 tvrdi da je ugradnja solarnih panela posledica prokišnjavanja.",
                 id="reversed-cause-and-effect"),
    pytest.param("Veštak u DOK-05 navodi da su nosači solarnih panela oštetili hidroizolaciju krova.",
                 id="polarity-flipped"),
    pytest.param("Ako sud prihvati tvrdnju tuženog iz DOK-03 da nosači solarnih panela nisu oštetili "
                 "hidroizolaciju krova, tužilac predlaže dopunu veštačenja.",
                 id="conditional-does-not-erase-attribution"),
    pytest.param("Tuženi tvrdi da nosači solarnih panela nisu oštetili hidroizolaciju krova.",
                 id="no-source-label-is-not-a-bypass"),
    pytest.param("Tuženi je rekao da nosači solarnih panela nisu oštetili hidroizolaciju krova.",
                 id="alternate-attribution-verb-is-not-a-bypass"),
    pytest.param("Predlažemo da sud uzme u obzir da je hidroizolacija zamenjena 20.04.2026. godine (DOK-03).",
                 id="proposal-does-not-exempt-embedded-factual-premise"),
])
def test_unsupported_attributions_are_rejected(spis, tekst):
    with pytest.raises(NepouzdanIzvor):
        proveri(tekst, *spis)


@pytest.mark.parametrize(("tekst", "oznake"), [
    pytest.param("Veštak u nalazu DOK-05 navodi da je uzrok prokišnjavanja neodgovarajuće izvedena hidroizolacija.",
                 {"DOK-05"}, id="P1-expert-causal-opinion"),
    pytest.param("Tuženi u DOK-02 tvrdi da su solarni paneli uzrok prokišnjavanja.",
                 {"DOK-02"}, id="P2-defendants-causal-position"),
    pytest.param("Tuženi u DOK-06 osporava nalaz veštaka.",
                 {"DOK-06"}, id="P3-defendant-disputes-expert"),
    pytest.param("Tužilac u DOK-03 tvrdi da su solarni paneli postavljeni nakon prokišnjavanja.",
                 {"DOK-03"}, id="P4-plaintiffs-chronology"),
    pytest.param("Prema nalazu veštaka (DOK-05): „Nosači solarnih panela nisu oštetili hidroizolaciju krova.“",
                 {"DOK-05"}, id="P5-literal-quote-keeps-speaker"),
    pytest.param("Tužilac osporava zaključak veštaka iz DOK-05 da nosači solarnih panela nisu oštetili hidroizolaciju krova.",
                 {"DOK-05"}, id="P5-argument-keeps-embedded-speaker"),
    pytest.param("Prema nalazu veštaka DOK-05, hidroizolacija krova nije oštećena nosačima solarnih panela.",
                 {"DOK-05"}, id="P6-accurate-active-to-passive-paraphrase"),
    pytest.param("Тужени у ДОК-06 оспорава налаз вештака.",
                 {"DOK-06"}, id="Cyrillic"),
    pytest.param("Тужени у ДОК‑006 оспорава налаз вештака.",
                 {"DOK-06"}, id="Cyrillic-nonbreaking-hyphen-and-zero-padding"),
    pytest.param("Tuženi u DOK 00006 osporava nalaz veštaka.",
                 {"DOK-06"}, id="space-and-zero-padding-in-source-label"),
    pytest.param("Tužilac predlaže da sud zatraži dopunu veštačenja.",
                 set(), id="P7-proposed-action"),
    pytest.param("Ako se utvrdi da su solarni paneli izazvali prokišnjavanje, tužilac može predložiti dopunu veštačenja.",
                 set(), id="P7-hypothetical-fact"),
])
def test_grounded_attributions_and_nonfactual_arguments_are_allowed(spis, tekst, oznake):
    assert proveri(tekst, *spis) == oznake


def test_valid_clause_cannot_borrow_support_from_unread_source(spis):
    izvori, stanje = spis
    del izvori["DOK-05"]
    with pytest.raises(NepouzdanIzvor):
        proveri("Veštak u DOK-05 navodi da nosači solarnih panela nisu oštetili hidroizolaciju krova.",
                izvori, stanje)


def test_review_request_does_not_cite_unread_documents_as_evidence(spis):
    assert proveri("Pogledaj DOK-82 i DOK-83.", *spis) == set()
    with pytest.raises(NepouzdanIzvor):
        proveri("Pogledaj DOK-82 i DOK-83 jer DOK-82 potvrđuje da je nalaz dostavljen.", *spis)
    with pytest.raises(NepouzdanIzvor):
        proveri("Pogledaj DOK-82 i DOK-83, jer je hidroizolacija zamenjena 20.04.2026. godine.", *spis)
    with pytest.raises(NepouzdanIzvor):
        proveri("Pogledaj DOK-82 i DOK-83. Hidroizolacija je zamenjena 20.04.2026. godine.", *spis)


def test_ps_reference_cannot_borrow_another_utterance_from_the_same_document(spis):
    _, stanje = spis
    izjave = [red for red in stanje["dogadjaji"] if red["oznaka"] == "DOK-06"]
    pogresan = next(red for red in izjave if "osporava nalaz" in red["izvod"])
    tacan = next(red for red in izjave if "uvid u gradjevinski dnevnik" in red["izvod"])
    tvrdnja = "Tuženi tvrdi da veštak nije izvršio uvid u građevinski dnevnik"
    assert proveri(f"{tvrdnja} [[{tacan['id']}]].", *spis) == {"DOK-06"}
    with pytest.raises(NepouzdanIzvor):
        proveri(f"{tvrdnja} [[{pogresan['id']}]].", *spis)


def test_standalone_server_excerpt_returns_its_source_for_the_atomic_fence(spis):
    _, stanje = spis
    dogadjaj = next(red for red in stanje["dogadjaji"] if red["oznaka"] == "DOK-03")
    assert proveri(f"[[{dogadjaj['id']}]].", *spis) == {"DOK-03"}


def test_source_fidelity_does_not_depend_on_golden_case_words_or_labels():
    tekst = "NALAZ I MIŠLJENJE VEŠTAKA\nMerenje je izvršeno u laboratoriji 17.02.2026. godine."
    izvori = {"DOK-81": {"tekst": tekst, "vrsta": ps.vrsta_dokumenta(tekst)}}
    assert proveri(
        "Prema nalazu veštaka (DOK-81): „Merenje je izvršeno u laboratoriji 17.02.2026. godine.“", izvori,
    ) == {"DOK-81"}
    with pytest.raises(NepouzdanIzvor):
        proveri("U DOK-81 sud je utvrdio da je merenje izvršeno u laboratoriji 17.02.2026. godine.", izvori)


def test_party_record_cannot_support_a_court_decision(spis):
    izvori, stanje = spis
    izvod = "Sud prihvata predlog za dopunu vestacenja."
    izjava = "Sud je već prihvatio predlog za dopunu veštačenja"
    tekst = f"PODNESAK TUZIOCA\n{izvod}"
    izvori["DOK-83"] = {"tekst": tekst, "vrsta": ps.vrsta_dokumenta(tekst)}
    assert proveri(f"{izjava} (DOK-07).", izvori, stanje) == {"DOK-07"}
    with pytest.raises(NepouzdanIzvor):
        proveri(f"{izjava} (DOK-83).", izvori, stanje)


@pytest.mark.parametrize("uvod", ["Tužilac citira željeni ishod:", "Mogući ishod ako sud usvoji predlog:"])
def test_quoted_or_hypothetical_decision_is_not_a_court_act(spis, uvod):
    izvori, stanje = spis
    tekst = f"ZAPISNIK SA ROČIŠTA\n{uvod}\nSud prihvata predlog za dopunu vestacenja."
    izvori["DOK-83"] = {"tekst": tekst, "vrsta": ps.vrsta_dokumenta(tekst)}
    with pytest.raises(NepouzdanIzvor):
        proveri("Sud je već prihvatio predlog za dopunu veštačenja (DOK-83).", izvori, stanje)


def test_court_record_preserves_partys_attribution_in_body():
    tekst = "ZAPISNIK SA ROČIŠTA\nTužilac tvrdi da guma nije zamenjena."
    izvori = {"DOK-81": {"tekst": tekst, "vrsta": ps.vrsta_dokumenta(tekst, "court_decision")}}
    assert proveri("Tužilac u DOK-81 tvrdi da guma nije zamenjena.", izvori) == {"DOK-81"}
    with pytest.raises(NepouzdanIzvor):
        proveri("Sud je u DOK-81 utvrdio da guma nije zamenjena.", izvori)


def test_court_title_without_attestation_does_not_prove_court_authority():
    tekst = "ZAPISNIK SA ROČIŠTA\nSud konstatuje da guma nije zamenjena."
    izvori = {"DOK-81": {"tekst": tekst, "vrsta": ps.vrsta_dokumenta(tekst)}}
    with pytest.raises(NepouzdanIzvor):
        proveri("Sud u DOK-81 konstatuje da guma nije zamenjena.", izvori)


@pytest.mark.parametrize("telo", [
    "Citiram iskaz svedoka:\n„Guma nije zamenjena.“",
    "Tuženi je rekao:\nGuma nije zamenjena.",
    "Ako je zapis autentičan, moguće je sledeće:\nGuma nije zamenjena.",
])
def test_report_title_does_not_make_a_nested_quote_or_hypothesis_an_expert_assertion(telo):
    tekst = f"NALAZ I MIŠLJENJE VEŠTAKA\n{telo}"
    izvori = {"DOK-81": {"tekst": tekst, "vrsta": ps.vrsta_dokumenta(tekst)}}
    with pytest.raises(NepouzdanIzvor):
        proveri("Veštak u DOK-81 navodi da guma nije zamenjena.", izvori)
