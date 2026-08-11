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
    # Final Beta Gate F13 (MEDIUM): "predmet_delete" is a RESERVED entry --
    # confirmed via exhaustive @router.delete/@app.delete grep (2026-08-08)
    # that no case-delete endpoint exists anywhere in the codebase today.
    # Left in the allowlist (harmless -- log_action() only inserts when
    # explicitly called with this action string) so a future delete
    # endpoint doesn't need to remember to add it here too; if one is ever
    # added, it MUST call log_action("predmet_delete", ...) itself, the
    # same gap this mission just closed for klijent_delete.
    "predmet_create", "predmet_update", "predmet_delete", "predmet_view",
    # Dokumenti
    # "dokument_delete" is the same kind of reserved entry -- no document-
    # delete endpoint exists today either (only evidence-item delete,
    # routers/evidence.py, and note delete, api.py -- neither is "the
    # document").
    "dokument_upload", "dokument_delete", "dokument_view", "dokument_download",
    # Program Intake Sprint 004 (2026-08-05) — Human Review Orchestration.
    # Svaka ljudska odluka u intake review toku mora imati audit zapis
    # (misija Faza 5). "entity_corrected" pokriva 10-sekundnu ispravku
    # (routers/smart_intake.py::correct_entity — ranije bez audit poziva
    # uopšte, Sprint 004 Fork A §5); "dokument_review_resolved" pokriva
    # kanonski resolve_review() poziv (ranije nije ni postojao poziv koji
    # bi ovo trebalo da loguje — nova, jedina kapija za "review razrešen").
    "entity_corrected", "dokument_review_resolved",
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
    # Mission Ledger (2026-08-03) — Audit Link Completion (Phase 4). Ove
    # akcije su već povezane u shared/ai_provenance.py's canonical wrapper
    # (Mission Atlas) — dodavanje ovde zatvara poslednju kariku (Event/AI
    # poziv → AI Provenance red → OVAJ audit red, isti correlation_id) bez
    # menjanja bilo kog AI ponašanja. Ranije dokumentovano kao Project
    # Sentinel's SENT-004 / Mission Atlas's ATLAS-006, sada zatvoreno.
    "strategija_generisana", "copilot_analiza_predmeta",
    "zadaci_ai_analiza_complete", "briefing_generisan",
    # Mission Migration (2026-08-03) — Canonical AI Infrastructure Adoption.
    # Preostali Copilot handleri koji mutiraju stvarne podatke na osnovu AI
    # ekstrakcije (rok/beleška/klijent/naplata/plan) + Court Predictor,
    # Drafting, Evidence klasifikacija, upload AI analiza — isti obrazac kao
    # iznad, samo prošireno na sledeći sloj AI funkcionalnosti.
    "copilot_plan_predmeta", "copilot_dodaj_rok", "copilot_kreiraj_belesku",
    "copilot_povezi_klijenta", "copilot_naplati_radnju",
    "court_predictor_analiza", "drafting_generisan",
    "evidence_klasifikacija", "dokument_ai_analiza_complete",
    # Project Phoenix (2026-08-03) — Enterprise Reliability & Failure
    # Recovery Validation. Zatvara pravu tihu izgubljenu-podatak rupu:
    # nightly proactive_alerts insert je ranije bio DEBUG-only log sa nula
    # pokušaja; sada ima retry + ovaj durable audit trag ako i posle
    # ponavljanja ne uspe. SUPERSEDED (Program Alpha, 2026-08-04) — kept in
    # this allowlist only so any already-written historical audit rows using
    # this action name remain valid; no code path generates it anymore (see
    # "proactive_alert_insert_failed" below, which generalizes this exact
    # pattern to all 12 proactive_alerts call sites, not just the nightly one).
    "nightly_alert_insert_failed",
    # Program Alpha (2026-08-04) — canonical shared/proactive_alerts.py::
    # create_proactive_alert() generalizes Phoenix's nightly-only retry+audit
    # pattern above to every proactive_alerts call site platform-wide.
    "proactive_alert_insert_failed",
    # Phase 8 (Mission Migration remainder, closed by Project Phoenix
    # 2026-08-03 since its own reliability work touched these exact call
    # sites): main.py::ask_agent and Drafting's generate/analiza calls.
    "copilot_pravno_pitanje", "drafting_nacrt", "drafting_analiza",
    # Mission Keystone (2026-08-04) — Phase 2 fresh metric recalculation
    # found routers/dokument.py::dokument_pitanje as a second, real,
    # unwrapped ask_agent call path that Mission Migration/Project Phoenix's
    # narrower inventories both missed (both only traced copilot.py's
    # delegation into ask_agent).
    "dokument_pitanje",
    # Program Delta, Sprint 001 (2026-08-05) — Canonical Case Evolution
    # Engine. Every consequence the canonical dispatcher (services/
    # case_evolution.py::handle_case_changed) completes gets its own audit
    # row — the mechanism Task 5 requires ("audit postoji" for every step).
    "case_evolution_consequence_completed",
    # Program Delta, Sprint 002 (2026-08-05) — Canonical Event Migration I.
    # REVIEW_REJECTED's own canonical definition (this sprint) requires a
    # domain-specific audit row, same shape as "dokument_review_resolved"
    # above but for the mutually-exclusive alternate outcome.
    "dokument_review_rejected",
    # Program Omega, Sprint 002 (2026-08-06) — Case Intelligence Aggregation
    # Engine. Domain-specific audit row for refresh_case_intelligence(),
    # carrying the full sourced summary (documents added, new contradictions,
    # risks, deadlines) in metadata — distinct from the generic
    # "case_evolution_consequence_completed" row every consequence gets.
    "case_intelligence_refreshed",
    # Program Omega, Sprint 003 (2026-08-06) — Canonical Action Engine.
    # Domain-specific audit row for refresh_case_actions(), carrying
    # created/updated/closed counts — every action lifecycle transition is
    # traceable back to the event that caused it.
    "case_action_refreshed",
    # Program Intake Sprint 006 (2026-08-05) — Canonical Case Assimilation.
    # Phase 1 audit finding: finalize_intake_job (routers/smart_intake.py)
    # had ZERO audit calls for document-into-case registration, unlike
    # Pipeline A's per-case upload (api.py), which always logged
    # "dokument_upload". This closes that gap for the Smart Intake path.
    "document_assimilated",
    # Night War Room V11-V32 (2026-08-09) — destruktivne poslovne operacije.
    # F-V11-001: 18 destruktivnih ruta nije dospevalo ni u kanonski
    # audit_immutable (nijedna nije zvala log_action) ni u middleware access log
    # (allowlist u shared/audit.py je pisan protiv "/api/billing", a billing
    # router ima prefiks "/billing" -- startswith nikad ne pogađa). Cela klasa
    # "korisnik je obrisao poslovni zapis" nije postojala u registru.
    #
    # Ovaj commit SAMO registruje akcije; pozivi se dodaju po grupama (V34-V39)
    # tek pošto je za svaku rutu source-dokazano gde tačno leži uspeh poslovne
    # mutacije. log_action() ionako tiho vraća None za neregistrovanu akciju, pa
    # registracija bez poziva ne menja nijedno postojeće ponašanje.
    #
    # user_webhook_delete vs integration_webhook_delete su NAMERNO dve akcije:
    # rute brišu iz dve različite tabele (user_webhooks / webhooks) sa istim
    # prostorom ID-eva, pa bi jedna akcija dala forenzički nerazlučive zapise.
    "rociste_delete", "komentar_delete", "zadatak_delete", "knowledge_delete",
    "client_portal_upload_delete", "billing_entry_delete", "faktura_create",
    "recurring_template_delete", "user_webhook_delete",
    "integration_webhook_delete", "tarifa_update",
    # V39-A2 (2026-08-10) — ispravka V32/V33 plana. V33 je izostavio
    # "saradnik_uklonjen" na osnovu tvrdnje da akcija "već postoji"; ta tvrdnja
    # je bila tačna za klijent_create i predmet_create, ali NE i za ovu. Bez
    # unosa ovde log_action("saradnik_uklonjen", ...) tiho vraća None, pa bi
    # poziv u routers/saradnja.py::ukloni_saradnika izgledao implementirano a u
    # produkciji ne bi upisao ništa. Registracija ostaje inertna dok V39-B ne
    # doda poziv; postojeći domenski zapis u `saradnja_audit` je nezavisan i
    # ostaje netaknut (OPTION A: log_action se DODAJE, ne zamenjuje).
    "saradnik_uklonjen",
    # V40-B1 (2026-08-10) — F-V38-001 posledica. `tarifa_update` pokriva samo
    # UPDATE i INSERT granu put_klijent_tarifa; uklanjanje tarife je zaseban
    # destruktivni poslovni događaj sa sopstvenim ranim return-om, i do V40-A
    # njegov uspeh uopšte nije bio dokaziv (DELETE rezultat se odbacivao).
    # Emitovanje "tarifa_update" za brisanje tvrdilo bi izmenu iznosa koja se
    # nije desila, pa je zasebna akcija jedina istinita opcija. Registracija je
    # inertna dok V40-B2 ne doda poziv.
    "tarifa_delete",
    # Provider Fabric V1.1 (2026-08-10) — kanonski AI poziv kroz AIGateway.
    # Bez ovog unosa log_action tiho vraća None, pa bi telemetrija fabrica bila
    # no-op (isti obrazac koji je F-V39-001 već jednom otkrio kod
    # saradnik_uklonjen). Metadata nosi SAMO ko/šta/koliko -- provider, model,
    # task, tokeni, latencija, klasa greške. Ni prompt ni odgovor NIKAD ne ulaze
    # u append-only ledger iz kog se sadržaj ne može obrisati.
    "ai_fabric_call",
    # Governance Wave 9 (2026-08-11), §11 — odluka Response Firewall-a.
    # Do sada su BLOCK i ESCALATE samo LOGOVANI: log se rotira, ne vezuje se za
    # korisnika i ne može se pokazati trećoj strani, pa „firewall je odbio
    # odgovor modela" nije bila dokaziva tvrdnja. Bez ovog unosa log_action
    # tiho vraća None (isti obrazac koji je F-V39-001 već otkrio kod
    # saradnik_uklonjen), pa bi ceo mehanizam izgledao implementirano a ne bi
    # upisivao ništa.
    #
    # NAMERNO SAMO BLOCK/ESCALATE dolaze ovde. ALLOW se dešava na svakom AI
    # pozivu, a ovaj ledger je hash-lanac sa UNIQUE(prev_hash) (migracija 081):
    # vezivanje za tu frekvenciju bi normalan saobraćaj pretvorilo u trajni
    # izvor prev_hash sudara i usporilo baš upis BLOCK zapisa. ALLOW ima svoj
    # deterministički red u AI Provenance tabeli, sa istim correlation_id-em.
    #
    # Metadata nosi SAMO odluku, naše sopstvene razloge, operaciju, provajdera,
    # model, correlation_id i vreme — nikad sirov odgovor modela, sadržaj
    # dokumenta ni tekst prompta.
    "ai_response_firewall_decision",
}


# ─── Javni API ────────────────────────────────────────────────────────────────

async def log_action(
    action: str,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip: Optional[str] = None,
    metadata: Optional[dict] = None,
    correlation_id: Optional[str] = None,
) -> Optional[str]:
    """
    Upisuje nepromenjivi zapis u audit_immutable tabelu.

    Vraća ID upisanog zapisa, ili None ako upis nije uspeo.
    Greška u audit-u NIKAD ne blokira glavni zahtev.

    correlation_id (Mission Ledger, 2026-08-03): ako nije eksplicitno
    prosleđen, čita se iz shared/ai_provenance.py's request-scoped konteksta
    — isti id koji Event Bus/AI Provenance već koriste za istu logičku
    operaciju, tako da postojeći pozivi (bez izmene) automatski dobijaju
    kontinuitet (Phase 2, Correlation ID Continuity).
    """
    if action not in AUDITABLE_ACTIONS:
        logger.debug("[AUDIT_IMMUTABLE] akcija=%s nije u skupu praćenih akcija — preskačem", action)
        return None

    if correlation_id is None:
        try:
            from shared.ai_provenance import current_correlation_id
            correlation_id = current_correlation_id()
        except Exception:
            correlation_id = None

    try:
        entry = await asyncio.to_thread(_build_and_insert, action, user_id, resource_type, resource_id, ip, metadata, correlation_id)
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
    correlation_id: Optional[str] = None,
) -> Optional[str]:
    """Sinhrona verzija za ne-async kontekste."""
    if action not in AUDITABLE_ACTIONS:
        return None
    if correlation_id is None:
        try:
            from shared.ai_provenance import current_correlation_id
            correlation_id = current_correlation_id()
        except Exception:
            correlation_id = None
    try:
        return _build_and_insert(action, user_id, resource_type, resource_id, ip, metadata, correlation_id)
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


def _is_missing_column_error(exc: Exception) -> bool:
    """Mission Ledger (2026-08-03): Postgres undefined_column SQLSTATE
    (42703) or its typical message shape — used to decide whether a
    correlation_id-bearing insert should fall back to the pre-migration-090
    column set. Deliberately narrow (unlike a bare `except Exception`) so a
    genuine, unrelated DB error (connection reset, etc.) still propagates
    immediately without a pointless extra attempt."""
    msg = str(exc).lower()
    return "42703" in msg or "does not exist" in msg


def _build_and_insert(
    action: str,
    user_id: Optional[str],
    resource_type: Optional[str],
    resource_id: Optional[str],
    ip: Optional[str],
    metadata: Optional[dict],
    correlation_id: Optional[str] = None,
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
            # Migracija 090 (drafted, not yet applied) dodaje 'correlation_id'
            # kolonu — pokušaj prvo sa njom (van hash-a, ne utiče na
            # _compute_entry_hash iznad, isti tretman kao 'metadata'). Padni
            # na upis bez nje SAMO ako je greška specifično "kolona ne
            # postoji" (_is_missing_column_error) — bilo koja druga greška
            # (npr. konekcija) propagira odmah, bez besmislenog dodatnog
            # pokušaja (isto ponašanje kao pre ove izmene za sve ostale
            # slučajeve grešaka).
            try:
                result = supa.table("audit_immutable").insert({**record, "correlation_id": correlation_id}).execute()
            except Exception as _wide_exc:
                if not _is_missing_column_error(_wide_exc):
                    raise
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
