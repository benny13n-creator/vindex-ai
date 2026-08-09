# -*- coding: utf-8 -*-
"""
Vindex AI — routers/rocista.py
Faza 1: Ročišta entity

POST   /api/rocista              — kreiraj ročište
GET    /api/rocista              — lista ročišta za predmet ili sva
PATCH  /api/rocista/{id}         — izmeni ročište
DELETE /api/rocista/{id}         — obriši ročište
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from datetime import date as _date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from security.html_sanitize import sanitize_user_input
from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.rocista")
router = APIRouter(tags=["rocista"])

_VALID_STATUS = {"zakazano", "odrzano", "odlozeno", "otkazano"}


def _norm_vreme(v: Optional[str]) -> Optional[str]:
    """Supabase vraća TIME kao 'HH:MM:SS' — normalizujemo na 'HH:MM'."""
    if not v:
        return None
    return v[:5] if len(v) >= 5 else v


class RocisteReq(BaseModel):
    predmet_id:         str           = Field(..., min_length=1, max_length=64)
    sud:                str           = Field(..., min_length=1, max_length=300)
    datum:              str           = Field(..., min_length=10, max_length=10)
    vreme:              Optional[str] = Field(None, max_length=8)
    sudnica:            Optional[str] = Field(None, max_length=100)
    broj_predmeta_suda: Optional[str] = Field(None, max_length=100)
    napomena:           Optional[str] = Field(None, max_length=2000)

    @field_validator("datum")
    @classmethod
    def _val_datum(cls, v: str) -> str:
        from datetime import date as _date
        try:
            _date.fromisoformat(v)
        except ValueError:
            raise ValueError("datum mora biti YYYY-MM-DD")
        return v

    @field_validator("vreme")
    @classmethod
    def _val_vreme(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("vreme mora biti HH:MM")
        return v

    @field_validator("sud", "sudnica", "broj_predmeta_suda", "napomena")
    @classmethod
    def _sanitize(cls, v: Optional[str]) -> Optional[str]:
        # XSS sweep (2026-07-24): "napomena" ovde je izvor koji
        # routers/email_notif.py kasnije interpolira direktno u HTML email
        # šablon (preko "dogadjaj": f"Follow-up ročište: {body.napomena}"
        # u FollowUpReq ispod) -- nesanitizovan HTML markup u ovom polju je
        # bio stvaran, sledljiv HTML-injection put do email klijenta.
        return sanitize_user_input(v)


class RocistePatchReq(BaseModel):
    sud:                Optional[str] = Field(None, max_length=300)
    datum:              Optional[str] = Field(None, max_length=10)
    vreme:              Optional[str] = Field(None, max_length=8)
    sudnica:            Optional[str] = Field(None, max_length=100)
    broj_predmeta_suda: Optional[str] = Field(None, max_length=100)
    status:             Optional[str] = Field(None, max_length=20)
    napomena:           Optional[str] = Field(None, max_length=2000)
    # Final Beta Gate F17 (MEDIUM): optional optimistic-concurrency token,
    # same opt-in/backward-compatible shape as api.py::update_predmet's own
    # if_updated_at (Program Lambda Cert 004) -- a caller not yet sending it
    # gets the exact prior unconditional-update behavior.
    if_updated_at:      Optional[str] = Field(None, max_length=64)

    @field_validator("datum")
    @classmethod
    def _val_datum(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        from datetime import date as _date
        try:
            _date.fromisoformat(v)
        except ValueError:
            raise ValueError("datum mora biti YYYY-MM-DD")
        return v

    @field_validator("status")
    @classmethod
    def _val_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_STATUS:
            raise ValueError(f"status mora biti jedan od: {sorted(_VALID_STATUS)}")
        return v

    @field_validator("vreme")
    @classmethod
    def _val_vreme(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("vreme mora biti HH:MM")
        return v

    @field_validator("sud", "sudnica", "broj_predmeta_suda", "napomena")
    @classmethod
    def _sanitize(cls, v: Optional[str]) -> Optional[str]:
        return sanitize_user_input(v)


@router.post("/api/rocista")
@limiter.limit("30/minute")
async def kreiraj_rociste(
    body: RocisteReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id")
            .eq("id", body.predmet_id)
            .eq("user_id", uid)
            .execute()
    )
    if not pred_r.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")

    payload = {
        "predmet_id":          body.predmet_id,
        "user_id":             uid,
        "sud":                 body.sud.strip(),
        "datum":               body.datum,
        "vreme":               body.vreme or None,
        "sudnica":             (body.sudnica or "").strip() or None,
        "broj_predmeta_suda":  (body.broj_predmeta_suda or "").strip() or None,
        "napomena":            (body.napomena or "").strip() or None,
        "status":              "zakazano",
    }

    # Program Phoenix, Mission 005 (LIVINGSYS-DEBT-043): this endpoint had zero idempotency
    # protection -- a client retry (perceived timeout, double-submit) created a 2nd physical
    # `rocista` row AND fired a 2nd ROCISTE_ZAKAZANO event (double genome_refresh cost, plus
    # refresh_case_actions/project_notifications running twice, same root-cause family as
    # -010). `rocista` has no idempotency-key column (unlike shared/intake_queue.py's own,
    # which would need a migration) -- reusing existing columns instead: an identical
    # (predmet_id, sud, datum, vreme) row already inserted in the last 30s is treated as the
    # same logical request, not a new hearing (2 genuinely distinct real hearings sharing the
    # exact same court/date/time for the same case is not a realistic scenario this window
    # would ever wrongly collapse).
    _dup_r = await asyncio.to_thread(
        lambda: supa.table("rocista").select("*")
            .eq("predmet_id", body.predmet_id).eq("user_id", uid)
            .eq("sud", payload["sud"]).eq("datum", payload["datum"])
            .gte("created_at", (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat())
            .execute()
    )
    _existing = next(
        (r for r in (_dup_r.data or []) if (r.get("vreme") or None) == payload["vreme"]), None
    )
    if _existing:
        logger.info("[ROCISTE] duplikat zahtev preskočen uid=%.8s predmet=%s datum=%s", uid, body.predmet_id, body.datum)
        _existing["vreme"] = _norm_vreme(_existing.get("vreme"))
        return {"rociste": _existing, "ok": True}

    r = await asyncio.to_thread(
        lambda: supa.table("rocista").insert(payload).execute()
    )
    if not r.data:
        raise HTTPException(status_code=500, detail="Greška pri kreiranju ročišta")

    row = r.data[0]
    row["vreme"] = _norm_vreme(row.get("vreme"))
    logger.info("[ROCISTE] kreirano uid=%.8s predmet=%s datum=%s", uid, body.predmet_id, body.datum)

    # ── ROCISTE_ZAKAZANO — Program Delta, Sprint 003 (2026-08-05) ───────────
    # Canonical Event Migration II. This USED TO be a direct, in-process
    # `asyncio.create_task(_rociste_genome_bg())` call (with a crude
    # `asyncio.sleep(2)` heuristic) -- rocista.py deciding for itself "a new
    # hearing changes the case's tactical context, refresh Genome". Per this
    # sprint's own Task 2 ("rocista.py ne sme znati kako se osvežava
    # Genome"), replaced with a durable ROCISTE_ZAKAZANO emission --
    # rocista.py no longer imports or calls _run_genome_background at all.
    # EventType.ROCISTE_ZAKAZANO existed since the original Event Bus
    # (services/event_bus.py) but had ZERO handlers and was NEVER emitted
    # anywhere in the repo (confirmed by grep) -- a genuinely dead event
    # type until this sprint, not a previously-working mechanism being
    # migrated. The Canonical Consequence Engine (services/case_evolution.py)
    # now owns it, reusing the EXISTING genome_refresh executor UNCHANGED
    # (no new Genome capability) -- exactly the same single consequence the
    # code above produced, nothing added (no Timeline entry -- this endpoint
    # never created one before, so none is invented now).
    try:
        from services.event_bus import EventType, emit_durable
        await emit_durable(
            EventType.ROCISTE_ZAKAZANO,
            uid,
            body.predmet_id,
            {"sud": body.sud.strip(), "datum": body.datum, "trigger": "rociste_created"},
        )
    except Exception as _e:
        logger.warning("[ROCISTE] ROCISTE_ZAKAZANO durable event upis greška (non-fatal) predmet=%s: %s", body.predmet_id, _e)

    return {"rociste": row, "ok": True}


@router.get("/api/rocista")
@limiter.limit("60/minute")
async def lista_rocista(
    request: Request,
    predmet_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    q = supa.table("rocista").select("*").eq("user_id", uid)
    if predmet_id:
        q = q.eq("predmet_id", predmet_id)
    else:
        # Final Beta Gate F27 (MEDIUM): the Calendar view (static/vindex.js's
        # kalendarLoad) calls this endpoint with no predmet_id -- "every
        # upcoming hearing across all my cases" -- but this query never
        # filtered by predmeti.status, so a hearing belonging to a case
        # closed today still rendered on the Calendar tomorrow. Only applied
        # in the no-predmet_id (cross-case) branch: a lawyer explicitly
        # viewing one specific (possibly closed) case's own hearing history
        # from that case's own page must still see it -- same distinction
        # already drawn by kalendar.py/email_notif.py's own active-case
        # filters.
        _aktivni_r = await asyncio.to_thread(
            lambda: supa.table("predmeti").select("id").eq("user_id", uid)
                .not_.in_("status", ["zatvoren", "arhiviran", "odbijen"]).execute()
        )
        _aktivni_ids = [p["id"] for p in (_aktivni_r.data or [])]
        q = q.in_("predmet_id", _aktivni_ids) if _aktivni_ids else q.eq("predmet_id", "__none__")
    if status:
        q = q.eq("status", status)

    r = await asyncio.to_thread(lambda: q.order("datum").limit(limit).offset(offset).execute())
    rows = r.data or []
    for row in rows:
        row["vreme"] = _norm_vreme(row.get("vreme"))
    return {"rocista": rows, "ukupno": len(rows), "limit": limit, "offset": offset}


@router.patch("/api/rocista/{rociste_id}")
@limiter.limit("30/minute")
async def izmeni_rociste(
    rociste_id: str,
    body: RocistePatchReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if_updated_at = updates.pop("if_updated_at", None)
    if not updates:
        raise HTTPException(status_code=422, detail="Nema polja za izmenu")

    # Final Beta Gate F26 (HIGH): a hearing's datum/vreme/status materially
    # affects what Dashboard (reads `rocista` live) and Workspace (reads
    # `case_actions`, only updated by the SAME 3 consequences hearing
    # CREATION already triggers) show as "today's hearing" -- before this
    # fix, a reschedule updated only the raw row and fired NOTHING
    # downstream, so Workspace/notifications kept showing the OLD date/
    # status until an unrelated event happened to touch the case. Captured
    # before the write so the emitted event reflects what actually changed.
    _materially_changed = bool({"datum", "vreme", "status"} & updates.keys())

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Final Beta Gate F17 (MEDIUM): optimistic-concurrency guard, same
    # opt-in shape as api.py::update_predmet -- `rocista` already has a
    # live, trigger-refreshed updated_at column (used immediately below),
    # so no migration is needed. A caller not sending if_updated_at gets
    # the exact prior unconditional-update behavior.
    q = supa.table("rocista").update(updates).eq("id", rociste_id).eq("user_id", uid)
    if if_updated_at:
        q = q.eq("updated_at", if_updated_at)
    r = await asyncio.to_thread(lambda: q.execute())

    if if_updated_at and not r.data:
        exists = await asyncio.to_thread(
            lambda: supa.table("rocista").select("id").eq("id", rociste_id).eq("user_id", uid).maybe_single().execute()
        )
        if not exists.data:
            raise HTTPException(status_code=404, detail="Ročište nije pronađeno")
        raise HTTPException(
            status_code=409,
            detail="Ročište je izmenjeno u međuvremenu. Osvežite stranicu i pokušajte ponovo.",
        )
    if not r.data:
        raise HTTPException(status_code=404, detail="Ročište nije pronađeno")

    row = r.data[0]
    row["vreme"] = _norm_vreme(row.get("vreme"))

    if _materially_changed:
        try:
            from services.event_bus import EventType, emit_durable
            await emit_durable(
                EventType.ROCISTE_ZAKAZANO,
                uid,
                row.get("predmet_id"),
                {"sud": row.get("sud"), "datum": row.get("datum"), "trigger": "rociste_updated"},
            )
        except Exception as _e:
            logger.warning("[ROCISTE] ROCISTE_ZAKAZANO (update) durable event upis greška (non-fatal) rociste=%s: %s", rociste_id, _e)

    return {"rociste": row, "ok": True}


# ── PRIORITET 5: Hearing Follow-Up ───────────────────────────────────────────

class FollowUpReq(BaseModel):
    predmet_id: str           = Field(..., min_length=1, max_length=64)
    napomena:   str           = Field(..., min_length=1, max_length=4000)
    rociste_id: Optional[str] = Field(default=None)

    @field_validator("napomena")
    @classmethod
    def _sanitize(cls, v: str) -> str:
        # Ova vrednost se direktno koristi u "dogadjaj": f"Follow-up
        # ročište: {body.napomena[:120]}" (linija ispod) -- konfirmisan
        # izvor HTML-injekcije u email_notif.py pre ove izmene.
        return sanitize_user_input(v)


@router.post("/api/rociste/followup")
@limiter.limit("20/minute")
async def hearing_followup(
    body: FollowUpReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Post-ročište follow-up:
    - Kreira belešku sa napomenom
    - Kreira hronologiju entry
    - Ažurira istoriju predmeta
    - Generiše preporuke sledećih koraka (rule-based)
    """
    uid  = user["user_id"]
    supa = _get_supa()
    today_iso = _date.today().isoformat()

    # Proveri vlasništvo
    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id,naziv,status")
            .eq("id", body.predmet_id)
            .eq("user_id", uid)
            .limit(1)
            .execute()
    )
    if not pred_r.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    predmet = pred_r.data[0]
    naziv   = predmet.get("naziv", "Predmet")

    # Taguj napomenu ročišta ako je dat rociste_id
    tag     = f"[Ročište follow-up{' #'+body.rociste_id[:8] if body.rociste_id else ''}]"
    tekst_b = f"{tag} {body.napomena}"

    # Paralelno upiši: beleška + hronologiju + istoriju
    await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_beleske").insert({
            "predmet_id": body.predmet_id,
            "user_id":    uid,
            "sadrzaj":    tekst_b[:2000],
        }).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").insert({
            "predmet_id": body.predmet_id,
            "user_id":    uid,
            "dogadjaj":   f"Follow-up ročište: {body.napomena[:120]}",
            "datum":      today_iso,
            "datum_iso":  today_iso,
            "vaznost":    "bitan",
            "akter":      "Advokat",
        }).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija").insert({
            "predmet_id": body.predmet_id,
            "user_id":    uid,
            "pitanje":    f"[Follow-up ročište] {today_iso}",
            "odgovor":    body.napomena[:2000],
            "confidence": "HIGH",
        }).execute()),
        return_exceptions=True,
    )

    # Rule-based preporuke sledećih koraka
    napomena_lower = body.napomena.lower()
    preporuke: list[str] = []

    if any(w in napomena_lower for w in ("odloženo", "odlozeno", "odlaganje", "odložiti")):
        preporuke.append("Ročište je odloženo — proverite i ažurirajte datum sledećeg ročišta.")
        preporuke.append("Obavestite klijenta o novom terminu.")
    if any(w in napomena_lower for w in ("dokaz", "dokaze", "dokumenta", "dokumenti", "veštačenje", "vestacenje")):
        preporuke.append("Identifikujte nedostajuće dokaze i zatražite ih od klijenta ili suda.")
    if any(w in napomena_lower for w in ("svedok", "svedoci", "saslušanje", "ispit")):
        preporuke.append("Pripremite svedoke za naredni pretres — uskladite iskaze sa dokumentacijom.")
    if any(w in napomena_lower for w in ("nagodba", "sporazum", "poravnanje")):
        preporuke.append("Razgovarajte sa klijentom o mogućnosti nagodbe — procenite uslove.")
    if any(w in napomena_lower for w in ("žalba", "zalba", "pobijanje", "revizija")):
        preporuke.append("Proverite rokove za žalbu i pripremite osnove za pobijanje presude.")
    if any(w in napomena_lower for w in ("presuda", "odluka", "rešenje", "resenje")):
        preporuke.append("Analizirajte presudu/odluku i utvrdite dalji tok postupka.")
    if any(w in napomena_lower for w in ("rok", "termin", "zakazano")):
        preporuke.append("Dodajte novi rok u sistem i obavestite klijenta o terminima.")

    if not preporuke:
        preporuke.append("Ažurirajte status predmeta i zabeleškite ishod ročišta.")
        preporuke.append("Planirajte sledeće korake sa klijentom.")

    logger.info("[FOLLOWUP] uid=%.8s predmet=%s", uid, body.predmet_id)

    return {
        "ok":         True,
        "predmet_id": body.predmet_id,
        "naziv":      naziv,
        "datum":      today_iso,
        "preporuke":  preporuke,
        "akcije": {
            "beleska_kreirana":     True,
            "hronologija_azurana":  True,
            "istorija_azurana":     True,
        },
    }


@router.delete("/api/rocista/{rociste_id}")
@limiter.limit("30/minute")
async def obrisi_rociste(
    rociste_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    r = await asyncio.to_thread(
        lambda: supa.table("rocista")
            .delete()
            .eq("id", rociste_id)
            .eq("user_id", uid)
            .execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Ročište nije pronađeno")

    # V34: audit tek POSLE zero-row guarda -- 0 obrisanih redova znači 404 i
    # nijedan zapis. log_action je best-effort po sopstvenom ugovoru, pa
    # neuspeh audita ne menja ishod brisanja.
    from shared.audit_immutable import log_action
    await log_action("rociste_delete", user_id=uid,
                     resource_type="rociste", resource_id=rociste_id)

    return {"ok": True}
