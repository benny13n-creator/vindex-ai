# -*- coding: utf-8 -*-
"""
Vindex AI — routers/intake.py

POST /api/intake/ekstrakcija      — GPT-4o-mini entity extraction
POST /api/intake/kreiraj          — Create predmet + link klijent + add rok
POST /api/intake/conflict-check   — Sukob interesa check (novi klijent + protivna strana)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService
from shared import rokovi as _rokovi_domen

logger = logging.getLogger("vindex.intake")
router = APIRouter(tags=["intake"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Program Lambda, Certification 004 (2026-08-06): Chaos Engineer + Database
# Reliability forks both independently found (Adversarial Certification-
# confirmed) that this endpoint had zero protection against a double-click/
# duplicate submit -- a bare INSERT with no idempotency key and no recent-
# duplicate check, unlike smart_intake.py's own hardened case-creation path
# (an atomic claim_intake_finalize RPC). A true atomic fix needs a
# client-generated idempotency key (a frontend change, out of this
# backend-only reliability sprint's scope) or a DB-level constraint shaped
# around a time window (awkward -- Postgres UNIQUE doesn't express "same
# user+name within N seconds" directly). This is a narrower, still-real
# mitigation: reject an unmistakably-duplicate submission (same user, same
# case name, within a few seconds) before it ever reaches the insert. 5
# seconds comfortably covers a real double-click or an impatient repeat
# button-press while never blocking two genuinely separate cases a user
# creates minutes apart -- a check-then-insert, not a DB-level atomic
# claim, so a residual race window remains for two requests landing within
# the same instant; narrowing that further needs the idempotency-key
# approach and is left as a named follow-up, not guessed at further here.
_DUPLICATE_CASE_WINDOW_SECONDS = 5

_EKSTRAKCIJA_SYSTEM = """Ti si pravni asistent za srpske advokate. Na osnovu opisa problema i opcionalnih nalaza iz analize dokumenta, ekstrahuj ključne podatke za otvaranje novog predmeta.

Vrati ISKLJUČIVO validan JSON bez markdown fence-ova, bez ikakvih komentara:
{
  "predlog_naziva_predmeta": "<kratak opisni naziv, max 80 znakova>",
  "protivna_strana": "<ime/naziv protivne strane ILI null ako nije pomenuta>",
  "vrsta_spora": "<radni spor|ugovorni spor|naknada štete|nasleđe|porodično pravo|privredno pravo|krivično|nekretnine|ostalo>",
  "vrednost_spora": "<iznos u RSD kao string npr. '500000 RSD' ILI null>",
  "prvi_rok": "<datum u formatu YYYY-MM-DD ILI null — SAMO ako je eksplicitno naveden u tekstu>",
  "rok_opis": "<opis roka ILI null>",
  "potrebni_dokumenti": ["<naziv dokumenta>"]
}

APSOLUTNA PRAVILA:
1. prvi_rok = null osim ako datum nije EKSPLICITNO naveden u tekstu. NE izmišljaj datume.
2. vrednost_spora = null ako iznos nije pomenut.
3. protivna_strana = null ako nije pomenuta.
4. Jezik: ISKLJUČIVO srpska ekavica. ZABRANJENA ijekavica: procijeniti→proceniti, procjena→procena, vrijed→vred, rješen→rešen, savjet→savet, mjesto→mesto.
5. potrebni_dokumenti: navedi 2-5 dokumenata tipičnih za ovu vrstu spora."""


@llm_retry
async def _pozovi_intake_api(oai, **kwargs):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške (retry-loop ispod
    ostaje odgovoran za JSON-parse greške, ne za transportne)."""
    return await oai.chat.completions.create(**kwargs)


async def _call_ekstrakcija(opis: str, nalazi: list) -> dict:
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)

    context_parts = [f"Opis problema:\n{opis}"]
    if nalazi:
        top = nalazi[:5]
        nalazi_tekst = "\n".join(
            f"- [{f.get('severity', '')}] {f.get('finding', '')}"
            for f in top if isinstance(f, dict)
        )
        if nalazi_tekst:
            context_parts.append(f"\nNalazi iz analize dokumenta:\n{nalazi_tekst}")

    user_msg = "\n".join(context_parts)

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            r = await _pozovi_intake_api(
                oai,
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _EKSTRAKCIJA_SYSTEM},
                    {"role": "user",   "content": user_msg[:3000]},
                ],
                temperature=0.2,
                max_tokens=600,
                response_format={"type": "json_object"},
            )
            raw = (r.choices[0].message.content or "{}").strip()
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("[INTAKE] JSON parse greška (pokušaj %d/3): %s", attempt + 1, e)
            last_exc = e
        except Exception as e:
            _sentry_capture(e)
            logger.error("[INTAKE] OpenAI greška: %s", e)
            raise HTTPException(status_code=502, detail="AI ekstrakcija trenutno nedostupna.")
    logger.error("[INTAKE] JSON parse greška posle 3 pokušaja: %s", last_exc)
    raise HTTPException(status_code=422, detail="AI ekstrakcija nije mogla da parsira odgovor. Pokušajte ponovo ili unesite podatke ručno.")


class EkstrakcijReq(BaseModel):
    opis_problema: str = Field(..., min_length=20, max_length=4000)
    analiza_results: Optional[List[dict]] = None


class DokumentIntakeRef(BaseModel):
    naziv_fajla: str = Field(..., min_length=1, max_length=500)
    session_id:  str = Field(..., min_length=1, max_length=128)
    chunks:      int = Field(default=0)


class IntakeKreirajReq(BaseModel):
    klijent_id:      str           = Field(..., min_length=1, max_length=64)
    naziv:           str           = Field(..., min_length=2, max_length=200)
    opis:            str           = Field(default="", max_length=4000)
    tip:             str           = Field(default="opsti", max_length=50)
    vrsta_spora:     str           = Field(default="", max_length=100)
    vrednost_spora:  str           = Field(default="", max_length=100)
    protivna_strana: str           = Field(default="", max_length=200)
    prvi_rok:        Optional[str] = Field(default=None, max_length=12)
    rok_opis:        Optional[str] = Field(default=None, max_length=300)
    dokumenti:       List[DokumentIntakeRef] = Field(default_factory=list)
    template_id:     Optional[str] = Field(default=None, max_length=100)
    # Billing setup (opciono)
    billing_tip:     Optional[str]   = Field(default=None, max_length=20)   # fiksni | satnica | aks
    billing_iznos:   Optional[float] = Field(default=None, ge=0)
    billing_aks:     Optional[str]   = Field(default=None, max_length=10)   # T01, T02...


@router.post("/api/intake/ekstrakcija")
@limiter.limit("20/minute")
async def intake_ekstrakcija(
    body: EkstrakcijReq,
    request: Request,
    user: dict = Depends(PermissionService.require("intake_ai")),
):
    """Ekstrahuje ključne podatke za novi predmet iz opisa problema i opcionalnih nalaza."""
    nalazi = body.analiza_results or []
    result = await _call_ekstrakcija(body.opis_problema, nalazi)

    await UsageService.consume(user["user_id"], user.get("email", ""), "intake_ai")

    return {
        "predlog_naziva_predmeta": result.get("predlog_naziva_predmeta") or "Novi predmet",
        "protivna_strana":        result.get("protivna_strana"),
        "vrsta_spora":            result.get("vrsta_spora") or "ostalo",
        "vrednost_spora":         result.get("vrednost_spora"),
        "prvi_rok":               result.get("prvi_rok"),
        "rok_opis":               result.get("rok_opis"),
        "potrebni_dokumenti":     result.get("potrebni_dokumenti") or [],
    }


@router.post("/api/intake/kreiraj")
@limiter.limit("30/minute")
async def intake_kreiraj(
    body: IntakeKreirajReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Kreira predmet, linkuje klijenta i opcionalno dodaje rok."""
    uid  = user["user_id"]
    supa = _get_supa()

    opis_delovi = [body.opis] if body.opis else []
    if body.protivna_strana:
        opis_delovi.append(f"Protivna strana: {body.protivna_strana}")
    if body.vrsta_spora:
        opis_delovi.append(f"Vrsta spora: {body.vrsta_spora}")
    if body.vrednost_spora:
        opis_delovi.append(f"Vrednost spora: {body.vrednost_spora}")
    full_opis = "\n".join(opis_delovi)

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(seconds=_DUPLICATE_CASE_WINDOW_SECONDS)).isoformat()
    dup_check = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id, created_at")
            .eq("user_id", uid).eq("naziv", body.naziv)
            .gte("created_at", cutoff_iso)
            .limit(1).execute()
    )
    if dup_check.data:
        logger.warning(
            "[INTAKE] dupliran zahtev odbijen — uid=%.8s naziv=%r već kreiran pre <%ds (predmet=%s)",
            uid, body.naziv, _DUPLICATE_CASE_WINDOW_SECONDS, dup_check.data[0]["id"],
        )
        raise HTTPException(
            status_code=409,
            detail="Predmet sa ovim nazivom je upravo kreiran. Ako ovo nije duplikat, sačekajte par sekundi i pokušajte ponovo.",
        )

    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti").insert({
            "user_id": uid,
            "naziv":   body.naziv,
            "opis":    full_opis,
            "tip":     body.tip,
            "status":  "aktivan",
        }).execute()
    )
    if not pred_r.data:
        raise HTTPException(status_code=500, detail="Kreiranje predmeta nije uspelo.")
    predmet    = pred_r.data[0]
    predmet_id = predmet["id"]

    # Program Lambda, Certification 005 (2026-08-07) -- an Audit Continuity
    # fork found this endpoint (the Intake Wizard's own case-creation path)
    # had zero audit trail, unlike api.py::kreiraj_predmet (the OTHER
    # case-creation path), which already logs "predmet_create" via this same
    # already-shipped log_action/AUDITABLE_ACTIONS infrastructure -- a case
    # created through the wizard was silently invisible to the audit chain.
    # Reuses the identical action name/shape, not a new one.
    try:
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            "predmet_create",
            user_id=uid,
            resource_type="predmet",
            resource_id=predmet_id,
            ip=request.client.host if request.client else None,
            metadata={"naziv": body.naziv, "tip": body.tip, "source": "intake_wizard"},
        ))
    except Exception as _ae:
        logger.warning("[INTAKE] predmet_create audit log greška: %s", _ae)

    # Program Lambda, Certification 004: Database Reliability fork found
    # this step's own outcome had no status field in the response, unlike
    # every OTHER optional step below (rok_dodat/docs_linked/billing_kreiran)
    # -- a rejected/failed client link was invisible to the caller, who saw
    # success:True with no client attached and no way to know why short of
    # opening the case later. klijent_povezan now reports it explicitly.
    #
    # NIGHT STABILIZATION 001 / FAZA 1 (BR-002): `klijent_povezan` je bio
    # izveštaj koji NIKO ne čita. `_intakeKreiraj` u `static/vindex.js` uzima
    # samo `d.predmet_id` i odmah prelazi na ekran uspeha — advokat je dobijao
    # potpunu potvrdu kreiranja predmeta za klijenta koji uz taj predmet nije
    # vezan, bez ijednog signala. Mereno: `predmet_klijenti` je imao 0 redova
    # uz 19 predmeta i 5 klijenata.
    #
    # Klijent je za ovaj tok OBAVEZAN (`klijent_id` je obavezno polje, a
    # čarobnjak blokira korak bez izabranog klijenta), pa predmet bez veze nije
    # „delimičan uspeh" nego neuspeh. Isti obrazac koji `api.py` upload ruta već
    # koristi kad obavezan sledeći upis padne: ukloni ono što je upravo
    # napravljeno i podigni grešku, umesto da vratiš 200 na pola posla.
    # Kompenzacija je bezbedna baš ovde: veza je PRVI korak posle kreiranja
    # predmeta, pa još ništa drugo ne pokazuje na taj predmet.
    klijent_povezan = False
    _veza_greska: Optional[str] = None
    try:
        klijent_ok = await asyncio.to_thread(
            lambda: supa.table("klijenti").select("id").eq("id", body.klijent_id).eq("user_id", uid).maybe_single().execute()
        )
        # `.maybe_single()` vraća None (ne objekat) kad nema reda -- zato
        # `getattr`, inače bi ovo bio AttributeError umesto jasnog ishoda.
        if not getattr(klijent_ok, "data", None):
            logger.warning("[INTAKE] predmet_klijenti insert odbijen — klijent_id %.8s ne pripada uid=%.8s", body.klijent_id, uid)
            _veza_greska = "nepostojeci_klijent"
        else:
            await asyncio.to_thread(
                lambda: supa.table("predmet_klijenti").insert({
                    "predmet_id":     predmet_id,
                    "klijent_id":     body.klijent_id,
                    "uloga_klijenta": "stranka",
                }).execute()
            )
            klijent_povezan = True
    except Exception as e:
        logger.warning("[INTAKE] predmet_klijenti insert greška: %s", e)
        _veza_greska = "upis_veze"

    if not klijent_povezan:
        try:
            await asyncio.to_thread(
                lambda: supa.table("predmeti").delete().eq("id", predmet_id).eq("user_id", uid).execute()
            )
            logger.warning("[INTAKE] predmet %s uklonjen — klijent nije povezan (%s)", predmet_id, _veza_greska)
        except Exception as _ce:
            logger.error("[INTAKE] kompenzacija nije uspela, predmet %s ostaje bez klijenta: %s", predmet_id, _ce)
        if _veza_greska == "nepostojeci_klijent":
            raise HTTPException(status_code=404, detail="Klijent nije pronađen. Predmet nije kreiran.")
        raise HTTPException(
            status_code=500,
            detail="Predmet nije kreiran — povezivanje klijenta nije uspelo. Pokušajte ponovo.",
        )

    rok_dodat = False
    if body.prvi_rok:
        try:
            naziv_roka = (body.rok_opis or "Rok").strip()[:200]
            await asyncio.to_thread(
                lambda: supa.table("predmet_hronologija").insert({
                    "predmet_id": predmet_id,
                    "user_id":    uid,
                    "dogadjaj":   naziv_roka,
                    "datum":      body.prvi_rok,
                    "datum_iso":  body.prvi_rok,
                    "vaznost":    _rokovi_domen.normalizuj_vaznost("bitan"),
                    "akter":      "Intake Wizard (AI)",
                    # migracija 127 — W-INTAKE-ROK: `body.prvi_rok` dolazi
                    # iz forme koju je advokat popunio.
                    "izvor":      _IZVOR.IZVOR_AI_ASSISTED,
                }).execute()
            )
            rok_dodat = True
        except Exception as e:
            logger.warning("[INTAKE] rok insert greška: %s", e)

    # Link uploaded documents to the new predmet
    docs_linked = 0
    for dok in body.dokumenti[:10]:
        try:
            _doc_row = {
                "predmet_id":  predmet_id,
                "user_id":     uid,
                "naziv_fajla": dok.naziv_fajla[:500],
                "velicina_kb": 1,
                # Program Intake Sprint 001 (2026-08-04) -- bez ovoga red pada
                # na DB default 'na_cekanju', koji lažno sugeriše da je
                # dokument još u obradi zauvek (Fork 3 finding: dva pisca
                # predmet_dokumenti nikad ne postavljaju status). Ovaj wizard
                # korak samo POVEZUJE već otpremljen (session-based) dokument
                # sa novim predmetom -- ne ponavlja OCR/indeksiranje ovde --
                # pa 'sacuvano' je najhonestija vrednost iz postojećeg
                # vokabulara (api.py koristi isto 'sacuvano' kad Pinecone
                # indeksiranje nije (re)potvrđeno, ne izmišljena nova reč).
                "status": "sacuvano",
            }
            try:
                await asyncio.to_thread(
                    lambda r=_doc_row, sid=dok.session_id: supa.table("predmet_dokumenti").insert(
                        {**r, "session_id": sid}
                    ).execute()
                )
            except Exception:
                await asyncio.to_thread(
                    lambda r=_doc_row: supa.table("predmet_dokumenti").insert(r).execute()
                )
            docs_linked += 1
        except Exception as e:
            logger.warning("[INTAKE] dok link greška (%s): %s", dok.naziv_fajla, e)

    # Billing entry — kreiranje ako je advokat izabrao tip
    billing_kreiran = False
    if body.billing_tip in ("fiksni", "aks"):
        try:
            from routers.billing import AKS_TARIFA, BOD_RSD
            _today_iso = date.today().isoformat()
            if body.billing_tip == "fiksni" and body.billing_iznos:
                billing_row = {
                    "user_id":    uid,
                    "predmet_id": predmet_id,
                    "opis":       f"Honorar — {body.naziv}"[:400],
                    "tip":        "konsultacija",
                    "iznos_rsd":  float(body.billing_iznos),
                    "datum":      _today_iso,
                    "obracunato": False,
                }
            elif body.billing_tip == "aks" and body.billing_aks:
                sifra  = (body.billing_aks or "").upper()
                tarifa = AKS_TARIFA.get(sifra)
                if tarifa:
                    bodovi = tarifa.get("bodovi") or 0
                    iznos  = tarifa.get("fiksno_rsd") or (bodovi * BOD_RSD)
                    billing_row = {
                        "user_id":      uid,
                        "predmet_id":   predmet_id,
                        "opis":         tarifa["naziv"][:400],
                        "tip":          "postupak",
                        "tarifa_sifra": sifra,
                        "tarifa_naziv": tarifa["naziv"],
                        "bodovi":       bodovi,
                        "iznos_rsd":    float(iznos),
                        "datum":        _today_iso,
                        "obracunato":   False,
                    }
                else:
                    billing_row = None
            else:
                billing_row = None

            if billing_row:
                await asyncio.to_thread(
                    lambda r=billing_row: supa.table("billing_entries").insert(r).execute()
                )
                billing_kreiran = True
        except Exception as e:
            logger.warning("[INTAKE] billing entry greška: %s", e)

    elif body.billing_tip == "satnica":
        # Startuj tajmer odmah
        try:
            await asyncio.to_thread(
                lambda: supa.table("timer_sessions").insert({
                    "user_id":    uid,
                    "predmet_id": predmet_id,
                    "aktivan":    True,
                    "opis":       f"Rad — {body.naziv}"[:400],
                    "tip":        "satnica",
                }).execute()
            )
            billing_kreiran = True
        except Exception as e:
            logger.warning("[INTAKE] timer start greška: %s", e)

    # Template hronologija — ako je template izabran, dodaj predefinisane rokove
    tpl_hron_dodat = 0
    if body.template_id:
        tpl = next((t for t in _TEMPLATES if t["id"] == body.template_id), None)
        if tpl:
            today = date.today()
            hron_rows = []
            for h in tpl.get("hronologija_predlozi", []):
                offset = h.get("days_offset", 0)
                datum  = (today + timedelta(days=offset)).isoformat()
                hron_rows.append({
                    "predmet_id": predmet_id,
                    "user_id":    uid,
                    "dogadjaj":   h["dogadjaj"],
                    "vaznost":    h["vaznost"],
                    "datum":      datum,
                    "datum_iso":  datum,
                    "akter":      "Intake Wizard — šablon",
                    # migracija 127 — W-INTAKE-TPL1: sadrzaj je staticki
                    # `_TEMPLATES` katalog, advokat je izabrao sablon.
                    "izvor":      _IZVOR.IZVOR_DETERMINISTIC,
                })
            if hron_rows:
                try:
                    await asyncio.to_thread(
                        lambda: supa.table("predmet_hronologija").insert(hron_rows).execute()
                    )
                    tpl_hron_dodat = len(hron_rows)
                except Exception as e:
                    logger.warning("[INTAKE] template hronologija greška: %s", e)

    logger.info("[INTAKE] predmet=%s uid=%.8s rok=%s docs=%d billing=%s tpl_hron=%d",
                predmet_id, uid, rok_dodat, docs_linked, billing_kreiran, tpl_hron_dodat)

    # Night Shift M-013 (2026-08-02): pokreni Case Pipeline u pozadini, isti
    # obrazac kao post_from_template (routers/intake.py) i POST /api/predmeti
    # (api.py) -- ovo je bio jedini glavni predmet-creation put bez ovog
    # okidača (M-002 nalaz), a ujedno i najkorišćeniji AI-assisted put po
    # Bojan Workflow Gap Analysis-i.
    async def _run_pipeline() -> None:
        try:
            from services.case_pipeline import run_case_pipeline
            await run_case_pipeline(predmet_id, uid)
        except Exception as _pe:
            logger.warning("[INTAKE] pipeline greška predmet=%s: %s", predmet_id, _pe)

    asyncio.create_task(_run_pipeline())

    return {
        "success":          True,
        "predmet_id":       predmet_id,
        "predmet":          predmet,
        "klijent_povezan":  klijent_povezan,
        "rok_dodat":        rok_dodat,
        "docs_linked":      docs_linked,
        "billing_kreiran":  billing_kreiran,
        "tpl_hron_dodat":   tpl_hron_dodat,
    }


# ─── Conflict of Interest check ───────────────────────────────────────────────

_OPPOSING_ROLES = frozenset({
    "protivna_strana", "protivna_stranka", "tuzeni", "advokat_protivne",
})
_CLIENT_ROLES = frozenset({"stranka", "tuzilac"})


# PRG-P1-COI-CONVERGENCE-001: jedan poslovni pojam ("da li je ovo ista
# stranka?") imao je tri nezavisne implementacije. Ovo je jedina kanonska.
from routers.conflict_check import CONFLICT_WARN, _fuzzy_score
from routers.conflict_check import _normalize_name as _kanonska_normalizacija
from shared import rokovi as _IZVOR  # migracija 127 — kanonske vrednosti `izvor`


def _norm(s: str) -> str:
    """Normalizacija imena stranke — KANONSKA (`routers/conflict_check.py`).

    Ranije je ovde stajala lokalna normalizacija koja interpunkciju pretvara u
    razmak, pa je "Delta d.o.o." postajalo "delta d o o", a pravni nastavak se
    nije skidao. Zbog toga "Delta doo" i "Delta d.o.o." — ista firma — nisu bili
    prepoznati kao isti subjekt.
    """
    return _kanonska_normalizacija(s)


def _name_match(query: str, candidate: str) -> bool:
    """Da li su ovo ista stranka? ISTA odluka koju donosi kanonski COI.

    Ranije: `query in candidate or candidate in query`. Gola supstring provera,
    bez praga, nad tekstom kome pravni nastavak nije skinut. Posledice izmerene
    nad 19 realnih parova (PRG-P1-PREPUSH-001 i ovaj sprint):

      3 LAZNA POZITIVA — "Firma doo" ⊂ "Druga firma doo" -> Intake Wizard je
        prikazivao 🚫 BLOKIRAJUCI sukob interesa za dve nepovezane firme;
      6 LAZNIH NEGATIVA — "Петар Петровић" vs "Petar Petrović" (cirilica),
        "Petrović Petar" vs "Petar Petrović" (redosled reci),
        "Delta doo" vs "Delta d.o.o." (varijanta nastavka), tipfeler, srednje
        ime. Propusten sukob je teza greska od suvisne oznake.

    `CONFLICT_WARN` je isti prag na kome kanonska implementacija unosi nalaz u
    `konflikti`; ispod njega ona vraca "clear". Severity ovde i dalje odredjuje
    ULOGA (`_CLIENT_ROLES` / `_OPPOSING_ROLES`), ne skor — taj ugovor se ne menja.
    """
    if not query or not candidate:
        return False
    return _fuzzy_score(query, candidate) >= CONFLICT_WARN


class ConflictCheckIntakeReq(BaseModel):
    novi_klijent_ime:   str = Field(..., min_length=2, max_length=200)
    novi_klijent_firma: str = Field(default="", max_length=300)
    protivna_strana:    str = Field(default="", max_length=200)
    pib:                str = Field(default="", max_length=15)


# N4-COI-001: eksplicitna stanja provere sukoba interesa.
#
# Ranije je odgovor nosio SAMO `conflict_detected`. Pretraga je mogla da padne
# na CETIRI nezavisna mesta (spoljni `except` + tri `return_exceptions=True`
# gutaca), a svaki pad je zavrsavao kao prazna lista -> `len([]) > 0` == False
# -> "Nije detektovan sukob interesa. Mozete otvoriti predmet." Odgovor pri
# padu bio je bajt-identican odgovoru pri istinski cistoj proveri.
#
# `COI_CHECK_FAILED` se NIKAD ne sme preslikati u `COI_NO_CONFLICT`. To je
# jedini ekran u proizvodu ciji je posao da advokata upozori; lazno negativan
# nalaz nosi disciplinsku odgovornost (cl. 42 Zakona o advokaturi).
#
# Nazivi i vrednosti su NAMERNO identicni kanonskom ugovoru iz
# klijenti/router.py (BETA-P0-COI) — isti pojam, isto ime, ista istina.
COI_NO_CONFLICT    = "NO_CONFLICT"
COI_CONFLICT_FOUND = "CONFLICT_FOUND"
COI_CHECK_FAILED   = "CHECK_FAILED"


async def _run_conflict_check(
    uid: str, novi_klijent_ime: str, novi_klijent_firma: str = "",
    protivna_strana: str = "", pib: str = "",
) -> dict:
    """Jezgro provere sukoba interesa. Izdvojeno iz POST /api/intake/conflict-check
    (Zero-Touch Case investigation, 2026-08-03, BETA-002/Scenario 5) da bi ga
    Smart Intake finalize (routers/smart_intake.py) mogao pozvati direktno --
    bez Request/rate-limiter-a koji HTTP endpoint zahteva, i bez duplirane
    logike (Rule Zero). Ponašanje NEPROMENJENO za postojeći endpoint, čist
    premeštaj tela funkcije.

    Proverava tri scenarija:
    1. `protivna_strana` je već vaš klijent → BLOKIRAJUCI
    2. `novi_klijent_ime` je već na suprotnoj strani nekog vašeg predmeta → BLOKIRAJUCI
    3. `novi_klijent_ime` već postoji kao klijent (duplikat) → UPOZORENJE
    """
    supa = _get_supa()

    q_novi    = _norm(f"{novi_klijent_ime} {novi_klijent_firma}".strip())
    q_novi_i  = _norm(novi_klijent_ime)
    q_firma   = _norm(novi_klijent_firma) if novi_klijent_firma else ""
    q_protiv  = _norm(protivna_strana) if protivna_strana else ""

    conflicts: list[dict] = []
    # N4-COI-001: svaki izvor koji NIJE procitan. Neprazna lista => CHECK_FAILED.
    izvori_neuspeh: list[str] = []

    try:
        # Fetch all active clients for this user
        clients_res, predmeti_res = await asyncio.gather(
            asyncio.to_thread(
                lambda: supa.table("klijenti")
                            .select("id, ime, prezime, firma, pib_encrypted")
                            .eq("user_id", uid)
                            .neq("status", "soft_deleted")
                            .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("predmeti")
                            .select("id, naziv, tuzilac, tuzeni")
                            .eq("user_id", uid)
                            .execute()
            ),
            return_exceptions=True,
        )

        # N4-COI-001: `return_exceptions=True` je ranije pretvarao pao upit u
        # praznu listu bez ijednog traga. Prazno i neuspelo NISU isto.
        if isinstance(clients_res, Exception):
            izvori_neuspeh.append("klijenti")
            logger.error("[CONFLICT-CHECK] uid=%.8s izvor 'klijenti' NIJE procitan: %s",
                         uid, clients_res)
            all_clients: list[dict] = []
        else:
            all_clients = clients_res.data or []

        if isinstance(predmeti_res, Exception):
            izvori_neuspeh.append("predmeti")
            logger.error("[CONFLICT-CHECK] uid=%.8s izvor 'predmeti' NIJE procitan: %s",
                         uid, predmeti_res)
            all_predmeti: list[dict] = []
        else:
            all_predmeti = predmeti_res.data or []

        # For clients that match, fetch their predmet_klijenti roles in parallel
        matched_client_ids: list[str] = []
        client_names: dict[str, str] = {}
        for c in all_clients:
            c_name  = _norm(f"{c.get('ime', '')} {c.get('prezime', '')}".strip())
            c_firma = _norm(c.get("firma") or "")
            # Match against either query
            #
            # Guard za poredjenje `q_protiv` protiv `c_firma` mora biti `c_firma`,
            # a ne `q_firma`. `q_firma` je firma NOVOG klijenta i nije operand tog
            # poredjenja; kad je korisnik ne unese, cela grana se preskace i klijent
            # koji je PRAVNO LICE nikad ne udje u `matched_client_ids`. Scenario 1
            # nize (isti par operanada) vec koristi ispravan guard `c_firma_norm`.
            #
            # Posledica u produkciji: klijent `firma="Druga firma doo"` vezan za
            # predmet ulogom `stranka`, upit o protivnoj strani "Druga firma doo" --
            # doslovno isto ime -- vracao je NO_CONFLICT. Propusten sukob.
            #
            # Raniji supstring matcher je ovo SLUCAJNO maskirao ("druga" je podniska
            # "druga firma doo", pa je klijent ulazio preko `c_name`); tokenski
            # matcher iz `05c1042d` tu kompenzaciju vise ne pruza.
            if (
                (q_protiv and (_name_match(q_protiv, c_name) or (c_firma and _name_match(q_protiv, c_firma)))) or
                (q_novi_i and (_name_match(q_novi_i, c_name) or (q_firma and _name_match(q_firma, c_firma))))
            ):
                matched_client_ids.append(c["id"])
                display = f"{c.get('ime', '')} {c.get('prezime', '')}".strip() or c.get("firma", "")
                client_names[c["id"]] = display

        # Fetch roles for matched clients
        roles_by_client: dict[str, list[dict]] = {}
        if matched_client_ids:
            role_results = await asyncio.gather(*[
                asyncio.to_thread(
                    lambda cid=cid: supa.table("predmet_klijenti")
                                        .select("predmet_id, uloga_klijenta")
                                        .eq("klijent_id", cid)
                                        .execute()
                )
                for cid in matched_client_ids
            ], return_exceptions=True)

            for cid, res in zip(matched_client_ids, role_results):
                if isinstance(res, Exception):
                    # N4-COI-001: uloge bas POGODJENOG klijenta nisu procitane —
                    # to je sloj u kome se blokirajuci sukob i prepoznaje.
                    if "predmet_klijenti" not in izvori_neuspeh:
                        izvori_neuspeh.append("predmet_klijenti")
                    logger.error("[CONFLICT-CHECK] uid=%.8s uloge klijenta %.8s NISU procitane: %s",
                                 uid, cid, res)
                else:
                    roles_by_client[cid] = res.data or []

        # Predmet index for names
        predmet_names: dict[str, str] = {p["id"]: p.get("naziv", "") for p in all_predmeti}

        # Evaluate each matched client
        for cid in matched_client_ids:
            c_data = next((c for c in all_clients if c["id"] == cid), {})
            c_name_norm = _norm(f"{c_data.get('ime', '')} {c_data.get('prezime', '')}".strip())
            c_firma_norm = _norm(c_data.get("firma") or "")
            display_name = client_names.get(cid, "")
            roles = roles_by_client.get(cid, [])

            for pk in roles:
                uloga = pk.get("uloga_klijenta", "")
                pred_id = pk.get("predmet_id", "")
                pred_naziv = predmet_names.get(pred_id, pred_id[:8] + "...")

                # Scenario 1: protivna_strana matches a client you already represent
                if q_protiv and (_name_match(q_protiv, c_name_norm) or (c_firma_norm and _name_match(q_protiv, c_firma_norm))):
                    if uloga in _CLIENT_ROLES:
                        conflicts.append({
                            "tip":          "opposing_already_client",
                            "severity":     "BLOKIRAJUCI",
                            "opis":         f"'{protivna_strana}' je vaš postojeći klijent ('{display_name}', uloga: {uloga}) u predmetu '{pred_naziv}'.",
                            "predmet_id":   pred_id,
                            "predmet_naziv": pred_naziv,
                            "klijent_id":   cid,
                        })

                # Scenario 2: novi klijent is already listed as opposing party
                if q_novi_i and (_name_match(q_novi_i, c_name_norm) or (q_firma and c_firma_norm and _name_match(q_firma, c_firma_norm))):
                    if uloga in _OPPOSING_ROLES:
                        conflicts.append({
                            "tip":          "client_is_opposing",
                            "severity":     "BLOKIRAJUCI",
                            "opis":         f"'{novi_klijent_ime}' se već pojavljuje kao suprotna strana ('{display_name}', uloga: {uloga}) u predmetu '{pred_naziv}'.",
                            "predmet_id":   pred_id,
                            "predmet_naziv": pred_naziv,
                            "klijent_id":   cid,
                        })
                    elif uloga in _CLIENT_ROLES:
                        conflicts.append({
                            "tip":          "duplicate_client",
                            "severity":     "UPOZORENJE",
                            "opis":         f"Već postoji klijent sličnog imena: '{display_name}' (uloga: {uloga}) u predmetu '{pred_naziv}'.",
                            "predmet_id":   pred_id,
                            "predmet_naziv": pred_naziv,
                            "klijent_id":   cid,
                        })

        # Scenario 3: check predmeti.tuzilac / tuzeni text fields against protivna_strana
        if q_protiv:
            for pred in all_predmeti:
                tuzilac = _norm(pred.get("tuzilac") or "")
                tuzeni  = _norm(pred.get("tuzeni") or "")
                if _name_match(q_protiv, tuzilac) or _name_match(q_protiv, tuzeni):
                    # Avoid duplicate if already caught via klijenti
                    already_flagged = any(
                        c["tip"] == "opposing_already_client" and c["predmet_id"] == pred["id"]
                        for c in conflicts
                    )
                    if not already_flagged:
                        which = "tužilac" if _name_match(q_protiv, tuzilac) else "tuženi"
                        conflicts.append({
                            "tip":          "opposing_in_predmet_text",
                            "severity":     "UPOZORENJE",
                            "opis":         f"'{protivna_strana}' se pojavljuje kao {which} u predmetu '{pred.get('naziv', '')}'. Proverite da li postoji sukob.",
                            "predmet_id":   pred["id"],
                            "predmet_naziv": pred.get("naziv", ""),
                            "klijent_id":   None,
                        })

    except Exception as e:
        _sentry_capture(e)
        logger.error("[CONFLICT-CHECK] uid=%.8s provera NIJE izvršena: %s", uid, e)
        # N4-COI-001: ranije se ovde samo logovalo i propadalo u granu
        # "nema sukoba". Neuspeh mora ostati neuspeh sve do potrošača.
        if "provera" not in izvori_neuspeh:
            izvori_neuspeh.append("provera")

    # Deduplicate by (tip, predmet_id, klijent_id)
    seen: set[tuple] = set()
    unique_conflicts: list[dict] = []
    for c in conflicts:
        key = (c["tip"], c.get("predmet_id", ""), c.get("klijent_id", ""))
        if key not in seen:
            seen.add(key)
            unique_conflicts.append(c)

    conflict_detected = len(unique_conflicts) > 0
    has_blocker = any(c["severity"] == "BLOKIRAJUCI" for c in unique_conflicts)

    # N4-COI-001: neuspeh ima PREDNOST nad svakim drugim ishodom. Ako ijedan
    # izvor nije pročitan, provera NIJE izvršena — bez obzira na to što je
    # preostali sloj možda vratio nula pogodaka.
    if izvori_neuspeh:
        status_provere = COI_CHECK_FAILED
    elif conflict_detected:
        status_provere = COI_CONFLICT_FOUND
    else:
        status_provere = COI_NO_CONFLICT

    if status_provere == COI_CHECK_FAILED:
        preporuka = (
            "Provera sukoba interesa NIJE izvršena (" + ", ".join(izvori_neuspeh) + "). "
            "Rezultat se ne sme tumačiti kao odsustvo sukoba."
        )
    elif has_blocker:
        preporuka = (
            "Postoji BLOKIRAJUCI sukob interesa. Ne možete zastupati ovog klijenta "
            "u predmetu gde je suprotna strana vaš postojeći klijent (čl. 42 Zakona o advokaturi)."
        )
    elif conflict_detected:
        preporuka = (
            "Detektovano je potencijalno upozorenje. Proverite da li postoji sukob interesa "
            "pre otvaranja predmeta."
        )
    else:
        preporuka = "Nije detektovan sukob interesa. Možete otvoriti predmet."

    logger.info("[CONFLICT-CHECK] uid=%.8s status=%s konflikti=%d bloker=%s neuspeli_izvori=%s",
                uid, status_provere, len(unique_conflicts), has_blocker, izvori_neuspeh)

    return {
        "conflict_detected": conflict_detected,
        "has_blocker":       has_blocker,
        "conflicts":         unique_conflicts[:20],
        "preporuka":         preporuka,
        # Bez ovog polja frontend ne može da razlikuje "nema sukoba" od
        # "nije provereno" — `!undefined` je `true`.
        "status_provere":    status_provere,
        # Koji izvor tačno nije pročitan — advokat i log vide isti razlog.
        "izvori_neuspeh":    izvori_neuspeh,
    }


@router.post("/api/intake/conflict-check")
@limiter.limit("30/minute")
async def intake_conflict_check(
    body: ConflictCheckIntakeReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Provera sukoba interesa pre otvaranja predmeta (CRM Intake Wizard,
    ime-prvo tok). Jezgro logike je u _run_conflict_check -- vidi tamo za
    tri proverena scenarija."""
    rezultat = await _run_conflict_check(
        user["user_id"], body.novi_klijent_ime, body.novi_klijent_firma,
        body.protivna_strana, body.pib,
    )
    # N4-COI-001: neuspela provera se vraća kao GREŠKA, da je uhvati i `r.ok`
    # na frontendu — ne samo semantički status. Isti ugovor kao kanonski
    # klijenti/router.py::check_conflict.
    if rezultat.get("status_provere") == COI_CHECK_FAILED:
        raise HTTPException(
            status_code=503,
            detail={
                "status_provere": COI_CHECK_FAILED,
                "izvori_neuspeh": rezultat.get("izvori_neuspeh", []),
                "poruka": "Provera sukoba interesa nije izvršena. "
                          "Rezultat se ne sme tumačiti kao odsustvo sukoba.",
            },
        )
    return rezultat


# ─── Phase 6.2 — Template predmeti ───────────────────────────────────────────

_TEMPLATES: list[dict] = [
    {
        "id":    "tpl-gradjansko-steta",
        "naziv": "Tužba za naknadu štete",
        "tip":   "gradjansko",
        "opis_template": "Predmet za naknadu materijalne i nematerijalne štete. Stranka traži naknadu za pretrpljenu štetu.",
        "vrsta_spora": "naknada štete",
        "potrebni_dokumenti": ["Zapisnik o uviđaju", "Medicinska dokumentacija", "Veštačenje štete", "Polica osiguranja"],
        "hronologija_predlozi": [
            {"dogadjaj": "Prijem predmeta i analiza dokumentacije", "vaznost": "kritičan", "days_offset": 0},
            {"dogadjaj": "Podnošenje tužbe sudu",                   "vaznost": "kritičan", "days_offset": 30},
            {"dogadjaj": "Odgovor na tužbu protivne strane",        "vaznost": "važan",    "days_offset": 60},
        ],
        "tarifa_preporuka": "T01",
    },
    {
        "id":    "tpl-radno-otkaz",
        "naziv": "Radni spor — osporavanje otkaza",
        "tip":   "radno",
        "opis_template": "Predmet za poništaj rešenja o otkazu ugovora o radu. Rok za tužbu je 60 dana od dostavljanja rešenja.",
        "vrsta_spora": "radni spor",
        "potrebni_dokumenti": ["Rešenje o otkazu", "Ugovor o radu", "Evidencija radnog vremena", "Plate i obračuni"],
        "hronologija_predlozi": [
            {"dogadjaj": "Prijem rešenja o otkazu",               "vaznost": "kritičan", "days_offset": 0},
            {"dogadjaj": "Podnošenje tužbe (rok: 60 dana)",       "vaznost": "kritičan", "days_offset": 55},
            {"dogadjaj": "Predlog za vraćanje na rad",             "vaznost": "važan",    "days_offset": 70},
        ],
        "tarifa_preporuka": "T01",
    },
    {
        "id":    "tpl-porodicno-razvod",
        "naziv": "Razvod braka i deoба imovine",
        "tip":   "porodicno",
        "opis_template": "Predmet za sporazumni ili tužbeni razvod braka, sa pitanjem starateljstva i podele zajedničke imovine.",
        "vrsta_spora": "porodično pravo",
        "potrebni_dokumenti": ["Izvod iz matične knjige venčanih", "Izvod iz matične knjige rođenih (deca)", "Imovinska izjava", "Dokazi o zajedničkoj imovini"],
        "hronologija_predlozi": [
            {"dogadjaj": "Podnošenje tužbe/predloga za razvod",    "vaznost": "kritičan", "days_offset": 0},
            {"dogadjaj": "Ročište o starateljstvu",                 "vaznost": "kritičan", "days_offset": 45},
            {"dogadjaj": "Presuda o razvodu",                       "vaznost": "važan",    "days_offset": 120},
        ],
        "tarifa_preporuka": "T27",
    },
    {
        "id":    "tpl-krivicno-odbrana",
        "naziv": "Krivična odbrana",
        "tip":   "krivicno",
        "opis_template": "Predmet krivične odbrane okrivljenog. Obuhvata prisustvo saslušanju, žalbu na rešenje o pritvoru i odbranu na glavnom pretresu.",
        "vrsta_spora": "krivično",
        "potrebni_dokumenti": ["Krivična prijava", "Rešenje o pritvoru (ako postoji)", "Optužnica", "Dokazi odbrane"],
        "hronologija_predlozi": [
            {"dogadjaj": "Prisustvo prvom saslušanju",               "vaznost": "kritičan", "days_offset": 0},
            {"dogadjaj": "Uvid u spis predmeta",                     "vaznost": "kritičan", "days_offset": 7},
            {"dogadjaj": "Priprema odbrane za glavni pretres",        "vaznost": "važan",    "days_offset": 30},
        ],
        "tarifa_preporuka": "T12",
    },
    {
        "id":    "tpl-privredno-ugovor",
        "naziv": "Privredno — spor iz ugovora",
        "tip":   "privredno",
        "opis_template": "Predmet privrednog spora po osnovu neispunjenja ili raskida ugovora između privrednih subjekata.",
        "vrsta_spora": "ugovorni spor",
        "potrebni_dokumenti": ["Ugovor", "Fakture i otpremnice", "Prepiska stranaka", "Izvod iz APR-a"],
        "hronologija_predlozi": [
            {"dogadjaj": "Slanje opomene pred utuženje",              "vaznost": "važan",    "days_offset": 0},
            {"dogadjaj": "Podnošenje tužbe privrednom sudu",          "vaznost": "kritičan", "days_offset": 15},
            {"dogadjaj": "Predlog za privremenu meru obezbeđenja",    "vaznost": "važan",    "days_offset": 7},
        ],
        "tarifa_preporuka": "T02",
    },
    {
        "id":    "tpl-upravno-zalba",
        "naziv": "Upravna žalba / tužba",
        "tip":   "upravno",
        "opis_template": "Predmet po osnovu žalbe na upravni akt ili tužbe Upravnom sudu. Rok za žalbu je 15 dana, za upravni spor 30 dana.",
        "vrsta_spora": "ostalo",
        "potrebni_dokumenti": ["Prvostepeno rešenje", "Žalba (ako postoji)", "Dokazna dokumentacija", "Potvrda o dostavljanju"],
        "hronologija_predlozi": [
            {"dogadjaj": "Prijem prvostepenog rešenja",               "vaznost": "kritičan", "days_offset": 0},
            {"dogadjaj": "Podnošenje žalbe (rok: 15 dana)",           "vaznost": "kritičan", "days_offset": 12},
            {"dogadjaj": "Tužba Upravnom sudu (rok: 30 dana)",        "vaznost": "važan",    "days_offset": 27},
        ],
        "tarifa_preporuka": "T29",
    },
    {
        "id":    "tpl-izvrsenje",
        "naziv": "Izvršni postupak",
        "tip":   "izvrsenje",
        "opis_template": "Predmet za prinudno izvršenje pravosnažne sudske odluke ili izvršne isprave.",
        "vrsta_spora": "naknada štete",
        "potrebni_dokumenti": ["Izvršna isprava (presuda/rešenje)", "Potvrda pravosnažnosti", "Dokaz o dugu", "Podaci o dužniku"],
        "hronologija_predlozi": [
            {"dogadjaj": "Predlog za izvršenje",                      "vaznost": "kritičan",    "days_offset": 0},
            {"dogadjaj": "Rešenje o izvršenju",                       "vaznost": "važan",       "days_offset": 30},
            {"dogadjaj": "Sprovođenje izvršenja",                     "vaznost": "informativan", "days_offset": 60},
        ],
        "tarifa_preporuka": "T14",
    },
]


class FromTemplateReq(BaseModel):
    template_id: str  = Field(..., min_length=3, max_length=100)
    naziv:       str  = Field(..., min_length=1, max_length=200)
    klijent_id:  Optional[str] = Field(default=None)
    opis_extra:  Optional[str] = Field(default=None, max_length=2000)


@router.get("/api/intake/templates")
async def get_intake_templates(user: dict = Depends(get_current_user)):
    """Phase 6.2 — Lista predefinisanih template predmeta."""
    return {
        "templates": [
            {
                "id":                  t["id"],
                "naziv":               t["naziv"],
                "tip":                 t["tip"],
                "vrsta_spora":         t["vrsta_spora"],
                "potrebni_dokumenti":  t["potrebni_dokumenti"],
                "tarifa_preporuka":    t["tarifa_preporuka"],
            }
            for t in _TEMPLATES
        ],
        "total": len(_TEMPLATES),
    }


@router.post("/api/intake/from-template", status_code=201)
@limiter.limit("20/minute")
async def post_from_template(
    request: Request,
    body: FromTemplateReq,
    user: dict = Depends(get_current_user),
):
    """Phase 6.2 — Kreira predmet iz template-a sa predefinisanom hronologijom."""
    uid  = user["user_id"]
    supa = _get_supa()

    tpl = next((t for t in _TEMPLATES if t["id"] == body.template_id), None)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{body.template_id}' nije pronađen.")

    opis_final = tpl["opis_template"]
    if body.opis_extra:
        opis_final = f"{opis_final}\n\n{body.opis_extra}"

    # Kreiraj predmet
    pred_res = await asyncio.to_thread(
        lambda: supa.table("predmeti").insert({
            "user_id": uid,
            "naziv":   body.naziv,
            "opis":    opis_final,
            "tip":     tpl["tip"],
            "status":  "aktivan",
        }).execute()
    )
    if not pred_res.data:
        raise HTTPException(status_code=500, detail="Greška pri kreiranju predmeta.")

    predmet = pred_res.data[0]
    predmet_id = predmet["id"]

    # Poveži klijenta ako je naveden
    if body.klijent_id:
        try:
            klijent_ok = await asyncio.to_thread(
                lambda: supa.table("klijenti").select("id").eq("id", body.klijent_id).eq("user_id", uid).maybe_single().execute()
            )
            if klijent_ok.data:
                await asyncio.to_thread(
                    lambda: supa.table("predmet_klijenti").insert({
                        "predmet_id":     predmet_id,
                        "klijent_id":     body.klijent_id,
                        "uloga_klijenta": "stranka",
                    }).execute()
                )
        except Exception:
            pass  # non-blocking

    # Dodaj predefinisanu hronologiju sa relativnim datumima
    today = date.today()
    hron_rows = []
    for h in tpl.get("hronologija_predlozi", []):
        offset = h.get("days_offset", 0)
        datum  = (today + timedelta(days=offset)).isoformat()
        hron_rows.append({
            "predmet_id": predmet_id,
            "user_id":    uid,
            "dogadjaj":   h["dogadjaj"],
            "vaznost":    h["vaznost"],
            "datum":      datum,
            "datum_iso":  datum,
            "akter":      "Template (AI)",
            # migracija 127 — W-INTAKE-TPL2: isti staticki katalog. Oznaka
            # "(AI)" u `akter` je istorijski netacna -- sadrzaj nije LLM
            # (prijavljeno kao out-of-scope).
            "izvor":      _IZVOR.IZVOR_DETERMINISTIC,
        })
    if hron_rows:
        try:
            await asyncio.to_thread(
                lambda: supa.table("predmet_hronologija").insert(hron_rows).execute()
            )
        except Exception:
            pass  # non-blocking

    logger.info("[INTAKE-TEMPLATE] uid=%.8s template=%s predmet=%s",
                uid, body.template_id, predmet_id)

    # Pokreni pipeline u pozadini (ne blokira odgovor)
    async def _run_pipeline() -> None:
        try:
            from services.case_pipeline import run_case_pipeline
            await run_case_pipeline(predmet_id, uid)
        except Exception as _pe:
            logger.warning("[INTAKE-TEMPLATE] pipeline greška predmet=%s: %s", predmet_id, _pe)

    asyncio.create_task(_run_pipeline())

    return {
        "predmet_id":           predmet_id,
        "naziv":                body.naziv,
        "tip":                  tpl["tip"],
        "template_id":          body.template_id,
        "potrebni_dokumenti":   tpl["potrebni_dokumenti"],
        "hronologija_kreirana": len(hron_rows),
        "tarifa_preporuka":     tpl["tarifa_preporuka"],
        "status":               "kreiran",
    }


# ─── Bulk Import ──────────────────────────────────────────────────────────────

class BulkImportRed(BaseModel):
    ime:             str           = Field(default="", max_length=100)
    prezime:         str           = Field(default="", max_length=100)
    firma:           str           = Field(default="", max_length=200)
    email:           str           = Field(default="", max_length=200)
    telefon:         str           = Field(default="", max_length=50)
    naziv_predmeta:  str           = Field(..., min_length=2, max_length=200)
    tip:             str           = Field(default="opsti", max_length=50)
    opis:            str           = Field(default="", max_length=2000)


class BulkImportReq(BaseModel):
    redovi: List[BulkImportRed] = Field(..., min_length=1, max_length=100)


@router.post("/api/intake/bulk-import", status_code=201)
@limiter.limit("5/minute")
async def intake_bulk_import(
    request: Request,
    body: BulkImportReq,
    user: dict = Depends(get_current_user),
):
    """Bulk import klijenata i predmeta iz parsiranog CSV-a."""
    uid  = user["user_id"]
    supa = _get_supa()

    uspeh: list[dict] = []
    greske: list[dict] = []
    # V39-C: audit događaji se SAKUPLJAJU ovde, a emituju tek posle petlje.
    # Razlog: telo svakog reda je umotano u `except Exception -> greske.append`,
    # pa bi log_action pozvan unutar petlje, ako bi ikada digao, pretvorio
    # uspešan red u prijavljenu grešku -- audit bi menjao poslovni ishod.
    # Emitovanje izvan petlje čini to strukturno nemogućim.
    audit_dogadjaji: list[dict] = []

    for i, red in enumerate(body.redovi):
        try:
            # Pronađi ili kreiraj klijenta
            klijent_id: str | None = None

            if red.email:
                existing = await asyncio.to_thread(
                    lambda e=red.email: supa.table("klijenti")
                        .select("id")
                        .eq("user_id", uid)
                        .eq("email", e[:200])
                        .neq("status", "soft_deleted")
                        .limit(1)
                        .execute()
                )
                if existing.data:
                    klijent_id = existing.data[0]["id"]

            if not klijent_id:
                kl_row: dict = {"user_id": uid, "status": "aktivan"}
                if red.ime:    kl_row["ime"]    = red.ime[:100]
                if red.prezime: kl_row["prezime"] = red.prezime[:100]
                if red.firma:  kl_row["firma"]  = red.firma[:200]
                if red.email:  kl_row["email"]  = red.email[:200]
                if red.telefon: kl_row["telefon"] = red.telefon[:50]
                kl_res = await asyncio.to_thread(
                    lambda r=kl_row: supa.table("klijenti").insert(r).execute()
                )
                if not kl_res.data:
                    raise ValueError("Kreiranje klijenta nije uspelo")
                klijent_id = kl_res.data[0]["id"]
                # Klijent je ovde definitivno kreiran i NIJE podložan poništenju:
                # kompenzujući DELETE ispod briše samo `predmeti`, nikad klijenta.
                # Zato red koji kasnije padne i dalje ostavlja ovog klijenta u
                # bazi -- audit koji bi se tada izostavio lagao bi izostankom.
                # Grana ponovnog korišćenja postojećeg klijenta (email pogodak
                # iznad) NIJE create i namerno ne emituje ništa.
                audit_dogadjaji.append({
                    "action": "klijent_create", "resource_type": "klijent",
                    "resource_id": klijent_id,
                    "metadata": {"source": "bulk_import", "red": i + 1},
                })

            # Kreiraj predmet
            pr_res = await asyncio.to_thread(
                lambda: supa.table("predmeti").insert({
                    "user_id": uid,
                    "naziv":   red.naziv_predmeta,
                    "opis":    red.opis or "",
                    "tip":     red.tip or "opsti",
                    "status":  "aktivan",
                }).execute()
            )
            if not pr_res.data:
                raise ValueError("Kreiranje predmeta nije uspelo")
            predmet_id = pr_res.data[0]["id"]

            # Poveži klijenta. Ako ovaj insert padne, predmet je već kreiran (iznad) --
            # kompenzujući delete spreči orphan predmet bez veze sa klijentom (Mission 001, 2026-08-02).
            try:
                await asyncio.to_thread(
                    lambda: supa.table("predmet_klijenti").insert({
                        "predmet_id":     predmet_id,
                        "klijent_id":     klijent_id,
                        "uloga_klijenta": "stranka",
                    }).execute()
                )
            except Exception:
                await asyncio.to_thread(
                    lambda: supa.table("predmeti").delete().eq("id", predmet_id).execute()
                )
                raise

            # Tek ovde je predmet dokazano preživeo: INSERT sam po sebi nije
            # dokaz jer ga gornji `except` poništava kompenzujućim DELETE-om.
            # Emitovanje odmah posle INSERT-a tvrdilo bi kreiranje predmeta koji
            # u bazi više ne postoji. Ista akcija/oblik kao postojeća dva
            # producera (intake wizard, api.py::kreiraj_predmet), samo drugi
            # `source`. `klijent_id` u metadata je ONAJ stvarno upisan u
            # predmet_klijenti -- postojeći ili novi, zavisno od grane iznad.
            audit_dogadjaji.append({
                "action": "predmet_create", "resource_type": "predmet",
                "resource_id": predmet_id,
                "metadata": {"naziv": red.naziv_predmeta, "tip": red.tip or "opsti",
                             "source": "bulk_import", "klijent_id": klijent_id},
            })

            uspeh.append({"red": i + 1, "predmet_id": predmet_id, "naziv": red.naziv_predmeta})

        except Exception as e:
            greske.append({"red": i + 1, "naziv": red.naziv_predmeta, "greska": str(e)[:200]})

    # Jedan zapis po STVARNOM poslovnom događaju, nikad jedan agregatni po
    # importu. Redosled emitovanja prati redosled redova.
    from shared.audit_immutable import log_action
    _ip = request.client.host if request.client else None
    for _dog in audit_dogadjaji:
        await log_action(_dog["action"], user_id=uid,
                         resource_type=_dog["resource_type"],
                         resource_id=_dog["resource_id"],
                         ip=_ip, metadata=_dog["metadata"])

    logger.info("[BULK-IMPORT] uid=%.8s uspeh=%d greske=%d", uid, len(uspeh), len(greske))
    return {
        "uspeh":         len(uspeh),
        "greske_broj":   len(greske),
        "greske":        greske[:20],
        "predmeti":      uspeh,
    }


# ── Intake History ─────────────────────────────────────────────────────────────
@router.get("/api/intake/history")
async def intake_history(
    limit: int = 15,
    user: dict = Depends(get_current_user),
):
    """Poslednjih N predmeta koje je korisnik kreirao — za History sekciju u wizardu."""
    supa = _get_supa()
    uid  = user["user_id"]

    r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id, naziv, status, tip, created_at, predmet_klijenti(klijenti(ime, prezime, firma))")
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(max(1, min(limit, 30)))
            .execute()
    )

    items = []
    for p in (r.data or []):
        klijent = "—"
        veze = p.get("predmet_klijenti") or []
        if veze:
            k = veze[0].get("klijenti") or {}
            if k.get("firma"):
                klijent = k["firma"]
            elif k.get("prezime"):
                klijent = f"{(k.get('ime') or '').strip()} {k['prezime']}".strip()

        items.append({
            "id":      p["id"],
            "naziv":   p["naziv"],
            "status":  p.get("status", "aktivan"),
            "klijent": klijent,
            "datum":   (p.get("created_at") or "")[:10],
        })

    return {"items": items}
