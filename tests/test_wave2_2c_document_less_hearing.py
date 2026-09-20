# -*- coding: utf-8 -*-
"""
VINDEX AI V1, Wave 2, Task 2C -- ROCISTE_ZAKAZANO on document-less matters.

PROVEN PROBLEM (found empirically while writing Task 2B's own tests): a
matter with zero uploaded documents (a valid, normal lifecycle state -- a
lawyer can schedule a hearing before uploading anything) makes
_consequence_genome_refresh's own before/after verzija comparison see
None -> None. routers/case_dna.py::_do_genome_refresh's own D-1 guard
ALREADY returns early without bumping verzija in exactly this case ("no
document has text -- Genome does not refresh"), by design. The bug was in
_consequence_genome_refresh treating that legitimate no-op identically to
a genuine silently-swallowed failure: it raised, the event retried to
MAX_DISPATCH_ATTEMPTS, and dead-lettered -- so refresh_case_actions and
project_notifications, registered AFTER genome_refresh for ROCISTE_
ZAKAZANO, never got to run. A document-less matter's scheduled hearing
never became a worklist action or a deadline notification.

Fix: services/case_evolution.py::_consequence_genome_refresh now verifies
"no source material" against actual data (routers/case_dna.py's own
_razdvoji_dokumente_po_tekstu, not a second copy of the predicate) before
treating None -> None as a failure. DOCUMENT_ACCEPTED's own verification
is unchanged -- it only fires once a document was just accepted, so this
branch is a structural no-op there.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-test-key")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

from datetime import date, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api import app  # noqa: E402,F401 -- bootstraps the full import graph safely

from services.event_bus import Event, EventType  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Fake Postgres -- same proven harness as Wave 2 Task 2B's own tests.
# ═══════════════════════════════════════════════════════════════════════════

class _FakeQuery:
    def __init__(self, rows_ref):
        self._rows_ref = rows_ref
        self._filtered = list(rows_ref)
        self._op = "select"
        self._payload = None
        self._single = False

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def upsert(self, row, on_conflict=None, ignore_duplicates=False):
        self._op = "upsert"
        self._payload = row
        self._on_conflict = [c.strip() for c in (on_conflict or "").split(",") if c.strip()]
        self._ignore_duplicates = ignore_duplicates
        return self

    def eq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) == val]
        return self

    def neq(self, col, val):
        self._filtered = [r for r in self._filtered if r.get(col) != val]
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self._filtered = [r for r in self._filtered if r.get(col) in vals]
        return self

    @property
    def not_(self):
        return _NotFilter(self)

    def is_(self, col, val):
        if val in ("null", None):
            self._filtered = [r for r in self._filtered if r.get(col) is None]
        return self

    def gte(self, col, val):
        self._filtered = [r for r in self._filtered if (r.get(col) or "") >= val]
        return self

    def lt(self, col, val):
        self._filtered = [r for r in self._filtered if (r.get(col) or 0) < val]
        return self

    def order(self, col, desc=False):
        self._filtered.sort(key=lambda r: r.get(col) or "", reverse=desc)
        return self

    def limit(self, _n):
        return self

    def maybe_single(self):
        self._single = True
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        res = MagicMock()
        if self._op == "insert":
            new_row = dict(self._payload)
            new_row.setdefault("id", f"gen-{len(self._rows_ref) + 1}")
            new_row.setdefault("status", "open")
            self._rows_ref.append(new_row)
            res.data = [new_row]
        elif self._op == "update":
            for r in self._filtered:
                r.update(self._payload)
            res.data = list(self._filtered)
        elif self._op == "upsert":
            keys = self._on_conflict or ["id"]
            existing = next(
                (r for r in self._rows_ref if all(r.get(k) == self._payload.get(k) for k in keys)),
                None,
            )
            if existing is not None:
                if self._ignore_duplicates:
                    res.data = []
                else:
                    existing.update(self._payload)
                    res.data = [existing]
            else:
                new_row = dict(self._payload)
                new_row.setdefault("id", f"gen-{len(self._rows_ref) + 1}")
                self._rows_ref.append(new_row)
                res.data = [new_row]
        else:
            res.data = (self._filtered[0] if self._filtered else None) if self._single else list(self._filtered)
        return res


class _NotFilter:
    def __init__(self, query: "_FakeQuery"):
        self._query = query

    def in_(self, col, vals):
        vals = set(vals)
        self._query._filtered = [r for r in self._query._filtered if r.get(col) not in vals]
        return self._query

    def eq(self, col, val):
        self._query._filtered = [r for r in self._query._filtered if r.get(col) != val]
        return self._query

    def is_(self, col, val):
        if val in ("null", None):
            self._query._filtered = [r for r in self._query._filtered if r.get(col) is not None]
        return self._query


class _FakeSupa:
    def __init__(self, tables: dict):
        self.tables = {k: list(v) for k, v in tables.items()}

    def table(self, name):
        self.tables.setdefault(name, [])
        return _FakeQuery(self.tables[name])


def _predmet_row(case_dna=None):
    return {"id": "pred-1", "user_id": "user-1", "naziv": "Predmet A", "case_dna": case_dna or {}, "tip": "parnicno", "status": "aktivan"}


def _rociste_row_soon():
    return {
        "id": "roc-1", "predmet_id": "pred-1",
        "sud": "Osnovni sud", "datum": (date.today() + timedelta(days=5)).isoformat(),
        "status": "zakazano",
    }


def _event(event_type=EventType.ROCISTE_ZAKAZANO, event_id="evt-1"):
    return Event(type=event_type, user_id="user-1", predmet_id="pred-1",
                 payload={}, correlation_id="corr-1", event_id=event_id)


def _make_fake(with_hearing=True, dokumenti=None, case_dna=None):
    return _FakeSupa({
        "predmeti": [_predmet_row(case_dna)],
        "predmet_dokazi": [],
        "predmet_dokumenti": list(dokumenti or []),
        "rocista": [_rociste_row_soon()] if with_hearing else [],
        "case_actions": [],
        "notifications": [],
        "predmet_genome_history": [],
        "case_evolution_consequences": [],
    })


# ═══════════════════════════════════════════════════════════════════════════
# 1. _consequence_genome_refresh: document-less no-op vs genuine failure
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_document_less_matter_genome_refresh_is_noop_not_failure():
    from services.case_evolution import _consequence_genome_refresh

    fake = _make_fake(dokumenti=[])
    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock(return_value=None)):
        result = await _consequence_genome_refresh(_event())

    assert result == "skipped_no_genome_source"
    # No fake genome state was fabricated -- verzija stays exactly what it was (None).
    assert fake.tables["predmeti"][0]["case_dna"].get("verzija") is None


@pytest.mark.anyio
async def test_matter_with_only_textless_documents_is_also_noop():
    """A document that exists but has no extracted text (failed OCR, empty
    file) is the SAME 'no genome source' state as no document at all --
    routers/case_dna.py's own D-1 guard treats them identically."""
    from services.case_evolution import _consequence_genome_refresh

    fake = _make_fake(dokumenti=[{"id": "doc-1", "predmet_id": "pred-1", "tekst_sadrzaj": "   "}])
    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock(return_value=None)):
        result = await _consequence_genome_refresh(_event())

    assert result == "skipped_no_genome_source"


@pytest.mark.anyio
async def test_matter_with_text_bearing_document_and_stuck_verzija_still_raises():
    """Regression guard: a matter that DOES have real source material, but
    verzija still didn't move (a genuinely swallowed LLM/extraction
    failure), must still raise -- proves Task 2C did not weaken the
    genuine integrity check, only remove the false dependency."""
    from services.case_evolution import _consequence_genome_refresh

    fake = _make_fake(dokumenti=[{"id": "doc-1", "predmet_id": "pred-1", "tekst_sadrzaj": "Presuda broj 123..."}])
    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock(return_value=None)):
        with pytest.raises(RuntimeError, match="verzija unchanged"):
            await _consequence_genome_refresh(_event())


@pytest.mark.anyio
async def test_document_accepted_verification_unchanged_for_real_document():
    """DOCUMENT_ACCEPTED's own path is untouched: a real document exists
    (as it always does when this event fires) and verzija genuinely
    updates -- success reported normally, not through the new no-op
    branch."""
    from services.case_evolution import _consequence_genome_refresh

    fake = _make_fake(dokumenti=[{"id": "doc-1", "predmet_id": "pred-1", "tekst_sadrzaj": "Ugovor o radu..."}])

    async def _bump_verzija(*_a, **_kw):
        fake.tables["predmeti"][0]["case_dna"] = {"verzija": 1}

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock(side_effect=_bump_verzija)):
        result = await _consequence_genome_refresh(_event(EventType.DOCUMENT_ACCEPTED))

    assert result == "1"


# ═══════════════════════════════════════════════════════════════════════════
# 2. End-to-end: ROCISTE_ZAKAZANO on a document-less matter completes
#    without dead-lettering, and refresh_case_actions/project_notifications
#    actually run
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_rociste_zakazano_document_less_completes_and_produces_action():
    from services.case_evolution import handle_case_changed

    fake = _make_fake(with_hearing=True, dokumenti=[])

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock(return_value=None)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        # Must not raise / must not exhaust retries -- a single call
        # completing cleanly IS the proof there is no dead-letter here.
        await handle_case_changed(_event(EventType.ROCISTE_ZAKAZANO, event_id="evt-hearing-1"))

    open_actions = [r for r in fake.tables["case_actions"] if r.get("status") == "open"]
    assert any(a["tip"] == "PRIPREMITI_PODNESAK" for a in open_actions)
    # The deadline notification actually got projected -- the specific
    # "rok" vs "hitan_rok" split is priority calibration, not what this
    # task is about.
    assert len(fake.tables["notifications"]) == 1
    assert fake.tables["notifications"][0]["tip"] in ("rok", "hitan_rok")


@pytest.mark.anyio
async def test_rociste_zakazano_reschedule_does_not_duplicate_action():
    """Same hearing rescheduled (2nd ROCISTE_ZAKAZANO for the same
    predmet_id) must reconcile to the SAME logical action (update, not a
    2nd open row) -- the existing dedupe_key mechanism, now actually
    reachable for a document-less matter."""
    from services.case_evolution import handle_case_changed

    fake = _make_fake(with_hearing=True, dokumenti=[])

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock(return_value=None)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await handle_case_changed(_event(EventType.ROCISTE_ZAKAZANO, event_id="evt-hearing-1"))
        # Reschedule: same hearing, new date -- same rociste id, own row updated.
        fake.tables["rocista"][0]["datum"] = (date.today() + timedelta(days=9)).isoformat()
        await handle_case_changed(_event(EventType.ROCISTE_ZAKAZANO, event_id="evt-hearing-2"))

    open_actions = [r for r in fake.tables["case_actions"] if r.get("status") == "open"]
    hearing_actions = [a for a in open_actions if a["tip"] == "PRIPREMITI_PODNESAK"]
    assert len(hearing_actions) == 1


@pytest.mark.anyio
async def test_rociste_zakazano_retry_same_event_id_is_idempotent():
    """A retry of the SAME event_id (e.g. outer dispatch re-processing
    after a transient error in a later consequence) must not re-run
    genome_refresh or duplicate any consequence -- the existing
    case_evolution_consequences claim/completed tracking, exercised here
    for a document-less matter specifically."""
    from services.case_evolution import handle_case_changed

    fake = _make_fake(with_hearing=True, dokumenti=[])

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock(return_value=None)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        await handle_case_changed(_event(EventType.ROCISTE_ZAKAZANO, event_id="evt-retry-1"))
        n_after_first = len(fake.tables["case_actions"])
        await handle_case_changed(_event(EventType.ROCISTE_ZAKAZANO, event_id="evt-retry-1"))
        n_after_retry = len(fake.tables["case_actions"])

    assert n_after_retry == n_after_first


# ═══════════════════════════════════════════════════════════════════════════
# 3. Missing required hearing data fails honestly (no fabricated action) --
#    pre-existing behavior, unchanged by this task; guarded here so a
#    future change to Rule 1 cannot silently start fabricating a deadline
#    from an incomplete rociste row.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_rociste_missing_datum_produces_no_fabricated_action():
    from services.case_evolution import _consequence_refresh_case_actions

    fake = _make_fake(with_hearing=False, dokumenti=[])
    fake.tables["rocista"] = [{"id": "roc-bad", "predmet_id": "pred-1", "sud": "Osnovni sud", "datum": None, "status": "zakazano"}]

    with patch("services.case_evolution._get_supa", return_value=fake):
        await _consequence_refresh_case_actions(_event(EventType.ROCISTE_ZAKAZANO))

    # An active, document-less matter also trips the risk engine's own
    # "missing expected document type" rules -- this test is specifically
    # about the malformed rociste row not fabricating a PRIPREMITI_PODNESAK
    # deadline action from a missing datum, not about the total count.
    open_actions = [r for r in fake.tables["case_actions"] if r["status"] == "open"]
    assert not any(a["tip"] == "PRIPREMITI_PODNESAK" for a in open_actions)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Founder's own follow-up on the Wave 2 Task 2D corrective closure
#    review: a matter that ALREADY has processed documents, receiving
#    ROCISTE_ZAKAZANO, must not have its genuinely-successful genome
#    refresh confused with the None/None no-op this task's fix added.
#    _do_genome_refresh unconditionally sets genome["verzija"] =
#    stari_verzija + 1 on every successful run with at least one
#    text-bearing document (routers/case_dna.py, read directly, not
#    assumed) -- so a matter with real source material can never
#    legitimately land in the None/None (or equal-and-non-None) branch on
#    a genuinely successful run; only a genuine failure (the "greska" path,
#    which returns without writing) can produce a stuck verzija when
#    documents exist. This test proves the SUCCESS path end-to-end, not
#    just the isolated unit-level check test_matter_with_text_bearing_
#    document_and_stuck_verzija_still_raises (which proves the FAILURE
#    path is still honestly reported).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_rociste_zakazano_matter_with_documents_genome_success_not_confused_with_noop():
    from services.case_evolution import handle_case_changed

    fake = _make_fake(with_hearing=True, dokumenti=[
        {"id": "doc-1", "predmet_id": "pred-1", "tekst_sadrzaj": "Ugovor o radu, čl. 5..."},
    ])

    async def _bump_verzija(*_a, **_kw):
        fake.tables["predmeti"][0]["case_dna"] = {"verzija": 1}

    with patch("services.case_evolution._get_supa", return_value=fake), \
         patch("routers.case_dna._run_genome_background", new=AsyncMock(side_effect=_bump_verzija)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()):
        # Must not raise -- a genuinely successful genome bump (None -> 1)
        # must never be treated as the document-less no-op, nor as a
        # failure.
        await handle_case_changed(_event(EventType.ROCISTE_ZAKAZANO, event_id="evt-docs-hearing-1"))

    assert fake.tables["predmeti"][0]["case_dna"]["verzija"] == 1
    open_actions = [r for r in fake.tables["case_actions"] if r.get("status") == "open"]
    assert any(a["tip"] == "PRIPREMITI_PODNESAK" for a in open_actions)
