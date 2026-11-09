"""N8 kroz stvarno parsiranje, isporuku i keš pravnog agenta."""

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import main as M


_FIXTURES = Path(__file__).with_name("fixtures")
_ARHIVA = json.loads((_FIXTURES / "beta_n8_natural_9f16_live.json").read_text("utf-8"))
_USLOVNA_ARHIVA = json.loads((_FIXTURES / "beta_n8_conditional_fb4e_live.json").read_text("utf-8"))
PITANJE = _ARHIVA["pitanje"]
USLOVNI_ODGOVOR = {
    "brza_procena_pravna_utemeljenost": "visoka",
    "brza_procena_dokazna_potpunost": "potpuna",
    "pravni_zakljucak": (
        "Sud prebivališta u Novom Sadu ima opštu mesnu nadležnost. "
        "Sud boravišta u Beogradu može biti dodatno nadležan ako okolnosti upućuju na duži boravak."
    ),
    "pravni_osnov": "Član 39 ZPP",
    "potrebne_informacije": "Utvrditi okolnosti očekivanog dužeg boravka.",
    "procesni_koraci": "Pre izbora Beograda proveriti okolnosti koje upućuju na duži boravak.",
}


@pytest.fixture
def tok(monkeypatch):
    clan = "ZAKON: Zakon o parničnom postupku\nČLAN: Član 39\n" + M._lokalni_clan("Zakon o parničnom postupku", "39")
    meta = {
        "confidence": "HIGH", "top_score": 0.8, "top_article": "Član 39",
        "top_law": "Zakon o parničnom postupku",
        "izvori": [{"zakon": "Zakon o parničnom postupku", "clan": "Član 39", "score": 0.8}],
    }
    model = Mock()
    l2 = {}
    monkeypatch.setattr(M, "retrieve_documents", lambda *a, **k: ([clan], meta))
    monkeypatch.setattr(M, "retrieve_sudska_praksa", lambda *a, **k: [])
    monkeypatch.setattr(M, "retrieve_misljenja", lambda *a, **k: [])
    monkeypatch.setattr(M, "_pozovi_openai", model)
    monkeypatch.setattr(M, "_CACHE", {})
    monkeypatch.setattr(M, "_supa_cache_get", l2.get)
    monkeypatch.setattr(M, "_supa_cache_set", l2.__setitem__)
    monkeypatch.delenv("VINDEX_CACHE_BYPASS", raising=False)
    return model, meta, l2


def test_n8_exact_archived_model_response_is_withheld_without_caching(tok):
    model, _, l2 = tok
    raw = _ARHIVA["raw"]
    assert hashlib.sha256(raw.encode()).hexdigest() == "3240d795fd810c0bbfc6133f7f98dea0a1bcec22fc423ac2619fd2c4d4b5553f"
    model.return_value = raw
    rezultat = M.ask_agent(PITANJE)
    assert rezultat.get("blocked") is True, rezultat["data"]
    assert "Nema dodatnih rizika" not in rezultat["data"]
    assert not M._CACHE and not l2
    assert model.call_count == 1


def test_n8_exact_conditional_live_response_is_withheld_without_caching(tok):
    model, _, l2 = tok
    raw = _USLOVNA_ARHIVA["raw"]
    assert hashlib.sha256(raw.encode()).hexdigest() == "bfe06f29f5f433a17bb88db765a6a5038300c15bc85079dcfe790cc270cfac91"
    model.return_value = raw
    rezultat = M.ask_agent(_USLOVNA_ARHIVA["pitanje"])
    assert rezultat.get("blocked") and not M._CACHE and not l2


@pytest.mark.parametrize(("polje", "tvrdnja"), [
    ("procesni_koraci", "Podneti tužbu u Beogradu."),
    ("brza_procena_koraci", [{"akcija": "Podnesite tužbu u Beogradu.", "zasto": "Tamo je boravište."}]),
    ("brza_procena_obrazlozenje", "Sve potrebne okolnosti su utvrđene."),
    ("brza_procena_rizik", "Nema dodatnih rizika u postupku zbog jasne nadležnosti."),
    ("rizici_i_izuzeci", "Nema specifičnih rizika ili izuzetaka u vezi sa određivanjem mesne nadležnosti."),
    ("pravni_zakljucak", "Sud u Beogradu nije nadležan jer je prebivalište u Novom Sadu."),
    ("pravni_zakljucak", "Nadležan je i sud u Beogradu zbog boravišta."),
    ("kada_ne_vazi", "Prebivalište isključuje nadležnost suda boravišta."),
    ("potrebne_informacije", "Nije predmet pitanja."),
    ("pravni_osnov", "Sud boravišta je mesno nadležan po članu 39 ZOO."),
    ("pravni_zakljucak", "Sud boravišta je nadležan ako tuženi tamo živi najmanje 90 dana."),
    ("pravni_zakljucak", "Sud boravišta je nadležan ako tuženi tamo živi najmanje tri meseca."),
    ("pravni_zakljucak", "Sud boravišta je nadležan ako duži boravak traje 90 dana."),
    ("pravni_zakljucak", "Sud boravišta je nadležan ako tuženi tamo boravi duže od 90 dana."),
    ("procesni_koraci", "Ako tužilac odluči da proveri duži boravak, podneti tužbu u Beogradu."),
    ("pravni_zakljucak", "Sud boravišta može biti nadležan samo na osnovu boravišta."),
    ("pravni_zakljucak", "Jedini mesno nadležan sud je sud prebivališta."),
    ("procesni_koraci", "Nije utvrđeno da li je nadležan sud u Beogradu, ipak podneti tužbu u Beogradu."),
    ("procesni_koraci", "Tužbu predajte sudu u Beogradu."),
    ("brza_procena_rizik", "Rizik od pogrešnog izbora suda ne postoji."),
    ("pravni_zakljucak", "Sud boravišta u Beogradu je nadležan čak i ako se ne može pretpostaviti duži boravak tuženog."),
    ("pravni_zakljucak", "Sud boravišta u Beogradu nije nadležan ako se ne utvrdi duži boravak tuženog."),
    ("rizici_i_izuzeci", "Ako se ne dokaže duži boravak, sud u Beogradu neće biti nadležan."),
    ("procesni_koraci", "Podneti poseban zahtev za utvrđivanje mesne nadležnosti."),
    ("procesni_koraci", "Podneti poseban predlog za utvrđivanje mesne nadležnosti."),
    ("procesni_koraci", "Podneti zahtev da sud prethodno utvrdi svoju mesnu nadležnost."),
    ("brza_procena_koraci", [{"akcija": "Podnesite zahtev za utvrđivanje mesne nadležnosti."}]),
])
def test_n8_each_visible_contradiction_is_withheld(tok, polje, tvrdnja):
    model, _, l2 = tok
    model.return_value = json.dumps({**USLOVNI_ODGOVOR, "brza_procena_dokazna_potpunost": "delimicna", polje: tvrdnja})
    rezultat = M.ask_agent(PITANJE)
    assert rezultat.get("blocked") is True, rezultat["data"]
    assert not M._CACHE and not l2


@pytest.mark.parametrize("putanja", ["HIGH", "MEDIUM", "downgrade"])
def test_n8_delivered_answer_is_consistent_in_both_cache_layers(tok, putanja):
    model, meta, l2 = tok
    if putanja == "MEDIUM":
        meta.update(confidence="MEDIUM", top_score=0.6)
    raw = json.dumps(USLOVNI_ODGOVOR)
    model.side_effect = ["nevažeći JSON", raw] if putanja == "downgrade" else [raw]
    cold = M.ask_agent(PITANJE)
    l1 = M.ask_agent(PITANJE)
    assert l2
    M._CACHE.clear()
    l2_hit = M.ask_agent(PITANJE)
    assert not cold.get("blocked")
    assert "Pravna utemeljenost: VISOKA" in cold["data"]
    assert "Dokazna potpunost: DELIMIČNA" in cold["data"]
    assert "Novom Sadu" in cold["data"] and "duži boravak" in cold["data"]
    assert l1 == l2_hit == {**cold, "from_cache": True}
    assert model.call_count == (2 if putanja == "downgrade" else 1)


@pytest.mark.parametrize("dodatak", [
    "Pretpostavimo da će tuženi duže boraviti u Beogradu.",
    "Tuženi ne boravi duže vreme u Beogradu.",
    "Dužeg boravka nema.",
    "Stranke osporavaju da li će tuženi duže boraviti u Beogradu.",
    "Tužilac već duže boravi u Beogradu.",
    "Tuženi već duže boravi u Novom Sadu.",
    "Tuženi već duže boravi u Beogradu. Protivna strana osporava duži boravak.",
    "Tužilac tvrdi da tuženi u Beogradu boravi duže vreme, ali tuženi to negira.",
])
def test_n8_hypothetical_negated_or_disputed_stay_cannot_establish_additional_venue(tok, dodatak):
    model, _, l2 = tok
    model.return_value = json.dumps({**USLOVNI_ODGOVOR, "pravni_zakljucak": "Oba suda su mesno nadležna."})
    odgovor = M.ask_agent(f"{PITANJE} {dodatak}")
    assert odgovor.get("blocked") is True
    assert not l2


@pytest.mark.parametrize("okolnosti", [
    "Tuženi već duže boravi u Beogradu, gde radi i živi sa porodicom.",
    "Tuženi duže boravi u Beogradu i to nije sporno.",
    "Tuženi će u Beogradu boraviti i naredne dve godine; to potvrđuje ugovor o radu.",
])
def test_n8_supported_stay_keeps_supported_conclusion(tok, okolnosti):
    model, _, _ = tok
    model.return_value = json.dumps({
        **USLOVNI_ODGOVOR, "pravni_zakljucak": "Oba suda su mesno nadležna prema članu 39 ZPP.",
        "potrebne_informacije": "", "procesni_koraci": "",
    })
    odgovor = M.ask_agent(f"{PITANJE} {okolnosti}")
    assert not odgovor.get("blocked")
    assert "Oba suda su mesno nadležna" in odgovor["data"]
    assert "Dokazna potpunost: POTPUNA" in odgovor["data"]


@pytest.mark.parametrize("zakljucak", [
    "Sud u Beogradu nije nadležan jer prebivalište u Novom Sadu ima prednost.",
    "Sud u Beogradu nije mesno nadležan.",
    "Sud boravišta u Beogradu nadležan je tek kada duži boravak traje 90 dana.",
])
def test_n8_supported_stay_does_not_authorize_wrong_rule(tok, zakljucak):
    model, _, l2 = tok
    model.return_value = json.dumps({**USLOVNI_ODGOVOR, "pravni_zakljucak": zakljucak})
    rezultat = M.ask_agent(PITANJE + " Tuženi već duže boravi u Beogradu, gde radi i živi sa porodicom.")
    assert rezultat.get("blocked") and not l2


def test_n8_explicit_negative_condition_is_not_an_unconditional_exclusion(tok):
    model, _, _ = tok
    uslov = "Sud boravišta u Beogradu nije nadležan po tom osnovu ako okolnosti ne upućuju na duži boravak."
    model.return_value = json.dumps({**USLOVNI_ODGOVOR, "kada_ne_vazi": uslov})
    odgovor = M.ask_agent(PITANJE)
    assert not odgovor.get("blocked")
    assert uslov in odgovor["data"]


def test_n8_neutral_checks_and_questions_are_not_venue_claims(tok):
    model, _, _ = tok
    provera = "Proveriti okolnosti dužeg boravka u Beogradu radi odluke o mesnoj nadležnosti."
    pitanje = "Da li je sud u Beogradu nadležan na osnovu okolnosti dužeg boravka?"
    model.return_value = json.dumps({**USLOVNI_ODGOVOR, "procesni_koraci": provera, "kljucno_pitanje": pitanje})
    odgovor = M.ask_agent(PITANJE)
    assert not odgovor.get("blocked")
    assert provera in odgovor["data"] and pitanje in odgovor["data"]


@pytest.mark.parametrize("koraci", [
    "Ne podnositi poseban zahtev za utvrđivanje mesne nadležnosti. Proveriti okolnosti dužeg boravka.",
    "Ne treba da podnesete poseban zahtev za utvrđivanje mesne nadležnosti.",
    "Nije neophodno podneti poseban zahtev za utvrđivanje mesne nadležnosti.",
    "Ako okolnosti upućuju na duži boravak, u tužbi obrazložiti osnov mesne nadležnosti suda boravišta.",
])
def test_n8_ordinary_procedural_advice_is_not_a_standalone_venue_request(tok, koraci):
    model, _, _ = tok
    model.return_value = json.dumps({**USLOVNI_ODGOVOR, "procesni_koraci": koraci})
    rezultat = M.ask_agent(PITANJE)
    assert not rezultat.get("blocked")
    assert koraci in rezultat["data"]


@pytest.mark.parametrize("utvrdjen", [False, True])
def test_n8_prompt_overrides_generic_parnica_steps_only_within_residence_venue(tok, utvrdjen):
    model, _, _ = tok
    model.return_value = json.dumps(USLOVNI_ODGOVOR)
    pitanje = PITANJE
    if utvrdjen:
        pitanje += " Tuženi već duže boravi u Beogradu, gde radi i živi sa porodicom."
    assert not M.ask_agent(pitanje).get("blocked")
    prompt = model.call_args.args[0]
    assert "Ne predlaži takav zahtev ni drugi neproveren procesni korak" in prompt
    assert ("N8 — NEUTVRĐENE OKOLNOSTI" in prompt) is not utvrdjen
    if not utvrdjen:
        assert "Dodatna nadležnost suda boravišta ostaje neutvrđena" in prompt
        assert "proveru okolnosti očekivanog dužeg boravka pre izbora suda" in prompt


def test_n8_retrieved_wrong_law_cannot_be_a_basis_for_article_39_venue(tok, monkeypatch):
    model, meta, l2 = tok
    docs, _ = M.retrieve_documents(PITANJE)
    zoo = "ZAKON: Zakon o obligacionim odnosima\nČLAN: Član 39\n" + M._lokalni_clan("Zakon o obligacionim odnosima", "39")
    monkeypatch.setattr(M, "retrieve_documents", lambda *a, **k: ([*docs, zoo], meta))
    model.return_value = json.dumps({**USLOVNI_ODGOVOR, "pravni_osnov": "Član 39 ZOO"})
    rezultat = M.ask_agent(PITANJE)
    assert rezultat.get("blocked") and not l2


@pytest.mark.parametrize("zakljucak", [
    "Sud boravišta može biti dodatno nadležan kada okolnosti upućuju na to da će tuženi tamo boraviti duže.",
    "Sud boravišta može biti dodatno nadležan samo uz utvrđene okolnosti dužeg boravka.",
])
def test_n8_alternative_conditional_wording_is_delivered(tok, zakljucak):
    model, _, _ = tok
    model.return_value = json.dumps({**USLOVNI_ODGOVOR, "pravni_zakljucak": zakljucak})
    rezultat = M.ask_agent(PITANJE)
    assert not rezultat.get("blocked")
    assert zakljucak in rezultat["data"]


@pytest.mark.parametrize(("pitanje", "suffix"), [
    (PITANJE, "|n8-nadleznost-8"),
    ("Dva privredna društva su u sporu. Koji je sud nadležan?", "|n8-nadleznost-6"),
    ("Koji je rok zastarelosti po ZOO?", ""),
])
def test_only_residence_venue_cache_namespace_changes(pitanje, suffix):
    expected = hashlib.md5(
        f"{M._CACHE_VERZIJA}{suffix}|{M._normalizuj_za_cache(pitanje)}".encode(), usedforsecurity=False,
    ).hexdigest()
    assert M._cache_kljuc(pitanje) == expected


def test_n8_private_case_context_is_never_cached(tok):
    model, _, l2 = tok
    model.return_value = json.dumps(USLOVNI_ODGOVOR)
    pitanje = PITANJE + "\n\nKONTEKST PREDMETA:\nSintetički privatni predmet."
    assert not M.ask_agent(pitanje).get("blocked")
    assert not M.ask_agent(pitanje).get("from_cache")
    assert not M._CACHE and not l2
    assert model.call_count == 2
