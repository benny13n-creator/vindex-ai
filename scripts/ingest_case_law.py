# -*- coding: utf-8 -*-
"""
Vindex AI — Phase 1.2: Pinecone ingest for VKS case-law chunks.

Upserts 1,479 chunked decisions into namespace ``sudska_praksa`` of the
existing ``vindex-ai`` Pinecone index.  The default namespace (17,688 zakon
vectors) is NEVER touched.

Usage:
    python scripts/ingest_case_law.py --stage seed   # upsert 50-chunk stratified seed, verify, exit
    python scripts/ingest_case_law.py --stage full   # upsert remaining 1,429 chunks
    python scripts/ingest_case_law.py --stage all    # seed + full in one run (for automation)
    python scripts/ingest_case_law.py --rollback     # delete all sudska_praksa vectors
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_case_law")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TARGET_NAMESPACE = "sudska_praksa"
EMBEDDING_MODEL = "text-embedding-3-large"
EMBED_BATCH_SIZE = 100
UPSERT_BATCH_SIZE = 100
DEFAULT_NS_EXPECTED = 17707  # updated 2026-05-31: +19 vectors added by ingest_short_15/ingest_glossary_vasp_casp after Phase 1.2
CHUNKED_DIR = Path(__file__).parent.parent / "data" / "sudska_praksa" / "chunked"
STATE_FILE = Path(__file__).parent.parent / "data" / "sudska_praksa" / ".ingest_state.json"

SEED_PER_MATTER = {
    "krivicna": 13,
    "gradjanska": 13,
    "upravna": 12,
    "zastitaprava": 12,
}

SANITY_QUERIES_STAGE1 = [
    {"text": "krađa kako se kvalifikuje", "expected_matter": "Krivična"},
    {"text": "naknada štete ugovor", "expected_matter": "Građanska"},
    {"text": "upravni postupak žalba", "expected_matter": "Upravna"},
]

SANITY_QUERIES_FINAL = [
    {"text": "kvalifikacija teške krađe i razbojništva", "expected_matter": "Krivična"},
    {"text": "naknada štete zbog raskida ugovora o kupoprodaji", "expected_matter": "Građanska"},
    {"text": "rok za žalbu na upravno rešenje", "expected_matter": "Upravna"},
    {"text": "neodlučivanje organa po zahtevu", "expected_matter": "Zaštita prava"},
    {"text": "član 203", "expected_matter": None},  # article cross-reference query
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_SRLATMAP = str.maketrans("žšćčđŽŠĆČĐ", "zsccdZSCCD")


def _ascii_vector_id(chunk_id: str) -> str:
    """Transliterate Serbian special chars to ASCII for Pinecone vector ID requirement."""
    return chunk_id.translate(_SRLATMAP)


def _clean_metadata(meta: dict) -> dict:
    """
    Remove None/null values from metadata dict.
    Pinecone rejects null metadata values; use empty string as sentinel where needed.
    Also remove list fields that are empty (Pinecone accepts empty lists but not null).
    """
    cleaned = {}
    for k, v in meta.items():
        if v is None:
            continue  # drop null fields entirely
        if isinstance(v, list):
            cleaned[k] = [str(x) for x in v]  # ensure list of strings
        else:
            cleaned[k] = v
    return cleaned


_PARENT_TEXT_MAX_CHARS = 900


def _build_parent_text(dec_chunks: list, idx: int) -> str:
    """prev_chunk.text + curr + next_chunk.text — sliding window for parent-child retrieval."""
    parts = []
    if idx > 0:
        parts.append(dec_chunks[idx - 1]["text"])
    parts.append(dec_chunks[idx]["text"])
    if idx < len(dec_chunks) - 1:
        parts.append(dec_chunks[idx + 1]["text"])
    return " [...] ".join(parts)[:_PARENT_TEXT_MAX_CHARS]


def load_chunks(chunked_dir: Path = CHUNKED_DIR) -> list[dict]:
    """Load all chunk records from the 4 matter subdirectories, sorted.

    Each chunk includes parent_text (prev+curr+next chunk text, max 900 chars)
    for parent-child retrieval in retrieve.py.
    """
    all_chunks: list[dict] = []
    for slug in ["krivicna", "gradjanska", "upravna", "zastitaprava"]:
        for df in sorted((chunked_dir / slug).glob("*.json")):
            decision = json.loads(df.read_text(encoding="utf-8"))
            dec_chunks = decision["chunks"]
            for i, chunk in enumerate(dec_chunks):
                raw_meta = {
                    **chunk["metadata"],
                    "text": chunk["text"],
                    "parent_text": _build_parent_text(dec_chunks, i),
                }
                all_chunks.append({
                    "chunk_id": chunk["chunk_id"],
                    "matter_slug": slug,
                    "text": chunk["text"],
                    "metadata": _clean_metadata(raw_meta),
                })
    return all_chunks


def select_seed_chunks(all_chunks: list[dict]) -> list[dict]:
    """Pick first N chunks per matter (stratified seed, sorted by chunk_id within each matter)."""
    by_matter: dict[str, list[dict]] = {slug: [] for slug in SEED_PER_MATTER}
    for c in all_chunks:
        slug = c["matter_slug"]
        if slug in by_matter:
            by_matter[slug].append(c)

    seed: list[dict] = []
    for slug, n in SEED_PER_MATTER.items():
        seed.extend(by_matter[slug][:n])
    return seed


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_batch(texts: list[str], client) -> list[list[float]]:
    """Embed a batch of texts with text-embedding-3-large."""
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [e.embedding for e in resp.data]


# ---------------------------------------------------------------------------
# Pinecone helpers — namespace safety is enforced here
# ---------------------------------------------------------------------------

def _safe_upsert(index, vectors: list[dict], namespace: str) -> None:
    """Upsert with MANDATORY namespace assertion guard."""
    assert namespace == TARGET_NAMESPACE, (
        f"NAMESPACE SAFETY VIOLATION: attempted upsert to '{namespace}', "
        f"expected '{TARGET_NAMESPACE}'. ABORTING."
    )
    index.upsert(vectors=vectors, namespace=namespace)


def get_namespace_counts(index) -> dict[str, int]:
    """Return {namespace_name: vector_count}. Maps '__default__' to '' for display."""
    stats = index.describe_index_stats()
    ns_map = stats.namespaces or {}
    counts: dict[str, int] = {}
    for k, v in ns_map.items():
        name = "" if k == "__default__" else k
        counts[name] = v.vector_count if hasattr(v, "vector_count") else int(str(v).split("vector_count: ")[-1].split()[0])
    return counts


def verify_namespace_state(
    index,
    expected_default: int,
    expected_target: int,
    label: str = "",
) -> None:
    """
    Assert default namespace count == expected_default and
    sudska_praksa count == expected_target.
    Raises AssertionError on mismatch — triggers HARD STOP.
    """
    counts = get_namespace_counts(index)
    default_count = counts.get("", 0)
    target_count = counts.get(TARGET_NAMESPACE, 0)

    log.info(
        "[verify%s] default=%d (expected %d), %s=%d (expected %d)",
        f" {label}" if label else "",
        default_count, expected_default,
        TARGET_NAMESPACE, target_count, expected_target,
    )
    assert default_count == expected_default, (
        f"HARD STOP: default namespace has {default_count} vectors, expected {expected_default}. "
        "Production may be corrupted!"
    )
    assert target_count == expected_target, (
        f"HARD STOP: {TARGET_NAMESPACE} has {target_count} vectors, expected {expected_target}."
    )


# ---------------------------------------------------------------------------
# Sanity queries
# ---------------------------------------------------------------------------

def run_sanity_queries(
    index, queries: list[dict], client, label: str = "", strict_matter: bool = False
) -> int:
    """
    Embed each query, search sudska_praksa namespace, log top result.
    Returns number of queries that PASS.

    strict_matter=False (Stage 1 seed): PASS if results non-empty AND metadata intact.
    strict_matter=True  (Stage 2 final): also check matter matches expected.
    With only 50 seed chunks, matter-matching is statistically unreliable; the full
    1479-chunk corpus is required for reliable matter discrimination.
    """
    passed = 0
    for i, q in enumerate(queries, 1):
        emb = embed_batch([q["text"]], client)[0]
        result = index.query(
            vector=emb,
            top_k=5,
            namespace=TARGET_NAMESPACE,
            include_metadata=True,
        )
        matches = result.matches if hasattr(result, "matches") else result.get("matches", [])
        if not matches:
            log.warning("[sanity%s Q%d] FAIL — no results for: %s", label, i, q["text"])
            continue

        top = matches[0]
        top_meta = top.metadata if hasattr(top, "metadata") else top.get("metadata", {})
        top_score = top.score if hasattr(top, "score") else top.get("score", 0)
        top_dn = top_meta.get("decision_number", top_meta.get("decision_id_fallback", "?"))
        top_section = top_meta.get("section", "?")
        top_matter = top_meta.get("matter", "?")

        expected = q.get("expected_matter")
        metadata_ok = all(
            top_meta.get(f) for f in ("section", "court", "decision_date", "text")
        )

        if strict_matter and expected is not None and top_matter != expected:
            status = "WARN(matter mismatch)"
            log.info(
                "[sanity%s Q%d] %s | %s | %s | %s | score=%.3f",
                label, i, status, q["text"][:40], top_dn, top_section, top_score,
            )
            log.warning("[sanity%s Q%d] Expected matter=%s, got=%s", label, i, expected, top_matter)
        elif not metadata_ok:
            log.warning("[sanity%s Q%d] FAIL — metadata incomplete for: %s", label, i, q["text"])
        else:
            status = "PASS"
            log.info(
                "[sanity%s Q%d] %s | %s | %s | %s | score=%.3f",
                label, i, status, q["text"][:40], top_dn, top_section, top_score,
            )
            passed += 1

    return passed


# ---------------------------------------------------------------------------
# Progress state
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"seed_chunk_ids": [], "stage2_completed_ids": [], "last_batch": 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Stage 1 — seed upsert
# ---------------------------------------------------------------------------

def stage_seed(index, client) -> set[str]:
    """
    Embed + upsert 50 stratified chunks.
    Verify namespace counts, run sanity queries.
    Returns set of chunk_ids upserted in Stage 1.
    """
    log.info("=== STAGE 1: SEED UPSERT (50 chunks) ===")

    # Verify baseline before doing anything
    verify_namespace_state(index, DEFAULT_NS_EXPECTED, 0, label="pre-seed")

    all_chunks = load_chunks()
    seed = select_seed_chunks(all_chunks)
    assert len(seed) == 50, f"Expected 50 seed chunks, got {len(seed)}"

    log.info("Seed selection: %s",
             {slug: sum(1 for c in seed if c["matter_slug"] == slug) for slug in SEED_PER_MATTER})

    # Embed all 50 at once
    t0 = time.monotonic()
    texts = [c["text"] for c in seed]
    embeddings = embed_batch(texts, client)
    embed_time = time.monotonic() - t0
    assert len(embeddings) == 50 and len(embeddings[0]) == 3072, (
        f"Embedding shape wrong: {len(embeddings)} × {len(embeddings[0]) if embeddings else 0}"
    )
    log.info("Embedded 50 chunks in %.1fs", embed_time)

    # Build and upsert
    vectors = [
        {"id": _ascii_vector_id(c["chunk_id"]), "values": emb, "metadata": c["metadata"]}
        for c, emb in zip(seed, embeddings)
    ]
    _safe_upsert(index, vectors, TARGET_NAMESPACE)
    log.info("Upserted 50 seed vectors to namespace=%s", TARGET_NAMESPACE)

    # Wait for Pinecone to index
    log.info("Waiting 5s for Pinecone propagation...")
    time.sleep(5)

    # Verify state
    verify_namespace_state(index, DEFAULT_NS_EXPECTED, 50, label="post-seed")

    # Sanity queries — non-strict (50 chunks too few for reliable matter discrimination)
    passed = run_sanity_queries(index, SANITY_QUERIES_STAGE1, client, label=" stage1", strict_matter=False)
    if passed < len(SANITY_QUERIES_STAGE1):
        log.error(
            "HARD STOP: only %d/%d sanity queries passed after Stage 1. Rolling back.",
            passed, len(SANITY_QUERIES_STAGE1),
        )
        index.delete(delete_all=True, namespace=TARGET_NAMESPACE)
        time.sleep(3)
        verify_namespace_state(index, DEFAULT_NS_EXPECTED, 0, label="post-rollback")
        log.info("Rollback complete. Default namespace intact at %d.", DEFAULT_NS_EXPECTED)
        sys.exit(1)

    seed_ids = {c["chunk_id"] for c in seed}
    state = load_state()
    state["seed_chunk_ids"] = list(seed_ids)
    save_state(state)

    log.info("=== STAGE 1 COMPLETE ===")
    log.info("sudska_praksa: 50 vectors")
    log.info("default: %d vectors (unchanged)", DEFAULT_NS_EXPECTED)
    log.info("Sanity queries: %d/%d PASS", passed, len(SANITY_QUERIES_STAGE1))
    log.info("Proceeding to Stage 2 (1,429 remaining)")

    return seed_ids


# ---------------------------------------------------------------------------
# Stage 2 — full upsert of remaining 1,429
# ---------------------------------------------------------------------------

def stage_full(index, client, seed_ids: set[str]) -> None:
    """
    Embed + upsert the 1,429 non-seed chunks in batches of 100.
    Checks default namespace count every 200 chunks.
    """
    log.info("=== STAGE 2: FULL UPSERT (1,429 remaining chunks) ===")

    all_chunks = load_chunks()
    remaining = [c for c in all_chunks if c["chunk_id"] not in seed_ids]
    log.info("Remaining after seed exclusion: %d chunks", len(remaining))
    assert len(remaining) == len(all_chunks) - len(seed_ids), "Chunk count mismatch"

    state = load_state()
    completed_ids: set[str] = set(state.get("stage2_completed_ids", []))
    if completed_ids:
        log.info("Resuming — %d chunks already completed", len(completed_ids))
        remaining = [c for c in remaining if c["chunk_id"] not in completed_ids]
        log.info("After resume skip: %d chunks to go", len(remaining))

    total_upserted = len(seed_ids) + len(completed_ids)
    batch_num = 0
    t_start = time.monotonic()

    for batch_start in range(0, len(remaining), UPSERT_BATCH_SIZE):
        batch = remaining[batch_start: batch_start + UPSERT_BATCH_SIZE]
        batch_num += 1
        texts = [c["text"] for c in batch]

        # Embed
        try:
            embeddings = embed_batch(texts, client)
        except Exception as e:
            log.error("Embedding batch %d failed: %s — retrying in 10s", batch_num, e)
            time.sleep(10)
            try:
                embeddings = embed_batch(texts, client)
            except Exception as e2:
                log.error("HARD STOP: embedding batch %d failed on retry: %s", batch_num, e2)
                sys.exit(1)

        # Build payloads
        vectors = [
            {"id": _ascii_vector_id(c["chunk_id"]), "values": emb, "metadata": c["metadata"]}
            for c, emb in zip(batch, embeddings)
        ]

        # Upsert
        try:
            _safe_upsert(index, vectors, TARGET_NAMESPACE)
        except AssertionError:
            raise  # namespace safety violation — always re-raise
        except Exception as e:
            log.error("Upsert batch %d failed: %s — retrying in 5s", batch_num, e)
            time.sleep(5)
            try:
                _safe_upsert(index, vectors, TARGET_NAMESPACE)
            except Exception as e2:
                log.error("HARD STOP: upsert batch %d failed on retry: %s", batch_num, e2)
                sys.exit(1)

        total_upserted += len(batch)
        batch_ids = [c["chunk_id"] for c in batch]
        state["stage2_completed_ids"].extend(batch_ids)
        state["last_batch"] = batch_num
        save_state(state)

        log.info(
            "Batch %d | +%d vectors | sudska_praksa total so far: ~%d | elapsed: %.0fs",
            batch_num, len(batch), total_upserted, time.monotonic() - t_start,
        )

        # Every 2 batches (200 chunks): verify default namespace unchanged
        if batch_num % 2 == 0:
            time.sleep(2)
            counts = get_namespace_counts(index)
            default_count = counts.get("", 0)
            target_count = counts.get(TARGET_NAMESPACE, 0)
            log.info(
                "[checkpoint] default=%d, %s=%d",
                default_count, TARGET_NAMESPACE, target_count,
            )
            if default_count != DEFAULT_NS_EXPECTED:
                log.error(
                    "HARD STOP: default namespace changed from %d to %d!",
                    DEFAULT_NS_EXPECTED, default_count,
                )
                sys.exit(1)
        else:
            time.sleep(2)

    elapsed = time.monotonic() - t_start
    log.info("=== STAGE 2 COMPLETE === Total: ~%d vectors | Wall time: %.1fs", total_upserted, elapsed)


# ---------------------------------------------------------------------------
# Final verification + sanity queries
# ---------------------------------------------------------------------------

def final_verify(index, client) -> None:
    """Full post-ingest verification: namespace counts + 5 sanity queries."""
    log.info("=== FINAL VERIFICATION ===")

    # Give Pinecone a few seconds to settle
    time.sleep(5)
    verify_namespace_state(index, DEFAULT_NS_EXPECTED, 1479, label="final")

    passed = run_sanity_queries(index, SANITY_QUERIES_FINAL, client, label=" final", strict_matter=True)
    if passed < 4:
        log.error(
            "HARD STOP: only %d/5 final sanity queries passed. Investigate before Phase 1.3.",
            passed,
        )
        sys.exit(1)

    log.info("Final sanity queries: %d/5 PASS", passed)


# ---------------------------------------------------------------------------
# Production regression check
# ---------------------------------------------------------------------------

def production_regression(client) -> bool:
    """POST to /api/pitanje (Q01 = theft question) and verify KZ citation + disclaimer."""
    import httpx
    import os

    prod_url = os.getenv("RENDER_EXTERNAL_URL", "https://vindex-ai.onrender.com")
    api_key = os.getenv("BOT_API_KEY", "")

    question = "Koja je kazna za osnovnu krađu?"
    log.info("Production regression: Q01 → %s/api/pitanje", prod_url)

    try:
        resp = httpx.post(
            f"{prod_url}/api/bot/ask",
            json={"pitanje": question},
            headers={"X-Api-Key": api_key},
            timeout=60,
        )
        log.info("Production response HTTP %d (%.0fms)", resp.status_code, resp.elapsed.total_seconds() * 1000)
        if resp.status_code != 200:
            log.error("Production regression FAIL: HTTP %d", resp.status_code)
            return False

        body = resp.text
        has_kz_citation = "203" in body or "KZ" in body or "krivičn" in body.lower() or "krađ" in body.lower()
        has_disclaimer = "pravna napomena" in body.lower() or "pravni savet" in body.lower() or "savet" in body.lower()
        has_statusna = "STATUSNA" in body or "POTVRDA" in body

        log.info("KZ citation present: %s", has_kz_citation)
        log.info("Disclaimer present: %s", has_disclaimer)
        log.info("STATUSNA template: %s", has_statusna)

        if not has_kz_citation:
            log.error("Production regression FAIL: Q01 response doesn't mention KZ/203/krađa")
            return False

        log.info("Production regression: PASS")
        return True
    except Exception as e:
        log.error("Production regression FAIL: %s", e)
        return False


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def rollback(index) -> None:
    """Delete ALL sudska_praksa vectors. Default namespace NOT touched."""
    log.warning("ROLLBACK: deleting all vectors in namespace=%s", TARGET_NAMESPACE)
    index.delete(delete_all=True, namespace=TARGET_NAMESPACE)
    time.sleep(5)
    counts = get_namespace_counts(index)
    default_count = counts.get("", 0)
    target_count = counts.get(TARGET_NAMESPACE, 0)
    log.info("Post-rollback: default=%d, %s=%d", default_count, TARGET_NAMESPACE, target_count)
    assert default_count == DEFAULT_NS_EXPECTED, (
        f"Default namespace changed after rollback! Expected {DEFAULT_NS_EXPECTED}, got {default_count}"
    )
    log.info("Rollback complete — default namespace intact at %d", DEFAULT_NS_EXPECTED)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def stage_reingest(index, client) -> None:
    """
    Re-upsert all on-disk chunks with updated metadata (including parent_text).

    Does NOT delete existing vectors — Pinecone upsert is idempotent by vector ID.
    Vectors whose IDs exist in Pinecone get their metadata updated; new IDs are inserted.
    Vectors in Pinecone that have no corresponding JSON on disk are left untouched.

    Use when metadata schema changes (e.g. adding parent_text) without changing embeddings.
    """
    log.info("=== REINGEST MODE: updating metadata for all on-disk chunks ===")
    log.info("NOTE: embeddings are recomputed; vectors are upserted (update or insert).")

    all_chunks = load_chunks()
    total = len(all_chunks)
    log.info("Loaded %d chunks from disk", total)

    t_start = time.monotonic()
    total_upserted = 0

    for batch_start in range(0, total, UPSERT_BATCH_SIZE):
        batch = all_chunks[batch_start: batch_start + UPSERT_BATCH_SIZE]
        texts = [c["text"] for c in batch]

        embeddings = embed_batch(texts, client)
        vectors = [
            {"id": _ascii_vector_id(c["chunk_id"]), "values": emb, "metadata": c["metadata"]}
            for c, emb in zip(batch, embeddings)
        ]
        _safe_upsert(index, vectors, TARGET_NAMESPACE)
        total_upserted += len(batch)
        batch_num = batch_start // UPSERT_BATCH_SIZE + 1
        elapsed = time.monotonic() - t_start
        log.info(
            "Batch %d | +%d | total %d/%d | %.0fs elapsed",
            batch_num, len(batch), total_upserted, total, elapsed,
        )
        time.sleep(1)  # light throttle — avoid Pinecone rate limit

    elapsed = time.monotonic() - t_start
    log.info("=== REINGEST COMPLETE === %d vectors upserted in %.1fs", total_upserted, elapsed)


def main():
    parser = argparse.ArgumentParser(description="Phase 1.2: ingest case law into Pinecone")
    parser.add_argument(
        "--stage",
        choices=["seed", "full", "all"],
        required=False,
        default="all",
        help="seed = Stage 1 only; full = Stage 2 only; all = both (default)",
    )
    parser.add_argument("--rollback", action="store_true", help="Delete all sudska_praksa vectors")
    parser.add_argument(
        "--reingest", action="store_true",
        help="Re-upsert all on-disk chunks with updated metadata (e.g. parent_text). "
             "Does NOT delete existing vectors. Bypasses count checks.",
    )
    args = parser.parse_args()

    # Env checks
    api_key = os.getenv("PINECONE_API_KEY")
    host = os.getenv("PINECONE_HOST", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not host or not openai_key:
        log.error("HARD STOP: missing PINECONE_API_KEY, PINECONE_HOST, or OPENAI_API_KEY")
        sys.exit(1)

    from pinecone import Pinecone
    from openai import OpenAI

    pc = Pinecone(api_key=api_key)
    index = pc.Index(host=host)
    client = OpenAI(api_key=openai_key)

    if args.rollback:
        rollback(index)
        return

    if args.reingest:
        stage_reingest(index, client)
        return

    if args.stage in ("seed", "all"):
        seed_ids = stage_seed(index, client)
    else:
        # Stage full without running seed — load seed_ids from state
        state = load_state()
        seed_ids = set(state.get("seed_chunk_ids", []))
        if not seed_ids:
            log.error("HARD STOP: --stage full requires prior seed run. No seed_chunk_ids found in state.")
            sys.exit(1)
        log.info("Loaded %d seed_ids from state file", len(seed_ids))

    if args.stage in ("full", "all"):
        stage_full(index, client, seed_ids)

    if args.stage == "all":
        final_verify(index, client)
        ok = production_regression(client)
        if not ok:
            log.error("HARD STOP: production regression failed. Investigate before Phase 1.3.")
            sys.exit(1)

    log.info("Phase 1.2 ingest complete.")


if __name__ == "__main__":
    main()
