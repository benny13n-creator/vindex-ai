from pathlib import Path
import re
from typing import Optional, List, Any, Tuple

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
VECTOR_STORE_DIR = BASE_DIR / "vector_store"

EMBEDDING_MODEL = "text-embedding-3-large"

LAW_HINTS = {
    "rad": "zakon o radu",
    "radni odnos": "zakon o radu",
    "otkaz": "zakon o radu",
    "zarada": "zakon o radu",
    "porodic": "porodicni zakon",
    "brak": "porodicni zakon",
    "razvod": "porodicni zakon",
    "dete": "porodicni zakon",
    "aliment": "porodicni zakon",
    "krivic": "krivicni zakonik",
    "krivicni": "krivicni zakonik",
    "krivicno": "krivicni zakonik",
    "krivicni postupak": "zakonik o krivicnom postupku",
    "parnic": "zakon o parnicnom postupku",
    "parnica": "zakon o parnicnom postupku",
    "tuzba": "zakon o parnicnom postupku",
    "presuda": "zakon o parnicnom postupku",
    "izvrs": "zakon o izvrsenju i obezbedjenju",
    "izvrsenje": "zakon o izvrsenju i obezbedjenju",
    "obezbedjenj": "zakon o izvrsenju i obezbedjenju",
    "obligaci": "zakon o obligacionim odnosima",
    "steta": "zakon o obligacionim odnosima",
    "naknada": "zakon o obligacionim odnosima",
    "ugovor": "zakon o obligacionim odnosima",
    "zastarel": "zakon o obligacionim odnosima",
    "privredn": "zakon o privrednim drustvima",
    "drustv": "zakon o privrednim drustvima",
    "upravni spor": "zakon o upravnim sporovima",
    "upravnom sporu": "zakon o upravnim sporovima",
    "upravni postupak": "zakon o opstem upravnom postupku",
    "upravnog postupka": "zakon o opstem upravnom postupku",
    "vanparnic": "zakon o vanparnicnom postupku",
    "nasledj": "zakon o nasledjivanju",
    "ostavina": "zakon o nasledjivanju",
    "ustav": "ustav republike srbije",
    "potrosac": "zakon o zastiti potrosaca",
    "potroša": "zakon o zastiti potrosaca",
}

STOPWORDS = {
    "koji", "koja", "koje", "kako", "kada", "zasto", "sta", "gde",
    "da", "li", "se", "su", "je", "u", "na", "po", "za", "od", "do",
    "i", "ili", "a", "ali", "te", "uz", "kod", "sa", "bez", "prema",
    "ovo", "onaj", "ovaj", "taj", "njih", "njegov", "njen", "moze",
    "mogu", "ima", "imaju", "biti", "bio", "bila", "bilo", "nisu",
    "jeste", "nije", "clan", "član", "zakon", "stav", "tačka", "tacka"
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
    replacements = {
        "š": "s",
        "đ": "dj",
        "č": "c",
        "ć": "c",
        "ž": "z",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def tokenize_query(query: str) -> List[str]:
    q = normalize(query)
    tokens = re.findall(r"[a-z0-9]+", q)
    cleaned = []
    for token in tokens:
        if len(token) < 3:
            continue
        if token in STOPWORDS:
            continue
        cleaned.append(token)
    return cleaned


def guess_law(query: str) -> Optional[str]:
    q = normalize(query)
    ordered = sorted(LAW_HINTS.items(), key=lambda x: len(x[0]), reverse=True)

    for keyword, law_name in ordered:
        if normalize(keyword) in q:
            return law_name

    return None


def extract_article_number(query: str) -> Optional[str]:
    q = query.lower()

    patterns = [
        r"(?:član|clan)\s*(\d+[a-zA-Z]?)",
        r"(?:чл\.?|cl\.)\s*(\d+[a-zA-Z]?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            return match.group(1)

    return None


def build_article_label(article_number: Optional[str]) -> Optional[str]:
    if not article_number:
        return None
    return f"Član {article_number}"


def make_doc(doc_text: str, metadata: dict) -> Any:
    doc_obj = type("Doc", (), {})()
    doc_obj.page_content = doc_text
    doc_obj.metadata = metadata or {}
    return doc_obj


def unique_docs(docs: List[Any]) -> List[Any]:
    seen = set()
    unique = []

    for doc in docs:
        meta = doc.metadata or {}
        law = normalize(meta.get("law", ""))
        article = normalize(meta.get("article", ""))
        text_key = normalize(doc.page_content[:600])
        key = (law, article, text_key)

        if key not in seen:
            seen.add(key)
            unique.append(doc)

    return unique


def format_doc(doc: Any) -> str:
    metadata = doc.metadata or {}
    law = metadata.get("law", "Nepoznat zakon")
    article = metadata.get("article", "Nepoznat član")
    text = doc.page_content.strip()

    return f"""ZAKON: {law}
ČLAN: {article}

{text}
"""


def build_query_variations(
    query: str,
    guessed_law: Optional[str],
    article_label: Optional[str],
) -> List[str]:
    qn = normalize(query)
    tokens = tokenize_query(query)
    token_str = " ".join(tokens[:8]) if tokens else query

    variations = [query]

    if token_str and token_str != query:
        variations.append(token_str)

    if guessed_law:
        variations.append(f"{query} {guessed_law}")
        variations.append(f"{token_str} {guessed_law}")

    if article_label:
        variations.append(f"{article_label}")
        variations.append(f"{article_label} {query}")
        if guessed_law:
            variations.append(f"{article_label} {guessed_law}")
            variations.append(f"{article_label} {guessed_law} {token_str}")

    if "nematerijal" in qn and "stet" in qn:
        variations.append("nematerijalna steta zakon o obligacionim odnosima")
        variations.append("dusevni bol pretrpljeni strah umanjenje zivotne aktivnosti zakon o obligacionim odnosima")
        variations.append("naknada nematerijalne stete clan 200 zakon o obligacionim odnosima")

    if "otkaz" in qn and "rad" in qn:
        variations.append("otkaz ugovora o radu zakon o radu")
        variations.append("povreda radne obaveze zakon o radu")

    if "zastarel" in qn:
        variations.append("zastarelost potrazivanja zakon o obligacionim odnosima")

    deduped = []
    seen = set()

    for v in variations:
        key = normalize(v)
        if key not in seen:
            seen.add(key)
            deduped.append(v)

    return deduped


def direct_article_fetch(
    db: Chroma,
    article_label: Optional[str],
    guessed_law: Optional[str],
) -> List[Any]:
    if not article_label:
        return []

    collected = []

    try:
        if guessed_law:
            results = db.get(
                where={
                    "$and": [
                        {"article": article_label},
                        {"law": guessed_law},
                    ]
                }
            )
        else:
            results = db.get(where={"article": article_label})

        if results and results.get("documents"):
            for doc_text, meta in zip(results["documents"], results["metadatas"]):
                collected.append(make_doc(doc_text, meta))

    except Exception as e:
        print(f"[DIRECT_FETCH_ERROR] {e}")

    return collected


def priority_fetch(
    db: Chroma,
    query: str,
) -> List[Any]:
    qn = normalize(query)
    collected = []

    try:
        if "nematerijal" in qn and "stet" in qn:
            results = db.get(where={"law": "zakon o obligacionim odnosima"})

            if results and results.get("documents"):
                for doc_text, meta in zip(results["documents"], results["metadatas"]):
                    text_norm = normalize(doc_text)

                    if (
                        "nematerijalna steta" in text_norm
                        or "dusevni bol" in text_norm
                        or "fizicki bol" in text_norm
                        or "pretrpljeni strah" in text_norm
                        or "strah" in text_norm
                        or "umanjenje zivotne aktivnosti" in text_norm
                    ):
                        collected.append(make_doc(doc_text, meta))

    except Exception as e:
        print(f"[PRIORITY_FETCH_ERROR] {e}")

    return collected


def semantic_fetch(
    db: Chroma,
    query_variations: List[str],
    per_query_k: int = 8,
) -> List[Any]:
    collected = []

    for qv in query_variations:
        try:
            docs = db.similarity_search(qv, k=per_query_k)
            if docs:
                collected.extend(docs)
        except Exception as e:
            print(f"[SIMILARITY_FETCH_ERROR] {qv} -> {e}")

    return collected


def compute_doc_score(
    query: str,
    doc: Any,
    guessed_law: Optional[str],
    article_label: Optional[str],
) -> float:
    score = 0.0

    meta = doc.metadata or {}
    doc_law = normalize(meta.get("law", ""))
    doc_article = normalize(meta.get("article", ""))
    text = normalize(doc.page_content)

    qn = normalize(query)
    query_tokens = tokenize_query(query)

    # zakon
    if guessed_law:
        gl = normalize(guessed_law)
        if gl == doc_law:
            score += 35
        elif gl in doc_law:
            score += 24

    # član
    if article_label:
        al = normalize(article_label)
        if al == doc_article:
            score += 60
        elif al in doc_article:
            score += 45
        elif al in text:
            score += 20

    # token hits
    token_hits = 0
    for token in query_tokens:
        if token in text:
            token_hits += 1
    score += min(token_hits * 4, 32)

    # korisne fraze
    important_phrases = [
        "nematerijalna steta",
        "dusevni bol",
        "fizicki bol",
        "pretrpljeni strah",
        "umanjenje zivotne aktivnosti",
        "zastarelost",
        "naknada stete",
        "otkaz ugovora o radu",
        "povreda radne obaveze",
        "rok za zalbu",
        "zabluda",
        "prevara",
        "raskid ugovora",
    ]

    for phrase in important_phrases:
        if phrase in qn and phrase in text:
            score += 10

    # jaka pravila za nematerijalnu štetu
    if "nematerijal" in qn and "stet" in qn:
        if "nematerijalna steta" in text:
            score += 80
        if "dusevni bol" in text:
            score += 50
        if "fizicki bol" in text:
            score += 40
        if "pretrpljeni strah" in text:
            score += 50
        elif "strah" in text:
            score += 35
        if "umanjenje zivotne aktivnosti" in text:
            score += 50

        if doc_law == "zakon o obligacionim odnosima":
            score += 30
        else:
            score -= 40

        if doc_article == normalize("Član 200"):
            score += 120

    # blagi bonus ako postoji article metadata
    if doc_article:
        score += 2

    # penal za očigledan promašaj teme
    if "nematerijal" in qn and "nematerijal" not in text:
        score -= 12

    if "stet" in qn and "stet" not in text:
        score -= 10

    if "otkaz" in qn and "otkaz" not in text:
        score -= 12

    if "zastarel" in qn and "zastarel" not in text:
        score -= 12

    return score


def rank_docs(
    query: str,
    docs: List[Any],
    guessed_law: Optional[str],
    article_label: Optional[str],
) -> List[Any]:
    scored: List[Tuple[float, Any]] = []

    for doc in docs:
        s = compute_doc_score(query, doc, guessed_law, article_label)
        scored.append((s, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored]


def retrieve_article_raw(query: str):
    db = get_db()
    qn = normalize(query)

    # prioritet za nematerijalnu štetu
    if "nematerijal" in qn and "stet" in qn:
        try:
            results = db.get(
                where={
                    "$and": [
                        {"law": "zakon o obligacionim odnosima"},
                        {"article": "Član 200"},
                    ]
                }
            )

            if results and results.get("documents"):
                return {
                    "law": results["metadatas"][0].get("law", "Nepoznat zakon"),
                    "article": results["metadatas"][0].get("article", "Član 200"),
                    "text": results["documents"][0],
                }

        except Exception as e:
            print(f"[PRIORITY_200_ERROR] {e}")

    article_number = extract_article_number(query)
    if not article_number:
        return None

    article_label = build_article_label(article_number)
    guessed_law = guess_law(query)

    docs = direct_article_fetch(db, article_label, guessed_law)
    if not docs:
        return None

    best = docs[0]
    return {
        "law": best.metadata.get("law", "Nepoznat zakon"),
        "article": best.metadata.get("article", article_label),
        "text": best.page_content,
    }


def retrieve_documents(query: str, k: int = 5) -> List[str]:
    db = get_db()

    guessed_law = guess_law(query)
    article_number = extract_article_number(query)
    article_label = build_article_label(article_number)

    collected_docs: List[Any] = []

    # 0) priority fetch
    collected_docs.extend(priority_fetch(db, query))

    # 1) direktno gađanje člana
    collected_docs.extend(direct_article_fetch(db, article_label, guessed_law))

    # 2) semantic fetch kroz više varijacija
    query_variations = build_query_variations(query, guessed_law, article_label)
    collected_docs.extend(
        semantic_fetch(
            db,
            query_variations,
            per_query_k=max(k * 3, 10),
        )
    )

    # 3) dedupe
    collected_docs = unique_docs(collected_docs)

    # 4) rerank
    ranked_docs = rank_docs(query, collected_docs, guessed_law, article_label)

    # 5) final
    return [format_doc(doc) for doc in ranked_docs[:k]]