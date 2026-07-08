# -*- coding: utf-8 -*-
"""
Vindex AI — routers/workflow.py

Workflow Engine — kompletni životni ciklus predmeta.

Razlika:
  RANIJE: AI kreira task.
  SADA:   AI kreira task → dodeljuje → prati → eskalira → zatvara → uči.

Endpoints:
  POST   /api/workflow/template/kreiraj       — predložak sa koracima
  GET    /api/workflow/template/lista         — lista predložaka firme
  POST   /api/workflow/pokreni                — pokreni workflow za predmet
  GET    /api/workflow/predmet/{predmet_id}   — aktivni workflow predmeta
  PATCH  /api/workflow/step/{step_id}/zavrsi  — završi korak, aktivira sledeći
  GET    /api/workflow/eskalacije             — prekoračeni koraci
  POST   /api/workflow/eskalacije/cron        — cron za slanje eskalacionih alertova
  GET    /api/workflow/statistika             — dashboard: prosek, uska grla
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.workflow")
router = APIRouter(prefix="/api/workflow", tags=["workflow"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_firma(supa, uid: str) -> dict:
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("kancelarije")
                .select("id")
                .eq("admin_uid", uid)
                .maybe_single()
                .execute()
        )
        if r.data:
            return {"kancelarija_id": r.data["id"], "is_admin": True}
        r2 = await asyncio.to_thread(
            lambda: supa.table("kancelarija_clanovi")
                .select("kancelarija_id, uloga")
                .eq("user_id", uid)
                .eq("status", "aktivan")
                .maybe_single()
                .execute()
        )
        if r2.data:
            uloga = r2.data.get("uloga", "saradnik")
            return {
                "kancelarija_id": r2.data["kancelarija_id"],
                "is_admin": uloga in ("admin", "partner"),
            }
    except Exception:
        pass
    return {"kancelarija_id": None, "is_admin": False}


async def _notify(supa, uid: str, naslov: str, opis: str, urgentnost: str = "normalna") -> None:
    try:
        await asyncio.to_thread(
            lambda: supa.table("proactive_alerts").insert({
                "user_id":    uid,
                "tip":        "workflow",
                "naslov":     naslov[:100],
                "opis":       opis[:500],
                "urgentnost": urgentnost,
                "procitana":  False,
            }).execute()
        )
    except Exception as e:
        logger.debug("[WF] Notifikacija greška: %s", e)


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class TemplateKorak(BaseModel):
    naziv:           str
    opis:            Optional[str] = None
    rok_dana:        int = Field(5, ge=1, le=365)
    auto_assign:     Optional[str] = None  # 'partner'|'saradnik'|'ai'
    eskalacija_dana: int = Field(3, ge=1, le=30)


class TemplateRequest(BaseModel):
    naziv:        str = Field(..., min_length=2, max_length=200)
    tip_predmeta: Optional[str] = None
    opis:         Optional[str] = None
    koraci:       list[TemplateKorak] = Field(..., min_length=1)


class PokretanjeRequest(BaseModel):
    predmet_id:  str
    template_id: Optional[str] = None
    naziv:       Optional[str] = None
    # Ako nema template_id, minimalni workflow
    koraci:      Optional[list[TemplateKorak]] = None


class ZavrsiRequest(BaseModel):
    ishod:    Optional[str] = None
    komentar: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/template/kreiraj")
@limiter.limit("20/minute")
async def kreiraj_template(
    request: Request,
    payload: TemplateRequest,
    user:    dict = Depends(get_current_user),
):
    """Kreira predložak workflow-a sa koracima."""
    uid  = user["user_id"]
    supa = _get_supa()
    firma = await _get_firma(supa, uid)

    if not firma["kancelarija_id"]:
        raise HTTPException(status_code=403, detail="Niste član nijedne kancelarije.")

    koraci_json = [k.model_dump() for k in payload.koraci]

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("workflow_templates").insert({
                "kancelarija_id": firma["kancelarija_id"],
                "naziv":          payload.naziv,
                "tip_predmeta":   payload.tip_predmeta,
                "opis":           payload.opis or "",
                "koraci":         koraci_json,
            }).execute()
        )
        return {"ok": True, "template": r.data[0] if r.data else {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/template/lista")
@limiter.limit("30/minute")
async def lista_templatea(
    request:      Request,
    user:         dict = Depends(get_current_user),
    tip_predmeta: Optional[str] = None,
):
    """Lista predložaka workflow-a za firmu."""
    uid  = user["user_id"]
    supa = _get_supa()
    firma = await _get_firma(supa, uid)

    if not firma["kancelarija_id"]:
        return {"templates": [], "poruka": "Niste član nijedne kancelarije."}

    try:
        q = (supa.table("workflow_templates")
             .select("*")
             .eq("kancelarija_id", firma["kancelarija_id"])
             .eq("aktivan", True))
        if tip_predmeta:
            q = q.eq("tip_predmeta", tip_predmeta)
        r = await asyncio.to_thread(lambda: q.order("naziv").limit(50).execute())
        return {"templates": r.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pokreni")
@limiter.limit("20/minute")
async def pokreni_workflow(
    request: Request,
    payload: PokretanjeRequest,
    user:    dict = Depends(get_current_user),
):
    """
    Pokreće workflow za predmet.
    Može da koristi template ili ad-hoc korake.
    Kreira sve korake odjednom, aktivira prvi, šalje notifikaciju.
    """
    uid  = user["user_id"]
    supa = _get_supa()
    firma = await _get_firma(supa, uid)

    if not firma["kancelarija_id"]:
        raise HTTPException(status_code=403, detail="Niste član nijedne kancelarije.")

    # Odredi korake
    koraci = []
    naziv_wf = payload.naziv or "Workflow"

    if payload.template_id:
        tmpl_r = await asyncio.to_thread(
            lambda: supa.table("workflow_templates")
                .select("*")
                .eq("id", payload.template_id)
                .maybe_single()
                .execute()
        )
        if not tmpl_r.data:
            raise HTTPException(status_code=404, detail="Predložak nije pronađen.")
        tmpl = tmpl_r.data
        koraci = tmpl.get("koraci", [])
        naziv_wf = payload.naziv or tmpl.get("naziv", "Workflow")
    elif payload.koraci:
        koraci = [k.model_dump() for k in payload.koraci]
    else:
        raise HTTPException(status_code=400, detail="Potreban template_id ili lista koraka.")

    if not koraci:
        raise HTTPException(status_code=400, detail="Predložak nema korake.")

    try:
        # Kreiraj instancu
        inst_r = await asyncio.to_thread(
            lambda: supa.table("workflow_instances").insert({
                "kancelarija_id": firma["kancelarija_id"],
                "predmet_id":     payload.predmet_id,
                "template_id":    payload.template_id,
                "naziv":          naziv_wf,
                "kreirao_uid":    uid,
                "status":         "aktivan",
                "current_step":   0,
            }).execute()
        )
        if not inst_r.data:
            raise HTTPException(status_code=500, detail="Greška pri kreiranju workflow-a.")

        wf_id = inst_r.data[0]["id"]
        danas = date.today()

        # Kreiraj korake
        steps_insert = []
        for idx, korak in enumerate(koraci):
            rok = (danas + timedelta(days=int(korak.get("rok_dana", 5)))).isoformat()
            steps_insert.append({
                "workflow_id":     wf_id,
                "kancelarija_id":  firma["kancelarija_id"],
                "step_idx":        idx,
                "naziv":           korak.get("naziv", f"Korak {idx + 1}"),
                "opis":            korak.get("opis", ""),
                "assigned_uid":    korak.get("assigned_uid"),
                "status":          "aktivan" if idx == 0 else "ceka",
                "rok_datum":       rok,
                "eskalacija_dana": int(korak.get("eskalacija_dana", 3)),
            })

        await asyncio.to_thread(
            lambda: supa.table("workflow_steps").insert(steps_insert).execute()
        )

        # Notifikacija za prvi korak
        prvi = steps_insert[0]
        if prvi.get("assigned_uid"):
            asyncio.create_task(
                _notify(supa, prvi["assigned_uid"],
                        f"Novi workflow korak: {prvi['naziv']}",
                        f"Workflow '{naziv_wf}' je pokrenut. Vaš korak: {prvi['naziv']} (rok: {prvi['rok_datum']})",
                        "normalna")
            )

        return {
            "ok":          True,
            "workflow_id": wf_id,
            "naziv":       naziv_wf,
            "koraka":      len(koraci),
            "prvi_korak":  koraci[0].get("naziv", "Korak 1"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predmet/{predmet_id}")
@limiter.limit("30/minute")
async def workflow_predmeta(
    predmet_id: str,
    request:    Request,
    user:       dict = Depends(get_current_user),
):
    """Aktivni workflow i svi koraci za predmet."""
    uid  = user["user_id"]
    supa = _get_supa()
    firma = await _get_firma(supa, uid)

    if not firma["kancelarija_id"]:
        return {"workflows": []}

    try:
        wf_r = await asyncio.to_thread(
            lambda: supa.table("workflow_instances")
                .select("*")
                .eq("predmet_id", predmet_id)
                .eq("kancelarija_id", firma["kancelarija_id"])
                .order("started_at", desc=True)
                .limit(5)
                .execute()
        )
        workflows = wf_r.data or []

        # Za svaki workflow dohvati korake
        result = []
        for wf in workflows:
            steps_r = await asyncio.to_thread(
                lambda wid=wf["id"]: supa.table("workflow_steps")
                    .select("*")
                    .eq("workflow_id", wid)
                    .order("step_idx")
                    .execute()
            )
            result.append({**wf, "koraci": steps_r.data or []})

        return {"workflows": result, "ukupno": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/step/{step_id}/zavrsi")
@limiter.limit("60/minute")
async def zavrsi_korak(
    step_id: str,
    request: Request,
    payload: ZavrsiRequest,
    user:    dict = Depends(get_current_user),
):
    """
    Završava korak workflow-a.
    Automatski aktivira sledeći korak i šalje notifikaciju dodelje_nom.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        # Dohvati korak
        step_r = await asyncio.to_thread(
            lambda: supa.table("workflow_steps")
                .select("*, workflow_instances(id, naziv, predmet_id, kancelarija_id, kreirao_uid, current_step)")
                .eq("id", step_id)
                .maybe_single()
                .execute()
        )
        if not step_r.data:
            raise HTTPException(status_code=404, detail="Korak nije pronađen.")

        step = step_r.data
        wf   = step.get("workflow_instances") or {}
        wf_id = wf.get("id") or step.get("workflow_id")

        if step.get("status") in ("zavrseno", "preskoceno"):
            raise HTTPException(status_code=400, detail="Korak je već završen.")

        # Završi ovaj korak
        await asyncio.to_thread(
            lambda: supa.table("workflow_steps")
                .update({
                    "status":       "zavrseno",
                    "completed_at": _now_iso(),
                    "ishod":        payload.ishod,
                    "komentar":     payload.komentar,
                    "updated_at":   _now_iso(),
                })
                .eq("id", step_id)
                .execute()
        )

        sledeci_idx = (step.get("step_idx") or 0) + 1

        # Dohvati sledeći korak
        sledeci_r = await asyncio.to_thread(
            lambda: supa.table("workflow_steps")
                .select("*")
                .eq("workflow_id", wf_id)
                .eq("step_idx", sledeci_idx)
                .maybe_single()
                .execute()
        )
        sledeci = (sledeci_r.data if sledeci_r else None)

        if sledeci:
            # Aktiviraj sledeći korak
            await asyncio.to_thread(
                lambda: supa.table("workflow_steps")
                    .update({"status": "aktivan", "updated_at": _now_iso()})
                    .eq("id", sledeci["id"])
                    .execute()
            )
            await asyncio.to_thread(
                lambda: supa.table("workflow_instances")
                    .update({"current_step": sledeci_idx})
                    .eq("id", wf_id)
                    .execute()
            )
            # Notifikacija za sledeći korak
            if sledeci.get("assigned_uid"):
                asyncio.create_task(
                    _notify(supa, sledeci["assigned_uid"],
                            f"Sledeći korak: {sledeci['naziv']}",
                            f"Workflow '{wf.get('naziv', '')}': prethodni korak završen. "
                            f"Vaš korak: {sledeci['naziv']} (rok: {sledeci.get('rok_datum', '/')})",
                            "normalna")
                )
            return {"ok": True, "sledeci_korak": sledeci["naziv"], "sledeci_idx": sledeci_idx}
        else:
            # Nema više koraka — workflow završen
            await asyncio.to_thread(
                lambda: supa.table("workflow_instances")
                    .update({"status": "zavrsen", "completed_at": _now_iso()})
                    .eq("id", wf_id)
                    .execute()
            )
            # Notifikacija kreatoru
            if wf.get("kreirao_uid"):
                asyncio.create_task(
                    _notify(supa, wf["kreirao_uid"],
                            f"Workflow završen: {wf.get('naziv', '')}",
                            "Svi koraci su uspešno završeni.",
                            "normalna")
                )
            return {"ok": True, "workflow_zavrsen": True, "poruka": "Svi koraci su završeni."}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/eskalacije")
@limiter.limit("20/minute")
async def eskalacije(
    request: Request,
    user:    dict = Depends(get_current_user),
):
    """Svi prekoračeni aktivni koraci workflow-a (rok_datum < danas)."""
    uid  = user["user_id"]
    supa = _get_supa()
    firma = await _get_firma(supa, uid)

    if not firma["kancelarija_id"]:
        return {"eskalacije": [], "ukupno": 0}

    danas = date.today().isoformat()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("workflow_steps")
                .select("*, workflow_instances(naziv, predmet_id)")
                .eq("kancelarija_id", firma["kancelarija_id"])
                .eq("status", "aktivan")
                .lt("rok_datum", danas)
                .order("rok_datum")
                .limit(50)
                .execute()
        )
        koraci = r.data or []

        for k in koraci:
            rok = k.get("rok_datum", danas)
            try:
                dana_kasnjenja = (date.today() - date.fromisoformat(rok)).days
            except Exception:
                dana_kasnjenja = 0
            k["dana_kasnjenja"] = dana_kasnjenja

        return {"eskalacije": koraci, "ukupno": len(koraci)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _check_escalations() -> dict:
    """Standalone helper — šalje eskalacione alertove za prekoračene korake. Koristi unified cron."""
    supa  = _get_supa()
    danas = date.today().isoformat()
    poslato = 0

    r = await asyncio.to_thread(
        lambda: supa.table("workflow_steps")
            .select("id, naziv, assigned_uid, rok_datum, eskalacija_dana")
            .eq("status", "aktivan")
            .lt("rok_datum", danas)
            .limit(200)
            .execute()
    )
    for korak in (r.data or []):
        if not korak.get("assigned_uid"):
            continue
        rok = korak.get("rok_datum", danas)
        try:
            dana = (date.today() - date.fromisoformat(rok)).days
        except Exception:
            dana = 0
        if dana < (korak.get("eskalacija_dana") or 3):
            continue
        await _notify(supa, korak["assigned_uid"],
                      f"KASNJENJE: {korak['naziv']}",
                      f"Korak '{korak['naziv']}' kasni {dana} dan(a). Rok je bio: {rok}.",
                      "hitna")
        await asyncio.to_thread(
            lambda kid=korak["id"]: supa.table("workflow_steps")
                .update({"status": "eskaliran", "updated_at": _now_iso()})
                .eq("id", kid)
                .execute()
        )
        poslato += 1

    return {"eskalacionih_alertova": poslato}


@router.post("/eskalacije/cron")
async def eskalacije_cron(request: Request):
    """
    Cron endpoint — šalje eskalacione alertove za prekoračene korake.
    Header: X-Cron-Secret
    """
    cron_secret = os.getenv("BRIEFING_CRON_SECRET", "")
    x_secret    = request.headers.get("X-Cron-Secret", "")
    if cron_secret and x_secret != cron_secret:
        raise HTTPException(status_code=403, detail="Neovlašćen pristup.")

    try:
        rezultat = await _check_escalations()
        return {"ok": True, **rezultat}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistika")
@limiter.limit("10/minute")
async def workflow_statistika(
    request: Request,
    user:    dict = Depends(get_current_user),
):
    """Dashboard statistika: prosečno vreme završetka, uska grla."""
    uid  = user["user_id"]
    supa = _get_supa()
    firma = await _get_firma(supa, uid)

    if not firma["kancelarija_id"]:
        return {"poruka": "Niste član nijedne kancelarije."}

    try:
        inst_r, steps_r = await asyncio.gather(
            asyncio.to_thread(
                lambda: supa.table("workflow_instances")
                    .select("status, started_at, completed_at")
                    .eq("kancelarija_id", firma["kancelarija_id"])
                    .limit(200)
                    .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("workflow_steps")
                    .select("naziv, status, rok_datum, completed_at, created_at")
                    .eq("kancelarija_id", firma["kancelarija_id"])
                    .limit(500)
                    .execute()
            ),
        )
        instances = inst_r.data or []
        steps     = steps_r.data or []

        # Agregiraj statusove instanci
        by_status = {}
        for inst in instances:
            s = inst.get("status", "aktivan")
            by_status[s] = by_status.get(s, 0) + 1

        # Uska grla: koraci koji najčešće kasne
        kasne: dict[str, int] = {}
        for s in steps:
            if s.get("rok_datum") and s.get("status") == "aktivan":
                try:
                    if date.fromisoformat(s["rok_datum"]) < date.today():
                        kasne[s["naziv"]] = kasne.get(s["naziv"], 0) + 1
                except Exception:
                    pass

        uska_grla = sorted(kasne.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "ukupno_workflow": len(instances),
            "by_status":       by_status,
            "ukupno_koraka":   len(steps),
            "uska_grla":       [{"naziv": n, "kasnjenja": k} for n, k in uska_grla],
            "aktivnih":        by_status.get("aktivan", 0),
            "zavrsenih":       by_status.get("zavrsen", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
