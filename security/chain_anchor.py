# -*- coding: utf-8 -*-
"""
Vindex AI — security/chain_anchor.py

External Chain Anchor — dnevno sidri root hash audit lanca na nezavisnoj lokaciji.

Problem: ako napadač kompromituje Supabase, može:
  1. Obrisati sve zapise u audit_immutable
  2. Upisati lažnu istoriju
  3. Promeniti trigger (ako ima superuser privilegije)

Rešenje: jednom dnevno izračunaj root hash (SHA-256 svih entry_hash vrednosti)
i sačuvaj ga na NEZAVISNOJ lokaciji — odvojenoj od Supabase naloga.

Lokacije (konfigurišu se env varom ANCHOR_BACKEND):
  - "supabase_secondary" — zasebna Supabase tabela sa ograničenim pristupom
  - "stdout" — ispisuje na konzolu (za logging sisteme koji čuvaju logove)
  - "file" — čuva u lokalnom fajlu (za dev/test)

Root hash je: SHA-256( SHA-256(entry1) || SHA-256(entry2) || ... || SHA-256(entryN) )
ako je tabela prazna, vraća genesis hash.

Kako verifikovati:
  1. Pročitaj anchor hash za datum X iz nezavisne lokacije
  2. Pročitaj sve audit_immutable redove za datum X iz Supabase
  3. Izračunaj lokalni root hash
  4. Poredi — ako se razlikuju, neko je menjao logove posle toga
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone, date
from typing import Optional

logger = logging.getLogger("vindex.security.chain_anchor")

_GENESIS_HASH = "0" * 64
_ANCHOR_BACKEND = os.getenv("ANCHOR_BACKEND", "stdout").lower()


# ─── Javni API ────────────────────────────────────────────────────────────────

async def anchor_today() -> dict:
    """
    Izračunava root hash za tekući dan i sidri ga na nezavisnoj lokaciji.

    Pozivati jednom dnevno — Supabase Scheduled Function ili cron job.
    Vraća: {"date": ..., "root_hash": ..., "record_count": ..., "anchored": bool}
    """
    today = date.today().isoformat()
    try:
        root_hash, count = await asyncio.to_thread(_compute_root_hash, today)
        anchored = await _persist_anchor(today, root_hash, count)
        result = {"date": today, "root_hash": root_hash, "record_count": count, "anchored": anchored}
        logger.info("[ANCHOR] %s root_hash=%s records=%d anchored=%s", today, root_hash[:16], count, anchored)
        return result
    except Exception as e:
        logger.error("[ANCHOR] greška: %s", e)
        return {"date": today, "root_hash": None, "record_count": 0, "anchored": False, "error": str(e)}


async def verify_anchor(target_date: str) -> dict:
    """
    Verifikuje audit log za dati datum poređenjem sa sačuvanim anchor hashom.

    Returns:
        {"ok": bool, "date": str, "stored_hash": str, "computed_hash": str, "message": str}
    """
    try:
        stored = await _load_anchor(target_date)
        if not stored:
            return {"ok": False, "date": target_date, "message": "Anchor hash nije pronađen za ovaj datum."}

        computed_hash, count = await asyncio.to_thread(_compute_root_hash, target_date)
        ok = computed_hash == stored["root_hash"]

        if not ok:
            logger.error(
                "[ANCHOR] INTEGRITET NARUŠEN za %s: stored=%s computed=%s",
                target_date, stored["root_hash"][:16], computed_hash[:16],
            )

        return {
            "ok": ok,
            "date": target_date,
            "stored_hash":   stored["root_hash"],
            "computed_hash": computed_hash,
            "record_count":  count,
            "message": "Integritet potvrđen." if ok else "UPOZORENJE: Hash se razlikuje — mogući tampering!",
        }
    except Exception as e:
        return {"ok": False, "date": target_date, "message": f"Greška verifikacije: {e}"}


# ─── Interni helpers ──────────────────────────────────────────────────────────

def _compute_root_hash(target_date: str) -> tuple[str, int]:
    """
    Izračunava Merkle-style root hash svih zapisa za dati datum.
    SHA-256( sort(entry_hashes).join("") )
    """
    from api import _get_supa
    supa = _get_supa()

    # Sve entry_hash vrednosti za dati dan, sortiramo po seq
    result = (
        supa.table("audit_immutable")
        .select("seq, entry_hash")
        .gte("created_at", f"{target_date}T00:00:00+00:00")
        .lt("created_at",  f"{target_date}T23:59:59.999+00:00")
        .order("seq", desc=False)
        .execute()
    )
    rows = result.data or []

    if not rows:
        return _GENESIS_HASH, 0

    # Merkle-style: SHA-256 od konkatenacije svih entry_hash vrednosti
    h = hashlib.sha256()
    for row in rows:
        h.update(row["entry_hash"].encode("ascii"))

    return h.hexdigest(), len(rows)


async def _persist_anchor(target_date: str, root_hash: str, count: int) -> bool:
    """Sačuvaj anchor na konfigurisan backend."""
    payload = {
        "date":         target_date,
        "root_hash":    root_hash,
        "record_count": count,
        "created_at":   datetime.now(timezone.utc).isoformat(),
    }

    if _ANCHOR_BACKEND == "supabase_secondary":
        return await _persist_supabase(payload)
    elif _ANCHOR_BACKEND == "file":
        return _persist_file(payload)
    else:
        # stdout — logujemo tako da monitoring sistemi (Render logs, Datadog...)
        # automatski čuvaju ovu liniju i ona postaje nezavisna kopija
        logger.info("[ANCHOR_RECORD] %s", json.dumps(payload))
        return True


async def _persist_supabase(payload: dict) -> bool:
    """Čuva u chain_anchors tabeli (zasebna, readonly za sve osim admin)."""
    try:
        from api import _get_supa
        supa = _get_supa()
        await asyncio.to_thread(
            lambda: supa.table("chain_anchors").upsert(
                payload, on_conflict="date"
            ).execute()
        )
        return True
    except Exception as e:
        logger.error("[ANCHOR] Supabase persist greška: %s", e)
        return False


def _persist_file(payload: dict) -> bool:
    """Čuva u lokalnom JSON fajlu (za dev/test)."""
    try:
        path = os.getenv("ANCHOR_FILE_PATH", "/tmp/vindex_anchors.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
        return True
    except Exception as e:
        logger.error("[ANCHOR] file persist greška: %s", e)
        return False


async def _load_anchor(target_date: str) -> Optional[dict]:
    """Čita sačuvani anchor za dati datum."""
    if _ANCHOR_BACKEND == "supabase_secondary":
        try:
            from api import _get_supa
            supa = _get_supa()
            result = await asyncio.to_thread(
                lambda: supa.table("chain_anchors")
                    .select("*")
                    .eq("date", target_date)
                    .maybe_single()
                    .execute()
            )
            return result.data
        except Exception:
            return None
    return None  # Stdout i file backend ne podržavaju verifikaciju
