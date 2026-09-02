# -*- coding: utf-8 -*-
"""
Vindex AI — Notification Engine

GET    /notifications               — lista obaveštenja (auto-refresh > 6h)
POST   /notifications/refresh       — forsiraj regeneraciju
PATCH  /notifications/{id}/read     — označi kao pročitano
PATCH  /notifications/read-group    — označi SVE stavke grupisane notifikacije kao pročitane
PATCH  /notifications/read-all      — označi sva kao pročitana
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.attention_priority import NOTIFICATIONS_TO_CANONICAL, CANONICAL_ORDER
from shared.deps import _get_supa, get_current_user
from shared.rate import limiter
# FAZA 6.2 (INV-2): notifikacija je izvrsiva posledica -- gura tvrdnju o roku
# advokatu. Nepotvrdjen AI opazen rok ne sme da je proizvede. Isti kanonski
# gejt kao email i SMS, fail-closed.
from shared.rokovi import filtriraj_izvrsive as _filtriraj_izvrsive
from shared.rok_potvrda import potvrdjeni_ids as _potvrdjeni_ids

logger = logging.getLogger("vindex.notifications")
router = APIRouter(tags=["notifications"])

_REFRESH_HOURS = 6

# ── Tipovi notifikacija sa prioritetima i ikonama ─────────────────────────────
NOTIF_TIPOVI: dict[str, dict] = {
    # Rokovi
    "rok":          {"label": "Nadolazeći rok",         "priority": "normal",  "icon": "calendar"},
    "hitan_rok":    {"label": "Hitan rok",               "priority": "high",    "icon": "calendar-alert"},
    # BLACKSWAN-CRIT-002 (Operation Black Swan, Mission 001, Scenario 15): a deadline
    # that passed while the lawyer was away used to just vanish -- _generate_notifications
    # only ever queried upcoming rokovi, then deleted every unread "rok"/"hitan_rok" row on
    # its next regeneration, with nothing for a since-passed deadline to regenerate INTO.
    "rok_propusten":{"label": "Propušten rok",           "priority": "urgent",  "icon": "alarm"},
    "rok_7":        {"label": "Rok za 7 dana",           "priority": "normal",  "icon": "calendar"},
    "rok_3":        {"label": "Rok za 3 dana",           "priority": "high",    "icon": "calendar-alert"},
    "rok_1":        {"label": "Rok SUTRA",               "priority": "urgent",  "icon": "alarm"},
    # Ročišta
    "rociste_sutra":  {"label": "Ročište SUTRA",         "priority": "urgent",  "icon": "gavel"},
    "rociste_nedelja":{"label": "Ročište za 7 dana",     "priority": "normal",  "icon": "gavel"},
    # Predmeti
    "neaktivnost":    {"label": "Neaktivan predmet",     "priority": "low",     "icon": "sleep"},
    "predmet_zatvoren":{"label": "Predmet zatvoren",     "priority": "low",     "icon": "archive"},
    # Saradnja
    "saradnja_predmet": {"label": "Dodeljen predmet",    "priority": "high",    "icon": "users"},
    "saradnja_komentar":{"label": "Novi komentar saradnika","priority": "normal","icon": "message-square"},
    # Inbox
    "inbox_poruka":   {"label": "Nova poruka u inboxu",  "priority": "normal",  "icon": "mail"},
    # Billing / SEF
    "faktura_kasnjenje":{"label": "Faktura kasni > 30 dana","priority": "high", "icon": "alert-circle"},
    "faktura_placena":  {"label": "Faktura plaćena",     "priority": "normal",  "icon": "check-circle"},
    "sef_status":       {"label": "SEF status fakture",  "priority": "normal",  "icon": "file-check"},
    # AI
    "ai_analiza_gotova":{"label": "AI analiza završena", "priority": "normal",  "icon": "cpu"},
}

# Program Omega Sprint 006 (2026-08-06): derived from the canonical model
# (shared/attention_priority.py) instead of an independently-maintained
# {word: number} dict — same values as before (urgent=0...info=4), now
# provably a translation, not a parallel copy.
PRIORITY_ORDER = {word: CANONICAL_ORDER[canon] for word, canon in NOTIFICATIONS_TO_CANONICAL.items()}


def _u_tihom_periodu() -> bool:
    """Tihi period: 22:00–08:00 — push se ne šalje (osim urgent)."""
    h = datetime.now().hour
    return h >= 22 or h < 8


def _grupiraj_notifikacije(notifs: list[dict]) -> list[dict]:
    """Grupiši rok_* notifikacije istog tipa u jednu sa brojem."""
    grupe: dict[str, list[dict]] = defaultdict(list)
    single: list[dict] = []

    for n in notifs:
        tip = n.get("tip", "ostalo")
        if tip.startswith("rok") or tip.startswith("hitan_rok") or tip.startswith("rociste"):
            grupe[tip].append(n)
        else:
            single.append(n)

    result = list(single)
    for tip, items in grupe.items():
        if len(items) == 1:
            result.append(items[0])
        else:
            tip_label = NOTIF_TIPOVI.get(tip, {}).get("label", tip)
            grouped_item = {
                **items[0],
                "naslov": f"{len(items)} × {tip_label}",
                "grouped_count": len(items),
                "grouped_items": [i.get("naslov", "") for i in items[:5]],
                # Final Beta Gate F21 (MEDIUM): mark-read only ever PATCHed
                # items[0].id (the representative row this dict is spread
                # from) -- the other N-1 rows never got procitano=true
                # server-side. The group re-collapsed onto the same item[0]
                # on the next load so it LOOKED read, but a lawyer dismissing
                # "3 × Hitan rok" never individually saw the other 2
                # deadlines, whose rows stayed unread until the next ≤6h
                # regen cycle silently deleted/reinserted them. Frontend now
                # PATCHes every id in this list, not just the representative one.
                "ids": [i.get("id") for i in items if i.get("id")],
            }
            result.append(grouped_item)

    result.sort(key=lambda n: PRIORITY_ORDER.get(
        n.get("prioritet") or NOTIF_TIPOVI.get(n.get("tip", ""), {}).get("priority", "normal"),
        2
    ))
    return result


async def trigger_notifikacija(
    supa,
    user_id: str,
    tip: str,
    naslov: str,
    tekst: str,
    predmet_id: str | None = None,
    priority: str | None = None,
) -> None:
    """
    Kreira notifikaciju u bazi. Pozivati iz billing.py, saradnja.py, itd.
    Push se ne šalje u tihom periodu (22:00–08:00) osim za urgent prioritet.
    """
    tip_info = NOTIF_TIPOVI.get(tip, {})
    p = priority or tip_info.get("priority", "normal")

    if _u_tihom_periodu() and p != "urgent":
        logger.debug("[NOTIF] Tihi period — notifikacija odložena: %s", tip)

    try:
        await asyncio.to_thread(
            lambda: supa.table("notifications").insert({
                "user_id":    user_id,
                "tip":        tip,
                "naslov":     naslov,
                "poruka":     tekst,
                "predmet_id": predmet_id,
                "prioritet":  p,
                "procitano":  False,
            }).execute()
        )
    except Exception as e:
        logger.warning("[NOTIF] trigger_notifikacija greška: %s", e)


async def _generate_notifications(uid: str) -> int:
    """
    Generiše nova obaveštenja:
      - Rokovi u narednih 7 dana (tip: rok / hitan_rok)
      - Predmeti bez aktivnosti 30+ dana (tip: neaktivnost)
    Pre upisivanja briše stare neprocitane iste kategorije.
    Vraca broj generisanih.
    """
    supa = _get_supa()
    today     = date.today()
    today_iso = today.isoformat()
    in_7_iso  = (today + timedelta(days=7)).isoformat()
    in_2_iso  = (today + timedelta(days=2)).isoformat()
    ago_30    = (today - timedelta(days=30)).isoformat()

    new_notifs: list[dict] = []

    # ── 1. Rokovi u narednih 7 dana ───────────────────────────────────────────
    try:
        rokovi_r, predmeti_r = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("id, akter, predmet_id, dogadjaj, datum_iso, vaznost")
                .eq("user_id", uid)
                .gte("datum_iso", today_iso)
                .lte("datum_iso", in_7_iso)
                .order("datum_iso")
                .limit(30)
                .execute()),
            asyncio.to_thread(lambda: supa.table("predmeti")
                .select("id, naziv, status")
                .eq("user_id", uid)
                .execute()),
            return_exceptions=True,
        )
        pred_map: dict[str, str] = {}
        # Program Lambda, Certification 005 (2026-08-07): a closed/archived
        # case's own predmet_hronologija rows (deadline events) never get
        # cleaned up, so without this exclusion this block would keep
        # generating "Hitan rok"/"Nadolazeći rok" notifications for a case
        # the user already closed, forever -- the SAME status guard the
        # neaktivnost block below already applies, just missing here.
        closed_pids: set[str] = set()
        if not isinstance(predmeti_r, Exception) and predmeti_r.data:
            pred_map = {p["id"]: p.get("naziv", "") for p in predmeti_r.data}
            closed_pids = {p["id"] for p in predmeti_r.data if p.get("status") in ("zatvoren", "arhiviran")}

        if not isinstance(rokovi_r, Exception):
            # INV-2: nepotvrdjen AI rok ne proizvodi notifikaciju.
            _sirovi = rokovi_r.data or []
            for r in _filtriraj_izvrsive(_sirovi, _potvrdjeni_ids([x.get("id") for x in _sirovi])):
                pid   = r.get("predmet_id", "")
                if pid in closed_pids:
                    continue
                naziv = pred_map.get(pid, "Predmet")
                datum = r.get("datum_iso", "")
                hitan = datum <= in_2_iso
                tip = "hitan_rok" if hitan else "rok"
                new_notifs.append({
                    "user_id":    uid,
                    "tip":        tip,
                    "naslov":     f"{'⚠ Hitan rok' if hitan else 'Nadolazeći rok'} — {naziv}",
                    "poruka":     f"{r.get('dogadjaj', '')} ({datum})",
                    "predmet_id": pid,
                    # Program Omega Sprint 006 (2026-08-06): was hand-rolled
                    # "hitan"/"normalan" -- neither is a member of
                    # PRIORITY_ORDER's own vocabulary ("urgent"/"high"/
                    # "normal"/"low"/"info"), so _grupiraj_notifikacije's own
                    # sort (`n.get("prioritet") or NOTIF_TIPOVI...`) always
                    # took the truthy-but-wrong "prioritet" branch and NEVER
                    # fell through to the correct tip-based lookup -- every
                    # hitan_rok notification silently sorted as if "normal"
                    # (PRIORITY_ORDER.get("hitan", 2) == 2, the same default
                    # as "normal"), never actually surfacing above ordinary
                    # rokovi. Fixed: derive from the SAME NOTIF_TIPOVI table
                    # trigger_notifikacija() itself already uses, one source
                    # of truth (`tip`), not a second hand-typed value.
                    "prioritet":  NOTIF_TIPOVI[tip]["priority"],
                })
    except Exception as e:
        logger.error("[NOTIF-GEN] rokovi greška: %s", e)

    # ── 1b. Propušteni rokovi (BLACKSWAN-CRIT-002) — poslednjih 90 dana ───────
    try:
        pre_90_iso = (today - timedelta(days=90)).isoformat()
        rokovi_propusteni_r, predmeti_r2 = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("id, akter, predmet_id, dogadjaj, datum_iso, vaznost")
                .eq("user_id", uid)
                .gte("datum_iso", pre_90_iso)
                .lt("datum_iso", today_iso)
                .order("datum_iso", desc=True)
                .limit(30)
                .execute()),
            asyncio.to_thread(lambda: supa.table("predmeti")
                .select("id, naziv, status")
                .eq("user_id", uid)
                .execute()),
            return_exceptions=True,
        )
        pred_map2: dict[str, str] = {}
        closed_pids2: set[str] = set()
        if not isinstance(predmeti_r2, Exception) and predmeti_r2.data:
            pred_map2 = {p["id"]: p.get("naziv", "") for p in predmeti_r2.data}
            closed_pids2 = {p["id"] for p in predmeti_r2.data if p.get("status") in ("zatvoren", "arhiviran")}

        if not isinstance(rokovi_propusteni_r, Exception):
            # INV-2: isto i za "propusten rok" -- tvrdnja da je advokat NESTO
            # propustio je jednako izvrsiva kao opomena da nesto dolazi.
            _sirovi2 = rokovi_propusteni_r.data or []
            for r in _filtriraj_izvrsive(_sirovi2, _potvrdjeni_ids([x.get("id") for x in _sirovi2])):
                pid = r.get("predmet_id", "")
                if pid in closed_pids2:
                    continue
                naziv = pred_map2.get(pid, "Predmet")
                datum = r.get("datum_iso", "")
                new_notifs.append({
                    "user_id":    uid,
                    "tip":        "rok_propusten",
                    "naslov":     f"⚠ Propušten rok — {naziv}",
                    "poruka":     f"{r.get('dogadjaj', '')} ({datum}) — proveriti da li je i dalje otvoreno.",
                    "predmet_id": pid,
                    "prioritet":  NOTIF_TIPOVI["rok_propusten"]["priority"],
                })
    except Exception as e:
        logger.error("[NOTIF-GEN] propusteni rokovi greška: %s", e)

    # ── 2. Predmeti bez aktivnosti 30+ dana ───────────────────────────────────
    try:
        pred_r, hron_r, bel_r = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmeti")
                .select("id, naziv, status")
                .eq("user_id", uid)
                .execute()),
            asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("predmet_id")
                .eq("user_id", uid)
                .gte("created_at", ago_30)
                .execute()),
            asyncio.to_thread(lambda: supa.table("predmet_beleske")
                .select("predmet_id")
                .eq("user_id", uid)
                .gte("created_at", ago_30)
                .execute()),
            return_exceptions=True,
        )
        active_pids: set[str] = set()
        if not isinstance(hron_r, Exception):
            active_pids |= {r["predmet_id"] for r in (hron_r.data or [])}
        if not isinstance(bel_r, Exception):
            active_pids |= {r["predmet_id"] for r in (bel_r.data or [])}

        if not isinstance(pred_r, Exception):
            for p in (pred_r.data or []):
                if p.get("status") in ("zatvoren", "arhiviran"):
                    continue
                if p["id"] not in active_pids:
                    new_notifs.append({
                        "user_id":    uid,
                        "tip":        "neaktivnost",
                        "naslov":     f"Predmet bez aktivnosti — {p.get('naziv', '')}",
                        "poruka":     "Nema beleški ni događaja u poslednjih 30 dana.",
                        "predmet_id": p["id"],
                        # Same fix as the rokovi block above -- was hardcoded
                        # "info", which does not match NOTIF_TIPOVI["neaktivnost"]
                        # ["priority"] ("low") -- a smaller-severity instance of
                        # the same 2-fields-disagree bug (not a mis-sort into
                        # "normal" like hitan_rok, but a mismatch nonetheless).
                        "prioritet":  NOTIF_TIPOVI["neaktivnost"]["priority"],
                    })
    except Exception as e:
        logger.error("[NOTIF-GEN] neaktivnost greška: %s", e)

    if not new_notifs:
        return 0

    # ── Briši stare neprocitane iste kategorije ───────────────────────────────
    # Operation One Truth (2026-08-07): this delete used to match on user_id +
    # procitano + tip ONLY -- with no awareness that services/case_evolution.py's
    # own `_consequence_project_case_actions_to_notifications` (Program Omega,
    # Final Sprint 007) ALSO writes rok/hitan_rok rows for this same user, via a
    # dedupe-key-based upsert that is meant to be the durable, individually-
    # reconciled record for each deadline. That module's own docstring claims
    # "routers/notifications.py's own rok/hitan_rok generation is retired in the
    # same commit" -- false; this block is still live (confirmed by tracing this
    # code directly, not trusting that claim, per this mission's own Principle 0).
    # Consequence: every time this function ran and found >=1 new notif, its
    # blanket delete wiped out EVERY unread rok/hitan_rok/neaktivnost row for the
    # user, including ones case_evolution.py had just correctly, individually
    # reconciled seconds earlier -- silently discarding a dedupe-tracked deadline
    # alert. Scoped now to only ever delete THIS function's own rows (which never
    # set dedupe_key), never case_evolution.py's.
    tipovi = list({n["tip"] for n in new_notifs})
    try:
        await asyncio.to_thread(
            lambda: supa.table("notifications")
                .delete()
                .eq("user_id", uid)
                .eq("procitano", False)
                .in_("tip", tipovi)
                .is_("dedupe_key", "null")
                .execute()
        )
    except Exception as e:
        logger.warning("[NOTIF-GEN] brisanje starih greška: %s", e)

    # ── Upiši nova ────────────────────────────────────────────────────────────
    try:
        await asyncio.to_thread(
            lambda: supa.table("notifications").insert(new_notifs).execute()
        )
    except Exception as e:
        logger.error("[NOTIF-GEN] insert greška: %s", e)
        return 0

    return len(new_notifs)


@router.get("/notifications")
@limiter.limit("60/minute")
async def get_notifications(
    request: Request,
    user: dict = Depends(get_current_user),
    samo_neprocitane: bool = False,
):
    """
    Vraca lista obaveštenja. Ako je prošlo > 6h od poslednje generacije,
    pokreće auto-refresh u pozadini.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Auto-refresh provera
    try:
        last_r = await asyncio.to_thread(
            lambda: supa.table("notifications")
                .select("created_at")
                .eq("user_id", uid)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
        )
        last_ts = None
        if last_r.data:
            ts_str = last_r.data[0].get("created_at", "")
            if ts_str:
                try:
                    last_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except Exception:
                    pass

        age_h = (
            (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
            if last_ts else 999
        )
        if age_h > _REFRESH_HOURS:
            asyncio.create_task(_generate_notifications(uid))

    except Exception as e:
        logger.error("[NOTIF] auto-refresh provera greška: %s", e)

    # Fetch
    try:
        q = supa.table("notifications").select("*").eq("user_id", uid)
        if samo_neprocitane:
            q = q.eq("procitano", False)
        r = await asyncio.to_thread(
            lambda: q.order("created_at", desc=True).limit(50).execute()
        )
        data = r.data or []
        data = _grupiraj_notifikacije(data)
        neprocitane = sum(1 for n in data if not n.get("procitano"))
        return {
            "notifications": data,
            "ukupno":        len(data),
            "neprocitane":   neprocitane,
        }
    except Exception as e:
        logger.error("[NOTIF] fetch greška: %s", e)
        return {"notifications": [], "ukupno": 0, "neprocitane": 0}


@router.post("/notifications/refresh")
@limiter.limit("5/minute")
async def refresh_notifications(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Forsiraj regeneraciju obaveštenja (sinhrono)."""
    n = await _generate_notifications(user["user_id"])
    return {"generisano": n, "ok": True}


@router.patch("/notifications/read-all")
@limiter.limit("30/minute")
async def mark_all_read(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Označi sva obaveštenja kao pročitana."""
    uid  = user["user_id"]
    supa = _get_supa()
    try:
        await asyncio.to_thread(
            lambda: supa.table("notifications")
                .update({"procitano": True})
                .eq("user_id", uid)
                .eq("procitano", False)
                .execute()
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Greška pri ažuriranju.")


class MarkGroupReadReq(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=50)


@router.patch("/notifications/read-group")
@limiter.limit("120/minute")
async def mark_group_read(
    body: MarkGroupReadReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Final Beta Gate F21 (MEDIUM): grouped notifications (see
    _grupiraj_notifikacije's own "ids" field above) collapse N same-tip rows
    onto ONE representative dict for display -- clicking that group used to
    only ever PATCH the representative row's own id via mark_read below. The
    other N-1 rows stayed procitano=false server-side (the group merely
    re-collapsed onto the same visible representative on the next load, so
    it LOOKED read). This marks every id in the group in one call."""
    uid  = user["user_id"]
    supa = _get_supa()
    try:
        await asyncio.to_thread(
            lambda: supa.table("notifications")
                .update({"procitano": True})
                .in_("id", body.ids)
                .eq("user_id", uid)
                .execute()
        )
        return {"ok": True}
    except Exception:
        raise HTTPException(status_code=500, detail="Greška pri ažuriranju.")


@router.patch("/notifications/{notif_id}/read")
@limiter.limit("120/minute")
async def mark_read(
    notif_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Označi jedno obaveštenje kao pročitano."""
    uid  = user["user_id"]
    supa = _get_supa()
    try:
        await asyncio.to_thread(
            lambda: supa.table("notifications")
                .update({"procitano": True})
                .eq("id", notif_id)
                .eq("user_id", uid)
                .execute()
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Greška pri ažuriranju.")
