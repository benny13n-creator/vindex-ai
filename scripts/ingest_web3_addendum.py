# -*- coding: utf-8 -*-
"""
Ingest Web3 Addendum — dodaje nedostajuće chunkove u web3_zdi_mca namespace:
  1. ZOO čl. 552 — Ugovor o razmeni (pojam)
  2. ZOO čl. 553 — Ugovor o razmeni (dejstva)
  3. Sintetizovani vodič: B2B razmena digitalne imovine
  4. Sintetizovani vodič: DI i cross-border transakcije
  5. Sintetizovani vodič: Distinkcija barter vs. maloprodajno plaćanje

Run: python scripts/ingest_web3_addendum.py
     python scripts/ingest_web3_addendum.py --dry-run
"""

import os
import sys
import time
import hashlib
import argparse
import logging
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_web3_addendum")

NAMESPACE    = "web3_zdi_mca"
EMBED_MODEL  = "text-embedding-3-large"

# ── Novi chunkovi ─────────────────────────────────────────────────────────────

NOVI_CHUNKOVI = [
    {
        "id":    "zoo_cl552_chunk_0",
        "naslov": "ZOO čl. 552 — Ugovor o razmeni (pojam)",
        "izvor":  "ZOO Sl. glasnik RS 29/1978, 39/1985, 45/1989, 57/1989",
        "propis": "ZOO",
        "tip":    "zoo_clan",
        "tekst": (
            "Član 552 ZOO:\n"
            "(1) Ugovorom o razmeni svaki ugovarač se obavezuje prema svom saugovaraču "
            "da prenese na njega svojinu neke stvari i da mu je u tu svrhu preda.\n"
            "(2) Predmet razmene mogu biti i druga prenosiva prava.\n\n"
            "NAPOMENA ZA DIGITALNU IMOVINU: Digitalna imovina kao 'prenosivo pravo' (stav 2) "
            "može biti predmet ugovora o razmeni. Srpska kompanija može zaključiti ugovor "
            "o razmeni sa inostranom kompanijom kojim daje digitalnu imovinu a prima robu "
            "ili usluge (i obrnuto). ZOO čl. 552 je generalni pravni osnov za barter/razmenu."
        ),
    },
    {
        "id":    "zoo_cl553_chunk_0",
        "naslov": "ZOO čl. 553 — Ugovor o razmeni (dejstva)",
        "izvor":  "ZOO Sl. glasnik RS 29/1978, 39/1985, 45/1989, 57/1989",
        "propis": "ZOO",
        "tip":    "zoo_clan",
        "tekst": (
            "Član 553 ZOO:\n"
            "Iz ugovora o razmeni nastaju za svakog ugovarača obaveze i prava koje iz "
            "ugovora o prodaji nastaju za prodavca.\n\n"
            "PRIMENA NA DI: Oba učesnika B2B barter transakcije imaju iste obaveze "
            "i prava kao prodavac u ugovoru o prodaji — odgovornost za nedostatke, "
            "obaveza prenosa prava, zaštita od evikcije. ZOO čl. 452-556 (prodaja) "
            "primenjuje se shodnom primenom na obe strane ugovora o razmeni."
        ),
    },
    {
        "id":    "zdi_b2b_razmena_vodic",
        "naslov": "B2B razmena digitalne imovine — pravni vodič (ZDI + ZOO)",
        "izvor":  "ZDI Sl. glasnik RS 153/2020 + ZOO Sl. glasnik RS 29/1978",
        "propis": "ZDI",
        "tip":    "zdi_vodic",
        "tekst": (
            "B2B RAZMENA DIGITALNE IMOVINE — PRAVNI VODIČ\n\n"
            "PITANJE: Da li srpska kompanija može zaključiti ugovor o razmeni digitalne imovine "
            "sa inostranom kompanijom?\n\n"
            "ODGOVOR — DA, uz ispunjenje zakonskih uslova:\n\n"
            "1. PRAVNI OSNOV:\n"
            "   • ZDI čl. 2: Digitalna imovina se može 'kupovati, prodavati, razmenjivati ili prenositi' "
            "— reč 'razmenjivati' eksplicitno uključuje barter između pravnih lica.\n"
            "   • ZOO čl. 552: Ugovor o razmeni — svaki ugovarač prenosi na drugog svojinu "
            "neke stvari ili drugog prenosivog prava. Digitalna imovina kao prenosivo pravo "
            "može biti predmet razmene.\n"
            "   • ZOO čl. 553: Prava i obaveze prodavca iz ugovora o prodaji primenjuju se "
            "na oba učesnika ugovora o razmeni.\n\n"
            "2. ŠTA NIJE ZABRANJENO:\n"
            "   • ZDI ne zabranjuje B2B barter između dve kompanije.\n"
            "   • Zabrana iz ZDI čl. 97 odnosi se isključivo na maloprodaju (B2C, "
            "potrošač→trgovac) — ne na B2B ugovore između pravnih lica.\n\n"
            "3. OBAVEZNI USLOVI:\n"
            "   • Ako transakcija zahteva konverziju DI u/iz RSD: obavezno koristiti "
            "licenciranog VASP pružaoca (ZDI čl. 29).\n"
            "   • Za inostrane transakcije primenjuje se ZDP (Zakon o deviznom poslovanju) — "
            "tekuće i kapitalne transakcije podležu posebnim pravilima.\n"
            "   • AML/KYC: ZSPNFT čl. 9 — KYC obaveza za transakcije ≥15.000 EUR.\n\n"
            "4. PREPORUČENA FORMA:\n"
            "   Pisani ugovor o razmeni (ZOO čl. 552) sa eksplicitnom specifikacijom: "
            "vrsta i količina DI, tržišna vrednost u EUR/RSD na dan transakcije, "
            "obaveze prenosa, rok isporuke, i merodavno pravo."
        ),
    },
    {
        "id":    "zdi_crossborder_vodic",
        "naslov": "Cross-border transakcije digitalne imovine — ZDI + ZDP",
        "izvor":  "ZDI Sl. glasnik RS 153/2020",
        "propis": "ZDI",
        "tip":    "zdi_vodic",
        "tekst": (
            "CROSS-BORDER TRANSAKCIJE DIGITALNE IMOVINE\n\n"
            "Kada srpska kompanija trguje digitalnom imovinom sa inostranom kompanijom, "
            "primenjuju se dva pravna sloja:\n\n"
            "SLOJ 1 — ZDI (lex specialis za DI):\n"
            "• ZDI čl. 2: DI se može 'razmenjivati ili prenositi' — cross-border transfer dozvoljen.\n"
            "• ZDI čl. 94: VASP pružalac može pružati usluge i u stranoj državi "
            "(direktno ili preko ogranka), u skladu s propisima te države.\n"
            "• ZDI čl. 29: Svaki VASP koji posreduje u transakciji mora imati dozvolu NBS ili KHoV.\n\n"
            "SLOJ 2 — ZDP (Zakon o deviznom poslovanju):\n"
            "• Tekuće devizne transakcije (plaćanje za robu/usluge): slobodne uz obavezno "
            "korišćenje ovlašćene banke za konverziju.\n"
            "• Kapitalne transakcije (investicije, zajmovi): podležu posebnim uslovima NBS.\n"
            "• Obaveza izveštavanja NBS za transakcije iznad praga.\n\n"
            "AML ASPEKT (ZSPNFT):\n"
            "• ZSPNFT čl. 9: KYC identifikacija obavezna za transakcije ≥15.000 EUR.\n"
            "• Travel Rule (FATF R.16): Za transfere ≥1.000 EUR prenose se podaci "
            "o pošiljaocu i primaocu.\n\n"
            "KLJUČNI ZAKLJUČAK: Cross-border transakcija DI između srpske i inostrane "
            "kompanije je dozvoljena uz: (1) licencirani VASP ako se vrši konverzija, "
            "(2) poštovanje ZDP propisa, (3) KYC po ZSPNFT."
        ),
    },
    {
        "id":    "zdi_barter_vs_placanje_distinkcija",
        "naslov": "Distinkcija: B2B barter DI vs. maloprodajno plaćanje DI (čl. 97)",
        "izvor":  "ZDI Sl. glasnik RS 153/2020",
        "propis": "ZDI",
        "tip":    "zdi_vodic",
        "tekst": (
            "KLJUČNA DISTINKCIJA: BARTER vs. MALOPRODAJNO PLAĆANJE DIGITALNOM IMOVINOM\n\n"
            "SLUČAJ A — B2B BARTER (DOZVOLJENO):\n"
            "Kompanija A daje BTC kompaniji B, kompanija B daje robu/usluge kompaniji A.\n"
            "Pravni osnov: ZOO čl. 552 (ugovor o razmeni) + ZDI čl. 2 ('razmenjivati').\n"
            "ZDI NE zabranjuje ovaj oblik transakcije.\n"
            "Obaveza: koristiti licenciranog VASP-a za konverziju u RSD (ZDI čl. 29).\n\n"
            "SLUČAJ B — MALOPRODAJNO PLAĆANJE (REGULISANO — čl. 97):\n"
            "Potrošač plaća digitalnom imovinom u prodavnici.\n"
            "Prema ZDI čl. 97: prihvatanje DI u zamenu za robu/usluge u trgovini na malo "
            "MOŽE SE VRŠITI ISKLJUČIVO PREKO pružaoca usluga sa dozvolom iz čl. 3 st. 1 t. 7.\n"
            "Direktan prenos digitalne imovine neposredno sa potrošača na trgovca je ZABRANJEN.\n"
            "VASP mora: primiti DI od potrošača → zameniti za zakonsko sredstvo plaćanja "
            "→ preneti iznos na račun trgovca.\n\n"
            "ZAKLJUČAK:\n"
            "• Čl. 97 ZDI reguliše B2C (maloprodajni) scenario — ne primenjuje se na B2B.\n"
            "• B2B barter između pravnih lica uređuje ZOO čl. 552-553 uz ZDI čl. 2.\n"
            "• Oba slučaja zahtevaju VASP posrednika ako postoji konverzija u RSD."
        ),
    },
]


def _embed(client, text: str) -> list:
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from pinecone import Pinecone
    import openai

    api_key_pc = os.environ.get("PINECONE_API_KEY", "")
    api_key_oa = os.environ.get("OPENAI_API_KEY", "")
    index_name = os.environ.get("PINECONE_INDEX_NAME", "vindex")

    if not api_key_pc or not api_key_oa:
        log.error("PINECONE_API_KEY ili OPENAI_API_KEY nedostaje.")
        sys.exit(1)

    pc    = Pinecone(api_key=api_key_pc)
    index = pc.Index(index_name)
    oa    = openai.OpenAI(api_key=api_key_oa)

    log.info("Pocetak ingesta %d chunkova → namespace=%s", len(NOVI_CHUNKOVI), NAMESPACE)

    vektori = []
    for chunk in NOVI_CHUNKOVI:
        log.info("Embedding: %s", chunk["naslov"])
        vec = _embed(oa, chunk["tekst"])
        vektori.append({
            "id": chunk["id"],
            "values": vec,
            "metadata": {
                "naslov": chunk["naslov"],
                "izvor":  chunk["izvor"],
                "propis": chunk["propis"],
                "tip":    chunk["tip"],
                "tekst":  chunk["tekst"],
            },
        })
        time.sleep(0.3)

    if args.dry_run:
        log.info("[DRY-RUN] Preskacemo upsert. Vektori koji bi bili upisani:")
        for v in vektori:
            log.info("  ID=%s | tekst=%d znakova", v["id"], len(v["metadata"]["tekst"]))
        return

    index.upsert(vectors=vektori, namespace=NAMESPACE)
    log.info("Upsert zavrsen: %d vektora u %s", len(vektori), NAMESPACE)

    # Verifikacija
    time.sleep(2)
    stats = index.describe_index_stats()
    ns_count = stats.namespaces.get(NAMESPACE, {})
    count = getattr(ns_count, 'vector_count', '?')
    log.info("Namespace %s sada ima %s vektora.", NAMESPACE, count)


if __name__ == "__main__":
    main()
