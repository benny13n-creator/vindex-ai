# -*- coding: utf-8 -*-
"""
Vindex AI — routers/oblasti.py

Phase 5.1: Više pravnih oblasti — dedicirani AI asistenti za:
  • Krivično pravo  (KZ + ZKP)
  • Privredno pravo (ZPD + ZOO + Zakon o stečaju)
  • Radno pravo     (ZR + ZBZO)

Endpoints:
  POST /api/oblasti/krivicno   — krivično pravo Q&A
  POST /api/oblasti/privredno  — privredno pravo Q&A
  POST /api/oblasti/radno      — radno pravo Q&A

Svaki endpoint koristi isti RAG pipeline (retrieve_documents) ali sa
specijalizovanim system promptom prilagođenim datoj pravnoj oblasti.
Ne dira: /api/pitanje, SYSTEM_PROMPT_PARNICA, klasifikuj_pitanje.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.oblasti")
router = APIRouter(tags=["oblasti"])

# ─── Konstante ───────────────────────────────────────────────────────────────

_DISCLAIMER = (
    "\n\n---\n\n"
    "⚠️ **Pravna napomena:** Vindex AI pruža informacije zasnovane na zakonskim "
    "tekstovima Republike Srbije i ne predstavlja pravni savet. Ovaj odgovor ne "
    "zamenjuje konsultaciju sa licenciranim advokatom. Pre donošenja bilo kakvih "
    "pravnih odluka, obratite se stručnjaku."
)

_ANTIFAB = (
    "\n\nZABRANJENO: Ne smeš generisati tvrdnje o sadržaju konkretnih članova zakona koji "
    "NISU prisutni u dostavljenom kontekstu. Ako pitanje implicira određeni član a taj "
    "član nije u kontekstu, navedi to eksplicitno umesto da generišeš sadržaj."
)

# ─── System prompti po oblasti ───────────────────────────────────────────────

SYSTEM_PROMPT_KRIVICNO = """Ti si Vindex AI — specijalizovani pravni sistem za krivično pravo Republike Srbije.
Korisnici su advokati odbrane, javni tužioci i sudije koji proveravaju svaki tvoj zaključak.
Jedna netačnost u krivičnopravnoj materiji = ozbiljna posledica po klijenta.

PRIMARNI IZVORI — PRIMENJUJ ISKLJUČIVO ove zakone:
→ KZ  (Krivični zakonik, Sl. glasnik RS br. 85/2005, 88/2005, 107/2005, 72/2009, 111/2009, 121/2012, 104/2013, 108/2014, 94/2016, 35/2019) — krivična dela, sankcije, odgovornost
→ ZKP (Zakonik o krivičnom postupku, Sl. glasnik RS br. 72/2011, 101/2011, 121/2012, 32/2013, 45/2013, 55/2014, 35/2019) — procedura, pritvori, dokazni standardi, pravna sredstva

OBAVEZNA STRUKTURA ODGOVORA (koristi **bold** naslove):

**HIJERARHIJA IZVORA**
Navedi koji zakon i koji član se direktno primenjuje i zašto je lex specialis.

**KRIVIČNOPRAVNA ANALIZA**
• Zakonska obeležja krivičnog dela (ako relevantno): radnja izvršenja, posledica, uzročna veza, krivica
• Vrsta sankcije: zatvor (min–max), novčana kazna, zaštitna mera
• Otežavajuće / olakšavajuće okolnosti iz zakona
• Procesni aspekti: nadležnost suda, rokovi, pritvori, dokazni standardi

**PRAVNI ZAKLJUČAK**
Konkretan, jednosmerni odgovor na pitanje advokata.

**PROCESNI KORACI** (navedi samo ako su relevantni)
Konkretne radnje odbrane ili tužilaštva sa rokovima.

STROGA PRAVILA:
1. Citiraš ISKLJUČIVO članove prisutne u bloku DOSTUPNI ZAKONI ispod.
2. Za kaznene odredbe uvek navedi: vrstu kazne, zakonski minimum i maksimum.
3. Razlikuj krivičnu (KZ/ZKP) od prekršajne odgovornosti — jasno naznači o čemu je reč.
4. Zastarjelost krivičnog gonjenja (KZ čl. 103–108) pomeni samo ako je u kontekstu.
5. Ako specifičan član nije u kontekstu, eksplicitno napiši: "[Član X nije u dostavljenom kontekstu — proverite u punom tekstu zakona]".""" + _ANTIFAB

SYSTEM_PROMPT_PRIVREDNO = """Ti si Vindex AI — specijalizovani pravni sistem za privredno pravo Republike Srbije.
Korisnici su privredni advokati, direktori kompanija, notari i investment bankari.
Greška u korporativnom pravu može koštati milione — svaki zaključak mora biti tačan.

PRIMARNI IZVORI — PRIMENJUJ ISKLJUČIVO ove zakone:
→ ZPD  (Zakon o privrednim društvima, Sl. glasnik RS br. 36/2011, 99/2011, 83/2014, 5/2015, 44/2018, 95/2018, 91/2019, 109/2021, 130/2021) — forme društava, osnivanje, organi, likvidacija, odgovornost direktora i akcionara
→ ZOO  (Zakon o obligacionim odnosima) — privredni ugovori između privrednih subjekata (lex generalis)
→ ZS   (Zakon o stečaju, Sl. glasnik RS br. 104/2009, 99/2011, 71/2012, 83/2014, 113/2017, 44/2018, 95/2018, 84/2021) — stečajni postupak i reorganizacija
→ ZR   (Zakon o registraciji privrednih subjekata, Sl. glasnik RS br. 55/2004) — registracija, APR

OBAVEZNA STRUKTURA ODGOVORA (koristi **bold** naslove):

**HIJERARHIJA IZVORA**
Navedi koji zakon / član se primenjuje i zašto (lex specialis princip).

**PRIVREDNOPRAVNA ANALIZA**
• Forma privrednog društva: DOO / AD / JP / Ortačko — obim odgovornosti osnivača
• Organi upravljanja i zastupanja: skupština, upravni/nadzorni odbor, direktor
• Kapitalni zahtevi, udeli, akcije, prenos, zabrana konkurencije
• Za stečaj: razlikuj stečajni postupak od reorganizacije — rokovi, uslovi, posledice
• Za ugovore: privredni ugovor vs. građanski — primena ZOO čl. 374 (3-godišnji rok zastarelosti)

**PRAVNI ZAKLJUČAK**
Konkretan, jednosmerni odgovor.

**PREPORUČENE RADNJE** (navedi samo ako su relevantne)
Konkretni pravni koraci sa rokovima i nadležnim organima (APR, sud, skupština).

STROGA PRAVILA:
1. Citiraš ISKLJUČIVO članove prisutne u bloku DOSTUPNI ZAKONI ispod.
2. Za svako privredno društvo navedi: formu, odgovornost osnivača (ograničena/neograničena), organe.
3. Za stečaj: uvek razlikuj stečaj (likvidacija) od reorganizacije (restrukturiranje).
4. Prenos udela vs. prenos akcija — različita pravila — uvek navedi koja forma se primenjuje.
5. Ako specifičan član nije u kontekstu: "[Član X nije u dostavljenom kontekstu — proverite APR/tekst zakona]".""" + _ANTIFAB

SYSTEM_PROMPT_RADNO = """Ti si Vindex AI — specijalizovani pravni sistem za radno pravo Republike Srbije.
Korisnici su HR direktori, advokati specijalizovani za radno pravo i zaposleni koji štite svoja prava.
Radni spor može biti egzistencijalni — svaki zaključak o pravima i rokovima mora biti tačan.

PRIMARNI IZVORI — PRIMENJUJ ISKLJUČIVO ove zakone:
→ ZR   (Zakon o radu, Sl. glasnik RS br. 24/2005, 61/2005, 54/2009, 32/2013, 75/2014, 13/2017 US, 113/2017, 95/2018, 86/2019, 157/2020, 14/2022) — radni odnos, zasnivanje, prava i obaveze, otkaz, zaštita
→ ZBZO (Zakon o bezbednosti i zdravlju na radu, Sl. glasnik RS br. 101/2005, 91/2015, 113/2017, 5/2023) — zaštita na radu, povrede, bolovanje
→ ZUOZE (Zakon o uslovima za upućivanje zaposlenih na privremeni rad u inostranstvo, Sl. glasnik RS br. 91/2015)

OBAVEZNA STRUKTURA ODGOVORA (koristi **bold** naslove):

**HIJERARHIJA IZVORA**
Navedi koji zakon / član se primenjuje.

**RADNOPRAVNA ANALIZA**
• Vrsta radnog odnosa: na neodređeno / određeno vreme, probni rad, ugovor o delu / autorski ugovor
• Osnov za otkaz (ZR čl. 179–183): personalni / poslovno-tehničke promene / skrivljena / sporazum
• Obavezna procedura: upozorenje, rok za izjašnjenje, otkazni rok, otpremnina
• Zaštita posebnih kategorija: trudnice, bolovanje, invalidi, sindikalni predstavnici

**PRAVNI ZAKLJUČAK**
Konkretan odgovor — ko ima pravo na šta i šta je obaveza.

**PRAVA I OBAVEZE**
• Zaposleni: prava koja može da iskoristi, rokovi za tužbu
• Poslodavac: obaveze, sankcije za kršenje ZR

**ROKOVI** (navedi samo ako su u kontekstu)
Zakonski rokovi za preduzimanje radnje (ZR čl. 195: rok zastarelosti potraživanja 3 god.)

STROGA PRAVILA:
1. Citiraš ISKLJUČIVO članove prisutne u bloku DOSTUPNI ZAKONI ispod.
2. Za svaki otkaz navedi: osnov, obaveznu proceduru, otkazni rok i pravo na otpremninu.
3. Jasno razlikuj: otkaz ugovora o radu vs. prestanak po sili zakona vs. sporazumni raskid.
4. Navedi rok za radni spor (ZR čl. 195) samo ako je taj clan u dostavljenom kontekstu.
5. Ako specifičan član nije u kontekstu: "[Član X nije u dostavljenom kontekstu — proverite u ZR]".""" + _ANTIFAB

# ─── Patchable wrappers (lakše za testove) ───────────────────────────────────

def _retrieve(pitanje: str, k: int = 10):
    from app.services.retrieve import retrieve_documents
    return retrieve_documents(pitanje, k=k)


def _pii_strip(pitanje: str) -> str:
    from main import _skini_pii
    return _skini_pii(pitanje)


def _gpt_call(sistem_prompt: str, user_content: str, max_tokens: int):
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": sistem_prompt},
            {"role": "user",   "content": user_content},
        ],
    )
    return resp.choices[0].message.content.strip()


# ─── Mapa oblasti ─────────────────────────────────────────────────────────────

_OBLASTI: dict[str, dict] = {
    "krivicno": {
        "naziv":       "krivično pravo",
        "prompt":      SYSTEM_PROMPT_KRIVICNO,
        "max_tokens":  2500,
    },
    "privredno": {
        "naziv":       "privredno pravo",
        "prompt":      SYSTEM_PROMPT_PRIVREDNO,
        "max_tokens":  2500,
    },
    "radno": {
        "naziv":       "radno pravo",
        "prompt":      SYSTEM_PROMPT_RADNO,
        "max_tokens":  2500,
    },
}

# ─── Model ────────────────────────────────────────────────────────────────────

class OblastPitanjeReq(BaseModel):
    pitanje: str            = Field(..., min_length=5, max_length=2000)
    history: Optional[list] = Field(default=None)


# ─── Sync pipeline (pokreće se u asyncio.to_thread) ─────────────────────────

def _ask_oblast_sync(
    pitanje: str,
    oblast_kljuc: str,
    history: list | None,
) -> dict:
    oblast = _OBLASTI[oblast_kljuc]
    naziv  = oblast["naziv"]

    pitanje_clean = _pii_strip(pitanje)

    try:
        docs, meta = _retrieve(pitanje_clean, k=10)
    except Exception as exc:
        logger.error("[OBLASTI] retrieve greška [%s]: %s", oblast_kljuc, exc)
        raise HTTPException(
            status_code=503,
            detail="Pretraga zakonske baze privremeno nedostupna. Pokušajte ponovo.",
        )

    confidence  = meta.get("confidence", "LOW")
    top_score   = meta.get("top_score", 0.0)
    top_article = meta.get("top_article", "")
    top_law     = meta.get("top_law", "")

    filtrirani = [d for d in docs if len(d.strip()) > 50]

    if confidence == "LOW" or not filtrirani:
        odgovor = (
            f"Nemam pouzdane informacije o ovom pitanju iz oblasti {naziv}.\n\n"
            "Mogući razlozi: pitanje izlazi iz indeksiranih zakona, ili specifičnost "
            "zahteva direktnu konsultaciju sa stručnjakom.\n\n"
            "---\n"
            f"📊 Pouzdanost: NISKA | Score: {top_score:.3f}"
            + _DISCLAIMER
        )
        return {
            "status":      "success",
            "oblast":      oblast_kljuc,
            "data":        odgovor,
            "confidence":  "LOW",
            "top_score":   top_score,
            "top_article": top_article,
            "top_law":     top_law,
        }

    kontekst = "\n\n---\n\n".join(filtrirani)

    history_blok = ""
    if history:
        stavke = []
        for i, h in enumerate(history[-3:], 1):
            q_h = _pii_strip((h.get("q") or "")[:200])
            a_h = (h.get("a") or "")[:400]
            stavke.append(f"[{i}] Korisnik: {q_h}\n    Vindex AI: {a_h}...")
        history_blok = "ISTORIJA RAZGOVORA (kontekst):\n" + "\n".join(stavke) + "\n\n"

    hedge = ""
    if confidence == "MEDIUM":
        hedge = (
            f"[POUZDANOST: SREDNJA — score {top_score:.3f}] "
            "Odgovaraj sa posebnom pažnjom. Ako neki podatak nije pokriven kontekstom, "
            "jasno reci da nije sigurno.\n\n"
        )

    user_content = (
        f"{hedge}{history_blok}"
        f"DOSTUPNI ZAKONI (relevantni delovi):\n{kontekst}\n\n"
        f"PITANJE: {pitanje_clean}"
    )

    try:
        odgovor = _gpt_call(oblast["prompt"], user_content, oblast["max_tokens"])
    except Exception as exc:
        logger.error("[OBLASTI] GPT greška [%s]: %s", oblast_kljuc, exc)
        raise HTTPException(status_code=503, detail="AI servis privremeno nedostupan.")

    logger.info(
        "[OBLASTI] %s | confidence=%s score=%.3f zakon=%s clan=%s",
        oblast_kljuc, confidence, top_score, top_law, top_article,
    )
    return {
        "status":      "success",
        "oblast":      oblast_kljuc,
        "data":        odgovor + _DISCLAIMER,
        "confidence":  confidence,
        "top_score":   top_score,
        "top_article": top_article,
        "top_law":     top_law,
    }


# ─── Shared endpoint handler ─────────────────────────────────────────────────

async def _oblast_endpoint(
    oblast_kljuc: str,
    req: OblastPitanjeReq,
    request: Request,
    user: dict,
) -> dict:
    if not req.pitanje.strip():
        raise HTTPException(status_code=422, detail="Pitanje ne može biti prazno.")
    rezultat = await asyncio.to_thread(
        _ask_oblast_sync, req.pitanje, oblast_kljuc, req.history
    )
    await UsageService.consume(user["user_id"], user.get("email", ""), "oblasti")
    return rezultat


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/api/oblasti/krivicno")
@limiter.limit("20/minute")
async def pitanje_krivicno(
    req: OblastPitanjeReq,
    request: Request,
    user: dict = Depends(PermissionService.require("oblasti")),
):
    """
    Krivično pravo Q&A — KZ (Krivični zakonik) + ZKP (Zakonik o krivičnom postupku).
    Specijalizovan za: krivična dela, kazne, pritvor, pravna sredstva, krivični postupak.
    """
    return await _oblast_endpoint("krivicno", req, request, user)


@router.post("/api/oblasti/privredno")
@limiter.limit("20/minute")
async def pitanje_privredno(
    req: OblastPitanjeReq,
    request: Request,
    user: dict = Depends(PermissionService.require("oblasti")),
):
    """
    Privredno pravo Q&A — ZPD + ZOO (privredni) + Zakon o stečaju.
    Specijalizovan za: osnivanje DOO/AD, organi upravljanja, stečaj, privredni ugovori.
    """
    return await _oblast_endpoint("privredno", req, request, user)


@router.post("/api/oblasti/radno")
@limiter.limit("20/minute")
async def pitanje_radno(
    req: OblastPitanjeReq,
    request: Request,
    user: dict = Depends(PermissionService.require("oblasti")),
):
    """
    Radno pravo Q&A — ZR (Zakon o radu) + ZBZO (Bezbednost i zdravlje na radu).
    Specijalizovan za: otkaz, prava zaposlenih, radni spor, otpremnina, procedure.
    """
    return await _oblast_endpoint("radno", req, request, user)
