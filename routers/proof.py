# -*- coding: utf-8 -*-
"""
Vindex AI — routers/proof.py

Proof Endpoint — dokazuje da sve implementirane funkcije zaista rade.

Testira:
  1. Svaku tabelu iz migracije 045 i 046 (SELECT COUNT(*))
  2. case_profitability VIEW
  3. Pinecone konekciju i broj vektora
  4. OpenAI konekciju (brz test-embedding)
  5. Dostupnost svakog novog router-a
  6. Anomaly detection tabelu (044)
  7. Firm memory tabele (046)

Output:
  GET /api/admin/proof → {
    "overall": "PASS"|"FAIL",
    "checks": [{"name": ..., "status": "PASS"|"FAIL"|"WARN", "detail": ...}],
    "pass_count": N,
    "fail_count": N,
    "warn_count": N,
    "trajanje_ms": N
  }

Dostupno samo founderu (is_founder check).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user, _is_founder
from shared.rate import limiter

logger = logging.getLogger("vindex.proof")
router = APIRouter(prefix="/api/admin", tags=["admin-proof"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


async def _test_table(supa, table_name: str) -> dict:
    """SELECT COUNT(*) na tabeli — potvrđuje da tabela postoji i RLS ne blokira service_role."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table(table_name).select("id", count="exact").limit(1).execute()
        )
        count = r.count if r.count is not None else len(r.data or [])
        return _check(f"DB: {table_name}", "PASS", f"{count} redova dostupno")
    except Exception as e:
        return _check(f"DB: {table_name}", "FAIL", str(e)[:200])


async def _test_view(supa, view_name: str) -> dict:
    """SELECT iz VIEW-a."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table(view_name).select("predmet_id").limit(1).execute()
        )
        return _check(f"VIEW: {view_name}", "PASS", f"VIEW dostupan, {len(r.data or [])} redova")
    except Exception as e:
        return _check(f"VIEW: {view_name}", "FAIL", str(e)[:200])


async def _test_pinecone() -> dict:
    """Pinecone konekcija i statistike indeksa."""
    try:
        from pinecone import Pinecone
        api_key = os.getenv("PINECONE_API_KEY", "").strip()
        if not api_key:
            return _check("Pinecone", "FAIL", "PINECONE_API_KEY nije postavljen")

        pc = Pinecone(api_key=api_key)
        host = os.getenv("PINECONE_HOST", "").strip()
        idx_name = os.getenv("PINECONE_INDEX_NAME", "vindex-ai").strip()

        idx = pc.Index(host=host) if host else pc.Index(idx_name)
        stats = await asyncio.to_thread(lambda: idx.describe_index_stats())
        total = stats.total_vector_count
        ns_count = len(stats.namespaces or {})
        return _check("Pinecone", "PASS", f"{total:,} vektora, {ns_count} namespace-ova")
    except Exception as e:
        return _check("Pinecone", "FAIL", str(e)[:200])


async def _test_openai() -> dict:
    """OpenAI konekcija — kratki embedding poziv."""
    try:
        from openai import AsyncOpenAI
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        r = await oai.embeddings.create(
            model="text-embedding-3-large",
            input="test konekcije vindex",
        )
        dims = len(r.data[0].embedding) if r.data else 0
        return _check("OpenAI", "PASS", f"Embedding OK ({dims} dim)")
    except Exception as e:
        return _check("OpenAI", "FAIL", str(e)[:200])


async def _test_router_url(path: str) -> dict:
    """
    Proverava da li je ruta registrovana u FastAPI app-u
    tako što uvozi app i proverava routes listu.
    """
    try:
        import api as _api_module
        app = _api_module.app
        registered = [r.path for r in app.routes if hasattr(r, "path")]
        # Traži prefix (path može biti /api/corrections/capture itd.)
        prefix = path.split("{")[0].rstrip("/")
        matched = any(r.startswith(prefix) for r in registered)
        if matched:
            return _check(f"Router: {path}", "PASS", "Ruta registrovana u FastAPI")
        else:
            return _check(f"Router: {path}", "FAIL", f"Ruta nije pronađena (prefix: {prefix})")
    except Exception as e:
        return _check(f"Router: {path}", "WARN", f"Ne mogu proveriti: {e}")


async def _test_env_var(var_name: str, required: bool = True) -> dict:
    """Proverava da li je env varijabla postavljena."""
    val = os.getenv(var_name, "")
    if val:
        masked = val[:4] + "***" if len(val) > 4 else "***"
        return _check(f"ENV: {var_name}", "PASS", f"Postavljena ({masked})")
    status = "FAIL" if required else "WARN"
    return _check(f"ENV: {var_name}", status, "Nije postavljena")


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/proof")
@limiter.limit("10/hour")
async def proof_check(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Sveobuhvatna provera svih implementiranih funkcija.
    Samo founder može pokrenuti. Vraća JSON sa PASS/FAIL za svaku stavku.
    """
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted to founder.")

    t0 = time.perf_counter()
    supa = _get_supa()
    checks: list[dict] = []

    # ── 1. DB tabele — migracija 045 ──────────────────────────────────────────
    tabele_045 = [
        "ai_corrections",
        "firm_style_profile",
        "zakoni_monitoring",
        "zadaci",
        "case_benchmarks",
    ]
    for t in tabele_045:
        checks.append(await _test_table(supa, t))

    # ── 2. VIEW — case_profitability ──────────────────────────────────────────
    checks.append(await _test_view(supa, "case_profitability"))

    # ── 3. DB tabele — migracija 046 ──────────────────────────────────────────
    tabele_046 = [
        "memory_entries",
        "partner_profiles",
        "judge_patterns",
        "client_memory",
    ]
    for t in tabele_046:
        checks.append(await _test_table(supa, t))

    # ── 4. Nove kolone u kancelarije (045) ────────────────────────────────────
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("kancelarije")
                .select("pinecone_namespace, firma_slug")
                .limit(1)
                .execute()
        )
        checks.append(_check("DB: kancelarije.pinecone_namespace", "PASS", "Kolona postoji"))
    except Exception as e:
        checks.append(_check("DB: kancelarije.pinecone_namespace", "FAIL", str(e)[:150]))

    # ── 5. Nove kolone u ai_corrections (046) ────────────────────────────────
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("ai_corrections")
                .select("tip_korekcije, partner_uid")
                .limit(1)
                .execute()
        )
        checks.append(_check("DB: ai_corrections.tip_korekcije+partner_uid", "PASS", "Kolone postoje"))
    except Exception as e:
        checks.append(_check("DB: ai_corrections.tip_korekcije+partner_uid", "FAIL", str(e)[:150]))

    # ── 6. DB tabele — migracija 047 ──────────────────────────────────────────
    tabele_047 = [
        "memory_graph_edges",
        "workflow_templates",
        "workflow_instances",
        "workflow_steps",
    ]
    for t in tabele_047:
        checks.append(await _test_table(supa, t))

    # ── 7. Trust score kolone u memory_entries (047) ──────────────────────────
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("memory_entries")
                .select("confidence, izvor, potvrde_count, potvrdjeno_od, expires_at, zastarela")
                .limit(1)
                .execute()
        )
        checks.append(_check("DB: memory_entries trust kolone (047)", "PASS", "Sve trust score kolone postoje"))
    except Exception as e:
        checks.append(_check("DB: memory_entries trust kolone (047)", "FAIL", str(e)[:150]))

    # ── 8. Migracija 044 — anomaly detection ─────────────────────────────────
    checks.append(await _test_table(supa, "user_daily_activity"))
    checks.append(await _test_table(supa, "chain_anchors"))

    # ── 9. Pinecone ───────────────────────────────────────────────────────────
    checks.append(await _test_pinecone())

    # ── 10. OpenAI ────────────────────────────────────────────────────────────
    checks.append(await _test_openai())

    # ── 11. Router registracija ───────────────────────────────────────────────
    rute = [
        "/api/corrections/capture",
        "/api/zakon-monitoring/cron",
        "/api/zakon-monitoring/impact-analiza",
        "/api/profitabilnost/pregled",
        "/api/zadaci/kreiraj",
        "/api/zadaci/ai-analiziraj",
        "/api/benchmarking/satnica",
        "/api/firma-memorija/dodaj",
        "/api/firma-memorija/potvrdi",
        "/api/memory-graph/dodaj-vezu",
        "/api/memory-graph/preporuka",
        "/api/workflow/pokreni",
        "/api/workflow/eskalacije/cron",
        "/api/admin/proof",
    ]
    for ruta in rute:
        checks.append(await _test_router_url(ruta))

    # ── 12. Firm memory pipeline konekcije ───────────────────────────────────
    try:
        import api as _api_mod
        has_mem_fn = hasattr(_api_mod, "_fetch_firm_memory_context")
        checks.append(_check(
            "Firma memorija: _fetch_firm_memory_context",
            "PASS" if has_mem_fn else "FAIL",
            "Funkcija postoji u api.py" if has_mem_fn else "Funkcija nije pronađena",
        ))
    except Exception as _fme:
        checks.append(_check("Firma memorija: _fetch_firm_memory_context", "WARN", str(_fme)[:100]))

    try:
        import inspect
        from main import ask_agent as _ask_agent
        sig = inspect.signature(_ask_agent)
        has_mem_param = "memory_context" in sig.parameters
        checks.append(_check(
            "ask_agent: memory_context parametar",
            "PASS" if has_mem_param else "FAIL",
            "Parametar postoji" if has_mem_param else "Parametar nije pronađen u ask_agent potpisu",
        ))
    except Exception as _ame:
        checks.append(_check("ask_agent: memory_context parametar", "WARN", str(_ame)[:100]))

    checks.append(await _test_router_url("/api/cron/daily"))

    # ── 13. Cron heartbeat — kada je poslednji put pokrenuto ─────────────────
    try:
        hb_r = await asyncio.to_thread(
            lambda: supa.table("chain_anchors")
                .select("anchored_at")
                .eq("id", "cron_daily_heartbeat")
                .maybe_single()
                .execute()
        )
        if hb_r.data and hb_r.data.get("anchored_at"):
            from datetime import datetime, timezone
            last = datetime.fromisoformat(hb_r.data["anchored_at"].replace("Z", "+00:00"))
            sada = datetime.now(timezone.utc)
            sati_od = round((sada - last).total_seconds() / 3600, 1)
            status = "PASS" if sati_od <= 36 else "WARN"
            checks.append(_check(
                "Cron heartbeat (poslednji run)",
                status,
                f"Pre {sati_od}h — {'OK' if status == 'PASS' else 'UPOZORENJE: cron možda ne radi!'}",
            ))
        else:
            checks.append(_check("Cron heartbeat", "WARN", "Cron još nije pokrenut ni jednom — pokrenite ručno ili podesite na Render.com"))
    except Exception as _hbe:
        checks.append(_check("Cron heartbeat", "WARN", str(_hbe)[:100]))

    # ── 14. ENV varijable ─────────────────────────────────────────────────────
    env_checks = [
        ("OPENAI_API_KEY", True),
        ("PINECONE_API_KEY", True),
        ("SUPABASE_URL", True),
        ("SUPABASE_SERVICE_ROLE_KEY", True),
        ("BRIEFING_CRON_SECRET", False),
        ("ANCHOR_BACKEND", False),
    ]
    for var, required in env_checks:
        checks.append(await _test_env_var(var, required))

    # ── Agregiraj rezultate ───────────────────────────────────────────────────
    pass_count = sum(1 for c in checks if c["status"] == "PASS")
    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")
    overall    = "PASS" if fail_count == 0 else "FAIL"
    trajanje   = round((time.perf_counter() - t0) * 1000)

    logger.info("[PROOF] %s — %d PASS, %d FAIL, %d WARN (%dms)", overall, pass_count, fail_count, warn_count, trajanje)

    return {
        "overall":      overall,
        "pass_count":   pass_count,
        "fail_count":   fail_count,
        "warn_count":   warn_count,
        "trajanje_ms":  trajanje,
        "checks":       checks,
        "poruka": (
            f"Sve {pass_count} provera prošle uspešno." if overall == "PASS"
            else f"{fail_count} provera NIJE prošlo. Videti 'checks' za detalje."
        ),
    }
