from pathlib import Path
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

VECTOR_STORE_DIR = Path("vector_store")

db = Chroma(
    persist_directory=str(VECTOR_STORE_DIR),
    embedding_function=OpenAIEmbeddings(model="text-embedding-3-large")
)

data = db.get(include=["metadatas"])

laws = set()

for meta in data["metadatas"]:
    if not meta:
        continue
    law = meta.get("law")
    if law:
        laws.add(law)

print(f"\n📚 Ukupan broj zakona: {len(laws)}\n")

print("Lista zakona:\n")
for i, law in enumerate(sorted(laws), 1):
    print(f"{i}. {law}")