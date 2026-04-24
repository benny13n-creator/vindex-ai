# -*- coding: utf-8 -*-
"""
Briše stare Pinecone vektore (law="krivicni zakonik" / "zakon o porezu na dohodak gradjana")
i re-indeksira iste fajlove sa kratkim kodovima law="KZ" / law="ZPDG".

Pokretanje:
    python reindex_shortcodes.py
    python reindex_shortcodes.py --test    # + test queriji na kraju
"""

import os
import sys
import time
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("reindex_sc")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
INDEX_NAME       = "vindex-ai"

# Mapa stari naziv → novi kratki kod
RENAME_MAP = {
    "krivicni zakonik":                "KZ",
    "zakon o porezu na dohodak gradjana": "ZPDG",
}

TEST_QUERIJI = [
    ("neovlašćen pristup računaru",           "KZ"),
    ("kapitalni dobitak porez kriptovaluta",  "ZPDG"),
]


def obrisi_po_filteru(index, stari_naziv: str) -> None:
    log.info("Brišem vektore: law='%s' ...", stari_naziv)
    try:
        index.delete(filter={"law": {"$eq": stari_naziv}})
        log.info("  ✓ Brisanje pokrenuto (Pinecone async — čekam 5s za propagaciju)")
        time.sleep(5)
    except Exception as e:
        log.error("  [GREŠKA] Brisanje '%s': %s", stari_naziv, e)


def main():
    pokreni_test = "--test" in sys.argv

    if not PINECONE_API_KEY:
        log.error("PINECONE_API_KEY nije postavljen u .env")
        sys.exit(1)
    if not OPENAI_API_KEY:
        log.error("OPENAI_API_KEY nije postavljen u .env")
        sys.exit(1)

    from pinecone import Pinecone
    from openai import OpenAI
    from ingest_kz_zpdg import indeksiraj, ZAKONI

    pc     = Pinecone(api_key=PINECONE_API_KEY)
    index  = pc.Index(INDEX_NAME)
    client = OpenAI(api_key=OPENAI_API_KEY)

    stats = index.describe_index_stats()
    log.info("Pinecone stats PRE: %d vektora ukupno", stats.total_vector_count)

    # ── Korak 1: briši stare vektore ─────────────────────────────────────────
    log.info("\n=== BRISANJE STARIH VEKTORA ===")
    for stari in RENAME_MAP:
        obrisi_po_filteru(index, stari)

    stats = index.describe_index_stats()
    log.info("Pinecone stats POSLE BRISANJA: %d vektora ukupno", stats.total_vector_count)

    # ── Korak 2: re-indeksiraj sa kratkim kodovima ────────────────────────────
    log.info("\n=== RE-INDEKSIRANJE SA KRATKIM KODOVIMA ===")

    # ZAKONI iz ingest_kz_zpdg.py već imaju naziv="KZ" i naziv="ZPDG"
    for zakon_cfg in ZAKONI:
        fajl = Path(__file__).parent / "data" / "laws" / "pdfs" / zakon_cfg["fajl"]
        if not fajl.exists():
            log.error("  [SKIP] Fajl ne postoji: %s — pokreni ingest_kz_zpdg.py --only-scrape", fajl)
            continue
        log.info("Indeksiram: %s → law='%s'", zakon_cfg["fajl"], zakon_cfg["naziv"])
        try:
            n = indeksiraj(zakon_cfg, index, client)
            log.info("  ✓ %s: %d vektora upisano", zakon_cfg["naziv"], n)
        except Exception as e:
            log.error("  [GREŠKA] %s: %s", zakon_cfg["naziv"], e)

    time.sleep(5)
    stats = index.describe_index_stats()
    log.info("\nPinecone stats POSLE RE-INDEKSIRANJA: %d vektora ukupno", stats.total_vector_count)

    # ── Korak 3: test queriji ─────────────────────────────────────────────────
    if pokreni_test:
        log.info("\n=== TEST QUERIJI ===")
        from openai import OpenAI as _OAI
        _c = _OAI(api_key=OPENAI_API_KEY)
        EMBEDDING_MODEL = "text-embedding-3-large"

        for query, ocekivani_zakon in TEST_QUERIJI:
            log.info("\nQuery: '%s'  (očekivano: %s)", query, ocekivani_zakon)
            try:
                emb = _c.embeddings.create(model=EMBEDDING_MODEL, input=[query])
                vektor = emb.data[0].embedding
                res = index.query(vector=vektor, top_k=5, include_metadata=True)
                if not res.matches:
                    log.warning("  → NEMA REZULTATA")
                    continue
                pronadjen = False
                for r in res.matches[:3]:
                    meta  = r.metadata or {}
                    zakon = meta.get("law", "?")
                    clan  = meta.get("article", "?")
                    tekst = (meta.get("text", "") or "")[:100].replace("\n", " ")
                    hit   = "✓" if zakon == ocekivani_zakon else " "
                    log.info("  [%.3f] %s %s / %s — %s...", r.score, hit, zakon, clan, tekst)
                    if zakon == ocekivani_zakon:
                        pronadjen = True
                if not pronadjen:
                    log.warning("  [!] ZAKON '%s' NIJE U TOP-3 REZULTATIMA", ocekivani_zakon)
                else:
                    log.info("  ✓ OK — '%s' pronađen u rezultatima", ocekivani_zakon)
            except Exception as e:
                log.error("  [GREŠKA] %s", e)

        log.info("\n=== TEST ZAVRŠEN ===")


if __name__ == "__main__":
    main()
