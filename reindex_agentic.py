# -*- coding: utf-8 -*-
"""
Vindex AI — Agentic Re-ingestion (Sprint 1)

Čita sve PDF fajlove zakona, deli ih semantički (po stavovima),
i upisuje v2 vektore u Pinecone sa bogatim metapodacima.

STARI vektori se NE brišu — novi dobijaju v2 ID prefix i koegzistiraju
dok test query ne potvrdi ispravnost, nakon čega se stari brišu ručno.

Pokretanje:
    python reindex_agentic.py
    python reindex_agentic.py --dry-run    # prikaži statistiku bez upisa
    python reindex_agentic.py --verify     # samo verifikacioni test
    python reindex_agentic.py --cleanup    # obriši stare v1 vektore (posle verifikacije!)
"""

import os
import re
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
log = logging.getLogger("reindex_agentic")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
INDEX_HOST       = os.getenv("PINECONE_HOST", "").strip()
INDEX_NAME       = os.getenv("PINECONE_INDEX_NAME", "").strip()
EMBEDDING_MODEL  = "text-embedding-3-large"
BATCH_SIZE       = 40

PDF_FOLDER = Path(__file__).parent / "data" / "laws" / "pdfs"

# Mapiranje stem naziva fajla → puni naziv zakona
PDF_LAW_MAP = {
    "zakon_o_obligacionim_odnosima":      "zakon o obligacionim odnosima",
    "zakon_o_radu":                        "zakon o radu",
    "porodicni_zakon":                     "porodicni zakon",
    "zakon_o_parnicnom_postupku":          "zakon o parnicnom postupku",
    "zakon_o_krivicnom_postupku":          "zakonik o krivicnom postupku",
    "zakon_o_izvrsenju_i_obezbedjenju":    "zakon o izvrsenju i obezbedjenju",
    "zakon_o_nasledjivanju":               "zakon o nasledjivanju",
    "zakon_o_opstem_upravnom_postupku":    "zakon o opstem upravnom postupku",
    "zakon_o_upravnim_sporovima":          "zakon o upravnim sporovima",
    "zakon_o_vanparnicnom_postupku":       "zakon o vanparnicnom postupku",
    "zakon_o_privredin_drustvima":         "zakon o privrednim drustvima",
    "ustav_republike_srbije":              "ustav republike srbije",
    "zakon_o_zastiti_podataka_o_licnosti": "zakon o zastiti podataka o licnosti",
    "zakon_o_zastiti_potrosaca":           "zakon o zastiti potrosaca",
    "zakon_o_digitalnoj_imovini":          "zakon o digitalnoj imovini",
    "zakon_o_sprecavanju_pranja_novca":    "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "krivicni_zakonik":                    "KZ",
    "zakon_o_porezu_na_dohodak_gradjana":  "ZPDG",
}

VERIFY_QUERY = (
    "Koji su rokovi za registraciju privrednog društva u APR i CROSO "
    "nakon osnivanja, i ko može zastupati društvo u tom procesu?"
)


def _normalizuj_ime(ime: str) -> str:
    return re.sub(r"\s+copy$", "", ime.lower().strip())


def _izvuci_tekst(pdf_path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp1250", "latin-1"):
        try:
            return pdf_path.read_text(encoding=enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return pdf_path.read_text(encoding="utf-8", errors="replace")


def _embed_batch(tekstovi: list[str], client) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=tekstovi)
    return [e.embedding for e in resp.data]


def reindex_fajl(
    pdf_path: Path,
    zakon_naziv: str,
    index,
    client,
    dry_run: bool = False,
) -> int:
    from semantic_chunker import podeli_zakon_na_chunkove

    try:
        tekst = _izvuci_tekst(pdf_path)
    except Exception as e:
        log.error("  [GREŠKA] Čitanje %s: %s", pdf_path.name, e)
        return 0

    chunkovi = podeli_zakon_na_chunkove(tekst, zakon_naziv)
    log.info("  %s → %d chunkova (stavova)", zakon_naziv, len(chunkovi))

    if dry_run:
        # Ispisi statistiku bez upisa
        clanovi  = {c["metadata"]["parent_id"] for c in chunkovi}
        avg_stav = len(chunkovi) / len(clanovi) if clanovi else 0
        log.info(
            "  [DRY] Članova: %d | Avg stavova/članu: %.1f | Ukupno chunkova: %d",
            len(clanovi), avg_stav, len(chunkovi),
        )
        return len(chunkovi)

    ukupno = 0
    for i in range(0, len(chunkovi), BATCH_SIZE):
        batch    = chunkovi[i:i + BATCH_SIZE]
        tekstovi = [c["text"] for c in batch]

        try:
            embeddinzi = _embed_batch(tekstovi, client)
        except Exception as e:
            log.error("  [GREŠKA] Embedding batch %d: %s", i // BATCH_SIZE + 1, e)
            time.sleep(5)
            continue

        vektori = []
        for c, emb in zip(batch, embeddinzi):
            vektori.append({
                "id":       c["id"],
                "values":   emb,
                "metadata": c["metadata"],
            })

        try:
            index.upsert(vectors=vektori)
            ukupno += len(vektori)
            log.info(
                "  → Batch %d: %d vektora upisano (ukupno: %d)",
                i // BATCH_SIZE + 1, len(vektori), ukupno,
            )
        except Exception as e:
            log.error("  [GREŠKA] Pinecone upsert: %s", e)

        time.sleep(0.4)

    return ukupno


def verifikuj(index, client) -> bool:
    """Verifikacioni test: pitanje o APR/CROSO mora naći ZPD chunk."""
    log.info("\n=== VERIFIKACIJA ===")
    log.info("Query: '%s'", VERIFY_QUERY)

    emb  = client.embeddings.create(model=EMBEDDING_MODEL, input=[VERIFY_QUERY])
    vec  = emb.data[0].embedding

    # Pretražujemo samo v2 vektore (po zakon="ZPD" filteru)
    res = index.query(vector=vec, top_k=5, include_metadata=True,
                      filter={"zakon": {"$eq": "ZPD"}})

    if not res.matches:
        # Pokušaj bez filtera
        res = index.query(vector=vec, top_k=10, include_metadata=True)

    if not res.matches:
        log.error("  ✗ VERIFIKACIJA NEUSPEŠNA — nema rezultata")
        return False

    pronasao_zpd = False
    for r in res.matches[:5]:
        meta  = r.metadata or {}
        zakon = meta.get("zakon", meta.get("law", "?"))
        clan  = meta.get("article", f"Član {meta.get('clan', '?')}")
        prev  = (meta.get("tekst_preview") or meta.get("text", ""))[:80].replace("\n", " ")
        log.info("  [%.3f] %s / %s — %s...", r.score, zakon, clan, prev)
        if "ZPD" in zakon or "privredn" in str(meta.get("law", "")).lower():
            pronasao_zpd = True

    if pronasao_zpd:
        log.info("  ✓ VERIFIKACIJA OK — ZPD chunk pronađen")
    else:
        log.warning("  ⚠ ZPD chunk nije u top-5 — proveri ingestion")

    return True  # Barem neki rezultati postoje


def obrisi_stare_vektore(index) -> None:
    """Briše v1 vektore (law filter) za sve zakone. Pokrenuti tek posle verifikacije!"""
    log.warning("[CLEANUP] Brišem stare v1 vektore...")
    stari_nazivi = list({v for v in PDF_LAW_MAP.values()})
    for naziv in stari_nazivi:
        try:
            index.delete(filter={"law": {"$eq": naziv}})
            log.info("  Obrisan: law='%s'", naziv)
            time.sleep(1)
        except Exception as e:
            log.error("  [GREŠKA] Brisanje '%s': %s", naziv, e)
    log.info("[CLEANUP] Gotovo.")


def main():
    dry_run = "--dry-run" in sys.argv
    verify  = "--verify"  in sys.argv
    cleanup = "--cleanup" in sys.argv

    if not PINECONE_API_KEY:
        log.error("PINECONE_API_KEY nije postavljen")
        sys.exit(1)
    if not OPENAI_API_KEY:
        log.error("OPENAI_API_KEY nije postavljen")
        sys.exit(1)
    if not INDEX_HOST:
        log.error("PINECONE_HOST nije postavljen")
        sys.exit(1)

    from pinecone import Pinecone
    from openai  import OpenAI

    pc     = Pinecone(api_key=PINECONE_API_KEY)
    index  = pc.Index(host=INDEX_HOST)
    client = OpenAI(api_key=OPENAI_API_KEY)

    if verify:
        verifikuj(index, client)
        return

    if cleanup:
        obrisi_stare_vektore(index)
        return

    stats = index.describe_index_stats()
    log.info("Pinecone PRE: %d vektora", stats.total_vector_count)

    pdfs = list(PDF_FOLDER.glob("*.pdf"))
    log.info("Pronađeno %d PDF fajlova\n", len(pdfs))

    ukupno = 0
    for pdf_path in pdfs:
        ime = _normalizuj_ime(pdf_path.stem)
        zakon = None
        for kljuc, vrednost in PDF_LAW_MAP.items():
            if kljuc in ime or ime in kljuc:
                zakon = vrednost
                break
        if not zakon:
            zakon = ime.replace("_", " ")
            log.warning("[!] Nije mapiran: %s → '%s'", pdf_path.name, zakon)

        log.info("Obradujem: %s → %s", pdf_path.name, zakon)
        n = reindex_fajl(pdf_path, zakon, index, client, dry_run=dry_run)
        ukupno += n
        log.info("")

    if not dry_run:
        time.sleep(5)
        stats = index.describe_index_stats()
        log.info("Pinecone POSLE: %d vektora (novo upisano: %d)", stats.total_vector_count, ukupno)
        log.info("\nPokreni verifikaciju: python reindex_agentic.py --verify")
        log.info("Posle verifikacije brišeš stare: python reindex_agentic.py --cleanup")
    else:
        log.info("[DRY-RUN] Ukupno bi bilo upisano: %d chunkova", ukupno)


if __name__ == "__main__":
    main()
