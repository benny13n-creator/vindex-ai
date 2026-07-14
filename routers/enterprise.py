# -*- coding: utf-8 -*-
"""
Vindex AI — routers/enterprise.py

Enterprise funkcionalnosti: upravljanje timom, firma-nivo statistike,
delegiranje predmeta, role-based access control.

NAPOMENA (Faza 72 čišćenje): ovaj fajl je izvorno pisan protiv tabele
"firma_clanovi"/"firma_pozivnice" — ispostavilo se pri auditu da te tabele
DO POSTOJE u bazi (verovatno kreirane direktno u Supabase Dashboard-u, van
migrations/ foldera), ali su prazne i nikad korišćene — routers/kancelarija.py
je od početka bio STVARNI, aktivni tim-management sistem (kancelarije/
kancelarija_clanovi, već ima svoj UI u Podešavanja -> Kancelarija). Prva 4
endpointa iz ovog fajla (tim/pozovi, tim/clanovi, tim/{user_id} DELETE,
tim/uloge) su bila mrtav kod bez ijednog frontend poziva, formalno obeležena
[SUPERSEDED] u prethodnoj sesiji — obrisana u potpunosti umesto da se drže
kao upozorenje, pošto /api/kancelarija/pozovi, /uloga/{clan_id},
/ukloni/{clan_id} u potpunosti pokrivaju tu funkcionalnost.

  - statistike i kapacitet čitaju iz kancelarije/kancelarija_clanovi
    (_get_firma_id / _get_firma_clan_ids) jer nemaju ekvivalent nigde
    drugde -- prihod/fakture agregacija i pregled zauzetosti tima.
  - predmet/delegiraj i predmet/delegiranja rade nezavisno od gornjeg
    (samo predmet_delegiranja tabela, migrirana u 054) -- delegiranje
    predmeta konkretnom advokatu u firmi nema ekvivalent nigde.

Endpoints:
  GET    /api/enterprise/statistike        — firma-nivo dashboard
  POST   /api/enterprise/predmet/delegiraj — delegiraj predmet advokatu
  GET    /api/enterprise/kapacitet         — pregled zauzetosti advokata
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.enterprise")
router = APIRouter(tags=["enterprise"])


async def _get_firma_id(supa, user_id: str) -> str:
    """Vrati kancelarija_id za korisnika (kao admin ili aktivan clan) ili podigne 404.

    NAPOMENA: ovaj fajl je originalno pisan protiv tabele "firma_clanovi" koja
    nikad nije migrirana -- stvarni, aktivni tim-management sistem
    (routers/kancelarija.py) koristi "kancelarije"/"kancelarija_clanovi".
    Ispravljeno da cita iz stvarnih tabela umesto da uvek baca 404.
    """
    admin_r = await asyncio.to_thread(
        lambda: supa.table("kancelarije")
            .select("id")
            .eq("admin_uid", user_id)
            .maybe_single()
            .execute()
    )
    if admin_r.data:
        return admin_r.data["id"]

    member_r = await asyncio.to_thread(
        lambda: supa.table("kancelarija_clanovi")
            .select("kancelarija_id")
            .eq("user_id", user_id)
            .eq("status", "ACTIVE")
            .maybe_single()
            .execute()
    )
    if not member_r.data:
        raise HTTPException(status_code=404, detail="Niste clan nijedne firme.")
    return member_r.data["kancelarija_id"]


async def _get_firma_clan_ids(supa, kancelarija_id: str, admin_uid: str) -> list[dict]:
    """Vrati sve aktivne clanove firme (uloga + user_id), ukljucujuci admina.

    admin_uid nema svoj red u kancelarija_clanovi (vidi routers/kancelarija.py
    firma_predmeti) -- eksplicitno ga dodajemo na pocetak liste.
    """
    r = await asyncio.to_thread(
        lambda: supa.table("kancelarija_clanovi")
            .select("user_id, uloga")
            .eq("kancelarija_id", kancelarija_id)
            .eq("status", "ACTIVE")
            .execute()
    )
    clanovi = list(r.data or [])
    if not any(c.get("user_id") == admin_uid for c in clanovi):
        clanovi.insert(0, {"user_id": admin_uid, "uloga": "admin"})
    return clanovi


# ── Request modeli ─────────────────────────────────────────────────────────────

class DelegiranjeRequest(BaseModel):
    predmet_id: str
    advokat_user_id: str
    napomena: Optional[str] = None


# ── Statistike i kapacitet ─────────────────────────────────────────────────────

@router.get("/api/enterprise/statistike")
async def firma_statistike(user: dict = Depends(get_current_user)):
    """Firma-nivo dashboard statistike."""
    uid = user["user_id"]
    supa = _get_supa()

    firma_id = await _get_firma_id(supa, uid)

    clanovi = await _get_firma_clan_ids(supa, firma_id, uid)
    clan_ids = [c["user_id"] for c in clanovi]

    if not clan_ids:
        return {"firma_id": firma_id, "clanovi_count": 0}

    predmeti_r, klijenti_r, fakture_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("user_id, status", count="exact")
                .in_("user_id", clan_ids)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("klijenti")
                .select("user_id", count="exact")
                .in_("user_id", clan_ids)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("fakture")
                .select("user_id, iznos_sa_pdv, status")
                .in_("user_id", clan_ids)
                .execute()
        ),
    )

    fakture = fakture_r.data or []
    ukupan_prihod  = sum(float(f.get("iznos_sa_pdv") or 0) for f in fakture)
    placene_fakture = sum(1 for f in fakture if f.get("status") == "placena")

    # Broj predmeta po statusu
    predmeti = predmeti_r.data or []
    predmeti_po_statusu: dict[str, int] = {}
    for p in predmeti:
        s = p.get("status") or "nepoznat"
        predmeti_po_statusu[s] = predmeti_po_statusu.get(s, 0) + 1

    return {
        "firma_id":            firma_id,
        "clanovi_count":       len(clan_ids),
        "predmeti_ukupno":     predmeti_r.count or len(predmeti),
        "predmeti_po_statusu": predmeti_po_statusu,
        "klijenti_ukupno":     klijenti_r.count or 0,
        "fakture_prihod":      round(ukupan_prihod, 2),
        "fakture_placene":     placene_fakture,
        "fakture_ukupno":      len(fakture),
    }


@router.get("/api/enterprise/kapacitet")
async def firma_kapacitet(user: dict = Depends(get_current_user)):
    """Pregled zauzetosti advokata u firmi — broj aktivnih predmeta po advokatu."""
    uid = user["user_id"]
    supa = _get_supa()

    firma_id = await _get_firma_id(supa, uid)

    clanovi = await _get_firma_clan_ids(supa, firma_id, uid)

    if not clanovi:
        return {"kapacitet": []}

    # Dohvati aktivne predmete za sve clanove odjednom
    clan_ids = [c["user_id"] for c in clanovi]
    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("user_id, status")
            .in_("user_id", clan_ids)
            .eq("status", "aktivan")
            .execute()
    )

    # Grupisanje po user_id
    pred_count: dict[str, int] = {}
    for p in (pred_r.data or []):
        uid_p = p["user_id"]
        pred_count[uid_p] = pred_count.get(uid_p, 0) + 1

    kapacitet = [
        {
            "user_id":          c["user_id"],
            "uloga":            c["uloga"],
            "aktivnih_predmeta": pred_count.get(c["user_id"], 0),
        }
        for c in clanovi
    ]
    kapacitet.sort(key=lambda x: x["aktivnih_predmeta"], reverse=True)

    return {"kapacitet": kapacitet, "firma_id": firma_id}


# ── Delegiranje predmeta ───────────────────────────────────────────────────────

@router.post("/api/enterprise/predmet/delegiraj")
async def delegiraj_predmet(
    payload: DelegiranjeRequest,
    user: dict = Depends(get_current_user),
):
    """Delegiraj predmet drugom advokatu u firmi."""
    uid = user["user_id"]
    supa = _get_supa()

    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("naziv, user_id")
            .eq("id", payload.predmet_id)
            .eq("user_id", uid)
            .maybe_single()
            .execute()
    )
    if not pred_r.data:
        raise HTTPException(
            status_code=404,
            detail="Predmet nije pronadjen ili nemate pravo delegiranja.",
        )

    await asyncio.to_thread(
        lambda: supa.table("predmet_delegiranja").insert({
            "predmet_id":      payload.predmet_id,
            "od_user_id":      uid,
            "na_user_id":      payload.advokat_user_id,
            "napomena":        payload.napomena,
            "status":          "aktivno",
        }).execute()
    )

    logger.info("Predmet %s delegiran sa %s na %s", payload.predmet_id, uid, payload.advokat_user_id)
    return {"ok": True, "predmet_id": payload.predmet_id}


@router.get("/api/enterprise/predmet/delegiranja")
async def get_delegiranja(user: dict = Depends(get_current_user)):
    """Lista predmeta delegiranih od/ka korisniku."""
    uid = user["user_id"]
    supa = _get_supa()

    od_r, ka_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmet_delegiranja")
                .select("*")
                .eq("od_user_id", uid)
                .order("created_at", desc=True)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_delegiranja")
                .select("*")
                .eq("na_user_id", uid)
                .order("created_at", desc=True)
                .execute()
        ),
    )

    return {
        "delegirano_od_mene": od_r.data or [],
        "delegirano_ka_meni": ka_r.data or [],
    }
