# -*- coding: utf-8 -*-
"""
Conflict Check Engine — provera konflikta interesa pre prihvatanja klijenta.

POST /api/conflict-check
Proverava 4 sloja:
  1. Tužilac/tuženi u predmetima (fuzzy)
  2. Klijenti tabela (ime, firma, email, PIB) (fuzzy)
  3. Predmet_klijenti uloge (suprotna strana, bivši klijent)
  4. Advokat suprotne strane u hronologiji (fuzzy)

Vraća: status (clear/conflict/review) + lista konflikata sa slojem, severitetom,
        conflict_score i conflict_reason.
"""
import asyncio
import logging
import re
import unicodedata

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from shared.deps import _get_supa
from shared.permissions import PermissionService
from shared.usage import UsageService

logger = logging.getLogger("vindex.conflict_check")
router = APIRouter(prefix="/api/conflict-check", tags=["conflict_check"])

# ── Fuzzy matching helpers ────────────────────────────────────────────────────

try:
    from rapidfuzz import fuzz
    _RAPIDFUZZ = True
except ImportError:
    _RAPIDFUZZ = False

_CYR_TO_LAT = str.maketrans({
    'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Ђ':'Dj','Е':'E','Ж':'Zh','З':'Z',
    'И':'I','Ј':'J','К':'K','Л':'L','Љ':'Lj','М':'M','Н':'N','Њ':'Nj','О':'O',
    'П':'P','Р':'R','С':'S','Т':'T','Ћ':'C','У':'U','Ф':'F','Х':'H','Ц':'Ts',
    'Ч':'Ch','Џ':'Dz','Ш':'Sh',
    'а':'a','б':'b','в':'v','г':'g','д':'d','ђ':'dj','е':'e','ж':'zh','з':'z',
    'и':'i','ј':'j','к':'k','л':'l','љ':'lj','м':'m','н':'n','њ':'nj','о':'o',
    'п':'p','р':'r','с':'s','т':'t','ћ':'c','у':'u','ф':'f','х':'h','ц':'ts',
    'ч':'ch','џ':'dz','ш':'sh',
})

CONFLICT_HARD = 85   # Definitivni konflikt
CONFLICT_WARN = 70   # Potencijalni konflikt — review


def _normalize_name(name: str) -> str:
    """Ćirilica→latinica, ukloni pravne nastavke, bez dijakritika, lowercase."""
    if not name:
        return ""
    s = name.translate(_CYR_TO_LAT)
    for suffix in [' d.o.o.', ' d.o.o', ' doo', ' a.d.', ' a.d', ' ad',
                   ' d.d.', ' dd', ' j.p.', ' jp', ' o.d.', ' od',
                   ' k.d.', ' kd', ' preduzetnik', ' pr.', ' pr']:
        if s.lower().endswith(suffix.lower()):
            s = s[:len(s) - len(suffix)]
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s


def _fuzzy_score(a: str, b: str) -> int:
    """Score 0–100 sličnosti između dva string-a."""
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return 0
    if na == nb:
        return 100
    if _RAPIDFUZZ:
        return max(fuzz.token_sort_ratio(na, nb), fuzz.partial_ratio(na, nb))
    import difflib
    return int(difflib.SequenceMatcher(None, na, nb).ratio() * 100)


def _best_score(termin: str, candidates: list[str]) -> int:
    """Najveći fuzzy score između termina i liste kandidata."""
    return max((_fuzzy_score(termin, c) for c in candidates if c), default=0)


def _conflict_reason(termin: str, matched_val: str, score: int, context: str) -> str:
    if score == 100:
        return f"Tačno podudaranje: '{matched_val}' u {context}"
    return f"Fuzzy podudaranje {score}%: '{termin}' ≈ '{matched_val}' u {context}"


# ── Statusi ───────────────────────────────────────────────────────────────────

_AKTIVNI_STATUSI  = {"aktivan", "u toku", "priprema", "odložen", "žalba"}
_ZATVORENI_STATUSI = {"zatvoren", "rešen", "povučen", "odbačen", "arhiviran"}


def _is_active(status: str) -> bool:
    return (status or "").lower() in _AKTIVNI_STATUSI


def _is_closed(status: str) -> bool:
    return (status or "").lower() in _ZATVORENI_STATUSI


# ── Request model ─────────────────────────────────────────────────────────────

class ConflictReq(BaseModel):
    ime_prezime: Optional[str] = None
    firma:       Optional[str] = None
    email:       Optional[str] = None
    pib:         Optional[str] = None
    advokat_ime: Optional[str] = None


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("")
async def check_conflict(req: ConflictReq, user=Depends(PermissionService.require("conflict_check"))):
    """
    4-slojna fuzzy provera konflikta interesa.
    Sloj 1: predmeti.tuzilac / tuzeni
    Sloj 2: klijenti tabela (ime, firma, email, PIB)
    Sloj 3: predmet_klijenti uloge
    Sloj 4: advokat suprotne strane u hronologiji
    Uključuje zatvorene predmete sa oznakom [BIVŠI KLIJENT].
    """
    supa = _get_supa()
    uid  = user["user_id"]

    termini: list[str] = []
    if req.ime_prezime and req.ime_prezime.strip():
        termini.append(req.ime_prezime.strip())
    if req.firma and req.firma.strip():
        termini.append(req.firma.strip())

    if not termini and not req.email and not req.pib and not req.advokat_ime:
        return {"status": "clear", "konflikti": [], "poruka": "Nisu uneseni podaci za proveru.",
                "pretraga": [], "slojevi": {}}

    konflikti:   list[dict] = []
    reviewed:    set        = set()
    sloj_status: dict       = {"predmeti": "ok", "klijenti": "ok", "uloge": "ok", "advokat": "ok"}

    # ── SLOJ 1: Predmeti — tužilac/tuženi (fuzzy) ────────────────────────────
    try:
        pr = await asyncio.to_thread(
            lambda: supa.table("predmeti").select(
                "id,naziv,tip,status,tuzilac,tuzeni,created_at"
            ).eq("user_id", uid).execute()
        )

        for p in (pr.data or []):
            pid   = p["id"]
            tuz   = p.get("tuzilac") or ""
            tuz2  = p.get("tuzeni")  or ""
            bivsi = _is_closed(p.get("status", ""))

            for termin in termini:
                if pid in reviewed:
                    break

                score_tuz  = _fuzzy_score(termin, tuz)
                score_tuz2 = _fuzzy_score(termin, tuz2)
                best_score = max(score_tuz, score_tuz2)

                if best_score < CONFLICT_WARN:
                    continue

                which     = "tuzilac" if score_tuz >= score_tuz2 else "tuzeni"
                matched_v = tuz if which == "tuzilac" else tuz2
                label     = "[BIVŠI KLIJENT] " if bivsi else ""
                konflikti.append({
                    "sloj":            "predmeti",
                    "tip_konflikta":   which,
                    "sever":           "VISOK" if (_is_active(p.get("status","")) and best_score >= CONFLICT_HARD)
                                       else ("SREDNJI" if best_score >= CONFLICT_HARD else "NIZAK"),
                    "predmet_id":      pid,
                    "predmet_naziv":   p.get("naziv",""),
                    "predmet_status":  p.get("status",""),
                    "predmet_tip":     p.get("tip",""),
                    "podudaranje":     matched_v,
                    "datum":           (p.get("created_at","") or "")[:10],
                    "conflict_score":  best_score,
                    "conflict_reason": _conflict_reason(termin, matched_v, best_score, f"{label}predmet '{p.get('naziv','')}'"),
                    "opis":            f"{label}'{termin}' ({best_score}%) ≈ {which} '{matched_v}' u predmetu '{p.get('naziv','')}' [{p.get('status','')}]",
                })
                reviewed.add(pid)
                break

    except Exception as exc:
        logger.warning("[CONFLICT/S1] predmeti greška: %s", exc)
        sloj_status["predmeti"] = "greška"

    # ── SLOJ 2: Klijenti — ime, firma, email, PIB (fuzzy) ────────────────────
    try:
        kl = await asyncio.to_thread(
            lambda: supa.table("klijenti").select(
                "id,ime,prezime,firma,email,pib"
            ).eq("user_id", uid).execute()
        )

        matching_klijent_ids:  list = []
        matching_klijenti_map: dict = {}
        match_scores:          dict = {}  # kid → score

        for k in (kl.data or []):
            kid       = k["id"]
            puno_ime  = f"{k.get('ime','') or ''} {k.get('prezime','') or ''}".strip()
            firma_k   = k.get("firma","") or ""
            email_k   = (k.get("email","") or "").lower()
            pib_k     = (k.get("pib","") or "").strip()

            # PIB i email — exact match
            if req.pib and req.pib.strip() and req.pib.strip() == pib_k:
                matching_klijent_ids.append(kid)
                matching_klijenti_map[kid] = k
                match_scores[kid] = 100
                continue
            if req.email and req.email.lower() == email_k:
                matching_klijent_ids.append(kid)
                matching_klijenti_map[kid] = k
                match_scores[kid] = 100
                continue

            # Fuzzy po imenu/firmi
            best = 0
            for termin in termini:
                best = max(best, _best_score(termin, [puno_ime, firma_k]))
            if best >= CONFLICT_WARN:
                matching_klijent_ids.append(kid)
                matching_klijenti_map[kid] = k
                match_scores[kid] = best

        if matching_klijent_ids:
            kpr_all = await asyncio.to_thread(
                lambda: supa.table("predmet_klijenti").select(
                    "klijent_id,predmet_id,uloga,predmeti(naziv,status,tip)"
                ).in_("klijent_id", matching_klijent_ids).execute()
            )

            for kp in (kpr_all.data or []):
                pp   = kp.get("predmeti") or {}
                pid  = kp.get("predmet_id","")
                kid  = kp.get("klijent_id","")
                if pid in reviewed:
                    continue

                k       = matching_klijenti_map.get(kid, {})
                uloga   = kp.get("uloga","") or ""
                display = (k.get("firma","") or "").strip() or \
                          f"{k.get('ime','') or ''} {k.get('prezime','') or ''}".strip() or "?"
                score   = match_scores.get(kid, CONFLICT_WARN)

                je_suprotna = any(x in uloga.lower() for x in ("suprotna","protivna","tuženi","oponent"))
                je_bivsi    = _is_closed(pp.get("status","")) or "bivši" in uloga.lower() or "bivsi" in uloga.lower()
                tip_k = "suprotna_strana" if je_suprotna else ("bivsi_klijent" if je_bivsi else "klijent_u_sistemu")

                label = "[BIVŠI KLIJENT] " if je_bivsi else ""
                konflikti.append({
                    "sloj":            "klijenti",
                    "tip_konflikta":   tip_k,
                    "sever":           "VISOK" if (je_suprotna and _is_active(pp.get("status",""))) else "SREDNJI",
                    "predmet_id":      pid,
                    "predmet_naziv":   pp.get("naziv",""),
                    "predmet_status":  pp.get("status",""),
                    "predmet_tip":     pp.get("tip",""),
                    "podudaranje":     display,
                    "uloga":           uloga,
                    "conflict_score":  score,
                    "conflict_reason": f"{label}Klijent '{display}' (score {score}%) nastupao kao '{uloga}'",
                    "opis":            f"{label}'{display}' ({score}%) nastupao kao '{uloga}' u predmetu '{pp.get('naziv','')}' [{pp.get('status','')}]",
                })
                reviewed.add(pid)

    except Exception as exc:
        logger.warning("[CONFLICT/S2] klijenti greška: %s", exc)
        sloj_status["klijenti"] = "greška"

    # ── SLOJ 3: Advokat suprotne strane (fuzzy) ───────────────────────────────
    if req.advokat_ime and req.advokat_ime.strip():
        try:
            hr = await asyncio.to_thread(
                lambda: supa.table("predmet_hronologija").select(
                    "predmet_id,dogadjaj,akter,datum,predmeti(naziv,status,tip)"
                ).eq("user_id", uid).execute()
            )
            seen_adv: set = set()
            for h in (hr.data or []):
                akter    = h.get("akter") or ""
                dogadjaj = h.get("dogadjaj") or ""
                pid      = h.get("predmet_id","")
                if pid in seen_adv:
                    continue

                score_a = _fuzzy_score(req.advokat_ime, akter)
                score_d = _fuzzy_score(req.advokat_ime, dogadjaj)
                score   = max(score_a, score_d)

                if score < CONFLICT_WARN:
                    continue

                pp = h.get("predmeti") or {}
                bivsi = _is_closed(pp.get("status",""))
                label = "[BIVŠI PREDMET] " if bivsi else ""
                konflikti.append({
                    "sloj":            "advokat",
                    "tip_konflikta":   "advokat_suprotne_strane",
                    "sever":           "SREDNJI",
                    "predmet_id":      pid,
                    "predmet_naziv":   pp.get("naziv",""),
                    "predmet_status":  pp.get("status",""),
                    "predmet_tip":     pp.get("tip",""),
                    "podudaranje":     req.advokat_ime,
                    "conflict_score":  score,
                    "conflict_reason": f"{label}Advokat '{req.advokat_ime}' (score {score}%) nađen u hronologiji",
                    "opis":            f"{label}Advokat '{req.advokat_ime}' ({score}%) pominje se u hronologiji predmeta '{pp.get('naziv','')}'",
                })
                seen_adv.add(pid)

        except Exception as exc:
            logger.warning("[CONFLICT/S3] advokat greška: %s", exc)
            sloj_status["advokat"] = "greška"

    # ── Odredi ukupni status ──────────────────────────────────────────────────
    visoki  = [k for k in konflikti if k.get("sever") == "VISOK"]
    srednji = [k for k in konflikti if k.get("sever") == "SREDNJI"]
    aktivni = [k for k in konflikti if _is_active(k.get("predmet_status",""))]

    if not konflikti:
        final_status = "clear"
        poruka = "Nije pronađen konflikt interesa. Možete prihvatiti klijenta."
    elif visoki and aktivni:
        final_status = "conflict"
        poruka = (f"🚨 OZBILJAN KONFLIKT: {len(visoki)} konflikata visokog prioriteta u aktivnim predmetima! "
                  f"Prihvatanje klijenta može biti povreda Kodeksa profesionalne etike advokata Srbije.")
    elif aktivni:
        final_status = "conflict"
        poruka = (f"⚠️ KONFLIKT: {len(aktivni)} predmeta sa aktivnim preklapanjem. "
                  f"Konsultujte čl. 44–48 Kodeksa profesionalne etike pre prihvatanja.")
    else:
        final_status = "review"
        poruka = (f"🔍 PREGLED: {len(konflikti)} zatvorenih predmeta sa preklapanjem (bivši klijenti). "
                  f"Preporučena detaljna provera pre prihvatanja.")

    logger.info("[CONFLICT] user=%s termini=%s status=%s konflikata=%d visoki=%d rapidfuzz=%s",
                uid[:8], termini, final_status, len(konflikti), len(visoki), _RAPIDFUZZ)

    await UsageService.consume(uid, user.get("email", ""), "conflict_check")

    return {
        "status":    final_status,
        "konflikti": konflikti,
        "poruka":    poruka,
        "pretraga":  termini,
        "ukupno":    len(konflikti),
        "visoki":    len(visoki),
        "srednji":   len(srednji),
        "slojevi":   sloj_status,
        "fuzzy_engine": "rapidfuzz" if _RAPIDFUZZ else "difflib",
    }
