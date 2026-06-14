# -*- coding: utf-8 -*-
"""
Vindex AI — services/case_pipeline.py
Case Wizard Automation Pipeline [FAZA:CASE-WIZARD-PIPELINE]

Orchestrates post-wizard automation: doc analysis, auto-linking, rokovi extraction,
strategija, HCC briefing, risk snapshot, copilot preporuka.

Every step is fault-tolerant: a failure moves to the next step.
Every step checks for an existing marker before running (idempotency).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger("vindex.pipeline")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

from openai import AsyncOpenAI  # noqa: E402 — after env load
from shared.deps import _get_supa  # noqa: E402


# ─── Result types ─────────────────────────────────────────────────────────────

class StepStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED  = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class StepResult:
    step: str
    status: StepStatus
    poruka: str = ""
    data: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == StepStatus.SUCCESS


@dataclass
class PipelineResult:
    predmet_id: str
    user_id: str
    steps: list[StepResult] = field(default_factory=list)
    case_ready_score: int = 0
    checklist: list[dict] = field(default_factory=list)
    copilot_preporuka: str = ""

    def to_dict(self) -> dict:
        return {
            "predmet_id":        self.predmet_id,
            "case_ready_score":  self.case_ready_score,
            "checklist":         self.checklist,
            "copilot_preporuka": self.copilot_preporuka,
            "koraci": [
                {
                    "korak":   s.step,
                    "status":  s.status.value,
                    "poruka":  s.poruka,
                }
                for s in self.steps
            ],
        }


# ─── Case Ready Score ─────────────────────────────────────────────────────────

def calculate_case_ready_score(
    dokumenti:  list,
    klijenti:   list,
    rokovi:     list,
    istorija:   list,
    rocista:    list,
) -> tuple[int, list[dict]]:
    """
    Computes Case Ready Score 0–100 and a checklist from raw Supabase data.
    Called both from pipeline and workspace endpoint.
    """
    score = 0
    checklist: list[dict] = []

    has_docs = len(dokumenti) > 0
    if has_docs:
        score += 20
    checklist.append({"stavka": "Dokumentacija priložena", "ok": has_docs, "poen": 20})

    has_klijent = len(klijenti) > 0
    if has_klijent:
        score += 20
    checklist.append({"stavka": "Klijenti evidentirani", "ok": has_klijent, "poen": 20})

    has_rokovi = len(rokovi) > 0
    if has_rokovi:
        score += 15
    checklist.append({"stavka": "Rokovi definisani", "ok": has_rokovi, "poen": 15})

    has_strat = any(
        "[Strategija" in (r.get("pitanje") or "")
        for r in istorija
    )
    if has_strat:
        score += 20
    checklist.append({"stavka": "Strategija generisana", "ok": has_strat, "poen": 20})

    has_rizik = any(
        "[Rizik]" in (r.get("pitanje") or "")
        for r in istorija
    )
    if has_rizik:
        score += 15
    checklist.append({"stavka": "Rizik procenjen", "ok": has_rizik, "poen": 15})

    has_rociste = len(rocista) > 0
    if has_rociste:
        score += 10
    checklist.append({"stavka": "Ročište evidentirano", "ok": has_rociste, "poen": 10})

    return score, checklist


# ─── Step helpers ─────────────────────────────────────────────────────────────

def _safe_data(r) -> list:
    if isinstance(r, Exception):
        return []
    return r.data or []


def _tag_exists(istorija: list, tag: str) -> bool:
    return any(tag in (r.get("pitanje") or "") for r in istorija)


def _today() -> str:
    return date.today().isoformat()


# ─── Individual steps ─────────────────────────────────────────────────────────

async def _step_analiza_dokumenata(supa, predmet_id: str, user_id: str) -> StepResult:
    """
    STEP 1: Check for documents. If docs exist and were already analyzed during
    upload, SUCCESS. If no docs, SKIP. If docs exist without analysis, FAILED.
    """
    try:
        docs_r, ist_r = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
                .select("id,naziv_fajla")
                .eq("predmet_id", predmet_id)
                .execute()),
            asyncio.to_thread(lambda: supa.table("predmet_istorija")
                .select("pitanje")
                .eq("predmet_id", predmet_id)
                .eq("user_id", user_id)
                .like("pitanje", "[Auto-analiza]%")
                .limit(1)
                .execute()),
            return_exceptions=True,
        )
        docs    = _safe_data(docs_r)
        analize = _safe_data(ist_r)

        if not docs:
            return StepResult("analiza_dokumenata", StepStatus.SKIPPED,
                              "Nema uploadovanih dokumenata")
        if analize:
            return StepResult("analiza_dokumenata", StepStatus.SUCCESS,
                              f"{len(docs)} dok. analizirano",
                              {"dokumenti": len(docs)})
        return StepResult("analiza_dokumenata", StepStatus.FAILED,
                          f"{len(docs)} dok. bez analize — biće analizirani pri otvaranju")
    except Exception as exc:
        logger.warning("[PIPELINE][step1] greška: %s", exc)
        return StepResult("analiza_dokumenata", StepStatus.FAILED, str(exc)[:120])


async def _step_auto_linking(supa, predmet_id: str, user_id: str,
                             predmet: dict) -> StepResult:
    """
    STEP 2: Verify klijent links. Intake already creates the primary link;
    we also search klijenti for additional matches from predmet opis.
    """
    try:
        pk_r = await asyncio.to_thread(lambda: supa.table("predmet_klijenti")
            .select("klijent_id,uloga_klijenta")
            .eq("predmet_id", predmet_id)
            .execute())
        links = _safe_data(pk_r)
        if links:
            return StepResult("auto_linking", StepStatus.SUCCESS,
                              f"{len(links)} klijent(a) povezano",
                              {"klijenti_count": len(links)})
        return StepResult("auto_linking", StepStatus.SKIPPED,
                          "Nema povezanih klijenata")
    except Exception as exc:
        logger.warning("[PIPELINE][step2] greška: %s", exc)
        return StepResult("auto_linking", StepStatus.FAILED, str(exc)[:120])


async def _step_ekstrakcija_rokova(supa, predmet_id: str, user_id: str,
                                    predmet: dict) -> StepResult:
    """
    STEP 3: Extract deadlines/dates from predmet opis using GPT-4o-mini.
    Idempotent: skips if [Pipeline:rokovi] marker exists or opis is too short.
    """
    try:
        ist_r = await asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("pitanje")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .like("pitanje", "[Pipeline:rokovi]%")
            .limit(1)
            .execute())
        if _safe_data(ist_r):
            return StepResult("ekstrakcija_rokova", StepStatus.SUCCESS,
                              "Rokovi već ekstraktovani (idempotent)")

        opis = (predmet.get("opis") or "").strip()
        naziv = (predmet.get("naziv") or "").strip()
        tekst = f"Naziv predmeta: {naziv}\n\nOpis: {opis}" if opis else naziv
        if len(tekst) < 30:
            return StepResult("ekstrakcija_rokova", StepStatus.SKIPPED,
                              "Opis predmeta prekratak za ekstrakciju rokova")

        oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        _system = (
            "Ekstrahuj datume i rokove iz pravnog teksta. "
            "Vrati ISKLJUČIVO JSON niz (može biti prazan): "
            '[{"datum":"YYYY-MM-DD","opis":"kratak opis roka","vaznost":"kritičan|bitan|normalan"}] '
            "SAMO ako je datum eksplicitno naveden. NE izmišljaj datume. "
            "Datumi moraju biti u budućnosti ili bliskoj prošlosti (max 1 godina unazad). "
            "Ako nema datuma vrati []."
        )
        r = await asyncio.wait_for(
            oai.chat.completions.create(
                model="gpt-4o-mini", temperature=0, max_tokens=400,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _system},
                    {"role": "user",   "content": tekst[:2000]},
                ],
            ),
            timeout=20.0,
        )
        raw = (r.choices[0].message.content or "{}").strip()

        try:
            parsed = json.loads(raw)
            items = parsed if isinstance(parsed, list) else (
                parsed.get("rokovi") or parsed.get("items") or []
            )
        except Exception:
            items = []

        inserted = 0
        today_iso = _today()
        one_year_ago = (date.today() - timedelta(days=365)).isoformat()
        for item in items[:5]:
            d = (item.get("datum") or "")[:10]
            if not d or d < one_year_ago:
                continue
            opis_roka = (item.get("opis") or "Rok")[:200]
            vaznost   = item.get("vaznost", "bitan")
            if vaznost not in ("kritičan", "bitan", "normalan"):
                vaznost = "bitan"
            try:
                await asyncio.to_thread(lambda d=d, op=opis_roka, vz=vaznost: supa.table("predmet_hronologija").insert({
                    "predmet_id": predmet_id,
                    "user_id":    user_id,
                    "dogadjaj":   op,
                    "datum":      d,
                    "datum_iso":  d,
                    "vaznost":    vz,
                    "akter":      "Pipeline (AI)",
                }).execute())
                inserted += 1
            except Exception as ins_e:
                logger.debug("[PIPELINE][step3] insert greška: %s", ins_e)

        await asyncio.to_thread(lambda: supa.table("predmet_istorija").insert({
            "predmet_id": predmet_id,
            "user_id":    user_id,
            "pitanje":    f"[Pipeline:rokovi] {today_iso}",
            "odgovor":    json.dumps({"inserted": inserted, "found": len(items)},
                                     ensure_ascii=False),
            "confidence": "MEDIUM",
        }).execute())

        if inserted > 0:
            return StepResult("ekstrakcija_rokova", StepStatus.SUCCESS,
                              f"{inserted} rok(a) dodat(o)",
                              {"inserted": inserted})
        return StepResult("ekstrakcija_rokova", StepStatus.SKIPPED,
                          "Nema prepoznatih rokova u opisu predmeta")
    except Exception as exc:
        logger.warning("[PIPELINE][step3] greška: %s", exc)
        return StepResult("ekstrakcija_rokova", StepStatus.FAILED, str(exc)[:120])


async def _step_kalendar(supa, predmet_id: str, user_id: str) -> StepResult:
    """
    STEP 4: Verify rokovi were added to calendar (predmet_hronologija = calendar).
    """
    try:
        r = await asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("id")
            .eq("predmet_id", predmet_id)
            .limit(1)
            .execute())
        if _safe_data(r):
            return StepResult("kalendar", StepStatus.SUCCESS,
                              "Kalendar sadrži rokove predmeta")
        return StepResult("kalendar", StepStatus.SKIPPED,
                          "Nema rokova u kalendaru")
    except Exception as exc:
        logger.warning("[PIPELINE][step4] greška: %s", exc)
        return StepResult("kalendar", StepStatus.FAILED, str(exc)[:120])


async def _step_strategija(supa, predmet_id: str, user_id: str,
                            predmet: dict) -> StepResult:
    """
    STEP 5: Initial litigation strategy using GPT-4o-mini (lite version).
    Idempotent: skips if [Strategija Pipeline] entry already exists.
    """
    try:
        ist_r = await asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("pitanje")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .like("pitanje", "[Strategija Pipeline]%")
            .limit(1)
            .execute())
        if _safe_data(ist_r):
            return StepResult("strategija", StepStatus.SUCCESS,
                              "Strategija već generisana (idempotent)")

        naziv = (predmet.get("naziv") or "").strip()
        opis  = (predmet.get("opis")  or "").strip()
        tip   = (predmet.get("tip")   or "opsti").strip()
        if len(naziv) + len(opis) < 10:
            return StepResult("strategija", StepStatus.SKIPPED,
                              "Nedovoljno podataka za strategiju")
        tekst = f"Predmet: {naziv}\nTip: {tip}\nOpis: {opis}".strip()

        oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        _system = (
            "Ti si srpski pravni strateg. Na osnovu opisa predmeta daj kratku inicijalnu "
            "procenu (max 200 reči, srpski ekavica):\n"
            "1. Vrsta spora i primenljivi zakoni\n"
            "2. Procena izgleda (optimistično / neutralno / pesimistično)\n"
            "3. Preporučena strategija (tužba / odbrana / nagodba)\n"
            "4. Sledeći koraci (2-3 konkretna)\n"
            "Budi konkretan, bez opštih fraza."
        )
        r = await asyncio.wait_for(
            oai.chat.completions.create(
                model="gpt-4o-mini", temperature=0.2, max_tokens=600,
                messages=[
                    {"role": "system", "content": _system},
                    {"role": "user",   "content": tekst[:3000]},
                ],
            ),
            timeout=25.0,
        )
        rezultat = (r.choices[0].message.content or "").strip()
        if not rezultat:
            return StepResult("strategija", StepStatus.FAILED, "AI nije vratio sadržaj")

        await asyncio.to_thread(lambda: supa.table("predmet_istorija").insert({
            "predmet_id": predmet_id,
            "user_id":    user_id,
            "pitanje":    "[Strategija Pipeline] Inicijalna procena",
            "odgovor":    rezultat,
            "confidence": "MEDIUM",
        }).execute())
        return StepResult("strategija", StepStatus.SUCCESS,
                          "Inicijalna strategija generisana",
                          {"chars": len(rezultat)})
    except Exception as exc:
        logger.warning("[PIPELINE][step5] greška: %s", exc)
        return StepResult("strategija", StepStatus.FAILED, str(exc)[:120])


async def _step_hcc(supa, predmet_id: str, user_id: str,
                     predmet: dict) -> StepResult:
    """
    STEP 6: If an upcoming hearing exists, generate a minimal HCC briefing.
    Idempotent: skips if [HCC Pipeline] entry exists.
    """
    try:
        today_iso   = _today()
        in_90d_iso  = (date.today() + timedelta(days=90)).isoformat()
        rocista_r   = await asyncio.to_thread(lambda: supa.table("rocista")
            .select("id,datum,sud,tip_postupka,status")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .gte("datum", today_iso)
            .lte("datum", in_90d_iso)
            .order("datum")
            .limit(1)
            .execute())
        rocista = _safe_data(rocista_r)
        if not rocista:
            return StepResult("hcc", StepStatus.SKIPPED,
                              "Nema zakazanih ročišta u narednih 90 dana")

        ist_r = await asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("pitanje")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .like("pitanje", "[HCC Pipeline]%")
            .limit(1)
            .execute())
        if _safe_data(ist_r):
            return StepResult("hcc", StepStatus.SUCCESS,
                              "HCC brifing već generisan (idempotent)")

        rociste    = rocista[0]
        datum_roc  = rociste.get("datum", today_iso)
        sud        = rociste.get("sud", "sud")
        tip        = rociste.get("tip_postupka", "gradjanski")
        naziv      = (predmet.get("naziv") or "").strip()
        opis       = (predmet.get("opis")  or "")[:800]

        oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        _system = (
            "Ti si pravni asistent koji priprema kratki pre-briefing za ročište. "
            "Vrati 3-5 konkretnih napomena šta advokat treba da uradi pre ročišta. "
            "Srpski ekavica, max 150 reči."
        )
        r = await asyncio.wait_for(
            oai.chat.completions.create(
                model="gpt-4o-mini", temperature=0.1, max_tokens=300,
                messages=[
                    {"role": "system", "content": _system},
                    {"role": "user",   "content": (
                        f"Predmet: {naziv}\nOpis: {opis}\n"
                        f"Ročište: {datum_roc} | Sud: {sud} | Tip: {tip}"
                    )},
                ],
            ),
            timeout=20.0,
        )
        brifing = (r.choices[0].message.content or "").strip()
        if not brifing:
            return StepResult("hcc", StepStatus.FAILED, "AI nije vratio brifing")

        await asyncio.to_thread(lambda: supa.table("predmet_istorija").insert({
            "predmet_id": predmet_id,
            "user_id":    user_id,
            "pitanje":    f"[HCC Pipeline] {datum_roc}",
            "odgovor":    brifing,
            "confidence": "MEDIUM",
        }).execute())
        return StepResult("hcc", StepStatus.SUCCESS,
                          f"Pre-brifing za ročište {datum_roc} generisan",
                          {"datum": datum_roc})
    except Exception as exc:
        logger.warning("[PIPELINE][step6] greška: %s", exc)
        return StepResult("hcc", StepStatus.FAILED, str(exc)[:120])


async def _step_risk_snapshot(supa, predmet_id: str, user_id: str,
                               predmet: dict) -> StepResult:
    """
    STEP 7: Generate initial risk snapshot using GPT-4o-mini.
    Idempotent: skips if today's [Rizik] entry already exists.
    """
    try:
        today_iso = _today()
        today_tag = f"[Rizik] {today_iso}"
        ist_r = await asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("pitanje")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .eq("pitanje", today_tag)
            .limit(1)
            .execute())
        if _safe_data(ist_r):
            return StepResult("risk_snapshot", StepStatus.SUCCESS,
                              "Risk snapshot već postoji za danas (idempotent)")

        naziv = (predmet.get("naziv") or "").strip()
        opis  = (predmet.get("opis")  or "")[:1000]
        tip   = (predmet.get("tip")   or "opsti")

        oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        _system = (
            "Na osnovu opisa predmeta proceni rizik. Vrati ISKLJUČIVO JSON: "
            '{"nivo":"visok|srednji|nizak","faktori_plus":["str"],"faktori_minus":["str"]} '
            "Max 3 faktora po listi. Srpski ekavica."
        )
        r = await asyncio.wait_for(
            oai.chat.completions.create(
                model="gpt-4o-mini", temperature=0, max_tokens=300,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _system},
                    {"role": "user",   "content": f"Predmet: {naziv}\nTip: {tip}\nOpis: {opis}"},
                ],
            ),
            timeout=20.0,
        )
        raw  = (r.choices[0].message.content or "{}").strip()
        data = json.loads(raw)
        nivo = data.get("nivo", "srednji")
        if nivo not in ("visok", "srednji", "nizak"):
            nivo = "srednji"

        await asyncio.to_thread(lambda: supa.table("predmet_istorija").insert({
            "predmet_id": predmet_id,
            "user_id":    user_id,
            "pitanje":    today_tag,
            "odgovor":    json.dumps(data, ensure_ascii=False),
            "confidence": "MEDIUM",
        }).execute())
        return StepResult("risk_snapshot", StepStatus.SUCCESS,
                          f"Rizik: {nivo}",
                          {"nivo": nivo, "data": data})
    except Exception as exc:
        logger.warning("[PIPELINE][step7] greška: %s", exc)
        return StepResult("risk_snapshot", StepStatus.FAILED, str(exc)[:120])


async def _step_copilot_preporuka(supa, predmet_id: str, user_id: str,
                                   predmet: dict, step3: StepResult,
                                   step7: StepResult) -> StepResult:
    """
    STEP 8: Generate initial Copilot advice based on pipeline state.
    """
    try:
        naziv = (predmet.get("naziv") or "").strip()
        opis  = (predmet.get("opis")  or "")[:800]
        tip   = (predmet.get("tip")   or "opsti")

        rizik_nivo = step7.data.get("nivo", "srednji") if step7.ok else "srednji"
        rok_count  = step3.data.get("inserted", 0) if step3.ok else 0

        _context = (
            f"Predmet: {naziv} | Tip: {tip} | Rizik: {rizik_nivo}\n"
            f"Opis: {opis}\n"
            f"Rokovi pronađeni: {rok_count}"
        )

        oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        _system = (
            "Ti si Vindex Copilot — AI pravni asistent. "
            "Generiši 2-3 konkretne akcione preporuke za advokata koji je upravo otvorio ovaj predmet. "
            "Format: kratke rečenice, bez numeracije, srpski ekavica, max 100 reči. "
            "Preporuke moraju biti specifične za ovaj predmet, ne opšte."
        )
        r = await asyncio.wait_for(
            oai.chat.completions.create(
                model="gpt-4o-mini", temperature=0.3, max_tokens=200,
                messages=[
                    {"role": "system", "content": _system},
                    {"role": "user",   "content": _context},
                ],
            ),
            timeout=20.0,
        )
        preporuka = (r.choices[0].message.content or "").strip()
        if not preporuka:
            preporuka = "Proverite dokumentaciju i rokove predmeta."

        return StepResult("copilot_preporuka", StepStatus.SUCCESS,
                          "Inicijalni savet generisan",
                          {"preporuka": preporuka})
    except Exception as exc:
        logger.warning("[PIPELINE][step8] greška: %s", exc)
        return StepResult("copilot_preporuka", StepStatus.FAILED,
                          str(exc)[:120],
                          {"preporuka": "Proverite dokumentaciju i rokove predmeta."})


async def _step_istorija(supa, predmet_id: str, user_id: str,
                          steps: list[StepResult]) -> StepResult:
    """
    STEP 9: Record pipeline execution summary in predmet_istorija.
    Idempotent: one entry per day.
    """
    try:
        today_iso = _today()
        tag       = f"[Pipeline] {today_iso}"
        existing  = await asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("id")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .eq("pitanje", tag)
            .limit(1)
            .execute())
        if _safe_data(existing):
            return StepResult("istorija", StepStatus.SUCCESS,
                              "Pipeline zapis već postoji za danas (idempotent)")

        summary = {
            "datum":   today_iso,
            "koraci":  [
                {"korak": s.step, "status": s.status.value, "poruka": s.poruka}
                for s in steps
            ],
            "uspesno": sum(1 for s in steps if s.status == StepStatus.SUCCESS),
            "preskoceno": sum(1 for s in steps if s.status == StepStatus.SKIPPED),
            "neuspesno":  sum(1 for s in steps if s.status == StepStatus.FAILED),
        }
        await asyncio.to_thread(lambda: supa.table("predmet_istorija").insert({
            "predmet_id": predmet_id,
            "user_id":    user_id,
            "pitanje":    tag,
            "odgovor":    json.dumps(summary, ensure_ascii=False),
            "confidence": "HIGH",
        }).execute())
        return StepResult("istorija", StepStatus.SUCCESS,
                          f"Pipeline zapis sačuvan ({summary['uspesno']} uspešnih)")
    except Exception as exc:
        logger.warning("[PIPELINE][step9] greška: %s", exc)
        return StepResult("istorija", StepStatus.FAILED, str(exc)[:120])


# ─── Main orchestrator ────────────────────────────────────────────────────────

async def run_case_pipeline(predmet_id: str, user_id: str) -> PipelineResult:
    """
    Runs all 9 pipeline steps. Fault-tolerant: one failure does not stop others.
    Returns PipelineResult with Case Ready Score and checklist.
    """
    supa = _get_supa()

    # Verify predmet exists
    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("naziv,opis,tip,status")
            .eq("id", predmet_id)
            .eq("user_id", user_id)
            .single()
            .execute()
    )
    if not pred_r.data:
        raise ValueError(f"Predmet {predmet_id} nije pronađen ili nema pristup")

    predmet = pred_r.data
    result  = PipelineResult(predmet_id=predmet_id, user_id=user_id)

    # Run steps sequentially; each step is isolated
    step1 = await _step_analiza_dokumenata(supa, predmet_id, user_id)
    step2 = await _step_auto_linking(supa, predmet_id, user_id, predmet)
    step3 = await _step_ekstrakcija_rokova(supa, predmet_id, user_id, predmet)
    step4 = await _step_kalendar(supa, predmet_id, user_id)
    step5 = await _step_strategija(supa, predmet_id, user_id, predmet)
    step6 = await _step_hcc(supa, predmet_id, user_id, predmet)
    step7 = await _step_risk_snapshot(supa, predmet_id, user_id, predmet)
    step8 = await _step_copilot_preporuka(supa, predmet_id, user_id, predmet,
                                           step3, step7)
    step9 = await _step_istorija(supa, predmet_id, user_id,
                                  [step1, step2, step3, step4, step5, step6, step7, step8])

    result.steps = [step1, step2, step3, step4, step5, step6, step7, step8, step9]

    # Compute Case Ready Score from current DB state
    docs_r, pk_r, hron_r, ist_r, roc_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("id").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti")
            .select("klijent_id").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("id").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("pitanje").eq("predmet_id", predmet_id)
            .eq("user_id", user_id).execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("id").eq("predmet_id", predmet_id)
            .eq("user_id", user_id).execute()),
        return_exceptions=True,
    )

    result.case_ready_score, result.checklist = calculate_case_ready_score(
        dokumenti=_safe_data(docs_r),
        klijenti=_safe_data(pk_r),
        rokovi=_safe_data(hron_r),
        istorija=_safe_data(ist_r),
        rocista=_safe_data(roc_r),
    )
    result.copilot_preporuka = step8.data.get("preporuka", "")

    logger.info(
        "[PIPELINE] predmet=%s score=%d steps=%d/9",
        predmet_id[:8], result.case_ready_score, len(result.steps),
    )
    return result
