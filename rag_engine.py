from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path
from typing import Optional

import gdown
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI

load_dotenv()

# ─────────────────────────────────────────────
# KONSTANTE
# ─────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
VECTOR_STORE_DIR = BASE_DIR / "vector_store"

EMBEDDING_MODEL = "text-embedding-3-large"
LLM_MODEL = "gpt-4o"
TEMPERATURE = 0
TOP_K_RETRIEVE = 12
TOP_K_FINAL = 6

# ─────────────────────────────────────────────
# AUTO-DOWNLOAD VECTOR STORE
# ─────────────────────────────────────────────


def preuzmi_vector_store():
    if VECTOR_STORE_DIR.exists():
        print("✅ Vector store već postoji!")
        return

    print("⬇️ Preuzimam bazu zakona...")
    zip_path = BASE_DIR / "vector_store.zip"

    gdown.download(
        id="1pwlGDwyOmTATMRKKosLbuQjxm2SQ13jo",
        output=str(zip_path),
        quiet=False
    )

    if not zip_path.exists():
        print("❌ Zip NIJE preuzet!")
        return

    print(f"📦 Zip preuzet, velicina: {zip_path.stat().st_size}")
    print("📦 Raspakujem...")

    with zipfile.ZipFile(zip_path, "r") as z:
        imena = z.namelist()
        print(f"Fajlovi u zipu: {imena[:5]}")
        z.extractall(BASE_DIR)

    print(f"📁 Sadrzaj vector_store: {list(VECTOR_STORE_DIR.iterdir())[:5]}")
    zip_path.unlink()
    print("✅ Gotovo!")


preuzmi_vector_store()

# ─────────────────────────────────────────────
# MAPIRANJE ZAKONA
# ─────────────────────────────────────────────

LAW_KEYWORDS: dict[str, str] = {
    "rad": "zakon o radu",
    "porodic": "porodicni zakon",
    "krivic": "zakon o krivicnom postupku",
    "parnic": "zakon o parnicnom postupku",
    "izvrs": "zakon o izvrsenju i obezbedjenju",
    "obligaci": "zakon o obligacionim odnosima",
    "privredn": "zakon o privrednim drustvima",
    "uprav": "zakon o opstem upravnom postupku",
    "vanparnic": "zakon o vanparnicnom postupku",
    "nasledj": "zakon o nasledjivanju",
    "ustav": "ustav republike srbije",
    "zastit": "zakon o zastiti potrosaca",
    "zastita": "zakon o zastiti podataka o licnosti",
    "krivic zakon": "krivicni zakonik",
}

STOPWORDS: set[str] = {
    "koji", "koja", "koje", "kako", "kada", "zasto", "sta", "gde",
    "da", "li", "se", "su", "je", "u", "na", "po", "za", "od", "do",
    "i", "ili", "a", "ali", "te", "uz", "kod", "sa", "bez", "prema",
    "ovo", "onaj", "ovaj", "taj", "njih", "njegov", "njen", "moze",
    "mogu", "ima", "imaju", "biti", "bio", "bila", "bilo", "nisu",
    "jeste", "nije", "clan", "zakon", "srbije", "republike",
}

# ─────────────────────────────────────────────
# DB — singleton
# ─────────────────────────────────────────────

_DB: Optional[Chroma] = None


def get_db() -> Chroma:
    global _DB
    if _DB is not None:
        return _DB

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    _DB = Chroma(
        persist_directory=str(VECTOR_STORE_DIR),
        embedding_function=embeddings,
    )
    return _DB


# ─────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────

def normalize(text: str) -> str:
    text = (text or "").lower()
    for src, dst in {"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z"}.items():
        text = text.replace(src, dst)
    return text


def guess_law(query: str) -> Optional[str]:
    q = normalize(query)
    for kw, law in LAW_KEYWORDS.items():
        if kw in q:
            return law
    return None


def extract_article_number(query: str) -> Optional[str]:
    q = query.lower()
    m = re.search(r"(?:član|clan)\s*(\d+[a-zA-Z]?)", q, flags=re.IGNORECASE)
    return m.group(1) if m else None


def tokenize(query: str) -> list[str]:
    q = normalize(query)
    tokens = re.findall(r"[a-z0-9]+", q)
    return [t for t in tokens if len(t) >= 3 and t not in STOPWORDS]


def deduplicate(docs: list) -> list:
    seen: set[tuple] = set()
    result = []
    for doc in docs:
        meta = getattr(doc, "metadata", {}) or {}
        content = getattr(doc, "page_content", "") or ""
        key = (
            meta.get("law", ""),
            meta.get("article", ""),
            normalize(content[:200]),
        )
        if key not in seen:
            seen.add(key)
            result.append(doc)
    return result


def format_doc(doc) -> str:
    metadata = getattr(doc, "metadata", {}) or {}
    text = (getattr(doc, "page_content", "") or "").strip()
    law = metadata.get("law", "Nepoznat zakon")
    article = metadata.get("article", "Nepoznat član")
    return f"ZAKON: {law}\nČLAN: {article}\n\n{text}"


# ─────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────

def score_doc(doc, query: str, guessed_law: Optional[str], article_label: Optional[str]) -> float:
    score = 0.0
    meta = getattr(doc, "metadata", {}) or {}
    content = getattr(doc, "page_content", "") or ""

    doc_law = normalize(meta.get("law", ""))
    doc_article = normalize(meta.get("article", ""))
    text = normalize(content)
    qn = normalize(query)
    tokens = tokenize(query)

    if guessed_law:
        gn = normalize(guessed_law)
        if gn == doc_law:
            score += 50
        elif gn in doc_law:
            score += 35

    if article_label:
        an = normalize(article_label)
        if an == doc_article:
            score += 80
        elif an in doc_article:
            score += 55
        elif an in text:
            score += 30

    hits = sum(1 for t in tokens if t in text)
    score += min(hits * 5, 30)

    high_value = [
        "nematerijalna steta", "dusevni bol", "fizicki bol",
        "pretrpljeni strah", "umanjenje zivotne aktivnosti",
        "zastarelost", "otkaz ugovora o radu", "povreda radne obaveze",
        "naknada stete", "ugovor o radu", "nasledjivanje",
        "razvod braka", "starateljstvo", "hipoteka",
    ]
    for phrase in high_value:
        if phrase in qn and phrase in text:
            score += 15

    critical_terms = ["nematerijal", "stet", "otkaz", "zastarel", "krivic", "nasledj"]
    for term in critical_terms:
        if term in qn and term not in text:
            score -= 20

    if guessed_law and normalize(guessed_law) in text:
        score += 8

    return score


def rerank(docs: list, query: str, guessed_law: Optional[str], article_label: Optional[str]) -> list:
    scored = [(score_doc(d, query, guessed_law, article_label), d) for d in docs]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored]


# ─────────────────────────────────────────────
# RETRIEVAL
# ─────────────────────────────────────────────

def retrieve_documents(query: str, k: int = TOP_K_FINAL) -> list[str]:
    db = get_db()
    guessed_law = guess_law(query)
    article_num = extract_article_number(query)
    article_label = f"Član {article_num}" if article_num else None

    collected: list = []

    if article_label:
        try:
            where = (
                {"$and": [{"article": article_label}, {"law": guessed_law}]}
                if guessed_law
                else {"article": article_label}
            )
            results = db.get(where=where)
            if results and results.get("documents"):
                for text, meta in zip(results["documents"], results["metadatas"]):
                    obj = type("Doc", (), {"page_content": text, "metadata": meta})()
                    collected.append(obj)
        except Exception as e:
            print(f"[DIRECT_FETCH] {e}")

    variations = _build_variations(query, guessed_law, article_label)
    for v in variations:
        try:
            docs = db.similarity_search(v, k=TOP_K_RETRIEVE)
            collected.extend(docs)
        except Exception as e:
            print(f"[SIMILARITY] '{v}': {e}")

    collected = deduplicate(collected)
    ranked = rerank(collected, query, guessed_law, article_label)
    top = ranked[:k]

    if not top:
        return []

    return [format_doc(d) for d in top]


def _build_variations(query: str, guessed_law: Optional[str], article_label: Optional[str]) -> list[str]:
    variations = [query]

    if guessed_law:
        variations.append(f"{query} {guessed_law}")

    if article_label:
        variations.append(f"{article_label} {query}")
        if guessed_law:
            variations.append(f"{article_label} {guessed_law}")

    qn = normalize(query)
    expansions = {
        "nematerijal": [
            "nematerijalna steta zakon o obligacionim odnosima",
            "dusevni bol fizicki bol pretrpljeni strah umanjenje zivotne aktivnosti",
        ],
        "otkaz": [
            "otkaz ugovora o radu zakon o radu",
            "povreda radne obaveze otkazni rok",
        ],
        "zastarel": ["zastarelost potrazivanja rok zastarelosti"],
        "nasledj": ["nasledjivanje zakonski naslednici testamenat"],
        "razvod": ["razvod braka bračna zajednica porodični zakon"],
        "staratelj": ["starateljstvo maloletnik porodični zakon"],
    }

    for kw, extras in expansions.items():
        if kw in qn:
            variations.extend(extras)

    seen: set[str] = set()
    result = []
    for v in variations:
        key = normalize(v)
        if key not in seen:
            seen.add(key)
            result.append(v)

    return result


# ─────────────────────────────────────────────
# SISTEM PROMPT
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """
Ti si stručni pravni AI asistent za advokate u Republici Srbiji.

═══════════════════════════════════════════════════════════
APSOLUTNA PRAVILA — NIJEDNO SE NE SME PREKRŠITI
═══════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════
DOZVOLJENA INTERPRETACIJA (OGRANIČENA)
═══════════════════════════════════════════════════════════

DOZVOLJENO JE:

• Izvesti KRATAK i DIREKTAN zaključak koji logički proizlazi iz dostavljenog teksta
• Preformulisati zakonsku normu u praktičan i jasan odgovor
• Sažeti zakon u konkretne tačke koje su korisne advokatu
• Kada je moguće, organizuj odgovor sledećim redosledom:

1. osnovno pravilo
1. izuzeci ili posebni slučajevi
1. pravna posledica
1. šta treba dodatno proveriti za konkretan slučaj

NIJE DOZVOLJENO:

• Dodavanje informacija koje ne postoje u tekstu
• Pretpostavljanje činjenica koje nisu navedene
• Proširivanje odgovora van dostavljenog konteksta

1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog zakonskog konteksta.
1. ZABRANJENO: korišćenje opšteg znanja, pretpostavki, analogija ili pravnih zaključaka koji nisu direktno podržani dostavljenim tekstom.
1. ZABRANJENO: izmišljanje zakona, članova, stavova, tačaka, rokova, prava, obaveza ili pravnih posledica.
1. ZABRANJENO: mešanje pravnih instituta ukoliko to nije eksplicitno podržano tekstom.
1. Ako traženi odgovor NIJE u kontekstu → reci to jasno i precizno.
1. Ako je kontekst DELIMIČAN → navedi šta jeste pronađeno, ali jasno označi šta nedostaje.
1. Ako postoji tačan zakon i član → OBAVEZNO ih navedi sa punim nazivom.
1. Ako postoji stav ili tačka unutar člana → navedi ih precizno.
1. Citiraj SAMO ono što postoji u dostavljenom kontekstu — doslovno, bez izmena.
1. Nivo pouzdanosti mora biti realan.

═══════════════════════════════════════════════════════════
OBAVEZAN FORMAT ODGOVORA
═══════════════════════════════════════════════════════════

PRAVNI OSNOV:
• Navedi zakon i član koji direktno odgovara na pitanje

ODGOVOR:
• Daj direktan i jasan odgovor na pitanje

CITAT IZ ZAKONA:
[Doslovan citat koji direktno podržava odgovor.]

PRAVNA POSLEDICA:
• Ako pravna posledica jasno proizlazi iz teksta → navedi je

POSTUPANJE U PRAKSI:
[Samo ako je direktno podržano tekstom.]

OGRANIČENJA ODGOVORA:
[Šta kontekst NE pokriva.]

NAPOMENA O POUZDANOSTI:
[VISOKA / SREDNJA / NISKA]

═══════════════════════════════════════════════════════════
STIL
═══════════════════════════════════════════════════════════

• Srpski jezik, latinica
• Profesionalan, precizan, bez generičkog uvoda
• Kratke rečenice, jasna struktura
""".strip()

# ─────────────────────────────────────────────
# ANSWER ENGINE
# ─────────────────────────────────────────────

_CLIENT: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI()
    return _CLIENT


def build_context(docs: list[str]) -> str:
    if not docs:
        return "NEMA PRONAĐENOG KONTEKSTA."
    separator = "\n\n" + ("─" * 80) + "\n\n"
    return "\n\n" + separator.join(docs)


def answer_question(question: str) -> str:
    if not question or not question.strip():
        return _no_context_response("Pitanje je prazno.")

    docs = retrieve_documents(question, k=TOP_K_FINAL)
    context = build_context(docs)

    if not docs:
        return _no_context_response(
            "Na osnovu dostupne baze nije pronađen dovoljno relevantan zakonski tekst."
        )

    user_prompt = f"""PITANJE ADVOKATA:
{question.strip()}

DOSTAVLJENI ZAKONSKI KONTEKST:
{context}

─────────────────────────────────────────────
INSTRUKCIJA:
Odgovori ISKLJUČIVO na osnovu gore dostavljenog konteksta.
Ako kontekst ne daje direktan odgovor na pitanje, reci to otvoreno.
Nikad ne dopunjuj praznine sopstvenim znanjem.
Navedi tačan naziv zakona, član, stav i tačku gde god je to moguće.
""".strip()

    try:
        response = get_client().chat.completions.create(
            model=LLM_MODEL,
            temperature=TEMPERATURE,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        return content.strip() if content else _no_context_response("Model nije vratio sadržaj.")

    except Exception as e:
        print(f"[LLM_ERROR] {e}")
        return _no_context_response(f"Greška pri generisanju odgovora: {e}")


def _no_context_response(reason: str) -> str:
    return f"""PRAVNI OSNOV:
Nije direktno potvrđeno u dostavljenom kontekstu.

ODGOVOR:
{reason}

CITAT IZ ZAKONA:
Nije pronađen direktan citat koji u potpunosti odgovara pitanju.

PRAVNA POSLEDICA:
Nije moguće pouzdano zaključiti pravnu posledicu samo na osnovu dostavljenog teksta.

POSTUPANJE U PRAKSI:
Za konkretno postupanje u praksi potreban je širi pravni i činjenični kontekst.

OGRANIČENJA ODGOVORA:
Preporučuje se direktna konsultacija izvornog teksta zakona ili nadležnih pravnih baza.

NAPOMENA O POUZDANOSTI:
NISKA — relevantan zakonski kontekst nije pronađen u bazi.""".strip()