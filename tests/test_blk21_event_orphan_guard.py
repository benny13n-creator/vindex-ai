# -*- coding: utf-8 -*-
"""BLK-2.1 — DOGAĐAJ SE NE UPISUJE ZA PREDMET KOJI SE BRIŠE ILI JE OBRISAN.

DOKAZANI KVAR (deterministička trka, 55 iteracija, produkcija `61dd6b6`):

    barijera puštena TAČNO kad korak 5b brisanja obriše `events`
    → 54/55 iteracija ostavilo orphan: predmet obrisan, `events` red ostao

`events.predmet_id` nema strani ključ (kolona je `TEXT`, `predmeti.id` je
`UUID`), pa korak 7 (`DELETE FROM predmeti`) takav red ne dodiruje. Poller
(`dispatch_pending_events`) ne proverava postojanje predmeta, pa bi takav
događaj bio i DISPEČOVAN — Case Evolution nad mrtvim predmetom.

INVARIANT KOJI OVAJ PAKET ČUVA:

    ACTIVE   → događaj dozvoljen
    DELETING → događaj odbijen
    DELETED  → događaj odbijen

Bez izmene šeme: koristi se postojeći tombstone `predmeti.brisanje_zapoceto`
(migracija 114), isti koji `shared/rag_acl.py` već čita.
"""
import asyncio
import os
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.event_bus import (  # noqa: E402
    EventType, emit_durable, predmet_prima_dogadjaje,
)

PID = "11111111-2222-3333-4444-555555555555"
UID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _supa(redovi=None, puca=None):
    """Dvojnik koji beleži svaki INSERT u `events` i ume da vrati stanje predmeta."""
    supa = MagicMock()
    supa.upisani = []

    def _table(ime):
        t = MagicMock()
        if ime == "predmeti":
            if puca:
                t.select.return_value.eq.return_value.limit.return_value.execute.side_effect = puca
            else:
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = redovi
        elif ime == "events":
            def _insert(red, **kw):
                supa.upisani.append(red)
                m = MagicMock()
                m.execute.return_value.data = [{}]
                return m
            t.insert.side_effect = _insert
        return t

    supa.table.side_effect = _table
    return supa


# ═══════════════════════════════════════════════════════════════════════════
# 1 — GUARD SAM PO SEBI
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_1_aktivan_predmet_prima_dogadjaje():
    s = _supa(redovi=[{"id": PID, "brisanje_zapoceto": None}])
    assert await predmet_prima_dogadjaje(s, PID) is True


@pytest.mark.anyio
async def test_1b_tombstonovan_predmet_ne_prima():
    """Prozor između koraka 5b i 7 — tačno tu orphan nastaje."""
    s = _supa(redovi=[{"id": PID, "brisanje_zapoceto": "2026-08-24T00:00:00+00:00"}])
    assert await predmet_prima_dogadjaje(s, PID) is False


@pytest.mark.anyio
async def test_1c_obrisan_predmet_ne_prima():
    s = _supa(redovi=[])
    assert await predmet_prima_dogadjaje(s, PID) is False


@pytest.mark.anyio
@pytest.mark.parametrize("pid", [None, "", "pred-1", "pred-001", "nije-uuid"])
async def test_1d_ne_uuid_i_prazan_predmet_id_prolaze(pid):
    """Izmereno na produkciji: 871 od 1000 redova u uzorku nosi `predmet_id`
    koji NIJE UUID (`pred-1`, `pred-001` — talog jediničnih testova), a 86 ima
    NULL. Takav red ne može referencirati stvaran predmet, pa ne može biti ni
    orphan; upit bi samo pukao sa `22P02`."""
    s = _supa(redovi=[])
    assert await predmet_prima_dogadjaje(s, pid) is True
    s.table.assert_not_called()


@pytest.mark.anyio
async def test_1e_pad_provere_PROPUSTA_dogadjaj():
    """`events` je outbox: izgubljen događaj trajno lomi Case Pipeline
    (BLACKSWAN-HIGH-008 — predmet bez PREDMET_KREIRAN nikad ne dobije prolaz),
    dok je orphan red pitanje higijene. Prolazna greška baze zato NE sme da
    guta događaje."""
    s = _supa(puca=TimeoutError("connection timeout expired"))
    assert await predmet_prima_dogadjaje(s, PID) is True


@pytest.mark.anyio
async def test_1f_greska_neispravnog_uuid_a_propusta():
    s = _supa(puca=Exception('invalid input syntax for type uuid: "pred-1" (22P02)'))
    assert await predmet_prima_dogadjaje(s, PID) is True


# ═══════════════════════════════════════════════════════════════════════════
# 2 — emit_durable POŠTUJE GUARD
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_2_emit_za_aktivan_predmet_upisuje():
    s = _supa(redovi=[{"id": PID, "brisanje_zapoceto": None}])
    await emit_durable(EventType.PREDMET_KREIRAN, UID, PID, {"x": 1}, supa=s)
    assert len(s.upisani) == 1
    assert s.upisani[0]["predmet_id"] == PID


@pytest.mark.anyio
async def test_2b_emit_za_tombstonovan_NE_upisuje():
    s = _supa(redovi=[{"id": PID, "brisanje_zapoceto": "2026-08-24T00:00:00+00:00"}])
    await emit_durable(EventType.PREDMET_KREIRAN, UID, PID, {"x": 1}, supa=s)
    assert s.upisani == [], "orphan događaj upisan za predmet u brisanju"


@pytest.mark.anyio
async def test_2c_emit_za_obrisan_NE_upisuje():
    s = _supa(redovi=[])
    await emit_durable(EventType.PREDMET_KREIRAN, UID, PID, {"x": 1}, supa=s)
    assert s.upisani == [], "orphan događaj upisan za obrisan predmet"


@pytest.mark.anyio
async def test_2d_emit_bez_predmeta_i_dalje_radi():
    """Sistemski događaji nisu vezani za predmet i ne smeju biti pogođeni."""
    s = _supa(redovi=[])
    await emit_durable(EventType.DOCUMENT_JOB_ENQUEUED, UID, None, {"x": 1}, supa=s)
    assert len(s.upisani) == 1


@pytest.mark.anyio
async def test_2e_emit_ne_gubi_dogadjaj_kad_provera_padne():
    s = _supa(puca=TimeoutError("connection timeout expired"))
    await emit_durable(EventType.PREDMET_KREIRAN, UID, PID, {"x": 1}, supa=s)
    assert len(s.upisani) == 1, "događaj izgubljen zbog prolazne greške provere"


# ═══════════════════════════════════════════════════════════════════════════
# 3 — SVI PISCI PROLAZE KROZ GUARD (§12: ako ijedan zaobilazi, nije zatvoreno)
# ═══════════════════════════════════════════════════════════════════════════

def _izvor(putanja):
    with open(os.path.join(os.path.dirname(__file__), "..", putanja), encoding="utf-8") as f:
        return f.read()


def test_3_svi_pisci_u_events_zovu_guard():
    """Popis mesta koja rade `table("events").insert(...)`. Svako mora imati
    guard u istoj funkciji. Ovaj test pada ako neko doda novog pisca."""
    import re

    ocekivani = {
        "services/event_bus.py": 4,   # emit_durable (2 grane) + 2 reapera
        "api.py": 2,                  # PREDMET_KREIRAN (2 grane)
        "routers/case_dna.py": 2,     # GENOME_UPDATED (2 grane)
    }
    for putanja, koliko in ocekivani.items():
        izvor = _izvor(putanja)
        upisi = len(re.findall(r'table\(\s*"events"\s*\)\.insert', izvor))
        assert upisi == koliko, (
            "%s ima %d upisa u `events`, ocekivano %d — nov pisac mora dobiti guard "
            "(BLK-2.1 §12)" % (putanja, upisi, koliko))
        assert "predmet_prima_dogadjaje" in izvor, (
            "%s upisuje u `events` bez guarda — orphan je ponovo moguc" % putanja)


def test_3b_nijedan_drugi_fajl_ne_upisuje_u_events():
    """Ako se pojavi nov pisac izvan poznata tri fajla, ovaj test pada."""
    import re
    from pathlib import Path

    koren = Path(os.path.join(os.path.dirname(__file__), ".."))
    dozvoljeni = {"services/event_bus.py", "api.py", "routers/case_dna.py"}
    nadjeni = set()
    for p in koren.rglob("*.py"):
        rel = p.relative_to(koren).as_posix()
        if rel.startswith(("tests/", "scripts/", ".vindex_ai_team/")):
            continue
        try:
            izvor = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if re.search(r'table\(\s*"events"\s*\)\.insert', izvor):
            nadjeni.add(rel)
    assert nadjeni == dozvoljeni, (
        "promenjen skup pisaca u `events`: %s (ocekivano %s)" % (sorted(nadjeni), sorted(dozvoljeni)))


# ═══════════════════════════════════════════════════════════════════════════
# 4 — REAPERI (backfill) POŠTUJU TOMBSTONE
# ═══════════════════════════════════════════════════════════════════════════

def test_4_reaperi_zovu_guard_pre_backfilla():
    """Oba reapera biraju po `created_at`, bez obzira na tombstone — predmet u
    brisanju bi dobio NOV događaj koji korak 5b više ne stigne da obriše."""
    izvor = _izvor("services/event_bus.py")
    for marker in ("reap_missing_pipeline_events", "reap_missing_rociste_events"):
        assert marker in izvor
    # guard mora stajati unutar obe petlje backfilla
    assert izvor.count("if not await predmet_prima_dogadjaje(supa,") >= 2, (
        "bar jedan reaper backfill-uje bez provere tombstone-a")
