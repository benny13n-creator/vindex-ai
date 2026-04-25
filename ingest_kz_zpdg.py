# -*- coding: utf-8 -*-
"""
Vindex AI — Scrape i ingest Krivičnog zakonika + ZPDG u Pinecone.

Pokretanje:
    python ingest_kz_zpdg.py [--only-scrape] [--only-index] [--test]

Opcije:
    --only-scrape   Samo skine HTML i sačuva .pdf tekstove (ne diraj Pinecone)
    --only-index    Samo indeksira već sačuvane .pdf tekstove (ne skida HTML)
    --test          Posle indexiranja pokreni test querije i ispiši rezultate
"""

import os
import re
import sys
import time
import hashlib
import logging

import requests
from bs4 import BeautifulSoup
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest")

# ─── Konfiguracija ───────────────────────────────────────────────────────────

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
INDEX_NAME       = "vindex-ai"
EMBEDDING_MODEL  = "text-embedding-3-large"
BATCH_SIZE       = 40
MIN_TEKST_DUZINA = 80
MAX_TEKST_DUZINA = 2000

PDF_FOLDER = Path(__file__).parent / "data" / "laws" / "pdfs"

ZAKONI = [
    {
        "url":   "https://www.paragraf.rs/propisi/krivicni_zakonik.html",
        "naziv": "KZ",
        "fajl":  "krivicni_zakonik.pdf",
        "prioritetni": [170, 208, 302, 303, 304],
    },
    {
        "url":   "https://www.paragraf.rs/propisi/zakon-o-porezu-na-dohodak-gradjana.html",
        "naziv": "ZPDG",
        "fajl":  "zakon_o_porezu_na_dohodak_gradjana.pdf",
        "prioritetni": list(range(72, 80)),
    },
    {
        "url":   "https://www.paragraf.rs/propisi/zakon-o-privrednim-drustvima.html",
        "naziv": "zakon o privrednim drustvima",
        "fajl":  "zakon_o_privredin_drustvima.pdf",
        "prioritetni": [10, 11, 12, 13, 14, 31, 32, 33, 139, 140, 141],
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sr,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TEST_QUERIJI = [
    "neovlašćen pristup računaru krivično delo",
    "kapitalni dobitak kriptovaluta porez",
    "kompjuterski kriminal zloupotreba",
    "porez na dohodak digitalna imovina prihod",
]

# ─── Scraping ────────────────────────────────────────────────────────────────

def _skini_stranicu(url: str, pokusaji: int = 3) -> str:
    """Skida HTML stranicu sa retry logikom."""
    for i in range(pokusaji):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text
        except requests.RequestException as e:
            log.warning("Pokušaj %d/%d neuspešan: %s", i + 1, pokusaji, e)
            if i < pokusaji - 1:
                time.sleep(3 * (i + 1))
    raise RuntimeError(f"Nije moguće skinuti: {url}")


def _izvuci_tekst_iz_html(html: str) -> str:
    """
    Parsira HTML paragraf.rs propisa i vraća čist tekst zakona.

    paragraf.rs struktura:
    - Glavni tekst u <div class="clan-naslov"> i <div class="clan-tekst">
    - Alternativno: <div id="div_text"> ili <article>
    - Naslovi članova: <h2> ili <strong> sa "Član X"
    """
    soup = BeautifulSoup(html, "html.parser")

    # Ukloni neбитne elemente
    for tag in soup.find_all(["script", "style", "nav", "header", "footer",
                               "aside", ".ads", ".advertisement"]):
        tag.decompose()

    # Pokušaj da nađemo glavni sadržaj zakona
    # paragraf.rs koristi različite selektore zavisno od propisa
    kandidati = [
        soup.find("div", {"id": "div_text"}),
        soup.find("div", {"class": "propis-tekst"}),
        soup.find("div", {"class": "law-content"}),
        soup.find("div", {"id": "propis"}),
        soup.find("main"),
        soup.find("article"),
        soup.find("div", {"class": re.compile(r"content|tekst|propis", re.I)}),
    ]
    kontejner = next((k for k in kandidati if k is not None), None)

    if kontejner:
        tekst = kontejner.get_text(separator="\n", strip=True)
    else:
        # Fallback: ceo body
        tekst = soup.get_text(separator="\n", strip=True)

    # Čišćenje: ukloni višestruke prazne redove
    linije = [l.rstrip() for l in tekst.split("\n")]
    rezultat = []
    prev_blank = False
    for l in linije:
        if not l.strip():
            if not prev_blank:
                rezultat.append("")
            prev_blank = True
        else:
            rezultat.append(l)
            prev_blank = False

    return "\n".join(rezultat).strip()


def skini_i_sacuvaj(zakon: dict) -> Path:
    """Skida zakon sa paragraf.rs i čuva ga kao plain text u pdf fajl."""
    log.info("Skidam: %s", zakon["url"])
    html = _skini_stranicu(zakon["url"])
    tekst = _izvuci_tekst_iz_html(html)

    # Provera da li je tekst prihvatljiv
    clan_count = len(re.findall(r"(?m)^Član\s+\d+", tekst))
    log.info("  Ekstraktovan tekst: %d znakova, ~%d članova", len(tekst), clan_count)

    if clan_count < 5:
        log.warning("  [!] Malo članova (%d) — paragraf.rs možda blokira ili promenio strukturu", clan_count)

    putanja = PDF_FOLDER / zakon["fajl"]
    putanja.write_text(tekst, encoding="utf-8")
    log.info("  Sačuvano: %s", putanja)
    return putanja


# ─── Chunking ────────────────────────────────────────────────────────────────

def _podeli_na_clanove(tekst: str, naziv_zakona: str,
                       prioritetni: list[int] | None = None) -> list[dict]:
    """
    Deli tekst zakona po članovima.
    Prioritetni članovi dobijaju dupli chunk za bolji retrieval recall.
    """
    pattern = re.compile(
        r"(?m)^[ \t]*(?:Član|ČLAN|Čl\.|ČL\.)\s+(\d+[a-zA-Zа-яА-Я]?)\b",
        re.UNICODE,
    )
    matches = list(pattern.finditer(tekst))
    if not matches:
        log.warning("  Nije pronađen nijedan član u tekstu!")
        return [{"clan": "Opšte odredbe", "tekst": tekst[:MAX_TEKST_DUZINA]}]

    prioritetni_set = set(prioritetni or [])
    clanovi = []
    vidjeni_clanovi: set[str] = set()  # deduplication — zadržavamo prvu pojavu

    for i, m in enumerate(matches):
        broj_str = m.group(1)
        # Preskoči [sX] annotated verzije u appendix sekcijama
        pos_pre = m.start() - 1
        if pos_pre >= 0 and tekst[pos_pre] in "[]":
            continue

        label = f"Član {broj_str}"
        if label in vidjeni_clanovi:
            continue  # dedup — zadržavamo samo prvu pojavu
        vidjeni_clanovi.add(label)

        try:
            broj_int = int(re.sub(r"[^0-9]", "", broj_str))
        except ValueError:
            broj_int = -1

        pocetak = m.start()
        kraj    = matches[i + 1].start() if i + 1 < len(matches) else len(tekst)
        tekst_c = tekst[pocetak:kraj].strip()

        if len(tekst_c) < MIN_TEKST_DUZINA:
            continue

        # Prefiks za bolji semantički kontekst u vektorskoj bazi
        prefiks = f"ZAKON: {naziv_zakona}\n"
        unos = {
            "clan":  label,
            "tekst": (prefiks + tekst_c)[:MAX_TEKST_DUZINA],
        }
        clanovi.append(unos)

        # Prioritetni članovi → dual chunk bez prefiksa za bolji recall
        if broj_int in prioritetni_set:
            clanovi.append({
                "clan":  label,
                "tekst": tekst_c[:MAX_TEKST_DUZINA],
                "_dual": True,
            })
            log.info("    [★] Prioritetan član %s — dual chunk", broj_str)

    return clanovi


# ─── Embedding i Pinecone ────────────────────────────────────────────────────

def _embed_batch(tekstovi: list[str], client) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=tekstovi)
    return [e.embedding for e in resp.data]


def _vektor_id(zakon: str, clan: str, verzija: str = "") -> str:
    key = f"{zakon}|{clan}|{verzija}"
    return hashlib.md5(key.encode()).hexdigest()


def indeksiraj(zakon: dict, index, client) -> int:
    """Čita sačuvani fajl i indeksira u Pinecone. Vraća broj upisanih vektora."""
    putanja = PDF_FOLDER / zakon["fajl"]
    if not putanja.exists():
        raise FileNotFoundError(f"Fajl nije pronađen: {putanja}")

    tekst  = putanja.read_text(encoding="utf-8")
    naziv  = zakon["naziv"]
    clanovi = _podeli_na_clanove(tekst, naziv, zakon.get("prioritetni"))
    log.info("  %s → %d chunkova za indeksiranje", naziv, len(clanovi))

    ukupno = 0
    for i in range(0, len(clanovi), BATCH_SIZE):
        batch    = clanovi[i:i + BATCH_SIZE]
        tekstovi = [c["tekst"] for c in batch]

        try:
            embeddinzi = _embed_batch(tekstovi, client)
        except Exception as e:
            log.error("  [GREŠKA] Embedding batch %d: %s", i // BATCH_SIZE + 1, e)
            time.sleep(5)
            continue

        vektori = []
        for j, (c, emb) in enumerate(zip(batch, embeddinzi)):
            verzija = "dual" if c.get("_dual") else ""
            vektori.append({
                "id":       _vektor_id(naziv, c["clan"], verzija),
                "values":   emb,
                "metadata": {
                    "law":     naziv,
                    "article": c["clan"],
                    "text":    c["tekst"],
                },
            })

        try:
            index.upsert(vectors=vektori)
            ukupno += len(vektori)
            log.info("  → Batch %d: upisano %d vektora (ukupno: %d)",
                     i // BATCH_SIZE + 1, len(vektori), ukupno)
        except Exception as e:
            log.error("  [GREŠKA] Pinecone upsert: %s", e)

        time.sleep(0.4)

    return ukupno


# ─── Test queriji ────────────────────────────────────────────────────────────

def test_queriji(index, client) -> None:
    """Pokreće test querije i ispisuje top 3 rezultata za svaki."""
    log.info("\n" + "=" * 60)
    log.info("TEST QUERIJI")
    log.info("=" * 60)

    for query in TEST_QUERIJI:
        log.info("\nQuery: '%s'", query)
        try:
            resp = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
            vektor = resp.data[0].embedding

            rezultati = index.query(
                vector=vektor,
                top_k=5,
                include_metadata=True,
            )
            if not rezultati.matches:
                log.warning("  → NEMA REZULTATA")
                continue

            for r in rezultati.matches[:3]:
                meta  = r.metadata or {}
                zakon = meta.get("law", "?")
                clan  = meta.get("article", "?")
                tekst = (meta.get("text", "") or "")[:120].replace("\n", " ")
                log.info(
                    "  [%.3f] %s / %s — %s...",
                    r.score, zakon, clan, tekst,
                )
        except Exception as e:
            log.error("  [GREŠKA] Query '%s': %s", query, e)

    log.info("\n" + "=" * 60)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    samo_scrape = "--only-scrape" in sys.argv
    samo_index  = "--only-index"  in sys.argv
    pokreni_test = "--test"       in sys.argv

    if not PINECONE_API_KEY:
        log.error("PINECONE_API_KEY nije postavljen u .env")
        sys.exit(1)
    if not OPENAI_API_KEY:
        log.error("OPENAI_API_KEY nije postavljen u .env")
        sys.exit(1)

    PDF_FOLDER.mkdir(parents=True, exist_ok=True)

    # ── SCRAPING ─────────────────────────────────────────────────────────────
    if not samo_index:
        log.info("=== SCRAPING PARAGRAF.RS ===")
        for zakon in ZAKONI:
            fajl = PDF_FOLDER / zakon["fajl"]
            if fajl.exists():
                log.info("  [SKIP] %s već postoji (%d B)", zakon["fajl"], fajl.stat().st_size)
                log.info("  → Brišem i ponovo skidamo...")
            try:
                skini_i_sacuvaj(zakon)
                time.sleep(2)  # Courtesy delay
            except Exception as e:
                log.error("  [GREŠKA] Scraping %s: %s", zakon["naziv"], e)
                if not samo_scrape:
                    log.error("  Preskačem indeksiranje za ovaj zakon.")

    if samo_scrape:
        log.info("=== Scraping završen. Fajlovi čuvani u %s ===", PDF_FOLDER)
        return

    # ── INDEKSIRANJE ──────────────────────────────────────────────────────────
    log.info("\n=== PINECONE INDEKSIRANJE ===")
    from pinecone import Pinecone
    from openai import OpenAI

    pc     = Pinecone(api_key=PINECONE_API_KEY)
    index  = pc.Index(INDEX_NAME)
    client = OpenAI(api_key=OPENAI_API_KEY)

    stats_pre = index.describe_index_stats()
    log.info("Pinecone stats pre indexiranja: %d vektora", stats_pre.total_vector_count)

    ukupno_sve = 0
    for zakon in ZAKONI:
        fajl = PDF_FOLDER / zakon["fajl"]
        if not fajl.exists():
            log.warning("  [SKIP] Fajl ne postoji: %s", zakon["fajl"])
            continue
        log.info("\nIndeksiranje: %s", zakon["naziv"])
        try:
            n = indeksiraj(zakon, index, client)
            ukupno_sve += n
            log.info("  ✓ %s: %d vektora upisano", zakon["naziv"], n)
        except Exception as e:
            log.error("  [GREŠKA] Indeksiranje %s: %s", zakon["naziv"], e)

    time.sleep(3)  # Pinecone write propagation
    stats_posle = index.describe_index_stats()
    log.info(
        "\n=== Završeno! Upisano %d novih vektora. Ukupno u bazi: %d ===",
        ukupno_sve, stats_posle.total_vector_count,
    )

    # ── TEST ──────────────────────────────────────────────────────────────────
    if pokreni_test:
        test_queriji(index, client)


if __name__ == "__main__":
    main()
