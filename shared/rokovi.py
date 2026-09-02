# -*- coding: utf-8 -*-
"""Kanonski čitalački ugovor za domen ROKOVA.

BETA-DEADLINE-DOMAIN-001.

ZAŠTO POSTOJI

Trinaest mesta u produkcionom kodu čitalo je tabelu `rokovi`. Ta tabela **ne
postoji** u produkciji (`GET /rest/v1/rokovi` → `404 / PGRST205`) i nikada nije
ni napravljena — nijedna migracija je ne kreira.

Presudan strukturni nalaz nije to što tabele nema, nego to što **nema nijednog
pisca**: nula `INSERT`/`UPDATE`/`UPSERT`/`DELETE` nad `rokovi` u celom repou.
Da je tabela sutra napravljena, ostala bi trajno prazna i svih trinaest upita
vratilo bi nula redova. Dakle ovo nije šema koja nedostaje — ovo je čitalačka
polovina ugovora čija druga polovina nikada nije napisana, dok je domenski
objekat u međuvremenu dobio stvarnog vlasnika.

KO JE STVARNI VLASNIK — mereno, ne pretpostavljeno

    predmet_hronologija   10 pisaca   (rokovi_lanac, intake, case_dna,
                                       predmeti_close, copilot, learning, api)
    rocista                3 pisca
    zadaci                 5+ pisaca
    rokovi                 0 pisaca

Svaka stvarna putanja kojom rok ulazi u sistem — ZPP lanac procesnih rokova,
Intake Wizard, Genome, zatvaranje predmeta — piše u `predmet_hronologija`.

ZAŠTO ROČIŠTA NISU OVDE

`rocista` je zaseban domenski objekat, ne sinonim. Šest mesta dohvata `rocista`
i `rokovi` u ISTOM `asyncio.gather`-u i prikazuje ih u odvojenim sekcijama
(„ROČIŠTA DANAS" vs „HITNI ROKOVI"). Spajanje bi svaki rok prikazalo i kao
ročište — dvostruko brojanje na ekranu koji advokat koristi da ne propusti dan.
Isto važi za `zadaci`: `zadaci.py` dohvata obe u istom `gather`-u i ispisuje ih
kao dve odvojene stavke, a izolacija im je različita (`zadaci` je
per-kancelarija, hronologija je per-user).

ŠTA JE ROK — pravilo koje se NE izmišlja ovde

Dva postojeća produkciona čitaoca već primenjuju isti kriterijum:

    routers/dashboard.py:89   predmet_hronologija .eq(user_id) .gte(datum_iso) .lte(datum_iso)
    routers/kalendar.py:76    isto

Red hronologije čiji `datum_iso` pada u traženi (budući) prozor JESTE
predstojeća obaveza. Ovaj modul tu zatečenu semantiku formalizuje, ne menja.

PRAZNO NIJE ISTO ŠTO I NEUSPEH

Cela poenta ovog sloja. Trinaest zatečenih mesta radilo je `except: return []`,
`except: pass` ili je puštalo 500 — pa je advokat na ekranu dobijao „nemate
hitnih rokova" iz upita koji nikada nije uspeo. Zato ovde nijedna putanja ne
vraća praznu listu na grešku: `Rezultat.uspeh` je jedini nosilac te razlike, a
`zahtevaj()` neuspeh pretvara u HTTP grešku.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger("vindex.rokovi")

# Kanonski vlasnik domena. Jedno mesto, da se ime tabele ne prepisuje po kodu.
TABELA = "predmet_hronologija"

# Kolone koje tabela STVARNO ima (mereno nad produkcijom preko PostgREST
# OpenAPI korena): akter, created_at, datum, datum_iso, dogadjaj,
# dokument_naziv, id, predmet_id, user_id, vaznost.
# `datum` je TEXT i slobodnog je oblika; `datum_iso` je DATE i jedino je ono
# uporedivo. Zato se filtrira i sortira isključivo po `datum_iso`.
_KOLONE = "id, predmet_id, dogadjaj, datum_iso, vaznost, akter"

# Podrazumevani prozor: koliko unapred „predstojeći rok" uopšte znači.
PROZOR_DANA = 7

# Gornja granica koju baza sme da vrati u jednom pozivu.
_MAX_LIMIT = 200


class Stanje(str, Enum):
    """Ishodi koje pozivalac mora umeti da razlikuje.

    `PRAZNO` postoji odvojeno od `OK` namerno: pozivalac koji ispisuje „nema
    rokova" mora moći da dokaže da je upit izvršen.
    """

    OK = "ok"                       # upit izvršen, ima redova
    PRAZNO = "prazno"               # upit izvršen, nema redova — legitimno prazno
    NEUSPEH = "neuspeh"             # upit NIJE izvršen; ne zna se ima li rokova
    NEDOZVOLJENO = "nedozvoljeno"   # subjekt nije vlasnikov
    NEISPRAVAN_SUBJEKT = "neispravan_subjekt"   # nema user_id / predmet_id
    NEISPRAVAN_PODATAK = "neispravan_podatak"   # red iz baze ne zadovoljava ugovor


# Vrednosti koje `vaznost` sme da ima — CHECK ograničenje u produkciji.
# Mereno na 52 reda: kritičan 17, važan 13, informativan 22.
VAZNOST_DOZVOLJENE = ("kritičan", "važan", "informativan")

_VAZNOST_RANG = {"kritičan": 0, "važan": 1, "informativan": 2}


def normalizuj_vaznost(vrednost: Optional[str]) -> str:
    """Bilo koji rečnik važnosti → vrednost koju CHECK u bazi STVARNO dozvoljava.

    ZAŠTO POSTOJI

    `supabase_setup.sql:415` glasi:

        vaznost TEXT NOT NULL DEFAULT 'informativan'
                CHECK (vaznost IN ('kritičan','važan','informativan'))

    a četiri pisca kanonske tabele upisuju vrednosti van tog skupa:

        routers/intake.py:282            "bitan"
        routers/predmeti_close.py:189    "kljucan"
        routers/rocista.py:398           "bitan"
        routers/ugovor_zastupanja.py:336 "kljucan"

    Svaki od njih pada na 23514 i svaki tu grešku guta u `logger.warning`. To
    je isti kvar koji je BETA-P1-DEADLINE-TRUTH zatvorio u `rokovi_lanac.py`,
    ponovljen na četiri mesta.

    ZAŠTO SE NE UVODI NOVI REČNIK

    Projekat već ima kanonsku skalu — `shared/attention_priority.py`. Ona
    `bitan` i `važan` oboje vodi u HIGH, a `kljucan` i `kritičan` u CRITICAL.
    Značenje pisaca je dakle nedvosmisleno i ovde se ne izmišlja: samo se
    prevodi u vrednosti koje baza prihvata.

    ZAOKRUŽUJE SE NAVIŠE, NIKAD NANIŽE

    MEDIUM ide u `važan`, ne u `informativan`. Baza nema srednju vrednost, a
    tiho snižavanje roka je gore od precenjivanja: precenjen rok advokat vidi i
    odbaci, potcenjen ne vidi.
    """
    from shared.attention_priority import (CRITICAL, HIGH, INFORMATIONAL, LOW,
                                           VAZNOST_TO_CANONICAL, to_canonical)

    if vrednost in VAZNOST_DOZVOLJENE:
        return vrednost                      # već kanonski za bazu

    kanonski = to_canonical(vrednost, VAZNOST_TO_CANONICAL)
    if kanonski == CRITICAL:
        return "kritičan"
    if kanonski in (LOW, INFORMATIONAL):
        return "informativan"
    # HIGH i MEDIUM
    if kanonski != HIGH:
        logger.info("[ROKOVI] vaznost %r → 'važan' (zaokruženo naviše)", vrednost)
    return "važan"


@dataclass(frozen=True)
class Rok:
    """Normalizovan rok. Nosi ISKLJUČIVO ono što u bazi stvarno postoji.

    Namerno NEMA polja `tip`, `status` ni `opis`: `predmet_hronologija` te
    kolone nema. `prekoracen` i `dana_do` nisu podaci iz baze nego izvedene
    vrednosti nad `datum` — računaju se ovde jednom, da ih trinaest pozivalaca
    ne bi računalo na trinaest načina.
    """

    izvor_id: str
    predmet_id: str
    naslov: str
    datum: date
    vaznost: str
    akter: str = ""
    dana_do: int = 0
    prekoracen: bool = False

    @property
    def kljuc_sortiranja(self) -> tuple:
        """Prvo po datumu, pa po važnosti — kritičan pre informativnog."""
        return (self.datum, _VAZNOST_RANG.get(self.vaznost, 9), self.naslov)

    def kao_dict(self) -> dict:
        return {
            "id":          self.izvor_id,
            "predmet_id":  self.predmet_id,
            "naziv":       self.naslov,
            "datum":       self.datum.isoformat(),
            "vaznost":     self.vaznost,
            "akter":       self.akter,
            "dana_do":     self.dana_do,
            "prekoracen":  self.prekoracen,
        }


@dataclass(frozen=True)
class Rezultat:
    """Ishod čitanja. `rokovi` je prazna lista i kad je upit pao — zato se
    prazna lista NIKAD ne sme čitati bez `uspeh`."""

    stanje: Stanje
    rokovi: list = field(default_factory=list)
    razlog: str = ""

    @property
    def uspeh(self) -> bool:
        return self.stanje in (Stanje.OK, Stanje.PRAZNO)

    def kao_dict(self) -> dict:
        return {
            "uspeh":   self.uspeh,
            "stanje":  self.stanje.value,
            "rokovi":  [r.kao_dict() for r in self.rokovi],
            "razlog":  self.razlog,
        }


def _neuspeh(stanje: Stanje, razlog: str) -> Rezultat:
    return Rezultat(stanje=stanje, rokovi=[], razlog=razlog)


def _u_rok(red: dict, danas: date) -> Optional[Rok]:
    """Jedan red baze → `Rok`. Vraća `None` ako red ne zadovoljava ugovor.

    Neispravan red se PRESKAČE, ne popravlja: red bez `datum_iso` ili bez
    `predmet_id` nije rok koji se sme prikazati kao rok.
    """
    sirovi_datum = red.get("datum_iso")
    predmet_id = red.get("predmet_id")
    if not sirovi_datum or not predmet_id:
        return None
    try:
        d = date.fromisoformat(str(sirovi_datum)[:10])
    except (ValueError, TypeError):
        return None

    naslov = (red.get("dogadjaj") or "").strip() or "Rok"
    vaznost = red.get("vaznost") or "informativan"
    if vaznost not in VAZNOST_DOZVOLJENE:
        # Nepoznata vrednost se ne preslikava u „informativan" -- to bi tiho
        # snizilo kritičan rok. Prolazi kakva jeste; rangiranje je degradira
        # na dno, a pozivalac vidi istinu.
        logger.warning("[ROKOVI] nepoznata vaznost %r na redu %s",
                       vaznost, red.get("id"))

    return Rok(
        izvor_id=str(red.get("id") or ""),
        predmet_id=str(predmet_id),
        naslov=naslov[:300],
        datum=d,
        vaznost=vaznost,
        akter=(red.get("akter") or "")[:200],
        dana_do=(d - danas).days,
        prekoracen=d < danas,
    )


async def _izvrsi(supa, gradi_upit) -> Rezultat:
    """Zajedničko telo: izvrši, normalizuj, nikad ne pretvori grešku u prazno."""
    danas = date.today()
    try:
        odgovor = await asyncio.to_thread(lambda: gradi_upit().execute())
    except Exception as e:
        # Ovde je bila rupa svih trinaest pozivalaca. Greška IZLAZI kao stanje,
        # ne kao prazna lista.
        logger.error("[ROKOVI] upit nije izvršen: %s", e)
        return _neuspeh(Stanje.NEUSPEH, "Rokovi nisu dohvaćeni: %s" % e)

    redovi = getattr(odgovor, "data", None)
    if redovi is None:
        redovi = []
    if not isinstance(redovi, list):
        return _neuspeh(Stanje.NEISPRAVAN_PODATAK,
                        "Neočekivan oblik odgovora baze.")

    rokovi = [r for r in (_u_rok(x, danas) for x in redovi) if r is not None]
    odbaceno = len(redovi) - len(rokovi)
    if odbaceno:
        logger.warning("[ROKOVI] %d red(ova) ne zadovoljava ugovor, preskočeno", odbaceno)

    rokovi.sort(key=lambda r: r.kljuc_sortiranja)
    return Rezultat(stanje=Stanje.OK if rokovi else Stanje.PRAZNO, rokovi=rokovi)


async def rokovi_za_korisnika(
    supa,
    user_id: str,
    *,
    od: Optional[date] = None,
    do: Optional[date] = None,
    limit: int = 100,
) -> Rezultat:
    """Svi rokovi jednog advokata u zadatom prozoru.

    `od` podrazumevano danas, `do` podrazumevano `od + PROZOR_DANA`. Za
    propuštene rokove pozivalac šalje `od` u prošlost.
    """
    if not user_id:
        return _neuspeh(Stanje.NEISPRAVAN_SUBJEKT, "Nedostaje korisnik.")

    _od = od or date.today()
    _do = do if do is not None else _od + timedelta(days=PROZOR_DANA)
    if _do < _od:
        return _neuspeh(Stanje.NEISPRAVAN_SUBJEKT, "Prozor se završava pre početka.")

    _limit = max(1, min(int(limit or 1), _MAX_LIMIT))

    def _upit():
        return (supa.table(TABELA)
                .select(_KOLONE)
                .eq("user_id", user_id)
                .gte("datum_iso", _od.isoformat())
                .lte("datum_iso", _do.isoformat())
                .order("datum_iso")
                .limit(_limit))

    return await _izvrsi(supa, _upit)


async def rokovi_za_predmet(
    supa,
    user_id: str,
    predmet_id: str,
    *,
    od: Optional[date] = None,
    do: Optional[date] = None,
    limit: int = 50,
) -> Rezultat:
    """Rokovi jednog predmeta.

    `user_id` filter se NE izostavlja iako je `predmet_id` uži: backend radi sa
    `service_role` ključem, pa je RLS zaobiđen i ovaj filter je jedina brana
    između kancelarija (isto obrazloženje kao u `shared/ownership.py`).
    """
    if not user_id:
        return _neuspeh(Stanje.NEISPRAVAN_SUBJEKT, "Nedostaje korisnik.")
    if not predmet_id:
        return _neuspeh(Stanje.NEISPRAVAN_SUBJEKT, "Nedostaje predmet.")

    _od = od or date.today()
    _do = do if do is not None else _od + timedelta(days=PROZOR_DANA)
    if _do < _od:
        return _neuspeh(Stanje.NEISPRAVAN_SUBJEKT, "Prozor se završava pre početka.")

    _limit = max(1, min(int(limit or 1), _MAX_LIMIT))

    def _upit():
        return (supa.table(TABELA)
                .select(_KOLONE)
                .eq("user_id", user_id)
                .eq("predmet_id", predmet_id)
                .gte("datum_iso", _od.isoformat())
                .lte("datum_iso", _do.isoformat())
                .order("datum_iso")
                .limit(_limit))

    return await _izvrsi(supa, _upit)


async def rok_po_id(supa, user_id: str, rok_id: str) -> Rezultat:
    """Jedan rok po identifikatoru, ograničen na vlasnika.

    `NEDOZVOLJENO` i „ne postoji" se namerno NE razlikuju prema pozivaocu —
    razlika bi bila proročište za nabrajanje tuđih redova (ista odluka kao
    404-umesto-403 u `shared/ownership.py`).
    """
    if not user_id:
        return _neuspeh(Stanje.NEISPRAVAN_SUBJEKT, "Nedostaje korisnik.")
    if not rok_id:
        return _neuspeh(Stanje.NEISPRAVAN_SUBJEKT, "Nedostaje identifikator roka.")

    def _upit():
        return (supa.table(TABELA)
                .select(_KOLONE)
                .eq("id", rok_id)
                .eq("user_id", user_id)
                .limit(1))

    rez = await _izvrsi(supa, _upit)
    if rez.stanje is Stanje.PRAZNO:
        return _neuspeh(Stanje.NEDOZVOLJENO, "Rok nije pronađen.")
    return rez


def zahtevaj(rez: Rezultat) -> list:
    """Rezultat → lista rokova, ili HTTP greška. Nikad tiho prazno.

    Pozivaoci koji su ranije radili `except: return []` koriste ovo: neuspeh
    prestaje da bude nevidljiv, a legitimno prazno i dalje prolazi.
    """
    if rez.stanje is Stanje.NEUSPEH:
        raise HTTPException(
            status_code=503,
            detail="Rokovi trenutno nisu dostupni. Odsustvo rezultata NE znači "
                   "da rokova nema — pokušajte ponovo.",
        )
    if rez.stanje is Stanje.NEISPRAVAN_PODATAK:
        raise HTTPException(status_code=503, detail="Neispravan odgovor baze za rokove.")
    if rez.stanje is Stanje.NEDOZVOLJENO:
        raise HTTPException(status_code=404, detail="Rok nije pronađen.")
    if rez.stanje is Stanje.NEISPRAVAN_SUBJEKT:
        raise HTTPException(status_code=400, detail=rez.razlog or "Neispravan zahtev.")
    return rez.rokovi

# ═══════════════════════════════════════════════════════════════════════════
# FAZA 6.2 — GRANICA IZMEĐU AI OPAŽANJA I IZVRŠIVE OBAVEZE (INV-2)
#
# FAZA 6.1 je UŽIVO dokazala kvar: Genome je upisao tri roka sa
# `vaznost="kritičan"`, a `_ACTIONABLE_VAZNOST = ["kritičan", "važan"]` — pa su
# sva tri bila podobna za email/SMS podsetnik i notifikaciju BEZ IJEDNE ljudske
# potvrde. Da je `korisnik_email_notif` bio uključen, advokat bi dobio opomenu
# za rok koji nikad nije video ni potvrdio.
#
# `vaznost` je AI PROCENA TEŽINE. Ona NIJE potvrda i NIJE ovlašćenje.
# Zato se ovde ne dira ni jedna postojeća `vaznost` vrednost niti njena
# semantika — uvodi se NEZAVISNA dimenzija: poreklo + potvrda.
#
# Poreklo se ne izmišlja: `akter` je POSTOJEĆE kanonsko polje koje oba AI
# proizvođača već popunjavaju svojim potpisom (izmereno na živoj bazi).
# Ljudski unos i ZPP lanac nose druge vrednosti i ovim se NE menjaju.
# ═══════════════════════════════════════════════════════════════════════════

#: Potpisi u `predmet_hronologija.akter` koje upisuju AI proizvođači.
#: `Genome (AI)`   — routers/case_dna.py::_sync_rokovi_to_hronologija
#: `Pipeline (AI)` — services/case_pipeline.py
#: Vrednost se poredi DOSLOVNO: nepoznat akter NIJE AI (fail-open za ljudski
#: unos je ispravan — ljudski rok nikad nije bio gejtovan i ne postaje sada).
AI_AKTERI: tuple = ("Genome (AI)", "Pipeline (AI)")


def je_ai_poreklo(akter: Optional[str]) -> bool:
    """Da li je ovaj red hronologije proizveo AI, a ne čovek?

    Namerno DOSLOVNO poređenje, bez `startswith`/`in`: labav test bi svrstao
    ljudski unos „Pipeline (AI) je pogrešio" u AI poreklo i tiho ugasio
    korisnikov sopstveni rok."""
    return (akter or "") in AI_AKTERI


def sme_pokrenuti_obavezu(red: dict, potvrdjeni_ids: Optional[set] = None) -> bool:
    """JEDINA kapija između opažanja i izvršive posledice (podsetnik, SMS,
    notifikacija).

    FAIL-CLOSED: red AI porekla prolazi ISKLJUČIVO ako je njegov `id` u skupu
    potvrđenih. Prazan/`None` skup znači „nijedna potvrda ne postoji", pa
    nijedan AI rok ne prolazi — to je ispravan ishod, ne greška.

    Red koji NIJE AI porekla prolazi nepromenjeno: ovaj gejt ne uvodi nova
    ograničenja nad rokovima koje je uneo čovek ili deterministički ZPP lanac.
    """
    if not je_ai_poreklo(red.get("akter")):
        return True
    rid = red.get("id")
    if not rid:
        # AI red bez `id` se ne može dovesti u vezu ni sa jednom potvrdom.
        return False
    return rid in (potvrdjeni_ids or set())


def filtriraj_izvrsive(redovi: Optional[list], potvrdjeni_ids: Optional[set] = None) -> list:
    """Primena `sme_pokrenuti_obavezu` na listu redova hronologije."""
    return [r for r in (redovi or []) if sme_pokrenuti_obavezu(r, potvrdjeni_ids)]
