from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

PDF_FOLDER = Path("data/laws/pdfs")
VECTOR_STORE_DIR = "vector_store"

def ingest_documents():

    documents = []

    for pdf in PDF_FOLDER.glob("*.pdf"):

        try:
            print(f"Učitavam: {pdf.name}")

            loader = PyPDFLoader(str(pdf))
            docs = loader.load()

            documents.extend(docs)

        except Exception as e:
            print(f"⚠️ Preskačem oštećen PDF: {pdf.name}")
            print(e)

    if not documents:
        print("Nijedan dokument nije učitan.")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=400
    )

    chunks = splitter.split_documents(documents)

    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=VECTOR_STORE_DIR
    )

    db.persist()

    print("✅ Ingestion završen.")