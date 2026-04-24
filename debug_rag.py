# -*- coding: utf-8 -*-
"""
Debug: trace parent_text flow from Pinecone -> _formatiraj_match -> kontekst string.
Pokretanje: python debug_rag.py
"""
import sys
import io
import logging
import os
from dotenv import load_dotenv

# Force UTF-8 output on Windows so Cyrillic/diacritics don't crash
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
# Uključi DEBUG i za retrieve logger
logging.getLogger("vindex.retrieve").setLevel(logging.DEBUG)

QUERY = "Koji su rokovi za registraciju privrednog drustva?"

def main():
    print("\n" + "="*70)
    print(f"QUERY: {QUERY}")
    print("="*70 + "\n")

    # ── 1. Direktan Pinecone hit — sirov metadata ─────────────────────────
    print("--- [1] DIREKTAN PINECONE HIT (top 3 matcheva, sirov metadata) ---\n")
    from pinecone import Pinecone
    from langchain_openai import OpenAIEmbeddings

    pc    = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index("vindex-ai")
    emb   = OpenAIEmbeddings(model="text-embedding-3-large")
    vec   = emb.embed_query(QUERY)

    res = index.query(vector=vec, top_k=3, include_metadata=True)
    for i, m in enumerate(res.matches):
        meta = m.metadata or {}
        print(f"  Match {i}: id={m.id}  score={m.score:.3f}")
        print(f"    law       = {meta.get('law', '[NEMA]')!r}")
        print(f"    article   = {meta.get('article', '[NEMA]')!r}")
        print(f"    zakon     = {meta.get('zakon', '[NEMA]')!r}")
        has_pt = "parent_text" in meta
        pt_len = len(meta.get("parent_text") or "")
        has_t  = "text" in meta
        t_len  = len(meta.get("text") or "")
        print(f"    parent_text present={has_pt}  len={pt_len}")
        print(f"    text        present={has_t}   len={t_len}")
        print(f"    all keys    = {list(meta.keys())}")
        if has_pt:
            print(f"    parent_text[:200] = {meta['parent_text'][:200]!r}")
        if has_t:
            print(f"    text[:200]        = {meta['text'][:200]!r}")
        print()

    # ── 2. _formatiraj_match output (DEBUG log će se ispisati gore) ────────
    print("\n--- [2] retrieve_documents OUTPUT (prvih 3 doc-a) ---\n")
    from app.services.retrieve import retrieve_documents
    docs = retrieve_documents(QUERY, k=6)
    for i, d in enumerate(docs[:3]):
        print(f"  doc[{i}] ({len(d)} chars):")
        print("  " + d[:500].replace("\n", "\n  "))
        print()

    # ── 3. Kontekst koji bi dobio LLM ─────────────────────────────────────
    print("\n--- [3] KONTEKST STRING (join sva 3) - prvih 800 char ---\n")
    kontekst = "\n\n---\n\n".join(docs[:3])
    print(kontekst[:800])
    print("\n" + "="*70)
    print("ZAKLJUČAK:")
    has_citabilni = any("CITABILNI TEKST" in d for d in docs)
    has_puni      = any("PUNI TEKST ČLANA" in d for d in docs)
    print(f"  CITABILNI TEKST prisutan u docs: {has_citabilni}")
    print(f"  PUNI TEKST ČLANA prisutan u docs: {has_puni}")
    if not has_citabilni:
        print("  ⚠ Vektori su v1 — nema parent_text u metapodacima.")
        print("    Reši: python reindex_agentic.py (bez --dry-run)")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
