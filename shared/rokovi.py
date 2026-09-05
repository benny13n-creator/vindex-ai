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

# ── PROVENIJENCIJA SADRŽAJA (migracija 127) ─────────────────────────────────
# `izvor` odgovara na pitanje KAKO je sadržaj zapisa nastao. To je ČETVRTA,
# nezavisna osa — ne meša se ni sa jednom od ostale tri:
#
#   `akter`   KO je izvršio radnju (stranka u događaju)
#   `izvor`   KAKO je sadržaj nastao                    <- ovde
#   potvrda   DA LI je čovek odobrio izvršivu upotrebu  (audit_immutable)
#   `vaznost` KOLIKO je događaj važan
#
# FAZA 6.2.1 je dokazala šta se dešava kad jedno polje nosi dva značenja:
# `api.py::predmet_upload_auto_analyze` upisuje LLM tekst u `akter`, pa je
# AI rok stizao do kapije kao „Poslodavac DOO Sever" i prolazio kao ljudski.
IZVOR_AI_AUTONOMOUS = "AI_AUTONOMOUS"   # model proizveo sadržaj, čovek ga nije video pre upisa
IZVOR_AI_ASSISTED   = "AI_ASSISTED"     # čovek dao/video vrednost, model je samo strukturirao
IZVOR_HUMAN_DIRECT  = "HUMAN_DIRECT"    # čovek uneo sadržaj rukom
IZVOR_DETERMINISTIC = "DETERMINISTIC"   # statički katalog u kodu, čovek izabrao
IZVOR_SYSTEM        = "SYSTEM"          # posledica lifecycle događaja, nije opažanje
IZVOR_LEGACY        = "LEGACY_UNKNOWN"  # nastalo pre ugovora, poreklo nedokazivo

#: Isti skup koji drži `CHECK` iz migracije 127. Držati usklađeno.
IZVOR_DOZVOLJENI: tuple = (
    IZVOR_AI_AUTONOMOUS, IZVOR_AI_ASSISTED, IZVOR_HUMAN_DIRECT,
    IZVOR_DETERMINISTIC, IZVOR_SYSTEM, IZVOR_LEGACY,
)

# FAZA 6.4.2 — UKLONJENO: `IZVOR_SME_BEZ_POTVRDE` i `IZVOR_TRAZI_POTVRDU`.
#
# FAZA 6.4.1 je dokazala da je taj koncept BIO ista greška koju su faze 6.1–6.3
# razotkrile kod `akter`: polje koje opisuje POREKLO počelo je da odlučuje o
# OVLAŠĆENJU. Izmereno: 4 od 6 klasa (`AI_ASSISTED`, `HUMAN_DIRECT`,
# `DETERMINISTIC`, `SYSTEM`) prolazile su kapiju nepotvrđene.
#
# Provenijencija ostaje — ali isključivo kao podatak za audit, objašnjenje i
# buduću politiku. NIJEDNA njena vrednost više ne proizvodi `ALLOW`.
#
# Namerno NE postoji zamenska lista „bezbednih izvora". Svaka takva lista je
# isti oblik greške; jedini način da je budući developer ne uvede je da je
# pojam ne postoji.

#: Potpisi u `predmet_hronologija.akter` koje upisuju AI proizvođači.
#: `Genome (AI)`   — routers/case_dna.py::_sync_rokovi_to_hronologija
#: `Pipeline (AI)` — services/case_pipeline.py
#: Vrednost se poredi DOSLOVNO: nepoznat akter NIJE AI (fail-open za ljudski
#: unos je ispravan — ljudski rok nikad nije bio gejtovan i ne postaje sada).
AI_AKTERI: tuple = ("Genome (AI)", "Pipeline (AI)")


def je_ai_poreklo(akter: Optional[str]) -> bool:
    """ZASTARELO ZA BEZBEDNOST — ne koristiti kao provenijenciju.

    Zadržano samo za prikaz i za regresione testove koji dokumentuju zašto je
    `akter` bio pogrešan izbor (FAZA 6.2.1). Kanonsko poreklo je `izvor`.

    Da li je ovaj red hronologije proizveo AI, a ne čovek?

    Namerno DOSLOVNO poređenje, bez `startswith`/`in`: labav test bi svrstao
    ljudski unos „Pipeline (AI) je pogrešio" u AI poreklo i tiho ugasio
    korisnikov sopstveni rok."""
    return (akter or "") in AI_AKTERI


# ═══════════════════════════════════════════════════════════════════════════
# FAZA 6.5 — JEDNA POLITIKA, VISE POTROSACA
#
# Do 6.4.2 je postojala samo odluka „sme li ovo da POKRENE akciju". FAZA 6.4.3
# je izmerila da to nije dovoljno: 36 od 43 modula koji dodiruju rokove
# OTKRIVAJU podatak umesto da izvrsavaju akciju, a klijentski portal je
# nepotvrdjen AI rok pokazivao trecem licu.
#
# Zato postoji JEDNA funkcija sa cetiri vrste potrosaca. Svaki kanal pita istu
# stvar i dobija odgovor po istom pravilu — nema `email politike`, `portal
# politike` i `izvoz politike` koje se vremenom raziđu.
# ═══════════════════════════════════════════════════════════════════════════

#: Ko trazi pristup roku.
POTROSAC_INTERNI = "INTERNAL"        # ovlascen advokat u svojoj kancelariji
POTROSAC_KLIJENT = "CLIENT"          # trece lice (klijentski portal)
POTROSAC_IZVOZ_SPOLJA = "EXPORT_EXTERNAL"   # sadrzaj napusta advokatov prostor
POTROSAC_AKCIJA = "ACTION"           # email/SMS/Viber/WhatsApp/kalendar

POTROSACI: tuple = (POTROSAC_INTERNI, POTROSAC_KLIJENT,
                    POTROSAC_IZVOZ_SPOLJA, POTROSAC_AKCIJA)


def sme_pristupiti(red: dict, odluke_mapa: Optional[dict] = None,
                   *, potrosac: str = POTROSAC_AKCIJA) -> bool:
    """Kanonska odluka: sme li OVAJ potrosac da dobije OVAJ rok?

    Ulaz je stanje odluke nad tacnim `red["id"]` — nista drugo. `izvor`,
    `akter` i `vaznost` se ne citaju ni ovde ni bilo gde nizvodno.

    Politika po potrosacu:

        stanje          INTERNAL   CLIENT   EXPORT_EXTERNAL   ACTION
        UNCONFIRMED     vidi       NE       NE                NE
        CONFIRMED       vidi       vidi     vidi              sme
        REJECTED        vidi       NE       NE                NE

    `INTERNAL` namerno vidi sve: advokat mora videti kandidata da bi ga uopste
    mogao potvrditi ili odbiti, a odbijen rok mora ostati u istoriji.
    ODBIJEN NIJE OBRISAN.

    Nepoznat potrosac je fail-closed — bolje da nova povrsina ne vidi nista
    nego da tiho dobije sve.
    """
    from shared.rok_potvrda import (
        STANJE_ODBIJEN, STANJE_POTVRDJEN, stanje_roka,
    )
    rid = red.get("id")
    if not rid:
        # Bez identiteta se red ne moze dovesti u vezu ni sa jednom odlukom.
        return potrosac == POTROSAC_INTERNI
    stanje = stanje_roka(rid, odluke_mapa)
    if potrosac == POTROSAC_INTERNI:
        return True
    if potrosac in (POTROSAC_KLIJENT, POTROSAC_IZVOZ_SPOLJA, POTROSAC_AKCIJA):
        return stanje == STANJE_POTVRDJEN
    return False        # nepoznat potrosac -> nista


def filtriraj_za(redovi: Optional[list], odluke_mapa: Optional[dict] = None,
                 *, potrosac: str = POTROSAC_AKCIJA) -> list:
    """Primena `sme_pristupiti` na listu."""
    return [r for r in (redovi or [])
            if sme_pristupiti(r, odluke_mapa, potrosac=potrosac)]


def sme_pokrenuti_obavezu(red: dict, potvrdjeni_ids: Optional[set] = None) -> bool:
    """JEDINA odluka o tome sme li se rok pretvoriti u izvršivu posledicu
    (email, SMS, Viber, WhatsApp, notifikacija, kalendar).

    Ulaz je ISKLJUČIVO stanje ovlašćenja. Ni `izvor`, ni `akter`, ni `vaznost`
    ne učestvuju — i to nije previd nego cela poenta:

        `akter`   KO je izvršio radnju        -> nikad nije bio ovlašćenje
        `izvor`   KAKO je sadržaj nastao      -> opis porekla, ne dozvola
        `vaznost` KOLIKO je važno             -> prioritet, ne dozvola
        potvrda   DA LI je čovek odobrio      -> JEDINO ovlašćenje

    FAZA 6.2 je gejtovala po `akter` i to je palo (6.2.1: model je upisivao ime
    stranke u to polje). FAZA 6.4 je gejtovala po `izvor` i to je palo (6.4.1:
    4/6 klasa je prolazilo nepotvrđeno). Zajednički uzrok oba pada je isti —
    atribut koji OPISUJE zapis dobio je moć da ga ODOBRI.

    Zato ovde nema nijedne grane po sadržaju reda. Nepotvrđeno je zabranjeno,
    bez izuzetka i bez obzira na to ko ga je napisao i koliko je hitno.

    POSLEDICA KOJU TREBA ZNATI: dok ne postoji površina kojom advokat potvrđuje
    rok, ova funkcija vraća `False` za svaki rok. To je namerno stanje —
    fail-closed — a ne kvar.
    """
    # FAZA 6.5: jedan vlasnik odluke. Ova funkcija je ACTION slucaj opste
    # politike `sme_pristupiti` — zadrzana je zato sto 7 izlaznih kanala vec
    # prosledjuje SKUP potvrdjenih id-eva, a ne mapu odluka. Prevod je ovde,
    # na jednom mestu, umesto u sedam poziva.
    from shared.rok_potvrda import STANJE_POTVRDJEN
    mapa = {str(x): STANJE_POTVRDJEN for x in (potvrdjeni_ids or set())}
    return sme_pristupiti(red, mapa, potrosac=POTROSAC_AKCIJA)


def filtriraj_izvrsive(redovi: Optional[list], potvrdjeni_ids: Optional[set] = None) -> list:
    """Primena `sme_pokrenuti_obavezu` na listu redova hronologije."""
    return [r for r in (redovi or []) if sme_pokrenuti_obavezu(r, potvrdjeni_ids)]


# ════════════════════════════════════════════════════════════════════════════
# Z016.2 — MINIMALNI UGOVOR ROKA: VRSTA i STANJE (migracija 129)
# ════════════════════════════════════════════════════════════════════════════
#
# Tri signala, tri odvojene uloge. Nijedan ne sme preuzeti tuđu — to je greška
# koju su FAZE 6.1–6.4.1 već platile dvaput (`akter`, pa `izvor`):
#
#     izvor    KAKO je red nastao       provenijencija (migracija 127)
#     vrsta    ŠTA red jeste            migracija 129
#     stanje   GDE je u životnom ciklusu migracija 129
#
# `vrsta` je jedini dozvoljen odgovor na pitanje „je li ovo rok". Pogađanje po
# tekstu (`_klasifikuj_dogadjaj` sa catch-all granom) i po `akter` je zabranjeno
# i pokriveno testom.

VRSTA_ROK      = "rok"        # obaveza sa rokom
VRSTA_ROCISTE  = "rociste"    # zakazano ročište
VRSTA_ZADATAK  = "zadatak"    # zadatak kancelarije
VRSTA_DOGADJAJ = "dogadjaj"   # istorijska činjenica predmeta — NIJE obaveza

#: Isti skup koji drži CHECK iz migracije 129. Držati usklađeno.
VRSTE_DOZVOLJENE: tuple = (VRSTA_ROK, VRSTA_ROCISTE, VRSTA_ZADATAK, VRSTA_DOGADJAJ)

STANJE_KANDIDAT  = "kandidat"    # predložen, čovek se nije izjasnio
STANJE_POTVRDJEN = "potvrdjen"   # čovek potvrdio
STANJE_ODBIJEN   = "odbijen"     # čovek odbio; NIJE obrisan
STANJE_IZVRSEN   = "izvrsen"     # obaveza izvršena
STANJE_OTKAZAN   = "otkazan"     # obaveza otkazana

STANJA_DOZVOLJENA: tuple = (STANJE_KANDIDAT, STANJE_POTVRDJEN, STANJE_ODBIJEN,
                            STANJE_IZVRSEN, STANJE_OTKAZAN)

#: Stanja koja su razrešena — rok koji je u njima NE traži više pažnju i ne
#: sme se pojaviti na aktivnom ekranu Danas.
STANJA_RAZRESENA: frozenset = frozenset({STANJE_ODBIJEN, STANJE_IZVRSEN, STANJE_OTKAZAN})

#: Prevod stanja odluke (audit trag) u domensko stanje. Postoji zato što su
#: legacy redovi bez `stanje` i dalje čitljivi kroz model potvrde.
_ODLUKA_U_STANJE = {
    "CONFIRMED": STANJE_POTVRDJEN,
    "REJECTED": STANJE_ODBIJEN,
    "UNCONFIRMED": STANJE_KANDIDAT,
}


def je_rok(red: Optional[dict]) -> bool:
    """Je li ovaj red rok — po IZJAVI, ne po pogađanju.

    `NULL` vrsta znači „nije izjavljeno" i vraća `False`: fail-closed. Zatečeni
    red se ne proglašava rokom retroaktivno.
    """
    return bool(red) and (red.get("vrsta") or "").strip().lower() == VRSTA_ROK


#: Stanja koja audit lanac NE MOZE da izrazi — za njih nema ni akcije ni
#: znacenja u `audit_immutable`. Samo ona imaju prednost nad odlukom.
STANJA_SAMO_KOLONA: frozenset = frozenset({STANJE_IZVRSEN, STANJE_OTKAZAN})


def stanje_zapisa(red: Optional[dict], odluke_mapa: Optional[dict] = None) -> Optional[str]:
    """Domensko stanje reda.

    PODELA ODGOVORNOSTI, i ona nije proizvoljna:

      `izvrsen` / `otkazan`   -> kolona `stanje` (migracija 129). Audit lanac ih
                                 ne moze izraziti; za njih tamo nema akcije.
      `potvrdjen` / `odbijen` -> audit lanac, gde ih je FAZA 6.5 namerno
                                 smestila. Ruta odluke SME SAMO DA CITA
                                 hronologiju — to je strukturno zakljucano
                                 (`test_ruta_odluke_ne_menja_rok`), pa potvrda
                                 ovde ne sme postati upis u red.

    Kolona se cita i za ostala stanja, ali TEK ako odluke nema — tako pisac koji
    upise `kandidat` ne moze pregaziti kasniju potvrdu.
    """
    if not red:
        return None
    s = (red.get("stanje") or "").strip().lower()
    if s in STANJA_SAMO_KOLONA:
        return s
    rid = red.get("id")
    if rid:
        from shared.rok_potvrda import stanje_roka
        iz_odluke = _ODLUKA_U_STANJE.get(stanje_roka(rid, odluke_mapa))
        if iz_odluke and iz_odluke != STANJE_KANDIDAT:
            return iz_odluke
    if s in STANJA_DOZVOLJENA:
        return s
    return STANJE_KANDIDAT if rid else None


def je_razresen(red: Optional[dict], odluke_mapa: Optional[dict] = None) -> bool:
    """Razrešen rok ne ulazi u aktivni Danas — ni odbijen, ni izvršen, ni otkazan."""
    return stanje_zapisa(red, odluke_mapa) in STANJA_RAZRESENA


# ── Upisna strana ───────────────────────────────────────────────────────────
#
# Pisci ne smeju pasti ako migracija 129 još nije pokrenuta: `INSERT` sa
# nepostojećom kolonom vraća 42703 i oborio bi stvaranje roka u produkciji.
# Zato se sposobnost šeme proverava jednom po procesu i kešira.

_KOLONE_129: Optional[bool] = None


def _sema_ima_129(supa) -> bool:
    global _KOLONE_129
    if _KOLONE_129 is not None:
        return _KOLONE_129
    try:
        supa.table("predmet_hronologija").select("vrsta, stanje").limit(1).execute()
        _KOLONE_129 = True
    except Exception:
        logger.info("[ROKOVI] migracija 129 nije primenjena — `vrsta`/`stanje` se ne upisuju")
        _KOLONE_129 = False
    return _KOLONE_129


def _resetuj_sondu() -> None:
    """Samo za testove."""
    global _KOLONE_129
    _KOLONE_129 = None


def oznake(*, vrsta: str, stanje: Optional[str] = None, supa=None) -> dict:
    """Fragment za `**` unutar `insert({...})`.

    Postoji zato sto omotavanje celog recnika (`insert(oznaci({...}))`) menja
    OBLIK poziva, a dva testa iz B8 mere bas taj oblik da bi dokazala da se
    `dokument_id` stvarno upisuje. Fragment cuva `insert({` doslovno.
    """
    if vrsta not in VRSTE_DOZVOLJENE:
        raise ValueError(f"nepoznata vrsta zapisa: {vrsta!r}")
    if stanje is not None and stanje not in STANJA_DOZVOLJENA:
        raise ValueError(f"nepoznato stanje: {stanje!r}")
    if supa is None or not _sema_ima_129(supa):
        return {}
    out = {"vrsta": vrsta}
    if stanje is not None:
        out["stanje"] = stanje
    return out


def oznaci(red: dict, *, vrsta: str, stanje: Optional[str] = None, supa=None) -> dict:
    """Dodaje eksplicitnu `vrsta`/`stanje` semantiku redu pre upisa.

    Kada migracija 129 nije primenjena, red se vraća NEIZMENJEN — pisac i dalje
    radi, a čitalac ostaje fail-closed. To je jedini način da se ugovor uvede
    bez prozora u kom stvaranje roka puca.
    """
    if vrsta not in VRSTE_DOZVOLJENE:
        raise ValueError(f"nepoznata vrsta zapisa: {vrsta!r}")
    if stanje is not None and stanje not in STANJA_DOZVOLJENA:
        raise ValueError(f"nepoznato stanje: {stanje!r}")
    if supa is None or not _sema_ima_129(supa):
        return red
    red["vrsta"] = vrsta
    if stanje is not None:
        red["stanje"] = stanje
    return red
