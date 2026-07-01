# -*- coding: utf-8 -*-
"""
Vindex AI 2.0 — services/decision_log.py

Decision Log: beleži svaku advokatsku odluku sa kontekstom i alternativama.
Core infrastruktura za Legal Operating Memory — organizaciona inteligencija.

Tabela: decision_log (migracija 036_decision_log.sql)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("vindex.decision_log")


# ─── Tipovi akcija ────────────────────────────────────────────────────────────

class DecisionType:
    STRATEGIJA_ODABRANA  = "strategija_odabrana"
    DOKUMENT_PRILOZEN    = "dokument_prilozen"
    ROK_DODAT            = "rok_dodat"
    PODNESAK_GENERISAN   = "podnesak_generisan"
    ANALIZA_POKRENUTA    = "analiza_pokrenuta"
    PREDMET_OTVOREN      = "predmet_otvoren"
    ROCISTE_ZAKAZANO     = "rociste_zakazano"
    ARGUMENT_ODABRAN     = "argument_odabran"
    NAGODBA_RAZMATRANA   = "nagodba_razmatrana"
    VESTACENJE_ZATRAZENO = "vestacenje_zatrazeno"


# ─── Core funkcije ────────────────────────────────────────────────────────────

async def log_decision(
    user_id:    str,
    akcija:     str,
    predmet_id: Optional[str]      = None,
    kontekst:   dict[str, Any]     = None,
    alternative: list[str]         = None,
    urgentnost: str                = "normalna",
) -> bool:
    """
    Beleži advokatsku odluku u decision_log tabelu.

    Gracefully ignoriše grešku ako tabela još ne postoji —
    migracija 036_decision_log.sql mora biti pokrenuta u Supabase.

    Vraća True ako je uspešno zapisano, False ako tabela nije dostupna.
    """
    try:
        from shared.deps import _get_supa
        supa = _get_supa()

        row: dict[str, Any] = {
            "user_id":    user_id,
            "akcija":     akcija,
            "kontekst":   kontekst or {},
            "alternative": alternative or [],
            "urgentnost": urgentnost,
        }
        if predmet_id:
            row["predmet_id"] = predmet_id

        await asyncio.to_thread(
            lambda: supa.table("decision_log").insert(row).execute()
        )
        logger.debug("[DecisionLog] %s uid=%.8s predmet=%s", akcija, user_id, predmet_id)
        return True

    except Exception as exc:
        err = str(exc)
        if "does not exist" in err or "relation" in err.lower():
            logger.debug("[DecisionLog] Tabela decision_log ne postoji — pokrenite migraciju 036.")
        else:
            logger.warning("[DecisionLog] Greška pri beleženju odluke: %s", exc)
        return False


async def get_decisions(
    user_id:    str,
    predmet_id: Optional[str] = None,
    limit:      int           = 20,
) -> list[dict]:
    """
    Dohvata poslednjih N odluka korisnika, opcionalno filtrirano po predmetu.
    Vraća praznu listu ako tabela ne postoji ili nema podataka.
    """
    try:
        from shared.deps import _get_supa
        supa = _get_supa()

        query = (
            supa.table("decision_log")
            .select("id,akcija,kontekst,alternative,urgentnost,created_at,predmet_id")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(min(limit, 100))
        )
        if predmet_id:
            query = query.eq("predmet_id", predmet_id)

        res = await asyncio.to_thread(lambda: query.execute())
        return res.data or []

    except Exception as exc:
        logger.debug("[DecisionLog] get_decisions greška: %s", exc)
        return []


async def get_decision_summary(user_id: str, predmet_id: Optional[str] = None) -> dict:
    """
    Vraća agregirani pregled odluka — ukupno po tipu akcije.
    Korisno za Organization Intelligence graph.
    """
    decisions = await get_decisions(user_id, predmet_id, limit=500)

    by_type: dict[str, int] = {}
    hitnih = 0

    for d in decisions:
        akcija = d.get("akcija", "nepoznata")
        by_type[akcija] = by_type.get(akcija, 0) + 1
        if d.get("urgentnost") == "hitna":
            hitnih += 1

    return {
        "ukupno":   len(decisions),
        "hitnih":   hitnih,
        "po_tipu":  by_type,
        "poslednjih_7_dana": sum(
            1 for d in decisions
            if _within_days(d.get("created_at", ""), 7)
        ),
    }


def _within_days(ts_str: str, days: int) -> bool:
    """Proverava da li je timestamp unutar zadatog broja dana."""
    try:
        from datetime import timedelta
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).days <= days
    except Exception:
        return False


# ─── Batch log (za pipeline korak) ───────────────────────────────────────────

async def log_pipeline_event(
    user_id:    str,
    predmet_id: str,
    eventi:     list[dict],
) -> None:
    """
    Batch log više događaja odjednom — efikasno za Case Pipeline.
    eventi: [{"akcija": str, "kontekst": dict}, ...]
    """
    if not eventi:
        return

    try:
        from shared.deps import _get_supa
        supa = _get_supa()

        rows = [
            {
                "user_id":    user_id,
                "predmet_id": predmet_id,
                "akcija":     e.get("akcija", "pipeline_korak"),
                "kontekst":   e.get("kontekst", {}),
                "alternative": e.get("alternative", []),
                "urgentnost": e.get("urgentnost", "normalna"),
            }
            for e in eventi
        ]

        await asyncio.to_thread(
            lambda: supa.table("decision_log").insert(rows).execute()
        )
        logger.info("[DecisionLog] batch log: %d eventi za predmet %s", len(rows), predmet_id)

    except Exception as exc:
        logger.debug("[DecisionLog] batch log greška: %s", exc)
