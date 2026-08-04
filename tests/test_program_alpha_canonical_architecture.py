# -*- coding: utf-8 -*-
"""
Program Alpha (2026-08-04) — Canonical Architecture, Masterprompt 001.

Proves the behavior of the canonicalization items actually implemented this
mission (Tier 1 of docs/architecture/CANONICAL_MIGRATION_PLAN.md):
1. Correlation-ID middleware unification (item 8) — the X-Correlation-ID a
   client sees now matches shared/ai_provenance.py's own request context,
   closing the gap 4 prior missions' internal wiring never actually reached.
2. Court Predictor's nivo/procenat unification (item 4) — the confidence
   percentage is now deterministically derived from the same score that
   determines the qualitative level, not a second, independent GPT call.
3. shared/proactive_alerts.py::create_proactive_alert (item 6) — the
   canonical function's own retry + durable-audit-on-exhaustion behavior,
   independent of any one of its 12 call sites.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake-test-key")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")
os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api import app
    return TestClient(app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Correlation-ID middleware unification
# ═══════════════════════════════════════════════════════════════════════════

class TestCorrelationIdUnification:
    def test_middleware_sets_the_canonical_ai_provenance_context(self, client):
        """The exact behavioral claim of this fix: the value returned in the
        X-Correlation-ID response header must be the SAME value
        shared.ai_provenance's own request context was set to during the
        request -- not two independent ids, which was the bug (Finding 1,
        the worst finding across all 6 Program Alpha domain audits)."""
        import shared.ai_provenance as ai_provenance
        captured = {}
        real_set_request_context = ai_provenance.set_request_context

        def _spy(*args, **kwargs):
            cid = real_set_request_context(*args, **kwargs)
            captured["correlation_id"] = cid
            return cid

        with patch("shared.ai_provenance.set_request_context", side_effect=_spy):
            r = client.get("/health")

        assert "correlation_id" in captured
        assert r.headers.get("x-correlation-id") == captured["correlation_id"]

    def test_incoming_header_is_reused_not_replaced(self, client):
        """An incoming X-Correlation-ID must be threaded through to
        ai_provenance's context, not silently overwritten with a fresh mint
        (this was already correct before the fix for the header itself --
        this test guards that the fix didn't regress it)."""
        cid = "incoming-test-cid-12345"
        r = client.get("/health", headers={"X-Correlation-ID": cid})
        assert r.headers.get("x-correlation-id") == cid

    def test_no_independent_correlation_id_var_remains(self):
        """The old, disconnected _correlation_id_var ContextVar must be
        fully gone, not just unused -- a lingering-but-dead second mechanism
        is exactly the kind of latent duplicate this mission exists to
        eliminate structurally, not just stop using."""
        import api
        assert not hasattr(api, "_correlation_id_var")


# ═══════════════════════════════════════════════════════════════════════════
# 2. Court Predictor nivo/procenat unification
# ═══════════════════════════════════════════════════════════════════════════

class TestCourtPredictorConfidenceUnification:
    def test_procenat_is_deterministic_function_of_score_not_llm(self):
        """The exact fix: procenat must be computed by _procenat_iz_score(),
        a pure function of the same score _calc_confidence_nivo() already
        uses -- not a second, independent GPT call. Calling it twice with
        the same score must return the same result (an LLM call would not
        be guaranteed to)."""
        from routers.court_predictor import _procenat_iz_score, _CONFIDENCE_MAX_SCORE

        assert _procenat_iz_score(0) == 20
        assert _procenat_iz_score(_CONFIDENCE_MAX_SCORE) == 80
        # Determinism: same input, same output, every time.
        assert _procenat_iz_score(5) == _procenat_iz_score(5) == _procenat_iz_score(5)
        # Never claims absolute (0% or 100%) certainty.
        for s in range(0, _CONFIDENCE_MAX_SCORE + 1):
            p = _procenat_iz_score(s)
            assert 20 <= p <= 80

    def test_calc_confidence_nivo_returns_score_for_procenat_derivation(self):
        """_calc_confidence_nivo()'s return signature must include the raw
        score (not just the nivo/boja/faktori tuple it returned before this
        fix) -- otherwise the caller has no way to derive procenat from the
        same evidence the nivo itself was computed from."""
        from routers.court_predictor import _calc_confidence_nivo

        result = _calc_confidence_nivo(rag_hits=20, vks_hits=6, kancelarija_data=None, dokazi_count=5)
        assert len(result) == 5
        nivo, boja, faktori_plus, faktori_minus, score = result
        assert isinstance(score, int)
        assert nivo in ("VISOKO", "SREDNJE", "NISKO")

    def test_nivo_and_procenat_can_never_contradict(self):
        """The actual bug this fix eliminates: nivo="NISKO" next to a
        contradictory high procenat (or vice versa) is now structurally
        impossible, because both come from the same score."""
        from routers.court_predictor import _calc_confidence_nivo, _procenat_iz_score

        # A genuinely low-evidence case.
        nivo, _, _, _, score = _calc_confidence_nivo(rag_hits=0, vks_hits=0, kancelarija_data=None, dokazi_count=0)
        procenat = _procenat_iz_score(score)
        assert nivo == "NISKO"
        assert procenat < 50  # low score -> low half of the 20-80 band

        # A genuinely high-evidence case.
        nivo, _, _, _, score = _calc_confidence_nivo(rag_hits=20, vks_hits=6, kancelarija_data={"uzoraka": 10, "win_rate": 80}, dokazi_count=6)
        procenat = _procenat_iz_score(score)
        assert nivo == "VISOKO"
        assert procenat > 50  # high score -> high half of the band


# ═══════════════════════════════════════════════════════════════════════════
# 3. Canonical create_proactive_alert()
# ═══════════════════════════════════════════════════════════════════════════

class TestCanonicalProactiveAlert:
    @pytest.mark.anyio
    async def test_succeeds_on_first_attempt(self):
        from shared.proactive_alerts import create_proactive_alert

        inserted = []
        def _table(name):
            c = MagicMock()
            def _insert(rec):
                inserted.append(rec)
                chain = MagicMock()
                chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "a1"}]))
                return chain
            c.insert = MagicMock(side_effect=_insert)
            return c
        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        ok = await create_proactive_alert(
            supa, user_id="u1", tip="rok_kritican", naslov="Test", opis="Opis", urgentnost="hitna",
        )
        assert ok is True
        assert len(inserted) == 1
        assert inserted[0]["naslov"] == "Test"
        assert inserted[0]["procitana"] is False

    @pytest.mark.anyio
    async def test_retries_then_succeeds(self):
        from shared.proactive_alerts import create_proactive_alert

        attempts = {"n": 0}
        def _table(name):
            c = MagicMock()
            def _insert(rec):
                attempts["n"] += 1
                chain = MagicMock()
                if attempts["n"] < 3:
                    chain.execute = MagicMock(side_effect=Exception("transient"))
                else:
                    chain.execute = MagicMock(return_value=MagicMock(data=[{"id": "a1"}]))
                return chain
            c.insert = MagicMock(side_effect=_insert)
            return c
        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        with patch("asyncio.sleep", new=AsyncMock()):
            ok = await create_proactive_alert(supa, user_id="u1", tip="t", naslov="N", opis="O")
        assert ok is True
        assert attempts["n"] == 3

    @pytest.mark.anyio
    async def test_exhausted_retries_writes_durable_audit_and_returns_false(self):
        """Absorbs Project Phoenix's own proven pattern -- a permanently
        failing insert must never vanish silently."""
        from shared.proactive_alerts import create_proactive_alert

        def _table(name):
            c = MagicMock()
            chain = MagicMock()
            chain.execute = MagicMock(side_effect=Exception("permanent outage"))
            c.insert = MagicMock(return_value=chain)
            return c
        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        audit_calls = []
        async def _fake_log_action(**kwargs):
            audit_calls.append(kwargs)

        with patch("asyncio.sleep", new=AsyncMock()), \
             patch("shared.audit_immutable.log_action", side_effect=_fake_log_action):
            ok = await create_proactive_alert(
                supa, user_id="u1", predmet_id="p1", tip="rok_kritican", naslov="N", opis="O", urgentnost="hitna",
            )

        import asyncio
        await asyncio.sleep(0)  # let the fire-and-forget audit task run

        assert ok is False
        assert len(audit_calls) == 1
        assert audit_calls[0]["action"] == "proactive_alert_insert_failed"
        assert audit_calls[0]["user_id"] == "u1"
        assert audit_calls[0]["resource_id"] == "p1"

    @pytest.mark.anyio
    async def test_retry_internally_false_makes_a_single_attempt_no_sleep(self):
        """Mission Olympus governance review (2026-08-04, Backend Engineering
        Review's F-5 finding): the internal blocking retry compounds badly
        with dispatch_pending_events()'s serial batch loop and migration
        091's stale-claim window under a sustained outage. Callers already
        inside an outer retry (the 3 services/event_bus.py handlers) must be
        able to opt out of the inner one entirely -- proves exactly one
        insert attempt is made and asyncio.sleep is never called."""
        from shared.proactive_alerts import create_proactive_alert

        attempts = {"n": 0}
        def _table(name):
            c = MagicMock()
            def _insert(rec):
                attempts["n"] += 1
                chain = MagicMock()
                chain.execute = MagicMock(side_effect=Exception("permanent outage"))
                return chain
            c.insert = MagicMock(side_effect=_insert)
            return c
        supa = MagicMock()
        supa.table = MagicMock(side_effect=_table)

        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep, \
             patch("shared.audit_immutable.log_action", new=AsyncMock()):
            ok = await create_proactive_alert(
                supa, user_id="u1", tip="rok_kritican", naslov="N", opis="O",
                retry_internally=False,
            )

        assert ok is False
        assert attempts["n"] == 1  # exactly one attempt, no retry
        mock_sleep.assert_not_awaited()  # no blocking backoff at all

    def test_event_bus_handlers_opt_out_of_internal_retry(self):
        """Structural proof the 3 Event Bus handlers actually pass
        retry_internally=False as a real keyword argument, not just that
        the parameter exists somewhere. Counts only actual keyword-argument
        lines (a trailing comma, not inside a `#` comment) so an explanatory
        comment that happens to mention the same text doesn't inflate the
        count."""
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent / "services" / "event_bus.py").read_text(encoding="utf-8")
        real_args = [
            line for line in src.splitlines()
            if line.strip().startswith("retry_internally=False,")
        ]
        assert len(real_args) == 3

    def test_action_name_is_auditable(self):
        from shared.audit_immutable import AUDITABLE_ACTIONS
        assert "proactive_alert_insert_failed" in AUDITABLE_ACTIONS

    def test_no_direct_insert_call_sites_remain_outside_the_canonical_module(self):
        """Structural proof the migration is complete, not partial -- per
        this mission's own prohibition on 'privremena rešenja koja ostaju u
        kodu' (half-migrated call sites left behind)."""
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent
        hits = [
            str(f) for f in repo_root.rglob("*.py")
            if "tests" not in f.parts and "__pycache__" not in f.parts
            and f.name != "proactive_alerts.py"
            and '.table("proactive_alerts").insert' in f.read_text(encoding="utf-8", errors="replace")
        ]
        assert hits == [], f"direct proactive_alerts insert found outside the canonical module: {hits}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Embedding model canonicalization (item 3, corrected during Phase 9
#    governance review to cover 4 additional live-application call sites
#    the original diagnostic missed)
# ═══════════════════════════════════════════════════════════════════════════

class TestEmbeddingModelCanonicalization:
    def test_all_9_live_call_sites_import_the_canonical_constant(self):
        """Mission Olympus's Architecture Review Agent (Phase 9) found the
        original diagnostic's '5 routers' framing missed 4 more live
        application call sites (api.py x2, uploaded_doc/ingest.py,
        drafting/playbook.py, interni_stavovi.py) -- fixed in the same
        pass, proven here so this claim can't silently regress."""
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent
        live_files = [
            "routers/auto_discovery.py", "routers/batch_ingest.py", "routers/knowledge_base.py",
            "routers/law_upload.py", "routers/proof.py", "api.py", "uploaded_doc/ingest.py",
            "drafting/playbook.py", "interni_stavovi.py",
        ]
        for rel in live_files:
            src = (repo_root / rel).read_text(encoding="utf-8", errors="replace")
            assert "EMBEDDING_MODEL" in src, f"{rel} does not reference the canonical EMBEDDING_MODEL constant"
            assert '"text-embedding-3-large"' not in src, f"{rel} still hardcodes the model string literal"

    def test_standalone_scripts_confirmed_not_imported_by_live_app(self):
        """These are correctly out of this mission's scope (manually-run
        ingestion/diagnostic tools, not the request-serving app) -- this
        test locks in that classification so a future change to any of
        them doesn't silently make it live-application code without this
        canonicalization being revisited."""
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent
        standalone = [
            "debug_rag.py", "diag_a6_prod.py", "diag_crypto_coverage.py",
            "ingest_glossary_vasp_casp.py", "ingest_kz.py", "ingest_laws.py",
            "ingest_misljenja.py", "scrape_zdi_mca.py",
        ]
        all_py = list(repo_root.rglob("*.py"))
        for rel in standalone:
            stem = Path(rel).stem
            importers = [
                str(f) for f in all_py
                if f.name != rel and "__pycache__" not in f.parts
                and (f"import {stem}" in f.read_text(encoding="utf-8", errors="replace")
                     or f"from {stem} import" in f.read_text(encoding="utf-8", errors="replace"))
            ]
            assert importers == [], f"{rel} is imported by {importers} -- no longer a standalone script, revisit EMBEDDING_MODEL scope"
