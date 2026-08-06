# -*- coding: utf-8 -*-
"""
Program Tau, Master Sprint 002 (2026-08-06) — "Canonical Case Context Engine".

Tests proving:
  1. shared/case_context.py::context_field carries the mandated
     {value, source, owner, refresh, timestamp} shape on every field.
  2. build_case_context() assembles all 13 contract fields from canonical
     sources, with zero GPT calls anywhere in the module.
  3. The Document Visibility Engine's own central claim: at 500/1000-document
     scale, no document is ever silently dropped -- every one is either in
     the Layer 4 excerpt set or listed with a working Layer 5 retrieval path.
  4. Determinism -- same input produces the same output across repeated
     calls/simulated restarts, and concurrent calls for different cases don't
     interfere (no shared mutable state).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Fake Supabase client -- minimal chainable query builder
# ═══════════════════════════════════════════════════════════════════════════

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, data):
        self._data = data
        self._single = False
        self._id_filter = None
        self._id_in_filter = None

    def select(self, *a, **k): return self
    def eq(self, field, value):
        # Only "id" is filtered for real -- get_document_full_text's own
        # lookup needs exact-row semantics; every other .eq() call in this
        # module (predmet_id/user_id/status) is a no-op here since every
        # fixture's own table data is already scoped to the case under test.
        if field == "id":
            self._id_filter = value
        return self
    def in_(self, field, values):
        # Program Lambda, Master Sprint 001: needed by
        # shared/case_context.py::_fetch_document_texts's own targeted
        # tekst_sadrzaj fetch (.in_("id", dokument_ids)) -- added when that
        # code silently fell back to its own fail-soft empty-dict path
        # against this fake (AttributeError swallowed, excerpts went empty,
        # and NOTHING in this file's own existing tests asserted on excerpt
        # CONTENT to catch it). Real supabase-py already supports .in_();
        # this fake needed to catch up.
        if field == "id":
            self._id_in_filter = set(values)
        return self
    def is_(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def desc(self, *a, **k): return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        data = self._data
        if self._id_filter is not None and isinstance(data, list):
            data = [row for row in data if row.get("id") == self._id_filter]
        if self._id_in_filter is not None and isinstance(data, list):
            data = [row for row in data if row.get("id") in self._id_in_filter]
        if self._single:
            return _FakeResult(data if isinstance(data, dict) else (data[0] if data else None))
        return _FakeResult(data)


class _FakeSupa:
    def __init__(self, tables: dict):
        self._tables = tables

    def table(self, name):
        return _FakeQuery(self._tables.get(name, []))


_UNSET = object()


def _base_tables(predmet=_UNSET, dokumenti=None, dokazi=None, rocista=None,
                  case_actions=None, hronologija=None, komentari=None):
    return {
        "predmeti": {
            "id": "p1", "naziv": "Test predmet", "tip_postupka": "parnicno",
            "sud": "Osnovni sud", "status": "aktivan", "stranka": "A", "protivnik": "B",
            "case_dna": {},
        } if predmet is _UNSET else predmet,
        "predmet_dokumenti": dokumenti or [],
        "predmet_dokazi": dokazi or [],
        "rocista": rocista or [],
        "case_actions": case_actions or [],
        "predmet_hronologija": hronologija or [],
        "predmet_komentari": komentari or [],
    }


def _make_docs(n, id_prefix="d"):
    """n documents, deliberately created out of chronological order (id N created
    BEFORE id N-1 for half of them) to prove selection doesn't depend on fetch order."""
    docs = []
    for i in range(1, n + 1):
        docs.append({
            "id": f"{id_prefix}{i}", "naziv_fajla": f"dokument_{i}.pdf",
            "created_at": f"2026-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}T00:00:00Z",
            "tekst_sadrzaj": f"Sadržaj dokumenta broj {i}. " * 50,
            "tip_dokaza": "ugovor", "status": "obradjen", "redni_broj": i,
        })
    return docs


# ═══════════════════════════════════════════════════════════════════════════
# context_field shape
# ═══════════════════════════════════════════════════════════════════════════

def test_context_field_shape():
    from shared.case_context import context_field
    f = context_field({"x": 1}, source="case_actions", owner="case_evolution.py", refresh="event-driven")
    assert set(f.keys()) == {"value", "source", "owner", "refresh", "timestamp"}
    assert f["value"] == {"x": 1}
    assert f["source"] == "case_actions"
    assert f["owner"] == "case_evolution.py"
    assert f["refresh"] == "event-driven"
    assert f["timestamp"]


# ═══════════════════════════════════════════════════════════════════════════
# build_case_context -- all 13 fields, zero GPT calls
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_build_case_context_predmet_not_found():
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables(predmet=None))
    result = await build_case_context("missing-id", "u1", supa)
    assert result["error"] == "predmet_not_found"


@pytest.mark.anyio
async def test_build_case_context_has_all_13_contract_fields():
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables())
    result = await build_case_context("p1", "u1", supa)
    expected = {
        "contract_version", "case_identity", "participants", "procedural_status",
        "timeline", "key_facts", "evidence_graph", "contradictions", "missing_evidence",
        "deadlines", "active_actions", "readiness", "relevant_documents",
        "document_summaries", "audit_metadata",
    }
    assert expected.issubset(result.keys())
    for field in expected - {"contract_version"}:
        assert set(result[field].keys()) == {"value", "source", "owner", "refresh", "timestamp"}, field


def test_case_context_module_makes_zero_gpt_calls():
    """Structural proof, not a behavior assumption: the module's own source
    never references the OpenAI SDK or a chat-completion call."""
    import shared.case_context as cc
    src = open(cc.__file__, encoding="utf-8").read()
    assert "openai" not in src.lower()
    assert "chat.completions" not in src


@pytest.mark.anyio
async def test_key_facts_none_when_genome_not_computed():
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables(predmet={
        "id": "p1", "naziv": "Test", "tip_postupka": "parnicno", "case_dna": {},
    }))
    result = await build_case_context("p1", "u1", supa)
    assert result["key_facts"]["value"] is None


@pytest.mark.anyio
async def test_key_facts_present_when_genome_computed():
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables(predmet={
        "id": "p1", "naziv": "Test", "tip_postupka": "parnicno",
        "case_dna": {"verzija": 1, "pravna_teorija": "Ugovorna odgovornost", "snaga_predmeta_procent": 70},
    }))
    result = await build_case_context("p1", "u1", supa)
    assert result["key_facts"]["value"]["pravna_teorija"] == "Ugovorna odgovornost"


@pytest.mark.anyio
async def test_contradictions_and_missing_evidence_are_disjoint():
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables(predmet={
        "id": "p1", "naziv": "Test", "tip_postupka": "parnicno",
        "case_dna": {
            "verzija": 1,
            "kontradikcije": [{"opis": "Datum se razlikuje", "lokacija_1": "DOK-1", "lokacija_2": "DOK-2", "tezina": "vazna"}],
            "nedostaje": [{"dokument": "Ugovor o zakupu", "hitnost": "kriticno"}],
        },
    }))
    result = await build_case_context("p1", "u1", supa)
    contra_tipovi = {g["tip"] for g in result["contradictions"]["value"]}
    missing_tipovi = {g["tip"] for g in result["missing_evidence"]["value"]}
    assert contra_tipovi == {"KONTRADIKCIJA"}
    assert "KONTRADIKCIJA" not in missing_tipovi


@pytest.mark.anyio
async def test_deadlines_distinguish_past_from_upcoming_program_tau_004():
    """Program Tau, Master Sprint 004 (2026-08-06): rocista has no date filter
    -- past and future hearings were previously undifferentiated in the
    deadlines field (Phase 2's own context-quality finding, item #15).
    Proves the new `proslo` label is computed correctly per row."""
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables(rocista=[
        {"id": "r1", "sud": "Osnovni sud", "datum": "2020-01-01", "status": "odrzano"},
        {"id": "r2", "sud": "Osnovni sud", "datum": "2099-01-01", "status": "zakazano"},
    ]))
    result = await build_case_context("p1", "u1", supa)
    rows = {r["id"]: r for r in result["deadlines"]["value"]}
    assert rows["r1"]["proslo"] is True
    assert rows["r2"]["proslo"] is False


@pytest.mark.anyio
async def test_readiness_reads_case_actions_critical_priority():
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables(case_actions=[
        {"tip": "PRIBAVITI_DOKAZ", "razlog": "Hitno", "prioritet": "critical",
         "rok": None, "dedupe_key": "k1", "status": "open"},
    ]))
    result = await build_case_context("p1", "u1", supa)
    assert result["readiness"]["value"]["status"] == "CRITICAL_GAP"
    assert result["audit_metadata"]["value"]["top_action_dedupe_key"] == "k1"


# ═══════════════════════════════════════════════════════════════════════════
# Document Visibility Engine -- the "no permanently invisible document" proof
# ═══════════════════════════════════════════════════════════════════════════

def test_select_documents_under_cap_includes_everything():
    from shared.case_context import _select_documents
    docs = _make_docs(10)
    included, not_included = _select_documents(docs)
    assert len(included) == 10
    assert not_included == []


def test_select_documents_500_scale_every_document_accounted_for():
    from shared.case_context import _select_documents, MAX_DOCS_INCLUDED
    docs = _make_docs(500)
    included, not_included = _select_documents(docs)
    assert len(included) <= MAX_DOCS_INCLUDED
    included_ids = {d["id"] for d in included}
    not_included_ids = {d["id"] for d in not_included}
    all_ids = {d["id"] for d in docs}
    # THE core claim: union of included + not_included == every document that
    # exists. Nothing is silently dropped -- it's either shown now or listed
    # with an id a caller can retrieve via get_document_full_text.
    assert included_ids | not_included_ids == all_ids
    assert included_ids & not_included_ids == set()


def test_select_documents_1000_scale_every_document_accounted_for():
    from shared.case_context import _select_documents, MAX_DOCS_INCLUDED
    docs = _make_docs(1000)
    included, not_included = _select_documents(docs)
    assert len(included) <= MAX_DOCS_INCLUDED
    assert {d["id"] for d in included} | {d["id"] for d in not_included} == {d["id"] for d in docs}


def test_select_documents_covers_late_documents_not_just_head():
    """The specific bug this engine exists to fix: case_commander.py's old
    _formatiraj_kontekst always showed the SAME first 10 of an unordered
    fetch. Prove the new selector reaches documents from across the full
    redni_broj range, not just the first N."""
    from shared.case_context import _select_documents
    docs = _make_docs(500)
    included, _ = _select_documents(docs)
    included_redni = sorted(d["redni_broj"] for d in included)
    # at least one selected document must come from the back half of the case
    assert any(rb > 250 for rb in included_redni)


def test_select_documents_recency_always_included():
    from shared.case_context import _select_documents, MAX_RECENT_ALWAYS_INCLUDED
    docs = _make_docs(200)
    # make doc "d200" the most recent by created_at
    for d in docs:
        d["created_at"] = "2020-01-01T00:00:00Z"
    docs[-1]["created_at"] = "2030-01-01T00:00:00Z"
    included, _ = _select_documents(docs)
    included_ids = {d["id"] for d in included}
    assert "d200" in included_ids


def test_select_documents_deterministic_across_repeated_calls():
    from shared.case_context import _select_documents
    docs = _make_docs(500)
    run1_included, run1_not = _select_documents(docs)
    run2_included, run2_not = _select_documents(docs)
    assert [d["id"] for d in run1_included] == [d["id"] for d in run2_included]
    assert [d["id"] for d in run1_not] == [d["id"] for d in run2_not]


def test_select_documents_out_of_input_order_still_deterministic():
    """Same document SET, different input ORDER (simulates a DB returning rows
    in a different sequence on a different call) -- selection by recency +
    redni_broj must not depend on incoming list order."""
    from shared.case_context import _select_documents
    docs = _make_docs(300)
    shuffled = list(reversed(docs))
    inc_a, _ = _select_documents(docs)
    inc_b, _ = _select_documents(shuffled)
    assert {d["id"] for d in inc_a} == {d["id"] for d in inc_b}


@pytest.mark.anyio
async def test_not_included_documents_are_retrievable_via_layer_5():
    from shared.case_context import build_case_context, get_document_full_text
    docs = _make_docs(300)
    supa = _FakeSupa(_base_tables(dokumenti=docs))
    result = await build_case_context("p1", "u1", supa)
    not_included = result["relevant_documents"]["value"]["not_included_but_retrievable"]
    assert len(not_included) > 0
    target = not_included[0]
    fetched = await get_document_full_text("p1", "u1", target["dokument_id"], supa)
    assert fetched["found"] is True
    assert fetched["naziv"] == target["naziv"]
    assert "Sadržaj dokumenta" in fetched["tekst_sadrzaj"]


@pytest.mark.anyio
async def test_get_document_full_text_not_found_is_explicit_not_an_exception():
    from shared.case_context import get_document_full_text
    supa = _FakeSupa(_base_tables())
    result = await get_document_full_text("p1", "u1", "does-not-exist", supa)
    assert result == {"found": False, "dokument_id": "does-not-exist"}


# ═══════════════════════════════════════════════════════════════════════════
# Determinism across simulated restarts + no cross-talk between parallel calls
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_build_case_context_deterministic_across_simulated_restarts():
    """Two independent build_case_context() calls, each against a FRESH
    _FakeSupa instance built from the same underlying data (simulating two
    separate process runs / a restart) must produce identical results, apart
    from the per-call timestamp fields."""
    from shared.case_context import build_case_context

    def _fresh_supa():
        return _FakeSupa(_base_tables(dokumenti=_make_docs(50)))

    r1 = await build_case_context("p1", "u1", _fresh_supa())
    r2 = await build_case_context("p1", "u1", _fresh_supa())

    def _strip_timestamps(d):
        return {k: (v["value"] if isinstance(v, dict) and "timestamp" in v else v) for k, v in d.items()}

    s1, s2 = _strip_timestamps(r1), _strip_timestamps(r2)
    # audit_metadata.generated_at also varies per call -- normalize it too
    s1["audit_metadata"].pop("generated_at", None)
    s2["audit_metadata"].pop("generated_at", None)
    assert s1 == s2


@pytest.mark.anyio
async def test_include_documents_false_skips_document_fetch_but_keeps_field_shape():
    """Lightweight mode for portfolio-wide callers (morning_briefing.py):
    relevant_documents/document_summaries must still carry the mandated
    {value, source, owner, refresh, timestamp} shape, but explicitly say
    documents were not fetched -- never silently imply zero documents exist."""
    from shared.case_context import build_case_context
    docs = _make_docs(50)
    supa = _FakeSupa(_base_tables(dokumenti=docs))
    result = await build_case_context("p1", "u1", supa, include_documents=False)
    rel = result["relevant_documents"]
    assert set(rel.keys()) == {"value", "source", "owner", "refresh", "timestamp"}
    assert rel["value"]["included"] == []
    assert rel["value"]["fetched_this_call"] is False
    assert rel["value"]["total_documents"] is None
    assert "not fetched" in rel["source"]
    # cheap fields must be completely unaffected by the lightweight flag
    assert result["readiness"]["value"]["status"]
    assert result["case_identity"]["value"]


@pytest.mark.anyio
async def test_included_document_excerpts_carry_real_text_content():
    """Program Lambda, Master Sprint 001: _fetch_raw's own predmet_dokumenti
    query no longer selects tekst_sadrzaj (metadata-only, for scaling --
    see that function's own comment); build_case_context() now fetches text
    for the selected documents in a 2nd, targeted query
    (_fetch_document_texts). This is the one test in this file that actually
    asserts on EXCERPT CONTENT rather than just count/id/naziv -- its own
    absence previously let a real regression (excerpts silently going empty)
    pass all 27 pre-existing tests in this file undetected."""
    from shared.case_context import build_case_context
    docs = _make_docs(5)
    supa = _FakeSupa(_base_tables(dokumenti=docs))
    result = await build_case_context("p1", "u1", supa, include_documents=True)
    included = result["relevant_documents"]["value"]["included"]
    assert len(included) == 5
    for item in included:
        assert item["excerpt"], f"excerpt for {item['naziv']} is empty -- text fetch did not work"
        assert "Sadržaj dokumenta" in item["excerpt"]


@pytest.mark.anyio
async def test_document_metadata_query_no_longer_selects_tekst_sadrzaj():
    """Structural proof of the fix itself: the predmet_dokumenti query in
    _fetch_raw must not request tekst_sadrzaj -- that column is fetched
    separately, only for the bounded selected subset."""
    import inspect
    from shared import case_context as mod
    src = inspect.getsource(mod._fetch_raw)
    # the metadata query's own .select(...) call, isolated by finding it
    # before the first .eq("predmet_id"...) that follows "predmet_dokumenti"
    idx = src.index('table("predmet_dokumenti")')
    select_call = src[idx: idx + 300]
    assert "tekst_sadrzaj" not in select_call


@pytest.mark.anyio
async def test_include_documents_true_is_still_the_default():
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables(dokumenti=_make_docs(5)))
    result = await build_case_context("p1", "u1", supa)
    assert result["relevant_documents"]["value"]["fetched_this_call"] is True
    assert len(result["relevant_documents"]["value"]["included"]) == 5


@pytest.mark.anyio
async def test_multiple_contradictions_all_captured_not_just_first():
    """Phase 7 forensic attack: 'a contradiction AI cannot see'. Proves all
    contradictions in case_dna reach the contract, not just one."""
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables(predmet={
        "id": "p1", "naziv": "Test", "tip_postupka": "parnicno",
        "case_dna": {
            "verzija": 1,
            "kontradikcije": [
                {"opis": "Kontradikcija 1", "lokacija_1": "DOK-1", "lokacija_2": "DOK-2", "tezina": "kriticna"},
                {"opis": "Kontradikcija 2", "lokacija_1": "DOK-3", "lokacija_2": "DOK-4", "tezina": "vazna"},
                {"opis": "Kontradikcija 3", "lokacija_1": "DOK-5", "lokacija_2": "DOK-6", "tezina": "manja"},
            ],
        },
    }))
    result = await build_case_context("p1", "u1", supa)
    opisi = {g["razlog"] for g in result["contradictions"]["value"]}
    assert opisi == {"Kontradikcija 1", "Kontradikcija 2", "Kontradikcija 3"}


@pytest.mark.anyio
async def test_large_evidence_count_not_silently_truncated():
    """Phase 7 forensic attack: evidence with a large item count must not be
    silently dropped or capped -- evidence_graph is a count/category rollup,
    not a list, so it has no reason to truncate."""
    from shared.case_context import build_case_context
    dokazi = [{"id": f"dk{i}", "snaga": "jak" if i % 2 == 0 else "slab", "kategorija": "pisani", "pravni_element": "x"} for i in range(200)]
    supa = _FakeSupa(_base_tables(dokazi=dokazi))
    result = await build_case_context("p1", "u1", supa)
    graf = result["evidence_graph"]["value"]
    assert graf["ukupno_dokaza"] == 200
    assert graf["po_kategoriji"]["pisani"]["broj"] == 200


@pytest.mark.anyio
async def test_active_action_always_included_even_with_zero_documents():
    """Phase 7 forensic attack: 'an active action not included'. Proves
    active_actions/deadlines are populated unconditionally -- they don't
    depend on the document layer at all, so a document-fetch problem can
    never silently hide an open action or a deadline."""
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables(
        dokumenti=[],
        case_actions=[{"tip": "PRIBAVITI_DOKAZ", "razlog": "Test akcija", "prioritet": "high",
                        "rok": "2026-09-01", "dedupe_key": "k1", "status": "open"}],
        rocista=[{"id": "r1", "sud": "Osnovni sud", "datum": "2026-09-15", "status": "zakazano"}],
    ))
    result = await build_case_context("p1", "u1", supa)
    assert result["active_actions"]["value"][0]["razlog"] == "Test akcija"
    assert result["deadlines"]["value"][0]["sud"] == "Osnovni sud"


@pytest.mark.anyio
async def test_genome_refresh_between_calls_is_reflected_immediately():
    """Phase 7 forensic attack: 'Genome refresh during an AI call'. No cache
    exists (see CANONICAL_CASE_CONTEXT_CONTRACT.md's own Non-goals) -- a
    case_dna change between two calls must be visible on the very next call,
    not stale."""
    from shared.case_context import build_case_context

    tables = _base_tables(predmet={
        "id": "p1", "naziv": "Test", "tip_postupka": "parnicno", "case_dna": {},
    })
    supa = _FakeSupa(tables)

    result_before = await build_case_context("p1", "u1", supa)
    assert result_before["key_facts"]["value"] is None

    # simulate a Genome refresh writing a fresh case_dna mid-session
    tables["predmeti"]["case_dna"] = {"verzija": 2, "pravna_teorija": "Nova teorija"}

    result_after = await build_case_context("p1", "u1", supa)
    assert result_after["key_facts"]["value"]["pravna_teorija"] == "Nova teorija"


@pytest.mark.anyio
async def test_parallel_calls_for_the_same_case_do_not_interfere():
    """Phase 7 forensic attack, same-case variant of the parallel-requests
    scenario -- two concurrent requests for the SAME case must each get a
    complete, correct result, not a partially-overwritten one."""
    from shared.case_context import build_case_context
    supa = _FakeSupa(_base_tables(dokumenti=_make_docs(30)))

    results = await asyncio.gather(*[build_case_context("p1", "u1", supa) for _ in range(5)])
    for r in results:
        assert r["case_identity"]["value"]["id"] == "p1"
        assert len(r["relevant_documents"]["value"]["included"]) == len(results[0]["relevant_documents"]["value"]["included"])


@pytest.mark.anyio
async def test_parallel_calls_for_different_cases_do_not_interfere():
    from shared.case_context import build_case_context

    supa_a = _FakeSupa(_base_tables(predmet={
        "id": "case-a", "naziv": "Predmet A", "tip_postupka": "parnicno", "case_dna": {},
    }))
    supa_b = _FakeSupa(_base_tables(predmet={
        "id": "case-b", "naziv": "Predmet B", "tip_postupka": "krivicno", "case_dna": {},
    }))

    result_a, result_b = await asyncio.gather(
        build_case_context("case-a", "u1", supa_a),
        build_case_context("case-b", "u2", supa_b),
    )
    assert result_a["case_identity"]["value"]["naziv"] == "Predmet A"
    assert result_b["case_identity"]["value"]["naziv"] == "Predmet B"
