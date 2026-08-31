"""IMPL TASK A001 — KANONSKI IDENTITET DOKUMENTA U `case_dna.dokazi_rang`.

Genome je dokument identifikovao isključivo imenom fajla, koje LLM prepisuje iz
zaglavlja. Ime fajla nije identitet: menja se pri preimenovanju, a dva dokumenta
istog predmeta smeju da se zovu isto. Posledica je bila da nijedan element
gornjeg kanonskog lanca nije mogao da se spoji sa stvarnim redom u bazi.

Ovi testovi drže jedno pravilo:

    STABILAN ID > tekstualna oznaka > LLM-generisana oznaka

`dokument_id` se izvodi DETERMINISTIČKI iz `docs` (`predmet_dokumenti.id`),
nikad od strane LLM-a, i ostaje `None` kada veza nije jednoznačna.
"""
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routers.case_dna as cd  # noqa: E402

UUID_A = "aaaaaaaa-1111-1111-1111-111111111111"
UUID_B = "bbbbbbbb-2222-2222-2222-222222222222"


def _doc(did, naziv, rb=1):
    return {"id": did, "naziv_fajla": naziv, "redni_broj": rb,
            "tekst_sadrzaj": "Sadržaj dokumenta dovoljne dužine za analizu.",
            "velicina_kb": 10, "pravni_elementi": []}


def _genome(*nazivi):
    return {
        "dokazi_rang": [
            {"redni_broj": i + 1, "naziv": n, "snaga_score": 80, "zvezdice": 4, "razlog": "x"}
            for i, n in enumerate(nazivi)
        ],
        "snaga_predmeta_procent": 70,
    }


async def _izvuci(docs, genome):
    """Pokreće STVARNI `_extract_genome`; lažira se ISKLJUČIVO GPT odgovor.

    Isti obrazac koji već koriste postojeći Genome testovi
    (tests/test_singlebrain2_readiness_unification.py:315-322) — mock vraća
    JSON STRING, jer `_extract_genome` sam radi `json.loads`."""
    odgovor = MagicMock()
    odgovor.choices = [MagicMock(message=MagicMock(content=json.dumps(genome)))]
    klijent = MagicMock()
    klijent.chat.completions.create = AsyncMock(return_value=odgovor)
    with patch("openai.AsyncOpenAI", return_value=klijent):
        return await cd._extract_genome(docs)


def _rang(rez):
    return rez.get("dokazi_rang") or []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1 — postojeći dokument dobija stabilan `dokument_id`
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_1_dokument_dobija_stabilan_id():
    rez = await _izvuci([_doc(UUID_A, "resenje_o_otkazu.docx")],
                        _genome("resenje_o_otkazu.docx"))
    assert _rang(rez)[0]["dokument_id"] == UUID_A
    # ime fajla ostaje kao display metapodatak, ali nije identitet
    assert _rang(rez)[0]["naziv"] == "resenje_o_otkazu.docx"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2 (§6) — PREIMENOVANJE NE MENJA IDENTITET
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_2_preimenovanje_ne_menja_identitet():
    """Isti `predmet_dokumenti.id`, drugo ime fajla → isti kanonski identitet."""
    pre = await _izvuci([_doc(UUID_A, "resenje_o_otkazu.docx")],
                        _genome("resenje_o_otkazu.docx"))
    posle = await _izvuci([_doc(UUID_A, "resenje_o_otkazu_final.docx")],
                          _genome("resenje_o_otkazu_final.docx"))
    assert _rang(pre)[0]["dokument_id"] == UUID_A
    assert _rang(posle)[0]["dokument_id"] == UUID_A
    assert _rang(pre)[0]["dokument_id"] == _rang(posle)[0]["dokument_id"]
    # a ime se JESTE promenilo — dokaz da identitet ne prati ime
    assert _rang(pre)[0]["naziv"] != _rang(posle)[0]["naziv"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3 (§7) — DVA DOKUMENTA ISTOG IMENA SE NE SMEJU SPOJITI
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_3_isto_ime_dva_dokumenta_ne_sme_da_spoji():
    """Ime fajla NIJE join key. Dvosmisleno → fail-closed, ne „prvi po redu"."""
    docs = [_doc(UUID_A, "ugovor.pdf", 1), _doc(UUID_B, "ugovor.pdf", 2)]
    rez = await _izvuci(docs, _genome("ugovor.pdf"))
    assert _rang(rez)[0]["dokument_id"] is None, (
        "dva dokumenta istog imena ne smeju biti razrešena na jedan ID"
    )


@pytest.mark.asyncio
async def test_3b_razlicita_imena_ostaju_razliciti_identiteti():
    docs = [_doc(UUID_A, "ugovor_2024.pdf"), _doc(UUID_B, "ugovor_2025.pdf")]
    rez = await _izvuci(docs, _genome("ugovor_2024.pdf", "ugovor_2025.pdf"))
    ids = [s["dokument_id"] for s in _rang(rez)]
    assert ids == [UUID_A, UUID_B]
    assert len(set(ids)) == 2


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4 (§8) — MOST DOKAZ → DOKUMENT → GENOME
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_4_kanonski_most_dokaz_dokument_genome():
    """`predmet_dokazi.dokument_id` → `predmet_dokumenti.id` → `dokazi_rang.dokument_id`.

    Genome NE duplira identitet dokaza — dovoljan je zajednički ključ
    dokumenta, po kome se dokazi spajaju bez tekstualnog posrednika."""
    dokaz_red = {"tvrdnja": "Tuženi je primio opomenu.", "dokument_id": UUID_A}
    rez = await _izvuci([_doc(UUID_A, "opomena.pdf")], _genome("opomena.pdf"))
    genome_id = _rang(rez)[0]["dokument_id"]

    assert genome_id == UUID_A
    assert dokaz_red["dokument_id"] == genome_id
    # spoj je moguć bez ijednog stringa
    spojeni = [d for d in [dokaz_red] if d["dokument_id"] == genome_id]
    assert len(spojeni) == 1


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5 (§9) — NIKAD HALUCINIRAN IDENTITET
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_5_nepoznat_dokument_ne_dobija_izmisljen_id():
    rez = await _izvuci([_doc(UUID_A, "postojeci.pdf")], _genome("nepostojeci.pdf"))
    assert _rang(rez)[0]["dokument_id"] is None


@pytest.mark.asyncio
async def test_5b_prazan_naziv_ne_dobija_id():
    """Prazan `naziv` ne sme da se poklopi ni sa čim."""
    rez = await _izvuci([_doc(UUID_A, "a.pdf")], _genome(""))
    assert _rang(rez)[0]["dokument_id"] is None


@pytest.mark.asyncio
async def test_5d_bez_dokumenata_ekstrakcija_kratko_spaja_kao_i_pre():
    """Zatečeno ponašanje, nedirnuto: prazna lista dokumenata daje `{}` pre
    nego što se do `dokazi_rang` uopšte stigne. Rezolucija ga ne menja."""
    assert await _izvuci([], _genome("bilo_sta.pdf")) == {}


@pytest.mark.asyncio
async def test_5c_id_nikad_nije_ime_ni_llm_oznaka():
    """Vrednost mora biti stvarni UUID iz `docs`, nikad `naziv` ni `DOK-NN`."""
    rez = await _izvuci([_doc(UUID_A, "resenje.docx")], _genome("resenje.docx"))
    v = _rang(rez)[0]["dokument_id"]
    assert v == UUID_A
    assert v != "resenje.docx"
    assert not str(v).upper().startswith("DOK-")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6 (§10) — DETERMINISTIČKA REGENERACIJA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_6_dve_regeneracije_daju_isti_id():
    docs = [_doc(UUID_A, "a.pdf", 1), _doc(UUID_B, "b.pdf", 2)]
    r1 = await _izvuci(docs, _genome("a.pdf", "b.pdf"))
    r2 = await _izvuci(docs, _genome("a.pdf", "b.pdf"))
    assert [s["dokument_id"] for s in _rang(r1)] == [s["dokument_id"] for s in _rang(r2)]


@pytest.mark.asyncio
async def test_6b_redosled_dokumenata_ne_menja_identitet():
    d1, d2 = _doc(UUID_A, "a.pdf", 1), _doc(UUID_B, "b.pdf", 2)
    r1 = await _izvuci([d1, d2], _genome("b.pdf"))
    r2 = await _izvuci([d2, d1], _genome("b.pdf"))
    assert _rang(r1)[0]["dokument_id"] == _rang(r2)[0]["dokument_id"] == UUID_B


@pytest.mark.asyncio
async def test_6c_llm_formulacija_razloga_ne_utice_na_identitet():
    docs = [_doc(UUID_A, "a.pdf")]
    g1 = _genome("a.pdf"); g1["dokazi_rang"][0]["razlog"] = "Prva formulacija."
    g2 = _genome("a.pdf"); g2["dokazi_rang"][0]["razlog"] = "Sasvim druga formulacija."
    assert _rang(await _izvuci(docs, g1))[0]["dokument_id"] == \
           _rang(await _izvuci(docs, g2))[0]["dokument_id"] == UUID_A


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7 — POSTOJEĆI UGOVOR OSTAJE KOMPATIBILAN
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_7_stara_polja_netaknuta_i_clamp_i_dalje_radi():
    docs = [_doc(UUID_A, "a.pdf")]
    g = _genome("a.pdf")
    g["dokazi_rang"][0]["snaga_score"] = 99999      # mora ostati clamp-ovano
    rez = await _izvuci(docs, g)
    s = _rang(rez)[0]
    assert s["snaga_score"] == 100                   # Single Brain clamp netaknut
    for k in ("redni_broj", "naziv", "zvezdice", "razlog"):
        assert k in s, k
    # `snaga_predmeta_procent` se NE proverava ovde: njegov kanonski vlasnik je
    # shared/genome_validator.py::compute_snaga_score, koji ga preračunava posle
    # ekstrakcije (semantic_registry: koncept STRENGTH). Vrednost iz LLM odgovora
    # nije ugovor ovog testa.
    assert isinstance(rez.get("snaga_predmeta_procent"), int)


@pytest.mark.asyncio
async def test_7b_validator_i_rezolucija_koriste_ISTO_pravilo_poklapanja():
    """Rezolucija ne sme biti blaža ni stroža od `_validate_dokazi_rang`."""
    from shared.genome_validator import _validate_dokazi_rang
    docs = [_doc(UUID_A, "Ugovor.PDF")]
    rez = await _izvuci(docs, _genome("ugovor.pdf"))   # drugi case
    assert _rang(rez)[0]["dokument_id"] == UUID_A      # rezolucija: pogodak
    assert _validate_dokazi_rang(_genome("ugovor.pdf"), docs) == []  # validator: bez flaga


@pytest.mark.asyncio
async def test_7c_nerazreseno_ime_i_dalje_dize_validator_flag():
    """Fail-closed `dokument_id=None` NE gasi postojeće upozorenje."""
    from shared.genome_validator import _validate_dokazi_rang
    docs = [_doc(UUID_A, "postojeci.pdf")]
    rez = await _izvuci(docs, _genome("nepostojeci.pdf"))
    assert _rang(rez)[0]["dokument_id"] is None
    flags = _validate_dokazi_rang(_genome("nepostojeci.pdf"), docs)
    assert len(flags) == 1 and flags[0]["polje"] == "dokazi_rang"


# ═══════════════════════════════════════════════════════════════════════════
# §11 — DIFF SPREMNOST (samo provera, impact analiza NIJE deo ovog taska)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_diff_prepoznaje_isti_dokument_uprkos_preimenovanju():
    """Preduslov za buduću Genome N ↔ N+1 uporedbu: isti objekat, isti ključ."""
    g_n = await _izvuci([_doc(UUID_A, "nalaz.pdf")], _genome("nalaz.pdf"))
    g_n1 = await _izvuci([_doc(UUID_A, "nalaz_v2.pdf")], _genome("nalaz_v2.pdf"))
    po_id_n = {s["dokument_id"] for s in _rang(g_n)}
    po_id_n1 = {s["dokument_id"] for s in _rang(g_n1)}
    assert po_id_n == po_id_n1 == {UUID_A}
    # po imenu bi diff pogrešno prijavio „nestao jedan, pojavio se drugi"
    assert {s["naziv"] for s in _rang(g_n)} != {s["naziv"] for s in _rang(g_n1)}
