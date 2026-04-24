# -*- coding: utf-8 -*-
"""
Vindex AI — Pinecone retrieval pipeline
Multi-stage: direktan fetch člana → semantička pretraga → GPT ekspanzija → reranking
"""

import re
import os
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, Future

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI
from pinecone import Pinecone

load_dotenv()

logger = logging.getLogger("vindex.retrieve")

# ─── Konfiguracija ────────────────────────────────────────────────────────────

EMBEDDING_MODEL = "text-embedding-3-large"
PINECONE_INDEX  = "vindex-ai"

# ─── Ključne reči za prepoznavanje zakona ───────────────────────────────────
# Vrednosti moraju tačno odgovarati "law" metapodatku u Pinecone indeksu.

LAW_HINTS = {
    # Zakon o radu
    "prestanak radnog odnosa":    "zakon o radu",
    "otkaz ugovora o radu":       "zakon o radu",
    "ugovor o radu":              "zakon o radu",
    "tehnoloski visak":           "zakon o radu",
    "visak zaposlenih":           "zakon o radu",
    "radni odnos":                "zakon o radu",
    "disciplinska":               "zakon o radu",
    "otkaz":                      "zakon o radu",
    "zarada":                     "zakon o radu",
    "rad":                        "zakon o radu",
    # Porodični zakon
    "staratelj":                  "porodicni zakon",
    "aliment":                    "porodicni zakon",
    "porodic":                    "porodicni zakon",
    "razvod":                     "porodicni zakon",
    "brak":                       "porodicni zakon",
    "dete":                       "porodicni zakon",
    # Krivični zakonik / ZKP
    "krivicni postupak":          "zakonik o krivicnom postupku",
    "krivicni":                   "krivicni zakonik",
    "krivicno":                   "krivicni zakonik",
    "krivic":                     "krivicni zakonik",
    # Zakon o parničnom postupku
    "parnica":                    "zakon o parnicnom postupku",
    "parnic":                     "zakon o parnicnom postupku",
    "tuzba":                      "zakon o parnicnom postupku",
    "presuda":                    "zakon o parnicnom postupku",
    # Zakon o izvršenju i obezbeđenju
    "obezbedjenj":                "zakon o izvrsenju i obezbedjenju",
    "izvrsenje":                  "zakon o izvrsenju i obezbedjenju",
    "izvrs":                      "zakon o izvrsenju i obezbedjenju",
    # Zakon o obligacionim odnosima
    "imovinska steta":            "zakon o obligacionim odnosima",
    "nematerijalna steta":        "zakon o obligacionim odnosima",
    "izgubljena dobit":           "zakon o obligacionim odnosima",
    "izmakla korist":             "zakon o obligacionim odnosima",
    "prekid zastarelosti":        "zakon o obligacionim odnosima",
    "zastarel":                   "zakon o obligacionim odnosima",
    "rok zastarelosti":           "zakon o obligacionim odnosima",
    "kada zastari":               "zakon o obligacionim odnosima",
    "zastarelo potrazivanje":     "zakon o obligacionim odnosima",
    "obligaci":                   "zakon o obligacionim odnosima",
    "naknada":                    "zakon o obligacionim odnosima",
    "ugovor":                     "zakon o obligacionim odnosima",
    "steta":                      "zakon o obligacionim odnosima",
    # Zakon o privrednim društvima
    "privredn":                   "zakon o privrednim drustvima",
    "drustv":                     "zakon o privrednim drustvima",
    # Opšti upravni postupak / Upravni sporovi
    "upravni spor":               "zakon o upravnim sporovima",
    "upravni postupak":           "zakon o opstem upravnom postupku",
    "cutanje administracije":     "zakon o opstem upravnom postupku",
    "cutanje uprave":             "zakon o opstem upravnom postupku",
    "drugostepen":                "zakon o opstem upravnom postupku",
    "drugostepeni organ":         "zakon o opstem upravnom postupku",
    "upravni sud":                "zakon o upravnim sporovima",
    "tuzba upravnom sudu":        "zakon o upravnim sporovima",
    "konacno resenje":            "zakon o upravnim sporovima",
    "rok za tuzbu":               "zakon o upravnim sporovima",
    "diskriminacij":              "zakon o radu",
    "teret dokazivanja":          "zakon o radu",
    "nejednako postupanje":       "zakon o radu",
    "ozakonjenje":                "zakon o opstem upravnom postupku",
    "upis u katastar":            "zakon o opstem upravnom postupku",
    "zabrana otudjenj":           "zakon o izvrsenju i obezbedjenju",
    # Ostalo
    "vanparnic":                  "zakon o vanparnicnom postupku",
    "nasledj":                    "zakon o nasledjivanju",
    "ostavina":                   "zakon o nasledjivanju",
    "ustav":                      "ustav republike srbije",
    "potrosac":                   "zakon o zastiti potrosaca",
    # Zakon o sprečavanju pranja novca i finansiranja terorizma (ZSPNFT)
    "pranje novca":               "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "pranja novca":               "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "finansiranje terorizma":     "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "aml":                        "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "kyc":                        "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "dubinska analiza":           "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "zspnft":                     "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "uprava za sprecavanje":      "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "obveznik aml":               "zakon o sprecavanju pranja novca i finansiranja terorizma",
    # Zakon o digitalnoj imovini (ZDI)
    "digitalna imovina":          "zakon o digitalnoj imovini",
    "digitalna aktiva":           "zakon o digitalnoj imovini",
    "kriptovaluta":               "zakon o digitalnoj imovini",
    "kripto":                     "zakon o digitalnoj imovini",
    "virtuelna valuta":           "zakon o digitalnoj imovini",
    "usdt":                       "zakon o digitalnoj imovini",
    "bitcoin":                    "zakon o digitalnoj imovini",
    "ethereum":                   "zakon o digitalnoj imovini",
    "zdi":                        "zakon o digitalnoj imovini",
    "digitalni token":            "zakon o digitalnoj imovini",
    "blockchain":                 "zakon o digitalnoj imovini",
    # Pametni ugovor / Smart contract → ZDI (algoritam, IKT sistem)
    "pametni ugovor":             "zakon o digitalnoj imovini",
    "smart contract":             "zakon o digitalnoj imovini",
    "smart kontrakt":             "zakon o digitalnoj imovini",
    "greska u kodu":              "zakon o digitalnoj imovini",
    "greska koda":                "zakon o digitalnoj imovini",
    "algoritam":                  "zakon o digitalnoj imovini",
    "ikt sistem":                 "zakon o digitalnoj imovini",
    "softverska greska":          "zakon o obligacionim odnosima",
    "nft":                        "zakon o digitalnoj imovini",
    "nft nije isporucen":         "zakon o obligacionim odnosima",
    # Web3 krivični scenariji → Krivični zakonik
    "kripto ukraden":             "krivicni zakonik",
    "novcanik hakovan":           "krivicni zakonik",
    "hakovan":                    "krivicni zakonik",
    "neovlascen pristup":         "krivicni zakonik",
    "racunarski kriminal":        "krivicni zakonik",
    "kradja kriptovalute":        "krivicni zakonik",
    "kradja kripto":              "krivicni zakonik",
    # Zarada od kripto → ZPDG
    "zarada od kripto":           "zakon o porezu na dohodak gradjana",
    "prihod od kripto":           "zakon o porezu na dohodak gradjana",
    "kapitalni dobitak":          "zakon o porezu na dohodak gradjana",
    "kapitaln":                   "zakon o porezu na dohodak gradjana",
    "porez na kripto":            "zakon o porezu na dohodak gradjana",
}

# Stop-reči za token matching (bez dijakritika — koriste se u normalizovanom tekstu)
STOPWORDS = {
    "koji", "koja", "koje", "kako", "kada", "zasto", "sta", "gde",
    "da", "li", "se", "su", "je", "u", "na", "po", "za", "od", "do",
    "i", "ili", "a", "ali", "te", "uz", "kod", "sa", "bez", "prema",
    "ovo", "onaj", "ovaj", "taj", "njih", "njegov", "njen", "moze",
    "mogu", "ima", "imaju", "biti", "bio", "bila", "bilo", "nisu",
    "jeste", "nije", "clan", "zakon", "stav", "tacka",
}

# ─── Singleton klijenti (inicijalizacija na prvo korišćenje) ─────────────────

_PINECONE_INDEX = None
_EMBEDDINGS     = None
_CLIENT         = None


def _get_index():
    global _PINECONE_INDEX
    if _PINECONE_INDEX is None:
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY nije postavljen u .env fajlu.")
        pc = Pinecone(api_key=api_key)
        _PINECONE_INDEX = pc.Index(PINECONE_INDEX)
        logger.info("Pinecone index '%s' povezan.", PINECONE_INDEX)
    return _PINECONE_INDEX


def _get_embeddings():
    global _EMBEDDINGS
    if _EMBEDDINGS is None:
        _EMBEDDINGS = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return _EMBEDDINGS


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _CLIENT


# ─── Pomoćne funkcije ─────────────────────────────────────────────────────────

def _normalizuj(tekst: str) -> str:
    """Uklanja dijakritike i pretvara u mala slova — za poređenje."""
    tekst = (tekst or "").lower()
    for src, dst in {"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z"}.items():
        tekst = tekst.replace(src, dst)
    return tekst


def _tokenizuj(query: str) -> list[str]:
    q = _normalizuj(query)
    tokeni = re.findall(r"[a-z0-9]+", q)
    return [t for t in tokeni if len(t) >= 3 and t not in STOPWORDS]


def _prepoznaj_zakon(query: str) -> Optional[str]:
    """Vraća naziv zakona prepoznat iz pitanja, ili None."""
    q = _normalizuj(query)
    # Sortiramo po dužini ključa (duže ključne fraze imaju prednost)
    sortirani = sorted(LAW_HINTS.items(), key=lambda x: len(x[0]), reverse=True)
    for kljuc, zakon in sortirani:
        if _normalizuj(kljuc) in q:
            return zakon
    return None


def _izvuci_broj_clana(query: str) -> Optional[str]:
    """Izvlači broj člana iz pitanja ako je eksplicitno naveden."""
    q = query.lower()
    obrasci = [
        r"(?:član|čl\.|cl\.)\s*(\d+[a-zA-Z]?)",
        r"(?:чл\.?)\s*(\d+[a-zA-Z]?)",
    ]
    for obrazac in obrasci:
        m = re.search(obrazac, q)
        if m:
            return m.group(1)
    return None


def _ugradi_query(query: str) -> list[float]:
    """Konvertuje tekst u embedding vektor."""
    return _get_embeddings().embed_query(query)


# ─── Pinecone operacije ───────────────────────────────────────────────────────

def _semanticka_pretraga(query: str, k: int = 10, filter_zakon: Optional[str] = None) -> list:
    """Semantička pretraga u Pinecone indeksu."""
    index = _get_index()
    vektor = _ugradi_query(query)
    filter_dict = {"law": {"$eq": filter_zakon}} if filter_zakon else None
    try:
        rezultati = index.query(
            vector=vektor,
            top_k=k,
            include_metadata=True,
            filter=filter_dict,
        )
        return rezultati.matches
    except Exception:
        logger.exception("Greška u semantičkoj pretrazi Pinecone")
        return []


def _pretraga_vec(vektor: list[float], k: int, filter_zakon: Optional[str] = None) -> list:
    """Semantička pretraga sa pre-computed vektorom — nema ponovnog embedovanja."""
    index = _get_index()
    filter_dict = {"law": {"$eq": filter_zakon}} if filter_zakon else None
    try:
        rezultati = index.query(
            vector=vektor,
            top_k=k,
            include_metadata=True,
            filter=filter_dict,
        )
        return rezultati.matches
    except Exception:
        logger.exception("Greška u pretraga_vec")
        return []


def _direktan_fetch_clana(label_clana: str, zakon: Optional[str] = None) -> list:
    """Direktan fetch člana po metapodatku 'article'."""
    index = _get_index()
    filter_dict = {"article": {"$eq": label_clana}}
    if zakon:
        filter_dict = {"$and": [
            {"article": {"$eq": label_clana}},
            {"law":     {"$eq": zakon}},
        ]}
    try:
        # Dummy vektor za metadata-only search (dimenzija mora da odgovara indeksu)
        dummy = [0.0] * 3072
        rezultati = index.query(
            vector=dummy,
            top_k=5,
            include_metadata=True,
            filter=filter_dict,
        )
        return rezultati.matches
    except Exception:
        logger.exception("Greška u direktnom fetchu člana %s", label_clana)
        return []


def _prosiri_query_gpt(query: str) -> list[str]:
    """
    GPT-4o-mini generisanje 4 alternativna search query-ja
    za bolji semantički zahvat.
    """
    try:
        client = _get_client()
        odgovor = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=200,
            timeout=20.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ti si ekspert za srpsko pravo. "
                        "Za dato pravno pitanje generiši tačno 4 kratka search query-ja (3-7 reči svaki) "
                        "koji će pronaći relevantne odredbe zakona u vektorskoj bazi. "
                        "Koristi pravne termine iz srpskih zakona. "
                        "SEMANTIČKO MAPIRANJE — obavezno primeni:\n"
                        "• 'pametni ugovor', 'smart contract', 'smart kontrakt', 'greška u kodu' → "
                        "koristi 'algoritam', 'IKT sistem', 'digitalna imovina ZDI', "
                        "'odgovornost za štetu ZOO čl. 154'\n"
                        "• 'NFT nije isporučen', 'NFT', 'digitalni kolekcionarski predmet' → "
                        "koristi 'naknada štete', 'ispunjenje obaveze', 'odgovornost prodavca ZOO'\n"
                        "• 'kripto ukraden', 'novčanik hakovan', 'neovlašćen pristup' → "
                        "koristi 'neovlašćen pristup računarskom sistemu', 'imovinska šteta', "
                        "'krivična prijava Krivični zakonik čl. 302 303 304'\n"
                        "• 'zarada od kripto', 'prihod od kriptovaluta', 'profit od digitalne imovine' → "
                        "koristi 'kapitalni dobitak', 'porez na dohodak ZPDG čl. 72b', 'prijava prihoda'\n"
                        "• 'novčanik hakovan', 'hack wallet' → "
                        "koristi 'krivična prijava', 'imovinska šteta ZOO', 'neovlašćen pristup KZ čl. 303'\n"
                        "• Za pitanja o kriptovalutama, digitalnoj imovini ili USDT: uključi "
                        "'digitalna imovina', 'kriptovaluta', 'virtuelna valuta', 'ZDI'\n"
                        "• Ako specifičan zakon nije jasan: uvek dodaj query sa "
                        "'odgovornost za štetu ZOO član 154 155' kao poslednji\n"
                        "Vrati SAMO query-je, jedan po liniji, bez numeracije i bez dodatnog teksta."
                    ),
                },
                {"role": "user", "content": f"Pitanje: {query}"},
            ],
        )
        tekst = odgovor.choices[0].message.content.strip()
        prošireni = [q.strip() for q in tekst.split("\n") if q.strip()]
        logger.debug("[GPT_EXPANSION] %s", prošireni)
        return prošireni[:4]
    except Exception:
        logger.warning("GPT query ekspanzija nije uspela, nastavljam bez nje.")
        return []


# ─── Scoring / reranking ──────────────────────────────────────────────────────

def _izracunaj_skor(match, query: str, zakon: Optional[str], label_clana: Optional[str]) -> float:
    """Reranking skor: Pinecone cosine skor + bonus za zakon/član/token hitove."""
    skor = match.score * 100
    meta = match.metadata or {}
    zakon_doc    = _normalizuj(meta.get("law", ""))
    clan_doc     = _normalizuj(meta.get("article", ""))
    tekst_doc    = _normalizuj(meta.get("text", ""))
    query_norm   = _normalizuj(query)

    # Bonus za tačan zakon
    if zakon:
        z = _normalizuj(zakon)
        if z == zakon_doc:
            skor += 30
        elif z in zakon_doc:
            skor += 15

    # Bonus za tačan član
    if label_clana:
        c = _normalizuj(label_clana)
        if c == clan_doc:
            skor += 50
        elif c in clan_doc:
            skor += 25

    # Token hits
    tokeni = _tokenizuj(query)
    pogodci = sum(1 for t in tokeni if t in tekst_doc)
    skor += min(pogodci * 3, 20)

    # Specijalni boost za nematerijalnu štetu (ZOO član 200)
    if "nematerijal" in query_norm and "stet" in query_norm:
        if "nematerijalna steta" in tekst_doc:
            skor += 50
        if "obligacion" in zakon_doc:
            skor += 20
        if "200" in clan_doc and "obligacion" in zakon_doc:
            skor += 80

    # Boost za zastarelost (ZOO čl. 360–395)
    if "zastarel" in query_norm:
        if any(x in tekst_doc for x in ["zastareva", "zastari", "zastarelost", "zastarelih", "zastarelo"]):
            skor += 45
        if "obligacion" in zakon_doc:
            try:
                m = re.search(r"\d+", clan_doc or "")
                if m and 360 <= int(m.group()) <= 395:
                    skor += 70
            except Exception:
                pass

    # Boost za periodična potraživanja (struja, komunalne)
    if any(x in query_norm for x in ["struj", "komunal", "vod", "gas", "telefon", "kirij", "najam"]):
        if any(x in tekst_doc for x in ["povremenih", "periodicn", "godisnje", "kracim razmacima"]):
            skor += 60

    # Boost za ZDI pitanja (Zakon o digitalnoj imovini)
    if any(x in query_norm for x in ["digital", "kripto", "bitcoin", "usdt", "ethereum", "token", "virtuelna", "zdi", "blockchain"]):
        if "digitalna imovina" in zakon_doc or "digitaln" in zakon_doc:
            skor += 40

    # Boost za pametne ugovore / smart contract → ZDI + ZOO odgovornost
    _sc_trigeri = ["pametni ugovor", "smart contract", "greska u kodu", "greska koda", "algoritam", "ikt sistem", "softverska greska"]
    if any(x in query_norm for x in _sc_trigeri):
        if "digitaln" in zakon_doc:
            skor += 35
        # ZOO čl. 154/155/200 — osnov odgovornosti za greške algoritma
        if "obligacion" in zakon_doc:
            skor += 25
            try:
                m_clan = re.search(r"\d+", clan_doc or "")
                if m_clan and int(m_clan.group()) in (154, 155, 200, 189):
                    skor += 45
            except Exception:
                pass

    return skor


# ─── Format izlaza ───────────────────────────────────────────────────────────

def _formatiraj_match(match) -> str:
    meta    = match.metadata or {}
    zakon   = meta.get("law", "Nepoznat zakon")
    clan    = meta.get("article", "Nepoznat član")
    tekst   = meta.get("text", "").strip()
    return f"ZAKON: {zakon}\nČLAN: {clan}\n\n{tekst}\n"


# ─── Konstante za ekspanziju ─────────────────────────────────────────────────

_ZDI_TRIGERI = frozenset([
    "digital", "kripto", "bitcoin", "usdt", "ethereum", "token", "nft",
    "virtuelna", "zdi", "blockchain",
])
_ZDI_TERMINI = [
    "digitalna imovina zakon",
    "kriptovaluta pravni status srbija",
    "ZDI digitalni token NFT",
]

_KZ_TRIGERI = frozenset([
    "hakovan", "ukraden", "kradja", "neovlascen", "racunarski kriminal",
    "krivicna prijava", "krivicno delo",
])
_KZ_TERMINI = [
    "neovlašćen pristup računarskom sistemu Krivični zakonik",
    "imovinska šteta krivično delo KZ čl. 302",
]

_ZPDG_TRIGERI = frozenset([
    "zarada od kripto", "prihod od kripto", "kapitalni dobitak",
    "porez na kripto", "kapitaln dobitak",
])
_ZPDG_TERMINI = [
    "kapitalni dobitak digitalna imovina ZPDG član 72",
    "porez na dohodak kriptovaluta prijava",
]
_SC_TRIGERI = frozenset([
    "pametni ugovor", "smart contract", "greska u kodu", "greska koda",
    "algoritam", "ikt sistem", "softverska greska",
])
_SC_TERMINI_ZDI = [
    "algoritam IKT sistem digitalna imovina",
    "pametni ugovor digitalni token ZDI",
]
_SC_TERMINI_ZOO = [
    "odgovornost za štetu ZOO član 154",
]
_ZOO_FALLBACK_CLANOVI = ["Član 154", "Član 155", "Član 200", "Član 189"]

# ─── Glavna javna funkcija ────────────────────────────────────────────────────

def retrieve_documents(query: str, k: int = 6) -> list[str]:
    """
    Retrieval pipeline v2 — PARALELNI.

    Sve Pinecone pretrage teku paralelno (ThreadPoolExecutor).
    Embedding se računa jedanput i deli između svih poziva.
    GPT ekspanzija teče u pozadini paralelno sa inicijalnim pretragama;
    čeka se maksimalno 3 sekunde — ako kasni, preskočena.
    """
    import time
    t0 = time.perf_counter()

    zakon       = _prepoznaj_zakon(query)
    broj_clana  = _izvuci_broj_clana(query)
    label_clana = f"Član {broj_clana}" if broj_clana else None
    q_norm      = _normalizuj(query)

    # ── Faza 0: embed query jedanput ─────────────────────────────────────────
    vektor = _ugradi_query(query)

    # ── Faza 1: sve inicijalne pretrage + GPT ekspanzija — u PARALELI ────────
    executor = ThreadPoolExecutor(max_workers=10)
    fjobs: list[Future] = []

    # a) Direktan fetch člana (ako je naveden)
    if label_clana:
        fjobs.append(executor.submit(_direktan_fetch_clana, label_clana, zakon))

    # b) Semantička sa filterom (k=8)
    fjobs.append(executor.submit(_pretraga_vec, vektor, 8, zakon))

    # c) Semantička bez filtera (k=6)
    fjobs.append(executor.submit(_pretraga_vec, vektor, 6, None))

    # d) ZDI specifična ekspanzija
    if any(x in q_norm for x in _ZDI_TRIGERI):
        for term in _ZDI_TERMINI:
            fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "zakon o digitalnoj imovini"))

    # e) Smart contract ekspanzija
    if any(x in q_norm for x in _SC_TRIGERI):
        for term in _SC_TERMINI_ZDI:
            fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "zakon o digitalnoj imovini"))
        for term in _SC_TERMINI_ZOO:
            fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "zakon o obligacionim odnosima"))

    # f) KZ ekspanzija — kripto krivična dela
    if any(x in q_norm for x in _KZ_TRIGERI):
        for term in _KZ_TERMINI:
            fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "krivicni zakonik"))

    # g) ZPDG ekspanzija — zarada od kripto
    if any(x in q_norm for x in _ZPDG_TRIGERI):
        for term in _ZPDG_TERMINI:
            fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "zakon o porezu na dohodak gradjana"))

    # i) GPT ekspanzija — paralelno, max 3s timeout
    gpt_future: Future = executor.submit(_prosiri_query_gpt, query)

    # Čekaj inicijalne pretrage
    svi_matchevi: list = []
    for f in as_completed(fjobs):
        try:
            svi_matchevi.extend(f.result())
        except Exception:
            pass

    # ── Faza 2: proširene pretrage iz GPT ekspanzije (ako je stigla) ──────────
    try:
        prosireni = gpt_future.result(timeout=3.0)
        exp_futs = [executor.submit(_semanticka_pretraga, eq, 3) for eq in prosireni[:3]]
        for f in as_completed(exp_futs, timeout=2.0):
            try:
                svi_matchevi.extend(f.result())
            except Exception:
                pass
        logger.debug("[GPT_EXP] Prosirene pretrage gotove")
    except Exception:
        logger.info("[GPT_EXP] Preskočena (timeout ili greška)")

    executor.shutdown(wait=False)

    # ── Faza 3: dedup + reranking ─────────────────────────────────────────────
    vidjeni: set[str] = set()
    jedinstveni = []
    for m in svi_matchevi:
        if m.id not in vidjeni:
            vidjeni.add(m.id)
            jedinstveni.append(m)

    skorovani = sorted(
        [(_izracunaj_skor(m, query, zakon, label_clana), m) for m in jedinstveni],
        key=lambda x: x[0], reverse=True,
    )

    # ── Faza 4: ZOO Legal Fallback (paralelno, samo ako treba) ───────────────
    top_skor = skorovani[0][0] if skorovani else 0
    if len(skorovani) < 3 or top_skor < 50:
        fb_futures = [
            executor  # executor je shut down — koristimo novi kratki
        ]
        with ThreadPoolExecutor(max_workers=4) as fb_exec:
            fb_futs = [
                fb_exec.submit(_direktan_fetch_clana, clan, "zakon o obligacionim odnosima")
                for clan in _ZOO_FALLBACK_CLANOVI
            ]
            for f in as_completed(fb_futs):
                try:
                    for m in f.result():
                        if m.id not in vidjeni:
                            vidjeni.add(m.id)
                            skor_fb = _izracunaj_skor(m, query, zakon, label_clana)
                            skorovani.append((skor_fb, m))
                except Exception:
                    pass
        skorovani.sort(key=lambda x: x[0], reverse=True)
        logger.info("[ZOO_FALLBACK] top_skor=%.1f — dodati ZOO čl. 154/155/200/189", top_skor)

    elapsed = time.perf_counter() - t0
    logger.info(
        "[RETRIEVE] %.2fs | unique=%d | top=%d | zakon=%s | član=%s",
        elapsed, len(jedinstveni), k, zakon or "—", label_clana or "—",
    )

    return [_formatiraj_match(m) for _, m in skorovani[:k]]


# ─── Dijagnostička funkcija: provera ZDI indeksiranosti ──────────────────────

def proveri_zdi_indeksiranost() -> dict:
    """
    Proverava da li su ključni članovi ZDI (2, 74, 75, 78) indeksirani u Pinecone.
    Vraća dict sa statusom svakog člana.
    Returns: {"Član 2": True/False, "Član 74": True/False, ...}
    """
    ciljni_clanovi = ["Član 2", "Član 74", "Član 75", "Član 78"]
    rezultat: dict[str, bool] = {}
    for clan in ciljni_clanovi:
        matchevi = _direktan_fetch_clana(clan, "zakon o digitalnoj imovini")
        pronadjen = any(
            _normalizuj(m.metadata.get("law", "")) == "zakon o digitalnoj imovini"
            and _normalizuj(m.metadata.get("article", "")) == _normalizuj(clan)
            for m in matchevi
        )
        rezultat[clan] = pronadjen
        logger.info("[ZDI_CHECK] %s: %s", clan, "✓ pronađen" if pronadjen else "✗ NIJE indeksiran")
    return rezultat
