# -*- coding: utf-8 -*-
"""
Vindex AI — Agentic RAG Retrieval Pipeline v3

Tehnike:
  Sprint 1 — Semantic Chunking    (metapodaci iz reindex_agentic.py)
  Sprint 2 — Multi-Query + HyDE   (_dekomponuj_query, _generiši_hyde)
  Sprint 3 — Cohere Re-ranking    (_cohere_rerank, fallback na interni skor)
  Sprint 4 — Parent-Doc Retrieval (_dohvati_parent_text — čita iz metapodataka)
  Sprint 5 — Self-RAG / CRAG      (_oceni_relevantnost + corrective loop)
"""

import re
import os
import json
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, Future

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI
from pinecone import Pinecone

load_dotenv()

try:
    import cohere as _cohere_lib
    _COHERE_AVAILABLE = True
except ImportError:
    _COHERE_AVAILABLE = False

logger = logging.getLogger("vindex.retrieve")

# ─── Konfiguracija ────────────────────────────────────────────────────────────

EMBEDDING_MODEL = "text-embedding-3-large"
PINECONE_INDEX  = "vindex-ai"

# ─── LAW_HINTS ────────────────────────────────────────────────────────────────

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
    "krivicni":                   "KZ",
    "krivicno":                   "KZ",
    "krivic":                     "KZ",
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
    "apr":                        "zakon o privrednim drustvima",
    "registracija":               "zakon o privrednim drustvima",
    "osnivanje":                  "zakon o privrednim drustvima",
    "zastupnik":                  "zakon o privrednim drustvima",
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
    # ZSPNFT
    "pranje novca":               "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "pranja novca":               "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "finansiranje terorizma":     "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "aml":                        "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "kyc":                        "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "dubinska analiza":           "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "zspnft":                     "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "uprava za sprecavanje":      "zakon o sprecavanju pranja novca i finansiranja terorizma",
    "obveznik aml":               "zakon o sprecavanju pranja novca i finansiranja terorizma",
    # ZDI
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
    # Web3 krivični → KZ
    "kripto ukraden":             "KZ",
    "novcanik hakovan":           "KZ",
    "hakovan":                    "KZ",
    "neovlascen pristup":         "KZ",
    "racunarski kriminal":        "KZ",
    "kradja kriptovalute":        "KZ",
    "kradja kripto":              "KZ",
    # ZPDG
    "zarada od kripto":           "ZPDG",
    "prihod od kripto":           "ZPDG",
    "kapitalni dobitak":          "ZPDG",
    "kapitaln":                   "ZPDG",
    "porez na kripto":            "ZPDG",
}

STOPWORDS = {
    "koji", "koja", "koje", "kako", "kada", "zasto", "sta", "gde",
    "da", "li", "se", "su", "je", "u", "na", "po", "za", "od", "do",
    "i", "ili", "a", "ali", "te", "uz", "kod", "sa", "bez", "prema",
    "ovo", "onaj", "ovaj", "taj", "njih", "njegov", "njen", "moze",
    "mogu", "ima", "imaju", "biti", "bio", "bila", "bilo", "nisu",
    "jeste", "nije", "clan", "zakon", "stav", "tacka",
}

# ─── Singleton klijenti ───────────────────────────────────────────────────────

_PINECONE_INDEX = None
_EMBEDDINGS     = None
_CLIENT         = None
_COHERE_CLIENT  = None


def _get_index():
    global _PINECONE_INDEX
    if _PINECONE_INDEX is None:
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY nije postavljen.")
        pc = Pinecone(api_key=api_key)
        _PINECONE_INDEX = pc.Index(PINECONE_INDEX)
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


def _get_cohere():
    global _COHERE_CLIENT
    if not _COHERE_AVAILABLE:
        return None
    if _COHERE_CLIENT is None:
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            return None
        _COHERE_CLIENT = _cohere_lib.Client(api_key)
    return _COHERE_CLIENT


# ─── Pomoćne funkcije ─────────────────────────────────────────────────────────

def _normalizuj(tekst: str) -> str:
    tekst = (tekst or "").lower()
    for src, dst in {"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z"}.items():
        tekst = tekst.replace(src, dst)
    return tekst


def _tokenizuj(query: str) -> list[str]:
    q = _normalizuj(query)
    tokeni = re.findall(r"[a-z0-9]+", q)
    return [t for t in tokeni if len(t) >= 3 and t not in STOPWORDS]


def _prepoznaj_zakon(query: str) -> Optional[str]:
    q = _normalizuj(query)
    sortirani = sorted(LAW_HINTS.items(), key=lambda x: len(x[0]), reverse=True)
    for kljuc, zakon in sortirani:
        if _normalizuj(kljuc) in q:
            return zakon
    return None


def _izvuci_broj_clana(query: str) -> Optional[str]:
    q = query.lower()
    for obrazac in [r"(?:član|čl\.|cl\.)\s*(\d+[a-zA-Z]?)", r"(?:чл\.?)\s*(\d+[a-zA-Z]?)"]:
        m = re.search(obrazac, q)
        if m:
            return m.group(1)
    return None


def _ugradi_query(query: str) -> list[float]:
    return _get_embeddings().embed_query(query)


# ─── Pinecone operacije ───────────────────────────────────────────────────────

def _semanticka_pretraga(query: str, k: int = 10, filter_zakon: Optional[str] = None) -> list:
    index = _get_index()
    vektor = _ugradi_query(query)
    filter_dict = {"law": {"$eq": filter_zakon}} if filter_zakon else None
    try:
        return index.query(vector=vektor, top_k=k, include_metadata=True, filter=filter_dict).matches
    except Exception:
        logger.exception("Greška u semantičkoj pretrazi")
        return []


def _pretraga_vec(vektor: list[float], k: int, filter_zakon: Optional[str] = None) -> list:
    index = _get_index()
    filter_dict = {"law": {"$eq": filter_zakon}} if filter_zakon else None
    try:
        return index.query(vector=vektor, top_k=k, include_metadata=True, filter=filter_dict).matches
    except Exception:
        logger.exception("Greška u pretraga_vec")
        return []


def _direktan_fetch_clana(label_clana: str, zakon: Optional[str] = None) -> list:
    index = _get_index()
    filter_dict: dict = {"article": {"$eq": label_clana}}
    if zakon:
        filter_dict = {"$and": [{"article": {"$eq": label_clana}}, {"law": {"$eq": zakon}}]}
    try:
        dummy = [0.0] * 3072
        return index.query(vector=dummy, top_k=5, include_metadata=True, filter=filter_dict).matches
    except Exception:
        logger.exception("Greška u direktnom fetchu člana %s", label_clana)
        return []


# ─── Sprint 2A: Multi-Query dekompozicija ─────────────────────────────────────

def _dekomponuj_query(query: str) -> list[str]:
    """gpt-4o-mini razlaže pitanje na 3 pravna pod-pitanja. Vraća listu stringova."""
    try:
        resp = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=300,
            timeout=6.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ti si pravni asistent. Dato korisničko pitanje razbij na "
                        "tačno 3 konkretna pravna pod-pitanja koja zajedno pokrivaju "
                        "ceo slučaj. Svako pod-pitanje mora biti samostalno i "
                        "pretraživljivo. Vrati samo JSON listu od 3 stringa."
                    ),
                },
                {"role": "user", "content": f"Pitanje: {query}"},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        # Očisti kod-blokove ako ih GPT doda
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(s, str) for s in parsed):
            logger.debug("[MULTI_Q] %s", parsed)
            return parsed[:3]
    except Exception as e:
        logger.warning("[MULTI_Q] Dekompozicija nije uspela: %s", e)
    return []


# ─── Sprint 2B: HyDE (Hypothetical Document Embedding) ───────────────────────

def _generiši_hyde(query: str) -> str:
    """gpt-4o-mini generiše hipotetički zakonski tekst koji bi odgovorio na pitanje."""
    try:
        resp = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=150,
            timeout=5.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ti si srpski pravni ekspert. Generiši 1-2 rečenice hipotetičkog "
                        "odgovora na pravno pitanje, pišući kao da citiraš tačan zakonski tekst. "
                        "Koristi pravnu terminologiju. Bez uvoda, samo tekst."
                    ),
                },
                {"role": "user", "content": f"Pitanje: {query}"},
            ],
        )
        hyde = resp.choices[0].message.content.strip()
        logger.debug("[HyDE] '%s'", hyde[:100])
        return hyde
    except Exception as e:
        logger.warning("[HyDE] Generisanje nije uspelo: %s", e)
        return ""


# ─── Sprint 3: Cohere Re-Ranking ─────────────────────────────────────────────

def _cohere_rerank(query: str, matches: list, k: int = 3) -> list:
    """
    Rerangira Pinecone rezultate Cohere modelom.
    Fallback: interni skor ako Cohere nije dostupan.
    """
    co = _get_cohere()
    if not co or not matches:
        return matches[:k]

    docs = []
    for m in matches:
        meta = m.metadata or {}
        # Koristi parent_text ako postoji, inače text
        tekst = meta.get("parent_text") or meta.get("text", "")
        docs.append(tekst[:1000])

    try:
        res = co.rerank(
            model="rerank-multilingual-v3.0",
            query=query,
            documents=docs,
            top_n=k,
        )
        reranked = [matches[r.index] for r in res.results]
        logger.debug("[COHERE] Reranked top-%d", k)
        return reranked
    except Exception as e:
        logger.warning("[COHERE] Reranking nije uspeo: %s — fallback na interni skor", e)
        return matches[:k]


# ─── Sprint 4: Parent Document Retrieval ─────────────────────────────────────

def _dohvati_parent_text(match) -> str:
    """
    Iz metapodataka chunka vraća parent_text (ceo član zakona).
    Backward-compat: ako nema parent_text, vraća text.
    """
    meta = match.metadata or {}
    parent = meta.get("parent_text")
    if parent and len(parent) > 100:
        return parent.strip()
    return (meta.get("text") or "").strip()


# ─── Sprint 5A: CRAG — ocena relevantnosti ───────────────────────────────────

def _oceni_relevantnost(query: str, docs: list[str]) -> str:
    """
    GPT-4o ocenjuje da li pronađeni dokumenti odgovaraju na pitanje.
    Vraća: "RELEVANTNO" | "DELIMIČNO" | "NIJE RELEVANTNO"
    """
    if not docs:
        return "NIJE RELEVANTNO"

    kontekst = "\n---\n".join(docs[:3])[:3000]
    try:
        resp = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=20,
            timeout=5.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Oceni da li sledeći pasusi iz pravne baze odgovaraju na pitanje. "
                        "Odgovori JEDNOM rečju: RELEVANTNO, DELIMIČNO, ili NIJE RELEVANTNO."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Pitanje: {query}\n\nPasusi:\n{kontekst}",
                },
            ],
        )
        ocena = resp.choices[0].message.content.strip().upper()
        # Normalizuj — GPT ponekad vrati "NIJE_RELEVANTNO" ili slično
        if "NIJE" in ocena:
            return "NIJE RELEVANTNO"
        if "DELIM" in ocena:
            return "DELIMIČNO"
        return "RELEVANTNO"
    except Exception as e:
        logger.warning("[CRAG] Ocena relevantnosti nije uspela: %s — pretpostavljam RELEVANTNO", e)
        return "RELEVANTNO"


# ─── Sprint 5B: CRAG — proširivanje pretrage ─────────────────────────────────

def _prosiri_pretragu_crag(query: str) -> list[str]:
    """Generiše 2 sinonimna upita za DELIMIČNO granu CRAG petlje."""
    try:
        resp = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=120,
            timeout=5.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generiši tačno 2 kratka alternativna pravna upita (3-6 reči svaki) "
                        "koji bi pronašli relevantne odredbe zakona za dato pitanje. "
                        "Koristi sinonime i srodne pravne pojmove. "
                        "Vrati JSON listu od 2 stringa."
                    ),
                },
                {"role": "user", "content": f"Pitanje: {query}"},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [s for s in parsed[:2] if isinstance(s, str)]
    except Exception as e:
        logger.warning("[CRAG] Proširivanje pretrage nije uspelo: %s", e)
    return []


# ─── Scoring (zadržan za fallback bez Cohere) ────────────────────────────────

def _izracunaj_skor(match, query: str, zakon: Optional[str], label_clana: Optional[str]) -> float:
    skor = match.score * 100
    meta = match.metadata or {}
    zakon_doc  = _normalizuj(meta.get("law", ""))
    clan_doc   = _normalizuj(meta.get("article", ""))
    tekst_doc  = _normalizuj(meta.get("text", "") + meta.get("parent_text", ""))
    query_norm = _normalizuj(query)

    if zakon:
        z = _normalizuj(zakon)
        skor += 30 if z == zakon_doc else (15 if z in zakon_doc else 0)

    if label_clana:
        c = _normalizuj(label_clana)
        skor += 50 if c == clan_doc else (25 if c in clan_doc else 0)

    tokeni  = _tokenizuj(query)
    pogodci = sum(1 for t in tokeni if t in tekst_doc)
    skor += min(pogodci * 3, 20)

    if "nematerijal" in query_norm and "stet" in query_norm:
        if "nematerijalna steta" in tekst_doc: skor += 50
        if "obligacion" in zakon_doc:          skor += 20
        if "200" in clan_doc and "obligacion" in zakon_doc: skor += 80

    if "zastarel" in query_norm:
        if any(x in tekst_doc for x in ["zastareva", "zastari", "zastarelost"]): skor += 45
        if "obligacion" in zakon_doc:
            try:
                m = re.search(r"\d+", clan_doc or "")
                if m and 360 <= int(m.group()) <= 395: skor += 70
            except Exception:
                pass

    if any(x in query_norm for x in ["digital", "kripto", "bitcoin", "usdt", "ethereum", "token", "nft", "blockchain"]):
        if "digitaln" in zakon_doc: skor += 40

    return skor


# ─── Format izlaza ───────────────────────────────────────────────────────────

def _formatiraj_match(match) -> str:
    """Sprint 4: razdvaja citabilni stav (≤300 char) od punog teksta člana za LLM kontekst."""
    meta         = match.metadata or {}
    zakon        = meta.get("law", "Nepoznat zakon")
    clan         = meta.get("article", "Nepoznat član")
    stav_tekst   = (meta.get("text") or "").strip()
    parent_tekst = _dohvati_parent_text(match)

    logger.debug(
        "[FORMAT] id=%s zakon=%s clan=%s | text_len=%d parent_len=%d | "
        "metadata_keys=%s",
        getattr(match, "id", "?"),
        zakon, clan,
        len(stav_tekst), len(parent_tekst),
        list(meta.keys()),
    )

    if parent_tekst and len(parent_tekst) > len(stav_tekst) + 50:
        return (
            f"ZAKON: {zakon}\nČLAN: {clan}\n\n"
            f"CITABILNI TEKST: {stav_tekst}\n\n"
            f"PUNI TEKST ČLANA:\n{parent_tekst}\n"
        )
    return f"ZAKON: {zakon}\nČLAN: {clan}\n\nCITABILNI TEKST: {parent_tekst}\n"


# ─── Konstante za ekspanziju ─────────────────────────────────────────────────

_ZDI_TRIGERI = frozenset(["digital", "kripto", "bitcoin", "usdt", "ethereum", "token", "nft", "virtuelna", "zdi", "blockchain"])
_ZDI_TERMINI = ["digitalna imovina zakon", "kriptovaluta pravni status srbija", "ZDI digitalni token NFT"]

_KZ_TRIGERI  = frozenset(["hakovan", "ukraden", "kradja", "neovlascen", "racunarski kriminal", "krivicna prijava", "krivicno delo"])
_KZ_TERMINI  = ["neovlašćen pristup računarskom sistemu Krivični zakonik", "imovinska šteta krivično delo KZ čl. 302"]

_ZPDG_TRIGERI = frozenset(["zarada od kripto", "prihod od kripto", "kapitalni dobitak", "porez na kripto", "kapitaln dobitak"])
_ZPDG_TERMINI = ["kapitalni dobitak digitalna imovina ZPDG član 72", "porez na dohodak kriptovaluta prijava"]

_SC_TRIGERI   = frozenset(["pametni ugovor", "smart contract", "greska u kodu", "greska koda", "algoritam", "ikt sistem", "softverska greska"])
_SC_TERMINI_ZDI = ["algoritam IKT sistem digitalna imovina", "pametni ugovor digitalni token ZDI"]
_SC_TERMINI_ZOO = ["odgovornost za štetu ZOO član 154"]

_ZOO_FALLBACK_CLANOVI = ["Član 154", "Član 155", "Član 200", "Član 189"]

# ─── Interna helper: jedan retrieval krug ────────────────────────────────────

def _jedan_retrieval_krug(
    query: str,
    vektor: list[float],
    zakon: Optional[str],
    label_clana: Optional[str],
    extra_queries: list[str],
    top_k_pinecone: int = 10,
) -> list:
    """
    Pokreće sve Pinecone pretrage paralelno i vraća deduplikovanu listu matcheva.
    """
    import time as _time
    q_norm = _normalizuj(query)

    executor = ThreadPoolExecutor(max_workers=12)
    fjobs: list[Future] = []

    # a) Direktan fetch člana
    if label_clana:
        fjobs.append(executor.submit(_direktan_fetch_clana, label_clana, zakon))

    # b) Semantička sa filterom
    fjobs.append(executor.submit(_pretraga_vec, vektor, top_k_pinecone, zakon))

    # c) Semantička bez filtera
    fjobs.append(executor.submit(_pretraga_vec, vektor, 6, None))

    # d) ZDI ekspanzija
    if any(x in q_norm for x in _ZDI_TRIGERI):
        for term in _ZDI_TERMINI:
            fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "zakon o digitalnoj imovini"))

    # e) Smart contract ekspanzija
    if any(x in q_norm for x in _SC_TRIGERI):
        for term in _SC_TERMINI_ZDI:
            fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "zakon o digitalnoj imovini"))
        for term in _SC_TERMINI_ZOO:
            fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "zakon o obligacionim odnosima"))

    # f) KZ ekspanzija
    if any(x in q_norm for x in _KZ_TRIGERI):
        for term in _KZ_TERMINI:
            fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "KZ"))

    # g) ZPDG ekspanzija
    if any(x in q_norm for x in _ZPDG_TRIGERI):
        for term in _ZPDG_TERMINI:
            fjobs.append(executor.submit(_semanticka_pretraga, term, 3, "ZPDG"))

    # h) Sprint 2A: multi-query pod-pitanja
    for sub_q in extra_queries:
        fjobs.append(executor.submit(_semanticka_pretraga, sub_q, 5, zakon))
        fjobs.append(executor.submit(_semanticka_pretraga, sub_q, 3, None))

    svi_matchevi: list = []
    for f in as_completed(fjobs):
        try:
            svi_matchevi.extend(f.result())
        except Exception:
            pass

    executor.shutdown(wait=False)

    # Deduplikacija po ID
    vidjeni: set[str] = set()
    jedinstveni = []
    for m in svi_matchevi:
        if m.id not in vidjeni:
            vidjeni.add(m.id)
            jedinstveni.append(m)

    return jedinstveni


# ─── Glavna javna funkcija ────────────────────────────────────────────────────

def retrieve_documents(query: str, k: int = 6) -> list[str]:
    """
    Agentic RAG pipeline — svi 5 sprintova.

    Redosled:
      1. Embed originalnog upita
      2. [PARALEL] Multi-query dekompozicija + HyDE generisanje
      3. [PARALEL] Pinecone retrieval (original + sub-queries + HyDE)
      4. Cohere re-ranking (ili interni skor ako Cohere nije dostupan)
      5. Parent text fetch iz metapodataka
      6. CRAG ocena relevantnosti + corrective petlja (max 2 iteracije)
    """
    import time as _time
    t0 = _time.perf_counter()

    zakon       = _prepoznaj_zakon(query)
    broj_clana  = _izvuci_broj_clana(query)
    label_clana = f"Član {broj_clana}" if broj_clana else None

    # ── Faza 0: Embed jedanput ────────────────────────────────────────────────
    vektor = _ugradi_query(query)

    # ── Faza 1: Query transformation (paralel) ────────────────────────────────
    with ThreadPoolExecutor(max_workers=2) as qte:
        f_multi = qte.submit(_dekomponuj_query, query)
        f_hyde  = qte.submit(_generiši_hyde,    query)

    sub_queries: list[str] = []
    hyde_text = ""
    try:
        sub_queries = f_multi.result(timeout=16.0)
    except Exception:
        logger.info("[MULTI_Q] Timeout ili greška — preskočena")

    try:
        hyde_text = f_hyde.result(timeout=13.0)
    except Exception:
        logger.info("[HyDE] Timeout ili greška — preskočena")

    # ── Faza 2: Retrieval ─────────────────────────────────────────────────────
    matchevi = _jedan_retrieval_krug(query, vektor, zakon, label_clana, sub_queries)

    # HyDE: embed hipotetičkog dokumenta i dodaj rezultate
    if hyde_text:
        hyde_vec = _ugradi_query(hyde_text)
        hyde_m   = _pretraga_vec(hyde_vec, 8, zakon) + _pretraga_vec(hyde_vec, 5, None)
        vidjeni  = {m.id for m in matchevi}
        for m in hyde_m:
            if m.id not in vidjeni:
                vidjeni.add(m.id)
                matchevi.append(m)
        logger.debug("[HyDE] Dodato %d novih matcheva", len(hyde_m))

    # GPT ekspanzija (background, max 3s)
    with ThreadPoolExecutor(max_workers=1) as gpe:
        gpt_fut = gpe.submit(
            lambda: _semanticka_pretraga.__module__ and
            __import__('app.services.retrieve', fromlist=['_prosiri_query_gpt']) and None
            or []
        )
        # Direktno pozovemo
        gpt_fut = gpe.submit(_prosiri_query_gpt_wrapper, query)
    try:
        prosireni = gpt_fut.result(timeout=3.0)
        vidjeni = {m.id for m in matchevi}
        with ThreadPoolExecutor(max_workers=4) as ee:
            efuts = [ee.submit(_semanticka_pretraga, eq, 3) for eq in prosireni[:3]]
            for f in as_completed(efuts, timeout=2.0):
                try:
                    for m in f.result():
                        if m.id not in vidjeni:
                            vidjeni.add(m.id)
                            matchevi.append(m)
                except Exception:
                    pass
    except Exception:
        pass

    # ── Faza 3: Re-ranking ────────────────────────────────────────────────────
    # Interni scoring za sortiranje kandidata pre Cohere
    skorovani = sorted(
        [(_izracunaj_skor(m, query, zakon, label_clana), m) for m in matchevi],
        key=lambda x: x[0], reverse=True,
    )
    top_kandid = [m for _, m in skorovani[:10]]

    # Cohere re-rank top-10 → top-k
    reranked = _cohere_rerank(query, top_kandid, k=k)

    # ZOO fallback ako je rezultat slab
    top_skor = skorovani[0][0] if skorovani else 0
    if len(reranked) < 3 or top_skor < 50:
        with ThreadPoolExecutor(max_workers=4) as fb:
            fbs = [
                fb.submit(_direktan_fetch_clana, clan, "zakon o obligacionim odnosima")
                for clan in _ZOO_FALLBACK_CLANOVI
            ]
            vidjeni = {m.id for m in reranked}
            for f in as_completed(fbs):
                try:
                    for m in f.result():
                        if m.id not in vidjeni:
                            vidjeni.add(m.id)
                            reranked.append(m)
                except Exception:
                    pass
        reranked = reranked[:k]

    # ── Faza 4: Parent Document fetch ─────────────────────────────────────────
    # _formatiraj_match automatski čita parent_text iz metapodataka
    docs = [_formatiraj_match(m) for m in reranked]

    # ── Faza 5: CRAG petlja (max 2 iteracije) ─────────────────────────────────
    docs = _crag_petlja(query, docs, zakon, vektor, k, max_iter=1)

    elapsed = _time.perf_counter() - t0
    logger.info(
        "[RETRIEVE] %.2fs | matches=%d | top=%d | zakon=%s | member=%s",
        elapsed, len(matchevi), k, zakon or "—", label_clana or "—",
    )

    return docs


def _prosiri_query_gpt_wrapper(query: str) -> list[str]:
    """GPT-4o-mini generiše 3 alternativna search querija."""
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=200,
            timeout=20.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ti si ekspert za srpsko pravo. "
                        "Za dato pravno pitanje generiši tačno 4 kratka search query-ja (3-7 reči svaki). "
                        "Koristi pravne termine iz srpskih zakona. "
                        "Vrati SAMO query-je, jedan po liniji, bez numeracije."
                    ),
                },
                {"role": "user", "content": f"Pitanje: {query}"},
            ],
        )
        tekst = resp.choices[0].message.content.strip()
        return [q.strip() for q in tekst.split("\n") if q.strip()][:4]
    except Exception:
        return []


# ─── Sprint 5: CRAG petlja ───────────────────────────────────────────────────

def _crag_petlja(
    query: str,
    docs: list[str],
    zakon: Optional[str],
    vektor: list[float],
    k: int,
    max_iter: int = 2,
) -> list[str]:
    """
    Corrective RAG petlja.
    RELEVANTNO   → vrati docs bez izmene
    DELIMIČNO    → proširi pretragu i ponovi reranking
    NIJE RELEVANTNO → aktiviraj HyDE i ponovi; ako i to ne uspe → vrati fallback
    """
    for iteracija in range(max_iter):
        ocena = _oceni_relevantnost(query, docs)
        logger.info("[CRAG] Iteracija %d — ocena: %s", iteracija + 1, ocena)

        if ocena == "RELEVANTNO":
            return docs

        if ocena == "DELIMIČNO":
            # Proširena pretraga sa sinonimima
            dodatni_upiti = _prosiri_pretragu_crag(query)
            if not dodatni_upiti:
                return docs  # ne možemo proširiti — vrati što imamo

            extra_matchevi: list = []
            for upit in dodatni_upiti:
                extra_matchevi.extend(_semanticka_pretraga(upit, 5, zakon))
                extra_matchevi.extend(_semanticka_pretraga(upit, 3, None))

            # Deduplikuj i re-rank sve zajedno
            vidjeni_ids = set()
            svi = list(docs)  # Počnemo od postojećih
            novi_matchevi = []
            for m in extra_matchevi:
                if m.id not in vidjeni_ids:
                    vidjeni_ids.add(m.id)
                    novi_matchevi.append(m)

            if novi_matchevi:
                reranked = _cohere_rerank(query, novi_matchevi, k=k)
                docs = [_formatiraj_match(m) for m in reranked]
                # Dodaj napomenu o delimičnoj pokrivenosti
                docs.append(
                    "[NAPOMENA] Pronađene odredbe pokrivaju deo pitanja. "
                    "Za potpun odgovor konsultujte i relevantne podzakonske akte."
                )
            return docs

        if ocena == "NIJE RELEVANTNO":
            if iteracija == 0:
                # Aktiviraj HyDE strategiju
                logger.info("[CRAG] Aktiviram HyDE fallback...")
                hyde = _generiši_hyde(query)
                if hyde:
                    hyde_vec = _ugradi_query(hyde)
                    hyde_matchevi = (
                        _pretraga_vec(hyde_vec, 10, zakon) +
                        _pretraga_vec(hyde_vec, 6, None)
                    )
                    if hyde_matchevi:
                        reranked = _cohere_rerank(query, hyde_matchevi, k=k)
                        docs = [_formatiraj_match(m) for m in reranked]
                        continue  # Ponovi ocenu sa HyDE rezultatima
            else:
                # Konačni fallback — identifikuj zakone po temi
                return [_fallback_poruka(query)]

    return docs


def _fallback_poruka(query: str) -> str:
    """Fallback poruka kada baza ne pokriva pitanje — identifikuje relevantne zakone po temi."""
    q = _normalizuj(query)

    relevantni = []
    if any(x in q for x in ["privredn", "drustv", "apr", "osnivanj", "registraci", "zastupnik"]):
        relevantni.append("Zakon o privrednim društvima (ZPD)")
    if any(x in q for x in ["rad", "zaposlen", "otkaz", "zarada"]):
        relevantni.append("Zakon o radu (ZR)")
    if any(x in q for x in ["ugovor", "obavez", "steta", "naknada"]):
        relevantni.append("Zakon o obligacionim odnosima (ZOO)")
    if any(x in q for x in ["porez", "poresk", "prihod", "priход"]):
        relevantni.append("Zakon o porezu na dohodak građana (ZPDG)")
    if any(x in q for x in ["krivic", "kazna", "kradja", "hakovan"]):
        relevantni.append("Krivični zakonik (KZ)")
    if not relevantni:
        relevantni = ["Zakon o privrednim društvima", "Zakon o obligacionim odnosima"]

    zakoni_str = "; ".join(relevantni)
    return (
        f"[SISTEM] Pitanje nije direktno pokriveno podacima u bazi. "
        f"Relevantni zakoni koje treba konsultovati: {zakoni_str}."
    )


# ─── Dijagnostička funkcija ───────────────────────────────────────────────────

def proveri_zdi_indeksiranost() -> dict:
    ciljni = ["Član 2", "Član 74", "Član 75", "Član 78"]
    rezultat: dict[str, bool] = {}
    for clan in ciljni:
        matchevi = _direktan_fetch_clana(clan, "zakon o digitalnoj imovini")
        pronadjen = any(
            _normalizuj(m.metadata.get("law", "")) == "zakon o digitalnoj imovini"
            and _normalizuj(m.metadata.get("article", "")) == _normalizuj(clan)
            for m in matchevi
        )
        rezultat[clan] = pronadjen
        logger.info("[ZDI_CHECK] %s: %s", clan, "✓" if pronadjen else "✗ NIJE indeksiran")
    return rezultat
