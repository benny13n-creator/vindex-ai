"""IMPL TASK A002 — KANONSKI IDENTITET DOKUMENTA U `case_dna.kontradikcije`.

Kontradikcija je jedini element Genome-a koji tvrdi odnos IZMEĐU dva dokumenta.
Do sada je taj odnos postojao samo kao string `"DOK-01 str.1"`, pa se od
kontradikcije nije moglo doći do stvarnog dokumenta.

`DOK-NN` NIJE LLM izmišljotina: izvedena je iz `predmet_dokumenti.redni_broj`,
koji migracija 106 čuva UNIQUE indeksom nad `(predmet_id, redni_broj)`. Zato je
rezolucija ovde jača nego kod `dokazi_rang` — jedinstvenost garantuje baza.

Nedodirljivo: `lokacija_1`/`lokacija_2` ostaju i prikaz i ulaz u
`shared/contradiction_identity.py::contradiction_identity`, čiji heš završava u
`case_actions.dedupe_key`.
"""
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routers.case_dna as cd  # noqa: E402
from shared.contradiction_identity import (  # noqa: E402
    contradiction_dedupe_key, contradiction_identity,
)
from shared.genome_validator import _validate_kontradikcije_lokacije  # noqa: E402

UUID_A = "aaaaaaaa-1111-1111-1111-111111111111"
UUID_B = "bbbbbbbb-2222-2222-2222-222222222222"


def _doc(did, naziv, rb):
    return {"id": did, "naziv_fajla": naziv, "redni_broj": rb,
            "tekst_sadrzaj": "Sadržaj dokumenta dovoljne dužine za analizu.",
            "velicina_kb": 10, "pravni_elementi": []}


def _genome(lok1, lok2="", opis="Razlog otkaza se kosi sa internom beleškom."):
    return {"kontradikcije": [{"opis": opis, "lokacija_1": lok1,
                              "lokacija_2": lok2, "tezina": "kriticna"}],
            "dokazi_rang": [], "snaga_predmeta_procent": 60}


async def _izvuci(docs, genome):
    """STVARNI `_extract_genome`; lažira se isključivo GPT odgovor."""
    odgovor = MagicMock()
    odgovor.choices = [MagicMock(message=MagicMock(content=json.dumps(genome)))]
    klijent = MagicMock()
    klijent.chat.completions.create = AsyncMock(return_value=odgovor)
    with patch("openai.AsyncOpenAI", return_value=klijent):
        return await cd._extract_genome(docs)


def _k(rez):
    return (rez.get("kontradikcije") or [])[0]


DOCS2 = [_doc(UUID_A, "resenje_o_otkazu.docx", 1), _doc(UUID_B, "interna_beleska.docx", 3)]


# ═══════════════════════════════════════════════════════════════════════════
# 1–2 — validan DOK-NN / redni_broj → pravi dokument_id
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_1_validan_dok_nn_daje_pravi_id():
    k = _k(await _izvuci(DOCS2, _genome("DOK-01 str.1", "DOK-03 str.2")))
    assert k["dokument_id_1"] == UUID_A
    assert k["dokument_id_2"] == UUID_B


@pytest.mark.asyncio
async def test_2_redni_broj_je_izvor_a_ne_pozicija_u_listi():
    """`DOK-03` mora dati dokument sa `redni_broj=3`, ne treći element liste."""
    docs = [_doc(UUID_A, "a.docx", 3), _doc(UUID_B, "b.docx", 1)]
    k = _k(await _izvuci(docs, _genome("DOK-03 str.1", "DOK-01 str.1")))
    assert k["dokument_id_1"] == UUID_A   # redni_broj 3
    assert k["dokument_id_2"] == UUID_B   # redni_broj 1


@pytest.mark.asyncio
@pytest.mark.parametrize("oznaka", ["DOK-1", "DOK-01", "DOK-001", "dok-01", "Dok-1"])
async def test_2b_vodece_nule_i_case_se_ponasaju_kao_u_validatoru(oznaka):
    k = _k(await _izvuci(DOCS2, _genome(f"{oznaka} str.1")))
    assert k["dokument_id_1"] == UUID_A


# ═══════════════════════════════════════════════════════════════════════════
# 3–4 — nepostojeći / dupli kandidat → None
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_3_nepostojeci_dokument_daje_none():
    k = _k(await _izvuci(DOCS2, _genome("DOK-99 str.1", "DOK-01 str.1")))
    assert k["dokument_id_1"] is None
    assert k["dokument_id_2"] == UUID_A


@pytest.mark.asyncio
async def test_4_dupli_redni_broj_daje_none_nikad_prvog():
    """Migracija 106 to sprečava na nivou baze, ali kod ne sme da se oslanja
    na to — ako dva dokumenta ipak nose isti `redni_broj`, fail-closed."""
    docs = [_doc(UUID_A, "a.docx", 2), _doc(UUID_B, "b.docx", 2)]
    k = _k(await _izvuci(docs, _genome("DOK-02 str.1")))
    assert k["dokument_id_1"] is None, "dvosmisleno se ne sme razrešiti"


# ═══════════════════════════════════════════════════════════════════════════
# 5–7 — nikakva heuristika ne sme proizvesti identitet
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_5_fuzzy_slicnost_ne_proizvodi_identitet():
    """Opis pominje ime fajla, ali bez DOK-NN oznake → nema identiteta."""
    k = _k(await _izvuci(DOCS2, _genome("resenje_o_otkazu.docx, strana 1")))
    assert k["dokument_id_1"] is None


@pytest.mark.asyncio
async def test_6_substring_ne_proizvodi_identitet():
    k = _k(await _izvuci(DOCS2, _genome("resenje str.1")))
    assert k["dokument_id_1"] is None


@pytest.mark.asyncio
async def test_7_llm_uuid_se_ne_prihvata():
    """Ako LLM sam upiše UUID u lokaciju, on NE postaje identitet."""
    lazni = "cccccccc-9999-9999-9999-999999999999"
    k = _k(await _izvuci(DOCS2, _genome(f"{lazni} str.1")))
    assert k["dokument_id_1"] is None
    assert k["dokument_id_1"] != lazni


@pytest.mark.asyncio
async def test_7b_slobodan_opis_bez_oznake_daje_none():
    k = _k(await _izvuci(DOCS2, _genome("iskaz svedoka na ročištu", "")))
    assert k["dokument_id_1"] is None
    assert k["dokument_id_2"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 8–10 — fail-closed, preimenovanje, dva ista naziva
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_8_dokument_bez_id_je_fail_closed():
    docs = [{"id": None, "naziv_fajla": "a.docx", "redni_broj": 1,
             "tekst_sadrzaj": "tekst", "velicina_kb": 5, "pravni_elementi": []}]
    k = _k(await _izvuci(docs, _genome("DOK-01 str.1")))
    assert k["dokument_id_1"] is None


@pytest.mark.asyncio
async def test_9_preimenovanje_ne_menja_identitet():
    """CASE A: isti `id` i `redni_broj`, drugo ime → isti dokument."""
    pre = _k(await _izvuci([_doc(UUID_A, "resenje_o_otkazu.docx", 1)],
                           _genome("DOK-01 str.1")))
    posle = _k(await _izvuci([_doc(UUID_A, "resenje_o_otkazu_izmene.docx", 1)],
                             _genome("DOK-01 str.1")))
    assert pre["dokument_id_1"] == posle["dokument_id_1"] == UUID_A


@pytest.mark.asyncio
async def test_10_isti_naziv_razliciti_dokumenti_ostaju_razliciti():
    """CASE B: ime fajla je irelevantno — razrešava `redni_broj`."""
    docs = [_doc(UUID_A, "ugovor.pdf", 1), _doc(UUID_B, "ugovor.pdf", 2)]
    k = _k(await _izvuci(docs, _genome("DOK-01 str.1", "DOK-02 str.1")))
    assert k["dokument_id_1"] == UUID_A
    assert k["dokument_id_2"] == UUID_B
    assert k["dokument_id_1"] != k["dokument_id_2"]


# ═══════════════════════════════════════════════════════════════════════════
# 11 — rezolucija i validator koriste ISTO pravilo
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("lok,ocekivan_id,ocekivano_flagova", [
    ("DOK-01 str.1", UUID_A, 0),
    ("DOK-99 str.1", None, 1),
    ("bez oznake",   None, 0),
])
async def test_11_rezolucija_i_validator_govore_isto(lok, ocekivan_id, ocekivano_flagova):
    """Ne sme postojati ulaz koji validator prihvata a rezolucija odbija — ni obrnuto."""
    k = _k(await _izvuci(DOCS2, _genome(lok)))
    assert k["dokument_id_1"] == ocekivan_id
    flags = _validate_kontradikcije_lokacije(_genome(lok), DOCS2)
    assert len([f for f in flags if f["polje"] == "kontradikcije.lokacija_1"]) == ocekivano_flagova


# ═══════════════════════════════════════════════════════════════════════════
# 12 — postojeći ugovor ostaje netaknut
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_12_lokacije_opis_tezina_netaknuti():
    k = _k(await _izvuci(DOCS2, _genome("DOK-01 str.1", "DOK-03 str.2")))
    assert k["lokacija_1"] == "DOK-01 str.1"
    assert k["lokacija_2"] == "DOK-03 str.2"
    assert k["tezina"] == "kriticna"
    assert k["opis"].startswith("Razlog otkaza")


@pytest.mark.asyncio
async def test_12b_identitet_kontradikcije_NIJE_promenjen():
    """`contradiction_identity` čita SAMO `lokacija_*`. Njen heš završava u
    `case_actions.dedupe_key` — promena bi napravila duplikate akcija."""
    rez = await _izvuci(DOCS2, _genome("DOK-01 str.1", "DOK-03 str.2"))
    posle = _k(rez)
    pre = {"opis": posle["opis"], "lokacija_1": "DOK-01 str.1",
           "lokacija_2": "DOK-03 str.2", "tezina": "kriticna"}
    assert contradiction_identity(posle) == contradiction_identity(pre)
    assert contradiction_dedupe_key(posle) == contradiction_dedupe_key(pre)


@pytest.mark.asyncio
async def test_12c_kontradikcija_bez_id_ostaje_citljiva():
    """Nerazrešena kontradikcija i dalje nosi pun čitljiv sadržaj."""
    k = _k(await _izvuci(DOCS2, _genome("DOK-99 str.1", "iskaz svedoka")))
    assert k["dokument_id_1"] is None and k["dokument_id_2"] is None
    assert k["opis"] and k["tezina"] == "kriticna"
    assert k["lokacija_1"] == "DOK-99 str.1"


@pytest.mark.asyncio
async def test_12d_a001_identitet_dokaza_i_dalje_radi():
    """A002 ne sme pokvariti A001."""
    g = _genome("DOK-01 str.1")
    g["dokazi_rang"] = [{"redni_broj": 1, "naziv": "resenje_o_otkazu.docx",
                         "snaga_score": 80, "zvezdice": 4, "razlog": "x"}]
    rez = await _izvuci(DOCS2, g)
    assert rez["dokazi_rang"][0]["dokument_id"] == UUID_A
    assert _k(rez)["dokument_id_1"] == UUID_A


# ═══════════════════════════════════════════════════════════════════════════
# DIFF SPREMNOST + DETERMINIZAM
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_determinizam_dve_regeneracije():
    g = _genome("DOK-01 str.1", "DOK-03 str.2")
    a = _k(await _izvuci(DOCS2, g))
    b = _k(await _izvuci(list(reversed(DOCS2)), g))
    assert (a["dokument_id_1"], a["dokument_id_2"]) == (b["dokument_id_1"], b["dokument_id_2"])


@pytest.mark.asyncio
async def test_diff_prepoznaje_isti_par_dokumenata_uprkos_preimenovanju():
    """Kontradikcija između ista dva objekta ostaje ista i kad se oba preimenuju."""
    n = _k(await _izvuci(DOCS2, _genome("DOK-01 str.1", "DOK-03 str.2")))
    docs2 = [_doc(UUID_A, "resenje_v2.docx", 1), _doc(UUID_B, "beleska_v2.docx", 3)]
    n1 = _k(await _izvuci(docs2, _genome("DOK-01 str.1", "DOK-03 str.2")))
    assert {n["dokument_id_1"], n["dokument_id_2"]} == \
           {n1["dokument_id_1"], n1["dokument_id_2"]} == {UUID_A, UUID_B}
