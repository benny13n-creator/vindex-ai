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
# LAMBDA008-PERF-002: run_background_agents() used to process (user, agent_type)
# pairs strictly sequentially inside api.py's own 600s asyncio.wait_for cap around
# the whole run -- as active-user count grows, later users in iteration order
# silently got fewer/no agent runs within that window, with no rotation across days
# (Red Team correction to the original finding: this cannot hang for hours, the
# outer timeout already prevents that -- the real defect is coverage, not duration).
# Bounded concurrency lets far more users fit inside the same 600s window without
# uncapped fan-out against OpenAI/DB.
_MAX_CONCURRENT_AGENT_RUNS = int(os.getenv("BACKGROUND_AGENTS_CONCURRENCY", "5"))


def _agent_modules() -> list:
    """JEDINI registar agenata (NS007: jedan spisak modula, ne dva registra). Modul sa `run(user_id, supa)` je
    legacy agent preporuka (dnevni cron); modul sa `planiraj` + `izvrsi` radi trajni autonomni rad
    (`run_autonomy_cycle`). Lenji import -- izbegava cirkularnost i skuplje import-e (drafting, retrieve) pri
    modul-load-u workers/background_agents.py."""
    from services.agent_tasks import court_portal_watcher, precedents_radar
    return [court_portal_watcher, precedents_radar]


def _agent_registry() -> dict[str, Callable]:
    return {m.AGENT_TYPE: m.run for m in _agent_modules() if callable(getattr(m, "run", None))}


def _work_agents() -> dict[str, object]:
    """Agenti trajnog rada, po `work_type` koji izvršavaju (isti spisak modula kao `_agent_registry`)."""
    return {m.WORK_TYPE: m for m in _agent_modules()
            if callable(getattr(m, "planiraj", None)) and callable(getattr(m, "izvrsi", None))}


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


async def _resolve_orgs_batched(user_ids: list[str], supa) -> dict[str, tuple[str, list[str]]]:
    """Vraća {user_id: (org_key, [clanovi])} za SVE user_ids u DVA upita
    ukupno, ne po jedan (ili dva) upita PO korisniku.

    FIX (nightly repair, 2026-07-24), Faza 3 item 11: prethodna verzija je
    zvala _org_key_and_members(user_id, supa) unutar for petlje -- 1-2
    upita PO korisniku (org_cache tada nije davao stvarnu uštedu, jer se
    svaki user_id u petlji pojavljuje tačno jednom). Sad: (1) jedan upit
    dohvata kancelarija_id za SVE korisnike odjednom, (2) jedan upit
    dohvata SVE članove SVIH pronađenih kancelarija odjednom. Solo advokat
    (bez tima) je i dalje sopstvena organizacija -- "solo:{user_id}"."""
    result: dict[str, tuple[str, list[str]]] = {}
    if not user_ids:
        return result

    try:
        membership_r = await asyncio.to_thread(
            lambda: supa.table("kancelarija_clanovi")
                .select("clan_id,kancelarija_id")
                .in_("clan_id", user_ids)
                .neq("status", "REMOVED")
                .execute()
        )
        membership_rows = membership_r.data or []
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[BACKGROUND_AGENTS] org membership batch upit neuspešan: %s", e)
        membership_rows = []

    user_to_kid = {row["clan_id"]: row["kancelarija_id"] for row in membership_rows if row.get("clan_id")}
    kancelarija_ids = sorted(set(user_to_kid.values()))

    members_by_kid: dict[str, list[str]] = {}
    if kancelarija_ids:
        try:
            all_members_r = await asyncio.to_thread(
                lambda: supa.table("kancelarija_clanovi")
                    .select("clan_id,kancelarija_id")
                    .in_("kancelarija_id", kancelarija_ids)
                    .neq("status", "REMOVED")
                    .execute()
            )
            for row in (all_members_r.data or []):
                kid = row.get("kancelarija_id")
                cid = row.get("clan_id")
                if kid and cid:
                    members_by_kid.setdefault(kid, []).append(cid)
        except Exception as e:
            _sentry_capture(e)
            logger.warning("[BACKGROUND_AGENTS] org members batch upit neuspešan: %s", e)

    for uid in user_ids:
        kid = user_to_kid.get(uid)
        if not kid:
            result[uid] = (f"solo:{uid}", [uid])
        else:
            members = members_by_kid.get(kid) or [uid]
            result[uid] = (f"kancelarija:{kid}", members)

    return result


async def _budget_used_by_org(org_to_members: dict[str, list[str]], supa) -> dict[str, dict[str, int]]:
    """Vraća {org_key: {agent_type: broj_izvrsenja_danas}} za SVE organizacije
    u JEDNOM upitu -- prethodna verzija je pozivala _budget_used_today
    posebno za SVAKOG (korisnik, agent_type) para (N x M upita). Vraćena
    mapa se u run_background_agents() dalje uvećava LOKALNO (bez novih
    upita) kako se svako izvršenje desi u toku ovog run-a."""
    all_member_ids = sorted({uid for members in org_to_members.values() for uid in members})
    today_iso = datetime.now(timezone.utc).date().isoformat()
    usage_rows: list[dict] = []
    if all_member_ids:
        try:
            r = await asyncio.to_thread(
                lambda: supa.table("usage_events")
                    .select("user_id,action")
                    .eq("feature", "background_agents")
                    .in_("user_id", all_member_ids)
                    .gte("created_at", today_iso)
                    .execute()
            )
            usage_rows = r.data or []
        except Exception as e:
            _sentry_capture(e)
            logger.warning("[BACKGROUND_AGENTS] budžet batch upit neuspešan: %s", e)
            # fail-open na budžet proveru -- ne blokira agente zbog privremene DB greške

    member_to_org: dict[str, str] = {}
    for org_key, members in org_to_members.items():
        for uid in members:
            member_to_org[uid] = org_key

    used: dict[str, dict[str, int]] = {org_key: {} for org_key in org_to_members}
    for row in usage_rows:
        org_key = member_to_org.get(row.get("user_id"))
        agent_type = row.get("action")
        if not org_key or not agent_type:
            continue
        used[org_key][agent_type] = used[org_key].get(agent_type, 0) + 1

    return used


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

    user_to_org = await _resolve_orgs_batched(user_ids, supa)
    org_to_members = {org_key: members for org_key, members in user_to_org.values()}
    budzet_po_orgu = await _budget_used_by_org(org_to_members, supa)

    sem = asyncio.Semaphore(_MAX_CONCURRENT_AGENT_RUNS)

    async def _process_one(user_id: str, agent_type: str, agent_fn) -> None:
        org_key, _members = user_to_org[user_id]
        async with sem:
            # Reserve the budget slot BEFORE awaiting the agent call, not after --
            # under concurrency, checking then incrementing only after the call
            # returns would let multiple in-flight tasks for the same org all pass
            # the check before any of them recorded usage (TOCTOU). This dict is
            # only ever mutated between two consecutive `await`s of the SAME
            # coroutine step (no `await` between the check and the increment
            # below), which asyncio's single-threaded event loop makes atomic.
            org_budget = budzet_po_orgu.setdefault(org_key, {})
            budzet_potrosen = org_budget.get(agent_type, 0)
            if budzet_potrosen >= _MAX_AGENT_RUNS_PER_ORG_PER_DAY:
                rezultat["org_budzet_iscrpljen"] += 1
                logger.info(
                    "[BACKGROUND_AGENTS] budžet iscrpljen org=%s (%d/%d) — preskačem uid=%.8s agent=%s",
                    org_key, budzet_potrosen, _MAX_AGENT_RUNS_PER_ORG_PER_DAY, user_id[:8], agent_type,
                )
                return
            org_budget[agent_type] = budzet_potrosen + 1

            try:
                ishod = await asyncio.wait_for(agent_fn(user_id, supa), timeout=_AGENT_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                logger.error(
                    "[BACKGROUND_AGENTS] TIMEOUT agent=%s uid=%.8s (>%ds)",
                    agent_type, user_id[:8], _AGENT_TIMEOUT_SECONDS,
                )
                rezultat["po_agentu"][agent_type]["greske"] += 1
                rezultat["greske"] += 1
                return
            except Exception as e:
                _sentry_capture(e)
                logger.error("[BACKGROUND_AGENTS] agent=%s uid=%.8s greška: %s", agent_type, user_id[:8], e)
                rezultat["po_agentu"][agent_type]["greske"] += 1
                rezultat["greske"] += 1
                return

            ishod = ishod if isinstance(ishod, dict) else {}
            rezultat["po_agentu"][agent_type]["izvrsenja"] += 1
            rezultat["po_agentu"][agent_type]["preporuke_kreirane"] += int(ishod.get("preporuke_kreirane", 0) or 0)
            rezultat["po_agentu"][agent_type]["greske"] += int(ishod.get("greske", 0) or 0)

            await _log_execution(user_id, agent_type, {"run_id": run_id, "ishod": ishod, "org_key": org_key}, supa)

    rezultat["korisnika_obradjeno"] = len(user_ids)
    tasks = [
        _process_one(user_id, agent_type, agent_fn)
        for user_id in user_ids
        for agent_type, agent_fn in registry.items()
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    return rezultat


# ══════════════════════════════════════════════════════════════════════════════
# NS007 — trajni autonomni rad (A2 Prepare / A3 Organize)
# ══════════════════════════════════════════════════════════════════════════════
# Pozivalac: SAMO uska ulazna tačka `POST /api/cron/autonomy` (routers/autonomy.py), posle atomskog zauzimanja
# prozora. Dnevni cron i dalje zove `run_background_agents` (legacy preporuke) — dva toka ne dele poslove.
#
#   1. PLAN       svaki agent trajnog rada vraća kandidate + poništene okidače. 0 poziva modela.
#   2. UPIS       jedan logički okidač = jedan red (UNIQUE user_id + dedupe_key); nova verzija istog okidača
#                 zastareva staru (SUPERSEDED, ne briše se); poništen okidač zastareva QUEUED/READY.
#   3. IZVRŠENJE  posao se zauzima ISKLJUČIVO kroz `autonomy_claim_work_item` (zakup + rezervacija budžeta).
#                 Ako zauzimanje ne uspe iz bilo kog razloga, izvršilac se NE poziva (nema poziva modela).
#   4. REZULTAT   upisuje ga samo vlasnik zakupa, u istoj naredbi sa READY_FOR_REVIEW. `NeuspehPosla` = FAILED
#                 (ne ponavlja se); drugi izuzetak = prolazno (zakup ističe, najviše max_attempts).
# Ništa se ne šalje napolje. Nijedan radni proizvod ne ide u memoriju znanja.

_AUTONOMY_MAX_POSLOVA_PO_CIKLUSU = int(os.getenv("AUTONOMY_MAX_ITEMS_PER_CYCLE", "25"))
_AUTONOMY_TIMEOUT_POSLA_S = int(os.getenv("AUTONOMY_ITEM_TIMEOUT_SECONDS", "120"))


async def _izvrsivi_poslovi(supa, tipovi: list[str]) -> list[dict]:
    if not tipovi:
        return []
    r = await asyncio.to_thread(
        lambda: supa.table("autonomy_work_items")
            .select("id,user_id,predmet_id,work_type,trigger_ref,status,lease_expires_at")
            .in_("status", ["QUEUED", "RUNNING"])
            .in_("work_type", tipovi)
            .order("queued_at")
            .limit(_AUTONOMY_MAX_POSLOVA_PO_CIKLUSU * 4)
            .execute()
    )
    sada = datetime.now(timezone.utc).isoformat()
    return [x for x in (r.data or [])
            if x["status"] == "QUEUED" or (x.get("lease_expires_at") and str(x["lease_expires_at"]) < sada)]


async def _zabelezi_upotrebu(supa, item: dict, run_id: str) -> bool:
    """usage_events red za plaćeno autonomno izvršenje (isti obrazac kao legacy agenti, feature='autonomy').
    Vraća False kad upis ne uspe — pozivalac to BROJI, ne tvrdi uspeh."""
    try:
        await asyncio.to_thread(lambda: supa.table("usage_events").insert({
            "user_id": item["user_id"], "feature": "autonomy", "action": item["work_type"],
            "meta": {"work_item_id": item["id"], "run_id": run_id, "attempt": item.get("attempt_count")},
        }).execute())
        return True
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[AUTONOMY] usage_events upis nije uspeo work=%s: %s", item.get("id"), type(e).__name__)
        return False


async def run_autonomy_cycle(run_id: str) -> dict:
    """Jedan ciklus trajnog autonomnog rada. Vraća sažetak (samo brojevi i bezbedni kodovi, bez sadržaja)."""
    from services import autonomy as au
    from shared.deps import _get_supa
    supa = _get_supa()
    agenti = _work_agents()
    rez = {"run_id": run_id, "planirano": 0, "duplikata": 0, "zastarelo": 0, "zauzeto": 0, "spremno": 0,
           "neuspeh": 0, "prolazno": 0, "budzet_iscrpljen": 0, "budzet_nepoznat": 0, "nije_zauzeto": 0,
           "dead_letter": 0, "planer_greske": 0, "zauzimanje_greska": 0,
           "upotreba_nije_zabelezena": 0}

    # 1–2. plan + upis
    for work_type, agent in agenti.items():
        try:
            plan = await agent.planiraj(supa)
        except Exception as e:
            _sentry_capture(e)
            logger.error("[AUTONOMY] planer %s pao run=%s: %s", work_type, run_id, type(e).__name__)
            rez["planer_greske"] += 1
            continue
        for p in plan.get("ponisteni", []):
            rez["zastarelo"] += await au.zastareli(supa, p["user_id"], p["predmet_id"], work_type, p["trigger_ref"], "")
        for k in plan.get("kandidati", []):
            ishod = await au.upisi_kandidata(supa, k)
            if ishod["ishod"] == "QUEUED":
                rez["planirano"] += 1
            else:
                rez["duplikata"] += 1
            rez["zastarelo"] += await au.zastareli(supa, k["user_id"], k["predmet_id"], work_type, k["trigger_ref"], k["dedupe_key"])

    # 3–4. izvršenje
    poslovi = await _izvrsivi_poslovi(supa, list(agenti))
    for posao in poslovi[:_AUTONOMY_MAX_POSLOVA_PO_CIKLUSU]:
        vlasnik = au.novi_vlasnik()
        try:
            z = await au.zauzmi_posao(supa, posao["id"], vlasnik)
        except Exception as e:
            _sentry_capture(e)
            logger.error("[AUTONOMY] zauzimanje nije uspelo work=%s: %s — izvršilac se NE poziva", posao["id"], type(e).__name__)
            rez["zauzimanje_greska"] += 1
            continue
        ishod = z.get("ishod")
        if ishod != "CLAIMED":
            kljuc = {"BUDGET_EXHAUSTED": "budzet_iscrpljen", "BUDGET_UNKNOWN": "budzet_nepoznat",
                     "DEAD_LETTER": "dead_letter"}.get(ishod, "nije_zauzeto")
            rez[kljuc] += 1
            continue
        rez["zauzeto"] += 1
        item = z["item"]
        agent = agenti[item["work_type"]]
        try:
            proizvod = await asyncio.wait_for(agent.izvrsi(supa, item), timeout=_AUTONOMY_TIMEOUT_POSLA_S)
        except au.NeuspehPosla as n:
            await au.oznaci_neuspeh(supa, item["id"], vlasnik, n.kod)
            rez["neuspeh"] += 1
            continue
        except Exception as e:
            _sentry_capture(e)
            logger.warning("[AUTONOMY] prolazna greška work=%s: %s — zakup ističe, ponovni pokušaj je ograničen",
                           item["id"], type(e).__name__)
            rez["prolazno"] += 1
            continue
        if await au.sacuvaj_rezultat(supa, item["id"], vlasnik, **proizvod):
            rez["spremno"] += 1
            # Računovodstvo POSLE trajnog upisa rezultata: budžet je već rezervisan u samoj stavci (izvor istine),
            # pa neuspeo upis u usage_events ne vraća posao u red i ne pokreće ga ponovo — samo se broji.
            if item.get("cost_class") == "PAID" and not await _zabelezi_upotrebu(supa, item, run_id):
                rez["upotreba_nije_zabelezena"] += 1
        else:
            rez["nije_zauzeto"] += 1   # zakup je u međuvremenu istekao/preuzet: rezultat se NE upisuje preko tuđeg
    return rez
