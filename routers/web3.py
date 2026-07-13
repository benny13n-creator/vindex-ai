# -*- coding: utf-8 -*-
"""
Vindex AI — routers/web3.py

F11: Digitalna imovina & Usklađenost moduli (PRO only)
  F11.1 — Web3 pretraga (ZDI/MiCA namespace)
  F11.2 — Compliance checker
  F11.3 — Whitepaper analiza
  F11.4 — MiCA Readiness Score
  F11.5 — ZDI License Checker
  F11.6 — AML/KYC Auditor
  F11.7 — Documentation Health Score (spremnost za due diligence, ne RAG-grounded)
  F11.8 — Exchange Reporting Simulator (opšta CARF/DAC8-tipa edukacija, ne RAG-grounded,
          namerno bez citiranja konkretnih članova — ti dokumenti nisu ingestovani)

F12: Smart Contract Legal Analyzer (PRO, 5 kredita)

Na mapi puta (blokirano na sadržaj/spoljni API, ne na kod — vidi audit sesije):
  CARF/DAC8 Readiness Analyzer, Wallet Provenance Report, Source-of-Funds paket,
  Cross-Jurisdiction Crypto Tax Intelligence.
"""
import asyncio
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from shared.deps import _audit, _deduct_credit, _deduct_n_credits, _get_supa, _is_founder, require_pro
from shared.rate import limiter
from web3_compliance import (
    web3_pretraga_sync as _web3_pretraga,
    compliance_check_sync as _compliance_check,
    whitepaper_check_sync as _whitepaper_check,
    mica_readiness_score_sync as _mica_readiness_score,
    zdi_license_checker_sync as _zdi_license_checker,
    aml_kyc_auditor_sync as _aml_kyc_auditor,
    documentation_health_score_sync as _documentation_health_score,
    exchange_reporting_simulator_sync as _exchange_reporting_simulator,
)

router = APIRouter()

logger = __import__("logging").getLogger("vindex.api")


class StrategijaRequest(BaseModel):
    tekst: str = Field(..., max_length=20000)


# ── F11: Web3/MiCA Compliance ─────────────────────────────────────────────────

@router.post("/web3/pretraga")  # F11.1
@limiter.limit("10/minute")
async def post_web3_pretraga(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F11.1 — Web3/MiCA RAG pretraga nad ZDI + MiCA namespacom (PRO)."""
    if len(req.tekst.strip()) < 10:
        raise HTTPException(status_code=422, detail="Upit mora imati najmanje 10 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "web3_pretraga", ""))
    try:
        rezultat = await asyncio.to_thread(
            _web3_pretraga, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "web3_pretraga", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F11] web3_pretraga greška")
        raise HTTPException(status_code=500, detail="Greška pri pretrazi ZDI/MiCA baze. Pokušajte ponovo.")


@router.post("/web3/compliance")  # F11.2
@limiter.limit("5/minute")
async def post_compliance_check(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F11.2 — Web3 Compliance Checker (ZDI + MiCA) (PRO)."""
    if len(req.tekst.strip()) < 30:
        raise HTTPException(status_code=422, detail="Opis aktivnosti mora imati najmanje 30 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "compliance_check", ""))
    try:
        rezultat = await asyncio.to_thread(
            _compliance_check, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "compliance_check", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F11] compliance_check greška")
        raise HTTPException(status_code=500, detail="Greška pri compliance analizi. Pokušajte ponovo.")


@router.post("/web3/whitepaper")  # F11.3
@limiter.limit("5/minute")
async def post_whitepaper_check(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F11.3 — Whitepaper analiza po ZDI + MiCA zahtevima (PRO)."""
    if len(req.tekst.strip()) < 100:
        raise HTTPException(status_code=422, detail="Whitepaper mora imati najmanje 100 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "whitepaper_check", ""))
    try:
        rezultat = await asyncio.to_thread(
            _whitepaper_check, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "whitepaper_check", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F11] whitepaper_check greška")
        raise HTTPException(status_code=500, detail="Greška pri analizi whitepapera. Pokušajte ponovo.")


@router.post("/web3/mica-score")  # F11.4
@limiter.limit("5/minute")
async def post_mica_score(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F11.4 — MiCA Readiness Score — scoring projekta po MiCA/ZDI (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Opis projekta mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "mica_score", ""))
    try:
        rezultat = await asyncio.to_thread(
            _mica_readiness_score, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {
            "score_data": rezultat["score_data"],
            "objasnjenje": rezultat["objasnjenje"],
            "modul": "mica_score",
            "credits_remaining": max(preostalo, 0),
        }
    except Exception:
        logger.exception("[F11] mica_score greška")
        raise HTTPException(status_code=500, detail="Greška pri MiCA scoring analizi. Pokušajte ponovo.")


@router.post("/web3/license-check")  # F11.5
@limiter.limit("10/minute")
async def post_license_check(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F11.5 — ZDI License Checker — provera potrebnih dozvola (PRO)."""
    if len(req.tekst.strip()) < 20:
        raise HTTPException(status_code=422, detail="Opis aktivnosti mora imati najmanje 20 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "license_check", ""))
    try:
        rezultat = await asyncio.to_thread(
            _zdi_license_checker, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {
            "license_data": rezultat["license_data"],
            "objasnjenje": rezultat["objasnjenje"],
            "modul": "license_check",
            "credits_remaining": max(preostalo, 0),
        }
    except Exception:
        logger.exception("[F11] license_check greška")
        raise HTTPException(status_code=500, detail="Greška pri proveri licence. Pokušajte ponovo.")


@router.post("/web3/aml-audit")  # F11.6
@limiter.limit("5/minute")
async def post_aml_audit(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F11.6 — AML/KYC Auditor — audit usklađenosti politike (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Tekst politike mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "aml_audit", ""))
    try:
        rezultat = await asyncio.to_thread(
            _aml_kyc_auditor, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {
            "audit_data": rezultat["audit_data"],
            "objasnjenje": rezultat["objasnjenje"],
            "modul": "aml_audit",
            "credits_remaining": max(preostalo, 0),
        }
    except Exception:
        logger.exception("[F11] aml_audit greška")
        raise HTTPException(status_code=500, detail="Greška pri AML/KYC auditu. Pokušajte ponovo.")


@router.post("/web3/health-score")  # F11.7
@limiter.limit("5/minute")
async def post_documentation_health_score(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F11.7 — Documentation Health Score: spremnost dokumentacije za regulatorni/bankarski due diligence (PRO)."""
    if len(req.tekst.strip()) < 30:
        raise HTTPException(status_code=422, detail="Opis dokumentacije mora imati najmanje 30 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "health_score", ""))
    try:
        rezultat = await asyncio.to_thread(
            _documentation_health_score, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {
            "health_data": rezultat["health_data"],
            "objasnjenje": rezultat["objasnjenje"],
            "modul": "health_score",
            "credits_remaining": max(preostalo, 0),
        }
    except Exception:
        logger.exception("[F11] health_score greška")
        raise HTTPException(status_code=500, detail="Greška pri proceni spremnosti dokumentacije. Pokušajte ponovo.")


@router.post("/web3/reporting-simulator")  # F11.8
@limiter.limit("10/minute")
async def post_reporting_simulator(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F11.8 — Exchange Reporting Simulator: opšta edukacija o obrascima CARF/DAC8-tipa izveštavanja (PRO)."""
    if len(req.tekst.strip()) < 20:
        raise HTTPException(status_code=422, detail="Opis scenarija mora imati najmanje 20 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "reporting_simulator", ""))
    try:
        rezultat = await asyncio.to_thread(
            _exchange_reporting_simulator, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "reporting_simulator", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F11] reporting_simulator greška")
        raise HTTPException(status_code=500, detail="Greška pri simulaciji izveštavanja. Pokušajte ponovo.")


# ── F12: Smart Contract Legal Analyzer ───────────────────────────────────────

_SC_SYSTEM_PROMPT = """\
Ti si pravni analitičar specijalizovan za digitalnu imovinu i blockchain tehnologije.
Analiziraš Solidity pametne ugovore isključivo iz pravne perspektive.
NISI alat za bezbednosni audit koda niti za tehničko objašnjavanje Solidity funkcija.

MISIJA: Iz strukture ugovora izvesti pravno relevantne posledice — ne opisivati kod.
Ciljna publika su srpski advokati, compliance profesionalci i regulatori koji ne poznaju Solidity.
Sav output mora biti na srpskom jeziku (ekavica), jasan, bez tehničkog žargona.

APSOLUTNA PRAVILA (nikada ne kršiti):
1. Ne iznosiš pravne zaključke — samo indikatore, faktore i posledice
2. Ne nagađaš poslovni model, emitenta ni regulatorni status
3. Ne koristiš procente poverenja — koristi: DA / MOGUĆE / NE / NEDOVOLJNO PODATAKA
4. Ne tvrdiš da je nešto nezakonito bez jasne osnove direktno u kodu
5. Jasno razlikuješ: DOKAZIVO IZ KODA | MOGUĆE NA OSNOVU KODA | NEDOVOLJNO PODATAKA
6. Svaki regulatorni navod mora citirati konkretan član zakona
7. Proxy/upgradeable ugovori uvek dobijaju posebno upozorenje

PRIORITET RIZIKA — navedi pravni_rizici ovim redosledom (od najvažnijeg):
1. Centralizovana kontrola nad sistemom
2. Mogućnost izmene ekonomskih parametara
3. Neograničeno mintovanje bez supply cap-a
4. Upravljanje korisničkim sredstvima od strane vlasnika
5. Zaključavanje sredstava bez mehanizma ranijeg izlaska
6. Odsustvo zaštitnih mehanizama (pause, emergency withdraw)

Vraćaš ISKLJUČIVO validan JSON. Bez markdown. Bez teksta van JSON strukture.

JSON SCHEMA:
{
  "pravni_sazetak": ["string"],
  "poslovna_funkcija": {
    "opis": "string",
    "tip_ugovora": "string"
  },
  "administrativna_ovlascenja": {
    "nivo": "VISOKA ili SREDNJA ili NISKA ili NEMA",
    "privilegovane_uloge": ["string"],
    "privilegovane_funkcije": [
      {
        "naziv": "string",
        "ovlasceni_akter": "string",
        "poslovna_posledica": "string",
        "pravna_posledica": "string"
      }
    ]
  },
  "centralizacija": {
    "nivo": "VISOKA ili SREDNJA ili NISKA",
    "obrazlozenje": "string",
    "faktori": ["string"]
  },
  "kljucne_radnje": [
    {
      "radnja": "string",
      "poslovna_funkcija": "string",
      "pravni_karakter": "string",
      "moguci_pravni_dogadjaji": ["string"]
    }
  ],
  "pravni_indikatori": {
    "pruzanje_finansijske_usluge": {
      "indikator": "DA ili MOGUĆE ili NE ili NEDOVOLJNO PODATAKA",
      "obrazlozenje": "string",
      "faktori_za": ["string"],
      "faktori_protiv": ["string"]
    },
    "upravljanje_tudom_imovinom": {
      "indikator": "DA ili MOGUĆE ili NE ili NEDOVOLJNO PODATAKA",
      "obrazlozenje": "string",
      "faktori_za": ["string"],
      "faktori_protiv": ["string"]
    },
    "investiciona_shema": {
      "indikator": "DA ili MOGUĆE ili NE ili NEDOVOLJNO PODATAKA",
      "obrazlozenje": "string",
      "faktori_za": ["string"],
      "faktori_protiv": ["string"]
    },
    "anonimnost_ucesnika": {
      "indikator": "DA ili MOGUĆE ili NE ili NEDOVOLJNO PODATAKA",
      "obrazlozenje": "string"
    }
  },
  "aml_kyc": {
    "nivo_rizika": "NIZAK ili SREDNJI ili VISOK",
    "obrazlozenje": "string",
    "karakteristike": ["string"],
    "napomena": "AML obaveze se tipično procenjuju na nivou platforme ili operatera sistema, a ne samog ugovora."
  },
  "klasifikacija_tokena": [
    {
      "kategorija": "string",
      "status": "DA ili MOGUĆE ili NEDOVOLJNO PODATAKA",
      "faktori_za": ["string"],
      "faktori_protiv": ["string"]
    }
  ],
  "pravni_rizici": [
    {
      "rizik": "string (jasna rečenica — pravna posledica, ne opis koda)",
      "ozbiljnost": "KRITIČAN ili VISOK ili SREDNJI ili NIZAK",
      "obrazlozenje": "string"
    }
  ],
  "regulatorna_relevantnost": [
    {
      "propis": "string",
      "relevantni_clanovi": [
        {
          "clan": "string",
          "razlog_aktivacije": "string",
          "relevantna_funkcija": "string"
        }
      ],
      "nivo_relevantnosti": "VISOK ili SREDNJI ili MOGUĆ",
      "obrazlozenje": "string"
    }
  ],
  "offchain_zavisnosti": [
    {
      "zavisnost": "string",
      "napomena": "string"
    }
  ],
  "proxy_upozorenje": "string ili null",
  "confidence_tier": "HIGH ili MEDIUM ili LOW",
  "limitacije_analize": ["string"]
}

PRAVILA ZA confidence_tier:
- HIGH: kompletan source code, jasna logika, nema proxy pattern-a
- MEDIUM: ima proxy/upgradeable komponenti ili je logika fragmentirana
- LOW: minimalan source, samo interfejsi, ili kompleksan proxy lanac"""


_DEFAULT_OFFCHAIN_PLACEHOLDER = {
    "zavisnost": "Nema identifikovanih eksplicitnih off-chain zavisnosti u dostavljenom kodu",
    "napomena": "Stvarna primena (frontend, deployment proces, upravljanje privatnim ključevima) može uvesti dodatne zavisnosti koje nisu predmet ove analize."
}

_AML_KYC_NAPOMENA = (
    " AML obaveze se tipično procenjuju na nivou platforme ili operatera sistema "
    "(koji mora imati politiku AML/KYC), a ne na nivou samog pametnog ugovora koji nema "
    "mehanizam za identifikaciju korisnika."
)

_LOCK_WITHOUT_EXIT_RISK = {
    "rizik": "Ne postoji mehanizam za prevremeni povraćaj sredstava u vanrednim okolnostima.",
    "ozbiljnost": "VISOK",
    "obrazlozenje": (
        "Korisnička sredstva su zaključana do isteka perioda bez mogućnosti ranijeg povlačenja, "
        "čak ni u slučaju kompromitacije ključa ili nestanka administratora."
    ),
}

_UNRESTRICTED_MINT_RISK = {
    "rizik": "Vlasnik ima diskreciono pravo neograničenog povećanja ponude tokena (mint bez supply cap-a).",
    "ozbiljnost": "VISOK",
    "obrazlozenje": (
        "Funkcija mint() je dostupna vlasniku bez vidljivog gornjeg limita ukupne ponude, "
        "što može uticati na vrednost postojećih tokena i predstavlja rizik za korisnike/investitore."
    ),
}


def _sc_extract_version(source: str) -> str:
    import re as _re
    m = _re.search(r'pragma\s+solidity\s+([^;]+);', source)
    return m.group(1).strip() if m else "nepoznata"


def _sc_extract_name(source: str) -> str:
    import re as _re
    m = _re.search(r'\bcontract\s+(\w+)', source)
    return m.group(1) if m else "Nepoznat"


def _sc_detect_proxy(source: str) -> bool:
    import re as _re
    return any([
        'delegatecall' in source,
        'upgradeable' in source.lower(),
        bool(_re.search(r'\bProxy\w*\b', source)),
        bool(_re.search(r'function\s+implementation\s*\(\s*\)', source)),
    ])


def _sc_detect_lock_without_exit(source: str) -> bool:
    import re as _re
    has_owner_control  = bool(_re.search(r'(onlyOwner|msg\.sender\s*==\s*owner|require\s*\(\s*msg\.sender\s*==\s*owner)', source, _re.IGNORECASE))
    has_lock_period    = bool(_re.search(r'(lockPeriod|lockUntil|lockTime|unlockTime|lock_period)', source, _re.IGNORECASE))
    has_emergency_exit = bool(_re.search(r'(emergencyWithdraw|pause\(|emergencyStop|circuitBreaker|emergency_withdraw|whenNotPaused)', source, _re.IGNORECASE))
    return has_owner_control and has_lock_period and not has_emergency_exit


def _sc_detect_unrestricted_mint(source: str) -> bool:
    import re as _re
    has_mint = bool(_re.search(r'\bmint\s*\(', source, _re.IGNORECASE))
    has_owner_only = bool(_re.search(r'(onlyOwner|msg\.sender\s*==\s*owner)', source, _re.IGNORECASE))
    has_supply_cap = bool(_re.search(r'(maxSupply|MAX_SUPPLY|totalSupply\s*\+\s*\w+\s*<=|cap\s*=)', source, _re.IGNORECASE))
    return has_mint and has_owner_only and not has_supply_cap


class SmartContractReq(BaseModel):
    solidity_source: str = Field(..., min_length=1, max_length=50000)

    @field_validator("solidity_source")
    @classmethod
    def ocisti(cls, v: str) -> str:
        return v.strip()


@router.post("/web3/analiziraj-ugovor")  # F12
@limiter.limit("3/minute")
async def post_analiziraj_ugovor(
    req: SmartContractReq,
    request: Request,
    user: dict = Depends(require_pro),
):
    """F12 — Smart Contract Legal Analyzer: Solidity izvorni kod → strukturirana pravna analiza (PRO, 5 kredita)."""
    import re as _re
    import json as _json

    source = req.solidity_source

    if len(source.split()) < 20:
        raise HTTPException(
            status_code=400,
            detail="Dostavljeni kod je previše kratak za pouzdanu pravnu analizu.",
        )

    email = user.get("email", "")
    if not _is_founder(email):
        from shared.deps import _get_credits
        credits = await asyncio.to_thread(_get_credits, user["user_id"])
        if credits < 5:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "NO_CREDITS",
                    "message": "Nemate dovoljno kredita za ovu analizu. Potrebno je 5 kredita.",
                    "credits_remaining": credits,
                },
            )
        # Deduciraj kredite PRE GPT poziva (isti pattern kao u /api/pitanje)
        preostalo = await asyncio.to_thread(_deduct_n_credits, user["user_id"], email, 5)
    else:
        preostalo = 9999

    solidity_version  = _sc_extract_version(source)
    contract_name     = _sc_extract_name(source)
    is_proxy_detected = _sc_detect_proxy(source)
    is_lock_without_exit = _sc_detect_lock_without_exit(source)
    is_unrestricted_mint = _sc_detect_unrestricted_mint(source)

    asyncio.create_task(_audit(user["user_id"], "smart_contract_analiza", ""))

    _static_note = (
        "NAPOMENA IZ STATIČKE ANALIZE: Kod sadrži funkcije sa owner-only kontrolom i mehanizam "
        "zaključavanja sredstava na vremenski period, ali ne sadrži prepoznatljiv emergency/pause/withdraw "
        "mehanizam za vanredne situacije. Ako ovo potvrdiš pregledom koda, OBAVEZNO uključi odgovarajući "
        "rizik u pravni_rizici sa ozbiljnost \"VISOK\", koji opisuje da korisnička sredstva mogu ostati "
        "nedostupna do isteka perioda zaključavanja bez mogućnosti ranijeg povlačenja u vanrednim okolnostima "
        "(greška, kompromitovan ključ, nestanak administratora).\n\n"
        if is_lock_without_exit else ""
    )
    if is_unrestricted_mint:
        _static_note += (
            "NAPOMENA IZ STATIČKE ANALIZE: Kod sadrži funkciju mint() ograničenu na vlasnika"
            " (onlyOwner ili ekvivalentno), bez vidljivog gornjeg limita ukupne ponude (max supply / cap)."
            " Ako ovo potvrdiš pregledom koda, OBAVEZNO uključi odgovarajući rizik u pravni_rizici sa"
            " ozbiljnost \"VISOK\", koji opisuje da vlasnik ima diskreciono pravo neograničenog povećanja"
            " ponude tokena, što može uticati na vrednost postojećih tokena i predstavljati rizik za"
            " korisnike/investitore.\n\n"
        )
    user_msg = (
        f"Analiziraj sledeći Solidity pametni ugovor:\n\n"
        f"Naziv ugovora (auto-extracted): {contract_name}\n"
        f"Verzija Solidity: {solidity_version}\n"
        f"Proxy pattern detektovan: {'Da' if is_proxy_detected else 'Ne'}\n\n"
        f"{_static_note}"
        f"--- POČETAK KODA ---\n{source}\n--- KRAJ KODA ---"
    )

    def _call_gpt(messages):
        from openai import OpenAI as _OAI
        client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            max_tokens=4000,
            messages=messages,
        )
        content    = (resp.choices[0].message.content or "").strip()
        tokens_out = resp.usage.total_tokens if resp.usage else 0
        return content, tokens_out

    def _parse_json(text: str) -> Optional[dict]:
        text = text.strip()
        text = _re.sub(r'^```[a-zA-Z]*\n?', '', text)
        text = _re.sub(r'\n?```$', '', text.strip()).strip()
        try:
            return _json.loads(text)
        except Exception:
            return None

    try:
        messages = [
            {"role": "system", "content": _SC_SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ]
        raw_content, tokens_used = await asyncio.to_thread(_call_gpt, messages)
    except Exception:
        logger.exception("[F12] GPT poziv neuspešan")
        raise HTTPException(status_code=500, detail="Greška na serveru. Pokušajte ponovo.")

    analysis_result = _parse_json(raw_content)
    if analysis_result is None:
        try:
            retry_messages = messages + [
                {"role": "assistant", "content": raw_content},
                {"role": "user",      "content": "Greška: odgovor nije validan JSON. Vrati SAMO čist JSON bez markdown-a, komentara ili teksta izvan JSON strukture."},
            ]
            raw_content2, tokens_used2 = await asyncio.to_thread(_call_gpt, retry_messages)
            tokens_used += tokens_used2
            analysis_result = _parse_json(raw_content2)
        except Exception:
            logger.exception("[F12] Retry GPT neuspešan")

    if analysis_result is None:
        raise HTTPException(
            status_code=422,
            detail="Analiza nije mogla biti generisana. Proverite da li je dostavljen validan Solidity kod.",
        )

    confidence_tier = str(analysis_result.get("confidence_tier", "LOW")).upper()
    if is_proxy_detected and confidence_tier == "HIGH":
        confidence_tier = "MEDIUM"
        analysis_result["confidence_tier"] = "MEDIUM"

    if not analysis_result.get("offchain_zavisnosti"):
        analysis_result["offchain_zavisnosti"] = [_DEFAULT_OFFCHAIN_PLACEHOLDER]

    _anon = (analysis_result.get("pravni_indikatori") or {}).get("anonimnost_ucesnika", {})
    if isinstance(_anon, dict):
        _obr = _anon.get("obrazlozenje", "")
        _obr_lower = _obr.lower()
        _already_covers_aml = (
            ("aml" in _obr_lower and "kyc" in _obr_lower)
            or ("platform" in _obr_lower and ("posrednik" in _obr_lower or "operater" in _obr_lower))
        )
        if not _already_covers_aml:
            _anon["obrazlozenje"] = _obr.rstrip(".") + "." + _AML_KYC_NAPOMENA

    if is_lock_without_exit:
        _existing = analysis_result.get("pravni_rizici", [])
        def _is_lock_exit_risk(text: str) -> bool:
            t = text.lower()
            return (
                any(kw in t for kw in ["povraćaj", "povracaj", "prevremen", "izlaz", "zaključan", "zakljucan"])
                and any(kw in t for kw in ["sredstav", "imovin"])
            )
        if not any(_is_lock_exit_risk(r.get("rizik", "")) for r in _existing):
            analysis_result["pravni_rizici"] = _existing + [_LOCK_WITHOUT_EXIT_RISK]

    if is_unrestricted_mint:
        _existing = analysis_result.get("pravni_rizici", [])
        def _is_mint_risk(text: str) -> bool:
            t = text.lower()
            if any(kw in t for kw in ["mint", "emisij", "emitova"]):
                return True
            if "ponude tokena" in t and any(kw in t for kw in ["neograničen", "diskrecion"]):
                return True
            return False
        if not any(_is_mint_risk(r.get("rizik", "")) for r in _existing):
            analysis_result["pravni_rizici"] = _existing + [_UNRESTRICTED_MINT_RISK]

    def _save():
        _get_supa().table("smart_contract_analyses").insert({
            "user_id":           user["user_id"],
            "contract_source":   source,
            "contract_name":     contract_name,
            "solidity_version":  solidity_version,
            "analysis_result":   analysis_result,
            "is_proxy_detected": is_proxy_detected,
            "confidence_tier":   confidence_tier,
            "tokens_used":       tokens_used,
        }).execute()

    try:
        await asyncio.to_thread(_save)
    except Exception:
        logger.exception("[F12] Greška pri čuvanju analize u Supabase — nastavljam")

    return {
        "modul":             "smart_contract",
        "contract_name":     contract_name,
        "solidity_version":  solidity_version,
        "is_proxy_detected": is_proxy_detected,
        "analysis_result":   analysis_result,
        "credits_remaining": max(preostalo, 0),
    }
