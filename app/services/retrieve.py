from pathlib import Path
import re
from typing import Optional, List, Any, Tuple

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

BASE_DIR = Path(__file__).resolve().parents[2]
VECTOR_STORE_DIR = BASE_DIR / "vector_store"

LAW_KEYWORDS = {
    "rad": "zakon o radu",
    "porodic": "porodicni zakon",
    "krivic": "krivicni zakonik",
    "parnic": "zakon o parnicnom postupku",
    "izvrs": "zakon o izvrsenju i obezbedjenju",
    "obligaci": "zakon o obligacionim odnosima",
    "privredn": "zakon o privrednim drustvima",
    "uprav": "zakon o opstem upravnom postupku",
    "vanparnic": "zakon o vanparnicnom postupku",
    "nasledj": "zakon o nasledjivanju",
    "ustav": "ustav republike srbije",
    "zastit": "zakon o zastiti potrosaca",
}

STOPWORDS = {
    "koji", "koja", "koje", "kako", "kada", "zasto", "sta", "gde",
    "da", "li", "se", "su", "je", "u", "na", "po", "za", "od", "do",
    "i", "ili", "a", "ali", "te", "uz", "kod", "sa", "bez", "prema",
    "ovo", "onaj", "ovaj", "taj", "njih", "njegov", "njen", "moze",
    "mogu", "ima", "imaju", "biti", "bio", "bila", "bilo", "nisu",
    "jeste", "nije", "clan", "član", "zakon"
}

_DB: Optional[Chroma] = None


# ===============================
# DB
# ===============================
def get_db() -> Chroma:
    global _DB
    if _DB is not None:
        return _DB

   OpenAIEmbeddings(model="text-embedding-3-large")
    _DB = Chroma(
        persist_directory=str(VECTOR_STORE_DIR),
        embedding_function=embeddings,
    )
    return _DB


# ===============================
# UTILS
# ===============================
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


def guess_law(query: str) -> Optional[str]:
    q = normalize(query)
    for keyword, law_name in LAW_KEYWORDS.items():
        if keyword in q:
            return law_name
    return None


def extract_article_number(query: str) -> Optional[str]:
    match = re.search(r"(?:član|clan)\s*(\d+[a-zA-Z]?)", query.lower())
    if match:
        return match.group(1)
    return None


def build_article_label(article_number: Optional[str]) -> Optional[str]:
    if not article_number:
        return None
    return f"Član {article_number}"


def tokenize_query(query: str) -> List[str]:
    q = normalize(query)
    tokens = re.findall(r"[a-zA-Z0-9čćžšđ]+", q)
    cleaned = []
    for t in tokens:
        if len(t) < 3:
            continue
        if t in STOPWORDS:
            continue
        cleaned.append(t)
    return cleaned


def unique_docs(docs: List[Any]) -> List[Any]:
    seen = set()
    result = []

    for doc in docs:
        meta = doc.metadata or {}
        key = (
            meta.get("law", ""),
            meta.get("article", ""),
            normalize(doc.page_content[:300])
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(doc)

    return result


def format_doc(doc: Any) -> str:
    law = doc.metadata.get("law", "Nepoznat zakon")
    article = doc.metadata.get("article", "Nepoznat član")
    text = doc.page_content

    return f"""ZAKON: {law}
ČLAN: {article}

{text}
"""


# ===============================
# QUERY ROUTER
# ===============================
def route_query(query: str) -> str:
    q = normalize(query)

    if "nematerijal" in q and "stet" in q:
        return "nematerijalna_steta"

    if "otkaz" in q and "rad" in q:
        return "otkaz_rada"

    if "zastarel" in q:
        return "zastarelost"

    return "default"


# ===============================
# SPECIAL HANDLERS
# ===============================
def handle_nematerijalna_steta(db: Chroma) -> List[str]:
    docs = db.similarity_search(
        "nematerijalna steta dusevni bol strah umanjenje zivotne aktivnosti zakon o obligacionim odnosima",
        k=20,
    )

    docs = [
        d for d in docs
        if any(x in normalize(d.page_content) for x in [
            "nematerijal",
            "dusevni bol",
            "strah",
            "zivotne aktivnosti",
            "umanjenje zivotne aktivnosti",
        ])
    ]

    docs = unique_docs(docs)
    if docs:
        return [format_doc(docs[0])]
    return []


def handle_otkaz_rada(db: Chroma) -> List[str]:
    docs = db.similarity_search(
        "otkaz ugovora o radu povreda radne obaveze zakon o radu",
        k=15,
    )
    docs = unique_docs(docs)
    if docs:
        return [format_doc(docs[0])]
    return []


# ===============================
# QUERY VARIATIONS
# ===============================
def build_query_variations(query: str, guessed_law: Optional[str], article_label: Optional[str]) -> List[str]:
    variations = [query]

    if guessed_law:
        variations.append(f"{query} {guessed_law}")

    if article_label:
        variations.append(f"{article_label} {query}")
        if guessed_law:
            variations.append(f"{article_label} {guessed_law}")

    qn = normalize(query)

    if "nematerijalna steta" in qn or ("nematerijal" in qn and "stet" in qn):
        variations.append("nematerijalna steta zakon o obligacionim odnosima")
        variations.append("dusevni bol strah umanjenje zivotne aktivnosti zakon o obligacionim odnosima")

    if "otkaz ugovora o radu" in qn or ("otkaz" in qn and "rad" in qn):
        variations.append("otkaz ugovora o radu zakon o radu")
        variations.append("povreda radne obaveze zakon o radu")

    deduped = []
    seen = set()
    for v in variations:
        key = normalize(v)
        if key not in seen:
            seen.add(key)
            deduped.append(v)

    return deduped


# ===============================
# SCORING LAYER
# ===============================
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

    # 1) Zakon
    if guessed_law:
        if normalize(guessed_law) == doc_law:
            score += 40
        elif normalize(guessed_law) in doc_law:
            score += 28

    # 2) Član
    if article_label:
        normalized_article = normalize(article_label)
        if normalized_article == doc_article:
            score += 60
        elif normalized_article in doc_article:
            score += 45
        elif normalized_article in text:
            score += 25

    # 3) Pogodak query tokena
    token_hits = 0
    for token in query_tokens:
        if token in text:
            token_hits += 1

    score += min(token_hits * 4, 28)

    # 4) Fraze visokog značaja
    high_value_phrases = [
        "nematerijalna steta",
        "dusevni bol",
        "fizicki bol",
        "pretrpljeni strah",
        "umanjenje zivotne aktivnosti",
        "zastarelost",
        "otkaz ugovora o radu",
        "povreda radne obaveze",
        "naknada stete",
    ]

    for phrase in high_value_phrases:
        if phrase in qn and phrase in text:
            score += 12

    # 5) Penal za očigledan promašaj materije
    if "nematerijal" in qn and "nematerijal" not in text:
        score -= 18

    if "stet" in qn and "stet" not in text:
        score -= 12

    if "otkaz" in qn and "otkaz" not in text:
        score -= 14

    if "zastarel" in qn and "zastarel" not in text:
        score -= 14

    # 6) Blagi bonus ako se naziv zakona pominje i u samom tekstu
    if guessed_law and normalize(guessed_law) in text:
        score += 6

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


# ===============================
# RAW ARTICLE FETCH
# ===============================
def retrieve_article_raw(query: str):
    db = get_db()
   query_norm = normalize(query)

# 🔥 PRIORITY: nematerijalna šteta → član 200 ZOO
if "nematerijal" in query_norm and "stet" in query_norm:
    try:
        results = db.get(
            where={
                "$and": [
                    {"law": "zakon o obligacionim odnosima"},
                    {"article": "Član 200"}
                ]
            }
        )

        if results and results.get("documents"):
            doc_obj = type("Doc", (), {})()
            doc_obj.page_content = results["documents"][0]
            doc_obj.metadata = results["metadatas"][0]

            return [format_doc(doc_obj)]

    except Exception as e:
        print(f"[PRIORITY_200 ERROR] {e}") 

    article_number = extract_article_number(query)
    if not article_number:
        return None

    target_article = f"Član {article_number}"
    law_name = guess_law(query)

    try:
        if law_name:
            results = db.get(
                where={
                    "$and": [
                        {"article": target_article},
                        {"law": law_name},
                    ]
                }
            )
        else:
            results = db.get(where={"article": target_article})

        if results and results.get("documents"):
            return {
                "law": results["metadatas"][0].get("law", "Nepoznat zakon"),
                "article": results["metadatas"][0].get("article", target_article),
                "text": results["documents"][0],
            }

    except Exception as e:
        print(f"[RETRIEVE_RAW] Greška: {e}")

    return None


# ===============================
# MAIN RETRIEVAL
# ===============================
def retrieve_documents(query: str, k: int = 5) -> List[str]:
    db = get_db()

    # 0) Router
    route = route_query(query)

    if route == "nematerijalna_steta":
        result = handle_nematerijalna_steta(db)
        if result:
            return result

    if route == "otkaz_rada":
        result = handle_otkaz_rada(db)
        if result:
            return result

    # 1) Osnovni signali
    guessed_law = guess_law(query)
    article_number = extract_article_number(query)
    article_label = build_article_label(article_number)

    collected_docs: List[Any] = []

    # 2) Direktno gađanje člana
    if article_label:
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
                    doc_obj = type("Doc", (), {})()
                    doc_obj.page_content = doc_text
                    doc_obj.metadata = meta
                    collected_docs.append(doc_obj)

        except Exception as e:
            print(f"[RETRIEVE][DIRECT] Greška: {e}")

    # 3) Query variations
    query_variations = build_query_variations(query, guessed_law, article_label)

    for qv in query_variations:
        try:
            docs = db.similarity_search(qv, k=max(k * 3, 10))
            collected_docs.extend(docs)
        except Exception as e:
            print(f"[RETRIEVE][SIMILARITY] Greška za query '{qv}': {e}")

    # 4) Keyword boost
    keyword_map = {
        "nematerijalna": "nematerijalna steta",
        "nematerijalne": "nematerijalna steta",
        "dusevni bol": "dusevni bol",
        "fizicki bol": "fizicki bol",
        "strah": "pretrpljeni strah",
        "naknada stete": "naknada stete",
        "zastarelost": "zastarelost potrazivanja",
        "otkaz": "otkaz ugovora o radu",
        "otkazni rok": "otkazni rok",
    }

    query_norm = normalize(query)
    for keyword, search_term in keyword_map.items():
        if keyword in query_norm:
            try:
                boost_docs = db.similarity_search(search_term, k=3)
                if boost_docs:
                    collected_docs.extend(boost_docs)
            except Exception as e:
                print(f"[RETRIEVE][KEYWORD_BOOST] Greška za '{keyword}': {e}")

    # 5) Dedupe
    collected_docs = unique_docs(collected_docs)

    # 6) Rank
    ranked_docs = rank_docs(query, collected_docs, guessed_law, article_label)

    # 7) Final output
    return [format_doc(doc) for doc in ranked_docs[:k]]