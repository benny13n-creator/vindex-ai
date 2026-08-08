# -*- coding: utf-8 -*-
"""
Vindex OS — routers/dashboard.py
Faza: Vindex OS

GET /api/dashboard/command-center  — agregirani OS pregled (PRIORITET 1)
GET /api/predmeti/{id}/health      — Matter Health Score 0-100 (PRIORITET 2)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter
from shared.query_timeout import gather_with_timeout

logger = logging.getLogger("vindex.dashboard")
router = APIRouter(tags=["dashboard"])

_RISK_LEVEL = {"nizak": 1, "srednji": 2, "visok": 3}


# ─── Command Center ───────────────────────────────────────────────────────────

@router.get("/api/dashboard/command-center")
@limiter.limit("30/minute")
async def command_center(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    today      = date.today()
    today_iso  = today.isoformat()
    in_2_iso   = (today + timedelta(days=2)).isoformat()
    in_7_iso   = (today + timedelta(days=7)).isoformat()
    ago_30_iso = (today - timedelta(days=30)).isoformat()
    ago_24h    = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    in_90_iso = (today + timedelta(days=90)).isoformat()

    # ── 10 parallel batch queries ─────────────────────────────────────────────
    # FIX (nightly repair, 2026-07-24): Command Center je ranije čitao SAMO
    # predmet_hronologija za rokove -- AI Deadline Guardian (routers/
    # zastarelost.py::guardian_scan) i 30+ drugih modula rade nad ODVOJENOM
    # "rokovi" tabelom. Rok upisan preko tih puteva se nikad nije pojavljivao
    # ovde. rokovi_tabela_r dodaje TAJ isti izvor u postojeći paralelni batch
    # (bez izmene write putanja bilo kog modula) -- v. spajanje ispod.
    # Program Phoenix, Mission 013 (LIVINGSYS-DEBT-040): this fan-out had no
    # overall timeout -- bounded to 15s (gather_with_timeout), a genuine
    # fast-fail instead of relying on the client library's own ~120s implicit
    # ceiling. On timeout every result is a TimeoutError, which the existing
    # return_exceptions=True fallback machinery below (_safe()) already
    # handles identically to a real per-query failure -- no new code paths.
    (predmeti_r, rocista_r, rokovi_r, risk_hist_r,
     beleske_r, dokumenti_r, ist_recent_r,
     fakture_r, rocista_buduci_r, rokovi_tabela_r,
     dokazi_all_r, dokumenti_all_r, rocista_all_r) = await gather_with_timeout(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,naziv,tip,status,updated_at")
            .eq("user_id", uid)
            .execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("id,predmet_id,sud,datum,vreme,status")
            .eq("user_id", uid)
            .eq("datum", today_iso)
            .order("vreme")
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("predmet_id,dogadjaj,datum_iso,vaznost")
            .eq("user_id", uid)
            .gte("datum_iso", today_iso)
            .lte("datum_iso", in_7_iso)
            .order("datum_iso")
            .limit(100)
            .execute()),
        # Operation Single Brain (2026-08-07): kept ONLY for the "risk changed since last look"
        # diff feature below (pad_procene) -- a legitimate historical comparison, not a source
        # of CURRENT risk anymore. This is the app's actual home-tab endpoint; it used to treat
        # this same cache as authoritative for "current" risk too (predmeti_visok_rizik), up to
        # 24h+ stale, the exact bug class this mission's Red Team reproduced and Operation One
        # Truth already fixed on the sibling /api/predmeti/dashboard endpoint -- this one was
        # missed. Renamed risk_r -> risk_hist_r to make the historical-only role explicit.
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("predmet_id,odgovor,created_at")
            .eq("user_id", uid)
            .like("pitanje", "[Rizik]%")
            .order("created_at", desc=True)
            .limit(300)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske")
            .select("predmet_id")
            .eq("user_id", uid)
            .gte("created_at", ago_30_iso)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("id,naziv_fajla,predmet_id,created_at")
            .eq("user_id", uid)
            .gte("created_at", ago_24h)
            .order("created_at", desc=True)
            .limit(20)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("predmet_id")
            .eq("user_id", uid)
            .gte("created_at", ago_30_iso)
            .execute()),
        asyncio.to_thread(lambda: supa.table("fakture")
            .select("iznos_sa_pdv,status")
            .eq("user_id", uid)
            .in_("status", ["nacrt", "izdata"])
            .execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("predmet_id,datum")
            .eq("user_id", uid)
            .eq("status", "zakazano")
            .gte("datum", today_iso)
            .lte("datum", in_90_iso)
            .order("datum")
            .execute()),
        asyncio.to_thread(lambda: supa.table("rokovi")
            .select("id,naziv,datum,tip,predmet_id,opis")
            .eq("user_id", uid)
            .gte("datum", today_iso)
            .lte("datum", in_7_iso)
            .order("datum")
            .limit(100)
            .execute()),
        # Operation Single Brain: the 3 tables calculate_procesni_rizik needs, bulk-fetched
        # once for the whole portfolio (same pattern as api.py::predmeti_dashboard's own fix)
        # so "visok rizik" reflects live current facts, not a stale snapshot.
        # Operation Singular Intelligence, Mission 002: .is_("deleted_at","null") added -- 1 of 3
        # remaining calculate_procesni_rizik callers still missing this filter (Team 7's Database
        # Evidence Chains audit); a soft-deleted evidence row could inflate/deflate Command
        # Center's own risk sphere/badges relative to Workspace/CCC for the same case.
        asyncio.to_thread(lambda: supa.table("predmet_dokazi")
            .select("predmet_id,snaga,kategorija")
            .eq("user_id", uid)
            .is_("deleted_at", "null")
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("predmet_id,tip_dokaza")
            .eq("user_id", uid)
            .execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("predmet_id,datum")
            .eq("user_id", uid)
            .eq("status", "zakazano")
            .execute()),
        label="dashboard.command_center",
    )

    def _safe(r):
        if isinstance(r, Exception):
            return []
        return r.data or []

    predmeti   = _safe(predmeti_r)
    pred_by_id = {p["id"]: p for p in predmeti}
    aktivni    = [p for p in predmeti if p.get("status") not in ("zatvoren", "arhiviran", "odbijen")]
    aktivni_count = len(aktivni)

    # Neplaćene fakture (nacrt + izdata)
    neplaceno_fakture_rsd = sum(
        float(f.get("iznos_sa_pdv") or 0)
        for f in _safe(fakture_r)
    )

    # Najranije nadolazeće ročište po predmetu (za sorting top_aktivni)
    earliest_rociste: dict[str, str] = {}
    for r in _safe(rocista_buduci_r):
        pid = r.get("predmet_id")
        d = r.get("datum") or "9999-12-31"
        if pid and d < earliest_rociste.get(pid, "9999-12-31"):
            earliest_rociste[pid] = d

    # Top 5 aktivnih — primarno po najranijem budućem ročištu, sekundarno po updated_at
    def _sort_key_aktivni(p: dict) -> tuple:
        has_rociste = p["id"] in earliest_rociste
        return (
            0 if has_rociste else 1,
            earliest_rociste.get(p["id"], "9999-12-31"),
            -(p.get("updated_at") or ""),
        )

    top_aktivni_predmeti = [
        {
            "id":              p["id"],
            "naziv":           p.get("naziv", "—"),
            "status":          p.get("status", "—"),
            "tip":             p.get("tip", ""),
            "sledece_rociste": earliest_rociste.get(p["id"]),
        }
        for p in sorted(aktivni, key=lambda p: (
            0 if p["id"] in earliest_rociste else 1,
            earliest_rociste.get(p["id"], "9999-12-31"),
        ))[:5]
    ]

    # Operation Living System (Wave 3, Portfolio Scale team, REPRODUCED HIGH): neither of the
    # 2 blocks below filtered by predmeti.status -- a hearing/deadline belonging to an
    # archived/closed case rendered on the home-tab "today"/"next 7 days"/"<48h urgent" panels
    # exactly like an active one, while the risk computation a few sections below in this SAME
    # endpoint (`aktivni`, already computed above) correctly excludes them. Reused here, not a
    # new query -- this is the app's actual home-tab endpoint, the worst place for a false
    # "hitan rok" alert about a case the lawyer already closed.
    aktivni_ids = {p["id"] for p in aktivni}

    # 1. Danasnja ročišta
    danasnja_rocista = [
        {
            "id":            r.get("id"),
            "predmet_id":    r.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(r.get("predmet_id", ""), {}).get("naziv", "—"),
            "sud":           r.get("sud", ""),
            "vreme":         (r.get("vreme") or "")[:5],
            "status":        r.get("status", ""),
        }
        for r in _safe(rocista_r) if r.get("predmet_id") in aktivni_ids
    ]

    # 2. Rokovi 7 dana + hitni (<48h)
    # Spojeno iz DVA izvora (nightly repair, 2026-07-24): predmet_hronologija
    # (istorijski dogadjaji/rokovi) I rokovi tabela (ista koju čita AI
    # Deadline Guardian, routers/zastarelost.py::guardian_scan) -- ranije se
    # ovde prikazivao samo prvi izvor.
    rokovi_7 = [
        {
            "predmet_id":    h.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(h.get("predmet_id", ""), {}).get("naziv", "—"),
            "dogadjaj":      h.get("dogadjaj", ""),
            "datum_iso":     h.get("datum_iso", ""),
            "vaznost":       h.get("vaznost", ""),
            "izvor":         "predmet_hronologija",
        }
        for h in _safe(rokovi_r) if h.get("predmet_id") in aktivni_ids
    ] + [
        {
            "predmet_id":    g.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(g.get("predmet_id", ""), {}).get("naziv", "—"),
            "dogadjaj":      g.get("naziv", "") or g.get("opis", "") or "Rok",
            "datum_iso":     g.get("datum", ""),
            "vaznost":       g.get("tip", ""),
            "izvor":         "rokovi",
        }
        for g in _safe(rokovi_tabela_r) if g.get("predmet_id") in aktivni_ids
    ]
    rokovi_7.sort(key=lambda r: r.get("datum_iso") or "9999")
    hitni_rokovi = [r for r in rokovi_7 if (r.get("datum_iso") or "9999") <= in_2_iso]

    # 3. Visok rizik (LIVE, canonical) + pad procene (current live value vs. the most recent
    # historical snapshot). Operation Single Brain (2026-08-07): "trenutni" risk is no longer
    # read from the potentially-stale cache -- it's computed fresh, per case, from the same
    # canonical engine every other risk surface uses. Only the PREVIOUS value (for the "risk
    # increased since last look" diff) legitimately needs history, so risk_hist_r is still used
    # for that one purpose, exactly as api.py's own workspace endpoint already does.
    from services.risk_engine import calculate_procesni_rizik as _calc_rizik_cc
    from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS_CC

    dokazi_map_cc: dict[str, list] = {}
    for d in _safe(dokazi_all_r):
        pid = d.get("predmet_id")
        if pid:
            dokazi_map_cc.setdefault(pid, []).append(d)
    dokumenti_map_cc: dict[str, list] = {}
    for d in _safe(dokumenti_all_r):
        pid = d.get("predmet_id")
        if pid:
            dokumenti_map_cc.setdefault(pid, []).append(d)
    rocista_map_cc: dict[str, list] = {}
    for r in _safe(rocista_all_r):
        pid = r.get("predmet_id")
        if pid:
            rocista_map_cc.setdefault(pid, []).append(r)

    prev_risk_by_pred: dict[str, str] = {}
    for r in _safe(risk_hist_r):
        pid = r.get("predmet_id")
        if pid and pid not in prev_risk_by_pred:
            try:
                prev_risk_by_pred[pid] = (json.loads(r.get("odgovor", "{}")) or {}).get("nivo", "")
            except Exception:
                pass

    predmeti_visok_rizik: list[dict] = []
    pad_procene: list[dict] = []
    for p in aktivni:
        pid = p["id"]
        live = _calc_rizik_cc(
            dokazi=dokazi_map_cc.get(pid, []), dokumenti=dokumenti_map_cc.get(pid, []),
            rocista=rocista_map_cc.get(pid, []), tip_predmeta=p.get("tip", "ostalo"),
            expected_docs=_EXPECTED_DOCS_CC,
        )
        nivo = (live.get("nivo") or "").lower()
        if nivo == "visok":
            predmeti_visok_rizik.append({
                "predmet_id":    pid,
                "predmet_naziv": pred_by_id.get(pid, {}).get("naziv", "—"),
                "rizik_nivo":    nivo,
                "faktori":       [],
            })
        prev_nivo = prev_risk_by_pred.get(pid, "")
        if prev_nivo and _RISK_LEVEL.get(nivo, 0) > _RISK_LEVEL.get(prev_nivo, 0):
            pad_procene.append({
                "predmet_id":      pid,
                "predmet_naziv":   pred_by_id.get(pid, {}).get("naziv", "—"),
                "prethodni_rizik": prev_nivo,
                "trenutni_rizik":  nivo,
            })

    # 4. Neaktivni predmeti (>30 dana)
    active_pids = (
        {r.get("predmet_id") for r in _safe(beleske_r)}
        | {r.get("predmet_id") for r in _safe(ist_recent_r)}
    )
    neaktivni_predmeti = [
        {
            "predmet_id":      p["id"],
            "naziv":           p.get("naziv", ""),
            "poslednja_izmena": (p.get("updated_at") or "")[:10],
        }
        for p in aktivni
        if p["id"] not in active_pids
    ]

    # 5. Novi dokumenti (zadnjih 24h)
    novi_dokumenti = [
        {
            "id":            d.get("id"),
            "predmet_id":    d.get("predmet_id", ""),
            "predmet_naziv": pred_by_id.get(d.get("predmet_id", ""), {}).get("naziv", "—"),
            "naziv_fajla":   d.get("naziv_fajla", ""),
            "created_at":    d.get("created_at", ""),
        }
        for d in _safe(dokumenti_r)
    ]

    # 6. AI preporuke (rule-based — without AI call)
    preporuke: list[str] = []
    if danasnja_rocista:
        n = len(danasnja_rocista)
        preporuke.append(f"Danas imate {n} ročiš{'te' if n == 1 else 'ta'} — proverite pripremu.")
    if hitni_rokovi:
        n = len(hitni_rokovi)
        preporuke.append(f"⚠ {n} hitan{'ih' if n > 1 else ''} rok{'ova' if n > 1 else ''} ističe za <48h — odmah reagujte.")
    if predmeti_visok_rizik:
        n = len(predmeti_visok_rizik)
        preporuke.append(f"{n} predmet{'a' if n > 1 else ''} visokog rizika zahteva pažnju.")
    if pad_procene:
        n = len(pad_procene)
        preporuke.append(f"Rizik se pogoršao na {n} predmet{'a' if n > 1 else ''} — analizirajte.")
    if novi_dokumenti:
        n = len(novi_dokumenti)
        preporuke.append(f"{n} novi{'h' if n > 1 else ''} dokument{'a' if n > 1 else ''} — pokrenite AI analizu.")
    if neaktivni_predmeti:
        n = len(neaktivni_predmeti)
        preporuke.append(f"{n} predmet{'a' if n > 1 else ''} bez aktivnosti >30 dana — proverite status.")

    summary = " ".join(preporuke[:2]) if preporuke else "Sve je pod kontrolom — nema hitnih upozorenja."

    return {
        # Backward compatible with existing /portfolio/dashboard consumer
        "ukupno_predmeta":   len(predmeti),
        "ukupno_aktivnih":   aktivni_count,
        "rokovi_7_dana":     rokovi_7,
        "hitni_rokovi":      hitni_rokovi,
        "neaktivni_30_dana": neaktivni_predmeti,
        "summary":           summary,
        # New OS fields
        "danasnja_rocista":     danasnja_rocista,
        "predmeti_visok_rizik":   predmeti_visok_rizik,
        "pad_procene":            pad_procene,
        # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-039): risk_hist_r's own
        # .limit(300) can silently drop older history at scale, understating
        # "risk worsened" coverage with zero signal. Same split as -003
        # (Mission 014): the cap itself is a genuine cost tradeoff, unchanged
        # and still the founder's call -- this is disclosure only.
        "pad_procene_truncated":  len(_safe(risk_hist_r)) >= 300,
        "novi_dokumenti":         novi_dokumenti,
        "ai_preporuke":           preporuke,
        "top_aktivni_predmeti":   top_aktivni_predmeti,
        "neplaceno_fakture_rsd":  neplaceno_fakture_rsd,
        "statistike": {
            "ukupno_aktivnih":        aktivni_count,
            "danasnja_rocista":       len(danasnja_rocista),
            "hitni_rokovi":           len(hitni_rokovi),
            "predmeti_visok_rizik":   len(predmeti_visok_rizik),
            "pad_procene":            len(pad_procene),
            "novi_dokumenti":         len(novi_dokumenti),
            "neaktivni":              len(neaktivni_predmeti),
            "neplaceno_fakture_rsd":  neplaceno_fakture_rsd,
        },
    }


# ─── Matter Health Score ──────────────────────────────────────────────────────

@router.get("/api/predmeti/{predmet_id}/health")
@limiter.limit("60/minute")
async def matter_health_score(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Project Sentinel (2026-08-03): ovaj endpoint je ranije računao SOPSTVENU,
    trećU nezavisnu "case health" formulu (drugačije težine, 48h prozor za
    hitne rokove umesto 7 dana koje koristi ostatak platforme, brojanje
    dokumenata bez tip_dokaza poklapanja) — potpuno nezavisno od
    services/risk_engine.py::calculate_procesni_rizik, koji već koriste
    routers/matter_intel.py i routers/ccc.py (Project Nexus). Nije imao
    frontend pozivaoca (potvrđeno pretragom static/*.js), ali je bio potpuno
    živ — rutiran, testiran — landmina za bilo koga ko ga ojača u UI kasnije
    i dobije broj koji se ne slaže sa Matter Intel/CCC/Cockpit za isti
    predmet istog dana. Sada delegira na kanonski izvor, isti obrazac kao
    ccc.py fix — `score`/`status`/`hitnih_rokova` sada dolaze isključivo iz
    calculate_procesni_rizik/identify_case_problems; `aktivnost` (beleška/
    komentar poslednjih 7 dana) ostaje sopstveni signal ovog pogleda jer
    risk_engine ne prati aktivnost uopšte."""
    uid  = user["user_id"]
    supa = _get_supa()

    today     = date.today()
    today_iso = today.isoformat()
    ago_7_iso = (today - timedelta(days=7)).isoformat()

    # Verify ownership + parallel fetch
    # Program Phoenix, Mission 013 (LIVINGSYS-DEBT-040): bounded to 15s (see
    # command_center's own identical fix above for full reasoning).
    pred_r, bel_r, kom_r, dok_r, roc_r, dokaz_r = await gather_with_timeout(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,status,tip").eq("id", predmet_id).eq("user_id", uid).limit(1).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske")
            .select("id").eq("predmet_id", predmet_id).gte("created_at", ago_7_iso).limit(1).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_komentari")
            .select("id").eq("predmet_id", predmet_id).gte("created_at", ago_7_iso).limit(1).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("id,tip_dokaza").eq("predmet_id", predmet_id).limit(200).execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("datum").eq("predmet_id", predmet_id).gte("datum", today_iso).limit(50).execute()),
        # Operation Singular Intelligence, Mission 002: .is_("deleted_at","null") added -- 3rd of 3
        # remaining calculate_procesni_rizik callers missing this filter (Team 7's audit).
        asyncio.to_thread(lambda: supa.table("predmet_dokazi")
            .select("snaga,kategorija,pravni_element").eq("predmet_id", predmet_id)
            .is_("deleted_at", "null").limit(200).execute()),
        label="dashboard.matter_health_score",
    )

    # A timeout on pred_r specifically must never be misreported as "case doesn't
    # exist" (404) -- that's a real, distinct, actionable-differently condition.
    if isinstance(pred_r, asyncio.TimeoutError):
        raise HTTPException(status_code=503, detail="Upit je predugo trajao. Pokušajte ponovo.")
    if isinstance(pred_r, Exception) or not (pred_r.data if not isinstance(pred_r, Exception) else []):
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    def _ok(r):
        return not isinstance(r, Exception) and bool(r.data)

    tip_predmeta = (pred_r.data[0] or {}).get("tip") or "ostalo"
    dok_data     = (dok_r.data   if not isinstance(dok_r,   Exception) else []) or []
    roc_data     = (roc_r.data   if not isinstance(roc_r,   Exception) else []) or []
    dokazi_data  = (dokaz_r.data if not isinstance(dokaz_r, Exception) else []) or []

    from services.risk_engine import calculate_procesni_rizik, identify_case_problems
    from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS

    rizik = calculate_procesni_rizik(
        dokazi=dokazi_data, dokumenti=dok_data, rocista=roc_data,
        tip_predmeta=tip_predmeta, expected_docs=_EXPECTED_DOCS,
    )
    problemi = identify_case_problems(rizik, tip_predmeta)

    aktivnost_prisutna = _ok(bel_r) or _ok(kom_r)
    aktivnost_poeni    = 25 if aktivnost_prisutna else 0

    razlozi: list[str] = [p["problem"] for p in problemi]
    if not aktivnost_prisutna:
        razlozi.append("Nema aktivnosti (beleška/komentar) u poslednjih 7 dana")

    # nivo (Nizak/Srednji/Visok) je jedini izvor statusne kategorije — ne
    # izmišljaju se novi pragovi nad health_score, isto kao ccc.py fix.
    _NIVO_TO_STATUS = {"Nizak": "zdrav", "Srednji": "upozorenje", "Visok": "kriticno"}
    status = _NIVO_TO_STATUS.get(rizik["nivo"], "upozorenje")

    return {
        "predmet_id": predmet_id,
        "score":      rizik["health_score"],
        "status":     status,
        "razlozi":    razlozi,
        "faktori": {
            "aktivnost":     aktivnost_poeni,
            "dokumentacija": len(dok_data),
            "hitnih_rokova": rizik["kriticni_rokovi"],
            "ima_rociste":   bool(roc_data),
        },
    }
