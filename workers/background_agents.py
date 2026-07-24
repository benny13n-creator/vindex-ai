# -*- coding: utf-8 -*-
"""
Vindex AI — workers/background_agents.py

KORAK B: Autonomni "Background" Action Agenti (2026-07-24)

Asinhroni radnik/kolektor koji pokreće registrovane agent-zadatke
(services/agent_tasks/*) za svakog korisnika sa aktivnim predmetima, sa
budžetskim limitom PO ORGANIZACIJI (kancelarija_id ako korisnik pripada
timu, inače "solo:{user_id}" -- v. _org_key_and_members).

Pozivalac: api.py's /api/cron/daily kao novi modul (isti obrazac kao
workflow eskalacije, zakon_monitoring, portal_monitoring -- svaki modul
izolovan try/except + timeout, jedna greška ne obara ostatak dnevnog
cron-a). Vidi run_background_agents() kao jedinu javnu ulaznu tačku.

Budžet: implementiran preko postojeće usage_events tabele (feature=
"background_agents", action=agent_type) umesto nove tabele -- svaka
izvršena agent-akcija je jedan red, brojanje "danas" po org članovima
sprečava da jedna firma pojede neograničen broj LLM poziva u jednom
cron ciklusu. Svako izvršenje se DODATNO upisuje u audit_immutable pod
akcijom AGENT_AUTONOMOUS_EXECUTION (nepromenjiv trag -- ko/šta/kada, v.
shared/audit_immutable.py) -- usage_events broji budžet, audit_immutable
je trag za bezbednosnu reviziju; namerno oba, različita svrha.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Callable, Optional

from shared.sentry import capture_exception as _sentry_capture

logger = logging.getLogger("vindex.background_agents")

_AGENT_TIMEOUT_SECONDS = 90
_MAX_AGENT_RUNS_PER_ORG_PER_DAY = int(os.getenv("AGENT_BUDGET_PER_ORG_DAILY", "40"))


def _agent_registry() -> dict[str, Callable]:
    # Lenji import -- izbegava cirkularnost i skuplje import-e (drafting,
    # retrieve) pri modul-load-u workers/background_agents.py.
    from services.agent_tasks import court_portal_watcher, precedents_radar
    return {
        court_portal_watcher.AGENT_TYPE: court_portal_watcher.run,
        precedents_radar.AGENT_TYPE:     precedents_radar.run,
    }


async def _get_active_user_ids(supa) -> list[str]:
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("user_id")
                .not_.in_("status", ["zatvoren", "arhiviran"])
                .execute()
        )
        return sorted({row["user_id"] for row in (r.data or []) if row.get("user_id")})
    except Exception as e:
        _sentry_capture(e)
        logger.error("[BACKGROUND_AGENTS] aktivni korisnici upit neuspešan: %s", e)
        return []


async def _org_key_and_members(user_id: str, supa) -> tuple[str, list[str]]:
    """Vraća (org_key, [user_id, ...članovi]). Solo advokat (bez tima) je
    sopstvena organizacija -- "solo:{user_id}"."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("kancelarija_clanovi")
                .select("kancelarija_id,clan_id")
                .eq("clan_id", user_id)
                .neq("status", "REMOVED")
                .maybe_single()
                .execute()
        )
        row = r.data
    except Exception:
        row = None

    if not row or not row.get("kancelarija_id"):
        return f"solo:{user_id}", [user_id]

    kid = row["kancelarija_id"]
    try:
        members_r = await asyncio.to_thread(
            lambda: supa.table("kancelarija_clanovi")
                .select("clan_id")
                .eq("kancelarija_id", kid)
                .neq("status", "REMOVED")
                .execute()
        )
        members = [m["clan_id"] for m in (members_r.data or []) if m.get("clan_id")]
    except Exception:
        members = [user_id]

    return f"kancelarija:{kid}", (members or [user_id])


async def _budget_used_today(member_user_ids: list[str], supa) -> int:
    today_iso = datetime.now(timezone.utc).date().isoformat()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("usage_events")
                .select("id", count="exact")
                .eq("feature", "background_agents")
                .in_("user_id", member_user_ids)
                .gte("created_at", today_iso)
                .execute()
        )
        return r.count or 0
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[BACKGROUND_AGENTS] budžet upit neuspešan: %s", e)
        return 0  # fail-open na budžet proveru -- ne blokira agenta zbog privremene DB greške


async def _log_execution(user_id: str, agent_type: str, meta: dict, supa) -> None:
    try:
        await asyncio.to_thread(
            lambda: supa.table("usage_events").insert({
                "user_id": user_id, "feature": "background_agents",
                "action": agent_type, "meta": meta,
            }).execute()
        )
    except Exception as e:
        logger.debug("[BACKGROUND_AGENTS] usage_events upis neuspešan (nije kritično): %s", e)

    try:
        from shared.audit_immutable import log_action
        await log_action(
            "AGENT_AUTONOMOUS_EXECUTION",
            user_id=user_id,
            resource_type="agent_task",
            resource_id=agent_type,
            metadata=meta,
        )
    except Exception as e:
        logger.debug("[BACKGROUND_AGENTS] audit_immutable upis neuspešan (nije kritično): %s", e)


async def run_background_agents(run_id: str) -> dict:
    """Glavna ulazna tačka -- poziva se iz api.py's /api/cron/daily. Vraća
    agregatni rezime; NIKAD ne baca (svaki korisnik/agent je izolovan)."""
    from shared.deps import _get_supa
    supa = _get_supa()

    rezultat = {
        "korisnika_obradjeno": 0,
        "org_budzet_iscrpljen": 0,
        "po_agentu": {},
        "greske": 0,
    }
    registry = _agent_registry()
    for agent_type in registry:
        rezultat["po_agentu"][agent_type] = {"izvrsenja": 0, "preporuke_kreirane": 0, "greske": 0}

    user_ids = await _get_active_user_ids(supa)
    if not user_ids:
        return rezultat

    org_cache: dict[str, tuple[str, list[str]]] = {}

    for user_id in user_ids:
        rezultat["korisnika_obradjeno"] += 1

        if user_id not in org_cache:
            org_key, members = await _org_key_and_members(user_id, supa)
            org_cache[user_id] = (org_key, members)
        org_key, members = org_cache[user_id]

        for agent_type, agent_fn in registry.items():
            budzet_potrosen = await _budget_used_today(members, supa)
            if budzet_potrosen >= _MAX_AGENT_RUNS_PER_ORG_PER_DAY:
                rezultat["org_budzet_iscrpljen"] += 1
                logger.info(
                    "[BACKGROUND_AGENTS] budžet iscrpljen org=%s (%d/%d) — preskačem uid=%.8s agent=%s",
                    org_key, budzet_potrosen, _MAX_AGENT_RUNS_PER_ORG_PER_DAY, user_id[:8], agent_type,
                )
                continue

            try:
                ishod = await asyncio.wait_for(agent_fn(user_id, supa), timeout=_AGENT_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                logger.error(
                    "[BACKGROUND_AGENTS] TIMEOUT agent=%s uid=%.8s (>%ds)",
                    agent_type, user_id[:8], _AGENT_TIMEOUT_SECONDS,
                )
                rezultat["po_agentu"][agent_type]["greske"] += 1
                rezultat["greske"] += 1
                continue
            except Exception as e:
                _sentry_capture(e)
                logger.error("[BACKGROUND_AGENTS] agent=%s uid=%.8s greška: %s", agent_type, user_id[:8], e)
                rezultat["po_agentu"][agent_type]["greske"] += 1
                rezultat["greske"] += 1
                continue

            ishod = ishod if isinstance(ishod, dict) else {}
            rezultat["po_agentu"][agent_type]["izvrsenja"] += 1
            rezultat["po_agentu"][agent_type]["preporuke_kreirane"] += int(ishod.get("preporuke_kreirane", 0) or 0)
            rezultat["po_agentu"][agent_type]["greske"] += int(ishod.get("greske", 0) or 0)

            await _log_execution(user_id, agent_type, {"run_id": run_id, "ishod": ishod, "org_key": org_key}, supa)

    return rezultat
