# -*- coding: utf-8 -*-
"""
Vindex AI — routers/hearing_cc.py
Hearing Command Center (PRO) — Phase: Intelligence

POST /api/rociste/command-center
  Generiše 12-sektorski borbeni brifing za predstojeće ročište.
  Cena: 3 kredita | PRO-only
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from shared.deps import (
    _audit, _deduct_n_credits, _get_supa,
    get_current_user, require_credits, require_pro,
)
from shared.cost import begin_cost_tracking, log_cost_to_db
from shared.rate import limiter

logger = logging.getLogger("vindex.hearing_cc")
router = APIRouter(tags=["hearing_cc"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ─── System prompts ───────────────────────────────────────────────────────────

_SYSTEM_GRADJANSKI = """Ti si elitni parničar sa 30 godina iskustva u srpskim parničnim postupcima.
Pripremaš sveobuhvatan borbeni brifing za predstojeće ročište u parničnom postupku.
Posebno analiziraj: teret dokazivanja (čl. 231 ZPP), procesne rokove, prekluziju dokaza,
koncentracijsko načelo (čl. 307-308 ZPP), te mogućnost presude zbog izostanka.
Odgovori ISKLJUČIVO na srpskom jeziku. Svi argumenti moraju imati osnov u ZPP i materijalnom pravu."""

_SYSTEM_KRIVICNI = """Ti si iskusan krivični branilac/tužilac sa 30 godina iskustva u srpskom krivičnom pravu.
Pripremaš brifing za krivično ročište / glavno pretresanje.
Posebno analiziraj: presumpciju nevinosti, teret dokazivanja tužilaštva, isključenje nezakonito
pribavljenih dokaza (čl. 84 ZKP), pravo na odbranu, zastarelost krivičnog gonjenja.
Odgovori ISKLJUČIVO na srpskom jeziku. Reference na ZKP i KZ Srbije."""

_SYSTEM_UPRAVNI = """Ti si specijalizovani pravnik za upravni postupak i upravni spor u Srbiji.
Pripremaš brifing za ročište pred upravnim sudom ili u upravnom postupku.
Posebno analiziraj: rokove za žalbu i tužbu (čl. 17 ZUSUS), diskreciona ovlašćenja uprave,
načelo zakonitosti, pravo na izjašnjenje (čl. 9 ZUP), razloge poništaja upravnog akta.
Odgovori ISKLJUČIVO na srpskom jeziku. Reference na ZUP, ZUSUS i posebne zakone."""

_SYSTEM_PRIVREDNI = """Ti si iskusni advokat specijalizovan za privrednopravne sporove pred privrednim sudovima u Srbiji.
Pripremaš sveobuhvatan borbeni brifing za predstojeće ročište u privrednom sporu.

SPECIFIKUM PRIVREDNIH SUDOVA:
- Nadležnost: Zakon o uređenju sudova — privredni sudovi sude u sporovima između privrednih subjekata
- Hitnost: privrednopravni sporovi imaju zakonski prioritet i kraće rokove (čl. 467 ZPP)
- Dokazi: poslovne knjige (čl. 55-59 Zakona o računovodstvu), finansijski izveštaji, fakture, izvodi, veštačenje
- ZPD (Zakon o privrednim društvima) — odgovornost direktora, kapital, skupštinska odluka, zastupanje
- ZOSL (Zakon o stečaju) — ako je stranka u stečaju ili likvidaciji, posebni prioriteti potraživanja
- ZOO (Zakon o obligacionim odnosima) — ugovorni osnov, odgovornost, raskid, naknada štete
- ZPP — parničný postupak pred privrednim sudom (iste procesne odredbe, ali hitno)

BRIFING SEKCIJE:
1. Stranke i kapacitet (privredno pravno lice, zastupnik, ovlašćenja, matični br./PIB)
2. Predmet spora (ugovorni osnov, vrednost potraživanja, kamate, troškovi)
3. Ključni dokazi (poslovne knjige, fakture, ugovori, izvodi — šta imamo, šta nedostaje)
4. Pravni osnov (konkretni članovi ZOO, ZPD, posebnih zakona)
5. Taktika na ročištu (procesne primedbe, predlozi za dokaze, veštačenje)
6. Rizici i alternativni ishodi (stečaj stranke, zastara, prigovor prebijanja)
7. Poravnanje vs. nastavak — komercijalna i pravna procena
8. Sledeći koraci i rokovi

Uvek navodi konkretne zakonske odredbe. Budi koncizan i operativan.
Odgovori ISKLJUČIVO na srpskom jeziku."""

_SYSTEM_RADNI = """Ti si specijalizovani pravnik za radne sporove i zaštitu prava radnika u Srbiji.
Pripremaš brifing za ročište u radnom sporu.
Posebno analiziraj: hitnost radnih sporova (čl. 195 ZOR), teret dokazivanja otkaznog razloga
(čl. 127 ZOR), zabranu diskriminacije (ZBD), zaštitu sindikalnih predstavnika, rokove za sudsku zaštitu.
Odgovori ISKLJUČIVO na srpskom jeziku. Reference na ZOR, ZBD i Kolektivne ugovore."""

_SYSTEM_PROMPTS: dict[str, str] = {
    "gradjanski": _SYSTEM_GRADJANSKI,
    "krivicni":   _SYSTEM_KRIVICNI,
    "upravni":    _SYSTEM_UPRAVNI,
    "privredni":  _SYSTEM_PRIVREDNI,
    "privredno":  _SYSTEM_PRIVREDNI,   # alias
    "radni":      _SYSTEM_RADNI,
}

_VALID_TIP = set(_SYSTEM_PROMPTS.keys())

_JSON_SCHEMA = """{
  "executive_brief": "string — sažetak 3-5 rečenica za ročište",
  "timeline": ["string — 'YYYY-MM-DD — opis događaja'"],
  "win_lose_matrix": {"u_prilog": ["string"], "na_stetu": ["string"]},
  "opposing_counsel": "string — strategija protivne strane + kako kontrirati",
  "judge_attack_mode": "string — ključni pravni argumenti + zakonske reference",
  "missing_evidence": ["string — dokaz koji nedostaje"],
  "witness_analysis": "string — analiza svedoka (ko, šta zna, pouzdanost)",
  "cross_examination": ["string — pitanje za unakrsno ispitivanje"],
  "practice_pack": "string — relevantna sudska praksa i analogije",
  "hearing_checklist": ["string — stavka kontrolne liste"],
  "hearing_score": 0,
  "risk_breakdown": {"overall": "NIZAK|SREDNJI|VISOK", "factors": ["string"]}
}"""


# ─── Pydantic ─────────────────────────────────────────────────────────────────

class HearingCCReq(BaseModel):
    predmet_id:    str = Field(..., min_length=1, max_length=64)
    datum_rocista: str = Field(..., min_length=10, max_length=10)
    tip_postupka:  str = Field(..., min_length=1, max_length=20)

    @field_validator("tip_postupka")
    @classmethod
    def _val_tip(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in _VALID_TIP:
            raise ValueError(f"tip_postupka mora biti jedan od: {sorted(_VALID_TIP)}")
        return v

    @field_validator("datum_rocista")
    @classmethod
    def _val_datum(cls, v: str) -> str:
        from datetime import date
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("datum_rocista mora biti YYYY-MM-DD")
        return v


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _first(r) -> Optional[dict]:
    return r.data[0] if r.data else None


async def _load_all_context(supa, uid: str, predmet_id: str) -> dict:
    results = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("*").eq("id", predmet_id).eq("user_id", uid).limit(1).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti")
            .select("klijent_id,klijenti(ime,prezime,firma)")
            .eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("naziv_fajla,created_at").eq("predmet_id", predmet_id)
            .eq("user_id", uid).order("created_at", desc=True).limit(20).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske")
            .select("sadrzaj,created_at").eq("predmet_id", predmet_id)
            .eq("user_id", uid).order("created_at", desc=True).limit(15).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("pitanje,odgovor,created_at").eq("predmet_id", predmet_id)
            .eq("user_id", uid).order("created_at", desc=True).limit(10).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("dogadjaj,datum_iso,vaznost").eq("predmet_id", predmet_id)
            .eq("user_id", uid).order("datum_iso").execute()),
        asyncio.to_thread(lambda: supa.table("predmet_komentari")
            .select("tekst,created_at").eq("predmet_id", predmet_id)
            .eq("user_id", uid).order("created_at", desc=True).limit(10).execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("datum,vreme,sud,status,napomena").eq("predmet_id", predmet_id)
            .eq("user_id", uid).order("datum", desc=True).limit(10).execute()),
        return_exceptions=True,
    )

    def _safe(r):
        if isinstance(r, Exception):
            return []
        return r.data or []

    pred_r = results[0]
    return {
        "predmet":     _first(pred_r) if not isinstance(pred_r, Exception) else None,
        "klijenti":    _safe(results[1]),
        "dokumenti":   _safe(results[2]),
        "beleske":     _safe(results[3]),
        "istorija":    _safe(results[4]),
        "hronologija": _safe(results[5]),
        "komentari":   _safe(results[6]),
        "rocista":     _safe(results[7]),
    }


def _build_prompt(ctx: dict, datum_rocista: str, tip_postupka: str) -> str:
    pred = ctx.get("predmet") or {}
    lines = [
        f"TIP POSTUPKA: {tip_postupka.upper()}",
        f"DATUM ROČIŠTA: {datum_rocista}",
        "",
        f"PREDMET: {pred.get('naziv', '—')}",
        f"Opis: {(pred.get('opis') or '—')[:500]}",
        f"Status: {pred.get('status', '—')} | Rizik: {pred.get('rizik', '—')}",
        f"Tužilac: {pred.get('tuzilac', '—')} | Tuženi: {pred.get('tuzeni', '—')}",
        f"Oblast: {pred.get('oblast', '—')}",
        "",
    ]

    if ctx["klijenti"]:
        lines.append("KLIJENTI:")
        for k in ctx["klijenti"]:
            kl = k.get("klijenti") or {}
            naziv = f"{kl.get('ime','')} {kl.get('prezime','')}".strip() or kl.get("firma", "?")
            lines.append(f"  - {naziv}")

    if ctx["hronologija"]:
        lines.append("\nHRONOLOGIJA DOGAĐAJA:")
        for h in ctx["hronologija"]:
            lines.append(f"  {h.get('datum_iso','?')} — {(h.get('dogadjaj') or '')[:200]} [{h.get('vaznost','')}]")

    if ctx["dokumenti"]:
        lines.append("\nDOKUMENTI:")
        for d in ctx["dokumenti"][:12]:
            lines.append(f"  {d.get('naziv_fajla','?')}")

    if ctx["beleske"]:
        lines.append("\nBELEŠKE:")
        for b in ctx["beleske"][:8]:
            lines.append(f"  {(b.get('created_at') or '')[:10]}: {(b.get('sadrzaj') or '')[:250]}")

    if ctx["rocista"]:
        lines.append("\nPREĐAŠNJA ROČIŠTA:")
        for r in ctx["rocista"]:
            nap = (r.get("napomena") or "")[:100]
            lines.append(f"  {r.get('datum','?')} {r.get('vreme','')} — {r.get('sud','?')} [{r.get('status','?')}]{(' — '+nap) if nap else ''}")

    if ctx["istorija"]:
        lines.append("\nISTORIJA AI UPITA (izvod):")
        for h in ctx["istorija"][:4]:
            lines.append(f"  Q: {(h.get('pitanje') or '')[:150]}")
            lines.append(f"  A: {(h.get('odgovor') or '')[:250]}")

    lines.append(f"\nGeneriši ISKLJUČIVO validan JSON objekat po sledećem šablonu:\n{_JSON_SCHEMA}")
    lines.append("Sve vrednosti moraju biti na srpskom jeziku. hearing_score mora biti integer 0-100.")
    return "\n".join(lines)


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/api/rociste/command-center")
@limiter.limit("10/minute")
async def hearing_command_center(
    body: HearingCCReq,
    request: Request,
    user: dict = Depends(require_pro),
    _cred: dict = Depends(require_credits),
):
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    begin_cost_tracking()

    ctx = await _load_all_context(supa, uid, body.predmet_id)
    if not ctx["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    system_prompt = _SYSTEM_PROMPTS[body.tip_postupka]
    user_prompt   = _build_prompt(ctx, body.datum_rocista, body.tip_postupka)

    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)

    try:
        resp = await oai.chat.completions.create(
            model="gpt-4o",
            temperature=0.1,
            max_tokens=4000,
            timeout=120.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        )
    except Exception as e:
        logger.error("[HCC] OpenAI greška uid=%.8s: %s", uid, e)
        raise HTTPException(status_code=503, detail="AI servis privremeno nedostupan. Pokušajte ponovo.")

    raw = (resp.choices[0].message.content or "{}").strip()
    try:
        brifing = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=503, detail="Neispravan odgovor AI servisa.")

    # require_credits već pre-deductovao 1 atomično — oduzmi samo 2 više
    n_extra = 2 if _cred.get("credit_pre_deducted") else 3
    preostalo = await asyncio.to_thread(_deduct_n_credits, uid, email, n_extra)
    asyncio.create_task(log_cost_to_db(uid, "hearing_command_center"))
    asyncio.create_task(_audit(uid, "hearing_command_center", body.predmet_id[:16]))

    logger.info("[HCC] uid=%.8s predmet=%s tip=%s score=%s",
                uid, body.predmet_id, body.tip_postupka, brifing.get("hearing_score"))

    return {
        "ok":                True,
        "predmet_id":        body.predmet_id,
        "datum_rocista":     body.datum_rocista,
        "tip_postupka":      body.tip_postupka,
        "brifing":           brifing,
        "krediti_preostalo": preostalo,
    }


# ─── Cross-examination generator ─────────────────────────────────────────────

class CrossExamRequest(BaseModel):
    predmet_id:    str = Field(..., min_length=1, max_length=64)
    svedok_opis:   str = Field(..., min_length=5, max_length=1000)
    tema:          str = Field(..., min_length=5, max_length=2000)
    nasa_pozicija: str = Field(..., min_length=3, max_length=500)
    tip_postupka:  str = Field("gradjanski", max_length=20)

    @field_validator("tip_postupka")
    @classmethod
    def _val_tip(cls, v: str) -> str:
        return v.lower().strip()


@router.post("/api/rociste/cross-exam")
@limiter.limit("10/minute")
async def cross_examination(
    body: CrossExamRequest,
    request: Request,
    user: dict = Depends(require_pro),
    _cred: dict = Depends(require_credits),
):
    """Generiše listu pitanja za unakrsno ispitivanje svedoka/veštaka (1 kredit)."""
    uid   = user["user_id"]
    email = user.get("email", "")

    prompt = f"""Si iskusni parničar sa 25 godina iskustva. Pripremaš pitanja za unakrsno ispitivanje svedoka.

TIP POSTUPKA: {body.tip_postupka.upper()}
NAŠA POZICIJA: {body.nasa_pozicija}
SVEDOK (ko je, šta zna, kakva je njegova uloga): {body.svedok_opis}
TEMA SVEDOČENJA (o čemu svedoči, šta tvrdi): {body.tema}

Generiši listu od 15-20 preciznih pitanja za unakrsno ispitivanje ovog svedoka.

## Pitanja za utvrđivanje kredibiliteta svedoka
(Lično poznavanje, pristranost, odnos sa strankom, interes u ishodu)
1. ...

## Pitanja za utvrđivanje činjenica
(Gde je bio, šta je video/čuo/znao, redosled događaja, direktno opažanje vs. zaključak)
1. ...

## Pitanja za slabljenje iskaza
(Kontradikcije sa ranijim izjavama, nemoguće tvrdnje, šta nije video, šta nije znao)
1. ...

## Zaključna pitanja
(Finalna poenta koja potkrepljuje naš narativ)
1. ...

Za svako pitanje koje je "dvostruko sečivo" (može nas povrediti ako svedok odgovori neočekivano) dodaj ⚠️ na kraju.
Sva pitanja moraju biti zatvorena (da/ne) ili precizno usmerena — bez otvorenih pitanja.
Odgovori ISKLJUČIVO na srpskom jeziku."""

    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)

    try:
        resp = await oai.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            max_tokens=2500,
            timeout=60.0,
            messages=[
                {"role": "system", "content": "Ti si elitni parničar koji priprema precizna pitanja za unakrsno ispitivanje. Odgovaraj ISKLJUČIVO na srpskom."},
                {"role": "user",   "content": prompt},
            ],
        )
    except Exception as e:
        logger.error("[CrossExam] OpenAI greška uid=%.8s: %s", uid, e)
        raise HTTPException(status_code=503, detail="AI servis privremeno nedostupan.")

    pitanja = (resp.choices[0].message.content or "").strip()

    preostalo = await asyncio.to_thread(_deduct_n_credits, uid, email, 0 if _cred.get("credit_pre_deducted") else 1)
    asyncio.create_task(_audit(uid, "cross_examination", body.predmet_id[:16]))

    logger.info("[CrossExam] uid=%.8s predmet=%s tip=%s", uid, body.predmet_id, body.tip_postupka)

    return {
        "ok":                True,
        "predmet_id":        body.predmet_id,
        "pitanja":           pitanja,
        "krediti_preostalo": preostalo,
    }


# ─── Brifing export (plain text) ─────────────────────────────────────────────

class BrifingExportReq(BaseModel):
    predmet_naziv:  str = Field("Predmet", max_length=200)
    datum_rocista:  str = Field("", max_length=10)
    tip_postupka:   str = Field("", max_length=20)
    brifing:        dict


@router.post("/api/rociste/command-center/export")
@limiter.limit("20/minute")
async def export_brifing(
    body: BrifingExportReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Konvertuje brifing JSON u plain text za copy/paste ili štampanje."""
    b = body.brifing
    lines = [
        "=" * 65,
        f"ROČIŠNI BRIFING — Vindex AI",
        f"Predmet:      {body.predmet_naziv}",
        f"Datum ročišta: {body.datum_rocista}",
        f"Tip postupka: {body.tip_postupka.upper()}",
        f"Ocena spremi: {b.get('hearing_score', '—')}/100",
        "=" * 65,
        "",
        "## SAŽETAK",
        b.get("executive_brief", "—"),
        "",
    ]

    if b.get("win_lose_matrix"):
        wlm = b["win_lose_matrix"]
        lines += ["## U PRILOG"]
        for item in (wlm.get("u_prilog") or []):
            lines.append(f"  + {item}")
        lines += ["", "## NA ŠTETU"]
        for item in (wlm.get("na_stetu") or []):
            lines.append(f"  - {item}")
        lines.append("")

    if b.get("timeline"):
        lines += ["## HRONOLOGIJA"]
        for t in b["timeline"]:
            lines.append(f"  {t}")
        lines.append("")

    if b.get("opposing_counsel"):
        lines += ["## STRATEGIJA PROTIVNE STRANE", b["opposing_counsel"], ""]

    if b.get("judge_attack_mode"):
        lines += ["## KLJUČNI PRAVNI ARGUMENTI", b["judge_attack_mode"], ""]

    if b.get("witness_analysis"):
        lines += ["## ANALIZA SVEDOKA", b["witness_analysis"], ""]

    if b.get("cross_examination"):
        lines += ["## PITANJA ZA UNAKRSNO ISPITIVANJE"]
        for q in b["cross_examination"]:
            lines.append(f"  ? {q}")
        lines.append("")

    if b.get("missing_evidence"):
        lines += ["## NEDOSTAJUĆI DOKAZI"]
        for e in b["missing_evidence"]:
            lines.append(f"  ! {e}")
        lines.append("")

    if b.get("practice_pack"):
        lines += ["## SUDSKA PRAKSA", b["practice_pack"], ""]

    if b.get("hearing_checklist"):
        lines += ["## KONTROLNA LISTA"]
        for c in b["hearing_checklist"]:
            lines.append(f"  ☐ {c}")
        lines.append("")

    if b.get("risk_breakdown"):
        rb = b["risk_breakdown"]
        lines += [f"## PROCENA RIZIKA: {rb.get('overall', '—')}"]
        for f_ in (rb.get("factors") or []):
            lines.append(f"  • {f_}")
        lines.append("")

    lines += ["=" * 65, "Generisano uz pomoć Vindex AI — za informativne svrhe.", "=" * 65]

    return {"tekst": "\n".join(lines)}
