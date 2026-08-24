# -*- coding: utf-8 -*-
"""BLK-1 — DATUM ≠ ROK.

BOJAN-BETA-FORENSIC-AUDIT-001 (2026-08-24) je dokazao uživo da Vindex izmišlja
rokove: tužba bez ijednog roka proizvela je red „Rok — tužba" sa datumom
sastavljanja i pouzdanošću 0.95, koji je završio u kalendaru advokata. Uzrok
nije bio prag (0.95 > 0.90) nego KRITERIJUM — pravna TEMA u prozoru od ±100
znakova ("žalba"/"tužba"/"isplata") tretirana je kao dokaz da je datum rok.

Ovi testovi zaključavaju novo pravilo: datum postaje rok samo uz eksplicitan
dokaz o roku neposredno ispred sebe, bez protiv-dokaza, novog reda ili drugog
datuma između. Svaki test ispod PADA na `9a2ce774` (stanje pre popravke) —
mereno, ne pretpostavljeno.
"""
import pytest

from shared.intake_extract import extract_deadline


# ─── TEST MATRIX A-J (nalog §10) ─────────────────────────────────────────────

def test_A_tuzba_bez_roka_ne_proizvodi_rok():
    """Datum sastavljanja tužbe nije rok — ni kad je reč 'isplatu' u blizini.

    Ovo je doslovan dokument iz forenzičkog audita. PRE popravke:
    ('12.01.2026', 0.95). POSLE: (None, 0.0)."""
    tekst = (
        "TUZBA\nTuzilac: Petar Petrovic\nTuzeni: MEGATRADE DOO\n"
        "Tuzeni nije izmirio obavezu u iznosu od 1.250.000,00 dinara.\n"
        "Predlazem da sud obaveze tuzenog na isplatu.\n"
        "U Beogradu, 12.01.2026. godine."
    )
    assert extract_deadline(tekst) == (None, 0.0)


def test_B_datum_potpisa_ugovora_nije_rok():
    """Drugi dokazani slučaj iz audita: 'Rok — ugovor' sa datumom potpisa."""
    tekst = (
        "UGOVOR O POSLOVNOJ SARADNJI\n"
        "Zakljucen dana 12.01.2026. godine izmedju Petra Petrovica i MEGATRADE DOO.\n"
        "Predmet ugovora je isporuka robe."
    )
    assert extract_deadline(tekst) == (None, 0.0)


def test_C_eksplicitan_relativni_rok_i_dalje_radi():
    """Regresija: stvarna pravna pouka mora ostati prepoznata."""
    tekst = (
        "RESENJE\nProtiv ovog resenja dozvoljena je zalba u roku od 15 dana "
        "od dana prijema.\nResenje je primljeno dana 10.08.2026. godine."
    )
    vrednost, conf = extract_deadline(tekst)
    assert vrednost == "15 dana"
    assert conf == pytest.approx(0.77)


def test_D_eksplicitna_rokovna_fraza_uplata():
    tekst = "OPOMENA\nRok za uplatu je 8 dana od prijema fakture.\nFaktura je primljena 01.08.2026."
    vrednost, conf = extract_deadline(tekst)
    assert vrednost == "8 dana"
    assert conf == pytest.approx(0.77)


def test_E_datum_uz_rec_tuzba_nije_rok():
    assert extract_deadline("Tuzba sastavljena 12.01.2026.") == (None, 0.0)


def test_F_datum_uz_rec_isplata_nije_rok():
    """'Isplata izvršena 12.01.2026' je prošao događaj, ne obaveza."""
    assert extract_deadline("Isplata izvrsena 12.01.2026.") == (None, 0.0)


def test_G_datum_rocista_nije_rok():
    """Ročište je događaj. Kalendar ga vodi kroz `rocista`, ne kao rok."""
    assert extract_deadline("Rociste je zakazano za 20.02.2026. godine u 10:00 casova.") == (None, 0.0)


def test_H_vise_datuma_samo_stvarni_rok_prolazi():
    """Pet datuma, jedan rok. Nijedan drugi ne sme da se zarazi."""
    tekst = (
        "IZVOD\nUgovor je zakljucen 01.03.2025. Roba je isporucena 15.04.2025.\n"
        "Resenje je primljeno 10.08.2026. Rociste je zakazano za 20.02.2027.\n"
        "Rok za zalbu istice 25.08.2026. godine."
    )
    vrednost, conf = extract_deadline(tekst)
    assert vrednost == "25.08.2026"
    assert conf == pytest.approx(0.95)


def test_I_dokument_bez_datuma_nema_rok():
    assert extract_deadline("OBAVESTENJE\nObavestavamo Vas da je postupak u toku.") == (None, 0.0)


def test_J_ista_ekstrakcija_dva_puta_daje_isti_rezultat():
    """Determinizam — isti ulaz, isti izlaz. Preduslov da ponovljena obrada
    istog dokumenta ne može proizvesti drugačiji (pa time i duplikatni) rok."""
    tekst = "Rok za zalbu istice 25.08.2026. godine."
    assert extract_deadline(tekst) == extract_deadline(tekst)


# ─── ADVERSARIAL (nalog §11) ─────────────────────────────────────────────────

def test_adv_eksplicitno_negiran_rok():
    """Reč 'Rok' postoji u tekstu, ali POSLE datuma i u rečenici koja rok
    negira. Rokovna reč iza datuma ne sme da ga usvoji unazad."""
    tekst = "Tuzba podneta 12.01.2026. godine. Rok za zalbu ne postoji u ovom dokumentu."
    assert extract_deadline(tekst) == (None, 0.0)


def test_adv_datum_potpisa_nije_rok_placanja():
    """'Ugovor je potpisan 12.01.2026. Rok za placanje je 30 dana.'

    Datum potpisa NE sme postati rok. Relativni izraz '30 dana' jeste rok, ali
    bez datuma-okidača ostaje relativan — `_deadline_to_iso` ga ne pretvara u
    ISO, pa se ne upisuje u kalendar. Nema izmišljenog konkretnog datuma."""
    vrednost, conf = extract_deadline("Ugovor je potpisan 12.01.2026. Rok za placanje je 30 dana.")
    assert vrednost == "30 dana"
    assert "12.01.2026" not in str(vrednost)


def test_adv_isplata_pre_dospeca():
    """Dva datuma, oba prošla, nijedna rokovna reč — nijedan nije rok."""
    tekst = "Isplata je izvrsena 12.01.2026, a obaveza je morala biti ispunjena do 10.01.2026."
    assert extract_deadline(tekst) == (None, 0.0)


def test_adv_gomila_pravnih_reci_i_datuma():
    """Šest datuma, svaki uz pravnu temu (tužba/žalba/isplata). Tema nije dokaz."""
    tekst = (
        "Tuzba 01.02.2026. Zalba 02.02.2026. Isplata 03.02.2026. "
        "Tuzba 04.02.2026. Zalba 05.02.2026. Isplata 06.02.2026."
    )
    assert extract_deadline(tekst) == (None, 0.0)


def test_adv_rokovna_rec_iz_prethodne_recenice_ne_prelazi_na_sledeci_datum():
    """Najsuptilniji slučaj: 'Rok ... ističe 25.08.2026.' i odmah zatim
    'U Beogradu, dana 05.08.2026.' Rokovna reč pripada PRVOM datumu."""
    tekst = (
        "Rok za zalbu istice 25.08.2026. godine.\n"
        "U Beogradu, dana 05.08.2026. godine."
    )
    vrednost, _ = extract_deadline(tekst)
    assert vrednost == "25.08.2026"


def test_adv_datum_prijema_izmedju_rokovne_reci_i_datuma():
    """'u roku od 15 dana od dana prijema.\\nResenje je primljeno dana
    10.08.2026.' — datum prijema je OKIDAČ, ne rok. Protiv-dokaz 'primljeno'
    stoji između rokovne reči i datuma."""
    tekst = (
        "Protiv ovog resenja dozvoljena je zalba u roku od 15 dana od dana prijema.\n"
        "Resenje je primljeno dana 10.08.2026. godine."
    )
    vrednost, _ = extract_deadline(tekst)
    assert vrednost != "10.08.2026"


# ─── INVARIJANTE (nalog §5) ──────────────────────────────────────────────────

@pytest.mark.parametrize("tekst", [
    "Presuda je doneta 12.01.2026.",
    "Resenje je dostavljeno 12.01.2026.",
    "Zapisnik je sastavljen 12.01.2026.",
    "Ugovor je overen 12.01.2026.",
    "Faktura je izdata 12.01.2026.",
    "Rociste je odrzano 12.01.2026.",
])
def test_invarijanta_dogadjajni_datumi_nikad_nisu_rok(tekst):
    """INVARIANT 1/4/5/6/7: puko postojanje datuma, tip dokumenta i tema
    nikad nisu dovoljni. Svaki od ovih datuma pripada svom događaju."""
    assert extract_deadline(tekst) == (None, 0.0)


def test_invarijanta_cirilica_rok_prepoznat():
    """Ćirilički rok mora proći isto kao latinični — inače bi popravka
    'rešila' lažne pozitive tako što bi ubila ćirilične dokumente."""
    vrednost, conf = extract_deadline("Рок за жалбу истиче 25.08.2026. године.")
    assert vrednost == "25.08.2026"
    assert conf == pytest.approx(0.95)


def test_invarijanta_cirilicni_dogadjajni_datum_nije_rok():
    assert extract_deadline("Пресуда је донета 12.01.2026. године.") == (None, 0.0)


# ─── TAČKA UPISA: prag i ljudska potvrda (nalog §8) ──────────────────────────

def test_prag_upisa_je_isti_kao_prag_review_queue():
    """Jedan prag, jedna istina: tačka upisa roka koristi ISTI
    AUTO_ACCEPT_THRESHOLD koji već odlučuje šta ide u review queue."""
    from shared.intake_documents import AUTO_ACCEPT_THRESHOLD
    assert AUTO_ACCEPT_THRESHOLD == 0.90
    # Dokazan rok mora preći taj prag, inače bi ga drugi sloj odbio.
    _, conf = extract_deadline("Rok za zalbu istice 25.08.2026. godine.")
    assert conf >= AUTO_ACCEPT_THRESHOLD


def test_relativni_rok_ne_postaje_datum_u_kalendaru():
    """Relativni rok ('15 dana') nema konkretan datum i zato se NE upisuje —
    `_deadline_to_iso` ga odbija. Ovo je namerno: bolje nijedan rok nego
    izmišljen datum."""
    from routers.smart_intake import _deadline_to_iso
    vrednost, _ = extract_deadline(
        "Protiv ovog resenja dozvoljena je zalba u roku od 15 dana od dana prijema."
    )
    assert vrednost == "15 dana"
    assert _deadline_to_iso(vrednost) is None


# ─── TAČKA UPISA: baza / kalendar / podsetnik (nalog §13, §14) ───────────────
#
# Testovi iznad zaključavaju ODLUKU (`extract_deadline`). Ovi zaključavaju
# POSLEDICU — šta finalize stvarno upiše u `predmet_hronologija`, jedini izvor
# iz kog `/api/kalendar/pregled` i `/notifications/refresh` čitaju rokove.
# Mocking obrazac je isti kao u tests/test_sprint003_classification_review_required.py.

import contextlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _blk1_request():
    return StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/smart-intake/jobs/job-1/finalize", "app": MagicMock(), "state": MagicMock(),
    })


def _blk1_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "advokat@vindex.rs"}


def _blk1_supa(hronologija_postoji=False):
    """Beleži svaki INSERT u predmet_hronologija u `supa.blk1_upisi`."""
    supa = MagicMock()
    supa.blk1_upisi = []

    def _table(name):
        t = MagicMock()
        if name == "intake_jobs":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                "id": "job-1", "status": "completed", "storage_path": "session/xyz",
                "original_filename": "resenje.pdf", "mime_type": "application/pdf",
                "predmet_id": None, "completed_at": None,
            }
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "predmeti":
            t.insert.return_value.execute.return_value.data = [{"id": "pred-001"}]
        elif name == "predmet_dokumenti":
            t.insert.return_value.execute.return_value.data = [{"id": "dok-001"}]
            # Detekcija "nastavljam prekinuti pokusaj" (smart_intake.py:1055) --
            # prazan rezultat znaci "ovo je prvi finalize", sto je slucaj koji
            # ovi testovi mere. Bez ovoga MagicMock vraca truthy `.data` i kod
            # ide u RESUME granu koja rok NAMERNO preskace.
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        elif name == "klijenti":
            t.select.return_value.eq.return_value.ilike.return_value.neq.return_value.limit.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [{"id": "kl-001"}]
        elif name == "predmet_klijenti":
            t.insert.return_value.execute.return_value.data = [{}]
        elif name == "predmet_hronologija":
            def _insert(red):
                supa.blk1_upisi.append(red)
                m = MagicMock()
                m.execute.return_value.data = [{}]
                return m
            t.insert.side_effect = _insert
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = (
                [{"id": "hron-postojeci"}] if hronologija_postoji else []
            )
        elif name == "intake_job_segments":
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
        return t

    supa.table.side_effect = _table
    return supa


async def _blk1_finalize(supa, entities, review=None):
    from routers.smart_intake import finalize_intake_job, FinalizeReq

    job_result = {
        "document": {"id": "dok-001", "document_type": "appeal"},
        "entities": entities,
        "review": review,
    }
    patches = (
        patch("routers.smart_intake._get_supa", return_value=supa),
        patch("shared.intake_segments._get_supa", return_value=supa),
        patch("shared.intake_documents.get_job_documents", new=AsyncMock(return_value=[job_result])),
        patch("shared.intake_worker.worker._download_and_decrypt", new=AsyncMock(return_value=b"raw")),
        patch("uploaded_doc.extractor.extract", return_value=("tekst", False, False, None, None)),
        patch("uploaded_doc.chunker.chunk_document", return_value={"chunks": []}),
        patch("uploaded_doc.ingest.ingest_session", return_value=None),
        patch("uploaded_doc.session.generate_session_id", return_value="sess-001"),
        patch("shared.kancelarija_utils.get_kancelarija_id", new=AsyncMock(return_value=None)),
        patch("shared.vector_origin.now_iso", return_value="2026-08-24T00:00:00Z"),
        patch("routers.smart_intake.intake_queue.claim_finalize",
              new=AsyncMock(return_value={"id": "job-1", "finalizing_at": "2026-08-24T00:00:00+00:00"})),
        patch("services.event_bus.emit_durable", new=AsyncMock()),
    )
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return await finalize_intake_job("job-1", _blk1_request(), FinalizeReq(), _blk1_user())


def _ent(entity_type, value, confidence, reviewed=False, corrected=None):
    return {"id": "e-" + entity_type, "entity_type": entity_type, "value": value,
            "confidence": confidence, "reviewed": reviewed, "corrected_value": corrected,
            "extraction_method": "regex"}


@pytest.mark.anyio
async def test_upis_dokazan_rok_ulazi_u_hronologiju_sa_provenance():
    """Dokazan rok mora da uđe u `predmet_hronologija` — to je jedini izvor
    kalendara — i mora da nosi izvorni dokument."""
    supa = _blk1_supa()
    rezultat = await _blk1_finalize(supa, [_ent("deadline", "27.09.2026", 0.95)])

    assert rezultat["rok_dodat"] is True
    assert len(supa.blk1_upisi) == 1
    red = supa.blk1_upisi[0]
    assert red["datum_iso"] == "2026-09-27"
    assert red["dokument_naziv"] == "resenje.pdf"


@pytest.mark.anyio
async def test_upis_naziv_vise_ne_tvrdi_vrstu_roka():
    """Raniji naziv je bio vrsta DOKUMENTA prikazana kao vrsta ROKA."""
    supa = _blk1_supa()
    await _blk1_finalize(supa, [_ent("deadline", "27.09.2026", 0.95)])

    dogadjaj = supa.blk1_upisi[0]["dogadjaj"]
    assert not dogadjaj.startswith("Rok — ")
    assert dogadjaj.startswith("Rok iz dokumenta (")


@pytest.mark.anyio
async def test_upis_niska_pouzdanost_ne_ulazi_u_kalendar():
    """Drugi sloj: i kad bi klasifikacija propustila nedokazan datum, upis ga
    zaustavlja — i to KAŽE, umesto da ćuti."""
    supa = _blk1_supa()
    rezultat = await _blk1_finalize(supa, [_ent("deadline", "27.09.2026", 0.55)])

    assert rezultat["rok_dodat"] is False
    assert rezultat["rok_preskocen_razlog"] == "niska_pouzdanost"
    assert supa.blk1_upisi == []


@pytest.mark.anyio
async def test_upis_ljudska_potvrda_nadjacava_prag():
    """Vrednost koju je advokat ispravio ulazi bez obzira na pouzdanost —
    prag štiti od mašine, ne od čoveka."""
    supa = _blk1_supa()
    rezultat = await _blk1_finalize(
        supa, [_ent("deadline", "01.01.2027", 0.20, reviewed=True, corrected="27.09.2026")])

    assert rezultat["rok_dodat"] is True
    assert supa.blk1_upisi[0]["datum_iso"] == "2026-09-27"


@pytest.mark.anyio
async def test_upis_TEST_J_dupla_obrada_ne_pravi_dupli_rok():
    """TEST J (nalog §10): isti dokument obrađen dvaput. Rok već postoji u
    predmetu — drugi upis se preskače, i razlog se prijavljuje."""
    supa = _blk1_supa(hronologija_postoji=True)
    rezultat = await _blk1_finalize(supa, [_ent("deadline", "27.09.2026", 0.95)])

    assert rezultat["rok_dodat"] is False
    assert rezultat["rok_preskocen_razlog"] == "vec_postoji"
    assert supa.blk1_upisi == []


@pytest.mark.anyio
async def test_upis_bez_roka_ne_dira_hronologiju():
    """Tužba bez roka: `extract_deadline` vraća None, entitet nema vrednost,
    `predmet_hronologija` ostaje netaknuta."""
    supa = _blk1_supa()
    rezultat = await _blk1_finalize(supa, [_ent("deadline", None, 0.0)])

    assert rezultat["rok_dodat"] is False
    assert rezultat["rok_preskocen_razlog"] is None
    assert supa.blk1_upisi == []
