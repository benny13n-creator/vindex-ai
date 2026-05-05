"""
Smoke test for B1 audit log.
Sends 3 queries through ask_agent(), fires the audit writes manually,
verifies 3 entries appear in response_audit with all required fields populated.

Usage: python test_audit_b1.py
"""
import asyncio
import hashlib
import os
import sys
import time

# ── required env check ──────────────────────────────────────────────────────
for var in ("OPENAI_API_KEY", "PINECONE_API_KEY", "PINECONE_HOST",
            "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "COHERE_API_KEY"):
    if not os.getenv(var):
        print(f"[SKIP] {var} not set — run from .env context", file=sys.stderr)
        sys.exit(0)

from dotenv import load_dotenv
load_dotenv()

from main import ask_agent, _skini_pii
from app.services.audit_log import _write, _sha, _get_supa

QUERIES = [
    "Koja je kazna za krađu?",
    "Šta je zastarelost potraživanja?",
    "Uslovi za razvod braka?",
]

REQUIRED_FIELDS = {
    "ts", "pipeline_id", "endpoint", "query_hash",
    "response_len", "response_hash", "latency_ms",
}


def _q_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:16]


async def run_smoke_test():
    print("=" * 60)
    print("B1 AUDIT LOG — SMOKE TEST (3 queries)")
    print("=" * 60)

    written_pipeline_ids = []

    for i, q in enumerate(QUERIES, 1):
        print(f"\n[{i}/3] Query: {q[:50]}")
        t0 = time.monotonic()
        result = ask_agent(q)
        latency_ms = int((time.monotonic() - t0) * 1000)

        qh = _q_hash(_skini_pii(q))
        entry = dict(
            endpoint="/api/pitanje",
            query_hash=qh,
            tip="PARNICA",
            confidence=result.get("confidence"),
            top_score=result.get("top_score"),
            top_article=result.get("top_article"),
            top_law=result.get("top_law"),
            response_text=result.get("data", ""),
            latency_ms=latency_ms,
        )

        # Write directly (not fire-and-forget) so we can check immediately
        await _write(**entry)

        # Fetch back from Supabase
        supa = _get_supa()
        rows = supa.table("response_audit").select("*").eq("query_hash", qh).order("ts", desc=True).limit(1).execute()
        if not rows.data:
            print(f"  FAIL — no row found for query_hash={qh}")
            sys.exit(1)

        row = rows.data[0]
        print(f"  pipeline_id  : {row['pipeline_id']}")
        print(f"  query_hash   : {row['query_hash']}")
        print(f"  confidence   : {row['confidence']}")
        print(f"  top_score    : {row['top_score']}")
        print(f"  top_article  : {row['top_article']}")
        print(f"  top_law      : {row['top_law']}")
        print(f"  response_len : {row['response_len']} chars")
        print(f"  response_hash: {row['response_hash']}")
        print(f"  latency_ms   : {row['latency_ms']} ms")
        print(f"  endpoint     : {row['endpoint']}")
        print(f"  tip          : {row['tip']}")

        # Verify all required fields populated
        missing = [f for f in REQUIRED_FIELDS if not row.get(f)]
        if missing:
            print(f"  FAIL — missing fields: {missing}")
            sys.exit(1)

        # Verify response_len matches
        expected_len = len(result.get("data", ""))
        if row["response_len"] != expected_len:
            print(f"  FAIL — response_len mismatch: {row['response_len']} != {expected_len}")
            sys.exit(1)

        # Verify response_hash matches
        expected_hash = _sha(result.get("data", ""), 32)
        if row["response_hash"] != expected_hash:
            print(f"  FAIL — response_hash mismatch")
            sys.exit(1)

        written_pipeline_ids.append(row["pipeline_id"])
        print(f"  PASS")

    print(f"\n{'=' * 60}")
    print(f"ALL 3 ENTRIES VERIFIED IN response_audit")
    print(f"Pipeline IDs: {written_pipeline_ids}")
    print(f"{'=' * 60}")

    # ── failure isolation test ─────────────────────────────────────────────
    print("\n[4/4] Failure isolation test — simulate Supabase unavailable")
    from unittest.mock import patch
    import app.services.audit_log as al_module
    original = al_module._supa

    al_module._supa = None  # knock out the client
    fake_url = "https://nonexistent.supabase.co"
    fake_key = "fake_key_0000000000000000000000000000000000000000000"

    async def _write_with_bad_client(**kwargs):
        # Temporarily override env to force a bad client
        old_url = os.environ.get("SUPABASE_URL")
        old_key = os.environ.get("SUPABASE_SERVICE_KEY")
        os.environ["SUPABASE_URL"] = fake_url
        os.environ["SUPABASE_SERVICE_KEY"] = fake_key
        al_module._supa = None
        try:
            await _write(**kwargs)
        finally:
            if old_url:
                os.environ["SUPABASE_URL"] = old_url
            if old_key:
                os.environ["SUPABASE_SERVICE_KEY"] = old_key
            al_module._supa = None

    try:
        await _write_with_bad_client(
            endpoint="/api/pitanje",
            query_hash="deadbeef00000000",
            tip="PARNICA",
            confidence="HIGH",
            top_score=0.75,
            top_article="Član 1",
            top_law="test",
            response_text="test",
            latency_ms=0,
        )
        print("  PASS — write failure did not raise exception (logged to stderr)")
    except Exception as e:
        print(f"  FAIL — exception escaped: {e}")
        sys.exit(1)
    finally:
        al_module._supa = original

    print("\nSMOKE TEST COMPLETE — B1 audit log operational")


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
