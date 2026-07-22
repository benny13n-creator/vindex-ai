# -*- coding: utf-8 -*-
"""
Tests for Case Genome Faza 1.1 + 1.2 (90-dnevni plan, 2026-07-18):

Faza 1.1 — routers/case_dna.py's _emit_genome_event i
           services/event_bus.py's EventType.GENOME_UPDATED durable-outbox.
Faza 1.2 — services/event_bus.py's on_genome_updated handler (prvi stvaran
           potrošač GENOME_UPDATED eventa) i _run_genome_background-ov novi
           'trigger' parametar (ispravka: pre 1.2 je funkcija UVEK pisala
           'upload_trigger' bez obzira na stvarnog pozivaoca).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_chain(data):
    chain = MagicMock()
    for attr in ["select", "eq", "update", "insert", "upsert", "order", "limit", "is_", "in_", "lt", "single", "maybe_single"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


# ═══════════════════════════════════════════════════════════════════════════
# Faza 1.1 — routers/case_dna.py — _emit_genome_event
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_emit_genome_event_inserts_row_with_correct_payload():
    from routers import case_dna as cd

    chain = _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(return_value=chain)

    genome = {"verzija": 3, "snaga_predmeta_procent": 62}
    corr_id = await cd._emit_genome_event(
        supa, "predmet-1", "user-1", genome, "manual_refresh", prev_verzija=2,
        verifikacija_odluka="approve_with_warning",
    )

    supa.table.assert_called_once_with("events")
    chain.insert.assert_called_once()
    row = chain.insert.call_args[0][0]
    assert row["event_type"] == "GenomeUpdated"
    assert row["user_id"] == "user-1"
    assert row["predmet_id"] == "predmet-1"
    payload = row["payload"]
    assert payload["verzija"] == 3
    assert payload["prev_verzija"] == 2
    assert payload["snaga_predmeta_procent"] == 62
    assert payload["trigger"] == "manual_refresh"
    assert payload["verifikacija_odluka"] == "approve_with_warning"
    # correlation_id: generisan u funkciji, deljen sa 1.2 audit metadata preko istog stringa
    assert payload["correlation_id"] == corr_id
    assert len(corr_id) == 36  # UUID4 string oblik, ne prazan/None


@pytest.mark.anyio
async def test_emit_genome_event_prev_verzija_defaults_to_none():
    """Prvi ikad refresh predmeta nema staru verziju."""
    from routers import case_dna as cd
    chain = _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(return_value=chain)
    await cd._emit_genome_event(supa, "p", "u", {"verzija": 1}, "upload_trigger")
    assert chain.insert.call_args[0][0]["payload"]["prev_verzija"] is None


@pytest.mark.anyio
async def test_emit_genome_event_swallows_errors():
    from routers import case_dna as cd

    supa = MagicMock()
    supa.table = MagicMock(side_effect=Exception("db down"))

    # ne sme da baci — greska u event-u ne sme da obori glavni zahtev
    await cd._emit_genome_event(supa, "predmet-1", "user-1", {"verzija": 1}, "upload_trigger")


# ═══════════════════════════════════════════════════════════════════════════
# Faza 1.1 — services/event_bus.py — EventType.GENOME_UPDATED
# ═══════════════════════════════════════════════════════════════════════════

def test_genome_updated_event_type_value_is_stable():
    """Zaključava string vrednost — dispatch_pending_events radi EventType(raw_type),
    tipfeler u vrednosti bi tiho pretvorio svaki Genome event u 'unknown_type'."""
    from services.event_bus import EventType
    assert EventType.GENOME_UPDATED.value == "GenomeUpdated"


@pytest.mark.anyio
async def test_dispatch_pending_events_recognizes_genome_updated_type():
    """Posle 1.2 postoji registrovan handler (on_genome_updated) za ovaj tip —
    ovaj test ne proverava handler logiku samu (to radi test ispod), samo da
    dispatch prepoznaje tip (ne pada u 'nepoznat_tip') i markira dispecovanim
    cak i ako handler-ov sopstveni DB poziv (audit_immutable insert) nije
    mock-ovan ovde (log_action sam guta svoje greske, videti shared/audit_immutable.py)."""
    from services import event_bus as eb

    row = {"id": "evt-genome-1", "event_type": "GenomeUpdated", "user_id": "u-1",
           "predmet_id": "p-1", "payload": {"verzija": 2, "trigger": "upload_trigger"},
           "dispatch_attempts": 0}

    marked = []
    def _table(name):
        chain = _make_chain([row] if name == "events" else [])
        def _capture(payload):
            marked.append(payload)
            return chain
        chain.update = MagicMock(side_effect=_capture)
        return chain
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("shared.deps._get_supa", return_value=supa):
        result = await eb.dispatch_pending_events()

    assert result["nepoznat_tip"] == 0
    assert result["dispecovano"] == 1
    assert any("dispatched_at" in m for m in marked)


# ═══════════════════════════════════════════════════════════════════════════
# Faza 1.2 — services/event_bus.py — on_genome_updated (Genome Audit Trail)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_on_genome_updated_writes_audit_row_with_correct_mapping():
    from services.event_bus import Event, EventType, on_genome_updated

    event = Event(
        type=EventType.GENOME_UPDATED,
        user_id="user-1",
        predmet_id="predmet-1",
        payload={
            "verzija": 5,
            "prev_verzija": 4,
            "snaga_predmeta_procent": 71,
            "trigger": "rociste_trigger",
            "correlation_id": "corr-123",
            "verifikacija_odluka": "require_review",
        },
    )

    captured = {}
    async def _fake_log_action(**kwargs):
        captured.update(kwargs)
        return "audit-row-1"

    with patch("shared.audit_immutable.log_action", side_effect=_fake_log_action):
        await on_genome_updated(event)

    assert captured["action"] == "genome_refresh"
    assert captured["user_id"] == "user-1"
    assert captured["resource_type"] == "predmet"
    assert captured["resource_id"] == "predmet-1"
    meta = captured["metadata"]
    assert meta["trigger"] == "rociste_trigger"
    assert meta["agent"] == "case_dna_extractor"
    assert meta["verzija"] == 5
    assert meta["prev_verzija"] == 4
    assert meta["snaga_predmeta_procent"] == 71
    assert meta["correlation_id"] == "corr-123"
    assert meta["verifikacija_odluka"] == "require_review"


@pytest.mark.anyio
async def test_on_genome_updated_swallows_errors():
    from services.event_bus import Event, EventType, on_genome_updated
    event = Event(type=EventType.GENOME_UPDATED, user_id="u", predmet_id="p", payload={})
    with patch("shared.audit_immutable.log_action", side_effect=Exception("db down")):
        await on_genome_updated(event)  # ne sme da baci


@pytest.mark.anyio
async def test_dispatch_pending_events_genome_updated_triggers_real_audit_write():
    """End-to-end: outbox red → dispatch_pending_events() → REGISTROVANI
    on_genome_updated handler (ne rucno prosledjen kao u drugim dispatch
    testovima) → log_action() poziv. Dokazuje da je 1.2 stvarno povezan na
    bus singleton, ne samo da funkcija postoji izolovano."""
    from services import event_bus as eb

    row = {"id": "evt-genome-2", "event_type": "GenomeUpdated", "user_id": "u-1",
           "predmet_id": "p-1",
           "payload": {"verzija": 2, "prev_verzija": 1, "trigger": "manual_refresh",
                       "snaga_predmeta_procent": 55, "correlation_id": "corr-abc"},
           "dispatch_attempts": 0}

    def _table(name):
        return _make_chain([row] if name == "events" else [])
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    captured = {}
    async def _fake_log_action(**kwargs):
        captured.update(kwargs)
        return "audit-1"

    with patch("shared.deps._get_supa", return_value=supa), \
         patch("shared.audit_immutable.log_action", side_effect=_fake_log_action):
        result = await eb.dispatch_pending_events()

    assert result["dispecovano"] == 1
    assert captured.get("action") == "genome_refresh"
    assert captured.get("metadata", {}).get("verzija") == 2
    assert captured.get("metadata", {}).get("correlation_id") == "corr-abc"


# ═══════════════════════════════════════════════════════════════════════════
# Faza 1.2 — routers/case_dna.py — _run_genome_background trigger threading
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_run_genome_background_threads_explicit_trigger():
    """Pre 1.2: funkcija je UVEK pisala 'upload_trigger' bez obzira na
    pozivaoca (poznata greska iz Faze 1.1 checklist-a). Posle 1.2:
    rocista.py/smart_intake.py prosledjuju tacnu vrednost — ovaj test
    proverava da se ta vrednost stvarno prenosi do _save_genome_history i
    _emit_genome_event, ne samo da parametar postoji."""
    from routers import case_dna as cd

    old_genome = {"verzija": 4, "snaga_predmeta_procent": 50}
    docs = [{"id": "d1", "naziv_fajla": "a.pdf", "redni_broj": 1,
             "tekst_sadrzaj": "tekst", "velicina_kb": 10}]

    def _table(name):
        if name == "predmeti":
            return _make_chain({"case_dna": old_genome})
        if name == "predmet_dokumenti":
            return _make_chain(docs)
        return _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=AsyncMock(return_value={"snaga_predmeta_procent": 55})), \
         patch("routers.case_dna._save_genome_history", new=AsyncMock()) as mock_hist, \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock(return_value="corr")) as mock_emit:
        await cd._run_genome_background("predmet-1", "user-1", 50, trigger="rociste_trigger")

    assert mock_hist.call_args[0][-1] == "rociste_trigger"
    # _emit_genome_event(supa, predmet_id, uid, genome, trigger, prev_verzija=stari_verzija)
    emit_args = mock_emit.call_args
    assert emit_args[0][4] == "rociste_trigger"
    assert emit_args.kwargs["prev_verzija"] == 4


# ═══════════════════════════════════════════════════════════════════════════
# Faza 1.3 — routers/case_dna.py — verify_genome() wiring
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_run_genome_background_computes_and_threads_verifikacija():
    """Faza 1.3: _run_genome_background mora da pozove verify_genome() nad
    stvarno ekstrahovanim genomom, upise rezultat u genome['_verifikacija'],
    i prosledi odluku u _emit_genome_event (ne samo da postoji funkcija)."""
    from routers import case_dna as cd

    old_genome = {"verzija": 1, "snaga_predmeta_procent": 50}
    # dokazi_rang referencira dokument koji ne postoji medju docs -> hard flag
    extracted = {
        "snaga_predmeta_procent": 60,
        "dokazi_rang": [{"naziv": "nepostojeci.pdf", "snaga_score": 70, "zvezdice": 4}],
    }
    docs = [{"id": "d1", "naziv_fajla": "a.pdf", "redni_broj": 1,
             "tekst_sadrzaj": "tekst", "velicina_kb": 10}]

    def _table(name):
        if name == "predmeti":
            return _make_chain({"case_dna": old_genome})
        if name == "predmet_dokumenti":
            return _make_chain(docs)
        return _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=AsyncMock(return_value=extracted)), \
         patch("routers.case_dna._save_genome_history", new=AsyncMock()), \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock(return_value="corr")) as mock_emit:
        await cd._run_genome_background("predmet-1", "user-1", 50, trigger="upload_trigger")

    passed_genome = mock_emit.call_args[0][3]
    assert passed_genome["_verifikacija"]["odluka"] == "require_review"
    assert mock_emit.call_args.kwargs["verifikacija_odluka"] == "require_review"


@pytest.mark.anyio
async def test_run_genome_background_skips_verification_on_extraction_error():
    """Ako _extract_genome vrati gresku, nema smisla verifikovati prazan/
    nepotpun rezultat — genome['_verifikacija'] se ne sme postaviti."""
    from routers import case_dna as cd

    old_genome = {"verzija": 1}
    docs = [{"id": "d1", "naziv_fajla": "a.pdf", "redni_broj": 1,
             "tekst_sadrzaj": "tekst", "velicina_kb": 10}]

    def _table(name):
        if name == "predmeti":
            return _make_chain({"case_dna": old_genome})
        if name == "predmet_dokumenti":
            return _make_chain(docs)
        return _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    with patch("routers.case_dna._get_supa", return_value=supa), \
         patch("routers.case_dna._extract_genome", new=AsyncMock(return_value={"greska": "OpenAI down"})), \
         patch("routers.case_dna._save_genome_history", new=AsyncMock()), \
         patch("routers.case_dna._emit_genome_event", new=AsyncMock(return_value="corr")) as mock_emit:
        await cd._run_genome_background("predmet-1", "user-1", None, trigger="upload_trigger")

    passed_genome = mock_emit.call_args[0][3]
    assert "_verifikacija" not in passed_genome
    assert mock_emit.call_args.kwargs["verifikacija_odluka"] is None


# ═══════════════════════════════════════════════════════════════════════════
# Reliability Patch v2 (2026-07-18) — _extract_genome overrides GPT's
# self-reported snaga_predmeta_procent/snaga_predmeta with compute_snaga_score()
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_extract_genome_overrides_gpt_reported_snaga_with_computed_value():
    """Regresioni test za tacan bug otkriven Reality Validation batch-om:
    GPT je anchor-ovao na primer iz prompta (65) bez obzira na predmet.
    _extract_genome mora da IGNORISE GPT-ov broj i racuna svoj iz
    snaga_faktori koje je GPT vratio."""
    from routers import case_dna as cd

    # GPT vraca anchor-ovanih 65% ali njegovi sopstveni faktori impliciraju
    # potpuno drugaciji broj (50 + 30 = 80) — tacno obrazac vidjen u batch-u
    gpt_json = (
        '{"snaga_predmeta_procent": 65, "snaga_predmeta": "srednja", '
        '"snaga_faktori": [{"faktor": "Pisani dokazi", "uticaj": "+20", "opis": "x"}, '
        '{"faktor": "Svedoci", "uticaj": "+10", "opis": "y"}]}'
    )
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=gpt_json))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None,
             "velicina_kb": 5, "tekst_sadrzaj": "neki tekst dokumenta"}]

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await cd._extract_genome(docs)

    # GPT je rekao 65/srednja — backend mora da ignorise to i racuna 80/jaka
    assert result["snaga_predmeta_procent"] == 80
    assert result["snaga_predmeta"] == "jaka"


@pytest.mark.anyio
async def test_extract_genome_different_faktori_produce_different_scores():
    """Dva razlicita GPT odgovora (razliciti snaga_faktori) moraju dati
    razlicit konacan procenat — direktno testira zahtev 'slicni slucajevi
    ne smeju automatski dobiti identican skor'."""
    from routers import case_dna as cd

    def _make_response(faktori_json: str) -> MagicMock:
        content = f'{{"snaga_predmeta_procent": 65, "snaga_faktori": {faktori_json}}}'
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content=content))]
        return resp

    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None,
             "velicina_kb": 5, "tekst_sadrzaj": "tekst"}]

    fake_client_weak = MagicMock()
    fake_client_weak.chat.completions.create = AsyncMock(
        return_value=_make_response('[{"uticaj": "-15"}, {"uticaj": "-10"}]'))
    with patch("openai.AsyncOpenAI", return_value=fake_client_weak):
        weak = await cd._extract_genome(docs)

    fake_client_strong = MagicMock()
    fake_client_strong.chat.completions.create = AsyncMock(
        return_value=_make_response('[{"uticaj": "+20"}, {"uticaj": "+15"}]'))
    with patch("openai.AsyncOpenAI", return_value=fake_client_strong):
        strong = await cd._extract_genome(docs)

    assert weak["snaga_predmeta_procent"] != strong["snaga_predmeta_procent"]


# ═══════════════════════════════════════════════════════════════════════════
# Core Consolidation Sec 1.3 (2026-07-22) — Case Genome jedini vlasnik istine:
# Evidence Vault (predmet_dokazi) mora teci u Genome ekstrakciju kao kontekst,
# ne ostati paralelna, neuporedjena istina.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_extract_genome_includes_evidence_vault_facts_in_prompt():
    """Kad se prosledi 'dokazi' (vec-klasifikovane cinjenice iz
    routers/evidence.py::klasifikuj_i_sacuvaj), _extract_genome MORA da ih
    ukljuci u tekst poslat GPT-u — ranije su bile tiho ignorisane (forensic
    audit 2026-07-22 nalaz: 'Genome nikad ne cita predmet_dokazi')."""
    from routers import case_dna as cd

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content='{"snaga_faktori": []}'))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None,
             "velicina_kb": 5, "tekst_sadrzaj": "tekst dokumenta"}]
    dokazi = [{"tvrdnja": "Tuženi je otkazao ugovor bez upozorenja",
               "kategorija": "cinjenica", "pravni_element": "uzročna veza"}]

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        await cd._extract_genome(docs, dokazi=dokazi)

    sent_messages = fake_client.chat.completions.create.call_args.kwargs["messages"]
    user_content = sent_messages[-1]["content"]
    assert "EVIDENCE VAULT" in user_content
    assert "Tuženi je otkazao ugovor bez upozorenja" in user_content
    assert "uzročna veza" in user_content


@pytest.mark.anyio
async def test_extract_genome_works_without_dokazi_arg():
    """Nazad-kompatibilnost: pozivi bez 'dokazi' (ili sa praznom listom)
    rade identicno kao pre ove izmene — dokazi je opcioni kontekst, ne
    obavezan ulaz."""
    from routers import case_dna as cd

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content='{"snaga_faktori": []}'))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

    docs = [{"redni_broj": 1, "naziv_fajla": "a.pdf", "tip_dokaza": None,
             "velicina_kb": 5, "tekst_sadrzaj": "tekst dokumenta"}]

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await cd._extract_genome(docs)

    assert "greska" not in result
    sent_messages = fake_client.chat.completions.create.call_args.kwargs["messages"]
    assert "EVIDENCE VAULT" not in sent_messages[-1]["content"]


@pytest.mark.anyio
async def test_fetch_dokazi_kontekst_never_raises():
    """Advisory kontekst — pad upita ne sme oboriti Genome ekstrakciju."""
    from routers import case_dna as cd
    supa = MagicMock()
    supa.table.side_effect = RuntimeError("db down")
    result = await cd._fetch_dokazi_kontekst(supa, "pred-1")
    assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# Core Consolidation Sec 1.5 (2026-07-22) — Genome rokovi_kriticni sync u
# predmet_hronologija (stvarna kalendar tabela, ranije nikad ne upisivano).
# ═══════════════════════════════════════════════════════════════════════════

def _chain_dna(select_data):
    c = MagicMock()
    for m in ['select', 'eq', 'is_', 'limit', 'order', 'execute', 'insert']:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock(); r.data = select_data
    c.execute = MagicMock(return_value=r)
    return c


@pytest.mark.anyio
async def test_sync_rokovi_inserts_active_deadline():
    from routers import case_dna as cd
    supa = MagicMock()
    supa.table.return_value = _chain_dna([])  # nema postojecih zapisa
    genome = {"rokovi_kriticni": [
        {"naziv": "Žalbeni rok", "datum": "2026-08-15", "opis": "Propuštanje gubi pravo na žalbu", "status": "aktivan"},
    ]}
    n = await cd._sync_rokovi_to_hronologija(supa, "pred-1", "uid-1", genome)
    assert n == 1
    insert_call = supa.table.return_value.insert.call_args[0][0]
    assert insert_call["datum_iso"] == "2026-08-15"
    assert insert_call["vaznost"] == "kritičan"
    assert insert_call["akter"] == "Genome (AI)"


@pytest.mark.anyio
async def test_sync_rokovi_skips_non_active_status():
    from routers import case_dna as cd
    supa = MagicMock()
    supa.table.return_value = _chain_dna([])
    genome = {"rokovi_kriticni": [
        {"naziv": "Rok", "datum": "2026-01-01", "opis": "x", "status": "prosao"},
        {"naziv": "Rok2", "datum": None, "opis": "y", "status": "nepoznat"},
    ]}
    n = await cd._sync_rokovi_to_hronologija(supa, "pred-1", "uid-1", genome)
    assert n == 0


@pytest.mark.anyio
async def test_sync_rokovi_deduplicates_against_existing():
    from routers import case_dna as cd
    supa = MagicMock()
    # Postojeci zapis sa istim (dogadjaj, datum_iso) — ne sme se duplirati
    supa.table.return_value = _chain_dna([
        {"dogadjaj": "Žalbeni rok: Propuštanje gubi pravo na žalbu", "datum_iso": "2026-08-15"},
    ])
    genome = {"rokovi_kriticni": [
        {"naziv": "Žalbeni rok", "datum": "2026-08-15", "opis": "Propuštanje gubi pravo na žalbu", "status": "aktivan"},
    ]}
    n = await cd._sync_rokovi_to_hronologija(supa, "pred-1", "uid-1", genome)
    assert n == 0


@pytest.mark.anyio
async def test_sync_rokovi_never_raises_on_db_error():
    from routers import case_dna as cd
    supa = MagicMock()
    supa.table.side_effect = RuntimeError("db down")
    genome = {"rokovi_kriticni": [{"naziv": "Rok", "datum": "2026-08-15", "status": "aktivan"}]}
    n = await cd._sync_rokovi_to_hronologija(supa, "pred-1", "uid-1", genome)
    assert n == 0


@pytest.mark.anyio
async def test_sync_rokovi_empty_list_is_noop():
    from routers import case_dna as cd
    supa = MagicMock()
    n = await cd._sync_rokovi_to_hronologija(supa, "pred-1", "uid-1", {"rokovi_kriticni": []})
    assert n == 0
    supa.table.assert_not_called()
