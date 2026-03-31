from __future__ import annotations 
from app.services.retrieve import retrieve_documents

import re
import shutil
import tempfile
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
ZIP_PATH = BASE_DIR / "vector_store.zip"

GDRIVE_FILE_ID = "11eP6RrmdDcWfYvjWeh4UAsvtxOmLDumV"

EMBEDDING_MODEL = "text-embedding-3-large"
LLM_MODEL = "gpt-4o"
TEMPERATURE = 0
TOP_K_RETRIEVE = 14
TOP_K_FINAL = 6

LAW_KEYWORDS = {
    "rad": "zakon o radu",
    "radni odnos": "zakon o radu",
    "otkaz": "zakon o radu",
    "zarada": "zakon o radu",
    "porodic": "porodicni zakon",
    "brak": "porodicni zakon",
    "razvod": "porodicni zakon",
    "dete": "porodicni zakon",
    "krivic": "zakonik o krivicnom postupku",
    "krivicni": "zakonik o krivicnom postupku",
    "krivicno": "zakonik o krivicnom postupku",
    "krivicni postupak": "zakonik o krivicnom postupku",
    "parnic": "zakon o parnicnom postupku",
    "parnica": "zakon o parnicnom postupku",
    "tuzba": "zakon o parnicnom postupku",
    "presuda": "zakon o parnicnom postupku",
    "izvrs": "zakon o izvrsenju i obezbedjenju",
    "izvrsenje": "zakon o izvrsenju i obezbedjenju",
    "obezbedjenje": "zakon o izvrsenju i obezbedjenju",
    "obligaci": "zakon o obligacionim odnosima",
    "ugovor": "zakon o obligacionim odnosima",
    "naknada stete": "zakon o obligacionim odnosima",
    "steta": "zakon o obligacionim odnosima",
    "zastarelost": "zakon o obligacionim odnosima",
    "nematerijalna": "zakon o obligacionim odnosima",
    "nematerijalna steta": "zakon o obligacionim odnosima",
    "fizicki bolovi": "zakon o obligacionim odnosima",
    "dusevni bolovi": "zakon o obligacionim odnosima",
    "umanjenje zivotne aktivnosti": "zakon o obligacionim odnosima",
    "naruzenost": "zakon o obligacionim odnosima",
    "povreda ugleda": "zakon o obligacionim odnosima",
    "povreda casti": "zakon o obligacionim odnosima",
    "povreda slobode": "zakon o obligacionim odnosima",
    "smrt bliskog lica": "zakon o obligacionim odnosima",
    "strah": "zakon o obligacionim odnosima",
    "privredn": "zakon o privrednim drustvima",
    "privredno drustvo": "zakon o privrednim drustvima",
    "doo": "zakon o privrednim drustvima",
    "uprav": "zakon o opstem upravnom postupku",
    "upravno": "zakon o opstem upravnom postupku",
    "vanparnic": "zakon o vanparnicnom postupku",
    "nasledj": "zakon o nasledjivanju",
    "nasledjivanje": "zakon o nasledjivanju",
    "ostavina": "zakon o nasledjivanju",
    "ustav": "ustav republike srbije",
    "potrosac": "zakon o zastiti potrosaca",
    "potrosaca": "zakon o zastiti potrosaca",
    "zastita podataka": "zakon o zastiti podataka o licnosti",
    "podaci o licnosti": "zakon o zastiti podataka o licnosti",
}

STOPWORDS = {
    "koji", "koja", "koje", "kako", "kada", "da", "li", "se", "su",
    "je", "u", "na", "po", "za", "od", "do", "i", "ili", "a", "ali",
    "te", "pa", "uz", "kod", "iz", "pod", "nad", "prema", "radi",
    "sta", "što", "sto", "moze", "može", "mogu", "mora", "treba",
    "clan", "član", "stav", "zakon", "srbije", "republike",
}

_DB = None
_CLIENT = None


def normalize(text: str) -> str:
    text = (text or "").lower().strip()
    replacements = {
        "š": "s",
        "đ": "dj",
        "č": "c",
        "ć": "c",
        "ž": "z",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"\s+", " ", text)
    return text


def vector_store_is_ready() -> bool:
    if not VECTOR_STORE_DIR.exists() or not VECTOR_STORE_DIR.is_dir():
        return False

    sqlite_file = VECTOR_STORE_DIR / "chroma.sqlite3"
    if sqlite_file.exists():
        return True

    try:
        return any(VECTOR_STORE_DIR.iterdir())
    except Exception:
        return False


def preuzmi_vector_store() -> None:
    if vector_store_is_ready():
        print("Vector store već postoji i spreman je.")
        return

    print("Preuzimam bazu zakona...")

    temp_dir = Path(tempfile.mkdtemp())

    try:
        if ZIP_PATH.exists():
            ZIP_PATH.unlink()

        downloaded = gdown.download(
            id=GDRIVE_FILE_ID,
            output=str(ZIP_PATH),
            quiet=False,
            fuzzy=False,
        )

        if not downloaded or not ZIP_PATH.exists():
            raise RuntimeError("Zip nije uspešno preuzet sa Google Drive-a.")

        print("Raspakujem vector store...")

        with zipfile.ZipFile(ZIP_PATH, "r") as z:
            z.extractall(temp_dir)
            print("Sadržaj temp_dir:", [p.name for p in temp_dir.iterdir()])

        # 1) prvo traži klasičan folder vector_store
        vector_store_src = None
        for p in temp_dir.rglob("vector_store"):
            if p.is_dir():
                vector_store_src = p
                break

        # 2) ako ne postoji folder vector_store, proveri da li su chroma fajlovi direktno u root-u
        if vector_store_src is None:
            root_sqlite = temp_dir / "chroma.sqlite3"
            if root_sqlite.exists():
                vector_store_src = temp_dir

        if vector_store_src is None:
            raise RuntimeError("Ni vector_store folder ni chroma.sqlite3 nisu pronađeni u zip arhivi.")

        if VECTOR_STORE_DIR.exists():
            shutil.rmtree(VECTOR_STORE_DIR, ignore_errors=True)

        # ako je source ceo temp_dir, napravi target pa prekopiraj sadržaj
        if vector_store_src == temp_dir:
            VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
            for item in temp_dir.iterdir():
                if item.name == ZIP_PATH.name:
                    continue
                target = VECTOR_STORE_DIR / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)
        else:
            shutil.move(str(vector_store_src), str(VECTOR_STORE_DIR))

        if not vector_store_is_ready():
            raise RuntimeError("Vector store je preuzet, ali nije validno pripremljen.")

        print("Vector store uspešno pripremljen.")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if ZIP_PATH.exists():
            ZIP_PATH.unlink()


def ensure_vector_store() -> None:
    if not vector_store_is_ready():
        preuzmi_vector_store()

    if not vector_store_is_ready():
        raise RuntimeError("Vector store nije dostupan ni nakon pokušaja preuzimanja.")


def get_db():
    global _DB
    if _DB is not None:
        return _DB

    ensure_vector_store()

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    _DB = Chroma(
        persist_directory=str(VECTOR_STORE_DIR),
        embedding_function=embeddings,
    )
    return _DB


def get_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI()
    return _CLIENT


def extract_article_number(text: str) -> Optional[str]:
    t = normalize(text)

    patterns = [
        r"\bclan\s+(\d+[a-z]?)\b",
        r"\bc\s*\.?\s*(\d+[a-z]?)\b",
        r"\bart\.?\s*(\d+[a-z]?)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, t)
        if match:
            return match.group(1)

    return None


def extract_paragraph_number(text: str) -> Optional[str]:
    t = normalize(text)

    patterns = [
        r"\bstav\s+(\d+)\b",
        r"\bst\.?\s*(\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, t)
        if match:
            return match.group(1)

    return None


def guess_law(query: str) -> Optional[str]:
    q = normalize(query)

    best_match = None
    best_len = 0

    for kw, law in LAW_KEYWORDS.items():
        kw_norm = normalize(kw)
        if kw_norm in q and len(kw_norm) > best_len:
            best_match = law
            best_len = len(kw_norm)

    return best_match


def tokenize(query: str) -> list[str]:
    q = normalize(query)
    tokens = re.findall(r"[a-z0-9]+", q)
    return [t for t in tokens if len(t) >= 3 and t not in STOPWORDS]


def deduplicate(docs) -> list:
    seen = set()
    result = []

    for doc in docs:
        meta = getattr(doc, "metadata", {}) or {}
        content = getattr(doc, "page_content", "") or ""
        key = (
            normalize(str(meta.get("law", ""))),
            normalize(str(meta.get("article", ""))),
            normalize(content[:300]),
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


def score_doc(doc, query: str, guessed_law: Optional[str]) -> float:
    score = 0.0

    meta = getattr(doc, "metadata", {}) or {}
    content = getattr(doc, "page_content", "") or ""

    doc_law = normalize(str(meta.get("law", "")))
    doc_article = normalize(str(meta.get("article", "")))
    text = normalize(content)
    q = normalize(query)
    tokens = tokenize(query)

    # 1. bonus za pogođen zakon
    if guessed_law:
        guessed_law_norm = normalize(guessed_law)
        if guessed_law_norm == doc_law:
            score += 60
        elif guessed_law_norm in doc_law:
            score += 40

    # 2. token hits
    token_hits = sum(1 for t in tokens if t in text)
    score += min(token_hits * 5, 30)

    # 3. član/stav bonus
    asked_article = extract_article_number(query)
    if asked_article:
        if asked_article in doc_article:
            score += 40
        elif re.search(rf"\bclan\s+{re.escape(asked_article)}\b", text):
            score += 28

    asked_paragraph = extract_paragraph_number(query)
    if asked_paragraph:
        if re.search(rf"\bstav\s+{re.escape(asked_paragraph)}\b", text):
            score += 12

    if asked_article and asked_paragraph:
        if (
            re.search(rf"\bclan\s+{re.escape(asked_article)}\b", text)
            and re.search(rf"\bstav\s+{re.escape(asked_paragraph)}\b", text)
        ):
            score += 18

    # 4. AGRESIVNI BOOST za nematerijalnu štetu -> ZOO član 200
    if "nematerijalna steta" in q or "nematerijalne stete" in q:
        if "obligacion" in doc_law:
            score += 50
        if "200" in doc_article and "obligacion" in doc_law:
            score += 70

        # kazna za pogrešan domen
        if any(x in doc_law for x in ["patent", "zig", "autors"]):
            score -= 60

    # 5. dodatni signal iz samog teksta člana 200
    zoo_signals = [
        "fizicke bolove",
        "dusevne bolove",
        "umanjenja zivotne aktivnosti",
        "naruzenosti",
        "povrede ugleda",
        "casti",
        "slobode",
        "prava licnosti",
        "smrti bliskog lica",
        "straha",
        "pravicnu novcanu naknadu",
    ]
    if "nematerijalna" in q or "steta" in q:
        hits = sum(1 for s in zoo_signals if s in text)
        score += hits * 6

    if len(text) < 120:
        score -= 5

    return score




SYSTEM_PROMPT = """Ti si stručni pravni AI asistent za advokate u Republici Srbiji.

STROGA PRAVILA:

1. Odgovaraš ISKLJUČIVO na osnovu dostavljenog zakonskog konteksta.
2. Zabranjeno je izmišljanje zakona, članova, stavova, rokova, prava, obaveza i pravnih posledica.
3. Ako odgovor nije jasno potvrđen u kontekstu, to moraš otvoreno reći.
4. Navodi tačan naziv zakona i član samo kada su potvrđeni u kontekstu.
5. Ne koristi opšte pravno znanje mimo dostavljenog konteksta.
6. Ne dopunjuj praznine pretpostavkama.
7. Ako je kontekst delimičan ili nejasan, to naglasi.

FORMAT ODGOVORA:

PRAVNI OSNOV:
[Tačan zakon i član ako su potvrđeni u kontekstu; ako nisu, napiši da nisu pouzdano potvrđeni]

ODGOVOR:
[Direktan i jasan odgovor zasnovan samo na kontekstu]

CITAT IZ ZAKONA:
[Kratak citat ili veran prenos relevantnog dela iz dostavljenog konteksta]

PRAVNA POSLEDICA:
[Samo ako jasno proizlazi iz dostavljenog teksta; inače napiši da nije moguće pouzdano zaključiti]

NAPOMENA O POUZDANOSTI:
[VISOKA / SREDNJA / NISKA]
"""


def build_context(docs: list[str]) -> str:
    if not docs:
        return "NEMA KONTEKSTA."
    return "\n\n—\n\n".join(docs)


def answer_question(question: str) -> str:
    print("=== RAG VERSION V3 CLOUD ===")
    if not question or not question.strip():
        return _no_context_response("Pitanje je prazno.")

    try:
        docs = retrieve_documents(question, k=TOP_K_FINAL)
    except Exception as e:
        print(f"[RETRIEVE_ERROR] {e}")
        return _no_context_response(f"Greška pri pristupu bazi: {e}")

    if not docs:
        return _no_context_response("Nije pronađen relevantan zakonski tekst.")

    context = build_context(docs)
    user_prompt = (
        f"PITANJE: {question.strip()}\n\n"
        f"KONTEKST:\n{context}\n\n"
        "Odgovori isključivo na osnovu konteksta."
    )

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
        return _no_context_response(f"Greška: {e}")


def _no_context_response(reason: str) -> str:
    return f"""PRAVNI OSNOV:
Nije pouzdano potvrđeno u dostavljenom kontekstu.

ODGOVOR:
{reason}

CITAT IZ ZAKONA:
Nije pronađen relevantan citat.

PRAVNA POSLEDICA:
Nije moguće pouzdano zaključiti samo na osnovu dostavljenog konteksta.

NAPOMENA O POUZDANOSTI:
NISKA"""