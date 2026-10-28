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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from security.html_sanitize import sanitize_user_input
from shared.deps import _get_supa, get_current_user
from shared.rate import limiter
from shared import rokovi as _rokovi_domen
from shared import rokovi as _IZVOR  # migracija 127 — kanonske vrednosti `izvor`

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


def _hitni_podsetnici(uid: str) -> None:
    """S2 (D2): posle advokatove radnje proveri da li događaju treba podsetnik koji ne sme da čeka dnevno slanje.
    Pozadinski zadatak POSLE odgovora — radnja je već sačuvana i ne čeka SMTP; greška se samo beleži."""
    try:
        from routers.email_notif import proveri_hitne_podsetnike
        proveri_hitne_podsetnike(uid)
    except Exception as exc:
        logger.error("[PODSETNIK] hitna provera nije pokrenuta uid=%.8s: %s", uid, type(exc).__name__)


@router.post("/api/rocista")
@limiter.limit("30/minute")
async def kreiraj_rociste(
    body: RocisteReq,
    request: Request,
    user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
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

    if background_tasks is not None:
        background_tasks.add_task(_hitni_podsetnici, uid)
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
    background_tasks: BackgroundTasks = None,
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

    # S1-C2 (revizija Sektora 1): „Vrati na zakazano“ na ODLOŽENOM ročištu posle zakazanog nastavka ostavljalo je dva
    # aktivna ročišta (Danas, kalendar, nedeljni email). Nastavak = drugo zakazano ročište istog predmeta sa kasnijim datumom.
    if updates.get("status") == "zakazano":
        try:
            _cur = await asyncio.to_thread(lambda: supa.table("rocista").select("id, predmet_id, datum, status, updated_at")
                                           .eq("id", rociste_id).eq("user_id", uid).limit(1).execute())
            _c = (_cur.data or [None])[0]
            _nastavci = []
            if _c and (_c.get("status") or "zakazano") == "odlozeno":
                _sva = await asyncio.to_thread(lambda: supa.table("rocista").select("id, datum, status, created_at")
                                               .eq("user_id", uid).eq("predmet_id", _c.get("predmet_id")).execute())

                def _nastavak(x) -> bool:
                    # 3. krug revizije: `updated_at` se menja pri svakoj izmeni, a nastavak se može upisati i PRE oznake
                    # „odloženo“ — zato je nastavak svako zakazano ročište istog predmeta sa KASNIJIM datumom ili upisano
                    # posle poslednje izmene. Lažno 409 (poruka kaže šta da se uradi) je bezbednije od dva aktivna ročišta.
                    if x.get("id") == rociste_id or (x.get("status") or "zakazano") != "zakazano":
                        return False
                    if _c.get("datum") and str(x.get("datum") or "") > str(_c.get("datum")):
                        return True
                    return bool(x.get("created_at") and _c.get("updated_at") and str(x["created_at"]) >= str(_c["updated_at"]))
                _nastavci = [x for x in (_sva.data or []) if _nastavak(x)]
        except Exception as exc:
            logger.error("[ROCISTA] provera nastavka pre vraćanja na zakazano nije uspela id=%s: %s", rociste_id, type(exc).__name__)
            raise HTTPException(status_code=503, detail="Stanje ročišta trenutno nije moguće proveriti. Ništa nije izmenjeno.")
        if _nastavci:
            raise HTTPException(
                status_code=409,
                detail=f"Za ovaj predmet je već zakazano kasnije ročište ({_nastavci[0].get('datum')}) — verovatno nastavak "
                       "odloženog. Da biste vratili ovo ročište, prvo otkažite to ročište. Ništa nije izmenjeno.")

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

    if background_tasks is not None:
        background_tasks.add_task(_hitni_podsetnici, uid)
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
            "vaznost":    _rokovi_domen.normalizuj_vaznost("bitan"),
            "akter":      "Advokat",
            # migracija 127 — W-ROCISTE: advokat unosi follow-up posle
            # rocista.
            "izvor":      _IZVOR.IZVOR_HUMAN_DIRECT,
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

    # Wave 2, Task 2D corrective closure (VINDEX-V1-EXECUTION-CONTRACT.md,
    # 2026-09-20) -- the delete and the durable SourceInvalidated event
    # used to be two independent network round-trips (a raw .delete()
    # here, then a separate emit_source_invalidated() call). A process
    # crash between them could leave the hearing deleted with NO event
    # ever recorded -- its own PRIPREMITI_PODNESAK case_actions row would
    # stay open forever, not until "some later event happens to touch the
    # matter," which the founder correctly rejected as not an integrity
    # guarantee. Now one Postgres RPC (migration 131): the delete and the
    # event insert happen inside that function's own single transaction --
    # either both commit or neither does.
    from services.event_bus import invalidate_rociste_atomic
    from shared.ai_provenance import current_correlation_id
    _deleted_predmet_id, invalidated = await invalidate_rociste_atomic(
        rociste_id=rociste_id, user_id=uid, correlation_id=current_correlation_id(), supa=supa,
    )
    if not invalidated:
        raise HTTPException(status_code=404, detail="Ročište nije pronađeno")

    # V34: audit tek POSLE zero-row guarda -- 0 obrisanih redova znači 404 i
    # nijedan zapis. log_action je best-effort po sopstvenom ugovoru, pa
    # neuspeh audita ne menja ishod brisanja.
    from shared.audit_immutable import log_action
    await log_action("rociste_delete", user_id=uid,
                     resource_type="rociste", resource_id=rociste_id)

    return {"ok": True}


# ── N3: predlozi ročišta iz dokumenata predmeta ──────────────────────────────
#
# Bojan: „da on sam radi zakazivanje u kalendaru". Datum iz sudskog poziva se ranije prekucavao ručno.
# Ovde se iz teksta dokumenata PREDMETA čitaju PREDLOZI (shared/rociste_iz_teksta.py) — ništa se ne upisuje
# u `rocista`. Advokat predlog proverava i zakazuje postojećim POST /api/rocista (isti 30-s duplikat
# štit), ili ga odbacuje (zapis u `audit_immutable`, bez nove tabele i migracije). Predlog nestaje kad
# postoji ročište istog datuma (i vremena, ako su oba poznata), bez obzira na stanje tog ročišta.

_AKCIJA_PREDLOG_ODBACEN = "rociste_predlog_odbacen"
_RESURS_PREDLOG = "rociste_predlog"
_KLJUC_PREDLOGA = re.compile(r"^\d{4}-\d{2}-\d{2}\|(?:\d{2}:\d{2})?$")


async def _predmet_pozivaoca(supa, predmet_id: str, uid: str) -> None:
    r = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).maybe_single().execute()
    )
    if not getattr(r, "data", None):
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")


@router.get("/api/rocista/predlozi")
@limiter.limit("60/minute")
async def predlozi_rocista(
    request: Request,
    predmet_id: str,
    user: dict = Depends(get_current_user),
):
    from routers.email_notif import _danas_beograd
    from shared.rociste_iz_teksta import broj_iz_teksta, nadji_rocista, sud_iz_teksta

    uid  = user["user_id"]
    supa = _get_supa()
    await _predmet_pozivaoca(supa, predmet_id, uid)
    try:
        dok_r, roc_r = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("id, naziv_fajla, tekst_sadrzaj")
                              .eq("predmet_id", predmet_id).eq("user_id", uid).limit(500).execute()),
            asyncio.to_thread(lambda: supa.table("rocista").select("datum, vreme")
                              .eq("predmet_id", predmet_id).eq("user_id", uid).execute()),
        )
    except Exception as exc:
        logger.warning("[ROCISTE/PREDLOZI] čitanje palo predmet=%s: %s", predmet_id, exc)
        raise HTTPException(status_code=503, detail="Predlozi ročišta nisu učitani. Ovo nije prazan spisak.")

    danas = _danas_beograd()
    postojeca = [(str(r.get("datum") or "")[:10], _norm_vreme(r.get("vreme"))) for r in (roc_r.data or [])]
    predlozi: dict = {}
    bez_teksta = proslih = 0
    for d in (dok_r.data or []):
        tekst = d.get("tekst_sadrzaj") or ""
        if not tekst.strip():
            bez_teksta += 1
            continue
        sud, broj = sud_iz_teksta(tekst), broj_iz_teksta(tekst)
        for n in nadji_rocista(tekst):
            if n["datum"] < danas:
                proslih += 1
                continue
            datum = n["datum"].isoformat()
            if any(pd == datum and (pv is None or n["vreme"] is None or pv == n["vreme"]) for pd, pv in postojeca):
                continue
            kljuc = f"{datum}|{n['vreme'] or ''}"
            p = predlozi.setdefault(kljuc, {"kljuc": kljuc, "datum": datum, "vreme": n["vreme"], "sud": sud,
                                            "sudnica": n["sudnica"], "broj_predmeta_suda": broj, "izvori": []})
            for polje, v in (("sud", sud), ("sudnica", n["sudnica"]), ("broj_predmeta_suda", broj)):
                if not p[polje] and v:
                    p[polje] = v
            p["izvori"].append({"dokument_id": d.get("id"), "naziv": d.get("naziv_fajla") or "Dokument", "citat": n["citat"]})

    if predlozi:
        try:
            odb = await asyncio.to_thread(
                lambda: supa.table("audit_immutable").select("resource_id")
                    .eq("user_id", uid).eq("action", _AKCIJA_PREDLOG_ODBACEN).eq("resource_type", _RESURS_PREDLOG)
                    .in_("resource_id", [f"{predmet_id}|{k}" for k in predlozi]).execute()
            )
        except Exception as exc:
            logger.warning("[ROCISTE/PREDLOZI] odbacivanja nisu pročitana predmet=%s: %s", predmet_id, exc)
            raise HTTPException(status_code=503, detail="Predlozi ročišta nisu učitani. Ovo nije prazan spisak.")
        odbaceni = {str(red.get("resource_id") or "").split("|", 1)[-1] for red in (odb.data or [])}
        for k in odbaceni:
            predlozi.pop(k, None)
        # Odbačen datum SA vremenom gasi i isti datum bez vremena (isto ročište iz drugog dokumenta).
        for k in [k for k, v in list(predlozi.items()) if v["vreme"] is None]:
            if any(o.startswith(predlozi[k]["datum"] + "|") and not o.endswith("|") for o in odbaceni):
                predlozi.pop(k)

    # Isti datum iz dva dokumenta, jednom sa vremenom a jednom bez → JEDAN predlog (sa vremenom), oba izvora.
    # Posle odbacivanja: odbačen predlog bez vremena se ne vraća kroz spajanje sa novim dokumentom.
    for kljuc in [k for k, v in predlozi.items() if v["vreme"] is None]:
        sa_vremenom = [v for v in predlozi.values() if v["datum"] == predlozi[kljuc]["datum"] and v["vreme"]]
        if len(sa_vremenom) == 1:
            sa_vremenom[0]["izvori"].extend(predlozi.pop(kljuc)["izvori"])

    return {"predlozi": sorted(predlozi.values(), key=lambda x: (x["datum"], x["vreme"] or "")),
            "dokumenata_bez_teksta": bez_teksta, "proslih": proslih}


class OdbaciPredlogReq(BaseModel):
    predmet_id: str = Field(..., min_length=1, max_length=64)
    kljuc:      str = Field(..., min_length=11, max_length=16)


@router.post("/api/rocista/predlozi/odbaci")
@limiter.limit("30/minute")
async def odbaci_predlog_rocista(
    body: OdbaciPredlogReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    if not _KLJUC_PREDLOGA.match(body.kljuc):
        raise HTTPException(status_code=422, detail="Neispravan predlog.")
    uid  = user["user_id"]
    supa = _get_supa()
    await _predmet_pozivaoca(supa, body.predmet_id, uid)
    from shared.audit_immutable import log_action
    zapis = await log_action(_AKCIJA_PREDLOG_ODBACEN, user_id=uid, resource_type=_RESURS_PREDLOG,
                             resource_id=f"{body.predmet_id}|{body.kljuc}")
    if zapis is None:
        raise HTTPException(status_code=503, detail="Odbacivanje nije zabeleženo. Predlog ostaje.")
    return {"ok": True}
