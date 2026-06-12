#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_zdi_mca.py — Jednokratni scraper za ZDI + MiCA seed podatke.
Pokreni lokalno: python scrape_zdi_mca.py
Puni Pinecone namespace: "web3_zdi_mca"

NAPOMENA: paragraf.rs može imati rate limiting.
Ako dobiješ 403/429, dodaj time.sleep(2) između zahteva.
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import re
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

# ── Konfiguracija ─────────────────────────────────────────────────────────────
PINECONE_API_KEY  = os.environ["PINECONE_API_KEY"]
PINECONE_HOST     = os.environ.get("PINECONE_HOST", "")
PINECONE_INDEX    = os.environ.get("PINECONE_INDEX_NAME", "vindex-ai")
OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]
NAMESPACE         = "web3_zdi_mca"
CHUNK_SIZE        = 500
CHUNK_OVERLAP     = 50
EMBED_MODEL       = "text-embedding-3-large"
BATCH_SIZE        = 50

# ── Klijenti ──────────────────────────────────────────────────────────────────
pc = Pinecone(api_key=PINECONE_API_KEY)
if PINECONE_HOST:
    index = pc.Index(host=PINECONE_HOST)
else:
    index = pc.Index(PINECONE_INDEX)
client = OpenAI(api_key=OPENAI_API_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "sr,en;q=0.9",
}

# ── MiCA seed tekstovi (ugrađeni — ne scrape) ─────────────────────────────────
MICA_SEED_TEKSTOVI = [
    {
        "id": "mica_overview",
        "naslov": "MiCA — Opšti pregled (Regulation EU 2023/1114)",
        "tekst": "Markets in Crypto-Assets Regulation (MiCA), Regulation (EU) 2023/1114, je prva sveobuhvatna EU regulativa za kripto-aktive. Na snazi od 30. decembra 2024. godine. Reguliše izdavanje, javnu ponudu i pružanje usluga u vezi sa kripto-aktivama u svim EU državama članicama. MiCA je primenljiva na: asset-referenced tokene (ART), e-money tokene (EMT) i ostale kripto-aktive. CASPs (Crypto-Asset Service Providers) moraju biti autorizovani u skladu sa Title V MiCA. Srbija nije članica EU, ali srpski subjekti koji pružaju usluge EU klijentima moraju biti MiCA usklađeni. MiCA beli papir (whitepaper) mora sadržati podatke o izdavaocu, kripto-aktivu, rizicima i pravima ulagača.",
    },
    {
        "id": "mica_casp",
        "naslov": "MiCA — CASP (Crypto-Asset Service Providers) — Title V",
        "tekst": "CASP po MiCA je svako pravno lice koje profesionalno pruža usluge u vezi sa kripto-aktivama: čuvanje i upravljanje, upravljanje platformom za trgovanje, zamenu kripto-aktiva za novac/drugu kripto-aktivu, izvršenje naloga, plasman, primanje i prenos naloga, savetovanje, upravljanje portfoliom. CASP mora biti autorizovan od nadležnog organa EU države u kojoj ima sedište. Autorizacija važi u svim EU državama (passport). Uslovi: dobar ugled, minimalni kapital, organizacioni zahtevi, AML/CFT usklađenost. Kazne za neovlašćeno pružanje CASP usluga: do 5 miliona EUR ili 3% godišnjeg prometa.",
    },
    {
        "id": "mica_art_emt",
        "naslov": "MiCA — Asset-Referenced Tokens i E-Money Tokens (Titles III i IV)",
        "tekst": "Asset-Referenced Token (ART) po MiCA je kripto-aktiva čija vrednost je vezana za više valuta, roba ili kripto-aktiva. Izdavalac ART mora biti autorizovan od nadležnog organa EU. E-Money Token (EMT) je kripto-aktiva vezana za jednu fiat valutu. Izdavalac EMT mora biti kreditna institucija ili e-novac institucija. Za ART i EMT pravila važe od 30.06.2024. Obaveze: whitepaper, likvidnosna rezerva (full backing), periodični audit rezervi, pravo na otkup od strane imaoca.",
    },
    {
        "id": "mica_whitepaper",
        "naslov": "MiCA — Whitepaper zahtevi (čl. 6 i dalje)",
        "tekst": "Whitepaper po MiCA (čl. 6) mora sadržati: identitet i kontakt podatke izdavaoca, opis projekta i tehnologije, prava i obaveze imaoca tokena, rizike, uslove ponude, podatke o eventualnoj podlozi. Whitepaper se podnosi nadležnom organu najmanje 20 radnih dana pre objave. Odgovornost za tačnost informacija u whitepaper-u je solidarna. Izuzetak od whitepaper obaveze: ponuda manja od 1 milion EUR u 12 meseci, ponuda do 150 lica po državi, ponuda samo institucionalnim investitorima.",
    },
    {
        "id": "mica_market_abuse",
        "naslov": "MiCA — Zabrana zloupotrebe tržišta (Title VI)",
        "tekst": "MiCA Title VI zabranjuje insider trading, market manipulation i unlawful disclosure of inside information na kripto-tržištima. Insider information = precizna, javno neobjavljena informacija koja bi značajno uticala na cenu kripto-aktive. Zabranjena ponašanja: wash trading, spoofing, front-running, pump and dump. Kazne: do 15% godišnjeg prometa ili 15 miliona EUR (koji je veći iznos). Krivična odgovornost fizičkih lica za namerne povrede.",
    },
    {
        "id": "mica_vs_zdi",
        "naslov": "Poređenje ZDI (Srbija) i MiCA (EU) — ključne razlike",
        "tekst": "ZDI (Srbija, Sl. glasnik 153/2020) i MiCA (EU 2023/1114) pokrivaju sličnu materiju ali se razlikuju. ZDI deli digitalnu imovinu na: virtuelne valute (NBS) i digitalne tokene (KHoV). MiCA deli na: ART, EMT i ostale kripto-aktive. Obe regulative zahtevaju beli papir (whitepaper). Razlika: ZDI prag bez odobrenja je 100.000 EUR/12 meseci ili manje od 20 lica; MiCA prag je 1 milion EUR/12 meseci ili do 150 lica. Srpski subjekti koji ciljaju EU tržište moraju biti usklađeni sa oba propisa.",
    },
    {
        "id": "zdi_porez",
        "naslov": "Oporezivanje digitalne imovine u Srbiji — ZDI + ZPDG",
        "tekst": "Prihodi od prodaje digitalne imovine u Srbiji oporezuju se kao kapitalni dobitak po stopi od 15% (čl. 79 ZPDG). Kapitalni dobitak = razlika između prodajne i nabavne cene. Oslobođenje 50% poreza: ako poreski obveznik u roku od 90 dana reinvestira prihod u osnovni kapital firme u RS. Poreska obaveza nastaje pri prodaji, razmeni ili konverziji digitalne imovine. PDV: virtuelne valute su oslobođene PDV-a. Izveštavanje: Poreska uprava, obrasci specifični za kapitalnu dobit.",
    },
    {
        "id": "zdi_kazne",
        "naslov": "ZDI — Kaznene odredbe (čl. 140-144)",
        "tekst": "Kaznene odredbe ZDI (čl. 140-144) predviđaju: Privredni prestup za pravno lice: novčana kazna 500.000 do 3.000.000 dinara za neovlašćeno pružanje usluga. Prekršaj za fizičko lice: novčana kazna 50.000 do 500.000 dinara. Krivično delo: ko bez dozvole pruža usluge sa digitalnom imovinom u vidu zanimanja ili radi sticanja imovinske koristi — zatvor do 3 godine i novčana kazna. Nadzor: NBS za virtuelne valute, KHoV za digitalne tokene.",
    },
    {
        "id": "zdi_aml_kyc",
        "naslov": "ZDI — AML/KYC obaveze (čl. 81-97)",
        "tekst": "Pružaoci usluga sa digitalnom imovinom po ZDI moraju sprovesti mere sprečavanja pranja novca i finansiranja terorizma (čl. 81-97). KYC obaveze: identifikacija stranke, proveravanje identiteta, praćenje poslovnog odnosa. Pojačane mere za politički eksponirana lica (PEP). Obaveza čuvanja dokumentacije: minimum 5 godina. Travel rule: podaci o pošiljaocu i primaocu pri transferu digitalne imovine iznad 1.000 EUR. Prijavljivanje sumljivih transakcija Upravi za sprečavanje pranja novca.",
    },
]


def chunkovati_tekst(tekst: str) -> list[str]:
    chunks = []
    for i in range(0, len(tekst), CHUNK_SIZE - CHUNK_OVERLAP):
        chunk = tekst[i:i + CHUNK_SIZE].strip()
        if len(chunk) > 50:
            chunks.append(chunk)
    return chunks


def generisi_embedding(tekst: str) -> list[float]:
    response = client.embeddings.create(model=EMBED_MODEL, input=tekst)
    return response.data[0].embedding


def upsert_batch(vektori: list[dict]):
    for i in range(0, len(vektori), BATCH_SIZE):
        batch = vektori[i:i + BATCH_SIZE]
        index.upsert(vectors=batch, namespace=NAMESPACE)
        print(f"  Upisano {min(i + BATCH_SIZE, len(vektori))}/{len(vektori)} vektora")
        time.sleep(0.5)


def scrape_zdi_paragraf() -> list[dict]:
    url = "https://www.paragraf.rs/propisi/zakon-o-digitalnoj-imovini.html"
    print(f"Scrapujem ZDI sa: {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        time.sleep(2)
    except Exception as e:
        print(f"UPOZORENJE: Scrape neuspešan ({e}). Koristiće se samo seed tekstovi.")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    tekst_ceo = soup.get_text(separator="\n", strip=True)

    pattern = re.compile(
        r"(Član\s+(\d+[a-z]?)\.?)\s*\n(.*?)(?=Član\s+\d+|$)",
        re.DOTALL | re.UNICODE,
    )
    matches = pattern.findall(tekst_ceo[:200000])

    clanovi = []
    for clan_naziv, broj, tekst in matches:
        tekst_clean = re.sub(r"\s+", " ", tekst).strip()
        if len(tekst_clean) > 20:
            clanovi.append({
                "clan": f"ZDI čl. {broj}",
                "naslov": clan_naziv,
                "tekst": f"{clan_naziv} ZDI:\n{tekst_clean}",
            })

    print(f"  Pronađeno {len(clanovi)} članova ZDI")
    return clanovi


def ingestuj_zdi_mca():
    print(f"\n=== VINDEX AI — Ingest ZDI + MiCA u namespace: {NAMESPACE} ===\n")
    svi_vektori = []

    print("Processujem MiCA seed tekstove...")
    for item in MICA_SEED_TEKSTOVI:
        chunks = chunkovati_tekst(item["tekst"])
        for idx_c, chunk in enumerate(chunks):
            vec_id = f"{item['id']}_chunk_{idx_c}"
            embedding = generisi_embedding(chunk)
            svi_vektori.append({
                "id": vec_id,
                "values": embedding,
                "metadata": {
                    "tekst": chunk,
                    "naslov": item["naslov"],
                    "izvor": "MiCA EU 2023/1114",
                    "tip": "mica_seed",
                    "propis": "MiCA",
                },
            })
        print(f"  ✓ {item['naslov'][:60]}...")
        time.sleep(0.3)

    print("\nScrapujem ZDI sa paragraf.rs...")
    zdi_clanovi = scrape_zdi_paragraf()

    if zdi_clanovi:
        for clan in zdi_clanovi:
            chunks = chunkovati_tekst(clan["tekst"])
            for idx_c, chunk in enumerate(chunks):
                vec_id = f"zdi_{hashlib.md5(clan['clan'].encode()).hexdigest()[:8]}_chunk_{idx_c}"
                embedding = generisi_embedding(chunk)
                svi_vektori.append({
                    "id": vec_id,
                    "values": embedding,
                    "metadata": {
                        "tekst": chunk,
                        "naslov": clan["clan"],
                        "izvor": "ZDI Sl. glasnik RS 153/2020",
                        "tip": "zdi_clan",
                        "propis": "ZDI",
                    },
                })
            time.sleep(0.2)
        print(f"  ✓ {len(zdi_clanovi)} članova ZDI processurano")
    else:
        print("  ! ZDI scrape neuspešan — nastavljamo samo sa seed tekstovima")

    print(f"\nUpisujem {len(svi_vektori)} vektora u namespace '{NAMESPACE}'...")
    upsert_batch(svi_vektori)
    print(f"\n✅ INGEST ZAVRŠEN: {len(svi_vektori)} vektora → namespace '{NAMESPACE}'")
    print("Pokretanje API servera je sada moguće sa Web3/MiCA funkcionalnostima.")


if __name__ == "__main__":
    ingestuj_zdi_mca()
