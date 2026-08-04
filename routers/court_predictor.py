# -*- coding: utf-8 -*-
"""
Vindex AI — routers/court_predictor.py

AI Court Predictor: predviđa ishod sudskog postupka na osnovu
opisa predmeta, sudske prakse i pravnih argumenata.

Endpoints:
  POST /api/predictor/analiza        — predviđanje ishoda + šansa za uspeh
  GET  /api/predictor/faktori        — lista faktora koji utiču na predviđanje
  POST /api/predictor/battle-report  — kompletna strateška analiza pre ročišta
  POST /api/predictor/hearing-prep   — 1-stranični brief za ročište
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService
from shared.sentry import capture_exception as _sentry_capture
from shared.llm_retry import llm_retry

try:
    # CELINA 2 (2026-07-24): koristi javni retrieve_sudska_praksa (Celina 1 mu
    # je dodala Cohere/GPT re-rank prolaz) umesto direktnih niskonivoovskih
    # _pretraga_praksa/_ugradi_query poziva -- ranije je court_predictor.py
    # imao sopstvenu, izolovanu RAG logiku koja NIJE dobijala re-rank
    # poboljšanje niti fail-soft embed guard koje su ostali RAG potrošači
    # (routers/praksa.py, routers/oblasti.py) dobili u Celini 1.
    from app.services.retrieve import retrieve_sudska_praksa
    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False

logger = logging.getLogger("vindex.court_predictor")
router = APIRouter(tags=["court-predictor"])


class PredictorRequest(BaseModel):
    opis_predmeta: str
    tip_postupka: str                          # gradjansko|krivicno|radno|upravno|privredno
    cinjenicni_opis: str
    dokazi: Optional[list[str]] = []
    suprotna_strana_argumenti: Optional[str] = None
    sud: Optional[str] = None
    predmet_id: Optional[str] = None


_PREDICTOR_SYSTEM = """Ti si ekspertni pravni analiticar sa 30 godina iskustva u srpskom pravosudju.
Analiziras pravne predmete i daješ procenu ishoda na osnovu:
- Vazeceg zakonodavstva Republike Srbije
- Sudske prakse srpskih sudova (dostavljena ispod ako je pronadjena)
- Jacine i relevantnosti dokaza
- Procesnih prednosti/nedostataka

STROGO pravilo:
1. Nikad ne garantuj ishod — uvek navedi procenat KAO OPSEG i objasni nesigurnost.
2. Navedi kontra-argumente koje suprotna strana moze koristiti.
3. Preporuci konkretne korake za jacanje pozicije.
4. Ako je dostavljena sudska praksa ispod, oslanjaj se na nju za konkretne primere;
   ako NIJE dostavljena, jasno navedi da je procena bazirana na opštem pravnom znanju.

Odgovori ISKLJUČIVO validnim JSON-om (bez markdown fenci):
{
  "procenat_min": 55,
  "procenat_max": 70,
  "analiza": "Pun tekst analize sa naslovima PROCENA ISHODA / KLJUCNI FAKTORI ZA i PROTIV / PREPORUCENA STRATEGIJA / RIZICI (markdown ** naslovi dozvoljeni unutar ovog stringa)",
  "kljucni_faktori_za": ["faktor 1", "faktor 2"],
  "kljucni_faktori_protiv": ["faktor 1", "faktor 2"],
  "preporucena_strategija": "konkretna preporuka",
  "rizici": ["rizik 1", "rizik 2"]
}

procenat_min/procenat_max: 0-100, min <= max, nikad tacna jedna vrednost bez opsega."""


@llm_retry
def _pozovi_predictor_api(oai_client, user_prompt: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo prediktuj_ishod -- izdvojen jer
    vanjska funkcija ima sopstveni try/except."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _PREDICTOR_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1500,
        temperature=0.3,
        timeout=25.0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or "{}"


def _rag_praksa_blok(query: str, top_k: int) -> str:
    """CELINA 2 (2026-07-24): zajednički helper -- pretražuje sudsku praksu
    preko retrieve_sudska_praksa (Celina 1: Cohere/GPT re-rank) i formatira
    je u tekstualni blok za prompt. Nikad ne baca -- vraća prazan string na
    grešku, pozivalac dodaje napomenu da RAG nije dostupan."""
    if not _RAG_AVAILABLE:
        return ""
    try:
        odluke = retrieve_sudska_praksa(query[:300], top_k)
    except Exception as exc:
        _sentry_capture(exc)
        logger.warning("[PREDICTOR] RAG greška: %s", exc)
        return ""
    if not odluke:
        return ""
    delovi = []
    for m in odluke:
        meta = getattr(m, "metadata", {}) or {}
        court = meta.get("court") or meta.get("sud") or "Sud"
        broj = meta.get("decision_number") or ""
        tekst = (meta.get("text") or meta.get("parent_text") or "").strip()[:400]
        if tekst:
            delovi.append(f"[{court} {broj}] {tekst}")
    return "\n\n".join(delovi)


@router.post("/api/predictor/analiza")
@limiter.limit("10/minute")
async def prediktuj_ishod(
    request: Request,
    payload: PredictorRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """AI predviđanje ishoda sudskog postupka."""
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not payload.opis_predmeta or len(payload.opis_predmeta) < 20:
        raise HTTPException(status_code=400, detail="Opis predmeta je prekratak (minimum 20 karaktera).")

    if payload.tip_postupka not in ["gradjansko", "krivicno", "radno", "upravno", "privredno"]:
        raise HTTPException(status_code=400, detail="Nepoznat tip postupka.")

    dokazi_txt = "\n".join([f"- {d}" for d in payload.dokazi]) if payload.dokazi else "Nisu navedeni"

    # CELINA 2 (2026-07-24): sistemski prompt tvrdi da se analiza bazira na
    # "sudskoj praksi srpskih sudova", ali ranije nijedan poziv nije stvarno
    # pretraživao praksu -- procena je bila isključivo iz opšteg znanja
    # modela. Sada stvarno pretražuje pre nego što tvrdi da je koristila.
    rag_query = f"{payload.tip_postupka} {payload.cinjenicni_opis}"[:600]
    rag_kontekst = await asyncio.to_thread(_rag_praksa_blok, rag_query, 6)

    user_prompt = f"""PREDMET ZA ANALIZU:

Tip postupka: {payload.tip_postupka.upper()}
Sud: {payload.sud or "Nije navedeno"}

OPIS: {payload.opis_predmeta}

CINJENICE:
{payload.cinjenicni_opis}

DOSTUPNI DOKAZI:
{dokazi_txt}

ARGUMENTI SUPROTNE STRANE:
{payload.suprotna_strana_argumenti or "Nisu poznati"}
""" + (
        f"\nRELEVANTNA SUDSKA PRAKSA:\n{rag_kontekst}\n"
        if rag_kontekst else
        "\nNapomena: nije pronađena relevantna sudska praksa u bazi — procena bazirana na opštem pravnom znanju.\n"
    ) + "\nAnaliziraj i daj strukturisano predvidjanje ishoda sa procentom sanse za uspeh."

    try:
        from openai import OpenAI
        from shared.ai_provenance import case_context as _ai_case_ctx
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="prediktuj_ishod"):
            raw = await asyncio.to_thread(_pozovi_predictor_api, oai, user_prompt)
        import json as _json
        rezultat = _json.loads(raw)
        analiza = (rezultat.get("analiza") or "").strip()

        # Sacuvaj analizu
        try:
            await asyncio.to_thread(
                lambda: supa.table("predictor_analize").insert({
                    "user_id":      uid,
                    "predmet_id":   payload.predmet_id,
                    "tip_postupka": payload.tip_postupka,
                    "opis":         payload.opis_predmeta[:500],
                    "analiza":      analiza[:5000],
                }).execute()
            )
            from shared.audit_immutable import log_action
            asyncio.create_task(log_action(
                action="court_predictor_analiza", user_id=uid,
                resource_type="predmet", resource_id=payload.predmet_id,
            ))
        except Exception as _exc:
            _sentry_capture(_exc)
            pass

        preostalo = await UsageService.consume(uid, email, "court_predictor")

        return {
            "analiza":                analiza,
            "procenat_min":           rezultat.get("procenat_min"),
            "procenat_max":           rezultat.get("procenat_max"),
            "kljucni_faktori_za":     rezultat.get("kljucni_faktori_za", []),
            "kljucni_faktori_protiv": rezultat.get("kljucni_faktori_protiv", []),
            "preporucena_strategija": rezultat.get("preporucena_strategija", ""),
            "rizici":                 rezultat.get("rizici", []),
            "rag_dostupan":           bool(rag_kontekst),
            "tip_postupka":           payload.tip_postupka,
            "credits_remaining":      preostalo,
        }

    except HTTPException:
        raise
    except Exception as e:
        _sentry_capture(e)
        logger.error("Court predictor greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri analizi: {str(e)}")


# ── Battle Report ─────────────────────────────────────────────────────────────

class BattleReportRequest(BaseModel):
    predmet_id:      Optional[str]       = None
    tip_postupka:    str
    opis_predmeta:   str
    sud:             Optional[str]       = None
    sudija:          Optional[str]       = None
    protivnicki_adv: Optional[str]       = None
    protivnik_naziv: Optional[str]       = None
    vrednost_spora:  Optional[str]       = None
    dokazi:          Optional[list[str]] = []


_BATTLE_REPORT_SYSTEM = """Ti si ekspertni pravni strateg sa 30 godina iskustva u srpskim sudovima.
Pises BATTLE REPORT — strateski dokument koji advokatu govori sve sto treba da zna pre rocista.

Format UVEK mora biti:

## ANALIZA TUZENE STRANE
[Ko je protivnik, kakva je njihova pravna pozicija, sta znamo o njima]

## ANALIZA SUDA / SUDIJE
[Na osnovu navedenog suda i sudije: tendencije, poznati obrasci odlucivanja. Ako sudija nije naveden — navedi opste karakteristike tog suda.]

## GDE CE NAPADATI
[Konkretne rupe u tvojoj poziciji koje ce protivna strana iskoristiti]

## GDE GRESE
[Slabosti protivnika koje mozes iskoristiti]

## KRITICNI FAKTORI
[2-3 faktora koji ce presuditi ishod]

## PREPORUCENA STRATEGIJA
[Konkretna taktika — ne genericka, nego prilagodjena ovom predmetu]

## RIZIK SCENARIJI
- Optimisticno (X%-Y%): [sta se mora desiti]
- Realisticno (X%-Y%): [najverovatniji ishod]
- Pesimisticno (X%-Y%): [sta moze poci naopako]

Ako je dostavljena SUDSKA PRAKSA ispod, oslanjaj se na konkretne odluke u
sekciji ANALIZA SUDA / SUDIJE i KRITICNI FAKTORI; ako nije dostavljena, jasno
navedi da je ta sekcija bazirana na opštem znanju, ne na konkretnoj praksi.

Ekavica. Direktan ton. Bez uvoda i zakljucka — samo analiza."""


@llm_retry
def _pozovi_battle_report_api(oai_client, user_prompt: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo battle_report -- izdvojen jer
    vanjska funkcija ima sopstveni try/except."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _BATTLE_REPORT_SYSTEM},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=2000,
        temperature=0.3,
        timeout=25.0,
    )
    return resp.choices[0].message.content.strip()


@router.post("/api/predictor/battle-report")
@limiter.limit("10/minute")
async def battle_report(
    request: Request,
    payload: BattleReportRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Battle Report: kompletna strateška analiza pre ročišta.
    Analizira sudiju, protivnika, slabosti i strategiju.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not payload.opis_predmeta or len(payload.opis_predmeta) < 30:
        raise HTTPException(status_code=400, detail="Opis predmeta je prekratak.")

    if payload.tip_postupka not in ["gradjansko", "krivicno", "radno", "upravno", "privredno"]:
        raise HTTPException(status_code=400, detail="Nepoznat tip postupka.")

    dokazi_txt = "\n".join([f"- {d}" for d in payload.dokazi]) if payload.dokazi else "Nisu navedeni"

    # CELINA 2 (2026-07-24): ista popravka kao prediktuj_ishod -- Battle
    # Report obećava analizu suda/sudije "na osnovu poznatih obrazaca", ali
    # ranije nikad nije pretraživao sudsku praksu.
    rag_query = f"{payload.tip_postupka} {payload.sud or ''} {payload.sudija or ''} {payload.opis_predmeta}"[:600]
    rag_kontekst = await asyncio.to_thread(_rag_praksa_blok, rag_query, 6)

    user_prompt = f"""BATTLE REPORT — PRIPREMA ZA POSTUPAK

Tip postupka: {payload.tip_postupka.upper()}
Sud: {payload.sud or "Nije naveden"}
Sudija: {payload.sudija or "Nije poznat"}
Protivnicka strana: {payload.protivnik_naziv or "Nije navedena"}
Protivnicka advokatska kancelarija: {payload.protivnicki_adv or "Nije poznata"}
Vrednost spora: {payload.vrednost_spora or "Nije navedena"}

OPIS PREDMETA:
{payload.opis_predmeta}

DOSTUPNI DOKAZI:
{dokazi_txt}
""" + (
        f"\nSUDSKA PRAKSA:\n{rag_kontekst}\n" if rag_kontekst else
        "\nNapomena: nije pronađena relevantna sudska praksa u bazi.\n"
    ) + "\nNapravi kompletan Battle Report."

    try:
        from openai import OpenAI
        from shared.ai_provenance import case_context as _ai_case_ctx
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="battle_report"):
            report = await asyncio.to_thread(_pozovi_battle_report_api, oai, user_prompt)

        try:
            await asyncio.to_thread(
                lambda: supa.table("predictor_analize").insert({
                    "user_id":      uid,
                    "predmet_id":   payload.predmet_id,
                    "tip_postupka": payload.tip_postupka,
                    "opis":         payload.opis_predmeta[:500],
                    "analiza":      report[:8000],
                    "tip_analize":  "battle_report",
                }).execute()
            )
            from shared.audit_immutable import log_action
            asyncio.create_task(log_action(
                action="court_predictor_analiza", user_id=uid,
                resource_type="predmet", resource_id=payload.predmet_id,
            ))
        except Exception as _exc:
            _sentry_capture(_exc)
            pass

        preostalo = await UsageService.consume(uid, email, "court_predictor")

        return {
            "battle_report":      report,
            "tip_postupka":       payload.tip_postupka,
            "sud":                payload.sud,
            "rag_dostupan":       bool(rag_kontekst),
            "credits_remaining":  preostalo,
        }

    except HTTPException:
        raise
    except Exception as e:
        _sentry_capture(e)
        logger.error("Battle report greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri generisanju: {str(e)}")


# ── Hearing Prep Auto-Brief ────────────────────────────────────────────────────

class HearingPrepRequest(BaseModel):
    predmet_id:         Optional[str] = None
    rociste_naziv:      str
    datum_rocista:      str
    tip_postupka:       str
    opis_predmeta:      str
    poslednji_podnesak: Optional[str] = None


_HEARING_PREP_SYSTEM = """Ti si iskusni pravni asistent koji priprema advokata za rociste.
Pises 1-stranicki briefing koji advokat moze da procita za 5 minuta pre ulaska u sudnicu.

Format:
## STA OCEKIVATI DANAS
[Kratko — sta ce se verovatno desiti na ovom rocistu]

## KLJUCNI ARGUMENTI (za poneti sa sobom)
[3-5 najvaznijih argumenata, s referencama na dokaze]

## MOGUCA PITANJA SUDA
[2-3 pitanja koja sudija moze postaviti i predlozeni odgovori]

## AKO PROTIVNA STRANA KAZE...
[1-2 verovatna napada i kako odgovoriti]

## NE ZABORAVI
[Dokumenta, potvrde, overene kopije koje treba poneti]

Koncizan, direktan, praktican. Ekavica."""


@llm_retry
def _pozovi_hearing_prep_api(oai_client, user_msg: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo hearing_prep_brief."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _HEARING_PREP_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=1000,
        temperature=0.4,
        timeout=25.0,
    )
    return resp.choices[0].message.content.strip()


@router.post("/api/predictor/hearing-prep")
@limiter.limit("20/minute")
async def hearing_prep_brief(
    request: Request,
    payload: HearingPrepRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Auto-brief za ročište — 1 stranica, sve što treba znati pre ulaska u sudnicu.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not payload.opis_predmeta or len(payload.opis_predmeta) < 20:
        raise HTTPException(status_code=400, detail="Opis predmeta je prekratak.")

    podnesak_txt = (
        f"\nPoslednji podnesak / belezka:\n{payload.poslednji_podnesak[:1000]}"
        if payload.poslednji_podnesak else ""
    )

    user_msg = f"""PRIPREMA ZA ROCISTE: {payload.rociste_naziv}
Datum: {payload.datum_rocista}
Tip: {payload.tip_postupka}

{payload.opis_predmeta}{podnesak_txt}"""

    try:
        from openai import OpenAI
        from shared.ai_provenance import case_context as _ai_case_ctx
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="hearing_prep"):
            brief = await asyncio.to_thread(_pozovi_hearing_prep_api, oai, user_msg)

        if payload.predmet_id:
            try:
                await asyncio.to_thread(
                    lambda: supa.table("hearing_briefovi").insert({
                        "user_id":       uid,
                        "predmet_id":    payload.predmet_id,
                        "rociste_naziv": payload.rociste_naziv,
                        "datum":         payload.datum_rocista,
                        "brief":         brief[:5000],
                    }).execute()
                )
                from shared.audit_immutable import log_action
                asyncio.create_task(log_action(
                    action="court_predictor_analiza", user_id=uid,
                    resource_type="predmet", resource_id=payload.predmet_id,
                ))
            except Exception as _exc:
                _sentry_capture(_exc)
                pass

        preostalo = await UsageService.consume(uid, email, "court_predictor")

        return {
            "brief":              brief,
            "rociste_naziv":      payload.rociste_naziv,
            "datum_rocista":      payload.datum_rocista,
            "credits_remaining":  preostalo,
        }

    except HTTPException:
        raise
    except Exception as e:
        _sentry_capture(e)
        logger.error("Hearing prep greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri generisanju: {str(e)}")


# ── Faktori ───────────────────────────────────────────────────────────────────

@router.get("/api/predictor/faktori")
async def get_faktori(user: dict = Depends(get_current_user)):
    """Lista faktora koji utiču na ishod po tipu postupka."""
    return {
        "faktori": {
            "gradjansko": [
                "Jacina pisanih dokaza (ugovori, priznanice)",
                "Svedoci i njihova verodostojnost",
                "Zastarelost potrazivanja",
                "Teret dokazivanja",
                "Sudska praksa u slicnim slucajevima",
            ],
            "krivicno": [
                "Alibi optuzenog",
                "Verodostojnost svedoka",
                "Materijalni dokazi i lanac staranja",
                "Vestacenja (sudski vestaci)",
                "Prethodne osude",
            ],
            "radno": [
                "Pismeni otkazni akt i procedure",
                "Evidencija o radu i ucinku",
                "Kolektivni ugovor i pravilnik",
                "Rok za osporavanje otkaza",
                "Diskriminatorski osnov",
            ],
            "upravno": [
                "Zakonitost upravnog akta",
                "Postovanje procedure donosenja",
                "Obrazlozenost odluke",
                "Rok za zalbu",
                "Nadleznost organa",
            ],
            "privredno": [
                "Ugovorna dokumentacija",
                "Finansijski izvestaji i vestak",
                "Registracioni podaci privrednog subjekta",
                "Likvidnost tuzene strane",
                "Medjunarodna arbitraza (ako postoji klauzula)",
            ],
        }
    }


# ── Argument Reputation Engine ────────────────────────────────────────────────

class ArgumentReputationRequest(BaseModel):
    tip_spora: str
    argumenti: list[str]
    sud: Optional[str] = None
    predmet_id: Optional[str] = None


_ARG_REPUTATION_SYSTEM = """Ti si srpski pravni analitičar sa pristupom sudskoj praksi.
Analiziraš argumente koje advokat planira da koristi u postupku i procenjuješ njihovu uspešnost
na osnovu dostavljenih odluka sudova.

Odgovori SAMO validnim JSON-om:
{
  "argumenti_analiza": [
    {
      "argument": "tekst argumenta",
      "uspesnost_procena": 72,
      "boja": "zelena",
      "obrazlozenje": "U 70%+ relevantnih odluka sudovi su prihvatali ovaj tip argumenta...",
      "preporuka": "Konkretan savet kako da se pojača ovaj argument",
      "relevantne_odluke": 5
    }
  ],
  "ukupna_snaga": 68,
  "slabosti": ["Argument X je slabo potkrepljen praksom..."],
  "preporuceni_redosled": ["argument najjači", "argument srednji"],
  "alternativni_argumenti": ["Razmotrite dodavanje argumenta o..."]
}

Pravila:
- uspesnost_procena 0-100 (0=nikad ne prolazi, 100=uvek prolazi)
- boja: "zelena" ako >=65, "žuta" ako 35-64, "crvena" ako <35
- Ekavica strogo. Nema ijekavice.
- Budi konkretan, ne generički."""


@llm_retry
def _pozovi_arg_reputation_api(oai_client, user_msg: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo argument_reputation."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _ARG_REPUTATION_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=2000,
        temperature=0.25,
        timeout=25.0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or "{}"


@router.post("/api/predictor/argument-reputation")
@limiter.limit("5/minute")
async def argument_reputation(
    request: Request,
    payload: ArgumentReputationRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Argument Reputation Engine — procenjuje uspešnost argumenata na osnovu 54k+ srpskih odluka.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not payload.argumenti:
        raise HTTPException(status_code=400, detail="Morate navesti najmanje jedan argument.")
    if len(payload.argumenti) > 10:
        raise HTTPException(status_code=400, detail="Maksimalno 10 argumenata po zahtevu.")

    # RAG pretraga za svaki argument
    rag_kontekst = ""
    if _RAG_AVAILABLE:
        try:
            rag_delovi = []
            for arg in payload.argumenti[:5]:
                query = f"{payload.tip_spora} {arg} {payload.sud or ''}"
                odluke = await asyncio.to_thread(retrieve_sudska_praksa, query.strip()[:300], 4)
                if odluke:
                    tekstovi = []
                    for m in odluke:
                        meta = getattr(m, "metadata", {}) or {}
                        court = meta.get("court") or meta.get("sud") or "Sud"
                        # CELINA 2 (2026-07-24) bug fix: metadata ključ je "text"
                        # (i "parent_text" kao fallback), ne "tekst" -- pinecone
                        # match objekti takodje nemaju .page_content (to je
                        # LangChain Document konvencija, ne Pinecone SDK). Ova
                        # tri poziva su ranije UVEK slala prazan tekst modelu.
                        tekst = (meta.get("text") or meta.get("parent_text") or "")[:400]
                        tekstovi.append(f"[{court}] {tekst}")
                    rag_delovi.append(
                        f"ARGUMENT: {arg}\nODLUKE ({len(odluke)}):\n" + "\n".join(tekstovi)
                    )
            rag_kontekst = "\n\n".join(rag_delovi)
        except Exception as e:
            _sentry_capture(e)
            logger.warning("[ARG_REP] RAG greška: %s", e)

    pouzdanost_napomena = "" if rag_kontekst else "\nNapomena: RAG nije dostupan — analiza bazirana samo na znanju modela."

    user_msg = (
        f"Tip spora: {payload.tip_spora}\n"
        f"Sud: {payload.sud or 'nije naveden'}\n\n"
        f"ARGUMENTI ZA ANALIZU:\n" +
        "\n".join(f"- {a}" for a in payload.argumenti) +
        (f"\n\nRELEVANTNA SUDSKA PRAKSA:\n{rag_kontekst}" if rag_kontekst else "") +
        pouzdanost_napomena
    )

    from openai import OpenAI
    from shared.ai_provenance import case_context as _ai_case_ctx
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        import json
        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="argument_reputation"):
            raw = await asyncio.to_thread(_pozovi_arg_reputation_api, oai, user_msg)
        rezultat = json.loads(raw)
    except Exception as e:
        _sentry_capture(e)
        logger.error("[ARG_REP] GPT greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri analizi: {str(e)}")

    try:
        await asyncio.to_thread(
            lambda: supa.table("predictor_analize").insert({
                "user_id":      uid,
                "predmet_id":   payload.predmet_id,
                "tip_postupka": payload.tip_spora,
                "opis":         "; ".join(payload.argumenti)[:500],
                "analiza":      json.dumps(rezultat, ensure_ascii=False)[:8000],
                "tip_analize":  "argument_reputation",
            }).execute()
        )
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="court_predictor_analiza", user_id=uid,
            resource_type="predmet", resource_id=payload.predmet_id,
        ))
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    preostalo = await UsageService.consume(uid, email, "court_predictor")

    return {
        **rezultat,
        "tip_spora":         payload.tip_spora,
        "rag_dostupan":      _RAG_AVAILABLE and bool(rag_kontekst),
        "credits_remaining": preostalo,
    }


# ── Judge Intelligence Profiler ───────────────────────────────────────────────

class JudgeProfileRequest(BaseModel):
    ime_sudije: Optional[str] = None
    sud: str
    tip_postupka: str
    predmet_id: Optional[str] = None


_JUDGE_PROFILE_SYSTEM = """Ti si srpski pravni analitičar koji profilira sudije i sudove
na osnovu sudske prakse. Cilj je da advokatu pomogneš da razumeš sa kim ima posla.

Odgovori SAMO validnim JSON-om:
{
  "sud": "naziv suda",
  "sudija": "ime sudije ili 'nije naveden'",
  "ukupno_odluka_analizirano": 12,
  "profil": {
    "tendencije": ["Sklon detaljnoj analizi pisanih dokaza", "Brzo odbacuje procesne prigovore"],
    "prosecno_trajanje_meseci": 14,
    "stopa_potvrdjivanja_zalbi": 35,
    "preferirani_argumenti": ["pisani dokazi", "ekspertska mišljenja"],
    "faktori_koje_ceni": ["uredna procesna dokumentacija", "jasna hronologija događaja"],
    "cega_se_kloniti": ["nejasni podnesci", "nedostatak pisanih dokaza"]
  },
  "strateska_preporuka": "Konkretna taktika prilagođena ovom sudu/sudiji",
  "pouzdanost_profila": "srednja",
  "upozorenje": "Profil baziran na sudskoj praksi, ne na ličnim podacima o sudiji."
}

- pouzdanost_profila: 'visoka' (10+ odluka), 'srednja' (5-9), 'niska' (<5 ili nema RAG)
- Ekavica strogo. Nema ijekavice."""


@llm_retry
def _pozovi_judge_profile_api(oai_client, user_msg: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo judge_profile."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _JUDGE_PROFILE_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=1500,
        temperature=0.2,
        timeout=25.0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or "{}"


@router.post("/api/predictor/judge-profile")
@limiter.limit("5/minute")
async def judge_profile(
    request: Request,
    payload: JudgeProfileRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Judge Intelligence Profiler — analiza suda/sudije iz 54k+ srpskih odluka.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    rag_kontekst = ""
    odluke_count = 0
    if _RAG_AVAILABLE:
        try:
            query = f"{payload.sud} {payload.ime_sudije or ''} {payload.tip_postupka} odluka presuda".strip()
            odluke = await asyncio.to_thread(retrieve_sudska_praksa, query[:300], 15)
            odluke_count = len(odluke)
            if odluke:
                delovi = []
                for m in odluke:
                    meta = getattr(m, "metadata", {}) or {}
                    court = meta.get("court") or meta.get("sud") or payload.sud
                    tekst = (meta.get("text") or meta.get("parent_text") or "")[:500]
                    delovi.append(f"[{court}] {tekst}")
                rag_kontekst = "\n\n".join(delovi)
        except Exception as e:
            _sentry_capture(e)
            logger.warning("[JUDGE_PROF] RAG greška: %s", e)

    user_msg = (
        f"Sud: {payload.sud}\n"
        f"Sudija: {payload.ime_sudije or 'nije naveden'}\n"
        f"Tip postupka: {payload.tip_postupka}\n"
        f"Broj analiziranih odluka: {odluke_count}\n" +
        (f"\nRELEVANTNA PRAKSA:\n{rag_kontekst}" if rag_kontekst else
         "\nNapomena: RAG nije dostupan — analiza bazirana na opštem znanju o srpskim sudovima.")
    )

    from openai import OpenAI
    import json
    from shared.ai_provenance import case_context as _ai_case_ctx
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="judge_profile"):
            raw = await asyncio.to_thread(_pozovi_judge_profile_api, oai, user_msg)
        rezultat = json.loads(raw)
        rezultat["ukupno_odluka_analizirano"] = odluke_count
        if not _RAG_AVAILABLE or odluke_count < 5:
            rezultat["pouzdanost_profila"] = "niska"
        elif odluke_count >= 10:
            rezultat["pouzdanost_profila"] = "visoka"
    except Exception as e:
        _sentry_capture(e)
        logger.error("[JUDGE_PROF] GPT greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri profilisanju: {str(e)}")

    try:
        await asyncio.to_thread(
            lambda: supa.table("predictor_analize").insert({
                "user_id":      uid,
                "predmet_id":   payload.predmet_id,
                "tip_postupka": payload.tip_postupka,
                "opis":         f"Sud: {payload.sud} | Sudija: {payload.ime_sudije or 'N/A'}",
                "analiza":      json.dumps(rezultat, ensure_ascii=False)[:8000],
                "tip_analize":  "judge_profile",
            }).execute()
        )
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="court_predictor_analiza", user_id=uid,
            resource_type="predmet", resource_id=payload.predmet_id,
        ))
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    preostalo = await UsageService.consume(uid, email, "court_predictor")

    return {
        **rezultat,
        "credits_remaining": preostalo,
    }


# ── Opponent Intelligence ─────────────────────────────────────────────────────

class OpponentIntelRequest(BaseModel):
    protivnik_naziv: str
    protivnicki_adv: Optional[str] = None
    tip_postupka: str
    predmet_id: Optional[str] = None
    poznate_informacije: Optional[str] = None


_OPPONENT_INTEL_SYSTEM = """Ti si špijun-strateg koji prikuplja obaveštajne podatke o protivnoj strani u sudskom postupku.
Cilj je da advokatu pružiš sve što treba da zna o protivniku PRE nego što uđe u sudnicu.

Odgovori SAMO validnim JSON-om:
{
  "protivnik": "naziv protivnika",
  "advokatska_kancelarija": "naziv kancelarije ili 'nije naveden'",
  "analiza": {
    "poznati_stil": "Opis stila vođenja postupka na osnovu dostupnih podataka...",
    "taktike": ["Taktika 1", "Taktika 2"],
    "stopa_nagodbi": "nepoznato",
    "slabosti": ["Slabost 1", "Slabost 2"],
    "snage": ["Snaga 1", "Snaga 2"]
  },
  "preporucena_taktika": "Konkretna taktika za ovog protivnika",
  "upozorenja": ["Upozorenje 1", "Upozorenje 2"],
  "pouzdanost": "niska"
}

- stopa_nagodbi: "visoka" | "niska" | "nepoznato"
- pouzdanost: "visoka" (puno podataka) | "srednja" | "niska" (malo ili nimalo podataka)
- Ekavica strogo. Nema ijekavice.
- Budi direktan i konkretan, ne generički."""


@llm_retry
def _pozovi_opponent_intel_api(oai_client, user_msg: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo opponent_intel."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _OPPONENT_INTEL_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=1500,
        temperature=0.3,
        timeout=25.0,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or "{}"


@router.post("/api/predictor/opponent-intel")
@limiter.limit("5/minute")
async def opponent_intel(
    request: Request,
    payload: OpponentIntelRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Opponent Intelligence — analiza protivne strane iz sudske prakse i internog CRM-a.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    # Interna istorija sa ovim protivnikom
    interni_kontekst = ""
    try:
        hist_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("naziv, status, opis")
                .eq("user_id", uid)
                .ilike("opis", f"%{payload.protivnik_naziv[:30]}%")
                .limit(5)
                .execute()
        )
        if hist_r.data:
            interni_kontekst = "INTERNI PREDMETI SA OVIM PROTIVNIKOM:\n" + "\n".join(
                f"- {p.get('naziv','?')} [{p.get('status','?')}]: {(p.get('opis') or '')[:150]}"
                for p in hist_r.data
            )
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    # RAG pretraga
    rag_kontekst = ""
    if _RAG_AVAILABLE:
        try:
            query = f"{payload.protivnik_naziv} {payload.protivnicki_adv or ''} {payload.tip_postupka}".strip()
            odluke = await asyncio.to_thread(retrieve_sudska_praksa, query[:300], 8)
            if odluke:
                delovi = []
                for m in odluke:
                    meta = getattr(m, "metadata", {}) or {}
                    court = meta.get("court") or meta.get("sud") or "Sud"
                    tekst = (meta.get("text") or meta.get("parent_text") or "")[:400]
                    delovi.append(f"[{court}] {tekst}")
                rag_kontekst = "RELEVANTNA SUDSKA PRAKSA:\n" + "\n\n".join(delovi)
        except Exception as e:
            _sentry_capture(e)
            logger.warning("[OPP_INTEL] RAG greška: %s", e)

    user_msg = (
        f"Protivnik: {payload.protivnik_naziv}\n"
        f"Advokatska kancelarija: {payload.protivnicki_adv or 'nije navedena'}\n"
        f"Tip postupka: {payload.tip_postupka}\n"
        + (f"\nPoznate informacije: {payload.poznate_informacije[:500]}\n"
           if payload.poznate_informacije else "")
        + (f"\n{interni_kontekst}\n" if interni_kontekst else "")
        + (f"\n{rag_kontekst}" if rag_kontekst else
           "\nNapomena: Nema dostupnih podataka iz sudske prakse — analiza bazirana na opštem znanju.")
    )

    from openai import OpenAI
    import json
    from shared.ai_provenance import case_context as _ai_case_ctx
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="opponent_intel"):
            raw = await asyncio.to_thread(_pozovi_opponent_intel_api, oai, user_msg)
        rezultat = json.loads(raw)
        if not rag_kontekst and not interni_kontekst:
            rezultat["pouzdanost"] = "niska"
    except Exception as e:
        _sentry_capture(e)
        logger.error("[OPP_INTEL] GPT greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri analizi protivnika: {str(e)}")

    try:
        await asyncio.to_thread(
            lambda: supa.table("predictor_analize").insert({
                "user_id":      uid,
                "predmet_id":   payload.predmet_id,
                "tip_postupka": payload.tip_postupka,
                "opis":         f"Protivnik: {payload.protivnik_naziv} | Adv: {payload.protivnicki_adv or 'N/A'}",
                "analiza":      json.dumps(rezultat, ensure_ascii=False)[:8000],
                "tip_analize":  "opponent_intel",
            }).execute()
        )
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="court_predictor_analiza", user_id=uid,
            resource_type="predmet", resource_id=payload.predmet_id,
        ))
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    preostalo = await UsageService.consume(uid, email, "court_predictor")

    return {
        **rezultat,
        "ima_internih_predmeta": bool(interni_kontekst),
        "rag_dostupan":          _RAG_AVAILABLE and bool(rag_kontekst),
        "credits_remaining":     preostalo,
    }


# ── Confidence Calibration ────────────────────────────────────────────────────

class ConfidenceCheckRequest(BaseModel):
    tip_spora: str  # "radno"|"parnicno"|"krivicno"|"upravno"|"privredno"
    opis_predmeta: str
    sud: Optional[str] = None
    predmet_id: Optional[str] = None
    dokazi: Optional[list[str]] = []


_CONFIDENCE_MAX_SCORE = 9  # 3 (rag) + 3 (vks) + 2 (kancelarija) + 1 (dokazi)


def _procenat_iz_score(score: int) -> int:
    """Program Alpha (2026-08-04): deterministički izvodi procenat poverenja
    iz istog `score`-a koji već odredjuje `nivo`, umesto da drugi, nezavisan
    GPT poziv nagadja sopstveni broj. Pre ovoga, `nivo` i `procenat` su bila
    DVA autora jedne percipirane vrednosti (Critical po Program Alpha's
    sopstvenom pravilu "dva autora istog podatka") -- ništa nije sprečavalo
    nivo="NISKO" da se prikaže pored procenat=78. Opseg 20-80% namerno nikad
    ne tvrdi apsolutnu (0% ili 100%) sigurnost."""
    score = max(0, min(_CONFIDENCE_MAX_SCORE, score))
    return 20 + round((score / _CONFIDENCE_MAX_SCORE) * 60)


def _calc_confidence_nivo(
    rag_hits: int,
    vks_hits: int,
    kancelarija_data: Optional[dict],
    dokazi_count: int,
) -> tuple[str, str, list[str], list[str], int]:
    """Vraća (nivo, boja, faktori_plus, faktori_minus, score)."""
    score = 0
    faktori_plus: list[str] = []
    faktori_minus: list[str] = []

    if rag_hits >= 15:
        score += 3
        faktori_plus.append(f"{rag_hits} sličnih predmeta u sudskoj praksi")
    elif rag_hits >= 5:
        score += 2
        faktori_plus.append(f"{rag_hits} sličnih predmeta u sudskoj praksi")
    else:
        faktori_minus.append(f"Svega {rag_hits} sličnih predmeta — ograničena referentna baza")

    if vks_hits >= 5:
        score += 3
        faktori_plus.append(f"{vks_hits} presuda Vrhovnog kasacionog suda")
    elif vks_hits >= 2:
        score += 1
        faktori_plus.append(f"{vks_hits} presuda Vrhovnog kasacionog suda")
    else:
        faktori_minus.append("Nema direktnih presuda VKS na ovu temu")

    if kancelarija_data:
        uzoraka = kancelarija_data.get("uzoraka", 0)
        wr = kancelarija_data.get("win_rate", 0)
        if uzoraka >= 5:
            score += 2
            faktori_plus.append(f"Kancelarija: {uzoraka} predmeta, win rate {wr}%")
        elif uzoraka > 0:
            score += 1
            faktori_plus.append(f"Kancelarija: {uzoraka} prethodnih predmeta")
        else:
            faktori_minus.append("Nema istorijata ove firme za ovaj tip spora")
    else:
        faktori_minus.append("Nema istorijata ove firme za ovaj tip spora")

    if dokazi_count >= 4:
        score += 1
        faktori_plus.append(f"Dobro dokumentovan predmet ({dokazi_count} dokaza)")
    elif dokazi_count == 0:
        faktori_minus.append("Dokazi nisu navedeni — nepotpuna analiza")

    if score >= 7:
        return "VISOKO", "zelena", faktori_plus, faktori_minus, score
    elif score >= 4:
        return "SREDNJE", "žuta", faktori_plus, faktori_minus, score
    else:
        return "NISKO", "crvena", faktori_plus, faktori_minus, score


@llm_retry
def _pozovi_confidence_api(oai_client, gpt_prompt: str) -> str:
    """CELINA 2 (2026-07-24): retry-ovani deo confidence_check."""
    resp = oai_client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=150,
        timeout=25.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Ti si srpski pravni analitičar. Odgovaraj SAMO validnim JSON-om. Ekavica."},
            {"role": "user",   "content": gpt_prompt},
        ],
    )
    return resp.choices[0].message.content or "{}"


@router.post("/api/predictor/confidence-check")
@limiter.limit("10/minute")
async def confidence_check(
    request: Request,
    payload: ConfidenceCheckRequest,
    user: dict = Depends(PermissionService.require("court_predictor")),
):
    """
    Confidence Calibration — ne vraća samo procenat nego strukturirani dokaz:
    VISOKO POVERENJE: 194 slična predmeta, 17 VKS presuda, win rate 73%.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not payload.opis_predmeta or len(payload.opis_predmeta) < 20:
        raise HTTPException(status_code=400, detail="Opis predmeta je prekratak.")

    if payload.tip_spora not in ("radno", "parnicno", "krivicno", "upravno", "privredno"):
        raise HTTPException(status_code=400, detail="Nepoznat tip spora.")

    # Korak 1: RAG pretraga sličnih odluka
    rag_hits = 0
    vks_hits = 0
    if _RAG_AVAILABLE:
        try:
            hits = await asyncio.to_thread(retrieve_sudska_praksa, payload.opis_predmeta[:600], 20)
            rag_hits = len(hits)
            vks_hits = sum(
                1 for h in hits
                if "Vrhovni kasacioni" in str(getattr(h, "metadata", {}).get("court", ""))
                or "VKS" in str(getattr(h, "metadata", {}).get("court", ""))
            )
        except Exception as e:
            _sentry_capture(e)
            logger.debug("[CONFIDENCE] RAG greška: %s", e)

    # Korak 2: Firmini podaci iz case_patterns
    kancelarija_data: Optional[dict] = None
    try:
        patterns_r = await asyncio.to_thread(
            lambda: supa.table("case_patterns")
                .select("faktor,pobede,porazi,uzoraka")
                .eq("user_id", uid)
                .eq("tip_spora", payload.tip_spora)
                .order("uzoraka", desc=True)
                .limit(10)
                .execute()
        )
        rows = patterns_r.data or []
        if rows:
            total = sum((r.get("pobede", 0) + r.get("porazi", 0)) for r in rows)
            wins  = sum(r.get("pobede", 0) for r in rows)
            kancelarija_data = {
                "uzoraka":    total,
                "win_rate":   round(wins / max(1, total) * 100, 1),
                "top_faktor": rows[0].get("faktor") if rows else None,
            }
    except Exception as e:
        _sentry_capture(e)
        logger.debug("[CONFIDENCE] case_patterns greška: %s", e)

    # Korak 3: Nivo pouzdanosti + deterministički procenat izveden IZ ISTOG
    # score-a (Program Alpha, 2026-08-04) -- ranije je "procenat" bio drugi,
    # nezavisan autor iste percipirane vrednosti (vidi _procenat_iz_score).
    nivo, boja, faktori_plus, faktori_minus, _confidence_score = _calc_confidence_nivo(
        rag_hits, vks_hits, kancelarija_data, len(payload.dokazi or [])
    )
    procenat = _procenat_iz_score(_confidence_score)

    # Korak 4: GPT-4o-mini — SAMO kratko obrazloženje/rizik, NIKAD procenat
    # (taj broj je sada isključivo deterministički, iznad).
    razlog     = ""
    kljucni_rizik = ""
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        dokazi_txt = ", ".join(payload.dokazi[:5]) if payload.dokazi else "nisu navedeni"
        gpt_prompt = (
            f"Predmet ({payload.tip_spora}), procenjeni nivo poverenja: {nivo}.\n\n"
            f"{payload.opis_predmeta[:800]}\n\n"
            f"Dokazi: {dokazi_txt}\n"
            f"Sud: {payload.sud or 'nije naveden'}\n\n"
            'Odgovori SAMO JSON-om: {"razlog_kratko": "...", "kljucni_rizik": "..."}\n'
            "Ekavica. Max 30 reči za razlog. NE navodi procenat ni broj — samo kratko obrazloženje i ključni rizik."
        )
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(predmet_id=payload.predmet_id, module_name="court_predictor", operation_name="confidence_check"):
            raw = await asyncio.to_thread(_pozovi_confidence_api, oai, gpt_prompt)
        import json as _json
        gpt_data    = _json.loads(raw)
        razlog      = gpt_data.get("razlog_kratko", "")
        kljucni_rizik = gpt_data.get("kljucni_rizik", "")
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[CONFIDENCE] GPT greška: %s", e)

    # Korak 5: Compose poruka za korisnika
    wr_deo = (
        f" i {kancelarija_data['uzoraka']} predmeta vaše kancelarije "
        f"sa win rate od {kancelarija_data['win_rate']}%"
        if kancelarija_data and kancelarija_data.get("uzoraka", 0) > 0
        else ""
    )
    poruka = (
        f"Na osnovu {rag_hits} sličnih predmeta iz sudske prakse"
        f"{wr_deo}, procenjujem {nivo} poverenje u ovu analizu."
    )

    # Sačuvaj u predictor_analize
    try:
        await asyncio.to_thread(
            lambda: supa.table("predictor_analize").insert({
                "user_id":      uid,
                "predmet_id":   payload.predmet_id,
                "tip_postupka": payload.tip_spora,
                "opis":         payload.opis_predmeta[:500],
                "analiza":      f"NIVO: {nivo} | PROCENAT: {procenat}% | {razlog}",
                "tip_analize":  "confidence_check",
            }).execute()
        )
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="court_predictor_analiza", user_id=uid,
            resource_type="predmet", resource_id=payload.predmet_id,
        ))
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    preostalo = await UsageService.consume(uid, email, "court_predictor")

    return {
        "nivo_pouzdanosti":   nivo,
        "boja":               boja,
        "procenat":           procenat,
        "razlog":             razlog,
        "kljucni_rizik":      kljucni_rizik,
        "faktori_plus":       faktori_plus,
        "faktori_minus":      faktori_minus,
        "kancelarija_data":   kancelarija_data,
        "rag_statistika": {
            "slicnih_presuda": rag_hits,
            "vks_presuda":     vks_hits,
        },
        "poruka_korisniku":   poruka,
        "credits_remaining":  preostalo,
    }


# ── Learning Stats ─────────────────────────────────────────────────────────────

@router.get("/api/predictor/learning-stats")
@limiter.limit("20/minute")
async def learning_stats(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Dashboard statistika učenja: win rate kancelarije po tipu spora,
    broj AI analiza, performanse preporuka.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Broj AI analiza
    ukupno_analiza = 0
    try:
        cnt_r = await asyncio.to_thread(
            lambda: supa.table("predictor_analize")
                .select("id", count="exact")
                .eq("user_id", uid)
                .execute()
        )
        ukupno_analiza = cnt_r.count or 0
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    # Win rate po tipu spora iz case_patterns
    tip_spora_performanse: list[dict] = []
    ukupni_win_rate: Optional[float] = None
    try:
        patterns_r = await asyncio.to_thread(
            lambda: supa.table("case_patterns")
                .select("tip_spora,pobede,porazi,uzoraka")
                .eq("user_id", uid)
                .execute()
        )
        rows = patterns_r.data or []
        if rows:
            agg: dict[str, dict] = {}
            for r in rows:
                tip = r.get("tip_spora", "ostalo")
                if tip not in agg:
                    agg[tip] = {"pobede": 0, "porazi": 0}
                agg[tip]["pobede"] += r.get("pobede", 0)
                agg[tip]["porazi"] += r.get("porazi", 0)

            for tip, d in agg.items():
                ukupno = d["pobede"] + d["porazi"]
                if ukupno > 0:
                    tip_spora_performanse.append({
                        "tip":      tip,
                        "win_rate": round(d["pobede"] / ukupno * 100, 1),
                        "uzoraka":  ukupno,
                    })

            tip_spora_performanse.sort(key=lambda x: x["uzoraka"], reverse=True)

            sve_pobede = sum(d["pobede"] for d in agg.values())
            sve_ukupno = sum(d["pobede"] + d["porazi"] for d in agg.values())
            if sve_ukupno > 0:
                ukupni_win_rate = round(sve_pobede / sve_ukupno * 100, 1)
    except Exception as e:
        _sentry_capture(e)
        logger.debug("[LEARNING_STATS] case_patterns greška: %s", e)

    # Broj recommendation_log unosa (prihvaćene/odbijene preporuke)
    prihvaceno = 0
    odbijeno   = 0
    try:
        rec_r = await asyncio.to_thread(
            lambda: supa.table("recommendation_log")
                .select("ishod")
                .eq("user_id", uid)
                .execute()
        )
        for r in (rec_r.data or []):
            if r.get("ishod") == "prihvacena":
                prihvaceno += 1
            elif r.get("ishod") == "odbijena":
                odbijeno += 1
    except Exception as _exc:
        _sentry_capture(_exc)
        pass

    if ukupni_win_rate is not None:
        poruka = (
            f"Na osnovu {sum(p['uzoraka'] for p in tip_spora_performanse)} predmeta, "
            f"vaš prosečni win rate je {ukupni_win_rate}%."
        )
    elif ukupno_analiza > 0:
        poruka = f"Pokrenuto {ukupno_analiza} AI analiza. Dodajte ishode predmeta za statistiku uspešnosti."
    else:
        poruka = "Pokrenite prve AI analize da bi sistem počeo da uči iz vaše prakse."

    return {
        "ukupno_analiza":        ukupno_analiza,
        "win_rate_kancelarije":  ukupni_win_rate,
        "tip_spora_performanse": tip_spora_performanse,
        "preporuke_prihvaceno":  prihvaceno,
        "preporuke_odbijeno":    odbijeno,
        "poruka":                poruka,
    }
