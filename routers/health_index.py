# routers/health_index.py
# Law Firm Health Index — jedan broj (0–100) koji opisuje zdravlje cele kancelarije.
# Chief Partner — proaktivna direktiva koju sistem šalje svakog jutra.
# Weak Signals — statistički obrasci iz zatvorenih predmeta.
# Institutional Risk — koncentracija klijenata, oblasti, ekspertize.

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI

from shared.deps import _get_supa
from shared.permissions import PermissionService
from shared.usage import UsageService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health_index"])

_openai = AsyncOpenAI()
_CACHE: dict = {}          # {uid: {score:…, ts:…, chief_partner:…, signals:…}}
_CACHE_TTL = 3600          # 1 sat


def _grade(score: int) -> str:
    if score >= 90: return "A+"
    if score >= 80: return "A"
    if score >= 70: return "B+"
    if score >= 60: return "B"
    if score >= 50: return "C+"
    if score >= 40: return "C"
    return "D"


def _grade_color(score: int) -> str:
    if score >= 80: return "#4ade80"
    if score >= 60: return "#fbbf24"
    if score >= 40: return "#fb923c"
    return "#f87171"


# ─── Kalkulacija komponenti ───────────────────────────────────────────────────

async def _compute_health(uid: str, supa) -> dict:
    today = date.today().isoformat()
    in_7  = (date.today() + timedelta(days=7)).isoformat()
    in_30 = (date.today() - timedelta(days=30)).isoformat()
    this_month_start = date.today().replace(day=1).isoformat()

    (
        predmeti_r,
        rocista_r,
        billing_r,
        hron_r,
        closed_r,
    ) = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,naziv,status,case_dna,rizik_nivo,created_at")
            .eq("user_id", uid).execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("predmet_id,datum,status")
            .eq("user_id", uid)
            .gte("datum", today).lte("datum", in_7).execute()),
        asyncio.to_thread(lambda: supa.table("billing_entries")
            .select("iznos,created_at")
            .eq("user_id", uid)
            .gte("created_at", this_month_start).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("predmet_id,created_at")
            .eq("user_id", uid)
            .gte("created_at", in_30).execute()),
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,naziv,case_dna,tip")
            .eq("user_id", uid).eq("status", "zatvoren").execute()),
        return_exceptions=True,
    )

    predmeti  = [] if isinstance(predmeti_r, Exception) else (predmeti_r.data or [])
    rocista   = [] if isinstance(rocista_r,  Exception) else (rocista_r.data  or [])
    billing   = [] if isinstance(billing_r,  Exception) else (billing_r.data  or [])
    hron      = [] if isinstance(hron_r,     Exception) else (hron_r.data     or [])
    closed    = [] if isinstance(closed_r,   Exception) else (closed_r.data   or [])

    aktivni   = [p for p in predmeti if p.get("status") != "zatvoren"]
    n_aktivni = len(aktivni)

    alerts   = []
    insights = []

    # ── 1. DEADLINE PRESSURE (20 bodova) ─────────────────────────────────────
    n_roc = len(rocista)
    overdue = [r for r in rocista if r.get("datum", "") < today]
    if overdue:
        dp_score = 4
        alerts.append(f"⚠️ {len(overdue)} ročišt{'e' if len(overdue)==1 else 'a'} je prošlo bez oznake završetka")
    elif n_roc == 0:
        dp_score = 20
    elif n_roc <= 2:
        dp_score = 16; alerts.append(f"📅 {n_roc} ročišt{'e' if n_roc==1 else 'a'} u narednih 7 dana — proveri pripremu")
    elif n_roc <= 4:
        dp_score = 11; alerts.append(f"📅 {n_roc} ročišta u narednih 7 dana — intenzivan period")
    else:
        dp_score = 6;  alerts.append(f"🔴 {n_roc} ročišta u narednih 7 dana — kritično opterećenje")

    # ── 2. SNAGA PREDMETA (20 bodova) ────────────────────────────────────────
    snage = []
    slabi = []
    for p in aktivni:
        genome = p.get("case_dna") or {}
        if isinstance(genome, dict):
            s = genome.get("snaga_predmeta_procent")
            if s is not None:
                try:
                    sv = float(s)
                    snage.append(sv)
                    if sv < 45:
                        slabi.append(p.get("naziv", "Predmet"))
                except Exception:
                    pass

    if not snage:
        cs_score = 12  # neutralno ako nema genome podataka
    else:
        avg = sum(snage) / len(snage)
        if avg >= 70:   cs_score = 20
        elif avg >= 55: cs_score = 15; insights.append(f"Prosečna snaga predmeta: {avg:.0f}%")
        elif avg >= 40: cs_score = 9;  alerts.append(f"⚠️ Prosečna snaga predmeta pala na {avg:.0f}%")
        else:           cs_score = 4;  alerts.append(f"🔴 Prosečna snaga predmeta kritično niska: {avg:.0f}%")
        if slabi:
            alerts.append(f"⚠️ Slabi predmeti (<45%): {', '.join(slabi[:3])}")

    # ── 3. NAPLATA (20 bodova) ────────────────────────────────────────────────
    mesecna = sum(float(b.get("iznos") or 0) for b in billing)
    if mesecna <= 0:
        bh_score = 8
        alerts.append("⚠️ Nema evidentiranih stavki naplate ovaj mesec")
    elif mesecna >= 200_000:
        bh_score = 20; insights.append(f"Naplata ovaj mesec: {mesecna:,.0f} RSD")
    elif mesecna >= 100_000:
        bh_score = 16; insights.append(f"Naplata ovaj mesec: {mesecna:,.0f} RSD")
    elif mesecna >= 50_000:
        bh_score = 12
    else:
        bh_score = 7;  alerts.append(f"Naplata ovaj mesec ispod očekivanog: {mesecna:,.0f} RSD")

    # ── 4. ANGAŽOVANOST KLIJENATA (15 bodova) ────────────────────────────────
    aktivni_ids = {p["id"] for p in aktivni}
    aktivni_u_30 = {h["predmet_id"] for h in hron if h.get("predmet_id") in aktivni_ids}
    neaktivni = len(aktivni_ids) - len(aktivni_u_30)
    if neaktivni <= 0:
        ce_score = 15
    elif neaktivni == 1:
        ce_score = 12; alerts.append("⚠️ 1 aktivni predmet bez aktivnosti 30+ dana")
    elif neaktivni <= 3:
        ce_score = 8;  alerts.append(f"⚠️ {neaktivni} aktivnih predmeta bez aktivnosti 30+ dana")
    else:
        ce_score = 3;  alerts.append(f"🔴 {neaktivni} predmeta zanemareno 30+ dana")

    # ── 5. PORTFOLIO RIZIK (15 bodova) ───────────────────────────────────────
    visok_rizik = sum(1 for p in aktivni if p.get("rizik_nivo") in ("visok", "kritican"))
    if n_aktivni == 0:
        pr_score = 15
    else:
        pct = visok_rizik / n_aktivni
        if pct == 0:        pr_score = 15
        elif pct <= 0.1:    pr_score = 13
        elif pct <= 0.25:   pr_score = 9;  alerts.append(f"⚠️ {visok_rizik} predmeta visokog rizika ({pct*100:.0f}% portfolija)")
        elif pct <= 0.4:    pr_score = 5;  alerts.append(f"🔴 {visok_rizik} predmeta visokog rizika — potrebna hitna akcija")
        else:               pr_score = 2;  alerts.append(f"🚨 Više od 40% portfolija je visokorizično")

    # ── 6. OPTEREĆENOST (10 bodova) ───────────────────────────────────────────
    if n_aktivni == 0:
        cl_score = 5
    elif n_aktivni <= 10:   cl_score = 10
    elif n_aktivni <= 20:   cl_score = 8
    elif n_aktivni <= 35:   cl_score = 5;  alerts.append(f"⚠️ {n_aktivni} aktivnih predmeta — visoko opterećenje")
    else:                   cl_score = 2;  alerts.append(f"🔴 {n_aktivni} aktivnih predmeta — preopterećenost")

    total = dp_score + cs_score + bh_score + ce_score + pr_score + cl_score
    total = max(0, min(100, total))

    return {
        "score":    total,
        "grade":    _grade(total),
        "color":    _grade_color(total),
        "alerts":   alerts[:6],
        "insights": insights[:3],
        "n_aktivni": n_aktivni,
        "n_zatvoreni": len(closed),
        "components": [
            {"label": "Rokovi i ročišta",     "score": dp_score, "max": 20},
            {"label": "Snaga predmeta",        "score": cs_score, "max": 20},
            {"label": "Naplata",               "score": bh_score, "max": 20},
            {"label": "Angažovanost",          "score": ce_score, "max": 15},
            {"label": "Rizik portfolija",      "score": pr_score, "max": 15},
            {"label": "Opterećenost",          "score": cl_score, "max": 10},
        ],
        "_raw": {
            "aktivni": aktivni,
            "closed":  closed,
            "n_roc":   n_roc,
            "mesecna": mesecna,
        }
    }


async def _compute_chief_partner(health: dict, uid: str) -> str:
    """Proaktivna direktiva: 3 konkretne akcije koje bi partner uradio danas."""
    alerts   = health.get("alerts", [])
    score    = health.get("score", 0)
    n_akt    = health.get("n_aktivni", 0)
    n_zat    = health.get("n_zatvoreni", 0)

    kontekst = f"""Zdravlje kancelarije danas: {score}/100 ({health.get('grade','')})
Aktivnih predmeta: {n_akt} | Zatvorenih: {n_zat}
Upozorenja:
""" + "\n".join(f"- {a}" for a in alerts)

    prompt = f"""{kontekst}

Ti si iskusni managing partner advokatske kancelarije sa 25 godina iskustva.
Na osnovu gornjih podataka, generiši TAČNO 3 konkretne akcije koje bi danas preduzeo.

PRAVILA:
- Svaka akcija mora biti konkretna i odmah izvodljiva (ne opšta)
- Piši u prvom licu, kratko i direktno
- Bez uvoda, bez zaključka, bez nabrajanja prednosti
- Ekavica (ne ijekavica)
- Format: samo 3 linije, svaka počinje brojem i tačkom

Primer formata:
1. Kontaktirati Petrovića — 40 dana bez kontakta, predmet na sudu u sredu.
2. Naplatiti 3 stare stavke od Jovanovića pre kraja meseca.
3. Prebaciti predmet Nikolić sa A. na B. — preopterećenost."""

    try:
        resp = await _openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=180,
            temperature=0.5,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error("[ChiefPartner] GPT greška: %s", e)
        return ""


async def _compute_weak_signals(uid: str, supa) -> list[dict]:
    """Otkrij obrasce iz zatvorenih predmeta — minimum 8 predmeta."""
    try:
        closed_r = await asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id,naziv,tip,oblast,status,case_dna,created_at")
            .eq("user_id", uid).eq("status", "zatvoren").execute())
        closed = closed_r.data or []
    except Exception:
        return []

    if len(closed) < 8:
        return []

    signals = []

    # G-031 (D26, VINDEX_OPERATIONAL_GAP_REGISTER.md) — bila je ovde:
    # genome.get("ishod") / genome.get("preporucena_akcija") -- NIJEDNO polje
    # ne postoji u Genome semi (routers/case_dna.py:39-115), pa je 'ishod' UVEK
    # bio "" i signal nikad nije mogao da pogodi. Stvaran ishod (pobeda/poraz/
    # nagodba/odustajanje/odbacena/ostalo) se ne belezi u Genome uopste -- upisan
    # je kao tekst u predmet_hronologija od strane routers/predmeti_close.py::
    # zatvori_predmet ("Predmet zatvoren — Ishod: <label>"). Isti parsing obrazac
    # kao routers/predmeti_close.py::get_predmet_ishod, samo bulk umesto po jednom
    # predmetu (jedan upit za sve zatvorene predmete, ne N+1).
    closed_ids = [p["id"] for p in closed if p.get("id")]
    ishod_po_predmetu: dict = {}
    if closed_ids:
        try:
            # Sortiranje po created_at (TIMESTAMPTZ, insert-redosled), NE po
            # 'datum' -- 'datum' je TEXT polje koje POZIVALAC bira
            # (zatvori_predmet prima 'datum_zatvaranja' kao opcioni parametar),
            # pa nije garantovano monotono sa stvarnim redosledom zatvaranja.
            # Predmet MOŽE biti ponovo otvoren (PATCH /api/predmeti/{id} dozvoljava
            # proizvoljnu promenu 'status', bez provere prelaza) i ponovo zatvoren,
            # sto ostavlja VISE "Predmet zatvoren" zapisa za isti predmet_id --
            # created_at garantovano odrazava koji je zapis STVARNO poslednji.
            hron_r = await asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("predmet_id,dogadjaj,created_at")
                .in_("predmet_id", closed_ids)
                .eq("user_id", uid)
                .ilike("dogadjaj", "Predmet zatvoren%")
                .order("created_at", desc=True)
                .execute())
            for row in (hron_r.data or []):
                pid = row.get("predmet_id")
                dogadjaj = row.get("dogadjaj") or ""
                if pid in ishod_po_predmetu or "Ishod:" not in dogadjaj:
                    continue  # prvi (najnoviji po created_at) pobeđuje
                ishod_po_predmetu[pid] = dogadjaj.split("Ishod:", 1)[1].strip().lower()
        except Exception as exc:
            logger.warning("[HealthIndex] weak_signals ishod upit greška: %s", exc)

    # Labele iz routers/predmeti_close.py::_ISHOD_LABEL, lowercased -- "poraz" i
    # "tužba odbačena" su jedini nedvosmisleno nepovoljni ishodi. Nagodba/
    # odustajanje su namerno izostavljeni (mogu biti strateški dobar potez, ne
    # automatski "loš" ishod).
    _NEPOVOLJNI_ISHODI = {"poraz", "tužba odbačena"}

    # Signal 1: Tip predmeta sa lošim ishodom
    tip_counter: dict = {}
    for p in closed:
        tip = p.get("tip", "opsti")
        ishod = ishod_po_predmetu.get(p.get("id"), "")
        if tip not in tip_counter:
            tip_counter[tip] = {"ukupno": 0, "lose": 0}
        tip_counter[tip]["ukupno"] += 1
        if ishod in _NEPOVOLJNI_ISHODI:
            tip_counter[tip]["lose"] += 1

    for tip, cnt in tip_counter.items():
        if cnt["ukupno"] >= 3 and cnt["lose"] / cnt["ukupno"] >= 0.6:
            pct = int(cnt["lose"] / cnt["ukupno"] * 100)
            signals.append({
                "icon": "📊",
                "tekst": f"U {cnt['lose']} od {cnt['ukupno']} {tip} predmeta ishod je bio nepovoljan ({pct}%) — razmotriti strategiju u ovoj oblasti"
            })

    # Signal 2: Predmeti bez genome analize
    bez_genome = sum(1 for p in closed if not p.get("case_dna"))
    if bez_genome > len(closed) * 0.4:
        signals.append({
            "icon": "💡",
            "tekst": f"{bez_genome} zatvorenih predmeta nema procenu — nema podataka za učenje iz prošlih ishoda"
        })

    # Signal 3: Mesečni trend kreiranja predmeta
    meseci: dict = {}
    for p in closed:
        m = (p.get("created_at") or "")[:7]
        if m: meseci[m] = meseci.get(m, 0) + 1
    if len(meseci) >= 3:
        sorted_m = sorted(meseci.keys())[-3:]
        trend = [meseci[m] for m in sorted_m]
        if trend[-1] > trend[0] * 1.5:
            signals.append({
                "icon": "📈",
                "tekst": f"Broj novih predmeta raste — poslednja 3 meseca: {trend[0]}, {trend[1]}, {trend[2]}. Proverite kapacitet."
            })

    return signals[:4]


async def _compute_inst_risk(uid: str, supa, aktivni: list) -> list[dict]:
    """Institucionalni rizici — koncentracija klijenata i oblasti."""
    risks = []

    # Koncentracija klijenata
    klij_count: dict = {}
    for p in aktivni:
        kid = p.get("klijent_id") or p.get("user_id")
        naziv = p.get("naziv", "")[:30]
        klij_count[naziv] = klij_count.get(naziv, 0) + 1

    if aktivni:
        sorted_klij = sorted(klij_count.items(), key=lambda x: x[1], reverse=True)
        top_pct = sorted_klij[0][1] / len(aktivni) if sorted_klij else 0
        if top_pct > 0.35:
            risks.append({
                "ikona": "⚠️",
                "naslov": "Koncentracija klijenata",
                "opis": f"Jedan klijent/predmet čini {top_pct*100:.0f}% aktivnog portfolija — visoki rizik zavisnosti"
            })

    # Koncentracija oblasti
    oblasti: dict = {}
    for p in aktivni:
        ob = p.get("tip") or p.get("oblast") or "ostalo"
        oblasti[ob] = oblasti.get(ob, 0) + 1
    if aktivni and oblasti:
        top_oblast, top_cnt = max(oblasti.items(), key=lambda x: x[1])
        pct = top_cnt / len(aktivni)
        if pct > 0.5:
            risks.append({
                "ikona": "🎯",
                "naslov": "Specijalizacija",
                "opis": f"{pct*100:.0f}% predmeta je iz oblasti '{top_oblast}' — snažna specijalizacija (prednost i rizik)"
            })

    # Stari predmeti bez aktivnosti
    godinu_dana = (date.today() - timedelta(days=365)).isoformat()
    stari = sum(1 for p in aktivni if (p.get("created_at") or "") < godinu_dana)
    if stari >= 3:
        risks.append({
            "ikona": "🕰️",
            "naslov": "Stari predmeti",
            "opis": f"{stari} predmeta starije od godinu dana — razmotriti zatvaranje ili intenziviranje"
        })

    return risks[:3]


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/api/firm/health-index")
async def get_health_index(
    force: bool = False,
    user=Depends(PermissionService.require("health_index")),
):
    uid = user["user_id"]

    # Cache hit
    cached = _CACHE.get(uid)
    if not force and cached and (datetime.utcnow() - cached["ts"]).total_seconds() < _CACHE_TTL:
        return cached["data"]

    supa = _get_supa()

    health  = await _compute_health(uid, supa)
    raw     = health.pop("_raw", {})
    aktivni = raw.get("aktivni", [])

    chief_partner, signals, risks = await asyncio.gather(
        _compute_chief_partner(health, uid),
        _compute_weak_signals(uid, supa),
        _compute_inst_risk(uid, supa, aktivni),
        return_exceptions=True,
    )

    result = {
        **health,
        "chief_partner":    chief_partner if isinstance(chief_partner, str) else "",
        "weak_signals":     signals       if isinstance(signals,       list) else [],
        "inst_risks":       risks         if isinstance(risks,         list) else [],
        "generated_at":     datetime.utcnow().isoformat(),
    }

    _CACHE[uid] = {"ts": datetime.utcnow(), "data": result}

    await UsageService.consume(uid, user.get("email", ""), "health_index")

    return result
