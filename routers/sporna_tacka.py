# -*- coding: utf-8 -*-
"""
Vindex AI — routers/sporna_tacka.py

S02 / B7 — ODLUKA ADVOKATA O AI PROTIVREČNOSTI (odluka osnivača A, 2026-10-31).

  POST /api/predmeti/{predmet_id}/sporne-tacke/{issue_id}/potvrdi   — → CONFIRMED
  POST /api/predmeti/{predmet_id}/sporne-tacke/{issue_id}/odbij     — → RESOLVED (close_reason WITHDRAWN)
  telo: {"ocekivano": {"status": "...", "odluka_at": "...", "sadrzaj": "..."}} — stanje i verzija sadržaja koje je
  advokat VIDEO (obavezno; `genome-v2` → `odluka`)

Protivrečnost koju je pronašla analiza je KANDIDAT. Aktivna je i nosi akciju „Razrešiti kontradikciju“ tek kad je
advokat potvrdi; odbijena izlazi iz aktivnih tokova i ostaje u istoriji. Koriste se postojeća stanja sporne tačke
(`predmet_issues.status`, migracija 119 — `shared/issue_v2.py`: DISCOVERED „provizorna“, CONFIRMED „advokat potvrdio —
tek tada sme nositi akcije“, `close_reason = WITHDRAWN`). Bez migracije, bez nove tabele.

Odluka važi za sadržaj koji je postojao kad je doneta (`updated_at` sporne tačke piše samo ova ruta;
`shared/issue_v2.efektivna_odluka`): kontradikcija ili tvrdnja nastala posle odluke traži novu odluku. Odluka se može
promeniti (potvrđena → odbijena i obrnuto) — svaka promena je nov audit zapis sa prethodnim stanjem.

## Šta ova ruta NIKAD ne radi
  * ne menja `predmet_contradictions` ni članove — odluka je zapis o spornoj tački, ne prepravka opažanja;
  * ne odlučuje grupno; ne potvrđuje automatski;
  * ne čita tuđe: `predmeti.user_id` i `predmet_issues.user_id` su brana (service_role zaobilazi RLS).

Upis je USLOVAN (`status` i `updated_at` = viđeni): istovremeni ili zastareli zahtev → jedan prolazi, drugi 409.
Audit je obavezan: ako zapis odluke ne uspe, stanje se vraća (uslovno) i odgovor je 503 — odluka bez istorije ne
ostaje. Posle odluke trajni događaj usklađuje akcije predmeta (isti put kao odluka o roku).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.sporna_tacka")
router = APIRouter(tags=["sporne-tacke"])

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_ODLUKE = {
    "potvrdi": {"status": "CONFIRMED", "close_reason": None, "audit": "sporna_tacka_potvrdjena",
                "dogadjaj": "potvrda_sporne_tacke", "vazi": "POTVRDJENA"},
    "odbij": {"status": "RESOLVED", "close_reason": "WITHDRAWN", "audit": "sporna_tacka_odbijena",
              "dogadjaj": "odbijanje_sporne_tacke", "vazi": "ODBIJENA"},
}
_ODLUCIVO = ("DISCOVERED", "REOPENED", "CONFIRMED", "RESOLVED")


class Vidjeno(BaseModel):
    status: Optional[str] = None
    odluka_at: Optional[str] = None
    sadrzaj: Optional[str] = None      # `shared/issue_v2.verzija_sadrzaja` sadržaja koji je advokat video


class OdlukaReq(BaseModel):
    ocekivano: Optional[Vidjeno] = None


def _sporna_tacka(supa, predmet_id: str, issue_id: str, uid: str) -> dict:
    if not (_UUID.match(predmet_id or "") and _UUID.match(issue_id or "")):
        raise HTTPException(status_code=404, detail="Sporna tačka nije pronađena.")
    pr = supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).limit(1).execute()
    if not (pr.data or []):
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")
    r = (supa.table("predmet_issues").select("id,predmet_id,status,close_reason,closed_at,label,updated_at")
         .eq("id", issue_id).eq("predmet_id", predmet_id).eq("user_id", uid).limit(1).execute())
    if not (r.data or []):
        raise HTTPException(status_code=404, detail="Sporna tačka nije pronađena.")
    return r.data[0]


def _stanje_sadrzaja(supa, red: dict, uid: str) -> tuple[str, str, dict]:
    """(efektivna odluka sporne tačke kao celine, verzija sadržaja, obuhvat sadržaja). POTVRDJENA/ODBIJENA samo ako je
    SVE što je sada otvoreno ili za pregled (kontradikcije i aktivni članovi) bilo u obuhvatu poslednje odluke i postoji od
    pre nje (`shared/issue_v2.efektivna_odluka`). Pad čitanja ide pozivaocu."""
    from shared.issue_v2 import (ODLUKA_CEKA, STATUS_POTVRDJENA, STATUS_RAZRESENA, efektivna_odluka, obuhvat_sadrzaja,
                                 procitaj_obuhvat_odluka, verzija_sadrzaja)
    ob = (procitaj_obuhvat_odluka(supa, [red["id"]], uid).get(str(red["id"]))
          if red.get("status") in (STATUS_POTVRDJENA, STATUS_RAZRESENA) else None)
    kon = (supa.table("predmet_contradictions").select("id,relation_type,created_at,state").eq("issue_id", red["id"])
           .in_("state", ["OPEN", "REVIEW_REQUIRED"]).execute()).data or []
    if not kon:
        return (efektivna_odluka({"issue_status": red.get("status"), "issue_odluka_at": red.get("updated_at"), "odluka_obuhvat": ob}),
                verzija_sadrzaja([]), {})
    cl = (supa.table("predmet_contradiction_claims").select("contradiction_id,dokaz_id,observed_at,removed_at")
          .in_("contradiction_id", [k["id"] for k in kon]).execute()).data or []
    aktivni = [c for c in cl if c.get("removed_at") is None]
    stavke = [{"id": k["id"], "relation_type": k.get("relation_type"), "issue_status": red.get("status"),
               "issue_odluka_at": red.get("updated_at"), "odluka_obuhvat": ob, "created_at": k.get("created_at"),
               "clanovi_od": [c.get("observed_at") for c in aktivni if c["contradiction_id"] == k["id"]],
               "claim_ids": [c["dokaz_id"] for c in aktivni if c["contradiction_id"] == k["id"]]} for k in kon]
    ishodi = {efektivna_odluka(s) for s in stavke}
    return (ishodi.pop() if len(ishodi) == 1 else ODLUKA_CEKA), verzija_sadrzaja(stavke), obuhvat_sadrzaja(stavke)


_PROMENJENO = "Sadržaj ili stanje ove sporne tačke se promenilo od kada ste je otvorili — osvežite prikaz. Ništa nije zabeleženo."


async def _odluci(predmet_id: str, issue_id: str, odluka: str, uid: str, ip, vidjeno: Optional[Vidjeno]) -> dict:
    cilj = _ODLUKE[odluka]
    supa = _get_supa()
    red = await asyncio.to_thread(_sporna_tacka, supa, predmet_id, issue_id, uid)
    staro, staro_at = red.get("status"), red.get("updated_at")
    if vidjeno is not None and (vidjeno.status != staro or (vidjeno.odluka_at or None) != (staro_at or None)):
        raise HTTPException(status_code=409, detail=_PROMENJENO)
    if staro not in _ODLUCIVO:
        raise HTTPException(status_code=409, detail="O ovoj spornoj tački se ne može odlučiti (spojena je). Ništa nije zabeleženo.")
    try:
        vazi, sadrzaj, obuhvat = await asyncio.to_thread(_stanje_sadrzaja, supa, red, uid)
    except Exception as exc:
        logger.error("[SPORNA_TACKA] stanje sporne tačke nije pročitano issue=%s: %s", issue_id, exc)
        raise HTTPException(status_code=503, detail="Stanje sporne tačke trenutno nije moguće proveriti. Ništa nije zabeleženo.")
    # Odluka se odnosi na sadržaj koji je advokat VIDEO — bez verzije tog sadržaja (stari prozor, API poziv bez nje)
    # nema dokaza šta je video, pa se ne beleži.
    if vidjeno is None or not vidjeno.sadrzaj or vidjeno.sadrzaj != sadrzaj:
        raise HTTPException(status_code=409, detail=_PROMENJENO)
    if vazi == cilj["vazi"]:
        return {"ok": True, "issue_id": issue_id, "status": staro, "promenjeno": False}

    # Vreme odluke je vreme BAZE ('now' = početak transakcije upisa) — isti sat kao `created_at`/`observed_at` sadržaja.
    izmena = {"status": cilj["status"], "close_reason": cilj["close_reason"],
              "closed_at": "now" if cilj["close_reason"] else None, "updated_at": "now"}

    def _upisi():
        q = (supa.table("predmet_issues").update(izmena).eq("id", issue_id).eq("predmet_id", predmet_id)
             .eq("user_id", uid).eq("status", staro))
        return (q.eq("updated_at", staro_at) if staro_at else q.is_("updated_at", "null")).execute()
    try:
        upisano = (await asyncio.to_thread(_upisi)).data or []
    except Exception as exc:
        logger.error("[SPORNA_TACKA] upis odluke nije uspeo issue=%s: %s", issue_id, exc)
        raise HTTPException(status_code=503, detail="Odluka trenutno nije sačuvana. Pokušajte ponovo.")
    if not upisano:
        raise HTTPException(status_code=409, detail=_PROMENJENO)
    upisano_at = upisano[0].get("updated_at")      # vrednost kakvu je baza sačuvala (uslov za vraćanje)

    async def _vrati(razlog: str) -> bool:
        """Uslovno vraća prethodno stanje (i `closed_at`). True samo ako je red stvarno vraćen. Ako nije, odluka je možda
        ostala bez audit zapisa — tada `efektivna_odluka` ionako ne priznaje odluku bez obuhvata iz audita (čeka)."""
        vrati = {"status": staro, "close_reason": red.get("close_reason"), "closed_at": red.get("closed_at"),
                 "updated_at": staro_at}
        try:
            r = await asyncio.to_thread(lambda: supa.table("predmet_issues").update(vrati).eq("id", issue_id)
                                        .eq("user_id", uid).eq("status", cilj["status"]).eq("updated_at", upisano_at).execute())
            if r.data:
                return True
            logger.critical("[SPORNA_TACKA] vraćanje (%s) nije pogodilo red issue=%s", razlog, issue_id)
        except Exception as exc:
            logger.critical("[SPORNA_TACKA] vraćanje (%s) nije uspelo issue=%s: %s — odluka bez potvrde sadržaja ili "
                            "audit zapisa", razlog, issue_id, exc)
        return False

    _NEIZVESNO = ("Odluka možda jeste upisana, ali bez zapisa odluke — zato se NE primenjuje (protivrečnost čeka odluku). "
                  "Osvežite prikaz i odlučite ponovo.")

    # Opažanje drži zaključan red sporne tačke dok upisuje (migracija 122), pa je upis odluke čekao njegov kraj. Sadržaj
    # se zato proverava i POSLE upisa: ako je u međuvremenu dodata tvrdnja ili relacija, odluka se vraća — advokat nije
    # video ono na šta bi se odnosila.
    try:
        _, sadrzaj_posle, _ = await asyncio.to_thread(_stanje_sadrzaja, supa, {**red, "status": cilj["status"], "updated_at": upisano_at}, uid)
    except Exception as exc:
        logger.error("[SPORNA_TACKA] sadržaj posle upisa nije pročitan issue=%s: %s", issue_id, exc)
        sadrzaj_posle = None
    if sadrzaj_posle != vidjeno.sadrzaj:
        if not await _vrati("sadržaj promenjen tokom odluke"):
            raise HTTPException(status_code=503, detail=_NEIZVESNO)
        raise HTTPException(status_code=409, detail=_PROMENJENO)

    from shared.audit_immutable import log_action
    zapis = await log_action(cilj["audit"], user_id=uid, resource_type="predmet_issue", resource_id=issue_id, ip=ip,
                             metadata={"predmet_id": predmet_id, "prethodni_status": staro, "prethodna_odluka_at": staro_at,
                                       "prethodno_vazi": vazi, "novi_status": cilj["status"], "sadrzaj": sadrzaj,
                                       "obuhvat": obuhvat,
                                       "close_reason": cilj["close_reason"], "label": red.get("label")})
    if not zapis:
        if not await _vrati("audit nije upisan"):
            raise HTTPException(status_code=503, detail=_NEIZVESNO)
        raise HTTPException(status_code=503, detail="Odluka nije sačuvana jer zapis odluke nije uspeo. Pokušajte ponovo.")

    try:
        from services.event_bus import EventType, emit_durable
        await emit_durable(EventType.MANUAL_CORRECTION_APPLIED, uid, predmet_id,
                           {"issue_id": issue_id, "odluka": cilj["dogadjaj"], "trigger": "sporna_tacka_odluka"})
    except Exception as exc:   # odluka je sačuvana; akcije se usklađuju na sledećem događaju predmeta
        logger.warning("[SPORNA_TACKA] događaj posle odluke nije upisan issue=%s: %s", issue_id, exc)
    return {"ok": True, "issue_id": issue_id, "status": cilj["status"], "promenjeno": True}


def _ip(request: Request):
    return request.client.host if request.client else None


@router.post("/api/predmeti/{predmet_id}/sporne-tacke/{issue_id}/potvrdi")
@limiter.limit("60/minute")
async def potvrdi(predmet_id: str, issue_id: str, request: Request, body: OdlukaReq = OdlukaReq(),
                  user: dict = Depends(get_current_user)):
    """Advokat potvrđuje da je protivrečnost stvarna — tek tada je aktivna i nosi akciju."""
    return await _odluci(predmet_id, issue_id, "potvrdi", user["user_id"], _ip(request), body.ocekivano)


@router.post("/api/predmeti/{predmet_id}/sporne-tacke/{issue_id}/odbij")
@limiter.limit("60/minute")
async def odbij(predmet_id: str, issue_id: str, request: Request, body: OdlukaReq = OdlukaReq(),
                user: dict = Depends(get_current_user)):
    """Advokat odbacuje protivrečnost — izlazi iz aktivnih tokova, ostaje u istoriji (`RESOLVED`, `WITHDRAWN`)."""
    return await _odluci(predmet_id, issue_id, "odbij", user["user_id"], _ip(request), body.ocekivano)
