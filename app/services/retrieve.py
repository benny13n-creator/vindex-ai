from pathlib import Path
import re
import os
from typing import Optional, List, Any, Tuple

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI
from pinecone import Pinecone

load_dotenv()

EMBEDDING_MODEL = "text-embedding-3-large"
PINECONE_INDEX = "vindex-ai"

LAW_HINTS = {
    "rad": "zakon o radu",
    "radni odnos": "zakon o radu",
    "otkaz": "zakon o radu",
    "zarada": "zakon o radu",
    "prestanak radnog odnosa": "zakon o radu",
    "tehnoloski visak": "zakon o radu",
    "visak zaposlenih": "zakon o radu",
    "disciplinska": "zakon o radu",
    "porodic": "porodicni zakon",
    "brak": "porodicni zakon",
    "razvod": "porodicni zakon",
    "dete": "porodicni zakon",
    "aliment": "porodicni zakon",
    "staratelj": "porodicni zakon",
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
    "izgubljena dobit": "zakon o obligacionim odnosima",
    "izmakla korist": "zakon o obligacionim odnosima",
    "imovinska steta": "zakon o obligacionim odnosima",
    "privredn": "zakon o privrednim drustvima",
    "drustv": "zakon o privrednim drustvima",
    "upravni spor": "zakon o upravnim sporovima",
    "upravni postupak": "zakon o opstem upravnom postupku",
    "vanparnic": "zakon o vanparnicnom postupku",
    "nasledj": "zakon o nasledjivanju",
    "ostavina": "zakon o nasledjivanju",
    "ustav": "ustav republike srbije",
    "potrosac": "zakon o zastiti potrosaca",
}

STOPWORDS = {
    "koji", "koja", "koje", "kako", "kada", "zasto", "sta", "gde",
    "da", "li", "se", "su", "je", "u", "na", "po", "za", "od", "do",
    "i", "ili", "a", "ali", "te", "uz", "kod", "sa", "bez", "prema",
    "ovo", "onaj", "ovaj", "taj", "njih", "njegov", "njen", "moze",
    "mogu", "ima", "imaju", "biti", "bio", "bila", "bilo", "nisu",
    "jeste", "nije", "clan", "zakon", "stav", "tacka"
}

_PINECONE_INDEX = None
_EMBEDDINGS = None
_CLIENT = None

def get_pinecone_index():
    global _PINECONE_INDEX
    if _PINECONE_INDEX is not None:
        return _PINECONE_INDEX
    api_key = os.getenv("PINECONE_API_KEY")
    pc = Pinecone(api_key=api_key)
    _PINECONE_INDEX = pc.Index(PINECONE_INDEX)
    print("Pinecone index povezan!")
    return _PINECONE_INDEX

def get_embeddings():
    global _EMBEDDINGS
    if _EMBEDDINGS is None:
        _EMBEDDINGS = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return _EMBEDDINGS

def get_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI()
    return _CLIENT

def normalize(text: str) -> str:
    text = (text or "").lower()
    replacements = {"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z"}
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text

def tokenize_query(query: str) -> List[str]:
    q = normalize(query)
    tokens = re.findall(r"[a-z0-9]+", q)
    return [t for t in tokens if len(t) >= 3 and t not in STOPWORDS]

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
        r"(?:чл.?|cl.)\s*(\d+[a-zA-Z]?)",
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

def expand_query_with_gpt(query: str) -> List[str]:
    """GPT proširuje query sa pravnim terminima za bolji semantic search."""
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            max_tokens=200,
            messages=[
                {
                    "role": "system",
                    "content": """Ti si ekspert za srpsko pravo.
Za dato pitanje generiši 4 kratka search query-ja (3-7 reči svaki)
koji će pronaći relevantne članove zakona.
Koristi pravne termine iz srpskih zakona.
Vrati SAMO query-je, jedan po liniji, bez numeracije."""
                },
                {"role": "user", "content": f"Pitanje: {query}"}
            ]
        )
        result = response.choices[0].message.content.strip()
        expanded = [q.strip() for q in result.split('\n') if q.strip()]
        print(f"[GPT_EXPANSION] {expanded}")
        return expanded[:4]
    except Exception as e:
        print(f"[GPT_EXPANSION_ERROR] {e}")
        return []

def embed_query(query: str) -> List[float]:
    """Konvertuje query u embedding vektor."""
    emb = get_embeddings()
    return emb.embed_query(query)

def pinecone_search(query: str, k: int = 10, law_filter: Optional[str] = None) -> List[dict]:
    """Semantic search u Pinecone."""
    index = get_pinecone_index()
    vector = embed_query(query)

    filter_dict = None
    if law_filter:
        filter_dict = {"law": {"$eq": law_filter}}

    try:
        results = index.query(
            vector=vector,
            top_k=k,
            include_metadata=True,
            filter=filter_dict,
        )
        return results.get("matches", [])
    except Exception as e:
        print(f"[PINECONE_SEARCH_ERROR] {e}")
        return []

def pinecone_fetch_article(article_label: str, law: Optional[str] = None) -> List[dict]:
    """Direktno pretražuje po metadati člana."""
    index = get_pinecone_index()

    filter_dict = {"article": {"$eq": article_label}}
    if law:
        filter_dict = {"$and": [{"article": {"$eq": article_label}}, {"law": {"$eq": law}}]}

    try:
        # Koristimo dummy vektor za metadata-only search
        dummy_vector = [0.0] * 3072
        results = index.query(
            vector=dummy_vector,
            top_k=5,
            include_metadata=True,
            filter=filter_dict,
        )
        return results.get("matches", [])
    except Exception as e:
        print(f"[PINECONE_FETCH_ERROR] {e}")
        return []

def format_match(match: dict) -> str:
    meta = match.get("metadata", {})
    law = meta.get("law", "Nepoznat zakon")
    article = meta.get("article", "Nepoznat član")
    text = meta.get("text", "").strip()
    return f"""ZAKON: {law}
ČLAN: {article}

{text}
"""

def compute_score(match: dict, query: str, guessed_law: Optional[str], article_label: Optional[str]) -> float:
    """Reranking skor na osnovu Pinecone score + metadata bonus."""
    base_score = match.get("score", 0.0) * 100
    meta = match.get("metadata", {})
    doc_law = normalize(meta.get("law", ""))
    doc_article = normalize(meta.get("article", ""))
    text = normalize(meta.get("text", ""))
    qn = normalize(query)

    # Bonus za tačan zakon
    if guessed_law:
        gl = normalize(guessed_law)
        if gl == doc_law:
            base_score += 30
        elif gl in doc_law:
            base_score += 15

    # Bonus za tačan član
    if article_label:
        al = normalize(article_label)
        if al == doc_article:
            base_score += 50
        elif al in doc_article:
            base_score += 30

    # Token hits
    tokens = tokenize_query(query)
    token_hits = sum(1 for t in tokens if t in text)
    base_score += min(token_hits * 3, 20)

    # Specijalni boost za nematerijalnu štetu
    if "nematerijal" in qn and "stet" in qn:
        if "nematerijalna steta" in text:
            base_score += 50
        if "obligacion" in doc_law:
            base_score += 20
        if "200" in doc_article and "obligacion" in doc_law:
            base_score += 80

    return base_score

def retrieve_documents(query: str, k: int = 6) -> List[str]:
    """Glavni retrieval pipeline koristeći Pinecone."""
    guessed_law = guess_law(query)
    article_number = extract_article_number(query)
    article_label = build_article_label(article_number)

    all_matches = []

    # 1) Direktno gađanje člana ako je naveden
    if article_label:
        matches = pinecone_fetch_article(article_label, guessed_law)
        all_matches.extend(matches)
        print(f"[DIRECT_FETCH] {len(matches)} rezultata za {article_label}")

    # 2) Semantic search sa originalnim queryjem
    matches = pinecone_search(query, k=12, law_filter=guessed_law)
    all_matches.extend(matches)

    # 3) Semantic search bez filtera (širi zahvat)
    matches = pinecone_search(query, k=8)
    all_matches.extend(matches)

    # 4) GPT Query Expansion
    expanded = expand_query_with_gpt(query)
    for eq in expanded:
        matches = pinecone_search(eq, k=6)
        all_matches.extend(matches)

    # 5) Dedupe po ID-u
    seen_ids = set()
    unique_matches = []
    for m in all_matches:
        if m["id"] not in seen_ids:
            seen_ids.add(m["id"])
            unique_matches.append(m)

    # 6) Rerank
    scored = [(compute_score(m, query, guessed_law, article_label), m) for m in unique_matches]
    scored.sort(key=lambda x: x[0], reverse=True)

    print(f"[RETRIEVE] Ukupno unique: {len(unique_matches)}, vracam top {k}")

    return [format_match(m) for _, m in scored[:k]]