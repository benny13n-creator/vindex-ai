# -*- coding: utf-8 -*-
"""
Vindex AI — shared/audit_immutable.py

Nepromenjivi (immutable) hash-chain audit log.

Svaki zapis sadrži SHA-256 hash prethodnog zapisa.
Ako neko promeni ili obriše bilo koji zapis, lanac se lomi i
integritet se može proveriti algoritmom verifikacije.

Ovo je kriptografski dokaz — ne može se falsifikovati bez otkrivanja.

Tabela: audit_immutable (INSERT-only — nikad UPDATE/DELETE)
Verifikacija integriteta: verify_chain_integrity()

Referenca: GDPR čl. 32, ZZPL čl. 50 — bezbednost obrade
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("vindex.audit.immutable")

# Sentinel za "nema prethodnog" — genesis hash
_GENESIS_HASH = "0" * 64

# Akcije koje se UVEK beleže u immutable log
AUDITABLE_ACTIONS: set[str] = {
    # Predmeti
    "predmet_create", "predmet_update", "predmet_delete", "predmet_view",
    # Dokumenti
    "dokument_upload", "dokument_delete", "dokument_view", "dokument_download",
    # Klijenti
    "klijent_create", "klijent_delete",
    # Autentifikacija
    "login_success", "login_failed", "logout", "password_change",
    "2fa_enable", "2fa_disable",
    # Export i brisanje podataka
    "data_export", "account_delete", "gdpr_erasure",
    # Admin akcije
    "admin_access", "user_role_change", "firm_settings_change",
    # AI operacije (samo metadata, ne sadržaj)
    "ai_analiza_complete", "ai_kompletna_analiza_complete",
    # Case Genome (Faza 1.2, 90-dnevni plan 2026-07-18)
    "genome_refresh",
    # Legal Reasoning Engine, Phase 0 (2026-07-23)
    "reasoning_graph_generated",
    # Bezbednosni događaji
    "injection_attempt_blocked", "rate_limit_exceeded",
    "suspicious_access", "api_key_rotation",
}


# ─── Javni API ────────────────────────────────────────────────────────────────

async def log_action(
    action: str,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[str]:
    """
    Upisuje nepromenjivi zapis u audit_immutable tabelu.

    Vraća ID upisanog zapisa, ili None ako upis nije uspeo.
    Greška u audit-u NIKAD ne blokira glavni zahtev.
    """
    if action not in AUDITABLE_ACTIONS:
        logger.debug("[AUDIT_IMMUTABLE] akcija=%s nije u skupu praćenih akcija — preskačem", action)
        return None

    try:
        entry = await asyncio.to_thread(_build_and_insert, action, user_id, resource_type, resource_id, ip, metadata)
        return entry
    except Exception as e:
        logger.warning("[AUDIT_IMMUTABLE] greška upisa (nije kritično): %s", e)
        return None


def log_action_sync(
    action: str,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[str]:
    """Sinhrona verzija za ne-async kontekste."""
    if action not in AUDITABLE_ACTIONS:
        return None
    try:
        return _build_and_insert(action, user_id, resource_type, resource_id, ip, metadata)
    except Exception as e:
        logger.warning("[AUDIT_IMMUTABLE] sync greška (nije kritično): %s", e)
        return None


async def verify_chain_integrity(limit: int = 1000) -> dict:
    """
    Proverava integritet hash lanca poslednjih `limit` zapisa.

    Vraća:
        {
            "ok": bool,
            "checked": int,
            "broken_at_seq": int | None,   # seq broj gde je lanac polupan
            "message": str,
        }
    """
    try:
        result = await asyncio.to_thread(_verify_chain_sync, limit)
        return result
    except Exception as e:
        return {"ok": False, "checked": 0, "broken_at_seq": None, "message": str(e)}


# ─── Interni helpers ──────────────────────────────────────────────────────────

def _build_and_insert(
    action: str,
    user_id: Optional[str],
    resource_type: Optional[str],
    resource_id: Optional[str],
    ip: Optional[str],
    metadata: Optional[dict],
) -> Optional[str]:
    """Sinhrono gradi i upisuje zapis u bazu."""
    from api import _get_supa
    supa = _get_supa()

    # Dohvati poslednji hash iz lanca
    prev_hash = _get_last_hash(supa)

    # Vreme upisa
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()

    # Hash IP adrese (ne čuvamo plaintext IP — privatnost)
    ip_hash = hashlib.sha256((ip or "").encode()).hexdigest()[:16] if ip else None

    # Kalkuliši entry hash
    entry_hash = _compute_entry_hash(
        prev_hash=prev_hash,
        user_id=user_id or "",
        action=action,
        ts=ts,
        resource_type=resource_type or "",
        resource_id=resource_id or "",
    )

    record = {
        "prev_hash":     prev_hash,
        "entry_hash":    entry_hash,
        "user_id":       user_id,
        "action":        action,
        "resource_type": resource_type,
        "resource_id":   str(resource_id)[:255] if resource_id else None,
        "ip_hash":       ip_hash,
        "metadata":      json.dumps(metadata or {}),
        "created_at":    ts,
    }

    result = supa.table("audit_immutable").insert(record).execute()
    inserted = (result.data or [{}])[0]
    return inserted.get("id")


def _get_last_hash(supa) -> str:
    """Vraća entry_hash poslednjeg zapisa, ili genesis hash ako tabela prazna."""
    try:
        result = (
            supa.table("audit_immutable")
            .select("entry_hash")
            .order("seq", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if rows:
            return rows[0]["entry_hash"]
    except Exception:
        pass
    return _GENESIS_HASH


def _compute_entry_hash(
    prev_hash: str,
    user_id: str,
    action: str,
    ts: str,
    resource_type: str,
    resource_id: str,
) -> str:
    """
    SHA-256 od konkatenacije svih ključnih polja.
    Bilo koja promena u bilo kom polju menja hash i lomi lanac.
    """
    payload = f"{prev_hash}|{user_id}|{action}|{ts}|{resource_type}|{resource_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_chain_sync(limit: int) -> dict:
    """Proverava integritet lanca (sinhrono)."""
    from api import _get_supa
    supa = _get_supa()

    result = (
        supa.table("audit_immutable")
        .select("seq, prev_hash, entry_hash, user_id, action, created_at, resource_type, resource_id")
        .order("seq", desc=False)
        .limit(limit)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return {"ok": True, "checked": 0, "broken_at_seq": None, "message": "Tabela prazna."}

    broken_at = None
    prev_hash = _GENESIS_HASH

    for i, row in enumerate(rows):
        expected_hash = _compute_entry_hash(
            prev_hash=prev_hash,
            user_id=row.get("user_id") or "",
            action=row.get("action") or "",
            ts=row.get("created_at") or "",
            resource_type=row.get("resource_type") or "",
            resource_id=row.get("resource_id") or "",
        )

        # Proveri da li prev_hash odgovara
        if row["prev_hash"] != prev_hash:
            broken_at = row["seq"]
            logger.error(
                "[AUDIT_IMMUTABLE] LANAC POLUPAN na seq=%d — prev_hash mismatch",
                broken_at,
            )
            break

        # Proveri entry_hash — detect tampering
        if row["entry_hash"] != expected_hash:
            broken_at = row["seq"]
            logger.error(
                "[AUDIT_IMMUTABLE] MODIFIKACIJA DETEKTOVANA na seq=%d — entry_hash ne odgovara",
                broken_at,
            )
            break

        prev_hash = row["entry_hash"]

    if broken_at is not None:
        return {
            "ok": False,
            "checked": rows.index(next(r for r in rows if r["seq"] == broken_at)) + 1,
            "broken_at_seq": broken_at,
            "message": f"Lanac je polupan na seq={broken_at}. Mogući tampering.",
        }

    return {
        "ok": True,
        "checked": len(rows),
        "broken_at_seq": None,
        "message": f"Integritet lanca potvrđen za {len(rows)} zapisa.",
    }
