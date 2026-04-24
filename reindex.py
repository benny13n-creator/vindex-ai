# -*- coding: utf-8 -*-
"""
Vindex AI — Re-indeksiranje Pinecone baze
Čita sve PDF zakone, deli po članovima, upisuje u Pinecone.
Pokretanje: C:/Python311/python.exe reindex.py
"""

import os
import re
import time
import hashlib
import pdfplumber
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
INDEX_NAME       = "vindex-ai"
EMBEDDING_MODEL  = "text-embedding-3-large"
BATCH_SIZE       = 50
MIN_TEKST_DUZINA = 80

PDF_FOLDER = Path(__file__).parent / "data" / "laws" / "pdfs"

# Mapiranje naziv fajla → naziv zakona u metapodatku
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
    "zakon_o_zastiti_podataka_o_licnosti,": "zakon o zastiti podataka o licnosti",
    "zakon_o_zastiti_potrosaca":           "zakon o zastiti potrosaca",
    "zakon_o_digitalnoj_imovini":          "zakon o digitalnoj imovini",
    "zakon_o_sprecavanju_pranja_novca":    "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "krivicni_zakonik":                    "krivicni zakonik",
    "zakon_o_porezu_na_dohodak_gradjana":  "zakon o porezu na dohodak gradjana",
}


def _normalizuj_ime(ime: str) -> str:
    return re.sub(r"\s+copy$", "", ime.lower().strip())


def _izvuci_tekst_pdf(pdf_path: Path) -> str:
    # Fajlovi su plain text sa .pdf ekstenzijom
    for enc in ("utf-8", "utf-8-sig", "cp1250", "latin-1"):
        try:
            return pdf_path.read_text(encoding=enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return pdf_path.read_text(encoding="utf-8", errors="replace")


def _podeli_na_clanove(tekst: str) -> list[dict]:
    """
    Deli tekst zakona na jednotek po čalnovima.
    Vraća listu {"clan": "Član 374", "tekst": "..."}
    """
    # Pattern: "Član 374" ili "Čl. 374" ili "ČLAN 374" na početku reda
    pattern = re.compile(
        r"(?m)^[ \t]*(?:Član|ČLAN|Čl\.|ČL\.|Member|member)\s+(\d+[a-zA-Zа-яА-Я]?)\b",
        re.UNICODE
    )

    matches = list(pattern.finditer(tekst))
    if not matches:
        # Ako nema prepoznatljivih članova, vrati ceo tekst kao jedan komad
        return [{"clan": "Opšte odredbe", "tekst": tekst[:3000]}]

    clanovi = []
    for i, m in enumerate(matches):
        broj = m.group(1)
        pocetak = m.start()
        kraj = matches[i + 1].start() if i + 1 < len(matches) else len(tekst)
        tekst_clana = tekst[pocetak:kraj].strip()
        if len(tekst_clana) >= MIN_TEKST_DUZINA:
            clanovi.append({
                "clan": f"Član {broj}",
                "tekst": tekst_clana[:2000],  # max 2000 znakova po članu
            })

    return clanovi


def _embed_batch(tekstovi: list[str], client: OpenAI) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=tekstovi)
    return [e.embedding for e in resp.data]


def _vektor_id(zakon: str, clan: str) -> str:
    key = f"{zakon}|{clan}"
    return hashlib.md5(key.encode()).hexdigest()


def main():
    print("=== Vindex AI — Re-indeksiranje ===\n")

    pc     = Pinecone(api_key=PINECONE_API_KEY)
    index  = pc.Index(INDEX_NAME)
    client = OpenAI(api_key=OPENAI_API_KEY)

    pdfs = list(PDF_FOLDER.glob("*.pdf"))
    print(f"Pronađeno {len(pdfs)} PDF fajlova.\n")

    ukupno_vektora = 0

    for pdf_path in pdfs:
        ime_fajla = _normalizuj_ime(pdf_path.stem)
        zakon = None
        for kljuc, vrednost in PDF_LAW_MAP.items():
            if kljuc in ime_fajla or ime_fajla in kljuc:
                zakon = vrednost
                break
        if not zakon:
            zakon = ime_fajla.replace("_", " ")
            print(f"  [!] Nije mapiran: {pdf_path.name} → koristim '{zakon}'")

        print(f"Obradujem: {pdf_path.name} → {zakon}")

        try:
            tekst = _izvuci_tekst_pdf(pdf_path)
        except Exception as e:
            print(f"  [GREŠKA] Čitanje PDF-a: {e}")
            continue

        clanovi = _podeli_na_clanove(tekst)
        print(f"  → {len(clanovi)} članova pronađeno")

        # Grupiši u batch-eve
        for i in range(0, len(clanovi), BATCH_SIZE):
            batch = clanovi[i:i + BATCH_SIZE]
            tekstovi = [f"ZAKON: {zakon}\n{c['clan']}\n\n{c['tekst']}" for c in batch]

            try:
                embeddinzi = _embed_batch(tekstovi, client)
            except Exception as e:
                print(f"  [GREŠKA] Embedding batch {i}: {e}")
                time.sleep(5)
                continue

            vektori = []
            for j, (c, emb) in enumerate(zip(batch, embeddinzi)):
                vektori.append({
                    "id":       _vektor_id(zakon, c["clan"]),
                    "values":   emb,
                    "metadata": {
                        "law":     zakon,
                        "article": c["clan"],
                        "text":    c["tekst"],
                    },
                })

            try:
                index.upsert(vectors=vektori)
                ukupno_vektora += len(vektori)
                print(f"  → Upisano {len(vektori)} vektora (batch {i//BATCH_SIZE + 1})")
            except Exception as e:
                print(f"  [GREŠKA] Pinecone upsert: {e}")

            time.sleep(0.5)  # rate limit

        print()

    print(f"=== Završeno! Ukupno upisano: {ukupno_vektora} vektora ===")


if __name__ == "__main__":
    main()
