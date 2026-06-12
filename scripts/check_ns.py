# -*- coding: utf-8 -*-
"""Scratch: verify Pinecone namespace counts after Faza 2B ingest."""
import sys, os
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from pinecone import Pinecone

pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
idx = pc.Index(os.environ.get("PINECONE_INDEX", "vindex-ai"))
stats = idx.describe_index_stats()

DEFAULT_EXPECTED = 17707
SP_EXPECTED = 12604

print("\n=== NAMESPACE COUNTS ===")
ns_map = stats.namespaces or {}
for ns_key, v in sorted(ns_map.items()):
    label = "(default)" if ns_key == "" else ns_key
    cnt = v.vector_count if hasattr(v, "vector_count") else int(str(v).split("vector_count: ")[-1].split()[0])
    flag = ""
    if ns_key == "" and cnt != DEFAULT_EXPECTED:
        flag = f"  ← CRITICAL! expected {DEFAULT_EXPECTED}"
    elif ns_key == "sudska_praksa" and cnt != SP_EXPECTED:
        flag = f"  ← WARNING: expected {SP_EXPECTED}"
    print(f"  {label:30s} {cnt:7d}{flag}")

# Default ns guard
default_count = next(
    (v.vector_count if hasattr(v, "vector_count") else int(str(v).split("vector_count: ")[-1].split()[0])
     for k, v in ns_map.items() if k == ""),
    0
)
sp_count = next(
    (v.vector_count if hasattr(v, "vector_count") else int(str(v).split("vector_count: ")[-1].split()[0])
     for k, v in ns_map.items() if k == "sudska_praksa"),
    0
)

print()
if default_count == DEFAULT_EXPECTED:
    print(f"  [OK] default namespace = {default_count} ✓")
else:
    print(f"  [CRITICAL] default namespace = {default_count} (expected {DEFAULT_EXPECTED}) ← STOP!")

if sp_count == SP_EXPECTED:
    print(f"  [OK] sudska_praksa = {sp_count} ✓")
else:
    print(f"  [INFO] sudska_praksa = {sp_count} (expected {SP_EXPECTED})")
