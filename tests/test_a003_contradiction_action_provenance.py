# -*- coding: utf-8 -*-
"""IMPL TASK A003 — ADITIVNA PROVENIJENCIJA DOKUMENTA U `case_actions.dokaz`.

A002 razrešava `DOK-NN` -> `predmet_dokumenti.id` i upisuje `dokument_id_1`/
`dokument_id_2` u samu kontradikciju. Do ovog taska tu vrednost nije čitao
NIKO — dokazano prebrojavanjem u A003 Decision Gate izveštaju.

Ovaj task je prenosi kroz Rule 3 (`RAZRESITI_KONTRADIKCIJU`) u
`case_actions.dokaz`, odakle je već čita postojeći potrošač
`routers/workspace.py::_normalize_case_action`.

Nedodirljivo, i ovde eksplicitno testirano da je ostalo netaknuto:
`lokacija_1`/`lokacija_2`, `izvor_dokumenti`, `dedupe_key` i identitet
kontradikcije (`shared/contradiction_identity.py`).
"""
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routers.case_dna as cd  # noqa: E402
from shared.contradiction_identity import contradiction_dedupe_key  # noqa: E402

UUID_A = "aaaaaaaa-1111-1111-1111-111111111111"
UUID_B = "bbbbbbbb-2222-2222-2222-222222222222"


# ═══════════════════════════════════════════════════════════════════════════
# Harness — isti obrazac koji koriste test_omega_sprint003 i test_a002
# ═══════════════════════════════════════════════════════════════════════════

def _make_target_supa(case_dna):
    """Podržava tačno lanac čitanja koji `_compute_target_actions` izdaje."""
    def _predmeti_table():
        t = MagicMock()
        res = MagicMock()
        res.data = {"case_dna": dict(case_dna or {}), "tip": "parnicno"}
        t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = res
        return t

    def _empty_table():
        t = MagicMock()
        chain = MagicMock()
        chain.execute.return_value = MagicMock(data=[])
        t.select.return_value.eq.return_value = chain
        t.select.return_value.eq.return_value.is_.return_value = chain
        t.select.return_value.eq.return_value.order.return_value = chain
        return t

    def _table(name):
        if name == "predmeti":
            return _predmeti_table()
        # A015: `_compute_target_actions` sada prvo pita ima li predmet V2
        # kontradikcije. Prazan odgovor znaci „nema V2" -> legacy Rule 3 se
        # izvrsava nepromenjen, sto je bas ono sto ovaj fajl i meri.
        if name in ("predmet_dokazi", "predmet_dokumenti", "rocista", "predmet_issues"):
            return _empty_table()
        raise AssertionError(f"neočekivana tabela {name}")

    supa = MagicMock()
    supa.table.side_effect = _table
    return supa


async def _rule3(kontradikcije):
    """STVARNI `_compute_target_actions`; lažira se isključivo Supabase."""
    from services.case_evolution import _compute_target_actions
    supa = _make_target_supa({"kontradikcije": kontradikcije})
    with patch("services.case_evolution._get_supa", return_value=supa):
        actions = await _compute_target_actions("pred-a003")
    return [a for a in actions if a["tip"] == "RAZRESITI_KONTRADIKCIJU"]


def _kontr(id1, id2, lok1="DOK-01 str.1", lok2="DOK-03 str.2", opis="Rešenje se kosi sa beleškom."):
    k = {"opis": opis, "lokacija_1": lok1, "lokacija_2": lok2, "tezina": "kriticna"}
    k["dokument_id_1"] = id1
    k["dokument_id_2"] = id2
    return k


# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO MATRIX — §5 mandata
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case1_dva_razlicita_dokumenta():
    a = (await _rule3([_kontr(UUID_A, UUID_B)]))[0]
    assert a["dokaz"]["dokument_id_1"] == UUID_A
    assert a["dokaz"]["dokument_id_2"] == UUID_B


@pytest.mark.asyncio
async def test_case2_intra_dokumentna_kontradikcija_nije_duplikat():
    """26% stvarnih kontradikcija je unutar JEDNOG dokumenta (dva iskaza).
    Jednaki ID-jevi su VALIDNI i ne smeju biti deduplicirani ni sažeti."""
    a = (await _rule3([_kontr(UUID_A, UUID_A,
                              lok1="DOK-02 Snežana Pavlović",
                              lok2="DOK-02 Miloš Đurić")]))[0]
    assert a["dokaz"]["dokument_id_1"] == UUID_A
    assert a["dokaz"]["dokument_id_2"] == UUID_A


@pytest.mark.asyncio
async def test_case3_prva_strana_nerazresena():
    a = (await _rule3([_kontr(None, UUID_B)]))[0]
    assert a["dokaz"]["dokument_id_1"] is None
    assert a["dokaz"]["dokument_id_2"] == UUID_B
    assert "dokument_id_1" in a["dokaz"]


@pytest.mark.asyncio
async def test_case4_druga_strana_nerazresena():
    a = (await _rule3([_kontr(UUID_A, None, lok2="Zakon o radu cl. 179")]))[0]
    assert a["dokaz"]["dokument_id_1"] == UUID_A
    assert a["dokaz"]["dokument_id_2"] is None
    assert "dokument_id_2" in a["dokaz"]


@pytest.mark.asyncio
async def test_case5_obe_strane_nerazresene_fail_closed():
    a = (await _rule3([_kontr(None, None, lok1="N/A", lok2="N/A")]))[0]
    assert a["dokaz"]["dokument_id_1"] is None
    assert a["dokaz"]["dokument_id_2"] is None


@pytest.mark.asyncio
async def test_case6_uparenost_lokacije_i_identiteta():
    """Zamena strana je korupcija provenijencije. Test mora pasti ako
    `lokacija_1` dobije `dokument_id_2` — zato tvrdi UPARENOST, ne postojanje."""
    k = _kontr(UUID_A, UUID_B, lok1="DOK-01 str.1", lok2="DOK-03 str.2")
    d = (await _rule3([k]))[0]["dokaz"]
    par = {(d["lokacija_1"], d["dokument_id_1"]), (d["lokacija_2"], d["dokument_id_2"])}
    assert par == {("DOK-01 str.1", UUID_A), ("DOK-03 str.2", UUID_B)}
    # Kontrola: obrnuto uparivanje MORA biti različito, inače test ne bi hvatao zamenu.
    assert par != {("DOK-01 str.1", UUID_B), ("DOK-03 str.2", UUID_A)}


# ═══════════════════════════════════════════════════════════════════════════
# FAIL-CLOSED I PRISUSTVO KLJUČEVA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_legacy_kontradikcija_bez_kljuceva_daje_none_a_ne_gresku():
    """Svih 19 kontradikcija u produkciji je ekstrahovano PRE A002 i nema ove
    ključeve. `None` je ispravan ishod; KeyError bi oborio ceo refresh akcija."""
    k = {"opis": "Stara kontradikcija.", "lokacija_1": "DOK-01", "lokacija_2": "DOK-02",
         "tezina": "vazna"}
    assert "dokument_id_1" not in k
    a = (await _rule3([k]))[0]
    assert a["dokaz"]["dokument_id_1"] is None
    assert a["dokaz"]["dokument_id_2"] is None


@pytest.mark.asyncio
async def test_kljucevi_uvek_postoje_u_svakoj_akciji():
    """Izostavljen ključ znači „ova verzija ne podržava provenijenciju",
    `None` znači „nije razrešeno". Ta dva se ne smeju mešati."""
    kontr = [_kontr(UUID_A, UUID_B), _kontr(None, None, opis="Druga."),
             _kontr(UUID_A, UUID_A, opis="Treća.")]
    for a in await _rule3(kontr):
        assert "dokument_id_1" in a["dokaz"]
        assert "dokument_id_2" in a["dokaz"]


@pytest.mark.asyncio
async def test_nema_pogadjanja_iz_lokacije():
    """Kad A002 nije razrešio, Rule 3 ne sme sam da parsira `DOK-NN`."""
    a = (await _rule3([_kontr(None, None, lok1="DOK-01 str.1", lok2="DOK-03 str.2")]))[0]
    assert a["dokaz"]["dokument_id_1"] is None
    assert a["dokaz"]["dokument_id_2"] is None
    assert "DOK-" not in str(a["dokaz"]["dokument_id_1"])


# ═══════════════════════════════════════════════════════════════════════════
# NEPROMENJENO PONAŠANJE — dokaz aditivnosti
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_izvor_dokumenti_ostaje_prikazni_tekst():
    """`izvor_dokumenti` se NE prenamenjuje u UUID-ove — postojeći invarijant
    `assert a["izvor_dokumenti"]` (test_omega_sprint003:359) mora ostati važeći
    i za kontradikciju kojoj su obe strane nerazrešene."""
    a = (await _rule3([_kontr(None, None, lok1="DOK-01 str.1", lok2="DOK-03 str.2")]))[0]
    assert a["izvor_dokumenti"] == ["DOK-01 str.1", "DOK-03 str.2"]


@pytest.mark.asyncio
async def test_dedupe_key_i_identitet_netaknuti():
    """Dodavanje provenijencije ne sme pomeriti identitet kontradikcije."""
    k_bez = {"opis": "X", "lokacija_1": "DOK-01 str.1", "lokacija_2": "DOK-03 str.2",
             "tezina": "kriticna"}
    k_sa = dict(k_bez, dokument_id_1=UUID_A, dokument_id_2=UUID_B)
    assert contradiction_dedupe_key(k_bez) == contradiction_dedupe_key(k_sa)
    a_bez = (await _rule3([k_bez]))[0]
    a_sa = (await _rule3([k_sa]))[0]
    assert a_bez["dedupe_key"] == a_sa["dedupe_key"]


@pytest.mark.asyncio
async def test_postojeca_dokaz_polja_nepromenjena():
    a = (await _rule3([_kontr(UUID_A, UUID_B)]))[0]
    d = a["dokaz"]
    assert d["opis"] == "Rešenje se kosi sa beleškom."
    assert d["lokacija_1"] == "DOK-01 str.1"
    assert d["lokacija_2"] == "DOK-03 str.2"
    assert d["tezina"] == "kriticna"
    assert set(d) == {"opis", "lokacija_1", "lokacija_2", "tezina",
                      "dokument_id_1", "dokument_id_2"}


# ═══════════════════════════════════════════════════════════════════════════
# END-TO-END — A002 producent → Rule 3 → case_actions.dokaz → workspace potrošač
# ═══════════════════════════════════════════════════════════════════════════

async def _izvuci_genome(docs, genome):
    """STVARNI `_extract_genome` (uključujući A002 blok); lažira se samo GPT odgovor."""
    odgovor = MagicMock()
    odgovor.choices = [MagicMock(message=MagicMock(content=json.dumps(genome)))]
    klijent = MagicMock()
    klijent.chat.completions.create = AsyncMock(return_value=odgovor)
    with patch("openai.AsyncOpenAI", return_value=klijent):
        return await cd._extract_genome(docs)


@pytest.mark.asyncio
async def test_e2e_uuid_iz_a002_stize_do_workspace_potrosaca():
    """Jedan deterministički UUID praćen kroz CEO stvarni lanac:

        predmet_dokumenti.id
          -> A002 (routers/case_dna.py::_extract_genome)
          -> case_dna.kontradikcije[].dokument_id_1
          -> Rule 3 (services/case_evolution.py::_compute_target_actions)
          -> case_actions.dokaz
          -> routers/workspace.py::_normalize_case_action  ->  "izvor"

    Nijedan korak nije zamenjen mock-om osim GPT odgovora i Supabase klijenta.
    """
    docs = [
        {"id": UUID_A, "naziv_fajla": "resenje_o_otkazu.docx", "redni_broj": 1,
         "tekst_sadrzaj": "Sadržaj rešenja dovoljne dužine za analizu.", "velicina_kb": 10},
        {"id": UUID_B, "naziv_fajla": "interna_beleska.docx", "redni_broj": 3,
         "tekst_sadrzaj": "Sadržaj beleške dovoljne dužine za analizu.", "velicina_kb": 10},
    ]
    gpt = {"kontradikcije": [{"opis": "Razlog otkaza se kosi sa internom beleškom.",
                              "lokacija_1": "DOK-01 str.1", "lokacija_2": "DOK-03 str.2",
                              "tezina": "kriticna"}],
           "dokazi_rang": [], "snaga_predmeta_procent": 60}

    # 1) PRODUCENT — A002 razrešava identitet iz stvarnog `redni_broj`
    genome = await _izvuci_genome(docs, gpt)
    k = genome["kontradikcije"][0]
    assert k["dokument_id_1"] == UUID_A
    assert k["dokument_id_2"] == UUID_B

    # 2) TRANSFORMER — Rule 3 prenosi, ne preračunava
    akcija = (await _rule3(genome["kontradikcije"]))[0]
    assert akcija["dokaz"]["dokument_id_1"] == UUID_A
    assert akcija["dokaz"]["dokument_id_2"] == UUID_B

    # 3) SKLADIŠTE — oblik reda koji ide u `case_actions` (isti ključ kao u
    #    _consequence_refresh_case_actions), uključujući JSON serijalizaciju
    red = {"predmet_id": "pred-a003", "tip": akcija["tip"], "razlog": akcija["razlog"],
           "dokaz": akcija["dokaz"], "prioritet": akcija["prioritet"],
           "rok": akcija.get("rok"), "dedupe_key": akcija["dedupe_key"],
           "izvor_dokumenti": akcija.get("izvor_dokumenti") or [],
           "id": "act-1", "created_at": "2026-08-29T00:00:00Z"}
    red = json.loads(json.dumps(red))  # `None` mora preživeti kao `null`
    assert red["dokaz"]["dokument_id_1"] == UUID_A

    # 4) POTROŠAČ — stvarni serializer iz routers/workspace.py
    from routers.workspace import _normalize_case_action
    stavka = _normalize_case_action(red, "Predmet A003")
    assert stavka["izvor"]["dokaz"]["dokument_id_1"] == UUID_A
    assert stavka["izvor"]["dokaz"]["dokument_id_2"] == UUID_B
    # display i identity koegzistiraju, nijedan nije zamenio drugi
    assert stavka["izvor"]["dokaz"]["lokacija_1"] == "DOK-01 str.1"
    assert stavka["izvor"]["izvor_dokumenti"] == ["DOK-01 str.1", "DOK-03 str.2"]


@pytest.mark.asyncio
async def test_e2e_preimenovanje_fajla_ne_menja_preneti_identitet():
    """A002 je vezan za `redni_broj`, ne za naziv — provera da se ta osobina
    ne gubi prolaskom kroz Rule 3."""
    docs = [{"id": UUID_A, "naziv_fajla": "SASVIM_DRUGO_IME.docx", "redni_broj": 1,
             "tekst_sadrzaj": "Sadržaj dokumenta dovoljne dužine za analizu.", "velicina_kb": 10}]
    gpt = {"kontradikcije": [{"opis": "Unutrašnja nepodudarnost iskaza.",
                              "lokacija_1": "DOK-01 str.1", "lokacija_2": "DOK-01 str.4",
                              "tezina": "vazna"}],
           "dokazi_rang": [], "snaga_predmeta_procent": 50}
    genome = await _izvuci_genome(docs, gpt)
    akcija = (await _rule3(genome["kontradikcije"]))[0]
    assert akcija["dokaz"]["dokument_id_1"] == UUID_A
    assert akcija["dokaz"]["dokument_id_2"] == UUID_A
