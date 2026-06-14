# -*- coding: utf-8 -*-
"""
Vindex AI — routers/billing.py

POST   /billing/entries                  — unesi naplativu radnju
PATCH  /billing/entries/{entry_id}       — izmeni (samo dok nije fakturisana)
DELETE /billing/entries/{entry_id}       — obrisi (samo dok nije fakturisana)
GET    /billing/entries?predmet_id=X     — sve radnje za predmet
POST   /billing/timer/start              — pokreni tajmer
POST   /billing/timer/stop               — zaustavi, opcionalno kreiraj entry
GET    /billing/timer/aktivan            — aktivni tajmer
GET    /billing/tarifa                   — lista AKS tarife sa RSD iznosima
GET    /billing/tarifa/{sifra}           — jedna stavka
POST   /billing/faktura                  — kreiraj fakturu iz odabranih radnji
GET    /billing/faktura/{id}/pdf         — PDF fakture
PATCH  /billing/faktura/{id}/status      — promeni status fakture
GET    /billing/pregled                  — mesecni pregled naplativosti
"""
from __future__ import annotations

import asyncio
import io
import logging
import math
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.billing")
router = APIRouter(prefix="/billing", tags=["billing"])

# Sl. glasnik RS 56/2025 — od 5. jula 2025.
BOD_RSD = 50

# AKS Advokatska tarifa — najcesci postupci.
# Bodovi su okvirni; verifikuj u Sluzbenom glasniku RS 56/2025.
AKS_TARIFA: dict[str, dict] = {
    "T01": {"naziv": "Tužba za novčano potraživanje (prostija)",  "bodovi": 12},
    "T02": {"naziv": "Tužba za novčano potraživanje (složenija)", "bodovi": 24},
    "T03": {"naziv": "Tužba na davanje/činjenje/trpljenje",       "bodovi": 18},
    "T04": {"naziv": "Žalba na prvostepenu presudu",              "bodovi": 12},
    "T05": {"naziv": "Revizija / vanredni pravni lek",            "bodovi": 20},
    "T06": {"naziv": "Ustavna žalba",                             "bodovi": 30},
    "T07": {"naziv": "Odgovor na tužbu",                          "bodovi": 12},
    "T08": {"naziv": "Odgovor na žalbu",                          "bodovi": 10},
    "T09": {"naziv": "Prigovor (procesni ili materijalni)",        "bodovi": 10},
    "T10": {"naziv": "Zastupanje na ročištu (prostija parnica)",  "bodovi": 16},
    "T11": {"naziv": "Zastupanje na ročištu (složenija parnica)", "bodovi": 24},
    "T12": {"naziv": "Zastupanje u krivičnom predmetu (ročište)", "bodovi": 24},
    "T13": {"naziv": "Žalba u krivičnom postupku",                "bodovi": 16},
    "T14": {"naziv": "Predlog za izvršenje (prostiji)",           "bodovi": 10},
    "T15": {"naziv": "Predlog za izvršenje (složeniji)",          "bodovi": 16},
    "T16": {"naziv": "Predlog za obezbeđenje potraživanja",       "bodovi": 14},
    "T17": {"naziv": "Usmena konsultacija (do 1 sat)",            "bodovi": 6},
    "T18": {"naziv": "Pisana konsultacija / pravni savet",        "bodovi": 10},
    "T19": {"naziv": "Podnesak u sudskom postupku",               "bodovi": 8},
    "T20": {"naziv": "Podnesak / uputstvo stranci",               "bodovi": 6},
    "T21": {"naziv": "Ugovor (prostiji)",                         "bodovi": 16},
    "T22": {"naziv": "Ugovor (složeniji)",                        "bodovi": 30},
    "T23": {"naziv": "Punomoćje / ovlašćenje",                   "bodovi": 4},
    "T24": {"naziv": "Krivična prijava",                          "bodovi": 12},
    "T25": {"naziv": "Prisustvo uviđaju / veštačenju",            "bodovi": 10},
    "T26": {"naziv": "Zahtev za mirno rešenje spora",             "bodovi": 10},
    "T27": {"naziv": "Zastupanje u porodičnom sporu (ročište)",   "bodovi": 20},
    "T28": {"naziv": "Nasledno-pravna izjava / tužba",            "bodovi": 18},
    "T29": {"naziv": "Zastupanje u upravnom postupku",            "bodovi": 14},
    "T30": {"naziv": "Satnica — 1 sat (minimalna tarifa)",        "bodovi": None, "fiksno_rsd": 7500},
}


async def _db(fn):
    return await asyncio.to_thread(fn)


async def _resolve_tarifa_for_predmet(supa, uid: str, predmet_id: str) -> float:
    """Resolves satnica: per-klijent → globalna → 7500 (AKS default)."""
    from routers.tarife import resolve_tarifa
    kl_r = await _db(lambda: supa.table("predmet_klijenti")
                     .select("klijent_id")
                     .eq("predmet_id", predmet_id)
                     .limit(1)
                     .execute())
    klijent_id = kl_r.data[0]["klijent_id"] if kl_r.data else None
    return await resolve_tarifa(supa, uid, klijent_id)


# ── Pydantic modeli ────────────────────────────────────────────────────────────

class EntryReq(BaseModel):
    predmet_id:   str            = Field(..., min_length=1)
    opis:         str            = Field(..., min_length=1, max_length=400)
    tip:          str            = Field(default="tarifa")
    tarifa_sifra: Optional[str] = Field(default=None)
    bodovi:       Optional[float] = None
    sati:         Optional[float] = None
    iznos_rsd:    Optional[float] = Field(default=None, ge=0)
    datum:        Optional[str]  = Field(default=None)


class EntryPatchReq(BaseModel):
    opis:      Optional[str]   = Field(default=None, max_length=400)
    bodovi:    Optional[float] = None
    sati:      Optional[float] = None
    iznos_rsd: Optional[float] = Field(default=None, ge=0)
    datum:     Optional[str]  = Field(default=None)


class TimerStartReq(BaseModel):
    predmet_id: str            = Field(..., min_length=1)
    opis:       Optional[str] = Field(default=None, max_length=200)


class TimerStopReq(BaseModel):
    kreiraj_entry: bool        = Field(default=True)
    opis:          Optional[str] = Field(default=None, max_length=400)
    tip:           str         = Field(default="satnica")


class FakturaReq(BaseModel):
    predmet_id:     str            = Field(..., min_length=1)
    entry_ids:      List[str]      = Field(..., min_length=1)
    klijent_naziv:  str            = Field(..., min_length=1, max_length=300)
    klijent_adresa: Optional[str] = Field(default=None)
    klijent_pib:    Optional[str] = Field(default=None)
    pdv_stopa:      float          = Field(default=0.0, ge=0, le=100)
    napomena:       Optional[str] = Field(default=None, max_length=1000)


class FakturaStatusReq(BaseModel):
    status: str = Field(..., pattern="^(nacrt|izdata|placena|stornirana)$")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/entries")
@limiter.limit("60/minute")
async def billing_entry_create(
    body: EntryReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    iznos        = body.iznos_rsd
    tarifa_naziv = None
    bodovi       = body.bodovi

    if body.tarifa_sifra:
        kod = body.tarifa_sifra.upper()
        t   = AKS_TARIFA.get(kod)
        if not t:
            raise HTTPException(status_code=400, detail="Nepoznata tarifa sifra.")
        tarifa_naziv = t["naziv"]
        if iznos is None:
            custom_r = await _db(lambda: supa.table("tarifne_stavke_custom")
                                 .select("iznos,naziv")
                                 .eq("user_id", uid)
                                 .eq("kod", kod)
                                 .maybe_single()
                                 .execute())
            if custom_r.data:
                iznos        = float(custom_r.data["iznos"])
                tarifa_naziv = custom_r.data.get("naziv") or t["naziv"]
            else:
                iznos = t.get("fiksno_rsd") or ((body.bodovi or t.get("bodovi", 0)) * BOD_RSD)
        if bodovi is None:
            bodovi = t.get("bodovi")

    if iznos is None and body.sati:
        satnica = await _resolve_tarifa_for_predmet(supa, uid, body.predmet_id)
        iznos = max(satnica, math.ceil(body.sati * satnica))

    if iznos is None:
        raise HTTPException(status_code=422, detail="iznos_rsd je obavezan kad tarifa_sifra nije navedena.")

    row = {
        "user_id":      uid,
        "predmet_id":   body.predmet_id,
        "opis":         body.opis,
        "tip":          body.tip,
        "tarifa_sifra": body.tarifa_sifra.upper() if body.tarifa_sifra else None,
        "tarifa_naziv": tarifa_naziv,
        "bodovi":       bodovi,
        "sati":         body.sati,
        "iznos_rsd":    iznos,
        "datum":        body.datum or date.today().isoformat(),
        "obracunato":   False,
    }

    r = await _db(lambda: supa.table("billing_entries").insert(row).execute())
    if not r.data:
        raise HTTPException(status_code=500, detail="Unos radnje nije uspeo.")
    return {"success": True, "entry": r.data[0]}


@router.patch("/entries/{entry_id}")
@limiter.limit("60/minute")
async def billing_entry_update(
    entry_id: str,
    body: EntryPatchReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    ex = await _db(lambda: supa.table("billing_entries").select("obracunato").eq("id", entry_id).eq("user_id", uid).maybe_single().execute())
    if not ex.data:
        raise HTTPException(status_code=404, detail="Radnja nije pronađena.")
    if ex.data.get("obracunato"):
        raise HTTPException(status_code=409, detail="Radnja je već fakturisana — izmena nije moguća.")

    patch: dict = {k: v for k, v in {
        "opis":      body.opis,
        "bodovi":    body.bodovi,
        "sati":      body.sati,
        "iznos_rsd": body.iznos_rsd,
        "datum":     body.datum,
    }.items() if v is not None}

    if not patch:
        raise HTTPException(status_code=422, detail="Nema podataka za izmenu.")

    r = await _db(lambda: supa.table("billing_entries").update(patch).eq("id", entry_id).eq("user_id", uid).execute())
    return {"success": True, "entry": r.data[0] if r.data else {}}


@router.delete("/entries/{entry_id}")
@limiter.limit("60/minute")
async def billing_entry_delete(
    entry_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    ex = await _db(lambda: supa.table("billing_entries").select("obracunato").eq("id", entry_id).eq("user_id", uid).maybe_single().execute())
    if not ex.data:
        raise HTTPException(status_code=404, detail="Radnja nije pronađena.")
    if ex.data.get("obracunato"):
        raise HTTPException(status_code=409, detail="Radnja je fakturisana — brisanje nije moguće.")

    await _db(lambda: supa.table("billing_entries").delete().eq("id", entry_id).eq("user_id", uid).execute())
    return {"success": True}


@router.get("/entries")
@limiter.limit("60/minute")
async def billing_entries_list(
    request: Request,
    predmet_id: str,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    r = await _db(lambda: supa.table("billing_entries").select("*").eq("user_id", uid).eq("predmet_id", predmet_id).order("datum", desc=True).execute())
    entries = r.data or []

    ukupno       = sum(float(e.get("iznos_rsd") or 0) for e in entries)
    obracunato   = sum(float(e.get("iznos_rsd") or 0) for e in entries if e.get("obracunato"))
    neobracunato = ukupno - obracunato

    return {
        "entries":          entries,
        "ukupno_rsd":       ukupno,
        "obracunato_rsd":   obracunato,
        "neobracunato_rsd": neobracunato,
    }


@router.post("/timer/start")
@limiter.limit("30/minute")
async def timer_start(
    body: TimerStartReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    existing = await _db(lambda: supa.table("timer_sessions").select("id,predmet_id").eq("user_id", uid).eq("aktivan", True).limit(1).execute())
    if existing.data:
        raise HTTPException(status_code=409, detail="Tajmer je već aktivan. Zaustavite ga pre pokretanja novog.")

    r = await _db(lambda: supa.table("timer_sessions").insert({
        "user_id":    uid,
        "predmet_id": body.predmet_id,
        "opis":       body.opis,
        "aktivan":    True,
    }).execute())
    if not r.data:
        raise HTTPException(status_code=500, detail="Pokretanje tajmera nije uspelo.")
    return {"success": True, "timer": r.data[0]}


@router.post("/timer/stop")
@limiter.limit("30/minute")
async def timer_stop(
    body: TimerStopReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    existing = await _db(lambda: supa.table("timer_sessions").select("*").eq("user_id", uid).eq("aktivan", True).limit(1).execute())
    if not existing.data:
        raise HTTPException(status_code=404, detail="Nema aktivnog tajmera.")

    t        = existing.data[0]
    start_dt = datetime.fromisoformat(t["start_at"].replace("Z", "+00:00"))
    stop_dt  = datetime.now(timezone.utc)
    trajanje = int((stop_dt - start_dt).total_seconds())

    await _db(lambda: supa.table("timer_sessions").update({
        "aktivan":    False,
        "stop_at":    stop_dt.isoformat(),
        "trajanje_s": trajanje,
    }).eq("id", t["id"]).execute())

    entry = None
    if body.kreiraj_entry:
        sati    = round(trajanje / 3600, 2)
        satnica = await _resolve_tarifa_for_predmet(supa, uid, t["predmet_id"])
        iznos   = max(satnica, math.ceil(sati * satnica))
        opis    = (body.opis or t.get("opis") or "Rad po predmetu (tajmer)").strip()[:400]
        er = await _db(lambda: supa.table("billing_entries").insert({
            "user_id":    uid,
            "predmet_id": t["predmet_id"],
            "opis":       opis,
            "tip":        body.tip,
            "sati":       sati,
            "iznos_rsd":  iznos,
            "datum":      date.today().isoformat(),
            "obracunato": False,
        }).execute())
        entry = er.data[0] if er.data else None

    logger.info("[BILLING] timer stop uid=%.8s trajanje=%ds", uid, trajanje)
    return {"success": True, "trajanje_s": trajanje, "trajanje_h": round(trajanje / 3600, 2), "entry": entry}


@router.get("/timer/aktivan")
@limiter.limit("120/minute")
async def timer_aktivan(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    r = await _db(lambda: supa.table("timer_sessions").select("*").eq("user_id", uid).eq("aktivan", True).limit(1).execute())
    if not r.data:
        return {"aktivan": False, "timer": None}
    return {"aktivan": True, "timer": r.data[0]}


@router.get("/tarifa")
@limiter.limit("120/minute")
async def tarifa_list(
    request: Request,
    user: dict = Depends(get_current_user),
):
    from routers.tarife import resolve_tarifne_stavke
    supa     = _get_supa()
    resolved = await resolve_tarifne_stavke(supa, user["user_id"])
    items = [
        {
            "sifra":     kod,
            "naziv":     v["naziv"],
            "bodovi":    v["bodovi"],
            "iznos_rsd": v["iznos_rsd"],
            "is_custom": v["is_custom"],
            "aks_iznos": v["aks_iznos"],
        }
        for kod, v in resolved.items()
    ]
    return {"tarifa": items, "bod_rsd": BOD_RSD}


@router.get("/tarifa/{sifra}")
@limiter.limit("120/minute")
async def tarifa_get(
    sifra: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    t = AKS_TARIFA.get(sifra.upper())
    if not t:
        raise HTTPException(status_code=404, detail=f"Tarifa sifra '{sifra}' ne postoji.")
    iznos = t.get("fiksno_rsd") or (t["bodovi"] * BOD_RSD if t.get("bodovi") else 0)
    return {"sifra": sifra.upper(), "naziv": t["naziv"], "bodovi": t.get("bodovi"), "iznos_rsd": iznos, "bod_rsd": BOD_RSD}


@router.post("/faktura")
@limiter.limit("20/minute")
async def faktura_create(
    body: FakturaReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    entries_r = await _db(lambda: supa.table("billing_entries").select("*").eq("user_id", uid).in_("id", body.entry_ids).execute())
    entries   = entries_r.data or []
    if not entries:
        raise HTTPException(status_code=404, detail="Radnje nisu pronađene.")

    already_billed = [e["id"] for e in entries if e.get("obracunato")]
    if already_billed:
        raise HTTPException(status_code=409, detail=f"{len(already_billed)} radnja/e su već na drugoj fakturi.")

    iznos_bez_pdv = sum(float(e.get("iznos_rsd") or 0) for e in entries)
    pdv_iznos     = round(iznos_bez_pdv * body.pdv_stopa / 100, 2)
    iznos_sa_pdv  = iznos_bez_pdv + pdv_iznos

    try:
        broj_r       = await _db(lambda: supa.rpc("get_next_broj_fakture", {"p_user_id": uid}).execute())
        broj_fakture = str(broj_r.data) if broj_r.data else f"{date.today().year}-001"
    except Exception:
        broj_fakture = f"{date.today().year}-001"

    faktura_r = await _db(lambda: supa.table("fakture").insert({
        "user_id":        uid,
        "predmet_id":     body.predmet_id,
        "broj_fakture":   broj_fakture,
        "klijent_naziv":  body.klijent_naziv,
        "klijent_adresa": body.klijent_adresa,
        "klijent_pib":    body.klijent_pib,
        "iznos_bez_pdv":  iznos_bez_pdv,
        "pdv_iznos":      pdv_iznos,
        "iznos_sa_pdv":   iznos_sa_pdv,
        "napomena":       body.napomena,
        "status":         "nacrt",
    }).execute())
    if not faktura_r.data:
        raise HTTPException(status_code=500, detail="Kreiranje fakture nije uspelo.")

    faktura    = faktura_r.data[0]
    faktura_id = faktura["id"]

    await _db(lambda: supa.table("billing_entries").update({
        "faktura_id":  faktura_id,
        "obracunato":  True,
    }).in_("id", body.entry_ids).eq("user_id", uid).execute())

    logger.info("[BILLING] faktura=%s uid=%.8s iznos=%.2f", faktura_id, uid, iznos_sa_pdv)
    return {"success": True, "faktura": faktura, "stavke": len(entries)}


@router.get("/faktura/{faktura_id}/pdf")
@limiter.limit("20/minute")
async def faktura_pdf(
    faktura_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    f_r = await _db(lambda: supa.table("fakture").select("*").eq("id", faktura_id).eq("user_id", uid).maybe_single().execute())
    if not f_r.data:
        raise HTTPException(status_code=404, detail="Faktura nije pronađena.")
    f = f_r.data

    e_r = await _db(lambda: supa.table("billing_entries").select("*").eq("faktura_id", faktura_id).eq("user_id", uid).order("datum").execute())
    entries = e_r.data or []

    pdf_bytes = await asyncio.to_thread(_generate_pdf, f, entries)
    filename  = f"faktura_{f['broj_fakture'].replace('/', '-')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/faktura/{faktura_id}/status")
@limiter.limit("30/minute")
async def faktura_status_update(
    faktura_id: str,
    body: FakturaStatusReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    r = await _db(lambda: supa.table("fakture").update({"status": body.status}).eq("id", faktura_id).eq("user_id", uid).execute())
    if not r.data:
        raise HTTPException(status_code=404, detail="Faktura nije pronađena.")
    return {"success": True, "status": body.status}


@router.get("/pregled")
@limiter.limit("30/minute")
async def billing_pregled(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid   = user["user_id"]
    supa  = _get_supa()
    today = date.today()
    mes_start = date(today.year, today.month, 1).isoformat()

    entries_r, fakture_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries").select("iznos_rsd,obracunato").eq("user_id", uid).gte("datum", mes_start).execute()),
        _db(lambda: supa.table("fakture").select("iznos_sa_pdv,status").eq("user_id", uid).gte("datum_fakture", mes_start).execute()),
        return_exceptions=True,
    )

    entries = entries_r.data if not isinstance(entries_r, Exception) else []
    fakture = fakture_r.data if not isinstance(fakture_r, Exception) else []

    ukupno_unoseno = sum(float(e.get("iznos_rsd") or 0) for e in (entries or []))
    obracunato     = sum(float(e.get("iznos_rsd") or 0) for e in (entries or []) if e.get("obracunato"))
    neobracunato   = ukupno_unoseno - obracunato
    fakturisano    = sum(float(f.get("iznos_sa_pdv") or 0) for f in (fakture or []))
    naplaceno      = sum(float(f.get("iznos_sa_pdv") or 0) for f in (fakture or []) if f.get("status") == "placena")

    return {
        "mesec":           f"{today.year}-{today.month:02d}",
        "ukupno_unoseno":  ukupno_unoseno,
        "obracunato":      obracunato,
        "neobracunato":    neobracunato,
        "fakturisano":     fakturisano,
        "naplaceno":       naplaceno,
    }


# ── PRIORITET 4: Naplata proširene funkcije ───────────────────────────────────

@router.get("/dugovanja")
@limiter.limit("30/minute")
async def billing_dugovanja(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Sve nenaplaćene stavke grupisane po predmetu — evidencija dugovanja."""
    uid  = user["user_id"]
    supa = _get_supa()

    entries_r, predmeti_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("id,predmet_id,opis,iznos_rsd,datum,tip,tarifa_naziv")
            .eq("user_id", uid)
            .eq("obracunato", False)
            .order("datum")
            .execute()),
        _db(lambda: supa.table("predmeti")
            .select("id,naziv")
            .eq("user_id", uid)
            .execute()),
        return_exceptions=True,
    )

    entries  = entries_r.data if not isinstance(entries_r, Exception) else []
    predmeti = predmeti_r.data if not isinstance(predmeti_r, Exception) else []
    pred_map = {p["id"]: p.get("naziv", "—") for p in predmeti}

    by_predmet: dict[str, dict] = {}
    for e in (entries or []):
        pid = e.get("predmet_id", "")
        if pid not in by_predmet:
            by_predmet[pid] = {
                "predmet_id":    pid,
                "predmet_naziv": pred_map.get(pid, "—"),
                "stavke":        [],
                "ukupno_rsd":    0.0,
            }
        by_predmet[pid]["stavke"].append(e)
        by_predmet[pid]["ukupno_rsd"] += float(e.get("iznos_rsd") or 0)

    dugovanja = sorted(by_predmet.values(), key=lambda x: x["ukupno_rsd"], reverse=True)
    ukupno_rsd = sum(g["ukupno_rsd"] for g in dugovanja)

    return {
        "dugovanja":   dugovanja,
        "ukupno_rsd":  ukupno_rsd,
        "predmeta":    len(dugovanja),
        "stavki":      len(entries or []),
    }


@router.get("/naplata-status")
@limiter.limit("30/minute")
async def billing_naplata_status(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Celokupni finansijski status — ukupno, fakturisano, naplaćeno, neizmireno."""
    uid  = user["user_id"]
    supa = _get_supa()

    entries_r, fakture_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("iznos_rsd,obracunato")
            .eq("user_id", uid)
            .execute()),
        _db(lambda: supa.table("fakture")
            .select("iznos_sa_pdv,iznos_bez_pdv,status,datum_fakture,broj_fakture")
            .eq("user_id", uid)
            .order("datum_fakture", desc=True)
            .execute()),
        return_exceptions=True,
    )

    entries = entries_r.data if not isinstance(entries_r, Exception) else []
    fakture = fakture_r.data if not isinstance(fakture_r, Exception) else []

    ukupno_stavke  = sum(float(e.get("iznos_rsd") or 0) for e in (entries or []))
    neobracunato   = sum(float(e.get("iznos_rsd") or 0) for e in (entries or []) if not e.get("obracunato"))
    fakturisano    = sum(float(f.get("iznos_sa_pdv") or 0) for f in (fakture or []))
    naplaceno      = sum(float(f.get("iznos_sa_pdv") or 0) for f in (fakture or []) if f.get("status") == "placena")
    neizmireno     = sum(float(f.get("iznos_sa_pdv") or 0) for f in (fakture or []) if f.get("status") == "izdata")
    nacrt_iznos    = sum(float(f.get("iznos_sa_pdv") or 0) for f in (fakture or []) if f.get("status") == "nacrt")

    return {
        "ukupno_stavke":  ukupno_stavke,
        "neobracunato":   neobracunato,
        "fakturisano":    fakturisano,
        "naplaceno":      naplaceno,
        "neizmireno":     neizmireno,
        "nacrt_iznos":    nacrt_iznos,
        "fakture_ukupno": len(fakture or []),
        "fakture_placene": sum(1 for f in (fakture or []) if f.get("status") == "placena"),
        "fakture_izdate":  sum(1 for f in (fakture or []) if f.get("status") == "izdata"),
    }


@router.get("/po-klijentu/{klijent_id}")
@limiter.limit("30/minute")
async def billing_po_klijentu(
    klijent_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Billing stavke i fakture za sve predmete jednog klijenta."""
    uid  = user["user_id"]
    supa = _get_supa()

    pk_r = await _db(lambda: supa.table("predmet_klijenti")
                     .select("predmet_id")
                     .eq("klijent_id", klijent_id)
                     .execute())
    pred_ids = [r["predmet_id"] for r in (pk_r.data or [])]
    if not pred_ids:
        return {"klijent_id": klijent_id, "predmeti": [], "stavke": [], "fakture": [],
                "ukupno_rsd": 0.0, "naplaceno": 0.0, "neizmireno": 0.0}

    entries_r, fakture_r, predmeti_r = await asyncio.gather(
        _db(lambda: supa.table("billing_entries")
            .select("*")
            .eq("user_id", uid)
            .in_("predmet_id", pred_ids)
            .order("datum", desc=True)
            .execute()),
        _db(lambda: supa.table("fakture")
            .select("*")
            .eq("user_id", uid)
            .in_("predmet_id", pred_ids)
            .order("datum_fakture", desc=True)
            .execute()),
        _db(lambda: supa.table("predmeti")
            .select("id,naziv,status")
            .in_("id", pred_ids)
            .execute()),
        return_exceptions=True,
    )

    entries  = entries_r.data if not isinstance(entries_r, Exception) else []
    fakture  = fakture_r.data if not isinstance(fakture_r, Exception) else []
    predmeti = predmeti_r.data if not isinstance(predmeti_r, Exception) else []

    ukupno_rsd = sum(float(e.get("iznos_rsd") or 0) for e in (entries or []))
    naplaceno  = sum(float(f.get("iznos_sa_pdv") or 0) for f in (fakture or []) if f.get("status") == "placena")

    return {
        "klijent_id":  klijent_id,
        "predmeti":    predmeti or [],
        "stavke":      entries or [],
        "fakture":     fakture or [],
        "ukupno_rsd":  ukupno_rsd,
        "naplaceno":   naplaceno,
        "neizmireno":  sum(float(f.get("iznos_sa_pdv") or 0) for f in (fakture or []) if f.get("status") == "izdata"),
    }


# ── PDF generator ─────────────────────────────────────────────────────────────

def _generate_pdf(faktura: dict, entries: list) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf    = io.BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=A4,
                               rightMargin=2*cm, leftMargin=2*cm,
                               topMargin=2.5*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    title_s = ParagraphStyle("t", parent=styles["Heading1"], fontSize=18, spaceAfter=4)
    sub_s   = ParagraphStyle("s", parent=styles["Normal"],   fontSize=9,  textColor=colors.grey)
    bold_s  = ParagraphStyle("b", parent=styles["Normal"],   fontSize=10, fontName="Helvetica-Bold")

    story.append(Paragraph(f"FAKTURA br. {faktura['broj_fakture']}", title_s))
    story.append(Paragraph(f"Datum: {faktura['datum_fakture']}", sub_s))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("Primalac:", bold_s))
    story.append(Paragraph(faktura.get("klijent_naziv", ""), styles["Normal"]))
    if faktura.get("klijent_adresa"):
        story.append(Paragraph(faktura["klijent_adresa"], styles["Normal"]))
    if faktura.get("klijent_pib"):
        story.append(Paragraph(f"PIB: {faktura['klijent_pib']}", styles["Normal"]))
    story.append(Spacer(1, 0.7*cm))

    header = [["R.br.", "Opis usluge", "Datum", "Iznos (RSD)"]]
    rows   = [[
        str(i),
        e.get("opis", ""),
        str(e.get("datum", "")),
        f"{float(e.get('iznos_rsd') or 0):,.2f}",
    ] for i, e in enumerate(entries, 1)]

    t = Table(header + rows, colWidths=[1.2*cm, 10*cm, 2.8*cm, 3*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR",      (0, 0), (-1, 0), colors.white),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1,-1), 9),
        ("ALIGN",          (3, 0), (3, -1), "RIGHT"),
        ("ALIGN",          (0, 0), (0, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1,-1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID",           (0, 0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
        ("BOTTOMPADDING",  (0, 0), (-1,-1), 5),
        ("TOPPADDING",     (0, 0), (-1,-1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    totals = [
        ["", "", "Bez PDV:", f"{float(faktura.get('iznos_bez_pdv') or 0):,.2f} RSD"],
        ["", "", "PDV:",     f"{float(faktura.get('pdv_iznos') or 0):,.2f} RSD"],
        ["", "", "UKUPNO:",  f"{float(faktura.get('iznos_sa_pdv') or 0):,.2f} RSD"],
    ]
    tt = Table(totals, colWidths=[1.2*cm, 10*cm, 2.8*cm, 3*cm])
    tt.setStyle(TableStyle([
        ("ALIGN",    (2, 0), (-1,-1), "RIGHT"),
        ("FONTNAME", (2, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1,-1), 9),
        ("LINEABOVE",(2, 2), (-1, 2), 1, colors.black),
    ]))
    story.append(tt)

    if faktura.get("napomena"):
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(f"Napomena: {faktura['napomena']}", sub_s))

    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("Generisano putem Vindex AI — vindex.ai", sub_s))

    doc.build(story)
    return buf.getvalue()
