from __future__ import annotations

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
        id="11eP6RrmdDcWfYvjWeh4UAsvtxOmLDumV",
        output=str(zip_path),
        quiet=False
    )
    if not zip_path.exists():
        print("Zip NIJE preuzet!")
        return
    print("Raspakujem...")
    VECTOR_STORE_DIR.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.namelist():
            filename = Path(member).name
            if filename:
                data = z.read(member)
                target = VECTOR_STORE_DIR / filename
                target.write_bytes(data)
    zip_path.unlink()
    print("Gotovo!")


preuzmi_vector_store()

LAW_KEYWORDS = {
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
}

STOPWORDS = {
    "koji", "koja", "koje", "kako", "kada", "da", "li", "se", "su",
    "je", "u", "na", "po", "za", "od", "do", "i", "ili", "a", "ali",
    "clan", "zakon", "srbije", "republike",
}

_DB = None


def get_db():
    global _DB
    if _DB is not None:
        return _DB
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    _DB = Chroma(
        persist_directory=str(VECTOR_STORE_DIR),
        embedding_function=embeddings,
    )
    return _DB


def normalize(text):
    text = (text or "").lower()
    for src, dst in [("š", "s"), ("đ", "dj"), ("č", "c"), ("ć", "c"), ("ž", "z")]:
        text = text.replace(src, dst)
    return text


def guess_law(query):
    q = normalize(query)
    for kw, law in LAW_KEYWORDS.items():
        if kw in q:
            return law
    return None


def tokenize(query):
    q = normalize(query)
    tokens = re.findall(r"[a-z0-9]+", q)
    return [t for t in tokens if len(t) >= 3 and t not in STOPWORDS]


def deduplicate(docs):
    seen = set()
    result = []
    for doc in docs:
        meta = getattr(doc, "metadata", {}) or {}
        content = getattr(doc, "page_content", "") or ""
        key = (meta.get("law", ""), meta.get("article", ""), content[:200])
        if key not in seen:
            seen.add(key)
            result.append(doc)
    return result


def format_doc(doc):
    metadata = getattr(doc, "metadata", {}) or {}
    text = (getattr(doc, "page_content", "") or "").strip()
    law = metadata.get("law", "Nepoznat zakon")
    article = metadata.get("article", "Nepoznat clan")
    return f"ZAKON: {law}\nCLAN: {article}\n\n{text}"


def score_doc(doc, query, guessed_law):
    score = 0.0
    meta = getattr(doc, "metadata", {}) or {}
    content = getattr(doc, "page_content", "") or ""
    doc_law = normalize(meta.get("law", ""))
    text = normalize(content)
    tokens = tokenize(query)
    if guessed_law:
        gn = normalize(guessed_law)
        if gn == doc_law:
            score += 50
        elif gn in doc_law:
            score += 35
    hits = sum(1 for t in tokens if t in text)
    score += min(hits * 5, 30)
    return score


def retrieve_documents(query, k=TOP_K_FINAL):
    db = get_db()
    guessed_law = guess_law(query)
    collected = []
    variations = [query]
    if guessed_law:
        variations.append(f"{query} {guessed_law}")
    for v in variations:
        try:
            docs = db.similarity_search(v, k=TOP_K_RETRIEVE)
            collected.extend(docs)
        except Exception as e:
            print(f"[SIMILARITY] {e}")
    collected = deduplicate(collected)
    scored = [(score_doc(d, query, guessed_law), d) for d in collected]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [d for _, d in scored[:k]]
    if not top:
        return []
    return [format_doc(d) for d in top]


SYSTEM_PROMPT = """Ti si strucni pravni AI asistent za advokate u Republici Srbiji.

PRAVILA:

1. Odgovaras ISKLJUCIVO na osnovu dostavljenog zakonskog konteksta.
1. ZABRANJENO: izmisljanje zakona, clanova ili pravnih posledica.
1. Ako odgovor NIJE u kontekstu, reci to jasno.
1. Navedi tacan naziv zakona i clana.

FORMAT ODGOVORA:

PRAVNI OSNOV:
[Zakon i clan koji direktno odgovara na pitanje]

ODGOVOR:
[Direktan i jasan odgovor]

CITAT IZ ZAKONA:
[Doslovan citat iz konteksta]

PRAVNA POSLEDICA:
[Ako jasno proizlazi iz teksta]

NAPOMENA O POUZDANOSTI:
[VISOKA / SREDNJA / NISKA]"""

_CLIENT = None


def get_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI()
    return _CLIENT


def build_context(docs):
    if not docs:
        return "NEMA KONTEKSTA."
    return "\n\n—\n\n".join(docs)


def answer_question(question):
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
        return content.strip() if content else _no_context_response("Greska.")
    except Exception as e:
        print(f"[LLM_ERROR] {e}")
        return _no_context_response(f"Greska: {e}")


def _no_context_response(reason):
    return f"""PRAVNI OSNOV:
Nije potvrdeno u dostavljenom kontekstu.

ODGOVOR:
{reason}

CITAT IZ ZAKONA:
Nije pronadjen.

PRAVNA POSLEDICA:
Nije moguce pouzdano zakljuciti.

NAPOMENA O POUZDANOSTI:
NISKA"""
