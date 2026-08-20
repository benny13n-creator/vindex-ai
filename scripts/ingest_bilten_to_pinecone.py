# -*- coding: utf-8 -*-
"""
VINDEX Faza 2A — Bilten Pinecone ingest script

Reads parsed bilten decision JSONs from a flat directory, chunks them using
the existing chunker_case_law.chunk_decision(), then upserts to the
``sudska_praksa`` Pinecone namespace.  Does NOT touch the default namespace.

Usage:
    python scripts/ingest_bilten_to_pinecone.py \
        --decisions data/sudska_praksa/raw_bilteni/as_nis/decisions/ \
        --dry-run          # embed + count only, do NOT upsert

    python scripts/ingest_bilten_to_pinecone.py \
        --decisions data/sudska_praksa/raw_bilteni/as_nis/decisions/
        # real upsert

Safety:
    - Asserts default namespace stays at DEFAULT_NS_EXPECTED before and after.
    - Aborts if default namespace count changes.
    - Aborts if sudska_praksa count increases by more than 3× expected.
"""

import argparse, json, logging, os, sys, time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is on sys.path so chunker_case_law can be imported
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_bilten_to_pinecone")

# ── Constants ────────────────────────────────────────────────────────────────

TARGET_NAMESPACE = "sudska_praksa"
EMBED_MODEL = "text-embedding-3-large"
EMBED_BATCH = 100
UPSERT_BATCH = 100
DEFAULT_NS_EXPECTED = 17707   # NEVER TOUCH THIS NAMESPACE
EMBED_DIM_EXPECTED = 3072

_SRLATMAP = str.maketrans("žšćčđŽŠĆČĐ", "zsccdZSCCD")

# Extra chars that are invalid in Pinecone vector IDs (spaces, Cyrillic, etc.)
# We transliterate Cyrillic to ASCII via our own map
_CYRILLIC_TRANSLIT = {
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ж': 'Zh',
    'З': 'Z', 'И': 'I', 'Й': 'J', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
    'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F',
    'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch', 'Ъ': '',
    'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'j', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f',
    'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '',
    'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    # Serbian-specific
    'Ђ': 'Dj', 'Љ': 'Lj', 'Њ': 'Nj', 'Ћ': 'C', 'Џ': 'Dz',
    'ђ': 'dj', 'љ': 'lj', 'њ': 'nj', 'ћ': 'c', 'џ': 'dz',
}

def _ascii_vector_id(chunk_id: str) -> str:
    """Transliterate Cyrillic and strip non-ASCII for Pinecone vector ID."""
    # Apply latin diacritics map first
    s = chunk_id.translate(_SRLATMAP)
    # Apply Cyrillic transliteration
    out = []
    for ch in s:
        if ch in _CYRILLIC_TRANSLIT:
            out.append(_CYRILLIC_TRANSLIT[ch])
        elif ord(ch) < 128 or ch in '-_':
            out.append(ch)
        else:
            out.append('_')
    result = ''.join(out)
    # Replace spaces with underscores
    result = result.replace(' ', '_').replace('/', '_')
    return result


def _clean_metadata(meta: dict) -> dict:
    """Enforce Pinecone metadata types: strings/numbers/bools/lists only."""
    clean = {}
    for k, v in meta.items():
        if v is None:
            clean[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            clean[k] = v
        elif isinstance(v, list):
            clean[k] = [str(x) for x in v]
        else:
            clean[k] = str(v)
    return clean


def get_namespace_counts(index) -> dict[str, int]:
    stats = index.describe_index_stats()
    ns_map = stats.namespaces or {}
    counts: dict[str, int] = {}
    for k, v in ns_map.items():
        name = "" if k == "__default__" else k
        counts[name] = v.vector_count if hasattr(v, "vector_count") else int(str(v).split("vector_count: ")[-1].split()[0])
    return counts


def verify_default_namespace(index, label: str = "") -> None:
    """Abort if default namespace has changed from expected."""
    counts = get_namespace_counts(index)
    default_count = counts.get("", 0)
    target_count = counts.get(TARGET_NAMESPACE, 0)
    log.info("[verify%s] default=%d (expected %d), %s=%d",
             f" {label}" if label else "",
             default_count, DEFAULT_NS_EXPECTED,
             TARGET_NAMESPACE, target_count)
    assert default_count == DEFAULT_NS_EXPECTED, (
        f"HARD STOP: default namespace has {default_count} vectors, "
        f"expected {DEFAULT_NS_EXPECTED}. Production may be corrupted!"
    )


# ── Chunk + prepare ──────────────────────────────────────────────────────────

def load_and_chunk(decisions_dir: Path) -> list[dict]:
    """
    Load all decision JSONs from a flat directory, chunk each, return flat chunk list.
    Each chunk dict: {chunk_id, text, metadata}
    """
    from chunker_case_law import chunk_decision

    json_files = sorted(decisions_dir.glob("*.json"))
    if not json_files:
        log.error("No JSON files found in %s", decisions_dir)
        sys.exit(1)

    log.info("Loading %d decision JSONs from %s", len(json_files), decisions_dir)
    all_chunks: list[dict] = []
    skipped = 0

    for fp in json_files:
        try:
            decision_json = json.loads(fp.read_text(encoding="utf-8"))
            # Ensure registrant field exists (bilten schema omits it)
            decision_json.setdefault("registrant", "")
            result = chunk_decision(decision_json)
            for chunk in result["chunks"]:
                raw_meta = {**chunk["metadata"], "text": chunk["text"]}
                all_chunks.append({
                    "chunk_id": chunk["chunk_id"],
                    "text": chunk["text"],
                    "metadata": _clean_metadata(raw_meta),
                })
        except Exception as exc:
            log.warning("Skipping %s: %s", fp.name, exc)
            skipped += 1

    log.info("Chunked: %d chunks from %d decisions (%d skipped)",
             len(all_chunks), len(json_files) - skipped, skipped)
    return all_chunks


# ── Embed ─────────────────────────────────────────────────────────────────────

def embed_chunks(chunks: list[dict], client) -> list[list[float]]:
    """Embed all chunks in batches. Returns list of embedding vectors."""
    texts = [c["text"] for c in chunks]
    embeddings: list[list[float]] = []
    total = len(texts)

    for i in range(0, total, EMBED_BATCH):
        batch_texts = texts[i:i + EMBED_BATCH]
        t0 = time.monotonic()
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch_texts)
        elapsed = time.monotonic() - t0
        batch_embs = [e.embedding for e in resp.data]
        assert len(batch_embs[0]) == EMBED_DIM_EXPECTED, \
            f"Unexpected embedding dim: {len(batch_embs[0])}"
        embeddings.extend(batch_embs)
        log.info("Embedded batch %d-%d / %d in %.1fs",
                 i + 1, min(i + EMBED_BATCH, total), total, elapsed)

    return embeddings


# ── Upsert ────────────────────────────────────────────────────────────────────

def upsert_chunks(chunks: list[dict], embeddings: list[list[float]], index) -> None:
    """Upsert vectors to sudska_praksa namespace in batches."""
    total = len(chunks)
    for i in range(0, total, UPSERT_BATCH):
        batch_c = chunks[i:i + UPSERT_BATCH]
        batch_e = embeddings[i:i + UPSERT_BATCH]
        vectors = [
            {
                "id": _ascii_vector_id(c["chunk_id"]),
                "values": emb,
                "metadata": c["metadata"],
            }
            for c, emb in zip(batch_c, batch_e)
        ]
        index.upsert(vectors=vectors, namespace=TARGET_NAMESPACE)
        log.info("Upserted batch %d-%d / %d → namespace=%s",
                 i + 1, min(i + UPSERT_BATCH, total), total, TARGET_NAMESPACE)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest bilten decision JSONs into Pinecone sudska_praksa namespace"
    )
    parser.add_argument(
        "--decisions", required=True,
        help="Directory containing flat decision JSONs (output of ingest_bilten.py)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Chunk + embed but do NOT upsert to Pinecone"
    )
    args = parser.parse_args()

    decisions_dir = Path(args.decisions)
    if not decisions_dir.exists():
        log.error("Decisions dir not found: %s", decisions_dir)
        sys.exit(1)

    # ── Step 1: chunk ────────────────────────────────────────────────────────
    all_chunks = load_and_chunk(decisions_dir)
    if not all_chunks:
        log.error("No chunks produced"); sys.exit(1)

    log.info("Total chunks to ingest: %d", len(all_chunks))
    for c in all_chunks[:3]:
        log.info("  Sample chunk: %s | %d chars | matter=%s",
                 c["chunk_id"][:50], len(c["text"]),
                 c["metadata"].get("matter", "?"))

    if args.dry_run:
        log.info("[DRY RUN] Skipping embed + upsert. Chunk count: %d", len(all_chunks))
        print(f"\nDRY RUN SUMMARY")
        print(f"  Chunks to upsert : {len(all_chunks)}")
        print(f"  Namespace target : {TARGET_NAMESPACE}")
        print(f"  Default ns guard : {DEFAULT_NS_EXPECTED} (never touched)")
        return

    # ── Step 2: connect ──────────────────────────────────────────────────────
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    pinecone_index_name = os.environ.get("PINECONE_INDEX", "vindex-ai")

    if not pinecone_api_key:
        log.error("PINECONE_API_KEY not set"); sys.exit(1)
    if not openai_api_key:
        log.error("OPENAI_API_KEY not set"); sys.exit(1)

    from pinecone import Pinecone
    from openai import OpenAI

    pc = Pinecone(api_key=pinecone_api_key)
    index = pc.Index(pinecone_index_name)
    oai = OpenAI(api_key=openai_api_key)

    # ── Step 3: pre-check ────────────────────────────────────────────────────
    verify_default_namespace(index, label="pre-ingest")
    counts_pre = get_namespace_counts(index)
    praksa_pre = counts_pre.get(TARGET_NAMESPACE, 0)
    log.info("Pre-ingest sudska_praksa count: %d", praksa_pre)

    # ── Step 4: embed ────────────────────────────────────────────────────────
    log.info("Embedding %d chunks...", len(all_chunks))
    embeddings = embed_chunks(all_chunks, oai)
    log.info("Embedding complete: %d vectors (dim=%d)", len(embeddings), len(embeddings[0]) if embeddings else 0)

    # ── Step 5: upsert ──────────────────────────────────────────────────────
    log.info("Upserting to %s...", TARGET_NAMESPACE)
    upsert_chunks(all_chunks, embeddings, index)

    # Wait for Pinecone propagation
    log.info("Waiting 8s for Pinecone propagation...")
    time.sleep(8)

    # ── Step 6: post-check ──────────────────────────────────────────────────
    verify_default_namespace(index, label="post-ingest")
    counts_post = get_namespace_counts(index)
    praksa_post = counts_post.get(TARGET_NAMESPACE, 0)
    added = praksa_post - praksa_pre

    log.info("Post-ingest sudska_praksa count: %d (+%d new)", praksa_post, added)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"BILTEN INGEST SUMMARY")
    print(f"{'='*55}")
    print(f"  Chunks upserted    : {len(all_chunks)}")
    print(f"  Vectors added      : +{added}")
    print(f"  sudska_praksa pre  : {praksa_pre}")
    print(f"  sudska_praksa post : {praksa_post}")
    print(f"  Default ns         : {counts_post.get('', 0)} (must = {DEFAULT_NS_EXPECTED})")
    print(f"  Namespace          : {TARGET_NAMESPACE}")


if __name__ == "__main__":
    main()
