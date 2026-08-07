# -*- coding: utf-8 -*-
"""
Matter Intelligence Dashboard — AI ocena zdravlja predmeta.

GET /api/matter-intel/predmeti/{predmet_id}
Vraća: snaga_dokaza, procesni_rizik, nedostajuci_dokazi, predstojeći_rokovi,
       otkriveni_problemi (deterministicki, services.risk_engine.identify_case_problems
       — jedini algoritam za "sledecu akciju" u celoj platformi, Core
       Consolidation Sec 1.2, 2026-07-22), health_score (0-100)
"""
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from shared.rate import limiter
from shared.deps import _get_supa, get_current_user
from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService
from services.risk_engine import calculate_procesni_rizik, identify_case_problems

logger = logging.getLogger("vindex.matter_intel")
router = APIRouter(prefix="/api/matter-intel", tags=["matter_intel"])


@llm_retry
def _pozovi_matter_intel_api(client, **kwargs):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return client.chat.completions.create(**kwargs)


def _d(r):
    """Koerzija asyncio.gather(..., return_exceptions=True) rezultata u listu —
    Exception ili prazan .data postaju []. Bila je duplirana kao identican
    lokalni closure na dva mesta u ovom fajlu (Faza 2.2 cleanup, 2026-07-18);
    sada jedna deljena funkcija, ponasanje nepromenjeno."""
    return (r.data if not isinstance(r, Exception) else []) or []


@router.get("/predmeti/{predmet_id}")
@limiter.limit("30/minute")
async def get_matter_intel(request: Request, predmet_id: str, user=Depends(get_current_user)):
    supa = _get_supa()
    uid  = user["user_id"]

    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select(
            "id,naziv,tip,status,rizik,opis,created_at"
        ).eq("id", predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404)
    predmet = pr.data[0]
    tip     = predmet.get("tip") or "ostalo"

    now = datetime.now(timezone.utc)

    # ── Sva 3 upita paralelno ────────────────────────────────────────────────
    dokazi_r, dok_r, rok_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_dokazi").select(
            "snaga,kategorija,pravni_element"
        ).eq("predmet_id", predmet_id).is_("deleted_at", "null").execute()),
        # Operation Single Brain (2026-08-07): this select was missing tip_dokaza --
        # calculate_procesni_rizik's missing-evidence detection reads exactly that column
        # (postojeci_tipovi = {d.get("tip_dokaza") ...}), so with it absent this endpoint
        # ALWAYS reported every expected document type as missing, regardless of what was
        # actually uploaded. Execution-tested (not just read) by this mission's Team 6
        # against routers/ccc.py's correct query for the identical case data, confirming a
        # real health_score/nedostajuci_dokazi divergence this fix closes.
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("naziv_fajla,status,tip_dokaza").eq(
            "predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("rocista").select(
            "sud,datum,status"
        ).eq("predmet_id", predmet_id).order("datum").execute()),
        return_exceptions=True,
    )

    # ── Dokazi analiza + procesni rizik — G-027 jedini izvor istine ───────────
    dokazi = ((dokazi_r.data if not isinstance(dokazi_r, Exception) else []) or [])
    _dok_data = ((dok_r.data if not isinstance(dok_r, Exception) else []) or [])
    _rok_data = ((rok_r.data if not isinstance(rok_r, Exception) else []) or [])

    _rizik = calculate_procesni_rizik(
        dokazi=dokazi, dokumenti=_dok_data, rocista=_rok_data,
        tip_predmeta=tip, expected_docs=_EXPECTED_DOCS,
    )
    snaga_label     = _rizik["snaga_dokaza"]
    snaga_pct       = _rizik["snaga_pct"]
    snaga_count     = _rizik["snaga_detalji"]
    nedostajuci     = _rizik["nedostajuci_dokazi"]
    predstojeći     = _rizik["predstojeći_rokovi"]
    kriticni        = _rizik["kriticni_rokovi"]
    procesni_rizik  = _rizik["nivo"]
    rizik_boja      = _rizik["boja"]
    health          = _rizik["health_score"]

    # ── Otkriveni problemi — Core Consolidation Sec 1.2, jedini algoritam ─────
    otkriveni_problemi = identify_case_problems(_rizik, tip)

    # Project Synapse (2026-08-03) — vidi _maybe_emit_health_and_deadline_events
    # docstring: dva vec ozicena proactive-alert handlera (services/event_bus.py)
    # nikad nisu triggerovana jer nista u repou nije emitovalo ta dva EventType.
    # Fire-and-forget: ne sme usporiti ovaj (cesto pozivan, na svakom case-open)
    # endpoint.
    asyncio.create_task(_maybe_emit_health_and_deadline_events(
        supa, uid, predmet_id, health, _rizik.get("kriticni_rocista") or [],
    ))

    # ── Trend aktivnosti + Health log — paralelno ────────────────────────────
    trend, health_history = await asyncio.gather(
        asyncio.to_thread(_compute_trend, supa, predmet_id, now),
        asyncio.to_thread(_log_and_fetch_health, supa, predmet_id, health, procesni_rizik, now),
    )

    return {
        "snaga_dokaza":     snaga_label,
        "snaga_pct":        snaga_pct,
        "snaga_detalji":    snaga_count,
        "procesni_rizik":   procesni_rizik,
        "rizik_boja":       rizik_boja,
        "nedostajuci_dokazi": nedostajuci,
        "nedostajuci_count":  len(nedostajuci),
        "predstojeći_rokovi": predstojeći,
        "kriticni_rokovi":    kriticni,
        "health_score":       health,
        "otkriveni_problemi": otkriveni_problemi,
        "trend":              trend,
        "health_history":     health_history,
    }


async def _maybe_emit_health_and_deadline_events(
    supa, uid: str, predmet_id: str, health: int, kriticni_rocista: list,
) -> None:
    """Project Synapse (2026-08-03): a full emit/consume audit of every
    services/event_bus.py EventType found HEALTH_SCORE_PROMENJEN and
    ROK_KRITICAN both already have real, fully-wired handlers (create a
    proactive_alerts row) that were NEVER emitted by anything in the repo --
    get_matter_intel already computes exactly the signal each one needs, on
    every case-open. This connects them.

    Dedup is mandatory, not optional: this endpoint runs on every case-open
    (matter_intel_load(), auto-called from pred_select()) -- emitting
    unconditionally would create a new duplicate alert every single page
    view. Guarded by checking for an existing UNREAD alert of the same type
    first; only emits if none exists yet."""
    from services.event_bus import emit, EventType

    try:
        if health < 30:
            existing = await asyncio.to_thread(
                lambda: supa.table("proactive_alerts").select("id")
                    .eq("predmet_id", predmet_id).eq("tip", "nizak_health_score")
                    .eq("procitana", False).limit(1).execute()
            )
            if not (existing.data or []):
                emit(EventType.HEALTH_SCORE_PROMENJEN, uid, predmet_id, {"health_score": health})
    except Exception as exc:
        logger.warning("[MATTER_INTEL] health-score event emit greška (non-fatal) predmet=%s: %s", predmet_id, exc)

    try:
        if kriticni_rocista:
            existing_rok = await asyncio.to_thread(
                lambda: supa.table("proactive_alerts").select("id")
                    .eq("predmet_id", predmet_id).eq("tip", "rok_kritican")
                    .eq("procitana", False).limit(1).execute()
            )
            if not (existing_rok.data or []):
                r0 = kriticni_rocista[0]
                emit(EventType.ROK_KRITICAN, uid, predmet_id, {
                    "naziv": f"Ročište — {r0.get('sud') or 'sud'}",
                    "datum": r0.get("datum", ""),
                })
    except Exception as exc:
        logger.warning("[MATTER_INTEL] rok-kritican event emit greška (non-fatal) predmet=%s: %s", predmet_id, exc)


def _log_and_fetch_health(supa, predmet_id: str, health: int, rizik_label: str, now: datetime) -> list:
    """
    Snimi dnevni health_score snapshot i vrati poslednjih 30 dana.
    Gracefully ignoriše greške (tabela možda ne postoji pre migracije 026).
    Vraća: [{"date": "YYYY-MM-DD", "score": int}, ...] ili []
    """
    try:
        today = now.date().isoformat()
        today_start = f"{today}T00:00:00+00:00"
        tomorrow    = f"{now.date().isoformat()}T23:59:59+00:00"

        # Upiši samo jednom dnevno (idempotentno)
        existing = supa.table("predmet_health_log").select("id") \
            .eq("predmet_id", predmet_id) \
            .gte("logged_at", today_start) \
            .lte("logged_at", tomorrow) \
            .limit(1).execute()

        if not existing.data:
            supa.table("predmet_health_log").insert({
                "predmet_id": predmet_id,
                "health_score": health,
                "rizik_label": rizik_label,
            }).execute()
    except Exception:
        pass  # tabela još ne postoji — migracija 026 nije primenjena

    try:
        from datetime import timedelta
        since = (now - timedelta(days=30)).isoformat()
        rows = supa.table("predmet_health_log").select("health_score,logged_at") \
            .eq("predmet_id", predmet_id) \
            .gte("logged_at", since) \
            .order("logged_at") \
            .execute()

        # Grupiši po danu — uzmi poslednji zapis po danu
        daily: dict[str, int] = {}
        for row in (rows.data or []):
            d = (row.get("logged_at","") or "")[:10]
            if d:
                daily[d] = row["health_score"]

        return [{"date": d, "score": s} for d, s in sorted(daily.items())]
    except Exception:
        return []


def _compute_trend(supa, predmet_id: str, now: datetime) -> str:
    """Trend aktivnosti: poredi broj Q&A unosa u 3 uzastopna perioda od 7 dana."""
    try:
        from datetime import timedelta
        p1_start = (now - timedelta(days=7)).isoformat()
        p2_start = (now - timedelta(days=14)).isoformat()
        p3_start = (now - timedelta(days=21)).isoformat()

        def _count(after: str, before: str) -> int:
            r = supa.table("predmet_istorija").select("id", count="exact") \
                .eq("predmet_id", predmet_id) \
                .gte("created_at", after).lt("created_at", before).execute()
            return r.count or 0

        c1 = _count(p1_start, now.isoformat())   # najnoviji period
        c2 = _count(p2_start, p1_start)
        c3 = _count(p3_start, p2_start)

        if c1 == 0 and c2 == 0 and c3 == 0:
            return None
        if c1 > c2:
            return "raste"
        if c1 < c2:
            return "opada"
        return "stagnira"
    except Exception:
        return None


# ─── Uncertainty Dashboard ───────────────────────────────────────────────────

import os as _os
from typing import Optional
from fastapi import Request
from pydantic import BaseModel


def _semafor(score: int) -> str:
    if score <= 35:
        return "zelena"
    if score <= 65:
        return "žuta"
    return "crvena"


@router.get("/predmeti/{predmet_id}/uncertainty")
@limiter.limit("20/minute")
async def get_uncertainty_dashboard(
    predmet_id: str,
    request: Request,
    user=Depends(PermissionService.require("matter_intel")),
):
    """
    Uncertainty Dashboard — semafor sistem po 5 dimenzija rizika.
    Vraća score 0-100 po svakoj dimenziji i AI analizu.
    """
    supa = _get_supa()
    uid  = user["user_id"]

    # Ownership check
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select(
            "id,naziv,tip,status,tuzeni,opis"
        ).eq("id", predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404)
    predmet = pr.data[0]
    tip = predmet.get("tip") or "ostalo"

    now = datetime.now(timezone.utc)

    # Paralelno dohvati sve podatke
    dok_r, rok_r, ist_r, billing_r, hron_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select(
            "tip_dokaza"
        ).eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("rocista").select(
            "sud,datum,status"
        ).eq("predmet_id", predmet_id).order("datum").execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija").select(
            "pitanje"
        ).eq("predmet_id", predmet_id).eq("user_id", uid).limit(100).execute()),
        asyncio.to_thread(lambda: supa.table("billing_entries").select(
            "id"
        ).eq("predmet_id", predmet_id).limit(1).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select(
            "dogadjaj"
        ).eq("predmet_id", predmet_id).limit(50).execute()),
        return_exceptions=True,
    )

    dokumenti = _d(dok_r)
    rokovi    = _d(rok_r)
    istorija  = _d(ist_r)
    billing   = _d(billing_r)
    hronolog  = _d(hron_r)

    # ── 1. Faktička nesigurnost ───────────────────────────────────────────────
    expected = _EXPECTED_DOCS.get(tip, _EXPECTED_DOCS["ostalo"])
    postojeci_tipovi = {d.get("tip_dokaza") for d in dokumenti if d.get("tip_dokaza")}
    nedostajuci_br = len([t for t in expected if t not in postojeci_tipovi])
    ukupno_ocekivanih = len(expected) if expected else 5
    cinjenicna = min(100, int(nedostajuci_br / max(1, ukupno_ocekivanih) * 100))

    # ── 2. Procesna nesigurnost ───────────────────────────────────────────────
    # Operation One Truth (2026-08-07): same naive-vs-aware datetime bug already
    # found and fixed in services/risk_engine.py (Project Synapse) and
    # routers/ccc.py (this same mission) -- comparing a naive datetime (from a
    # plain "YYYY-MM-DD") against timezone-AWARE `now` raised a silently-swallowed
    # TypeError, so kriticni_rokovi stayed 0 for any hearing stored as a plain
    # date. Fixed to compare calendar dates, matching the canonical pattern.
    kriticni_rokovi = 0
    for r in rokovi:
        try:
            ds = r.get("datum","") or ""
            dana = (datetime.fromisoformat(ds).date() - now.date()).days if len(ds) == 10 \
                else (datetime.fromisoformat(ds.replace("Z","+00:00")).date() - now.date()).days
            if 0 <= dana <= 7:
                kriticni_rokovi += 1
        except Exception:
            pass

    if not rokovi:
        procesna = 50
    elif kriticni_rokovi == 0:
        procesna = 0
    elif kriticni_rokovi == 1:
        procesna = 40
    else:
        procesna = 70

    # ── 3. Pravna nesigurnost ─────────────────────────────────────────────────
    ima_strategiju = any(
        "[Strategija" in (r.get("pitanje") or "") for r in istorija
    )
    ima_praksu = any(
        "praksa" in (h.get("dogadjaj") or "").lower() or
        "presuda" in (h.get("dogadjaj") or "").lower()
        for h in hronolog
    )
    if ima_strategiju and ima_praksu:
        pravna = 15
    elif ima_strategiju:
        pravna = 30
    else:
        pravna = 80

    # ── 4. Protivnička nesigurnost ────────────────────────────────────────────
    ima_info_protivnik = bool(predmet.get("tuzeni")) or any(
        "protivnik" in (h.get("dogadjaj") or "").lower() or
        "tuženi" in (h.get("dogadjaj") or "").lower()
        for h in hronolog
    )
    protivnicka = 50 if ima_info_protivnik else 70

    # ── 5. Finansijska nesigurnost ────────────────────────────────────────────
    finansijska = 30 if billing else 60

    # ── Ukupni score ──────────────────────────────────────────────────────────
    uncertainty_score = int((cinjenicna + procesna + pravna + protivnicka + finansijska) / 5)

    dimenzije = {
        "cinjenicna":   {"score": cinjenicna,   "boja": _semafor(cinjenicna),   "label": "Faktička nesigurnost"},
        "procesna":     {"score": procesna,      "boja": _semafor(procesna),     "label": "Procesna nesigurnost"},
        "pravna":       {"score": pravna,        "boja": _semafor(pravna),       "label": "Pravna nesigurnost"},
        "protivnicka":  {"score": protivnicka,   "boja": _semafor(protivnicka),  "label": "Protivnička nesigurnost"},
        "finansijska":  {"score": finansijska,   "boja": _semafor(finansijska),  "label": "Finansijska nesigurnost"},
    }

    # ── AI analiza ────────────────────────────────────────────────────────────
    ai_analiza = ""
    preporuke: list[str] = []
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=_os.environ["OPENAI_API_KEY"])
        _ctx = (
            f"Predmet: {predmet.get('naziv','')} (tip: {tip})\n"
            f"Faktička nesigurnost: {cinjenicna}/100\n"
            f"Procesna nesigurnost: {procesna}/100\n"
            f"Pravna nesigurnost: {pravna}/100\n"
            f"Protivnička nesigurnost: {protivnicka}/100\n"
            f"Finansijska nesigurnost: {finansijska}/100\n"
            f"Ukupni score: {uncertainty_score}/100"
        )
        _prompt = (
            "Analiziraj uncertainty profile pravnog predmeta. "
            "Vrati JSON: {\"analiza\": \"...\", \"preporuke\": [\"...\", \"...\"]}. "
            "Analiza max 80 reči. Preporuke: 2-3 konkretne akcije. "
            "Ekavica obavezno. Budi direktan i konkretan."
        )
        resp = await asyncio.to_thread(
            _pozovi_matter_intel_api,
            oai,
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=300,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _prompt},
                {"role": "user",   "content": _ctx},
            ],
        )
        import json as _json
        parsed = _json.loads(resp.choices[0].message.content or "{}")
        ai_analiza = parsed.get("analiza", "")
        preporuke  = parsed.get("preporuke", [])
    except Exception as e:
        _sentry_capture(e)
        logger.debug("[UNCERTAINTY] AI greška: %s", e)

    await UsageService.consume(uid, user.get("email", ""), "matter_intel")

    return {
        "uncertainty_score": uncertainty_score,
        "semafor":           _semafor(uncertainty_score),
        "dimenzije":         dimenzije,
        "ai_analiza":        ai_analiza,
        "preporuke":         preporuke,
    }


# ─── Pre-Flight Check ─────────────────────────────────────────────────────────

class PreflightRequest(BaseModel):
    tip_radnje: str
    opis_radnje: Optional[str] = None
    datum_radnje: Optional[str] = None


_PREFLIGHT_SYSTEM = """Ti si pravni asistent koji proverava spremnost pre važne pravne radnje.

Na osnovu podataka o predmetu i planiranoj radnji, generiši Pre-Flight checklist.

Vrati ISKLJUČIVO validan JSON:
{
  "status": "spreman" | "potrebna_paznja" | "nije_spreman",
  "score": <int 0-100>,
  "kategorije": [
    {
      "naziv": "Dokumentacija",
      "status": "ok" | "upozorenje" | "problem",
      "stavke": [
        {"tekst": "...", "status": "ok" | "upozorenje" | "problem", "akcija": "..."}
      ]
    }
  ],
  "kriticna_upozorenja": ["..."],
  "preporuke": ["konkretna akcija 1", "konkretna akcija 2"],
  "procena_rizika": "Kratak opis kljucnih rizika (max 100 reci)"
}

Kategorije moraju biti: Dokumentacija, Rokovi, Strategija, Protivnicka strana, Finansije.
Svaka kategorija ima 2-4 stavke. Ekavica. Budi konkretan i direktan."""


@router.post("/predmeti/{predmet_id}/preflight")
@limiter.limit("10/minute")
async def preflight_check(
    predmet_id: str,
    body: PreflightRequest,
    request: Request,
    user=Depends(PermissionService.require("matter_intel")),
):
    """
    Pre-Flight Check — provera spremnosti pre podneska, ročišta, nagodbe ili žalbe.
    Generiše strukturisanu checklist sa AI analizom.
    """
    supa = _get_supa()
    uid  = user["user_id"]

    _DOZVOLJENI_TIPOVI = {"podnesak", "rociste", "nagodba", "zalba"}
    if body.tip_radnje not in _DOZVOLJENI_TIPOVI:
        raise HTTPException(status_code=400, detail=f"tip_radnje mora biti: {', '.join(_DOZVOLJENI_TIPOVI)}")

    # Ownership check
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select(
            "id,naziv,tip,status,tuzeni,tuzilac,opis,sud"
        ).eq("id", predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404)
    predmet = pr.data[0]

    # Paralelno dohvati kontekst predmeta
    dok_r, rok_r, ist_r, hron_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select(
            "naziv_fajla,tip_dokaza"
        ).eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("rocista").select(
            "sud,datum,status"
        ).eq("predmet_id", predmet_id).order("datum").execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija").select(
            "pitanje,odgovor"
        ).eq("predmet_id", predmet_id).eq("user_id", uid).order(
            "created_at", desc=True
        ).limit(20).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select(
            "dogadjaj,datum_iso,vaznost"
        ).eq("predmet_id", predmet_id).order("datum_iso", desc=True).limit(20).execute()),
        return_exceptions=True,
    )

    dokumenti = _d(dok_r)
    rokovi    = _d(rok_r)
    istorija  = _d(ist_r)
    hronolog  = _d(hron_r)

    # Formatiranje konteksta za GPT
    tip_label = {
        "podnesak": "podnošenje podneska",
        "rociste":  "ročište",
        "nagodba":  "nagodbu/poravnanje",
        "zalba":    "žalbu",
    }.get(body.tip_radnje, body.tip_radnje)

    ctx_lines = [
        f"PREDMET: {predmet.get('naziv','')} (tip: {predmet.get('tip','')})",
        f"PLANIRANA RADNJA: {tip_label}",
        f"Datum radnje: {body.datum_radnje or 'Nije naveden'}",
        f"Opis radnje: {(body.opis_radnje or 'Nije naveden')[:300]}",
        f"Tužilac: {predmet.get('tuzilac','N/A')} | Tuženi: {predmet.get('tuzeni','N/A')}",
        f"Sud: {predmet.get('sud','N/A')}",
        "",
        f"DOKUMENTI ({len(dokumenti)}):",
    ]
    for d in dokumenti[:10]:
        ctx_lines.append(f"  - {d.get('naziv_fajla','?')} [{d.get('tip_dokaza','?')}]")

    ctx_lines.append(f"\nROCISTA ({len(rokovi)}):")
    for r in rokovi[:8]:
        ctx_lines.append(f"  - {r.get('sud','?')} — {r.get('datum','?')} [{r.get('status','?')}]")

    if istorija:
        ctx_lines.append("\nPOSLEDNJE AKTIVNOSTI:")
        for h in istorija[:5]:
            ctx_lines.append(f"  - {(h.get('pitanje',''))[:80]}")

    if hronolog:
        ctx_lines.append("\nHRONOLOGIJA:")
        for h in hronolog[:5]:
            ctx_lines.append(f"  - {h.get('dogadjaj','')[:80]} ({h.get('datum_iso','')})")

    kontekst = "\n".join(ctx_lines)

    # GPT-4o Pre-Flight analiza
    import json as _json
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=_os.environ["OPENAI_API_KEY"])
        resp = await asyncio.to_thread(
            _pozovi_matter_intel_api,
            oai,
            model="gpt-4o",
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _PREFLIGHT_SYSTEM},
                {"role": "user",   "content": kontekst},
            ],
        )
        rezultat = _json.loads(resp.choices[0].message.content or "{}")
        if not isinstance(rezultat, dict):
            rezultat = {}
        # BLACKSWAN-AI-001 fix (Operation Black Swan, Mission 001, AI Attack): "score" and
        # "status" were returned to the caller and persisted DIRECTLY from the GPT response
        # via **rezultat, with no clamping or enum validation -- unlike case_actions.
        # prioritet and Genome's own snaga_predmeta_procent, which both correctly clamp/
        # validate a GPT-influenced number before it's trusted. Reproduced: a 0-doc/0-
        # hearing case returned status="spreman" (ready), score=250 (spec says 0-100) --
        # BOTH reached the lawyer's screen AND got persisted with a hardcoded
        # confidence="HIGH" tag, unchecked against the documented 0-100 range or the
        # documented 3-value enum.
        try:
            _score = int(rezultat.get("score", 0))
        except (TypeError, ValueError):
            _score = 0
        rezultat["score"] = max(0, min(100, _score))
        if rezultat.get("status") not in ("spreman", "potrebna_paznja", "nije_spreman"):
            rezultat["status"] = "potrebna_paznja"
    except Exception as e:
        _sentry_capture(e)
        logger.error("[PREFLIGHT] AI greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri generisanju Pre-Flight Check-a.")

    await UsageService.consume(uid, user.get("email", ""), "matter_intel")

    # Snimi u predmet_istorija (idempotentno, best-effort)
    try:
        from datetime import date
        tag = f"[PreFlight] {body.tip_radnje} {date.today().isoformat()}"
        await asyncio.to_thread(
            lambda: supa.table("predmet_istorija").insert({
                "predmet_id": predmet_id,
                "user_id":    uid,
                "pitanje":    tag,
                "odgovor":    _json.dumps(rezultat, ensure_ascii=False)[:8000],
                "confidence": "HIGH",
            }).execute()
        )
    except Exception:
        pass

    return {
        "predmet_id":   predmet_id,
        "tip_radnje":   body.tip_radnje,
        "datum_radnje": body.datum_radnje,
        **rezultat,
    }
