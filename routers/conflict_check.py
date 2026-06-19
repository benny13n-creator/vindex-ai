# -*- coding: utf-8 -*-
"""
Conflict Check Engine — provera konflikta interesa pre prihvatanja klijenta.

POST /api/conflict-check
Proverava: tuzilac/tuzeni u predmetima, klijenti tabela, predmet_klijenti uloge.
Vraća: status (clear/conflict/review) + lista konflikata.
"""
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.conflict_check")
router = APIRouter(prefix="/api/conflict-check", tags=["conflict_check"])


class ConflictReq(BaseModel):
    ime_prezime: Optional[str] = None
    firma:       Optional[str] = None
    email:       Optional[str] = None


@router.post("")
async def check_conflict(req: ConflictReq, user=Depends(get_current_user)):
    """
    Proverava potencijalne konflikte interesa.
    Pretraži kancelarijske predmete i klijente po imenu/firmi/emailu.
    """
    supa = _get_supa()
    uid  = user["user_id"]

    termini = []
    if req.ime_prezime and req.ime_prezime.strip():
        termini.append(req.ime_prezime.strip())
    if req.firma and req.firma.strip():
        termini.append(req.firma.strip())

    if not termini:
        return {"status": "clear", "konflikti": [], "poruka": "Nisu uneseni podaci za proveru."}

    konflikti = []
    reviewed  = set()  # sprečava duplikate

    for termin in termini:
        t_low = termin.lower()

        # ── 1. Pretraži tuzilac/tuzeni u predmetima ─────────────────────────
        try:
            pr = supa.table("predmeti").select(
                "id,naziv,tip,status,tuzilac,tuzeni,created_at"
            ).eq("user_id", uid).is_("deleted_at", "null").execute()
            for p in (pr.data or []):
                pid = p["id"]
                if pid in reviewed:
                    continue
                tuz  = (p.get("tuzilac") or "").lower()
                tuz2 = (p.get("tuzeni")  or "").lower()
                if t_low in tuz:
                    konflikti.append({
                        "tip_konflikta": "tuzilac",
                        "predmet_id":    pid,
                        "predmet_naziv": p.get("naziv",""),
                        "predmet_status": p.get("status",""),
                        "predmet_tip":   p.get("tip",""),
                        "podudaranje":   p.get("tuzilac",""),
                        "datum":         (p.get("created_at","") or "")[:10],
                        "opis": f"Ime '{termin}' se poklapa sa tužiocem u predmetu '{p.get('naziv','')}'",
                    })
                    reviewed.add(pid)
                if t_low in tuz2 and pid not in reviewed:
                    konflikti.append({
                        "tip_konflikta": "tuzeni",
                        "predmet_id":    pid,
                        "predmet_naziv": p.get("naziv",""),
                        "predmet_status": p.get("status",""),
                        "predmet_tip":   p.get("tip",""),
                        "podudaranje":   p.get("tuzeni",""),
                        "datum":         (p.get("created_at","") or "")[:10],
                        "opis": f"Ime '{termin}' se poklapa sa tuženim u predmetu '{p.get('naziv','')}'",
                    })
                    reviewed.add(pid)
        except Exception as exc:
            logger.warning("[CONFLICT] predmeti greška: %s", exc)

        # ── 2. Pretraži klijente ─────────────────────────────────────────────
        try:
            kl = supa.table("klijenti").select(
                "id,ime,prezime,firma,email"
            ).eq("user_id", uid).execute()
            for k in (kl.data or []):
                puno_ime = ((k.get("ime","") + " " + k.get("prezime","")).strip()).lower()
                firma_k  = (k.get("firma","") or "").lower()
                email_k  = (k.get("email","") or "").lower()
                match = (t_low in puno_ime) or (t_low in firma_k)
                email_match = req.email and req.email.lower() == email_k
                if not match and not email_match:
                    continue
                # Pronađi predmete gde je ovaj klijent bio suprotna strana
                kpr = supa.table("predmet_klijenti").select(
                    "predmet_id,uloga,predmeti(naziv,status,tip)"
                ).eq("klijent_id", k["id"]).execute()
                for kp in (kpr.data or []):
                    pp  = kp.get("predmeti") or {}
                    pid = kp.get("predmet_id","")
                    if pid in reviewed:
                        continue
                    uloga = kp.get("uloga","")
                    display = (k.get("firma","").strip() or
                               (k.get("ime","")+" "+k.get("prezime","")).strip() or "?")
                    konflikti.append({
                        "tip_konflikta": "bivsi_klijent" if "klijent" in uloga.lower() else "suprotna_strana",
                        "predmet_id":    pid,
                        "predmet_naziv": pp.get("naziv",""),
                        "predmet_status": pp.get("status",""),
                        "predmet_tip":   pp.get("tip",""),
                        "podudaranje":   display,
                        "uloga":         uloga,
                        "opis": f"'{termin}' nastupao kao '{uloga}' u predmetu '{pp.get('naziv','')}'",
                    })
                    reviewed.add(pid)
        except Exception as exc:
            logger.warning("[CONFLICT] klijenti greška: %s", exc)

    # ── Odredi status ────────────────────────────────────────────────────────
    if not konflikti:
        status  = "clear"
        poruka  = "Nije pronađen konflikt interesa. Možete prihvatiti klijenta."
    else:
        active_conflicts = [k for k in konflikti if k.get("predmet_status","") not in ("zatvoren","arhiviran")]
        if active_conflicts:
            status = "conflict"
            poruka = (f"PAŽNJA: Pronađeno {len(active_conflicts)} aktivnih konflikata interesa! "
                      f"Konsultujte Kodeks profesionalne etike advokata pre prihvatanja.")
        else:
            status = "review"
            poruka = (f"Pronađeno {len(konflikti)} zatvorenih predmeta sa sličnim imenima. "
                      f"Preporučena detaljna provera.")

    logger.info("[CONFLICT] user=%s termini=%s status=%s konflikata=%d",
                uid[:8], termini, status, len(konflikti))

    return {
        "status":    status,
        "konflikti": konflikti,
        "poruka":    poruka,
        "pretraga":  termini,
    }
