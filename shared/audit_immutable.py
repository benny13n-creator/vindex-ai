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
import re
from typing import Any, Optional

logger = logging.getLogger("vindex.audit.immutable")

# Sentinel za "nema prethodnog" — genesis hash
_GENESIS_HASH = "0" * 64

# CELINA 5 (2026-07-24): Postgres/PostgREST text-serijalizuje timestamptz sa
# OTKINUTIM nulama na kraju frakcionog dela sekunde (npr. .990920 -> .99092),
# dok log_action() u trenutku upisa heš-uje pun 6-cifreni Python
# datetime.isoformat() string. Otkriveno prvim živim pokretanjem
# scripts/verify_backup_restore.py protiv produkcije 2026-07-24: bilo koji
# zapis čiji mikrosekundni deo završava nulom lažno prijavljuje
# "MODIFIKACIJA DETEKTOVANA" iako zapis NIJE menjan -- ovo je greška u
# verifikaciji (round-trip string mismatch), ne u samom lancu. Dopunjuje se
# nazad na 6 cifara SAMO za potrebe rehash-a pri verifikaciji; upisani
# entry_hash zapisi se nikad ne diraju.
_TS_FRAC_RE = re.compile(r"(\.\d{1,6})(?=(?:[+-]\d{2}:\d{2}|Z)?$)")


def _normalize_ts_for_hash(ts: str) -> str:
    m = _TS_FRAC_RE.search(ts)
    if not m:
        return ts
    digits = m.group(1)[1:]
    if len(digits) >= 6:
        return ts
    return ts[: m.start(1)] + "." + digits.ljust(6, "0") + ts[m.end(1):]

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
    # KORAK B — Autonomni Background Action Agenti (2026-07-24)
    "AGENT_AUTONOMOUS_EXECUTION",
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

_MAX_INSERT_RETRIES = 5


def _is_unique_violation(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "23505" in msg or "duplicate key" in msg


def _build_and_insert(
    action: str,
    user_id: Optional[str],
    resource_type: Optional[str],
    resource_id: Optional[str],
    ip: Optional[str],
    metadata: Optional[dict],
) -> Optional[str]:
    """Sinhrono gradi i upisuje zapis u bazu.

    CELINA 5 (2026-07-24): "pročitaj poslednji hash pa upiši" je TOCTOU
    race pod konkurentnim pozivima -- dokazano na seq=31/32
    (docs/security/AUDIT_CHAIN_INCIDENT_2026-07-24.md). Migracija 081
    dodaje delimični UNIQUE(prev_hash) indeks za sve redove nakon seq=32;
    kad dva poziva upadnu istovremeno, gubitnik dobija 23505
    unique-violation ovde umesto da tiho upiše duplirani prev_hash --
    petlja ispod ga hvata i ponavlja sa SVEŽIM prev_hash-om."""
    from api import _get_supa
    supa = _get_supa()

    ip_hash = hashlib.sha256((ip or "").encode()).hexdigest()[:16] if ip else None
    metadata_json = json.dumps(metadata or {})

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_INSERT_RETRIES):
        prev_hash = _get_last_hash(supa)

        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()

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
            "metadata":      metadata_json,
            "created_at":    ts,
        }

        try:
            result = supa.table("audit_immutable").insert(record).execute()
            inserted = (result.data or [{}])[0]
            return inserted.get("id")
        except Exception as e:
            last_exc = e
            if not _is_unique_violation(e):
                raise
            logger.warning(
                "[AUDIT_IMMUTABLE] prev_hash sudar (konkurentan upis), pokušaj %d/%d — ponavljam",
                attempt + 1, _MAX_INSERT_RETRIES,
            )

    raise last_exc  # type: ignore[misc]


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


# CELINA 5 (2026-07-24): jedini poznat, forenzički objašnjen prekid lanca
# do sada -- dokazano TOCTOU race između dva konkurentna upisa, NE
# tampering (pun nalaz: docs/security/AUDIT_CHAIN_INCIDENT_2026-07-24.md;
# migracija 081 sprečava ponavljanje). Bez ovog izuzetka bi
# verify_chain_integrity() TRAJNO stao na seq=32 i nikad ne bi proverio
# nijedan red posle toga -- čineći alat slep za STVARNI budući tampering.
# Svaki NOVI, neobjašnjen prekid i dalje tvrdo zaustavlja proveru.
_KNOWN_EXPLAINED_BREAKS: dict[int, str] = {
    32: "TOCTOU race dva konkurentna upisa (2026-07-18T21:35:17, razlika "
        "2.6ms) — oba pročitala isti prev_hash pre commit-a. Nije tampering.",
}


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
        return {"ok": True, "checked": 0, "broken_at_seq": None, "known_breaks": [], "message": "Tabela prazna."}

    broken_at = None
    known_breaks_hit: list[int] = []
    prev_hash = _GENESIS_HASH

    for i, row in enumerate(rows):
        expected_hash = _compute_entry_hash(
            prev_hash=prev_hash,
            user_id=row.get("user_id") or "",
            action=row.get("action") or "",
            ts=_normalize_ts_for_hash(row.get("created_at") or ""),
            resource_type=row.get("resource_type") or "",
            resource_id=row.get("resource_id") or "",
        )

        # Proveri da li prev_hash odgovara
        if row["prev_hash"] != prev_hash:
            if row["seq"] in _KNOWN_EXPLAINED_BREAKS:
                logger.warning(
                    "[AUDIT_IMMUTABLE] Poznat, objašnjen prekid na seq=%d — %s",
                    row["seq"], _KNOWN_EXPLAINED_BREAKS[row["seq"]],
                )
                known_breaks_hit.append(row["seq"])
                prev_hash = row["entry_hash"]  # re-anchor, nastavi proveru
                continue
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
            "known_breaks": known_breaks_hit,
            "message": f"Lanac je polupan na seq={broken_at}. Mogući tampering.",
        }

    message = f"Integritet lanca potvrđen za {len(rows)} zapisa."
    if known_breaks_hit:
        message += f" ({len(known_breaks_hit)} poznat objašnjen prekid preskočen, v. _KNOWN_EXPLAINED_BREAKS.)"

    return {
        "ok": True,
        "checked": len(rows),
        "broken_at_seq": None,
        "known_breaks": known_breaks_hit,
        "message": message,
    }
