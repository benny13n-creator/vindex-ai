import os
import re
import shutil
from pathlib import Path
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DOCS_FOLDER = BASE_DIR / "data" / "laws" / "pdfs"
VECTOR_STORE_DIR = BASE_DIR / "vector_store"


def normalize_text(text: str) -> str:
    """
    Stabilna normalizacija teksta bez menjanja semantike.
    Cilj: da parser pouzdanije prepozna 'Član X'.
    """
    if not text:
        return ""

    # standardizacija whitespace karaktera
    text = text.replace("\xa0", " ")
    text = text.replace("\uf0b7", " ")
    text = text.replace("\r", "\n")

    # spoji razbijene varijante reci "Član"
    text = re.sub(r"Č\s*l\s*a\s*n", "Član", text, flags=re.IGNORECASE)
    text = re.sub(r"\bČLAN\b", "Član", text)
    text = re.sub(r"\bčlan\b", "Član", text, flags=re.IGNORECASE)

    # očisti višak praznina, ali ne ubij potpuno strukturu
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_into_articles(text: str, law_name: str):
    """
    Pokušava da podeli zakon po 'Član X'.
    Ako ne uspe, vraća praznu listu.
    """
    text = normalize_text(text)

    if not text:
        return []

    # Hvata:
    # Član 1
    # Član 1.
    # Član 1)
    # Član 1a
    # Član 1A
    pattern = r"(Član\s*\d+[a-zA-Z]?[\.\)]?)"

    try:
        parts = re.split(pattern, text)
    except Exception as e:
        print(f"Greška pri splitovanju po članu za zakon '{law_name}': {e}")
        return []

    documents = []
    current_article = None
    current_text = ""

    for part in parts:
        cleaned_part = part.strip()

        if re.fullmatch(pattern, cleaned_part):
            if current_article and current_text.strip():
                documents.append(
                    Document(
                        page_content=current_text.strip(),
                        metadata={
                            "law": law_name,
                            "article": current_article,
                            "source": law_name,
                        },
                    )
                )

            current_article = (
                cleaned_part
                .replace(".", "")
                .replace(")", "")
                .strip()
            )
            current_text = ""
        else:
            if part:
                current_text += part

    if current_article and current_text.strip():
        documents.append(
            Document(
                page_content=current_text.strip(),
                metadata={
                    "law": law_name,
                    "article": current_article,
                    "source": law_name,
                },
            )
        )

    # zaštita: ako parser "nađe" samo 1 bezvezan član iz ogromnog teksta,
    # to često znači da split nije bio kvalitetan
    if len(documents) == 1:
        only_doc = documents[0]
        if len(only_doc.page_content.strip()) < 50:
            return []

    return documents


def safe_read_text(file_path: Path) -> str:
    """
    Fallback čitanje kao običan tekst.
    Pokušava više encoding varijanti bez pucanja.
    """
    encodings_to_try = ["utf-8", "utf-8-sig", "cp1250", "latin-1"]

    for enc in encodings_to_try:
        try:
            return file_path.read_text(encoding=enc, errors="ignore")
        except Exception:
            continue

    return ""


def split_large_documents(documents, max_chars=1800):
    """
    Minimalan, bezbedan chunking samo za prevelike delove.
    Ne menja sistem rada, samo sprečava katastrofu kod ogromnih članova.
    """
    chunked_docs = []

    for doc in documents:
        text = (doc.page_content or "").strip()

        if not text:
            continue

        if len(text) <= max_chars:
            chunked_docs.append(doc)
            continue

        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + max_chars

            # pokušaj da presečeš na kraju rečenice ili pasusa
            if end < len(text):
                split_candidates = [
                    text.rfind("\n\n", start, end),
                    text.rfind(". ", start, end),
                    text.rfind("; ", start, end),
                    text.rfind(": ", start, end),
                ]
                best_split = max(split_candidates)
                if best_split != -1 and best_split > start + 400:
                    end = best_split + 1

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunked_docs.append(
                    Document(
                        page_content=chunk_text,
                        metadata={
                            **doc.metadata,
                            "chunk": chunk_index,
                        },
                    )
                )
                chunk_index += 1

            start = end

    return chunked_docs


def load_document(file_path: Path):
    file_name = file_path.name
    law_name = file_path.stem.replace("_", " ")

    try:
        print(f"Učitavam kao PDF: {file_name}")
        loader = PyMuPDFLoader(str(file_path))
        docs = loader.load()

        if not docs:
            print(f"PDF je učitan, ali nema sadržaja: {file_name}")
            return []

        article_docs = []

        for doc in docs:
            page_text = normalize_text(doc.page_content)
            articles = split_into_articles(page_text, law_name)
            article_docs.extend(articles)

        if article_docs:
            print(f"Parsiran zakon po članu: {file_name}")
            return article_docs

        print(f"Nije uspeo split po članu, vraćam pune PDF stranice: {file_name}")

        fallback_docs = []
        for i, doc in enumerate(docs):
            page_text = normalize_text(doc.page_content)
            if not page_text:
                continue

            fallback_docs.append(
                Document(
                    page_content=page_text,
                    metadata={
                        "law": law_name,
                        "source": law_name,
                        "page": i + 1,
                    },
                )
            )

        return fallback_docs

    except Exception as e:
        print(f"PDF loader nije uspeo za: {file_name}")
        print(f"Greška: {e}")
        print("Pokušavam fallback kao običan tekst...")

        try:
            text = safe_read_text(file_path)
            text = normalize_text(text)

            if not text:
                print(f"Fallback tekst je prazan: {file_name}")
                return []

            article_docs = split_into_articles(text, law_name)

            if article_docs:
                print(f"Fallback parsiran po članu: {file_name}")
                return article_docs

            return [
                Document(
                    page_content=text,
                    metadata={
                        "law": law_name,
                        "source": law_name,
                    },
                )
            ]

        except Exception as e2:
            print(f"Text fallback nije uspeo za: {file_name}")
            print(f"Greška: {e2}")
            return []


def ingest_documents():
    print(f"BASE_DIR: {BASE_DIR}")
    print(f"DOCS_FOLDER: {DOCS_FOLDER}")
    print(f"VECTOR_STORE_DIR: {VECTOR_STORE_DIR}")

    if not DOCS_FOLDER.exists():
        print("Folder sa zakonima ne postoji.")
        return

    if not DOCS_FOLDER.is_dir():
        print("Putanja ka zakonima nije folder.")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Greška: OPENAI_API_KEY nije postavljen u .env fajlu.")
        return

    pdf_files = sorted(
        [p for p in DOCS_FOLDER.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    )

    if not pdf_files:
        print("Nema PDF fajlova u folderu sa zakonima.")
        return

    documents = []
    failed_files = []

    for file_path in pdf_files:
        docs = load_document(file_path)

        if docs:
            documents.extend(docs)
        else:
            failed_files.append(file_path.name)

    print(f"Ukupno učitanih dokumenata: {len(documents)}")

    if failed_files:
        print("Fajlovi koji nisu uspešno obrađeni:")
        for fname in failed_files:
            print(f" - {fname}")

    if not documents:
        print("Nema dokumenata za ingest.")
        return

    chunks = split_large_documents(documents)
    print(f"Ukupno chunkova: {len(chunks)}")

    if not chunks:
        print("Nema chunkova za upis u vector store.")
        return

    if VECTOR_STORE_DIR.exists():
        print("Brišem stari vector store...")
        shutil.rmtree(VECTOR_STORE_DIR, ignore_errors=True)

    embeddings = OpenAIEmbeddings()

    batch_size = 500

    db = Chroma(
        embedding_function=embeddings,
        persist_directory=str(VECTOR_STORE_DIR),
    )

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        db.add_documents(batch)
        print(f"Dodat batch {i // batch_size + 1}")

    print("Vector store uspešno napravljen.")


if __name__ == "__main__":
    ingest_documents()