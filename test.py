# test_db.py — snimi kao fajl i pokreni

from pathlib import Path
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

VECTOR_STORE_DIR = Path("vector_store")

# 🔒 Provera da li baza postoji
if not VECTOR_STORE_DIR.exists():
    print("❌ vector_store folder ne postoji. Pokreni ingest prvo.")
    exit()

# 🔒 Inicijalizacija DB
try:
    db = Chroma(
        persist_directory=str(VECTOR_STORE_DIR),
        embedding_function=OpenAIEmbeddings(model="text-embedding-3-large")
    )
except Exception as e:
    print(f"❌ Greška pri učitavanju baze: {e}")
    exit()

# 🔒 Broj dokumenata
try:
    count = db._collection.count()
    print(f"\n📊 Broj dokumenata u vector store: {count}")
except Exception as e:
    print(f"❌ Ne mogu da očitam broj dokumenata: {e}")
    exit()

# 🔴 Ako je prazno → nema šta dalje
if count == 0:
    print("❌ Baza je prazna — ingest nije uspeo.")
    exit()

# 🔎 Test pretrage
query = "član 200 obligacioni odnosi"
print(f"\n🔎 Test query: {query}\n")

try:
    results = db.similarity_search(query, k=3)
except Exception as e:
    print(f"❌ Greška pri pretrazi: {e}")
    exit()

# 🔎 Ispis rezultata
if not results:
    print("⚠️ Nema rezultata za query.")
else:
    for i, r in enumerate(results, 1):
        metadata = getattr(r, "metadata", {}) or {}
        content = (getattr(r, "page_content", "") or "").strip()

        print(f"--- REZULTAT {i} ---")
        print("Zakon:", metadata.get("law", "N/A"))
        print("Član:", metadata.get("article", "N/A"))
        print("Source:", metadata.get("source", "N/A"))
        print("\nTekst:")
        print(content[:300])
        print("\n" + "-" * 50 + "\n")