# -*- coding: utf-8 -*-
"""
Vindex AI — Pinecone ingestion za sudskapraksa.sud.rs odluke

Čita JSON fajlove iz vindex_scraper_output/odluke/, chunkuje ih pomoću
postojećeg chunker_case_law.chunk_decision(), embedduje i upsertuje u
Pinecone namespace 'sudska_praksa'.

Napomena: vektori iz biltena u istom namespaceu su nepovređeni jer
          sp_ prefiks garantuje odsustvo kolizije ID-eva.

Pokretanje:
    python scripts/ingest_sudskapraksa.py --dry-run
    python scripts/ingest_sudskapraksa.py
    python scripts/ingest_sudskapraksa.py --resume   # nastavlja od checkpointa

Opcije:
    --odluke-dir  putanja do direktorijuma sa JSON odlukama (default: auto-detect)
    --batch       broj chunk-ova po embedding pozivu (default: 100)
    --limit       maksimalan broj odluka (za testiranje)
    --dry-run     samo chunking i brojanje — bez upserta
    --resume      nastavi od sačuvanog checkpointa
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Windows UTF-8 fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Dodaj project root na sys.path
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_sp")

# ── Konstante ─────────────────────────────────────────────────────────────────
TARGET_NAMESPACE  = "sudska_praksa"
EMBED_MODEL       = "text-embedding-3-large"
EMBED_BATCH       = 100    # chunk-ova po embedding pozivu
UPSERT_BATCH      = 100    # vektora po upsert pozivu
MIN_TEKST_CHARS   = 80     # odluke sa manje teksta → metadata-only vektor
CKPT_EVERY        = 500    # odluka između checkpoint save-ova

# Auto-detect lokacija odluke direktorijuma
_DEFAULT_ODLUKE_DIR = _PROJECT_ROOT / "vindex_scraper_output" / "odluke"

# ── Cyrillic transliteracija za Pinecone ID-eve ───────────────────────────────
_SRLATMAP = str.maketrans("žšćčđŽŠĆČĐ", "zsccdZSCCD")
_CYR = {
    'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ж':'Zh','З':'Z','И':'I',
    'Й':'J','К':'K','Л':'L','М':'M','Н':'N','О':'O','П':'P','Р':'R','С':'S',
    'Т':'T','У':'U','Ф':'F','Х':'H','Ц':'Ts','Ч':'Ch','Ш':'Sh','Щ':'Shch',
    'Ъ':'','Ы':'Y','Ь':'','Э':'E','Ю':'Yu','Я':'Ya',
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ж':'zh','з':'z','и':'i',
    'й':'j','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s',
    'т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'shch',
    'ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
    'Ђ':'Dj','Љ':'Lj','Њ':'Nj','Ћ':'C','Џ':'Dz',
    'ђ':'dj','љ':'lj','њ':'nj','ћ':'c','џ':'dz',
}

def _safe_id(s: str) -> str:
    s = s.translate(_SRLATMAP)
    out = []
    for ch in s:
        if ch in _CYR:
            out.append(_CYR[ch])
        elif ord(ch) < 128:
            out.append(ch)
        else:
            out.append('_')
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', ''.join(out))


def _clean_meta(meta: dict) -> dict:
    """Pinecone dozvoljava samo str/int/float/bool/list metadata."""
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


# ── Mapiranje scraper schema → chunker schema ─────────────────────────────────
def _to_chunker_schema(rec: dict) -> dict:
    """
    Konvertuje scraper JSON (sudskapraksa format) u format koji očekuje
    chunker_case_law.chunk_decision().
    """
    tekst = (rec.get("tekst") or "").strip()

    # Za odluke bez punog teksta (npr. ECHR) koristimo kljucne_reci kao tekst
    if len(tekst) < MIN_TEKST_CHARS:
        kljucne = (rec.get("kljucne_reci") or "").strip()
        sud = (rec.get("sud") or "").strip()
        mat = (rec.get("materija") or "").strip()
        tekst = " | ".join(filter(None, [sud, mat, kljucne]))
        if not tekst:
            return None  # apsolutno nema sadržaja — preskoči

    return {
        "decision_id":     f"sp_{rec['id']}",
        "decision_number": rec.get("broj_predmeta") or "",
        "matter":          rec.get("materija") or "",
        "court":           rec.get("sud") or "",
        "decision_date":   rec.get("datum") or "",
        "registrant":      rec.get("upisnik") or "",
        "source_url":      rec.get("url") or f"https://sudskapraksa.sud.rs/sudska-praksa/{rec['id']}",
        "raw_text":        tekst,
        # Ekstra polja koja chunker čuva u metadata
        "_tip_odluke":     rec.get("tip_odluke") or "",
        "_kljucne_reci":   rec.get("kljucne_reci") or "",
        "_tip_suda":       rec.get("tip_suda") or "",
        "_has_pdf":        rec.get("has_pdf", False),
    }


# ── Checkpoint ─────────────────────────────────────────────────────────────────
def _ckpt_path(odluke_dir: Path) -> Path:
    return odluke_dir.parent / "ingest_checkpoint.json"


def load_checkpoint(odluke_dir: Path) -> dict:
    """Vraća {done_ids, failed_ids, seen_hashes} — tolerantno na stari format
    (samo done_ids) koji ne sadrži failed_ids/seen_hashes ključeve.

    done_ids   — odluke čiji su SVI chunk-ovi potvrđeno upsertovani u Pinecone
                 (ne samo ubačeni u buffer — vidi napomenu u main() petlji).
    failed_ids — odluke čiji je embed/upsert trajno neuspeo (posle retry-a) —
                 NE preskaču se na resume, pokušavaju se ponovo.
    seen_hashes — sha256 hash normalizovanog teksta svake ingestovane odluke,
                 za dedup PO SADRŽAJU (ne samo po fajl ID-u) preko izvora.
    """
    p = _ckpt_path(odluke_dir)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            done = set(data.get("done_ids", []))
            failed = set(data.get("failed_ids", []))
            hashes = set(data.get("seen_hashes", []))
            log.info(
                "Checkpoint učitan: %d odluka gotovo, %d ranije neuspešno (pokušaće se ponovo), %d hash-eva poznato",
                len(done), len(failed), len(hashes),
            )
            return {"done_ids": done, "failed_ids": failed, "seen_hashes": hashes}
        except Exception as e:
            log.warning("Checkpoint neispravan (%s) — počinjem iznova", e)
    return {"done_ids": set(), "failed_ids": set(), "seen_hashes": set()}


def save_checkpoint(odluke_dir: Path, done_ids: set[str], failed_ids: set[str], seen_hashes: set[str], stats: dict):
    p = _ckpt_path(odluke_dir)
    tmp = p.with_suffix(".tmp")
    data = {
        "done_ids": list(done_ids),
        "failed_ids": list(failed_ids),
        "seen_hashes": list(seen_hashes),
        "stats": stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


# ── Namespace stats ───────────────────────────────────────────────────────────
def ns_count(index, ns: str) -> int:
    stats = index.describe_index_stats()
    ns_map = stats.namespaces or {}
    for k, v in ns_map.items():
        if k == ns:
            return v.vector_count if hasattr(v, "vector_count") else 0
    return 0


# ── Embed batch ───────────────────────────────────────────────────────────────
def embed_batch(texts: list[str], oai_client, retry: int = 3) -> list[list[float]]:
    for attempt in range(retry):
        try:
            resp = oai_client.embeddings.create(model=EMBED_MODEL, input=texts)
            return [e.embedding for e in resp.data]
        except Exception as e:
            if attempt < retry - 1:
                wait = 2 ** attempt * 5
                log.warning("Embedding greška (%s) — retry za %ds", e, wait)
                time.sleep(wait)
            else:
                raise
    return []


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Ingestuje sudskapraksa.sud.rs odluke u Pinecone"
    )
    parser.add_argument("--odluke-dir", default=str(_DEFAULT_ODLUKE_DIR),
                        help="Direktorijum sa JSON odlukama")
    parser.add_argument("--batch", type=int, default=EMBED_BATCH,
                        help="Broj chunk-ova po embedding pozivu")
    parser.add_argument("--limit", type=int, default=0,
                        help="Maks. broj odluka (0 = sve)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Samo chunking/brojanje — bez upserta")
    parser.add_argument("--resume", action="store_true",
                        help="Nastavi od checkpointa (preskače već ingestovane)")
    args = parser.parse_args()

    odluke_dir = Path(args.odluke_dir)
    if not odluke_dir.exists():
        log.error("Direktorijum ne postoji: %s", odluke_dir)
        sys.exit(1)

    # ── Učitaj chunker ────────────────────────────────────────────────────────
    try:
        from chunker_case_law import chunk_decision
    except ImportError:
        log.error("chunker_case_law.py nije nađen u project root-u")
        sys.exit(1)

    # ── Učitaj JSON fajlove ───────────────────────────────────────────────────
    json_files = sorted(odluke_dir.glob("*.json"))
    if not json_files:
        log.error("Nema JSON fajlova u %s", odluke_dir)
        sys.exit(1)

    if args.limit:
        json_files = json_files[:args.limit]

    log.info("Pronađeno %d JSON fajlova u %s", len(json_files), odluke_dir)

    # ── Checkpoint ────────────────────────────────────────────────────────────
    done_ids: set[str] = set()
    failed_ids: set[str] = set()
    seen_hashes: set[str] = set()
    if args.resume:
        ckpt = load_checkpoint(odluke_dir)
        done_ids, failed_ids, seen_hashes = ckpt["done_ids"], ckpt["failed_ids"], ckpt["seen_hashes"]

    # ── Inicijalizuj API klijente ─────────────────────────────────────────────
    if not args.dry_run:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")

        pinecone_key = os.environ.get("PINECONE_API_KEY")
        openai_key   = os.environ.get("OPENAI_API_KEY")
        index_name   = os.environ.get("PINECONE_INDEX", "vindex-ai")

        if not pinecone_key: log.error("PINECONE_API_KEY nije postavljen"); sys.exit(1)
        if not openai_key:   log.error("OPENAI_API_KEY nije postavljen"); sys.exit(1)

        from pinecone import Pinecone
        from openai import OpenAI

        pc    = Pinecone(api_key=pinecone_key)
        index = pc.Index(index_name)
        oai   = OpenAI(api_key=openai_key)

        count_before = ns_count(index, TARGET_NAMESPACE)
        log.info("Pinecone namespace '%s': %d vektora pre ingesta", TARGET_NAMESPACE, count_before)
    else:
        index = oai = None
        count_before = 0

    # ── Statistike ────────────────────────────────────────────────────────────
    stats = {
        "odluke_procesirane": 0,
        "odluke_preskocene":  0,
        "odluke_greska":      0,
        "odluke_duplikat":    0,
        "chunk_ukupno":       0,
        "vektori_upsertovani": 0,
    }

    # Buffer za batch embedding + upsert. Svaki chunk nosi svoj odluka_id da
    # bismo posle flush-a znali TAČNO koje odluke da označimo done/failed —
    # KRITIČNO: odluka se markira "done" tek OVDE, posle potvrđenog upserta,
    # nikad ranije. Ranija verzija je markirala done_ids odmah po ulasku u
    # buffer — crash usred flush-a je značio da su odluke "gotove" u
    # checkpointu a NIKAD stvarno upsertovane u Pinecone (tih vektorâ prosto
    # nema, i --resume ih tiho preskače zauvek).
    chunk_buffer: list[dict] = []
    # Hash-eva čiji je sadržaj TRENUTNO u bufferu (nije još potvrđeno upsertovan).
    # Odvojeno od seen_hashes (potvrđeno persistovano) da duplikat druge odluke
    # ne bude tiho preskočen ako original na kraju NIKAD ne uspe da se upserta.
    pending_hashes: set[str] = set()

    def _flush_buffer(force: bool = False) -> bool:
        """Embed i upsert sve chunk-ove u bufferu. Vraća True ako je uspelo.
        Nikad ne baca — greška se hvata, pogođene odluke idu u failed_ids,
        run nastavlja sa sledećim fajlom umesto da se ceo posao sruši."""
        if not chunk_buffer:
            return True
        if not force and len(chunk_buffer) < args.batch:
            return True

        pending_ids = {c["odluka_id"] for c in chunk_buffer}
        pending_this_flush = {c["content_hash"] for c in chunk_buffer}

        try:
            texts = [c["text"] for c in chunk_buffer]
            embeddings = []
            for i in range(0, len(texts), args.batch):
                batch_texts = texts[i:i + args.batch]
                batch_embs  = embed_batch(batch_texts, oai)
                embeddings.extend(batch_embs)

            vectors = []
            for chunk, emb in zip(chunk_buffer, embeddings):
                vid = _safe_id(chunk["chunk_id"])
                vectors.append({
                    "id":       vid,
                    "values":   emb,
                    "metadata": chunk["metadata"],
                })

            for i in range(0, len(vectors), UPSERT_BATCH):
                index.upsert(vectors=vectors[i:i + UPSERT_BATCH],
                             namespace=TARGET_NAMESPACE)

        except Exception as exc:
            log.error(
                "Flush neuspeo za %d odluka (%s) — obeležene kao failed, run nastavlja: %s",
                len(pending_ids), ", ".join(list(pending_ids)[:5]), exc,
            )
            failed_ids.update(pending_ids)
            done_ids.difference_update(pending_ids)
            # NE dodajemo u seen_hashes — sadržaj nije potvrđeno persistovan,
            # pa eventualni duplikat mora imati priliku da i sam pokuša.
            pending_hashes.difference_update(pending_this_flush)
            chunk_buffer.clear()
            return False

        stats["vektori_upsertovani"] += len(vectors)
        stats["chunk_ukupno"]        += len(vectors)
        done_ids.update(pending_ids)
        failed_ids.difference_update(pending_ids)
        seen_hashes.update(pending_this_flush)
        pending_hashes.difference_update(pending_this_flush)
        chunk_buffer.clear()
        return True

    # ── Glavna petlja ─────────────────────────────────────────────────────────
    log.info("Počinjem ingestion (dry_run=%s, resume=%s) ...", args.dry_run, args.resume)

    for i, fp in enumerate(json_files, 1):
        odluka_id = fp.stem

        if odluka_id in done_ids:
            stats["odluke_preskocene"] += 1
            continue

        try:
            rec = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Ne mogu da čitam %s: %s", fp.name, e)
            stats["odluke_greska"] += 1
            continue

        chunker_in = _to_chunker_schema(rec)
        if chunker_in is None:
            stats["odluke_preskocene"] += 1
            done_ids.add(odluka_id)  # nema šta da se upserta — nema pending Pinecone posla
            continue

        # Dedup PO SADRŽAJU (ne samo po fajl ID-u) — ista odluka može stići pod
        # drugim ID-jem posle re-scrape-a. Hash se računa nad normalizovanim
        # tekstom PRE chunking-a da bude stabilan bez obzira na chunker verziju.
        norm_text = re.sub(r"\s+", " ", chunker_in["raw_text"]).strip().lower()
        content_hash = hashlib.sha256(norm_text.encode("utf-8")).hexdigest()
        if content_hash in seen_hashes:
            # Sadržaj POTVRĐENO već upsertovan (pod drugim ID-jem) — bezbedno preskoči.
            stats["odluke_duplikat"] += 1
            done_ids.add(odluka_id)
            continue
        if content_hash in pending_hashes:
            # Identičan sadržaj je TRENUTNO u bufferu, ishod još nepoznat — ne
            # markiramo ni done ni failed, samo preskačemo ovaj put. Ako original
            # na kraju ne uspe, ovaj fajl ostaje neobrađen i pokušaće se ponovo
            # na sledećem --resume (kao svaki običan fajl, nema rizika od gubitka).
            stats["odluke_duplikat"] += 1
            continue

        try:
            chunked = chunk_decision(chunker_in)
        except Exception as e:
            log.warning("Chunking greška za %s: %s", odluka_id, e)
            stats["odluke_greska"] += 1
            failed_ids.add(odluka_id)
            continue

        for chunk in chunked["chunks"]:
            meta = dict(chunk["metadata"])
            meta["text"] = chunk["text"]
            # Dodaj extra polja iz scraper-a
            meta["tip_odluke"]   = chunker_in.get("_tip_odluke", "")
            meta["kljucne_reci"] = chunker_in.get("_kljucne_reci", "")[:500]
            meta["tip_suda"]     = chunker_in.get("_tip_suda", "")
            meta["has_pdf"]      = chunker_in.get("_has_pdf", False)

            chunk_entry = {
                "odluka_id":    odluka_id,
                "content_hash": content_hash,
                "chunk_id":     f"sp_{odluka_id}__chunk_{chunk['chunk_index']}",
                "text":         chunk["text"],
                "metadata":     _clean_meta(meta),
            }

            if args.dry_run:
                stats["chunk_ukupno"] += 1
            else:
                chunk_buffer.append(chunk_entry)

        stats["odluke_procesirane"] += 1
        if args.dry_run:
            # Dry-run ne piše ništa u Pinecone — nema šta da se "potvrdi", pa
            # seen_hashes ažuriramo odmah (samo za procenu/preview svrhe).
            seen_hashes.add(content_hash)
        else:
            pending_hashes.add(content_hash)
        # NAPOMENA (samo za stvaran upsert): odluka_id se NE dodaje u done_ids,
        # i content_hash se NE dodaje u seen_hashes ovde — oba se dešavaju u
        # _flush_buffer(), tek posle potvrđenog upserta (vidi komentar gore).

        # Embed + upsert kada buffer dostigne batch veličinu
        if not args.dry_run and len(chunk_buffer) >= args.batch:
            _flush_buffer()

        # Progress log svakih 1000 odluka
        if i % 1000 == 0:
            log.info(
                "Napredak: %d/%d odluka | chunks=%d | vektori=%d | preskočeno=%d",
                i, len(json_files),
                stats["chunk_ukupno"],
                stats["vektori_upsertovani"],
                stats["odluke_preskocene"],
            )

        # Checkpoint svakih CKPT_EVERY odluka
        if i % CKPT_EVERY == 0 and not args.dry_run:
            save_checkpoint(odluke_dir, done_ids, failed_ids, seen_hashes, stats)

    # ── Završni flush ─────────────────────────────────────────────────────────
    if not args.dry_run:
        _flush_buffer(force=True)
        save_checkpoint(odluke_dir, done_ids, failed_ids, seen_hashes, stats)

    # ── Izveštaj ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("INGESTION ZAVRŠEN" if not args.dry_run else "DRY RUN ZAVRŠEN")
    print("=" * 65)
    print(f"  Odluke procesirane : {stats['odluke_procesirane']}")
    print(f"  Odluke preskočene  : {stats['odluke_preskocene']}")
    print(f"  Odluke duplikat    : {stats['odluke_duplikat']}")
    print(f"  Greške (retry-će se): {stats['odluke_greska']} (failed_ids: {len(failed_ids)})")
    print(f"  Chunks ukupno      : {stats['chunk_ukupno']}")

    if not args.dry_run:
        count_after = ns_count(index, TARGET_NAMESPACE)
        print(f"  Vektori upsertovani: {stats['vektori_upsertovani']}")
        print(f"  Pinecone '{TARGET_NAMESPACE}': {count_before} → {count_after} vektora")

    print("=" * 65)

    if args.dry_run:
        avg_chunks = stats["chunk_ukupno"] / max(stats["odluke_procesirane"], 1)
        print(f"\n  Prosek chunks/odluka: {avg_chunks:.1f}")
        est_total = int(stats["chunk_ukupno"] / max(stats["odluke_procesirane"], 1) * 87_000)
        print(f"  Procena za 87k odluka: ~{est_total:,} vektora u Pinecone")
        print(f"  Namespace target: {TARGET_NAMESPACE}")

    print()


if __name__ == "__main__":
    main()
