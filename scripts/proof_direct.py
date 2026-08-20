# -*- coding: utf-8 -*-
"""
Vindex AI — scripts/proof_direct.py

Lokalni proof test — ne treba JWT, radi direktno sa .env kljucevima.
Pokreni: python scripts/proof_direct.py

Testira:
  - Sve tabele iz migracija 044, 045, 046, 047
  - VIEW: case_profitability
  - Kolone: kancelarije.pinecone_namespace, ai_corrections.tip_korekcije
  - Pinecone konekcija + broj vektora
  - OpenAI embedding
"""
import os
import sys
import time

# Ucitaj .env iz roota projekta
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

PASS  = "\033[92mPASS\033[0m"
FAIL  = "\033[91mFAIL\033[0m"
WARN  = "\033[93mWARN\033[0m"

results = []

def check(name, status, detail=""):
    icon = PASS if status == "PASS" else (FAIL if status == "FAIL" else WARN)
    print(f"  {icon}  {name}")
    if detail:
        print(f"       {detail}")
    results.append(status)

# ─── Supabase ─────────────────────────────────────────────────────────────────
print("\n=== SUPABASE ===")
try:
    from supabase import create_client
    url  = os.environ["SUPABASE_URL"]
    key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SERVICE_KEY"]
    supa = create_client(url, key)
    check("Supabase konekcija", "PASS", url[:40] + "...")
except Exception as e:
    check("Supabase konekcija", "FAIL", str(e)[:100])
    supa = None

def test_table(name, col="id"):
    if not supa:
        check(f"DB: {name}", "FAIL", "Nema konekcije")
        return
    try:
        r = supa.table(name).select(col, count="exact").limit(1).execute()
        cnt = r.count if r.count is not None else len(r.data or [])
        check(f"DB: {name}", "PASS", f"{cnt} redova")
    except Exception as e:
        check(f"DB: {name}", "FAIL", str(e)[:120])

def test_columns(table, cols):
    if not supa:
        check(f"Kolone: {table}", "FAIL", "Nema konekcije")
        return
    try:
        supa.table(table).select(cols).limit(1).execute()
        check(f"Kolone: {table} ({cols})", "PASS")
    except Exception as e:
        check(f"Kolone: {table} ({cols})", "FAIL", str(e)[:120])

print("\n=== MIGRACIJA 044 ===")
test_table("user_daily_activity")
test_table("chain_anchors")

print("\n=== MIGRACIJA 045 ===")
test_table("ai_corrections")
test_table("firm_style_profile")
test_table("zakoni_monitoring")
test_table("zadaci")
test_table("case_benchmarks")
test_columns("kancelarije", "pinecone_namespace, firma_slug")

print("\n=== VIEW: case_profitability ===")
test_table("case_profitability", "predmet_id")

print("\n=== MIGRACIJA 046 ===")
test_table("memory_entries")
test_table("partner_profiles")
test_table("judge_patterns")
test_table("client_memory")
test_columns("ai_corrections", "tip_korekcije, partner_uid")

print("\n=== MIGRACIJA 047 ===")
test_table("memory_graph_edges")
test_table("workflow_templates")
test_table("workflow_instances")
test_table("workflow_steps")
test_columns("memory_entries", "confidence, izvor, potvrde_count, expires_at, zastarela")

# ─── Pinecone ─────────────────────────────────────────────────────────────────
print("\n=== PINECONE ===")
try:
    from pinecone import Pinecone
    api_key  = os.environ["PINECONE_API_KEY"]
    host     = os.getenv("PINECONE_HOST", "").strip()
    idx_name = os.getenv("PINECONE_INDEX_NAME", "vindex-ai").strip()
    pc  = Pinecone(api_key=api_key)
    idx = pc.Index(host=host) if host else pc.Index(idx_name)
    stats = idx.describe_index_stats()
    total = stats.total_vector_count
    ns    = len(stats.namespaces or {})
    check("Pinecone indeks", "PASS", f"{total:,} vektora, {ns} namespace-ova")
    for ns_name, ns_stats in (stats.namespaces or {}).items():
        cnt = getattr(ns_stats, "vector_count", "?")
        print(f"       namespace '{ns_name}': {cnt} vektora")
except Exception as e:
    check("Pinecone indeks", "FAIL", str(e)[:120])

# ─── OpenAI ───────────────────────────────────────────────────────────────────
print("\n=== OPENAI ===")
try:
    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    r   = oai.embeddings.create(model="text-embedding-3-large", input="vindex proof test")
    dims = len(r.data[0].embedding)
    check("OpenAI embedding", "PASS", f"{dims} dimenzija")
except Exception as e:
    check("OpenAI embedding", "FAIL", str(e)[:120])

# ─── ENV varijable ────────────────────────────────────────────────────────────
print("\n=== ENV VARIJABLE ===")
required = ["OPENAI_API_KEY", "PINECONE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
optional = ["BRIEFING_CRON_SECRET", "ANCHOR_BACKEND", "PINECONE_HOST", "PINECONE_INDEX_NAME"]
for v in required:
    val = os.getenv(v, "") or (os.getenv("SUPABASE_SERVICE_KEY", "") if v == "SUPABASE_SERVICE_ROLE_KEY" else "")
    check(f"ENV: {v}", "PASS" if val else "FAIL", (val[:4] + "***") if val else "NIJE POSTAVLJENA")
for v in optional:
    val = os.getenv(v, "")
    check(f"ENV: {v}", "PASS" if val else "WARN", (val[:8] + "...") if val else "nije postavljena (opciono)")

# ─── Rezultat ─────────────────────────────────────────────────────────────────
print("\n" + "="*50)
passed = results.count("PASS")
failed = results.count("FAIL")
warned = results.count("WARN")
overall = "PASS" if failed == 0 else "FAIL"
icon = "\033[92mPASS\033[0m" if overall == "PASS" else "\033[91mFAIL\033[0m"
print(f"  UKUPNO: {icon}  —  {passed} PASS  |  {failed} FAIL  |  {warned} WARN")
print("="*50 + "\n")
sys.exit(0 if overall == "PASS" else 1)
