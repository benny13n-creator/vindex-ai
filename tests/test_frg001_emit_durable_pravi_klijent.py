# -*- coding: utf-8 -*-
"""FRG001 — `emit_durable(event_id=...)` mora da gradi zahtev koji PRAVI supabase-py (requirements.txt: 2.28.3)
prihvata. Ranije: `insert(..., ignore_duplicates=True)` → TypeError pre ikakvog mrežnog zahteva, pa se nijedan
događaj sa stabilnim identitetom nije upisivao (fake ga je prihvatao). Mreža se ne dodiruje: presreće se
`execute()` i čita se izgrađen zahtev."""
import asyncio

import pytest
from postgrest._sync.request_builder import SyncQueryRequestBuilder
from supabase import create_client

EID = "11111111-2222-4333-8444-555555555555"


@pytest.fixture
def zahtevi(monkeypatch):
    uhvaceni = []

    def _execute(self):
        uhvaceni.append(self.request)
        return type("R", (), {"data": [], "count": 0})()
    monkeypatch.setattr(SyncQueryRequestBuilder, "execute", _execute)

    async def _prima(*a, **kw):
        return True
    monkeypatch.setattr("services.event_bus.predmet_prima_dogadjaje", _prima)
    return uhvaceni


def _klijent():
    return create_client("https://primer.invalid.supabase.co", "eyJhbGciOiJIUzI1NiJ9.e30.bGF6bmk")


def test_dogadjaj_sa_identitetom_je_on_conflict_id_do_nothing(zahtevi):
    from services.event_bus import EventType, emit_durable
    asyncio.run(emit_durable(EventType.NEW_EVIDENCE_REGISTERED, "uid-A", "pred-1", {"dokument_id": "d1"},
                             supa=_klijent(), event_id=EID))
    assert len(zahtevi) == 1
    r = zahtevi[0]
    assert r.http_method.value == "POST"
    assert "resolution=ignore-duplicates" in r.headers["prefer"]
    assert r.params.get("on_conflict") == "id"
    assert r.json["id"] == EID and r.json["event_type"] == "NewEvidenceRegistered"


def test_dogadjaj_bez_identiteta_ostaje_obican_insert(zahtevi):
    from services.event_bus import EventType, emit_durable
    asyncio.run(emit_durable(EventType.DOCUMENT_ACCEPTED, "uid-A", "pred-1", {"dokumenti": []}, supa=_klijent()))
    r = zahtevi[0]
    assert "resolution" not in r.headers.get("prefer", "") and "on_conflict" not in r.params
    assert "id" not in r.json
