# -*- coding: utf-8 -*-
"""
Vindex AI — Targeted KZ Re-ingest

Deletes all existing KZ vectors from Pinecone, then re-embeds and uploads
the complete Krivični zakonik with parent_text metadata (1500+ chunks).

Run:
    python ingest_kz.py
    python ingest_kz.py --dry-run   # stats only, no write
    python ingest_kz.py --verify    # post-upload verification only
"""

import os
import sys
import time
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_kz")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
INDEX_HOST       = "vindex-ai-t8z679r.svc.aped-4627-b74a.pinecone.io"
EMBEDDING_MODEL  = "text-embedding-3-large"
BATCH_SIZE       = 40
KZ_FILE          = Path(__file__).parent / "data" / "laws" / "pdfs" / "krivicni_zakonik.pdf"
KZ_LAW_NAME      = "KZ"

VERIFY_QUERIES = [
    ("kazna za kradju",          "KZ", "Član 203"),
    ("kazna za tesku kradju",    "KZ", "Član 204"),
    ("kazna za razbojnistvo",    "KZ", "Član 206"),
    ("kazna za prevaru",         "KZ", "Član 208"),
    ("ubistvo kazna",            "KZ", "Član 113"),
]


def _embed_batch(texts: list[str], client) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [e.embedding for e in resp.data]


def delete_kz_vectors(index) -> int:
    """Delete all vectors with law='KZ' using filter."""
    log.info("Deleting existing KZ vectors (filter: law=$eq:KZ)...")
    try:
        index.delete(filter={"law": {"$eq": KZ_LAW_NAME}})
        log.info("Delete request sent. Waiting 5s for propagation...")
        time.sleep(5)

        # Confirm deletion
        from langchain_openai import OpenAIEmbeddings
        emb = OpenAIEmbeddings(model=EMBEDDING_MODEL)
        vec = emb.embed_query("krivicno delo kazna")
        res = index.query(vector=vec, top_k=5, include_metadata=True,
                          filter={"law": {"$eq": KZ_LAW_NAME}})
        remaining = len(res.matches)
        log.info("After delete: %d KZ vectors still indexed (should be 0)", remaining)
        return remaining
    except Exception as e:
        log.error("Delete failed: %s", e)
        return -1


def ingest_kz(index, client, dry_run: bool = False) -> int:
    from semantic_chunker import podeli_zakon_na_chunkove

    if not KZ_FILE.exists():
        log.error("KZ file not found: %s", KZ_FILE)
        return 0

    log.info("Reading KZ file: %s (%d bytes)", KZ_FILE.name, KZ_FILE.stat().st_size)
    text = KZ_FILE.read_text(encoding="utf-8", errors="replace")
    log.info("KZ text: %d chars", len(text))

    chunks = podeli_zakon_na_chunkove(text, KZ_LAW_NAME)
    log.info("Chunker produced: %d chunks", len(chunks))

    # Stats
    has_parent = sum(1 for c in chunks if c["metadata"].get("parent_text"))
    articles = {c["metadata"]["article"] for c in chunks}
    log.info("Chunks with parent_text: %d/%d", has_parent, len(chunks))
    log.info("Unique articles: %d", len(articles))

    # Verify key articles
    for art in ["Član 203", "Član 204", "Član 206", "Član 208", "Član 113"]:
        found = [c for c in chunks if c["metadata"]["article"] == art]
        log.info("  %s: %d chunks %s", art, len(found),
                 "✓" if found else "✗ MISSING")

    if dry_run:
        log.info("[DRY RUN] No upload. Exiting.")
        return len(chunks)

    # Upload in batches
    uploaded = 0
    errors = 0
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [c["text"] for c in batch]

        try:
            embeddings = _embed_batch(texts, client)
        except Exception as e:
            log.error("Embedding batch %d failed: %s", i // BATCH_SIZE + 1, e)
            errors += 1
            time.sleep(5)
            continue

        vectors = []
        for chunk, emb in zip(batch, embeddings):
            vectors.append({
                "id":       chunk["id"],
                "values":   emb,
                "metadata": chunk["metadata"],
            })

        try:
            index.upsert(vectors=vectors)
            uploaded += len(vectors)
            log.info("Batch %d/%d: %d uploaded (total: %d)",
                     i // BATCH_SIZE + 1,
                     (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE,
                     len(vectors), uploaded)
        except Exception as e:
            log.error("Pinecone upsert batch %d failed: %s", i // BATCH_SIZE + 1, e)
            errors += 1

        time.sleep(0.5)

    log.info("Upload complete: %d vectors, %d errors", uploaded, errors)
    return uploaded


def verify(index) -> bool:
    from langchain_openai import OpenAIEmbeddings
    emb = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    log.info("\n=== VERIFICATION ===")
    all_ok = True

    # Give Pinecone a moment to index
    time.sleep(3)

    stats = index.describe_index_stats()
    log.info("Total index vectors after upload: %d", stats.total_vector_count)

    for query, expected_law, expected_article in VERIFY_QUERIES:
        vec = emb.embed_query(query)
        res = index.query(vector=vec, top_k=5, include_metadata=True,
                          filter={"law": {"$eq": expected_law}})
        articles = [m.metadata.get("article", "?") for m in res.matches]
        found = expected_article in articles
        status = "✓" if found else "✗"
        log.info("  %s Query: '%s' → top articles: %s", status, query, articles[:3])
        if not found:
            all_ok = False

    if all_ok:
        log.info("VERIFICATION PASSED ✓")
    else:
        log.warning("VERIFICATION FAILED — some expected articles not in top-5")
    return all_ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify",  action="store_true")
    args = parser.parse_args()

    if not PINECONE_API_KEY:
        log.error("PINECONE_API_KEY not set")
        sys.exit(1)
    if not OPENAI_API_KEY:
        log.error("OPENAI_API_KEY not set")
        sys.exit(1)

    from pinecone import Pinecone
    from openai import OpenAI

    pc    = Pinecone(api_key=PINECONE_API_KEY)
    idx   = pc.Index(host=INDEX_HOST)
    oai   = OpenAI(api_key=OPENAI_API_KEY)

    if args.verify:
        verify(idx)
        return

    if not args.dry_run:
        log.info("=== STEP 1: Delete existing KZ vectors ===")
        delete_kz_vectors(idx)

    log.info("=== STEP 2: Ingest KZ (dry_run=%s) ===", args.dry_run)
    n = ingest_kz(idx, oai, dry_run=args.dry_run)

    if not args.dry_run:
        log.info("=== STEP 3: Verify ===")
        verify(idx)

    log.info("Done. Uploaded %d vectors.", n)


if __name__ == "__main__":
    main()
