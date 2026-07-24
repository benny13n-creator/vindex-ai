# -*- coding: utf-8 -*-
"""
Vindex AI — services/retention_service.py

SEC-002: Data Retention & GDPR/ZZPL Cleanup (2026-07-24).

Formalizuje retention periode koji su do sada postojali samo kao
KOMENTARISAN, nikad izvršen SQL u migracijama (043_security_bulletproof.sql,
044_anomaly_detection.sql) — "Auto-cleanup: briše zapise starije od 90 dana
(pokrenuti kao cron job)" je pisano, ali nijedan cron nikad nije pozivao taj
DELETE. Ovaj modul je taj poziv, konačno povezan sa stvarnim schedule-om
(vidi routers/... cron dispečer).

NIJE OBUHVAĆENO OVIM MODULOM, namerno:
  - predmeti/klijenti/dokumenti — čuvaju se trajno po zakonskoj obavezi
    advokata (Zakon o advokaturi), potvrđeno u routers/gdpr.py's sopstvenoj
    poruci pri brisanju naloga. Ovo NIJE tehnički propust, nego već doneta
    pravna odluka — ne dirati bez nove, eksplicitne odluke.
  - audit_immutable — arhitektonski zaštićen od DELETE/UPDATE (trigger
    protect_audit_immutable, migracija 043) po dizajnu za tamper-evidence.
    Ne postoji "retention" opcija ovde bez menjanja tog trigera, što je
    posebna, mnogo veća odluka od ovog cleanup posla.
  - usage_events, response_audit — ISPRAVKA (2026-07-24): read-only analiza
    ih je POGREŠNO označila kao "potvrđeno mrtve" (SEC-034/SEC-035-klasa) —
    greška je otkrivena tek kroz test_retention_service.py's dokumentacioni
    test, koji je pokazao da su OBE tabele ŽIVE:
      * usage_events -- IMA migraciju (migrations/009_notifications_
        analytics.sql, `public.usage_events`, originalna analiza je
        tražila obrazac bez "public." prefiksa i promašila je) i aktivno
        se koristi u routers/analytics.py, routers/product_intelligence.py,
        routers/gdpr.py (deo GDPR export-a!), routers/onboarding.py,
        routers/voice.py, api.py.
      * response_audit -- NEMA migraciju u migrations/ (samo u legacy
        supabase_setup.sql/supabase_migration_v3.sql -- ovo JESTE prava
        SEC-034-klasa netraćene šeme), ali JE aktivno korišćena
        (app/services/audit_log.py) -- originalna Bash grep komanda je
        promašila ovaj poziv zbog escaping problema u shell-u, ne zato
        što ne postoji.
    Zaključak: obe tabele su NAMERNO izostavljene iz ovog cleanup-a, ali
    razlog nije "možda su mrtve" nego "aktivno se koriste, nemaju još
    definisan retention period" -- to je zaseban, budući scoping posao,
    ne ova promena. Ne preimenovati u "dead" bilo gde u kodu/dokumentaciji.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger("vindex.retention")

SECURITY_EVENTS_RETENTION_DAYS = 90
USER_DAILY_ACTIVITY_RETENTION_DAYS = 90
AI_FORENSICS_RETENTION_DAYS = 180

# SEC-002 analiza (2026-07-24, ispravljeno): OBE tabele su aktivno korišćene
# (vidi modul docstring za dokaz) -- NAMERNO izostavljene iz ovog cleanup-a
# jer nemaju još definisan retention period, ne zato što su mrtve. Zaseban
# scoping posao pre nego što se za njih doda automatsko brisanje.
TABLES_EXCLUDED_PENDING_RETENTION_DECISION = ("usage_events", "response_audit")


async def _delete_older_than(table: str, column: str, cutoff_iso: str) -> dict:
    """Briše redove iz `table` gde je `column` < cutoff_iso. Vraća broj
    obrisanih redova ili grešku -- izolovano, jedan pad ne sme oboriti
    ostatak retention posla (isti obrazac kao api.py's cron_daily moduli)."""
    import asyncio
    from shared.deps import _get_supa

    try:
        supa = _get_supa()
        result = await asyncio.to_thread(
            lambda: supa.table(table).delete().lt(column, cutoff_iso).execute()
        )
        obrisano = len(result.data or [])
        logger.info("[RETENTION] %s: obrisano %d redova (< %s)", table, obrisano, cutoff_iso)
        return {"status": "ok", "obrisano": obrisano, "cutoff": cutoff_iso}
    except Exception as exc:
        logger.error("[RETENTION] %s: greška pri brisanju: %s", table, exc)
        return {"status": "greska", "greska": str(exc)[:200], "cutoff": cutoff_iso}


async def _cleanup_security_events() -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SECURITY_EVENTS_RETENTION_DAYS)).isoformat()
    return await _delete_older_than("security_events", "created_at", cutoff)


async def _cleanup_user_daily_activity() -> dict:
    cutoff = (date.today() - timedelta(days=USER_DAILY_ACTIVITY_RETENTION_DAYS)).isoformat()
    return await _delete_older_than("user_daily_activity", "date", cutoff)


async def _cleanup_ai_forensics() -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=AI_FORENSICS_RETENTION_DAYS)).isoformat()
    return await _delete_older_than("ai_forensics", "started_at", cutoff)


async def _cleanup_pinecone_tmp_buffers() -> dict:
    """Poziva postojeći uploaded_doc/cleanup.py::cleanup_expired() -- do sada
    pokretan samo oportunistički (na leđima novog upload-a), ovde postaje
    deo pouzdanog, zakazanog dnevnog posla."""
    import asyncio
    try:
        from uploaded_doc.cleanup import cleanup_expired
        result = await asyncio.to_thread(cleanup_expired)
        logger.info(
            "[RETENTION] Pinecone tmp_*: %d namespace-a obrisano (%d chunk-ova, %d pregledano)",
            result.get("namespaces_deleted", 0),
            result.get("chunks_deleted", 0),
            result.get("namespaces_inspected", 0),
        )
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("[RETENTION] Pinecone tmp_* cleanup greška: %s", exc)
        return {"status": "greska", "greska": str(exc)[:200]}


async def execute_retention_cleanup() -> dict:
    """
    Master retention funkcija -- poziva se iz dnevnog cron dispečera.

    Svaki korak je izolovan (try/except unutar svoje _cleanup_* funkcije) --
    greška u jednom koraku ne sprečava ostale. Vraća dict sa po-tabelu
    rezultatima plus zbirni broj obrisanih redova/objekata, u istom obliku
    kao ostali moduli u api.py's cron_daily dispečeru (status/obrisano/
    duration po stavci), radi lakog uklapanja u taj rezultat.
    """
    rezultati: dict = {}
    ukupno_obrisano = 0

    rezultati["security_events"] = await _cleanup_security_events()
    ukupno_obrisano += rezultati["security_events"].get("obrisano", 0)

    rezultati["user_daily_activity"] = await _cleanup_user_daily_activity()
    ukupno_obrisano += rezultati["user_daily_activity"].get("obrisano", 0)

    rezultati["ai_forensics"] = await _cleanup_ai_forensics()
    ukupno_obrisano += rezultati["ai_forensics"].get("obrisano", 0)

    rezultati["pinecone_tmp_buffers"] = await _cleanup_pinecone_tmp_buffers()
    ukupno_obrisano += rezultati["pinecone_tmp_buffers"].get("namespaces_deleted", 0)

    rezultati["_summary"] = {
        "ukupno_obrisano": ukupno_obrisano,
        "tabele_van_dometa": list(TABLES_EXCLUDED_PENDING_RETENTION_DECISION),
        "greske": sum(1 for k, v in rezultati.items() if isinstance(v, dict) and v.get("status") == "greska"),
    }
    return rezultati
