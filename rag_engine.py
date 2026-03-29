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

BASE_DIR = Path(__file__).resolve().parent
VECTOR_STORE_DIR = BASE_DIR / "vector_store"

EMBEDDING_MODEL = "text-embedding-3-large"
LLM_MODEL = "gpt-4o"
TEMPERATURE = 0
TOP_K_RETRIEVE = 12
TOP_K_FINAL = 6


def preuzmi_vector_store():
    if VECTOR_STORE_DIR.exists():
        print("Vector store vec postoji!")
        return
    print("Preuzimam bazu zakona...")
    zip_path = BASE_DIR / "vector_store.zip"
    gdown.download(
        id="1pwlGDwyOmTATMRKKosLbuQjxm2SQ13jo",
        output=str(zip_path),
        quiet=False
    )
    if not zip_path.exists():
        print("Zip NIJE preuzet!")
        return
    print("Raspakujem...")
    VECTOR_STORE_DIR.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
    imena = z.namelist()
    print(f"Fajlovi u zipu: {imena[:5]}")
    # Raspakuj direktno u BASE_DIR
    z.extractall(BASE_DIR)
    # Ako nije napravljen vector_store folder, napravi ga
    if not VECTOR_STORE_DIR.exists():
        VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
        # Premesti fajlove u vector_store
        for ime in imena:
            src = BASE_DIR / ime
            dst = VECTOR_STORE_DIR / ime
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dst)


preuzmi_vector_store()

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
        key = (meta.get("law", ""), meta.get("article", ""), normalize(content[:200]))
        if key not in seen:
            seen.add(key)
            result.append(doc)
    return result


def format_doc(doc) -> str:
    metadata = getattr(doc, "metadata", {}) or {}
    text = (getattr(doc, "page_content", "") or "").strip()
    law = metadata.get("law", "Nepoznat zakon")
    article = metadata.get("article", "Nepoznat clan")
    return f"ZAKON: {law}\nCLAN: {article}\n\n{text}"


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


def retrieve_documents(query: str, k: int = TOP_K_FINAL) -> list[str]:
    db = get_db()
    guessed_law = guess_law(query)
    article_num = extract_article_number(query)
    article_label = f"Clan {article_num}" if article_num else None
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
        "nematerijal": ["nematerijalna steta zakon o obligacionim odnosima"],
        "otkaz": ["otkaz ugovora o radu zakon o radu"],
        "zastarel": ["zastarelost potrazivanja rok zastarelosti"],
        "nasledj": ["nasledjivanje zakonski naslednici testamenat"],
        "razvod": ["razvod braka bracna zajednica porodicni zakon"],
        "staratelj": ["starateljstvo maloletnik porodicni zakon"],
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


SYSTEM_PROMPT = """Ti si strucni pravni AI asistent za advokate u Republici Srbiji.

PRAVILA:

1. Odgovaras ISKLJUCIVO na osnovu dostavljenog zakonskog konteksta.
1. ZABRANJENO: izmisljanje zakona, clanova, rokova ili pravnih posledica.
1. Ako odgovor NIJE u kontekstu, reci to jasno.
1. Navedi tacan naziv zakona i clana.

FORMAT:

PRAVNI OSNOV:
[Zakon i clan]

ODGOVOR:
[Direktan odgovor]

CITAT IZ ZAKONA:
[Doslovan citat]

PRAVNA POSLEDICA:
[Ako jasno proizlazi]

NAPOMENA O POUZDANOSTI:
[VISOKA / SREDNJA / NISKA]""".strip()

_CLIENT: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI()
    return _CLIENT


def build_context(docs: list[str]) -> str:
    if not docs:
        return "NEMA PRONADJENOG KONTEKSTA."
    separator = "\n\n" + ("─" * 80) + "\n\n"
    return "\n\n" + separator.join(docs)


def answer_question(question: str) -> str:
    if not question or not question.strip():
        return _no_context_response("Pitanje je prazno.")
    docs = retrieve_documents(question, k=TOP_K_FINAL)
    context = build_context(docs)
    if not docs:
        return _no_context_response("Nije pronadjen relevantan zakonski tekst.")
    user_prompt = f"PITANJE: {question.strip()}\n\nKONTEKST:\n{context}\n\nOdgovori iskljucivo na osnovu konteksta."
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
        return content.strip() if content else _no_context_response("Model nije vratio sadrzaj.")
    except Exception as e:
        print(f"[LLM_ERROR] {e}")
        return _no_context_response(f"Greska: {e}")


def _no_context_response(reason: str) -> str:
    return f"""PRAVNI OSNOV:
Nije direktno potvrdeno u dostavljenom kontekstu.

ODGOVOR:
{reason}

CITAT IZ ZAKONA:
Nije pronadjen.

PRAVNA POSLEDICA:
Nije moguce pouzdano zakljuciti.

NAPOMENA O POUZDANOSTI:
NISKA""".strip()