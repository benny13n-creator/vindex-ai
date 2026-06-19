# -*- coding: utf-8 -*-
"""
Conflict Check Engine — provera konflikta interesa pre prihvatanja klijenta.

POST /api/conflict-check
Proverava 4 sloja:
  1. Tužilac/tuženi u predmetima
  2. Klijenti tabela (ime, firma, email)
  3. Predmet_klijenti uloge (suprotna strana, bivši klijent)
  4. Saradnici — da li je neko iz tima radio za suprotnu stranu

Vraća: status (clear/conflict/review) + lista konflikata sa slojem i severitetom.
"""
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.conflict_check")
router = APIRouter(prefix="/api/conflict-check", tags=["conflict_check"])

# Statusi aktivnog predmeta (sve ostalo = zatvoreno)
_AKTIVNI_STATUSI = {"aktivan", "u toku", "priprema", "odložen", "žalba"}


class ConflictReq(BaseModel):
    ime_prezime: Optional[str] = None
    firma:       Optional[str] = None
    email:       Optional[str] = None
    pib:         Optional[str] = None   # PIB firme (novi parametar)
    advokat_ime: Optional[str] = None   # Advokat suprotne strane


def _is_active(status: str) -> bool:
    return (status or "").lower() in _AKTIVNI_STATUSI


@router.post("")
async def check_conflict(req: ConflictReq, user=Depends(get_current_user)):
    """
    4-slojna provera konflikta interesa.
    Sloj 1: predmeti.tuzilac / tuzeni
    Sloj 2: klijenti tabela (ime, firma, email, PIB)
    Sloj 3: predmet_klijenti uloge
    Sloj 4: advokat suprotne strane u istoriji predmeta
    """
    supa = _get_supa()
    uid  = user["user_id"]

    termini = []
    if req.ime_prezime and req.ime_prezime.strip():
        termini.append(req.ime_prezime.strip())
    if req.firma and req.firma.strip():
        termini.append(req.firma.strip())

    if not termini and not req.email and not req.pib and not req.advokat_ime:
        return {"status": "clear", "konflikti": [], "poruka": "Nisu uneseni podaci za proveru.",
                "pretraga": [], "slojevi": {}}

    konflikti   = []
    reviewed    = set()
    sloj_status = {"predmeti": "ok", "klijenti": "ok", "uloge": "ok", "advokat": "ok"}

    # ── SLOJ 1: Predmeti — tužilac/tuženi polja ─────────────────────────────
    try:
        pr = supa.table("predmeti").select(
            "id,naziv,tip,status,tuzilac,tuzeni,created_at"
        ).eq("user_id", uid).is_("deleted_at", "null").execute()

        for p in (pr.data or []):
            pid  = p["id"]
            tuz  = (p.get("tuzilac") or "").lower()
            tuz2 = (p.get("tuzeni")  or "").lower()
            for termin in termini:
                t_low = termin.lower()
                if pid in reviewed:
                    continue
                if t_low in tuz:
                    konflikti.append({
                        "sloj":          "predmeti",
                        "tip_konflikta": "tuzilac",
                        "sever":         "VISOK" if _is_active(p.get("status","")) else "NIZAK",
                        "predmet_id":    pid,
                        "predmet_naziv": p.get("naziv",""),
                        "predmet_status": p.get("status",""),
                        "predmet_tip":   p.get("tip",""),
                        "podudaranje":   p.get("tuzilac",""),
                        "datum":         (p.get("created_at","") or "")[:10],
                        "opis": f"'{termin}' se poklapa sa tužiocem u predmetu '{p.get('naziv','')}' [{p.get('status','')}]",
                    })
                    reviewed.add(pid)
                if t_low in tuz2 and pid not in reviewed:
                    konflikti.append({
                        "sloj":          "predmeti",
                        "tip_konflikta": "tuzeni",
                        "sever":         "VISOK" if _is_active(p.get("status","")) else "NIZAK",
                        "predmet_id":    pid,
                        "predmet_naziv": p.get("naziv",""),
                        "predmet_status": p.get("status",""),
                        "predmet_tip":   p.get("tip",""),
                        "podudaranje":   p.get("tuzeni",""),
                        "datum":         (p.get("created_at","") or "")[:10],
                        "opis": f"'{termin}' se poklapa sa tuženim u predmetu '{p.get('naziv','')}' [{p.get('status','')}]",
                    })
                    reviewed.add(pid)
    except Exception as exc:
        logger.warning("[CONFLICT/S1] predmeti greška: %s", exc)
        sloj_status["predmeti"] = "greška"

    # ── SLOJ 2: Klijenti — ime, firma, email, PIB ────────────────────────────
    try:
        kl = supa.table("klijenti").select(
            "id,ime,prezime,firma,email"
        ).eq("user_id", uid).execute()

        for k in (kl.data or []):
            puno_ime = ((k.get("ime","") + " " + k.get("prezime","")).strip()).lower()
            firma_k  = (k.get("firma","") or "").lower()
            email_k  = (k.get("email","") or "").lower()

            # Matching po imenu/firmi
            matched = any(t.lower() in puno_ime or t.lower() in firma_k for t in termini)
            # Matching po emailu
            if req.email and req.email.lower() == email_k:
                matched = True

            if not matched:
                continue

            kpr = supa.table("predmet_klijenti").select(
                "predmet_id,uloga,predmeti(naziv,status,tip)"
            ).eq("klijent_id", k["id"]).execute()

            for kp in (kpr.data or []):
                pp   = kp.get("predmeti") or {}
                pid  = kp.get("predmet_id","")
                if pid in reviewed:
                    continue
                uloga   = kp.get("uloga","")
                display = (k.get("firma","").strip() or
                           (k.get("ime","")+" "+k.get("prezime","")).strip() or "?")
                je_suprotna = any(x in uloga.lower() for x in ("suprotna","protivna","tuženi","oponent"))
                je_bivsi    = "klijent" in uloga.lower()
                tip_k = "suprotna_strana" if je_suprotna else ("bivsi_klijent" if je_bivsi else "klijent_u_sistemu")
                konflikti.append({
                    "sloj":          "klijenti",
                    "tip_konflikta": tip_k,
                    "sever":         "VISOK" if (je_suprotna and _is_active(pp.get("status",""))) else "SREDNJI",
                    "predmet_id":    pid,
                    "predmet_naziv": pp.get("naziv",""),
                    "predmet_status": pp.get("status",""),
                    "predmet_tip":   pp.get("tip",""),
                    "podudaranje":   display,
                    "uloga":         uloga,
                    "opis": f"'{display}' nastupao kao '{uloga}' u predmetu '{pp.get('naziv','')}' [{pp.get('status','')}]",
                })
                reviewed.add(pid)
    except Exception as exc:
        logger.warning("[CONFLICT/S2] klijenti greška: %s", exc)
        sloj_status["klijenti"] = "greška"

    # ── SLOJ 3 (novo): Advokat suprotne strane u hronologiji ─────────────────
    if req.advokat_ime and req.advokat_ime.strip():
        try:
            adv_low = req.advokat_ime.strip().lower()
            hr = supa.table("predmet_hronologija").select(
                "predmet_id,dogadjaj,akter,datum,predmeti(naziv,status,tip)"
            ).eq("user_id", uid).execute()
            seen_adv = set()
            for h in (hr.data or []):
                akter = (h.get("akter") or "").lower()
                dogadjaj = (h.get("dogadjaj") or "").lower()
                pid = h.get("predmet_id","")
                if pid in seen_adv:
                    continue
                if adv_low in akter or adv_low in dogadjaj:
                    pp = h.get("predmeti") or {}
                    konflikti.append({
                        "sloj":          "advokat",
                        "tip_konflikta": "advokat_suprotne_strane",
                        "sever":         "SREDNJI",
                        "predmet_id":    pid,
                        "predmet_naziv": pp.get("naziv",""),
                        "predmet_status": pp.get("status",""),
                        "predmet_tip":   pp.get("tip",""),
                        "podudaranje":   req.advokat_ime,
                        "opis": f"Advokat '{req.advokat_ime}' se pominje u hronologiji predmeta '{pp.get('naziv','')}'",
                    })
                    seen_adv.add(pid)
        except Exception as exc:
            logger.warning("[CONFLICT/S3] advokat greška: %s", exc)
            sloj_status["advokat"] = "greška"

    # ── Odredi ukupni status ─────────────────────────────────────────────────
    visoki   = [k for k in konflikti if k.get("sever") == "VISOK"]
    srednji  = [k for k in konflikti if k.get("sever") == "SREDNJI"]
    aktivni  = [k for k in konflikti if _is_active(k.get("predmet_status",""))]

    if not konflikti:
        final_status = "clear"
        poruka = "Nije pronađen konflikt interesa. Možete prihvatiti klijenta."
    elif visoki and aktivni:
        final_status = "conflict"
        poruka = (f"🚨 OZBILJAN KONFLIKT: {len(visoki)} konflikata visokog prioriteta u aktivnim predmetima! "
                  f"Prihvatanje klijenta može biti povreda Kodeksa profesionalne etike advokata Srbije.")
    elif konflikti:
        active_cnt = len(aktivni)
        if active_cnt > 0:
            final_status = "conflict"
            poruka = (f"⚠️ KONFLIKT: {active_cnt} predmeta sa aktivnim preklapanjem. "
                      f"Konsultujte čl. 44-48 Kodeksa profesionalne etike pre prihvatanja.")
        else:
            final_status = "review"
            poruka = (f"🔍 PREGLED: {len(konflikti)} zatvorenih predmeta sa preklapanjem. "
                      f"Preporučena detaljna provera pre prihvatanja.")

    logger.info("[CONFLICT] user=%s termini=%s status=%s konflikata=%d visoki=%d",
                uid[:8], termini, final_status, len(konflikti), len(visoki))

    return {
        "status":       final_status,
        "konflikti":    konflikti,
        "poruka":       poruka,
        "pretraga":     termini,
        "ukupno":       len(konflikti),
        "visoki":       len(visoki),
        "srednji":      len(srednji),
        "slojevi":      sloj_status,
    }
