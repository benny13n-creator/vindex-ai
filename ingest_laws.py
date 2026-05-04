# -*- coding: utf-8 -*-
"""
Vindex AI — Bulk Law Ingest (14 laws)

For each law: deletes old vectors, re-chunks with parent_text, embeds, uploads.
Appends one status line to /docs/INDEX_EXPANSION_LOG.md after each law.

Run:
    python ingest_laws.py
    python ingest_laws.py --dry-run        # stats only, no Pinecone writes
    python ingest_laws.py --law ZKP        # single law by shortcode
    python ingest_laws.py --skip-delete    # upload without deleting old vectors
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_laws")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
INDEX_HOST       = os.getenv("PINECONE_HOST", "").strip()
EMBEDDING_MODEL  = "text-embedding-3-large"
BATCH_SIZE       = 40
DATA_DIR         = Path(__file__).parent / "data" / "laws" / "pdfs"
LOG_FILE         = Path(__file__).parent / "docs" / "INDEX_EXPANSION_LOG.md"

# Each entry: file, exact law name (used in metadata), shortcode, alt delete names
LAWS = [
    {
        "file":     "zakon_o_krivicnom_postupku.pdf",
        "name":     "zakonik o krivicnom postupku",
        "sc":       "ZKP",
        "del_alts": ["ZKP", "zakonik o krivičnom postupku"],
    },
    {
        "file":     "zakon_o_obligacionim_odnosima.pdf",
        "name":     "zakon o obligacionim odnosima",
        "sc":       "ZOO",
        "del_alts": ["ZOO", "zakon o obligacionim odnosima"],
    },
    {
        "file":     "zakon_o_parnicnom_postupku.pdf",
        "name":     "zakon o parnicnom postupku",
        "sc":       "ZPP",
        "del_alts": ["ZPP", "zakon o parničnom postupku"],
    },
    {
        "file":     "zakon_o_radu.pdf",
        "name":     "zakon o radu",
        "sc":       "ZR",
        "del_alts": ["ZR"],
    },
    {
        "file":     "porodicni_zakon.pdf",
        "name":     "porodicni zakon",
        "sc":       "PZ",
        "del_alts": ["PZ", "porodični zakon"],
    },
    {
        "file":     "zakon_o_nasledjivanju.pdf",
        "name":     "zakon o nasledjivanju",
        "sc":       "ZN",
        "del_alts": ["ZN", "zakon o nasleđivanju"],
    },
    {
        "file":     "zakon_o_privredin_drustvima.pdf",
        "name":     "zakon o privrednim drustvima",
        "sc":       "ZPD",
        "del_alts": ["ZPD", "zakon o privrednim društvima"],
    },
    {
        "file":     "zakon_o_opstem_upravnom_postupku.pdf",
        "name":     "zakon o opstem upravnom postupku",
        "sc":       "ZOUP",
        "del_alts": ["ZOUP", "zakon o opštem upravnom postupku"],
    },
    {
        "file":     "zakon_o_izvrsenju_i_obezbedjenju.pdf",
        "name":     "zakon o izvrsenju i obezbedjenju",
        "sc":       "ZIO",
        "del_alts": ["ZIO", "zakon o izvršenju i obezbeđenju"],
    },
    {
        "file":     "zakon_o_digitalnoj_imovini.pdf",
        "name":     "zakon o digitalnoj imovini",
        "sc":       "ZDI",
        "del_alts": ["ZDI"],
    },
    {
        "file":     "zakon_o_sprecavanju_pranja_novca.pdf",
        "name":     "zakon o sprecavanju pranja novca i finansiranja terorizma",
        "sc":       "ZSPNFT",
        "del_alts": ["ZSPNFT", "zakon o sprečavanju pranja novca i finansiranja terorizma",
                     "zakon o sprecavanju pranja novca"],
    },
    {
        "file":     "zakon_o_porezu_na_dohodak_gradjana.pdf",
        "name":     "zakon o porezu na dohodak gradjana",
        "sc":       "ZPDG",
        "del_alts": ["ZPDG", "zakon o porezu na dohodak građana"],
    },
    {
        "file":     "ustav_republike_srbije.pdf",
        "name":     "ustav republike srbije",
        "sc":       "USTAV",
        "del_alts": ["USTAV", "ustav republike srbije"],
    },
]


def _embed_batch(texts: list[str], client) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [e.embedding for e in resp.data]


def _delete_by_filter(index, law_name: str) -> None:
    try:
        index.delete(filter={"law": {"$eq": law_name}})
        log.info("  Delete sent for law=%r", law_name)
    except Exception as e:
        log.warning("  Delete failed for law=%r: %s", law_name, e)


def delete_law_vectors(index, law: dict) -> None:
    """Delete all old vectors for this law (primary name + alt names)."""
    names_to_delete = {law["name"]} | set(law.get("del_alts", []))
    log.info("[%s] Deleting old vectors (%d name variants)...", law["sc"], len(names_to_delete))
    for name in names_to_delete:
        _delete_by_filter(index, name)
    log.info("[%s] Waiting 5s for Pinecone propagation...", law["sc"])
    time.sleep(5)


def ingest_law(index, client, law: dict, dry_run: bool = False) -> dict:
    """Chunk, embed, and upload one law. Returns stats dict."""
    from semantic_chunker import podeli_zakon_na_chunkove

    law_file = DATA_DIR / law["file"]
    if not law_file.exists():
        log.error("[%s] File not found: %s", law["sc"], law_file)
        return {"chunks": 0, "articles": 0, "uploaded": 0, "errors": 0, "status": "FILE_MISSING"}

    log.info("[%s] Reading %s (%d bytes)", law["sc"], law["file"], law_file.stat().st_size)
    text = law_file.read_text(encoding="utf-8", errors="replace")
    log.info("[%s] Text length: %d chars", law["sc"], len(text))

    chunks = podeli_zakon_na_chunkove(text, law["name"])
    articles = {c["metadata"]["article"] for c in chunks}
    has_parent = sum(1 for c in chunks if c["metadata"].get("parent_text"))

    log.info("[%s] Chunks: %d | Articles: %d | With parent_text: %d/%d",
             law["sc"], len(chunks), len(articles), has_parent, len(chunks))

    if dry_run:
        log.info("[%s] DRY RUN — no upload.", law["sc"])
        return {"chunks": len(chunks), "articles": len(articles),
                "uploaded": 0, "errors": 0, "status": "DRY_RUN"}

    uploaded = 0
    errors   = 0
    total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        batch_num = i // BATCH_SIZE + 1

        try:
            embeddings = _embed_batch(texts, client)
        except Exception as e:
            log.error("[%s] Embedding batch %d/%d failed: %s", law["sc"], batch_num, total_batches, e)
            errors += 1
            time.sleep(5)
            continue

        vectors = [
            {"id": c["id"], "values": emb, "metadata": c["metadata"]}
            for c, emb in zip(batch, embeddings)
        ]

        try:
            index.upsert(vectors=vectors)
            uploaded += len(vectors)
            log.info("[%s] Batch %d/%d: +%d vectors (total: %d)",
                     law["sc"], batch_num, total_batches, len(vectors), uploaded)
        except Exception as e:
            log.error("[%s] Upsert batch %d/%d failed: %s", law["sc"], batch_num, total_batches, e)
            errors += 1

        time.sleep(0.3)

    status = "OK" if errors == 0 else f"PARTIAL ({errors} batch errors)"
    log.info("[%s] Done: %d uploaded, %d errors", law["sc"], uploaded, errors)
    return {"chunks": len(chunks), "articles": len(articles),
            "uploaded": uploaded, "errors": errors, "status": status}


def append_log(law: dict, stats: dict) -> None:
    """Append one line to INDEX_EXPANSION_LOG.md."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = (f"| {ts} | {law['sc']} | {law['name']} "
            f"| {stats['articles']} articles "
            f"| {stats['uploaded']} vectors "
            f"| {stats['status']} |\n")

    if not LOG_FILE.exists():
        LOG_FILE.write_text(
            "# INDEX_EXPANSION_LOG\n\n"
            "| Timestamp | SC | Law | Articles | Vectors | Status |\n"
            "|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line)
    log.info("[%s] Log appended: %s", law["sc"], line.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",      action="store_true", help="Stats only, no writes")
    parser.add_argument("--skip-delete",  action="store_true", help="Skip deletion step")
    parser.add_argument("--law",          type=str, default=None,
                        help="Process only this shortcode (e.g. ZKP)")
    args = parser.parse_args()

    if not PINECONE_API_KEY:
        log.error("PINECONE_API_KEY not set")
        sys.exit(1)
    if not OPENAI_API_KEY:
        log.error("OPENAI_API_KEY not set")
        sys.exit(1)
    if not INDEX_HOST:
        log.error("PINECONE_HOST not set")
        sys.exit(1)

    from pinecone import Pinecone
    from openai import OpenAI

    pc  = Pinecone(api_key=PINECONE_API_KEY)
    idx = pc.Index(host=INDEX_HOST)
    oai = OpenAI(api_key=OPENAI_API_KEY)

    laws_to_process = LAWS
    if args.law:
        laws_to_process = [l for l in LAWS if l["sc"].upper() == args.law.upper()]
        if not laws_to_process:
            log.error("Unknown shortcode: %s. Valid: %s",
                      args.law, ", ".join(l["sc"] for l in LAWS))
            sys.exit(1)

    log.info("=== INDEX EXPANSION: %d laws to process ===", len(laws_to_process))
    if args.dry_run:
        log.info("DRY RUN mode — no Pinecone writes")

    total_uploaded = 0
    results = []

    for i, law in enumerate(laws_to_process, start=1):
        log.info("\n--- [%d/%d] %s: %s ---", i, len(laws_to_process), law["sc"], law["name"])

        if not args.dry_run and not args.skip_delete:
            delete_law_vectors(idx, law)

        stats = ingest_law(idx, oai, law, dry_run=args.dry_run)
        total_uploaded += stats["uploaded"]
        results.append((law, stats))
        append_log(law, stats)

        # Small pause between laws to respect rate limits
        if i < len(laws_to_process):
            time.sleep(1)

    # Final summary
    log.info("\n=== SUMMARY ===")
    log.info("%-8s %-45s %7s %7s  %s", "SC", "Law", "Chunks", "Upload", "Status")
    log.info("-" * 85)
    for law, stats in results:
        log.info("%-8s %-45s %7d %7d  %s",
                 law["sc"], law["name"][:45],
                 stats["chunks"], stats["uploaded"], stats["status"])
    log.info("-" * 85)
    log.info("TOTAL vectors uploaded this run: %d", total_uploaded)

    if not args.dry_run:
        time.sleep(3)
        stats_pc = idx.describe_index_stats()
        log.info("Pinecone total vectors after run: %d", stats_pc.total_vector_count)


if __name__ == "__main__":
    main()
