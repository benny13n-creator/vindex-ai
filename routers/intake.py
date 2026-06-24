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
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.intake")
router = APIRouter(tags=["intake"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

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
4. Jezik: srpski ekavica.
5. potrebni_dokumenti: navedi 2-5 dokumenata tipičnih za ovu vrstu spora."""


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
            r = await oai.chat.completions.create(
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


@router.post("/api/intake/ekstrakcija")
@limiter.limit("20/minute")
async def intake_ekstrakcija(
    body: EkstrakcijReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Ekstrahuje ključne podatke za novi predmet iz opisa problema i opcionalnih nalaza."""
    nalazi = body.analiza_results or []
    result = await _call_ekstrakcija(body.opis_problema, nalazi)

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

    try:
        await asyncio.to_thread(
            lambda: supa.table("predmet_klijenti").insert({
                "predmet_id":     predmet_id,
                "klijent_id":     body.klijent_id,
                "uloga_klijenta": "stranka",
                "user_id":        uid,
            }).execute()
        )
    except Exception as e:
        logger.warning("[INTAKE] predmet_klijenti insert greška: %s", e)

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
                    "vaznost":    "bitan",
                    "akter":      "Intake Wizard (AI)",
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

    logger.info("[INTAKE] predmet=%s uid=%.8s rok=%s docs=%d", predmet_id, uid, rok_dodat, docs_linked)
    return {
        "success":      True,
        "predmet_id":   predmet_id,
        "predmet":      predmet,
        "rok_dodat":    rok_dodat,
        "docs_linked":  docs_linked,
    }


# ─── Conflict of Interest check ───────────────────────────────────────────────

_OPPOSING_ROLES = frozenset({
    "protivna_strana", "protivna_stranka", "tuzeni", "advokat_protivne",
})
_CLIENT_ROLES = frozenset({"stranka", "tuzilac"})


def _norm(s: str) -> str:
    """Lowercase, remove diacritics, collapse whitespace."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _name_match(query: str, candidate: str) -> bool:
    """Substring match in either direction (catches partial names)."""
    if not query or not candidate:
        return False
    return query in candidate or candidate in query


class ConflictCheckIntakeReq(BaseModel):
    novi_klijent_ime:   str = Field(..., min_length=2, max_length=200)
    novi_klijent_firma: str = Field(default="", max_length=300)
    protivna_strana:    str = Field(default="", max_length=200)
    pib:                str = Field(default="", max_length=15)


@router.post("/api/intake/conflict-check")
@limiter.limit("30/minute")
async def intake_conflict_check(
    body: ConflictCheckIntakeReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Provera sukoba interesa pre otvaranja predmeta.

    Proverava tri scenarija:
    1. `protivna_strana` je već vaš klijent → BLOKIRAJUCI
    2. `novi_klijent_ime` je već na suprotnoj strani nekog vašeg predmeta → BLOKIRAJUCI
    3. `novi_klijent_ime` već postoji kao klijent (duplikat) → UPOZORENJE
    """
    uid  = user["user_id"]
    supa = _get_supa()

    q_novi    = _norm(f"{body.novi_klijent_ime} {body.novi_klijent_firma}".strip())
    q_novi_i  = _norm(body.novi_klijent_ime)
    q_firma   = _norm(body.novi_klijent_firma) if body.novi_klijent_firma else ""
    q_protiv  = _norm(body.protivna_strana) if body.protivna_strana else ""

    conflicts: list[dict] = []

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

        all_clients: list[dict] = [] if isinstance(clients_res, Exception) else (clients_res.data or [])
        all_predmeti: list[dict] = [] if isinstance(predmeti_res, Exception) else (predmeti_res.data or [])

        # For clients that match, fetch their predmet_klijenti roles in parallel
        matched_client_ids: list[str] = []
        client_names: dict[str, str] = {}
        for c in all_clients:
            c_name  = _norm(f"{c.get('ime', '')} {c.get('prezime', '')}".strip())
            c_firma = _norm(c.get("firma") or "")
            # Match against either query
            if (
                (q_protiv and (_name_match(q_protiv, c_name) or (q_firma and _name_match(q_protiv, c_firma)))) or
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
                if not isinstance(res, Exception):
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
                            "opis":         f"'{body.protivna_strana}' je vaš postojeći klijent ('{display_name}', uloga: {uloga}) u predmetu '{pred_naziv}'.",
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
                            "opis":         f"'{body.novi_klijent_ime}' se već pojavljuje kao suprotna strana ('{display_name}', uloga: {uloga}) u predmetu '{pred_naziv}'.",
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
                            "opis":         f"'{body.protivna_strana}' se pojavljuje kao {which} u predmetu '{pred.get('naziv', '')}'. Proverite da li postoji sukob.",
                            "predmet_id":   pred["id"],
                            "predmet_naziv": pred.get("naziv", ""),
                            "klijent_id":   None,
                        })

    except Exception as e:
        logger.error("[CONFLICT-CHECK] uid=%.8s greška: %s", uid, e)

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

    if has_blocker:
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

    logger.info("[CONFLICT-CHECK] uid=%.8s konflikti=%d bloker=%s", uid, len(unique_conflicts), has_blocker)

    return {
        "conflict_detected": conflict_detected,
        "has_blocker":       has_blocker,
        "conflicts":         unique_conflicts[:20],
        "preporuka":         preporuka,
    }


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
            await asyncio.to_thread(
                lambda: supa.table("predmet_klijenti").insert({
                    "predmet_id":     predmet_id,
                    "klijent_id":     body.klijent_id,
                    "user_id":        uid,
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
