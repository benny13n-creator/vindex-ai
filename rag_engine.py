"""
rag_engine.py — Legal AI Agent za srpsko pravo

Bulletproof RAG sistem za advokate.
Kompatibilan sa ingest_service.py (metadata: law, article, source, chunk).

Autor: moj_prvi_agent
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI

load_dotenv()

import zipfile
from pathlib import Path

import gdown

BASE_DIR = Path(__file__).resolve().parent
VECTOR_STORE_DIR = BASE_DIR / "vector_store"
VECTOR_STORE_ZIP = BASE_DIR / "vector_store.zip"
GOOGLE_DRIVE_FILE_ID = "1pwlGDwyOmTATMRKKosLbuQjxm2SQ13jo"


def preuzmi_vector_store() -> None:
    """Preuzima vector_store.zip sa Google Drive-a i raspakuje ga ako baza ne postoji."""
    if VECTOR_STORE_DIR.exists():
        print("✅ vector_store već postoji, preskačem download.")
        return

    try:
        print("⬇️ Preuzimam bazu zakona...")
        gdown.download(
            id=GOOGLE_DRIVE_FILE_ID,
            output=str(VECTOR_STORE_ZIP),
            quiet=False,
            fuzzy=True,
        )

        if not VECTOR_STORE_ZIP.exists():
            raise FileNotFoundError("vector_store.zip nije preuzet.")

        print("📦 Raspakujem bazu...")
        with zipfile.ZipFile(VECTOR_STORE_ZIP, "r") as zf:
            extract_path = BASE_DIR / "vector_store"
            extract_path.mkdir(parents=True, exist_ok=True)
            zf.extractall(extract_path)

        if not VECTOR_STORE_DIR.exists():
            raise FileNotFoundError("Raspakivanje je završeno, ali folder vector_store ne postoji.")

        print("✅ Baza spremna!")

    except Exception as e:
        print(f"❌ Greška pri preuzimanju vector_store baze: {e}")
        raise

    finally:
        if VECTOR_STORE_ZIP.exists():
            VECTOR_STORE_ZIP.unlink()


preuzmi_vector_store()

# ─────────────────────────────────────────────
# KONSTANTE
# ─────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
VECTOR_STORE_DIR = BASE_DIR / "vector_store"

EMBEDDING_MODEL = "text-embedding-3-large"   # Veći model = bolji recall
LLM_MODEL = "gpt-4o"
TEMPERATURE = 0                              # NULA — nikakve kreativnosti
TOP_K_RETRIEVE = 12                          # Više kandidata → bolji rerank
TOP_K_FINAL = 6                              # Koliko šaljemo u prompt

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
    """Latinizacija + lowercase, bez izmene semantike."""
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
# SCORING — deterministički reranker
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

    # 1) Poklapanje zakona
    if guessed_law:
        gn = normalize(guessed_law)
        if gn == doc_law:
            score += 50
        elif gn in doc_law:
            score += 35

    # 2) Poklapanje člana — najvažniji signal
    if article_label:
        an = normalize(article_label)
        if an == doc_article:
            score += 80
        elif an in doc_article:
            score += 55
        elif an in text:
            score += 30

    # 3) Token poklapanje u tekstu
    hits = sum(1 for t in tokens if t in text)
    score += min(hits * 5, 30)

    # 4) Visokovredne fraze
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

    # 5) Penali za očigledni promašaj
    critical_terms = ["nematerijal", "stet", "otkaz", "zastarel", "krivic", "nasledj"]
    for term in critical_terms:
        if term in qn and term not in text:
            score -= 20

    # 6) Blagi bonus ako zakon pominje sebe u tekstu
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

    # ── Korak 1: Direktno gađanje po metapodacima (100% preciznost kad postoji)
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

    # ── Korak 2: Semantička pretraga sa varijacijama upita
    variations = _build_variations(query, guessed_law, article_label)
    for v in variations:
        try:
            docs = db.similarity_search(v, k=TOP_K_RETRIEVE)
            collected.extend(docs)
        except Exception as e:
            print(f"[SIMILARITY] '{v}': {e}")

    # ── Korak 3: Deduplikacija → reranking → slice
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

    # Tematske ekspanzije
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
        "zastarel": [
            "zastarelost potrazivanja rok zastarelosti",
        ],
        "nasledj": [
            "nasledjivanje zakonski naslednici testamenat",
        ],
        "razvod": [
            "razvod braka bračna zajednica porodični zakon",
        ],
        "staratelj": [
            "starateljstvo maloletnik porodični zakon",
        ],
    }

    for kw, extras in expansions.items():
        if kw in qn:
            variations.extend(extras)

    # Dedupe varijacija
    seen: set[str] = set()
    result = []
    for v in variations:
        key = normalize(v)
        if key not in seen:
            seen.add(key)
            result.append(v)

    return result


# ─────────────────────────────────────────────
# SISTEM PROMPT — stroga pravna logika
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
  2. izuzeci ili posebni slučajevi
  3. pravna posledica
  4. šta treba dodatno proveriti za konkretan slučaj

• Na kraju odgovora, kada je to opravdano kontekstom, dodaj kratku praktičnu napomenu šta je ključno proveriti da bi odgovor bio pravilno primenjen u konkretnom slučaju

NIJE DOZVOLJENO:

• Dodavanje informacija koje ne postoje u tekstu
• Pretpostavljanje činjenica koje nisu navedene
• Proširivanje odgovora van dostavljenog konteksta

1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog zakonskog konteksta.
2. ZABRANJENO: korišćenje opšteg znanja, pretpostavki, analogija ili pravnih zaključaka koji nisu direktno podržani dostavljenim tekstom.
3. ZABRANJENO: izmišljanje zakona, članova, stavova, tačaka, rokova, prava, obaveza ili pravnih posledica.
4. ZABRANJENO: mešanje pravnih instituta (npr. opšta naknada štete ≠ nematerijalna šteta) ukoliko to nije eksplicitno podržano tekstom.
5. Ako traženi odgovor NIJE u kontekstu → reci to jasno i precizno. Ne popunjavaj praznine.
6. Ako je kontekst DELIMIČAN → navedi šta jeste pronađeno, ali jasno označi šta nedostaje.
7. Ako postoji tačan zakon i član → OBAVEZNO ih navedi sa punim nazivom.
8. Ako postoji stav ili tačka unutar člana → navedi ih precizno (npr. “stav 2, tačka 3”).
9. Citiraj SAMO ono što postoji u dostavljenom kontekstu — doslovno, bez izmena.
10. Nivo pouzdanosti mora biti realan: ako postoji i najmanja sumnja → “srednja” ili “niska”.
11.Ako je pitanje preširoko, neodređeno ili može imati više pravnih režima, prvo jasno reci da tačan odgovor zavisi od vrste postupka, pravnog odnosa ili konkretnog zakona. Tek zatim navedi relevantne mogućnosti pregledno i hijerarhijski.

═══════════════════════════════════════════════════════════
OBAVEZAN FORMAT ODGOVORA
═══════════════════════════════════════════════════════════

PRAVNI OSNOV:

• Navedi zakon i član koji direktno odgovara na pitanje
• Ako navodiš više članova:
• ukratko objasni njihovu ulogu (npr. definicija + pravna posledica)
•Navodi SAMO najrelevantnije članove zakona (maksimalno 3). Ako postoji jedan ključni član, navedi samo njega.

ODGOVOR:
• Daj direktan i jasan odgovor na pitanje
• Ako je moguće, strukturiraj odgovor u kratke tačke
• Ne prepričavaj zakon — objasni šta norma znači u praksi
• Koristi isključivo informacije iz dostavljenog konteksta
• Kada daješ definiciju, koristi formulaciju koja je što bliža zakonskom tekstu

CITAT IZ ZAKONA:
[Doslovan citat koji direktno podržava odgovor. Ako ne postoji: “Nije pronađen direktan citat koji u potpunosti odgovara pitanju.”]

PRAVNA POSLEDICA:
• Ako pravna posledica jasno proizlazi iz teksta → navedi je
• Ako je delimično vidljiva → navedi samo ono što je sigurno
• Ako nije jasno → napiši da nije moguće pouzdano zaključiti 

POSTUPANJE U PRAKSI:
[Samo ako je direktno podržano tekstom. Ako ne: “Za konkretno postupanje u praksi potreban je širi pravni i činjenični kontekst.”]

OGRANIČENJA ODGOVORA:
[Šta kontekst NE pokriva, šta bi trebalo proveriti u izvornom tekstu zakona, eventualne izmene i dopune.]

NAPOMENA O POUZDANOSTI:
[VISOKA — citat je direktan i potpun / SREDNJA — kontekst je delimičan / NISKA — kontekst nije dovoljan]

═══════════════════════════════════════════════════════════
STIL
═══════════════════════════════════════════════════════════

• Srpski jezik, latinica
• Profesionalan, precizan, bez generičkog uvoda
• Kratke rečenice, jasna struktura
• Nikad ne pretpostavljaj ono što zakon ne kaže eksplicitno

═══════════════════════════════════════════════════════════
PRIORITET
═══════════════════════════════════════════════════════════

Advokat koristi ovaj alat da uštedi vreme.

Odgovor mora biti:
• jasan
• konkretan
• odmah primenljiv
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
    """
    Glavni ulaz za agenta.
    Prima pitanje, vraća strukturiran pravni odgovor.
    """
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


# ─────────────────────────────────────────────
# NAPOMENA ZA REINGEST
# ─────────────────────────────────────────────

"""
⚠️ VAŽNO: Ovaj fajl koristi EMBEDDING_MODEL = "text-embedding-3-large".
Ako je postojeći vector_store kreiran sa "text-embedding-3-small",
mora se pokrenuti reingest:

    python ingest_service.py

Pre toga, u ingest_service.py promeni:
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

Bez reingest-a pretraga neće raditi ispravno.
"""