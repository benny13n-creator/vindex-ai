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
import difflib
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

# PRG-P1-NIGHT-001: `rapidfuzz` je uklonjen iz ovog puta. Bio je uvezen kroz
# `try/except ImportError`, pa je COI verdikt tiho zavisio od toga da li je
# paket instaliran: isti kod i isti ulaz davali su "conflict" sa paketom i
# "clear" bez njega. Sada je jedini motor `difflib` iz standardne biblioteke,
# zbog cega verdikt vise ne moze da varira po okruzenju.
_FUZZY_ENGINE = "token-difflib"

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


# Prag na kome se dva TOKENA smatraju istim tokenom.
#
# Kalibrisan merenjem na oba smera greske, nad korpusom od 758 jednoznakovnih
# mutacija stvarnih srpskih imena (izostavljanje / transpozicija / udvajanje):
#
#     prag <= 85 -> 0 propustenih pravih tipfelera, "Nikola"/"Nikolina" oznaceno
#     prag >= 86 -> 4.4% propustenih pravih tipfelera (33/758)
#
# Za proveru sukoba interesa propusten sukob je povreda Kodeksa, a suvisna
# oznaka je neugodnost. Zato se bira plato bez laznih negativa; 82 je njegova
# sredina, najdalje od obe ivice.
_TOKEN_JAK = 82


def _ratio(x: str, y: str) -> int:
    return int(difflib.SequenceMatcher(None, x, y).ratio() * 100)


def _transponovano(x: str, y: str) -> bool:
    """Tacno jedna zamena susednih znakova: 'ilic' <-> 'iilc'.

    `difflib` na kratkim tokenima kaznjava transpoziciju nesrazmerno
    ("ilic"/"iilc" = 50), pa bi bez ovog uslova obican tipfeler u prezimenu
    sakrio stvarni sukob. Uslov je namerno uzak — trazi susedne znakove, pa
    "maric"/"ramic" (razlicita prezimena, isti znakovi) NE prolazi.
    """
    if len(x) != len(y) or x == y:
        return False
    r = [i for i in range(len(x)) if x[i] != y[i]]
    return (len(r) == 2 and r[1] == r[0] + 1
            and x[r[0]] == y[r[1]] and x[r[1]] == y[r[0]])


def _upareno(x: str, y: str) -> int:
    """Skor uparivanja dva tokena, ili 0 ako se ne smatraju istim tokenom."""
    r = _ratio(x, y)
    if r >= _TOKEN_JAK or _transponovano(x, y):
        return max(r, _TOKEN_JAK)
    return 0


def _skor_smer(kraci: list[str], duzi: list[str]) -> int:
    """Pohlepno upari svaki token kraćeg imena sa najboljim slobodnim tokenom
    dužeg. Token se troši, pa se isto prezime ne može dvaput iskoristiti."""
    slobodni = list(duzi)
    jaki: list[int] = []
    for t in kraci:
        if not slobodni:
            break
        i = max(range(len(slobodni)), key=lambda k: _upareno(t, slobodni[k]))
        r = _upareno(t, slobodni[i])
        if r:
            jaki.append(r)
            slobodni.pop(i)

    if len(kraci) == 1 and len(duzi) == 1:
        # Jednorečno ime nema čime da se potvrdi — ceo string je jedini dokaz.
        return _ratio(kraci[0], duzi[0])
    if not jaki:
        return 0
    prosek = sum(jaki) // len(jaki)
    if len(jaki) == len(kraci) and len(kraci) >= 2:
        # Dva ili više nezavisnih tokena se poklapaju → isti subjekt. Višak
        # tokena u dužem imenu (srednje ime, grad, ogranak) se tolerise.
        return prosek
    # Delimično preklapanje. JEDAN zajednički token nije dokaz identiteta:
    # "Firma doo" i "Druga firma doo" dele rec "firma", "Milan Jovanović" i
    # "Milica Jovanović" dele prezime — ni jedno ni drugo nije isti subjekt.
    return prosek * len(jaki) // len(duzi)


def _fuzzy_score(a: str, b: str) -> int:
    """Score 0–100 sličnosti između dva imena stranke.

    Model je tokenski, ne nad celim string-om. Raniji
    `max(token_sort_ratio, partial_ratio)` je vracao 100 kad god je kraće ime
    bilo podniska dužeg, pa je stranka "Firma doo" (posle skidanja pravnog
    nastavka: "firma") pravila blokirajuci sukob sa svime sto sadrži tu rec.
    """
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return 0
    if na == nb:
        return 100
    ta, tb = na.split(), nb.split()
    if not ta or not tb:
        return 0
    if len(ta) < len(tb):
        return _skor_smer(ta, tb)
    if len(tb) < len(ta):
        return _skor_smer(tb, ta)
    # Jednak broj tokena — racunaj oba smera da skor ne bi zavisio od toga
    # koja je stranka upisana prva.
    return max(_skor_smer(ta, tb), _skor_smer(tb, ta))


def _best_score(termin: str, candidates: list[str]) -> int:
    """Najveći fuzzy score između termina i liste kandidata."""
    return max((_fuzzy_score(termin, c) for c in candidates if c), default=0)


def _conflict_reason(termin: str, matched_val: str, score: int, context: str) -> str:
    if score == 100:
        return f"Tačno podudaranje: '{matched_val}' u {context}"
    return f"Fuzzy podudaranje {score}%: '{termin}' ≈ '{matched_val}' u {context}"


# ── Statusi ───────────────────────────────────────────────────────────────────

# Operation Single Brain (2026-08-07): "u_toku" (underscore) added -- routers/cio.py,
# routers/morning_briefing.py, and klijenti/router.py all already treat "u_toku" as an
# active predmeti.status literal (`.in_("status", ["aktivan", "u_toku", "pending"])`), but
# this set only had "u toku" (space) -- a case actually stored with the underscore variant
# silently fell through conflict screening as "not active", the opposite of what a conflict-
# of-interest check should ever silently do. Both spellings now recognized; no other module
# needed to change.
_AKTIVNI_STATUSI  = {"aktivan", "u toku", "u_toku", "priprema", "odložen", "žalba"}
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

    # ── SLOJ 2: Klijenti — ime, firma, email (fuzzy) ─────────────────────────
    #
    # BETA-P1-COLUMN-DRIFT-007 / DRIFT-001.
    #
    # Ovde je stajalo `select("id,ime,prezime,firma,email,pib")`. Kolona `pib`
    # NE POSTOJI -- PIB se cuva sifrovan, kao `pib_encrypted` (mereno nad
    # produkcijom: `?select=...,pib` -> 400/42703, bez `pib` -> 200).
    # PostgREST odbija CEO zahtev, pa je ovaj sloj pucao na SVAKOM pozivu:
    # pretraga po klijentima se nikad nije izvrsila, `provera_potpuna` je bila
    # `False` uvek, i provera se nikad nije naplatila.
    #
    # `pib` se NE preimenuje u `pib_encrypted`: poredjenje otvorenog PIB-a iz
    # forme sa sifrovanom vrednoscu se ne bi nikad poklopilo -- dobili bismo tih
    # lazno-negativan nalaz umesto glasne greske. Desifrovanje svih klijenata na
    # svakoj proveri bi zaobislo strogi audit trag iz BETA-P0-SENSITIVE-DATA-AUDIT.
    if req.pib and req.pib.strip():
        # Trazeno je podudaranje po PIB-u, a ono se ne moze izvesti. Provera se
        # degradira na nepotpunu -- tiho ignorisanje bi na etickom ekranu bilo
        # lazno-negativan nalaz.
        sloj_status["klijenti"] = "pib_nepodržan"
        logger.warning("[CONFLICT/S2] PIB pretraga nije podržana (šifrovana kolona)")

    try:
        kl = await asyncio.to_thread(
            lambda: supa.table("klijenti").select(
                "id,ime,prezime,firma,email"
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

            # Email — exact match. (PIB poredjenje je uklonjeno: `k` vise ne
            # nosi `pib`, jer ta kolona ne postoji. Zahtev sa PIB-om je gore
            # vec degradirao ovaj sloj na nepotpun.)
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

    # SOA2-006 (second-order audit, 2026-08-08) — SAFETY, not just billing.
    # All three search layers swallow their own exceptions into
    # sloj_status[...] = "greška" (lines ~202, ~287, ~332) and simply
    # contribute no hits. With every layer down, `konflikti` is empty for the
    # same reason it is empty when there genuinely is no conflict — and the
    # endpoint then told the lawyer "Nije pronađen konflikt interesa. Možete
    # prihvatiti klijenta." A database outage therefore produced a
    # professional-ethics FALSE CLEAR on the exact question the Kodeks
    # profesionalne etike makes the lawyer personally responsible for.
    #
    # "No evidence of a conflict" and "we could not look" must never render as
    # the same answer. An incomplete check degrades to `review` (an existing
    # status the frontend already handles conservatively) and is NOT charged,
    # matching this codebase's canonical semantics: no delivered result, no
    # credit.
    # BETA-P1-COLUMN-DRIFT-007: bilo koje stanje koje NIJE "ok" cini proveru
    # nepotpunom. Ranije se gledalo samo `== "greška"`, pa bi svako novo stanje
    # (npr. „pretraga po ovom polju nije podrzana") tiho prolazilo kao potpuna
    # provera. Fail-closed po konstrukciji, ne po nabrajanju.
    _slojevi_greska = sorted(k for k, v in sloj_status.items() if v != "ok")
    _provera_potpuna = not _slojevi_greska

    if not konflikti and not _provera_potpuna:
        final_status = "review"
        poruka = (
            "⚠️ PROVERA NIJE POTPUNA — pretraga nije uspela za: "
            f"{', '.join(_slojevi_greska)}. Odsustvo rezultata NE znači da konflikta nema. "
            "Ponovite proveru pre nego što donesete odluku o prihvatanju klijenta."
        )
    elif not konflikti:
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

    logger.info("[CONFLICT] user=%s termini=%s status=%s konflikata=%d visoki=%d engine=%s",
                uid[:8], termini, final_status, len(konflikti), len(visoki), _FUZZY_ENGINE)

    # Only charge for a check that actually ran. See the SOA2-006 note above.
    if _provera_potpuna:
        await UsageService.consume(uid, user.get("email", ""), "conflict_check")

    return {
        "status":          final_status,
        "provera_potpuna": _provera_potpuna,
        "slojevi_greska":  _slojevi_greska,
        "konflikti": konflikti,
        "poruka":    poruka,
        "pretraga":  termini,
        "ukupno":    len(konflikti),
        "visoki":    len(visoki),
        "srednji":   len(srednji),
        "slojevi":   sloj_status,
        "fuzzy_engine": _FUZZY_ENGINE,
    }
