from pathlib import Path
import re
import gdown
import zipfile
import tempfile
import shutil
from typing import Optional, List, Any, Tuple

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
VECTOR_STORE_DIR = BASE_DIR / "vector_store"

EMBEDDING_MODEL = "text-embedding-3-large"
GDRIVE_FILE_ID = "11eP6RrmdDcWfYvjWeh4UAsvtxOmLDumV"

LAW_HINTS = {
    "rad": "zakon o radu",
    "radni odnos": "zakon o radu",
    "otkaz": "zakon o radu",
    "zarada": "zakon o radu",
    "prestanak radnog odnosa": "zakon o radu",
    "tehnoloski visak": "zakon o radu",
    "visak zaposlenih": "zakon o radu",
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
    "jeste", "nije", "clan", "član", "zakon", "stav", "tacka"
}

_DB: Optional[Chroma] = None
_CLIENT: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI()
    return _CLIENT


def _download_vector_store() -> None:
    if VECTOR_STORE_DIR.exists() and any(VECTOR_STORE_DIR.iterdir()):
        print("Vector store vec postoji.")
        return

    print("Preuzimam bazu zakona...")
    zip_path = BASE_DIR / "vector_store.zip"

    try:
        if zip_path.exists():
            zip_path.unlink()

        downloaded = gdown.download(
            id=GDRIVE_FILE_ID,
            output=str(zip_path),
            quiet=False,
            fuzzy=False,
        )

        if not downloaded or not zip_path.exists():
            raise RuntimeError("Zip nije preuzet.")

        print("Raspakujem vector store...")
        temp_dir = Path(tempfile.mkdtemp())

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(temp_dir)

        vector_store_src = None
        for p in temp_dir.rglob("vector_store"):
            if p.is_dir():
                vector_store_src = p
                break

        if vector_store_src is None:
            if (temp_dir / "chroma.sqlite3").exists():
                vector_store_src = temp_dir

        if vector_store_src is None:
            raise RuntimeError("vector_store nije pronađen u zip arhivi.")

        if VECTOR_STORE_DIR.exists():
            shutil.rmtree(VECTOR_STORE_DIR, ignore_errors=True)

        if vector_store_src == temp_dir:
            VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
            for item in temp_dir.iterdir():
                if item.name == zip_path.name:
                    continue
                target = VECTOR_STORE_DIR / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)
        else:
            shutil.move(str(vector_store_src), str(VECTOR_STORE_DIR))

        print("Vector store uspesno pripremljen!")

    except Exception as e:
        print(f"[DOWNLOAD_ERROR] {e}")

    finally:
        if zip_path.exists():
            zip_path.unlink()
        if 'temp_dir' in locals():
            shutil.rmtree(temp_dir, ignore_errors=True)


def get_db() -> Chroma:
    global _DB
    if _DB is not None:
        return _DB

    _download_vector_store()

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    _DB = Chroma(
        persist_directory=str(VECTOR_STORE_DIR),
        embedding_function=embeddings,
    )
    return _DB


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


def expand_query_with_gpt(query: str) -> List[str]:
    """
    Koristi GPT da proširi query sa pravnim terminima.
    Ovo omogućava semantic search da pronađe relevantne članove
    čak i kada pitanje ne sadrži tačne pravne termine.
    """
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            max_tokens=300,
            messages=[
                {
                    "role": "system",
                    "content": """Ti si ekspert za srpsko pravo.
Tvoj zadatak je da za dato pravno pitanje generišeš 5 kratkih search query-ja
koji će pomoći u pronalaženju relevantnih članova zakona u bazi podataka.

PRAVILA:

- Svaki query treba biti kratak (3-8 reči)
- Koristi pravne termine koji se nalaze u zakonima
- Uključi naziv relevantnog zakona ako ga znaš
- Koristi srpski jezik
- Vrati SAMO listu query-ja, jedan po liniji, bez numeracije i objašnjenja"""
                },
                {
                    "role": "user",
                    "content": f"Pitanje: {query}"
                }
            ]
        )

        result = response.choices[0].message.content.strip()
        expanded = [q.strip() for q in result.split('\n') if q.strip()]
        print(f"[QUERY_EXPANSION] Original: {query}")
        print(f"[QUERY_EXPANSION] Expanded: {expanded}")
        return expanded[:5]

    except Exception as e:
        print(f"[QUERY_EXPANSION_ERROR] {e}")
        return []


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
                where={"$and": [{"article": article_label}, {"law": guessed_law}]}
            )
        else:
            results = db.get(where={"article": article_label})

        if results and results.get("documents"):
            for doc_text, meta in zip(results["documents"], results["metadatas"]):
                collected.append(make_doc(doc_text, meta))
    except Exception as e:
        print(f"[DIRECT_FETCH_ERROR] {e}")
    return collected


def priority_fetch(db: Chroma, query: str) -> List[Any]:
    qn = normalize(query)
    collected = []
    try:
        if "nematerijal" in qn and "stet" in qn:
            results = db.get(where={"law": "zakon o obligacionim odnosima"})
            if results and results.get("documents"):
                for doc_text, meta in zip(results["documents"], results["metadatas"]):
                    text_norm = normalize(doc_text)
                    if any(x in text_norm for x in [
                        "nematerijalna steta", "dusevni bol", "fizicki bol",
                        "pretrpljeni strah", "umanjenje zivotne aktivnosti"
                    ]):
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

    if guessed_law:
        gl = normalize(guessed_law)
        if gl == doc_law:
            score += 35
        elif gl in doc_law:
            score += 24

    if article_label:
        al = normalize(article_label)
        if al == doc_article:
            score += 60
        elif al in doc_article:
            score += 45
        elif al in text:
            score += 20

    token_hits = sum(1 for token in query_tokens if token in text)
    score += min(token_hits * 4, 32)

    important_phrases = [
        "nematerijalna steta", "dusevni bol", "fizicki bol",
        "pretrpljeni strah", "umanjenje zivotne aktivnosti",
        "zastarelost", "naknada stete", "otkaz ugovora o radu",
        "povreda radne obaveze", "prestanak radnog odnosa",
        "tehnoloski visak", "izgubljena dobit", "izmakla korist",
    ]
    for phrase in important_phrases:
        if phrase in qn and phrase in text:
            score += 10

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

    if doc_article:
        score += 2

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


def retrieve_documents(query: str, k: int = 5) -> List[str]:
    db = get_db()

    guessed_law = guess_law(query)
    article_number = extract_article_number(query)
    article_label = build_article_label(article_number)

    collected_docs: List[Any] = []

    # 0) Priority fetch za specijalne slučajeve
    collected_docs.extend(priority_fetch(db, query))

    # 1) Direktno gađanje člana ako je naveden
    collected_docs.extend(direct_article_fetch(db, article_label, guessed_law))

    # 2) Originalni query + keyword varijacije
    base_variations = [query]
    if guessed_law:
        base_variations.append(f"{query} {guessed_law}")
    collected_docs.extend(semantic_fetch(db, base_variations, per_query_k=10))

    # 3) GPT Query Expansion — ključno za milion pitanja
    expanded_queries = expand_query_with_gpt(query)
    if expanded_queries:
        collected_docs.extend(semantic_fetch(db, expanded_queries, per_query_k=8))

    # 4) Dedupe
    collected_docs = unique_docs(collected_docs)

    # 5) Rerank
    ranked_docs = rank_docs(query, collected_docs, guessed_law, article_label)

    return [format_doc(doc) for doc in ranked_docs[:k]]