# -*- coding: utf-8 -*-
"""
Vindex AI — routers/ugovor_zastupanja.py

POST /api/ugovor-zastupanja/generiši  — Generisanje ugovora o zastupanju
GET  /api/ugovor-zastupanja/tipovi    — Katalog oblasti prava i tipova nagrade
"""
from __future__ import annotations

import asyncio
import logging
import random
import string
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.ugovor_zastupanja")
router = APIRouter(tags=["ugovor"])

# ─── Katalozi ─────────────────────────────────────────────────────────────────

_OBLASTI_PRAVA: dict[str, str] = {
    "parnicno":       "Parnični postupak",
    "krivicno":       "Krivični postupak",
    "upravno":        "Upravni postupak",
    "radno":          "Radno pravo",
    "porodicno":      "Porodičnopravni predmeti",
    "nasledjivanje":  "Ostavinski (nasledni) postupak",
    "privredno":      "Privredno pravo",
    "nepokretnosti":  "Pravo nepokretnosti",
    "ostalo":         "Ostalo",
}

_TIPOVI_NAGRADE: dict[str, str] = {
    "pausal":       "Paušalna naknada",
    "po_satu":      "Satnica (po satu rada)",
    "uspeh":        "Naknada po uspehu",
    "po_aks_tarifi": "Po Advokatskoj tarifi AKS",
    "besplatno":    "Pro bono (bez naknade)",
}

_VALID_OBLASTI  = frozenset(_OBLASTI_PRAVA)
_VALID_NAGRADE  = frozenset(_TIPOVI_NAGRADE)

_NAGRADA_TEKST: dict[str, str] = {
    "pausal": (
        "Klijent se obavezuje da Advokatu isplati paušalnu naknadu u iznosu od {iznos}, "
        "na ime zastupanja u predmetu opisanom u članu 1 ovog ugovora. "
        "Naknada se isplaćuje u roku od 8 dana od zaključenja ovog ugovora, "
        "osim ako stranke ne dogovore drugačiji plan plaćanja."
    ),
    "po_satu": (
        "Klijent se obavezuje da Advokatu isplati naknadu po satu rada u iznosu od {iznos}. "
        "Naknada se obračunava mesečno prema evidenciji radnih sati Advokata i dospeva u roku od 8 dana "
        "od dostavljanja mesečnog obračuna."
    ),
    "uspeh": (
        "Naknada Advokata ugovara se kao naknada po uspehu. {iznos} "
        "Klijent je dužan da snosi troškove postupka (sudske takse, veštačenja i sl.) nezavisno od ishoda. "
        "Naknada po uspehu ne isključuje pravo Advokata na naknadu troškova zastupanja koje mu dosudom prizna sud."
    ),
    "po_aks_tarifi": (
        "Naknada Advokata obračunava se prema važećoj Advokatskoj tarifi "
        "Advokatske komore Srbije (Sl. glasnik RS br. 3/2021 i izmene). "
        "{iznos}"
    ),
    "besplatno": (
        "Stranke su saglasne da Advokat vrši zastupanje u konkretnom predmetu bez naknade (pro bono). "
        "{iznos}"
    ),
}


def _gen_broj() -> str:
    suffix = "".join(random.choices(string.digits, k=3))
    return f"{suffix}/{date.today().year}"


def _popuni_nagradu(tip: str, iznos: str, napomena: str) -> str:
    iznos_str = iznos.strip() if iznos.strip() else "po dogovoru stranaka"
    tekst = _NAGRADA_TEKST.get(tip, "")
    tekst = tekst.format(iznos=iznos_str)
    if napomena:
        tekst += f"\n\n{napomena.strip()}"
    return tekst


def _generiši_ugovor(
    *,
    broj:                  str,
    klijent_ime_prezime:   str,
    klijent_adresa:        str,
    klijent_jmbg:          str,
    klijent_firma:         str,
    advokat_ime:           str,
    advokat_adresa:        str,
    advokat_licenca:       str,
    predmet_opis:          str,
    oblast_prava:          str,
    nagrada_tip:           str,
    nagrada_iznos:         str,
    nagrada_napomena:      str,
    datum_zakljucenja:     str,
) -> str:
    oblast_naziv = _OBLASTI_PRAVA.get(oblast_prava, oblast_prava)

    klijent_blok = klijent_ime_prezime
    if klijent_firma:
        klijent_blok = f"{klijent_firma} (zastupano po: {klijent_ime_prezime})"
    if klijent_adresa:
        klijent_blok += f"\nAdresa: {klijent_adresa}"
    if klijent_jmbg:
        klijent_blok += f"\nJMBG: {klijent_jmbg}"

    advokat_blok = f"Advokat {advokat_ime}"
    if advokat_adresa:
        advokat_blok += f"\nAdresa kancelarije: {advokat_adresa}"
    if advokat_licenca:
        advokat_blok += f"\nBroj licence AKS: {advokat_licenca}"

    nagrada_tekst = _popuni_nagradu(nagrada_tip, nagrada_iznos, nagrada_napomena)
    nagrada_naziv = _TIPOVI_NAGRADE.get(nagrada_tip, nagrada_tip)

    return f"""U G O V O R   O   Z A S T U P A N J U
Broj: {broj}

Zaključen dana {datum_zakljucenja} godine, između:

I. KLIJENT:
{klijent_blok}
(u daljem tekstu: „Klijent")

II. ADVOKAT:
{advokat_blok}
Advokat upisani u Imenik advokata Advokatske komore Srbije
(u daljem tekstu: „Advokat")

Stranke su saglasne i zaključuju:


Član 1 — Predmet zastupanja

Advokat preuzima zastupanje Klijenta u predmetu:

    {predmet_opis}

Oblast prava: {oblast_naziv}

Advokat se obavezuje da će preduzimati sve zakonski dozvoljene radnje u cilju zaštite interesa Klijenta,
u skladu sa Zakonom o advokaturi (Sl. glasnik RS br. 31/2011) i Kodeksom profesionalne etike advokata.


Član 2 — Ovlašćenja advokata

Klijent ovlašćuje Advokata da u njegovo ime i za njegov račun:
  – zastupa Klijenta pred svim sudovima, organima uprave i drugim institucijama;
  – potpisuje podneske, zahteve i pravne lekove;
  – prima pismena i dostavnice u ime Klijenta;
  – preduzima sve procesne radnje neophodne za zaštitu prava Klijenta.

Advokat nije ovlašćen za zaključivanje nagodbi niti primanje novčanih sredstava bez posebne
pisane saglasnosti Klijenta u svakom konkretnom slučaju.


Član 3 — Naknada advokata ({nagrada_naziv})

{nagrada_tekst}

Troškovi nastali u okviru zastupanja (sudske takse, veštačenja, prevođenje i sl.) nisu uključeni
u advokatsku naknadu i padaju na teret Klijenta.


Član 4 — Obaveze klijenta

Klijent se obavezuje da:
  – blagovremeno dostavlja Advokatu sve isprave, informacije i dokaze relevantne za predmet;
  – uredno izmiruje ugovorenu naknadu i troškove u dogovorenim rokovima;
  – obaveštava Advokata o svim novim okolnostima koje mogu uticati na tok predmeta;
  – ne preduzima radnje u predmetu bez prethodne konsultacije sa Advokatom.


Član 5 — Poverljivost

Advokat je dužan da čuva kao profesionalnu tajnu sve podatke koje je saznao u toku zastupanja,
u skladu sa Zakonom o advokaturi i Kodeksom profesionalne etike advokata AKS.
Ova obaveza traje i nakon prestanka ovog ugovora.


Član 6 — Raskid ugovora

Svaka ugovorna strana može raskinuti ovaj ugovor u svako doba uz pismeno obaveštenje.
U slučaju raskida, Advokat je dužan da Klijentu preda sve spise i dokumenta bez odlaganja.
Naknada se obračunava srazmerno radnjama preduzetim do momenta raskida.


Član 7 — Primena prava i nadležnost

Na ovaj ugovor primenjuje se pravo Republike Srbije.
U slučaju spora, nadležan je sud prema sedištu advokatske kancelarije.


Član 8 — Završne odredbe

Ovaj ugovor sačinjen je u 2 (dva) istovetna primerka, od kojih svaka stranka zadržava po 1 (jedan).
Stupa na snagu danom potpisivanja od strane obe ugovorne strane.

──────────────────────────────────────────────────────────────────────────
    KLIJENT:                                    ADVOKAT:

    _____________________________           _____________________________
    {klijent_ime_prezime}                   Advokat {advokat_ime}
──────────────────────────────────────────────────────────────────────────
Generisano putem Vindex AI — {datum_zakljucenja}
"""


# ─── Request model ────────────────────────────────────────────────────────────

class UgovorZastupanjaReq(BaseModel):
    klijent_ime_prezime: str           = Field(..., min_length=3, max_length=200)
    klijent_adresa:      str           = Field(default="", max_length=300)
    klijent_jmbg:        str           = Field(default="", max_length=15)
    klijent_firma:       str           = Field(default="", max_length=200)
    advokat_ime:         str           = Field(..., min_length=3, max_length=150)
    advokat_adresa:      str           = Field(default="", max_length=300)
    advokat_licenca:     str           = Field(default="", max_length=30)
    predmet_opis:        str           = Field(..., min_length=5, max_length=1000)
    oblast_prava:        str           = Field(default="parnicno", max_length=30)
    nagrada_tip:         str           = Field(default="pausal", max_length=20)
    nagrada_iznos:       str           = Field(default="", max_length=200)
    nagrada_napomena:    str           = Field(default="", max_length=500)
    datum_zakljucenja:   Optional[str] = Field(default=None, max_length=10)
    predmet_id:          Optional[str] = Field(default=None, max_length=50)

    @field_validator("oblast_prava")
    @classmethod
    def _val_oblast(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _VALID_OBLASTI:
            raise ValueError(f"oblast_prava mora biti jedna od: {sorted(_VALID_OBLASTI)}")
        return v

    @field_validator("nagrada_tip")
    @classmethod
    def _val_nagrada(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _VALID_NAGRADE:
            raise ValueError(f"nagrada_tip mora biti jedan od: {sorted(_VALID_NAGRADE)}")
        return v

    @field_validator("datum_zakljucenja")
    @classmethod
    def _val_datum(cls, v: Optional[str]) -> Optional[str]:
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise ValueError("datum_zakljucenja mora biti YYYY-MM-DD")
        return v


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/ugovor-zastupanja/tipovi")
async def get_tipovi_ugovora():
    """Katalog oblasti prava i tipova advokatske nagrade."""
    return {
        "oblasti_prava": [
            {"kljuc": k, "naziv": v} for k, v in _OBLASTI_PRAVA.items()
        ],
        "tipovi_nagrade": [
            {"kljuc": k, "naziv": v} for k, v in _TIPOVI_NAGRADE.items()
        ],
    }


@router.post("/api/ugovor-zastupanja/generiši")
@limiter.limit("20/minute")
async def post_generiši_ugovor(
    body: UgovorZastupanjaReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Generiše ugovor o zastupanju na osnovu popunjenih polja.

    Ne zahteva OpenAI — čist template. Ako je prosleđen predmet_id,
    beleži zaključenje ugovora u predmet_hronologija.
    """
    uid  = user["user_id"]
    broj = _gen_broj()
    datum = body.datum_zakljucenja or date.today().isoformat()
    datum_prikaz = date.fromisoformat(datum).strftime("%d.%m.%Y")

    ugovor_tekst = _generiši_ugovor(
        broj=broj,
        klijent_ime_prezime=body.klijent_ime_prezime,
        klijent_adresa=body.klijent_adresa,
        klijent_jmbg=body.klijent_jmbg,
        klijent_firma=body.klijent_firma,
        advokat_ime=body.advokat_ime,
        advokat_adresa=body.advokat_adresa,
        advokat_licenca=body.advokat_licenca,
        predmet_opis=body.predmet_opis,
        oblast_prava=body.oblast_prava,
        nagrada_tip=body.nagrada_tip,
        nagrada_iznos=body.nagrada_iznos,
        nagrada_napomena=body.nagrada_napomena,
        datum_zakljucenja=datum_prikaz,
    )

    sacuvano = False

    if body.predmet_id:
        supa = _get_supa()

        pred_res = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                        .select("id, naziv")
                        .eq("id", body.predmet_id)
                        .eq("user_id", uid)
                        .single()
                        .execute()
        )
        if not pred_res.data:
            raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

        try:
            await asyncio.to_thread(
                lambda: supa.table("predmet_hronologija").insert({
                    "predmet_id": body.predmet_id,
                    "user_id":    uid,
                    "dogadjaj":   f"Ugovor o zastupanju zaključen — Klijent: {body.klijent_ime_prezime[:80]}",
                    "datum":      datum,
                    "datum_iso":  datum,
                    "vaznost":    "kljucan",
                    "akter":      f"Advokat {body.advokat_ime[:80]}",
                }).execute()
            )
            sacuvano = True
        except Exception as e:
            logger.warning("[UGOVOR] hronologija insert greška: %s", e)

    logger.info(
        "[UGOVOR] uid=%.8s broj=%s klijent=%.20s sacuvano=%s",
        uid, broj, body.klijent_ime_prezime, sacuvano,
    )

    return {
        "ok":                 True,
        "broj":               broj,
        "datum_zakljucenja":  datum_prikaz,
        "ugovor_tekst":       ugovor_tekst,
        "sacuvano_u_predmet": sacuvano,
        "predmet_id":         body.predmet_id,
    }
