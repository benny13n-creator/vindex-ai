# -*- coding: utf-8 -*-
"""
Vindex OS — routers/inbox.py
Faza: Vindex OS — PRIORITET 3

GET /api/inbox  — Unified Inbox: agregirani, sortirani feed svih aktivnosti

Program Omega, Sprint 005 (2026-08-06) — Unified Operational Experience:
this endpoint used to ALSO independently generate "rociste"/"rok" items
(hearing/deadline reminders) — a direct shadow-workflow duplicate of
`services/case_evolution.py::_compute_target_actions`'s own Rule 1
(`PRIPREMITI_PODNESAK`, sourced from the SAME `rocista`/deadline data),
rendered on the SAME home page as Sprint 004's own `GET /api/workspace`.
Both were live, both independently computed a priority-sorted "what needs
attention" list from overlapping data, under 2 different vocabularies
(this endpoint's own "kriticno/visok/srednji/nizak" vs. `case_actions`'
own "critical/high/medium/low/informational") — confirmed via
`docs/omega/SHADOW_WORKFLOW_AUDIT.md`. `case_actions`/Workspace is the
newer, deterministic, sourced, lifecycle-managed engine — it wins;
hearing/deadline items were removed from here. This endpoint's remaining,
genuinely NOT-covered-elsewhere concepts stay: unbilled invoices,
inactive-case nudges, and a lightweight "new document" ambient notice
(distinct from Workspace's own "Review Required," which specifically
means a document is BLOCKED pending human confirmation).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request

from shared.attention_priority import INBOX_TO_CANONICAL, CANONICAL_ORDER
from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.inbox")
router = APIRouter(tags=["inbox"])

# Program Omega Sprint 006 (2026-08-06): sort order now derived from the
# canonical model (shared/attention_priority.py) via INBOX_TO_CANONICAL,
# instead of this file keeping its own independent {word: number} ranking.
# The API's own response shape (item["prioritet"] values) is UNCHANGED —
# no frontend consumer reads that field for anything (confirmed: the
# frontend's own Inbox rendering colors by item type, not priority,
# static/vindex.js ~line 1642) — only the internal SORT decision moves
# onto the shared model. Same public interface (`.get(value, default)`)
# every call site below already uses.
_PRIORITET_ORDER = {word: CANONICAL_ORDER[canon] for word, canon in INBOX_TO_CANONICAL.items()}


@router.get("/api/inbox")
@limiter.limit("30/minute")
async def unified_inbox(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    today      = date.today()
    ago_30_iso = (today - timedelta(days=30)).isoformat()
    ago_24h    = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    ago_7_iso  = (today - timedelta(days=7)).isoformat()

    # ── Batch fetch ───────────────────────────────────────────────────────────
    # Program Omega Sprint 005: rocista/predmet_hronologija fetches removed —
    # hearing/deadline "what needs attention" signals now come exclusively
    # from case_actions/Workspace (see module docstring).
    (predmeti_r, dokumenti_r, billing_r, beleske_r, ist_r) = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,naziv,status")
            .eq("user_id", uid)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("id,predmet_id,naziv_fajla,created_at")
            .eq("user_id", uid)
            .gte("created_at", ago_24h)
            .order("created_at", desc=True)
            .limit(20)
            .execute()),
        asyncio.to_thread(lambda: supa.table("billing_entries")
            .select("id,predmet_id,opis,iznos_rsd,datum")
            .eq("user_id", uid)
            .eq("obracunato", False)
            .lte("datum", ago_7_iso)
            .order("datum")
            .limit(30)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske")
            .select("predmet_id")
            .eq("user_id", uid)
            .gte("created_at", ago_30_iso)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("predmet_id")
            .eq("user_id", uid)
            .gte("created_at", ago_30_iso)
            .execute()),
        return_exceptions=True,
    )

    def _safe(r):
        if isinstance(r, Exception):
            return []
        return r.data or []

    predmeti   = _safe(predmeti_r)
    aktivni    = [p for p in predmeti if p.get("status") not in ("zatvoren", "arhiviran", "odbijen")]
    pred_by_id = {p["id"]: p for p in predmeti}

    items: list[dict] = []

    # ── Novi dokumenti (last 24h) ─────────────────────────────────────────────
    for d in _safe(dokumenti_r):
        items.append({
            "tip":           "dokument",
            "prioritet":     "srednji",
            "naslov":        d.get("naziv_fajla", "Dokument"),
            "opis":          "Novi dokument — pokrenite AI analizu",
            "predmet_id":    d.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(d.get("predmet_id", ""), {}).get("naziv", "—"),
            "datum":         (d.get("created_at") or "")[:10],
            "id":            d.get("id", ""),
        })

    # ── Nenaplaćene stavke (>7 dana stare, nije obračunato) ──────────────────
    for b in _safe(billing_r):
        items.append({
            "tip":           "naplata",
            "prioritet":     "nizak",
            "naslov":        f"Nenaplaćena stavka — {b.get('opis', '')[:60]}",
            "opis":          f"{int(b.get('iznos_rsd') or 0):,} RSD — nije fakturisano",
            "predmet_id":    b.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(b.get("predmet_id", ""), {}).get("naziv", "—"),
            "datum":         b.get("datum", ""),
            "id":            b.get("id", ""),
        })

    # ── Neaktivni predmeti (>30 dana) ─────────────────────────────────────────
    active_pids = (
        {r.get("predmet_id") for r in _safe(beleske_r)}
        | {r.get("predmet_id") for r in _safe(ist_r)}
    )
    for p in aktivni:
        if p["id"] not in active_pids:
            items.append({
                "tip":           "neaktivan",
                "prioritet":     "nizak",
                "naslov":        f"Predmet bez aktivnosti — {p.get('naziv', '—')}",
                "opis":          "Bez beleški ili analiza >30 dana",
                "predmet_id":    p["id"],
                "predmet_naziv": p.get("naziv", "—"),
                "datum":         (p.get("updated_at") or "")[:10],
                "id":            p["id"],
            })

    # ── Sort: prioritet → datum ───────────────────────────────────────────────
    items.sort(key=lambda x: (
        _PRIORITET_ORDER.get(x["prioritet"], 9),
        x.get("datum") or "9999-12-31",
    ))

    return {
        "stavke":   items,
        "ukupno":   len(items),
        "kriticno": sum(1 for i in items if i["prioritet"] == "kriticno"),
        "visok":    sum(1 for i in items if i["prioritet"] == "visok"),
        "srednji":  sum(1 for i in items if i["prioritet"] == "srednji"),
        "nizak":    sum(1 for i in items if i["prioritet"] == "nizak"),
    }
