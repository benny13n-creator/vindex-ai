# -*- coding: utf-8 -*-
"""
TEST — _skini_zaglavlja() regex safety check.

Fetches parent_text for 10 known articles from Pinecone (existing index),
applies the new header-stripping function, and reports:
  - Original length
  - What was stripped (if anything)
  - Final clean length
  - Whether the result looks correct or suspicious

DOES NOT modify Pinecone. DOES NOT run ingestion. Read-only.
"""

import sys, os, time
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from pinecone import Pinecone
from semantic_chunker import _skini_zaglavlja, STUB_THRESHOLD

pc    = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index = pc.Index(host=os.environ["PINECONE_HOST"])

DUMMY = [0.0] * 3072

# Variety: long articles, short articles, known stubs, boundary-defect candidates
ARTICLES = [
    ("KZ",                            "Član 203"),   # long, fragmented (7 chunks) — likely clean
    ("KZ",                            "Član 204"),   # long, fragmented (7 chunks)
    ("zakon o obligacionim odnosima", "Član 200"),   # long, multiple stavovi
    ("zakon o obligacionim odnosima", "Član 371"),   # stub (short article)
    ("porodicni zakon",               "Član 88"),    # stub (107 chars in index)
    ("porodicni zakon",               "Član 170"),   # PZ has 6 boundary defects — candidate
    ("porodicni zakon",               "Član 171"),   # adjacent to 170
    ("zakon o radu",                  "Član 186"),   # ZR has 14 boundary defects — candidate
    ("zakon o radu",                  "Član 189"),   # ZR — another candidate
    ("zakon o nasledjivanju",         "Član 9"),     # ZN has 6 boundary defects — candidate
]

SEP  = "═" * 90
SEP2 = "─" * 90

out_lines = []

def emit(line=""):
    print(line)
    out_lines.append(line)

emit("TEST — _skini_zaglavlja() regex safety check")
emit(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
emit(f"Pinecone host: {os.environ.get('PINECONE_HOST', '?')}")
emit(f"Articles under test: {len(ARTICLES)}")
emit()
emit(SEP)

for idx, (law, article) in enumerate(ARTICLES, 1):
    emit()
    emit(f"[{idx:02d}] {law} · {article}")
    emit(SEP2)

    try:
        res = index.query(
            vector=DUMMY,
            top_k=10,
            filter={"law": {"$eq": law}, "article": {"$eq": article}},
            include_metadata=True,
        )
    except Exception as e:
        emit(f"  FETCH ERROR: {e}")
        continue

    if not res.matches:
        emit("  NO MATCHES FOUND IN INDEX")
        continue

    chunks_found = len(res.matches)

    # Collect longest non-empty parent_text across all chunks
    parent_text = ""
    for m in res.matches:
        pt = (m.metadata or {}).get("parent_text", "") or ""
        if len(pt) > len(parent_text):
            parent_text = pt

    emit(f"  Chunks in index : {chunks_found}")

    if not parent_text:
        emit("  parent_text     : EMPTY (old ingestion — no content to test)")
        continue

    orig_len = len(parent_text)
    clean, stripped = _skini_zaglavlja(parent_text)
    clean_len = len(clean)
    removed   = orig_len - clean_len

    stub_flag = "  ← STUB" if clean_len < STUB_THRESHOLD else ""

    if stripped:
        status = "STRIPPED"
        # Suspicion check: stripped too much (>15% of article) OR
        # stripped text doesn't start with a known header keyword
        import re
        _known_kw = re.compile(
            r'^(?:Glava|GLAVA|Deo|DEO|Odeljak|ODELJAK|Pododeljak|Poglavlje|POGLAVLJE)',
            re.UNICODE
        )
        all_caps_only = all(
            re.match(r'^[A-ZŠĐČĆŽА-Я \-]+$', ln.strip())
            for ln in stripped.split('\n') if ln.strip()
        )
        has_known_kw = bool(_known_kw.match(stripped.strip()))
        suspicious = (removed > orig_len * 0.15) and not (has_known_kw or all_caps_only)
        verdict = "SUSPICIOUS ⚠" if suspicious else "LOOKS CORRECT ✓"
    else:
        status  = "UNCHANGED"
        verdict = "NO STRIP NEEDED ✓"

    emit(f"  Original length : {orig_len} chars")
    emit(f"  After strip     : {clean_len} chars{stub_flag}")
    emit(f"  Chars removed   : {removed}")
    emit(f"  Status          : {status}  —  {verdict}")

    if stripped:
        emit()
        emit("  WHAT WAS STRIPPED:")
        for line in stripped.split('\n'):
            if line.strip():
                emit(f"    {line.strip()!r}")
        emit()
        emit("  LAST 200 chars of CLEAN text (verify sentence ends properly):")
        emit(f"    {clean[-200:]!r}")
    else:
        emit()
        emit("  LAST 200 chars of existing parent_text (verify no header leaked in):")
        emit(f"    {parent_text[-200:]!r}")

    emit()

emit(SEP)
emit("SUMMARY")
emit(SEP)
emit()
stripped_count  = sum(1 for _, a in ARTICLES for _ in ["x"])   # placeholder
emit("See individual results above.")
emit()
emit(f"Timestamp end: {time.strftime('%Y-%m-%d %H:%M:%S')}")

# ── Write to file ─────────────────────────────────────────────────────────────
out_path = os.path.join(os.path.dirname(__file__), "test_chunker_fix.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('\n'.join(out_lines) + '\n')
print(f"\n[Output also saved to: {out_path}]")
