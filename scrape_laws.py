"""
Skripta za skidanje važećih zakona sa paragraf.rs i ubacivanje u ChromaDB.
Koristi HTML verziju zakona koja sadrži samo važeće odredbe.
"""

import os
import re
import time
import shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import requests
from bs4 import BeautifulSoup
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

BASE_DIR = Path(__file__).resolve().parent
VECTOR_STORE_DIR = BASE_DIR / "vector_store"

# ── Lista zakona koje skidamo ──

ZAKONI = [
    # ── OSNOVNO GRAĐANSKO PRAVO ──
    {"naziv": "zakon o radu", "url": "https://www.paragraf.rs/propisi/zakon_o_radu.html"},
    {"naziv": "porodicni zakon", "url": "https://www.paragraf.rs/propisi/porodicni_zakon.html"},
    {"naziv": "zakon o obligacionim odnosima", "url": "https://www.paragraf.rs/propisi/zakon_o_obligacionim_odnosima.html"},
    {"naziv": "zakon o nasledjivanju", "url": "https://www.paragraf.rs/propisi/zakon_o_nasledjivanju.html"},
    {"naziv": "zakon o svojini i drugim stvarnim pravima", "url": "https://www.paragraf.rs/propisi/zakon_o_osnovama_svojinskopravnih_odnosa.html"},
    {"naziv": "zakon o hipoteci", "url": "https://www.paragraf.rs/propisi/zakon_o_hipoteci.html"},
    {"naziv": "zakon o zakupu stanova", "url": "https://www.paragraf.rs/propisi/zakon_o_stanovanju_i_odrzavanju_zgrada.html"},

    # ── POSTUPCI ──
    {"naziv": "zakon o parnicnom postupku", "url": "https://www.paragraf.rs/propisi/zakon_o_parnicnom_postupku.html"},
    {"naziv": "zakon o izvrsenju i obezbedjenju", "url": "https://www.paragraf.rs/propisi/zakon_o_izvrsenju_i_obezbedjenju.html"},
    {"naziv": "zakon o vanparnicnom postupku", "url": "https://www.paragraf.rs/propisi/zakon_o_vanparnicnom_postupku.html"},
    {"naziv": "zakon o opstem upravnom postupku", "url": "https://www.paragraf.rs/propisi/zakon_o_opstem_upravnom_postupku.html"},
    {"naziv": "zakon o upravnim sporovima", "url": "https://www.paragraf.rs/propisi/zakon_o_upravnim_sporovima.html"},
    {"naziv": "zakon o medijaciji", "url": "https://www.paragraf.rs/propisi/zakon_o_posredovanju_u_resavanju_sporova.html"},

    # ── KRIVIČNO PRAVO ──
    {"naziv": "krivicni zakonik", "url": "https://www.paragraf.rs/propisi/krivicni_zakonik.html"},
    {"naziv": "zakonik o krivicnom postupku", "url": "https://www.paragraf.rs/propisi/zakonik_o_krivicnom_postupku.html"},
    {"naziv": "zakon o maloletnim uciniocima krivicnih dela", "url": "https://www.paragraf.rs/propisi/zakon_o_maloletnim_uciniocima_krivicnih_dela_i_krivicnopravnoj_zastiti_maloletnih_lica.html"},

    # ── PRIVREDNO PRAVO ──
    {"naziv": "zakon o privrednim drustvima", "url": "https://www.paragraf.rs/propisi/zakon_o_privrednim_drustvima.html"},
    {"naziv": "zakon o stecaju", "url": "https://www.paragraf.rs/propisi/zakon_o_stecaju.html"},
    {"naziv": "zakon o trzistu kapitala", "url": "https://www.paragraf.rs/propisi/zakon_o_trzistu_kapitala.html"},
    {"naziv": "zakon o bankama", "url": "https://www.paragraf.rs/propisi/zakon_o_bankama.html"},
    {"naziv": "zakon o osiguranju", "url": "https://www.paragraf.rs/propisi/zakon_o_osiguranju.html"},
    {"naziv": "zakon o zastiti potrosaca", "url": "https://www.paragraf.rs/propisi/zakon_o_zastiti_potrosaca.html"},
    {"naziv": "zakon o elektronskoj trgovini", "url": "https://www.paragraf.rs/propisi/zakon_o_elektronskoj_trgovini.html"},

    # ── RADNO I SOCIJALNO ──
    {"naziv": "zakon o penzijskom i invalidskom osiguranju", "url": "https://www.paragraf.rs/propisi/zakon_o_penzijskom_i_invalidskom_osiguranju.html"},
    {"naziv": "zakon o zdravstvenom osiguranju", "url": "https://www.paragraf.rs/propisi/zakon_o_zdravstvenom_osiguranju.html"},
    {"naziv": "zakon o zdravstvenoj zastiti", "url": "https://www.paragraf.rs/propisi/zakon_o_zdravstvenoj_zastiti.html"},
    {"naziv": "zakon o zaposljavanju i osiguranju za slucaj nezaposlenosti", "url": "https://www.paragraf.rs/propisi/zakon_o_zaposljavanju_i_osiguranju_za_slucaj_nezaposlenosti.html"},
    {"naziv": "zakon o bezbednosti i zdravlju na radu", "url": "https://www.paragraf.rs/propisi/zakon_o_bezbednosti_i_zdravlju_na_radu.html"},

    # ── UPRAVNO I USTAVNO ──
    {"naziv": "ustav republike srbije", "url": "https://www.paragraf.rs/propisi/ustav_republike_srbije.html"},
    {"naziv": "zakon o drzavnim sluzbenicima", "url": "https://www.paragraf.rs/propisi/zakon_o_drzavnim_sluzbenicima.html"},
    {"naziv": "zakon o lokalnoj samoupravi", "url": "https://www.paragraf.rs/propisi/zakon_o_lokalnoj_samoupravi.html"},
    {"naziv": "zakon o slobodnom pristupu informacijama od javnog znacaja", "url": "https://www.paragraf.rs/propisi/zakon_o_slobodnom_pristupu_informacijama_od_javnog_znacaja.html"},
    {"naziv": "zakon o zastiti podataka o licnosti", "url": "https://www.paragraf.rs/propisi/zakon_o_zastiti_podataka_o_licnosti.html"},

    # ── NEPOKRETNOSTI ──
    {"naziv": "zakon o planiranju i izgradnji", "url": "https://www.paragraf.rs/propisi/zakon_o_planiranju_i_izgradnji.html"},
    {"naziv": "zakon o prometu nepokretnosti", "url": "https://www.paragraf.rs/propisi/zakon_o_prometu_nepokretnosti.html"},
    {"naziv": "zakon o katastru nepokretnosti", "url": "https://www.paragraf.rs/propisi/zakon_o_drzavnom_premeru_i_katastru.html"},

    # ── POREZI ──
    {"naziv": "zakon o porezu na dohodak gradjana", "url": "https://www.paragraf.rs/propisi/zakon_o_porezu_na_dohodak_gradjana.html"},
    {"naziv": "zakon o porezu na dobit pravnih lica", "url": "https://www.paragraf.rs/propisi/zakon_o_porezu_na_dobit_pravnih_lica.html"},
    {"naziv": "zakon o porezu na dodatu vrednost", "url": "https://www.paragraf.rs/propisi/zakon_o_porezu_na_dodatu_vrednost.html"},
    {"naziv": "zakon o porezima na imovinu", "url": "https://www.paragraf.rs/propisi/zakon_o_porezima_na_imovinu.html"},
    {"naziv": "zakon o poreskom postupku i poreskoj administraciji", "url": "https://www.paragraf.rs/propisi/zakon_o_poreskom_postupku_i_poreskoj_administraciji.html"},
    {"naziv": "zakon o doprinosima za obavezno socijalno osiguranje", "url": "https://www.paragraf.rs/propisi/zakon_o_doprinosima_za_obavezno_socijalno_osiguranje.html"},

    # ── PRAVOSUĐE I PROFESIJE ──
    {"naziv": "zakon o advokaturi", "url": "https://www.paragraf.rs/propisi/zakon_o_advokaturi.html"},
    {"naziv": "zakon o javnom beleznistvu", "url": "https://www.paragraf.rs/propisi/zakon_o_javnom_beleznistvu.html"},
    {"naziv": "zakon o uredjenju sudova", "url": "https://www.paragraf.rs/propisi/zakon_o_uredjenju_sudova.html"},
    {"naziv": "zakon o arbitrazi", "url": "https://www.paragraf.rs/propisi/zakon_o_arbitrazi.html"},
    {"naziv": "zakon o izvrsenju krivicnih sankcija", "url": "https://www.paragraf.rs/propisi/zakon_o_izvrsenju_krivicnih_sankcija.html"},
    {"naziv": "zakon o odgovornosti pravnih lica za krivicna dela", "url": "https://www.paragraf.rs/propisi/zakon_o_odgovornosti_pravnih_lica_za_krivicna_dela.html"},
    {"naziv": "zakon o maloletnim uciniocima krivicnih dela", "url": "https://www.paragraf.rs/propisi/zakon_o_maloletnim_uciniocima_krivicnih_dela_i_krivicnopravnoj_zastiti_maloletnih_lica.html"},

    # ── PRIVREDNO DOPUNJENO ──
    {"naziv": "zakon o finansijskom lizingu", "url": "https://www.paragraf.rs/propisi/zakon_o_finansijskom_lizingu.html"},
    {"naziv": "zakon o javnim nabavkama", "url": "https://www.paragraf.rs/propisi/zakon_o_javnim_nabavkama.html"},
    {"naziv": "zakon o racunovodstvu", "url": "https://www.paragraf.rs/propisi/zakon-o-racunovodstvu-2020.html"},
    {"naziv": "zakon o reviziji", "url": "https://www.paragraf.rs/propisi/zakon_o_reviziji.html"},
    {"naziv": "zakon o javno privatnom partnerstvu", "url": "https://www.paragraf.rs/propisi/zakon_o_javno-privatnom_partnerstvu_i_koncesijama.html"},

    # ── RADNO DOPUNJENO ──
    {"naziv": "zakon o socijalnoj zastiti", "url": "https://www.paragraf.rs/propisi/zakon_o_socijalnoj_zastiti.html"},
    {"naziv": "zakon o finansijskoj podrsci porodici sa decom", "url": "https://www.paragraf.rs/propisi/zakon_o_finansijskoj_podrsci_porodici_sa_decom.html"},
    {"naziv": "zakon o strancima", "url": "https://www.paragraf.rs/propisi/zakon_o_strancima.html"},

    # ── UPRAVNO DOPUNJENO ──
    {"naziv": "zakon o drzavljanstvu republike srbije", "url": "https://www.paragraf.rs/propisi/zakon_o_drzavljanstvu_republike_srbije.html"},
    {"naziv": "zakon o prekrsajima", "url": "https://www.paragraf.rs/propisi/zakon_o_prekrsajima.html"},
    {"naziv": "zakon o javnom redu i miru", "url": "https://www.paragraf.rs/propisi/zakon_o_javnom_redu_i_miru.html"},
    {"naziv": "zakon o zabrani diskriminacije", "url": "https://www.paragraf.rs/propisi/zakon_o_zabrani_diskriminacije.html"},

    # ── NEPOKRETNOSTI DOPUNJENO ──
    {"naziv": "zakon o eksproprijaciji", "url": "https://www.paragraf.rs/propisi/zakon_o_eksproprijaciji.html"},
    {"naziv": "zakon o drzavnom premeru i katastru", "url": "https://www.paragraf.rs/propisi/zakon_o_drzavnom_premeru_i_katastru.html"},

    # ── OSTALO ──
    {"naziv": "zakon o bezbednosti saobracaja na putevima", "url": "https://www.paragraf.rs/propisi/zakon_o_bezbednosti_saobracaja_na_putevima.html"},
    {"naziv": "zakon o zastiti zivotne sredine", "url": "https://www.paragraf.rs/propisi/zakon_o_zastiti_zivotne_sredine.html"},
    {"naziv": "zakon o autorskom i srodnim pravima", "url": "https://www.paragraf.rs/propisi/zakon_o_autorskom_i_srodnim_pravima.html"},
    {"naziv": "zakon o patentima", "url": "https://www.paragraf.rs/propisi/zakon_o_patentima.html"},
    {"naziv": "zakon o zigovima", "url": "https://www.paragraf.rs/propisi/zakon_o_zigovima.html"},
    {"naziv": "zakon o elektronskom dokumentu", "url": "https://www.paragraf.rs/propisi/zakon_o_elektronskom_dokumentu_elektronskoj_identifikaciji_i_uslugama_od_poverenja_u_elektronskom_poslovanju.html"},
    {"naziv": "zakon o zastiti podataka o licnosti", "url": "https://www.paragraf.rs/propisi/zakon_o_zastiti_podataka_o_licnosti.html"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def skini_zakon(naziv: str, url: str) -> list[Document]:
    """Skida jedan zakon sa paragraf.rs i vraća listu Document objekata."""
    print(f"\n📥 Skidam: {naziv}")
    print(f"   URL: {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.encoding = "utf-8"

        if response.status_code != 200:
            print(f"   ❌ Greška: status {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "lxml")

        # Ukloni nepotrebne elemente
        for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # Pronađi glavni sadržaj
        sadrzaj = (
            soup.find("div", class_="content")
            or soup.find("div", id="content")
            or soup.find("article")
            or soup.find("main")
            or soup.find("body")
        )

        if not sadrzaj:
            print(f"   ❌ Nije pronađen sadržaj")
            return []

        tekst = sadrzaj.get_text(separator="\n", strip=True)

        # Podeli po članovima
        dokumenti = podeli_na_clanove(tekst, naziv)
        print(f"   ✅ Pronađeno {len(dokumenti)} članova")
        return dokumenti

    except Exception as e:
        print(f"   ❌ Greška: {e}")
        return []


def podeli_na_clanove(tekst: str, naziv_zakona: str) -> list[Document]:
    """Deli tekst zakona na pojedinačne članove."""
    dokumenti = []

    # Pattern za prepoznavanje članova
    clan_pattern = re.compile(
        r'(?:^|\n)\s*(Član\s+\d+[a-zA-Z]?\.?\s*(?:[a-zA-ZšđčćžŠĐČĆŽ\s]*)?)\s*\n',
        re.MULTILINE | re.IGNORECASE
    )

    delovi = clan_pattern.split(tekst)

    if len(delovi) <= 1:
        # Ako nema jasnih članova, podeli po paragrafima
        paragrafi = [p.strip() for p in tekst.split("\n\n") if len(p.strip()) > 50]
        for i, paragraf in enumerate(paragrafi):
            doc = Document(
                page_content=paragraf[:2000],
                metadata={
                    "law": naziv_zakona,
                    "article": f"Deo {i+1}",
                    "source": naziv_zakona,
                }
            )
            dokumenti.append(doc)
        return dokumenti

    # Parsiraj član po član
    i = 1
    while i < len(delovi) - 1:
        naziv_clana = delovi[i].strip()
        sadrzaj_clana = delovi[i + 1].strip() if i + 1 < len(delovi) else ""

        # Preskoči brisane članove
        if "(Brisan)" in sadrzaj_clana or "(brisan)" in sadrzaj_clana:
            i += 2
            continue

        # Preskoči ako je prazan
        if not sadrzaj_clana or len(sadrzaj_clana) < 10:
            i += 2
            continue

        # Normalizuj naziv člana
        broj_match = re.search(r'\d+[a-zA-Z]?', naziv_clana)
        if broj_match:
            clan_broj = f"Član {broj_match.group()}"
        else:
            clan_broj = naziv_clana[:30]

        doc = Document(
            page_content=f"{clan_broj}\n\n{sadrzaj_clana[:2000]}",
            metadata={
                "law": naziv_zakona,
                "article": clan_broj,
                "source": naziv_zakona,
            }
        )
        dokumenti.append(doc)
        i += 2

    return dokumenti


def obrisi_staru_bazu():
    """Briše staru ChromaDB bazu."""
    if VECTOR_STORE_DIR.exists():
        print(f"\n🗑️  Brišem staru bazu: {VECTOR_STORE_DIR}")
        shutil.rmtree(VECTOR_STORE_DIR)
        print("   ✅ Stara baza obrisana")


def sacuvaj_u_bazu(dokumenti: list[Document]):
    """Čuva dokumente u ChromaDB."""
    if not dokumenti:
        print("   ⚠️  Nema dokumenata za čuvanje")
        return

    print(f"\n💾 Čuvam {len(dokumenti)} dokumenata u bazu...")

    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    # Dodaj u batch-evima
    batch_size = 50
    for i in range(0, len(dokumenti), batch_size):
        batch = dokumenti[i:i + batch_size]
        Chroma.from_documents(
            documents=batch,
            embedding=embeddings,
            persist_directory=str(VECTOR_STORE_DIR),
        )
        print(f"   Batch {i//batch_size + 1}/{(len(dokumenti)-1)//batch_size + 1} sačuvan")

    print(f"   ✅ Sačuvano!")


def main():
    print("=" * 60)
    print("  VINDEX AI — Scraper zakona sa paragraf.rs")
    print("=" * 60)

    # Obriši staru bazu
    obrisi_staru_bazu()

    svi_dokumenti = []

    for zakon in ZAKONI:
        dokumenti = skini_zakon(zakon["naziv"], zakon["url"])
        svi_dokumenti.extend(dokumenti)
        time.sleep(2)  # Pauza između zahteva

    print(f"\n📊 Ukupno sakupljeno: {len(svi_dokumenti)} članova")

    # Čuvaj u bazu
    sacuvaj_u_bazu(svi_dokumenti)

    print("\n" + "=" * 60)
    print("  ✅ GOTOVO! Baza je ažurirana sa važećim zakonima.")
    print("=" * 60)


if __name__ == "__main__":
    main()