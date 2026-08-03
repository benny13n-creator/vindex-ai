# -*- coding: utf-8 -*-
"""
Case Command Center — jedan API poziv koji agregira sve podatke predmeta.

GET /api/ccc/predmeti/{predmet_id}
Vraća: predmet, matter_intel, dokazi, rokovi, billing, aktivnosti, sudska_praksa
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user
from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS
from services.risk_engine import calculate_procesni_rizik

logger = logging.getLogger("vindex.ccc")
router = APIRouter(prefix="/api/ccc", tags=["ccc"])


@router.get("/predmeti/{predmet_id}")
async def get_ccc(predmet_id: str, user=Depends(get_current_user)):
    supa = _get_supa()
    uid  = user["user_id"]

    # ── Ownership check ─────────────────────────────────────────────────────
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select(
            "id,naziv,tip,status,oblast,tuzilac,tuzeni,rizik,vrednost_spora,opis,created_at"
        ).eq("id", predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404)
    predmet = pr.data[0]

    # ── Svih 6 upita paralelno ───────────────────────────────────────────────
    (
        dokazi_r,
        dok_count_r,
        rok_r,
        be_r,
        hron_r,
        kl_r,
    ) = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_dokazi").select(
            "snaga,kategorija"
        ).eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("id,naziv_fajla,status,tip_dokaza").eq(
            "predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("rocista").select(
            "id,sud,datum,status,napomena"
        ).eq("predmet_id", predmet_id).order("datum").limit(10).execute()),
        asyncio.to_thread(lambda: supa.table("billing_entries").select(
            "iznos,obracunato"
        ).eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select(
            "dogadjaj,akter,datum,vaznost"
        ).eq("predmet_id", predmet_id).order("datum_iso", desc=True).limit(8).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti").select(
            "uloga,klijenti(ime,prezime,firma)"
        ).eq("predmet_id", predmet_id).limit(4).execute()),
        return_exceptions=True,
    )

    # ── Dokazi statistika ────────────────────────────────────────────────────
    dokazi = (dokazi_r.data if not isinstance(dokazi_r, Exception) else []) or []
    dok_stats = {"jaka": 0, "srednja": 0, "slaba": 0, "ukupno": len(dokazi)}
    for d in dokazi:
        s = d.get("snaga", "srednja")
        if s in dok_stats:
            dok_stats[s] += 1

    # ── Dokumenti broji ─────────────────────────────────────────────────────
    tip_stat: dict = {}
    for d in ((dok_count_r.data if not isinstance(dok_count_r, Exception) else []) or []):
        t = d.get("tip_dokaza") or "neklasifikovan"
        tip_stat[t] = tip_stat.get(t, 0) + 1

    # ── Rokovi (sledeći 30 dana) ─────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    rokovi_data = []
    predstojeći = 0
    for r in ((rok_r.data if not isinstance(rok_r, Exception) else []) or []):
        dana = None
        try:
            dt_str = r.get("datum", "")
            if dt_str:
                dt = datetime.fromisoformat((dt_str + "T00:00:00") if len(dt_str) == 10 else dt_str.replace("Z", "+00:00"))
                dana = (dt - now).days
                if 0 <= dana <= 30:
                    predstojeći += 1
        except Exception:
            pass
        rokovi_data.append({**r, "dana_ostalo": dana})

    # ── Billing summary ──────────────────────────────────────────────────────
    billing_data = {"uneseno": 0, "nenaplaceno": 0, "naplaceno": 0}
    try:
        for e in ((be_r.data if not isinstance(be_r, Exception) else []) or []):
            iznos = float(e.get("iznos") or 0)
            billing_data["uneseno"] += iznos
            if e.get("obracunato"):
                billing_data["naplaceno"] += iznos
            else:
                billing_data["nenaplaceno"] += iznos
    except Exception as exc:
        logger.debug("[CCC] billing greška: %s", exc)

    # ── Klijenti ─────────────────────────────────────────────────────────────
    klijenti = []
    try:
        for k in ((kl_r.data if not isinstance(kl_r, Exception) else []) or []):
            ki = k.get("klijenti") or {}
            klijenti.append({
                "uloga": k.get("uloga", ""),
                "ime": ((ki.get("ime","") + " " + ki.get("prezime","")).strip()
                        or ki.get("firma","Klijent"))
            })
    except Exception as exc:
        logger.debug("[CCC] klijenti greška: %s", exc)

    # ── Nedostajući dokumenti + health_score ─────────────────────────────────
    # Project Nexus (2026-08-03): ovaj blok je ranije RUČNO računao i
    # "nedostajuci" (bez ikad selektovanog tip_dokaza -- gore sad ispravljeno
    # -- pa je "nedostajuci" UVEK bio kompletna expected lista, bez obzira šta
    # je stvarno otpremljeno) i sopstvenu kopiju health_score formule
    # (_compute_health, ispod, uklonjena) koja je hardkodovala nedostajuci_count=0
    # i imala svoj, nezavisno pokvaren naivni/svesni datetime bag (isti oblik
    # kao bag ispravljen u services/risk_engine.py par misija ranije). Sad
    # poziva ISTU deterministicku funkciju koju koristi Matter Intelligence
    # (services/risk_engine.py::calculate_procesni_rizik) -- jedan izvor
    # istine za "health_score"/"nedostajući dokazi" umesto dva koja mogu dati
    # različit odgovor za isti predmet pod istim imenom polja.
    _dok_count_data = (dok_count_r.data if not isinstance(dok_count_r, Exception) else []) or []
    _rok_raw = (rok_r.data if not isinstance(rok_r, Exception) else []) or []
    _rizik = calculate_procesni_rizik(
        dokazi=dokazi, dokumenti=_dok_count_data, rocista=_rok_raw,
        tip_predmeta=predmet.get("tip", "ostalo"), expected_docs=_EXPECTED_DOCS,
    )
    nedostajuci = _rizik["nedostajuci_dokazi"]
    health_score = _rizik["health_score"]

    # Kritičan rok (najhitniji u narednih 7 dana)
    kritican_rok = None
    for r in sorted(rokovi_data, key=lambda x: (x.get("dana_ostalo") is None, x.get("dana_ostalo") or 9999)):
        dana = r.get("dana_ostalo")
        if dana is not None and 0 <= dana <= 7:
            kritican_rok = r
            break

    return {
        "predmet":          predmet,
        "klijenti":         klijenti,
        "dok_stats":        dok_stats,
        "tip_stat":         tip_stat,
        "rokovi":           rokovi_data,
        "predstojeći":      predstojeći,
        "billing":          billing_data,
        "aktivnosti":       (hron_r.data if not isinstance(hron_r, Exception) else []) or [],
        "health_score":     health_score,
        "nedostajuci":      nedostajuci,
        "kritican_rok":     kritican_rok,
    }
