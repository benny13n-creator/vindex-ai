# -*- coding: utf-8 -*-
"""READ-ONLY: report current Pinecone namespace counts."""
import os, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from pinecone import Pinecone

api_key = os.getenv("PINECONE_API_KEY", "").strip()
host    = os.getenv("PINECONE_HOST", "").strip()
if not api_key or not host:
    print("ERROR: missing PINECONE_API_KEY or PINECONE_HOST"); sys.exit(1)

pc    = Pinecone(api_key=api_key)
index = pc.Index(host=host)
stats = index.describe_index_stats()

print("Pinecone namespace counts:")
for ns, v in sorted(stats.namespaces.items()):
    label = "(default/zakon)" if ns == "" else f"({ns})"
    vc = v.vector_count if hasattr(v, "vector_count") else int(str(v).split("vector_count: ")[-1].split()[0])
    print(f"  '{ns}' {label}: {vc}")
print(f"\nTotal vectors: {stats.total_vector_count}")
