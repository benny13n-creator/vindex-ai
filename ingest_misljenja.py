# -*- coding: utf-8 -*-
"""
Phase 2.4 — Ingest mišljenja ministarstava u Pinecone namespace 'misljenja'

Čita JSON fajlove iz data/misljenja/raw/,
chunka (mišljenja su kratki dokumenti — 1 chunk po dokumentu ili 2 ako je dugačak),
ugradjuje OpenAI text-embedding-3-large,
i upisuje u Pinecone namespace 'misljenja'.

Metadata po vektoru:
  tip         = "misljenje"
  ministarstvo
  datum
  broj
  oblast
  naziv
  text        = puni tekst chunka
  source      = izvor (minrzs.gov.rs / seed)

Pokretanje:
  python ingest_misljenja.py [--dry-run] [--force]
  --dry-run : prikazuje šta bi se indeksovalo bez upisa u Pinecone
  --force   : briše stare vektore pre upisa (namespace delete + re-ingest)
"""

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
)
log = logging.getLogger("ingest_misljenja")

RAW_DIR = Path(__file__).parent / "data" / "misljenja" / "raw"
NAMESPACE = "misljenja"
BATCH_SIZE = 50
MAX_TOKENS_PER_CHUNK = 600
EMBEDDING_MODEL = "text-embedding-3-large"

# ─── Lazy klijenti ────────────────────────────────────────────────────────────

_pc_index = None
_embeddings = None


def _get_index():
    global _pc_index
    if _pc_index is None:
        from pinecone import Pinecone
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY", "").strip())
        host = os.getenv("PINECONE_HOST", "").strip()
        name = os.getenv("PINECONE_INDEX_NAME", "vindex-ai").strip()
        if host:
            _pc_index = pc.Index(host=host)
        else:
            _pc_index = pc.Index(name)
        stats = _pc_index.describe_index_stats()
        log.info("[PINECONE] Konekcija OK — ukupno vektora: %d", stats.total_vector_count)
    return _pc_index


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        from langchain_openai import OpenAIEmbeddings
        _embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return _embeddings


# ─── Chunking ─────────────────────────────────────────────────────────────────

def _chunk_misljenje(doc: dict) -> list[dict]:
    """
    Mišljenja su kratki dokumenti (~500-1500 token).
    Strategija: 1 chunk ako tekst kratak, 2 chunka (overlap 100 tok) ako duži.
    Vraća listu chunk dict-ova sa metapodacima.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
    except ImportError:
        log.warning("tiktoken nije instaliran — koristim char-based split")
        enc = None

    tekst = (doc.get("tekst") or doc.get("text") or "").strip()
    naziv = (doc.get("naziv") or "").strip()
    # Kombinuj naziv + tekst za richer embedding
    full_text = f"{naziv}\n\n{tekst}" if naziv else tekst

    if not full_text:
        log.warning("Prazan tekst za %s — preskačem", doc.get("broj", "?"))
        return []

    # Tokenize
    if enc:
        tokens = enc.encode(full_text)
        n_tokens = len(tokens)
    else:
        n_tokens = len(full_text) // 4  # rough approximation

    chunks = []
    base_meta = {
        "tip":          "misljenje",
        "ministarstvo": doc.get("ministarstvo", ""),
        "datum":        doc.get("datum", ""),
        "broj":         doc.get("broj", ""),
        "oblast":       doc.get("oblast", ""),
        "naziv":        naziv,
        "source":       doc.get("source", "seed"),
        "url":          doc.get("url", ""),
    }

    if n_tokens <= MAX_TOKENS_PER_CHUNK:
        chunks.append({**base_meta, "text": full_text, "chunk_index": 0})
    else:
        # Podeli na 2 dela sa 50-token overlapom
        if enc:
            mid = n_tokens // 2
            overlap = 50
            chunk1_tokens = tokens[:mid + overlap]
            chunk2_tokens = tokens[max(0, mid - overlap):]
            chunk1_text = enc.decode(chunk1_tokens)
            chunk2_text = enc.decode(chunk2_tokens)
        else:
            mid = len(full_text) // 2
            chunk1_text = full_text[:mid + 200]
            chunk2_text = full_text[max(0, mid - 200):]

        chunks.append({**base_meta, "text": chunk1_text, "chunk_index": 0})
        chunks.append({**base_meta, "text": chunk2_text, "chunk_index": 1})

    log.debug("[CHUNK] %s → %d chunk(s)", doc.get("broj", "?"), len(chunks))
    return chunks


# ─── Embedding batch ──────────────────────────────────────────────────────────

def _embed_batch(texts: list[str]) -> list[list[float]]:
    emb = _get_embeddings()
    return emb.embed_documents(texts)


# ─── Pinecone upsert ──────────────────────────────────────────────────────────

def _upsert_batch(vectors: list[tuple], dry_run: bool = False):
    if dry_run:
        log.info("[DRY-RUN] Bi se upsertovalo %d vektora", len(vectors))
        return
    index = _get_index()
    index.upsert(vectors=vectors, namespace=NAMESPACE)
    log.info("[UPSERT] Upisano %d vektora u namespace='%s'", len(vectors), NAMESPACE)


# ─── Glavni tok ───────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    force   = "--force"   in sys.argv

    log.info("=== Phase 2.4 — Ingest mišljenja → Pinecone namespace '%s' ===", NAMESPACE)
    log.info("dry_run=%s force=%s", dry_run, force)

    # 1. Provjeri da postoji raw direktorijum
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.json")):
        log.info("[SCRAPER] Raw JSON nije pronađen — pokrećem scraper...")
        import scrape_misljenja
        scrape_misljenja.main()

    raw_files = sorted(RAW_DIR.glob("*.json"))
    log.info("[RAW] Pronađeno %d JSON fajlova u %s", len(raw_files), RAW_DIR)

    if not raw_files:
        log.error("Nema JSON fajlova za ingest!")
        sys.exit(1)

    # 2. Učitaj sve dokumente
    docs = []
    for fp in raw_files:
        try:
            with open(fp, encoding="utf-8") as f:
                doc = json.load(f)
            docs.append(doc)
        except Exception as e:
            log.warning("[LOAD] Greška pri čitanju %s: %s", fp.name, e)

    log.info("[LOAD] Učitano %d dokumenata", len(docs))

    # 3. Chunking
    all_chunks = []
    for doc in docs:
        chunks = _chunk_misljenje(doc)
        all_chunks.extend(chunks)

    log.info("[CHUNK] Ukupno %d chunkova", len(all_chunks))

    if dry_run:
        log.info("[DRY-RUN] Primer chunk #0:")
        if all_chunks:
            c = all_chunks[0]
            log.info("  tekst: %s...", c["text"][:100])
            log.info("  meta: ministarstvo=%s oblast=%s", c["ministarstvo"], c["oblast"])
        log.info("[DRY-RUN] Gotovo — nema upisa u Pinecone")
        print(f"\n[DRY-RUN] {len(all_chunks)} chunkova bi se indeksovalo u namespace '{NAMESPACE}'")
        return

    # 4. Force: briši namespace pre upisa
    if force:
        log.warning("[FORCE] Brišem namespace '%s'...", NAMESPACE)
        try:
            idx = _get_index()
            idx.delete(delete_all=True, namespace=NAMESPACE)
            time.sleep(2)
            log.info("[FORCE] Namespace obrisan")
        except Exception as e:
            log.warning("[FORCE] Brisanje namespace nije uspelo: %s — nastavlja se", e)

    # 5. Embed + upsert u batchevima
    total_upserted = 0
    batch_chunks = []
    batch_vectors = []

    for i, chunk in enumerate(all_chunks):
        batch_chunks.append(chunk)

        if len(batch_chunks) >= BATCH_SIZE or i == len(all_chunks) - 1:
            texts = [c["text"] for c in batch_chunks]
            log.info("[EMBED] Batch %d/%d — embedujem %d tekstova...",
                     total_upserted // BATCH_SIZE + 1,
                     (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE,
                     len(texts))
            try:
                embeddings = _embed_batch(texts)
            except Exception as e:
                log.error("[EMBED] Greška: %s — preskačem batch", e)
                batch_chunks = []
                continue

            vectors = []
            for chunk, emb in zip(batch_chunks, embeddings):
                vec_id = str(uuid.uuid4())
                # Pinecone metadata — sve string/int/float vrednosti
                meta = {k: str(v) if v is not None else "" for k, v in chunk.items() if k != "text"}
                meta["text"] = chunk["text"][:2000]  # Pinecone metadata limit
                vectors.append((vec_id, emb, meta))

            _upsert_batch(vectors, dry_run=False)
            total_upserted += len(vectors)
            batch_chunks = []
            time.sleep(0.3)  # rate limiting

    log.info("[DONE] Ingest završen — upisano %d vektora u namespace '%s'", total_upserted, NAMESPACE)

    # 6. Verifikacija
    try:
        idx = _get_index()
        stats = idx.describe_index_stats()
        ns_stats = stats.namespaces.get(NAMESPACE, {})
        ns_count = getattr(ns_stats, "vector_count", 0) or ns_stats.get("vector_count", 0) if hasattr(ns_stats, "get") else getattr(ns_stats, "vector_count", 0)
        log.info("[VERIFY] Namespace '%s': %d vektora", NAMESPACE, ns_count)
        print(f"\n✓ Ingest završen: {total_upserted} vektora u namespace '{NAMESPACE}'")
        print(f"✓ Pinecone verifikacija: {ns_count} vektora u '{NAMESPACE}'")
        if ns_count >= 50:
            print(f"✓ Minimum 50 mišljenja ispunjen ({ns_count} >= 50)")
        else:
            print(f"⚠ Manje od 50 vektora ({ns_count}) — dodaj više seed mišljenja")
    except Exception as e:
        log.warning("[VERIFY] Ne mogu proveriti statistiku: %s", e)
        print(f"\n✓ Ingest završen: {total_upserted} vektora upisano")


if __name__ == "__main__":
    main()
