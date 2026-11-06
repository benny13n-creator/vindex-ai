# -*- coding: utf-8 -*-
"""
Vindex AI — shared/ai_budget.py

AI BUDŽETSKA BRANA NA GRANICI PROVAJDERA (Early Access, Faza A).

PROBLEM (izmeren, v. docs/release/EARLY_ACCESS_AI_COST_PROTECTION.md)
  `UsageService.consume()` je od početka projektovan da se zove POSLE AI poziva
  („generiši AI odgovor, pa consume"). Statički inventar: od 81 rute koje dosežu
  provajdera, 55 naplaćuje tek posle poziva, 23 ne naplaćuje uopšte, 3 pre poziva.
  Nalog sa 0 kredita zato izvršava plaćen AI poziv, pa tek onda dobije 402 —
  trošak je napravljen, korisnik ga ne plaća. Isto važi za svaki SDK retry.

REŠENJE — BEZ NOVOG SISTEMA PRAVA I BEZ NOVE TABELE
  Ovaj modul NIJE drugi sistem prava ni drugi izvor cena. On samo primenjuje
  postojeće odluke na jedinoj tački kroz koju prolazi svaki OpenAI poziv
  (`shared/ai_client.py`, patch na SDK klasama, SEC-003):

    • ko i za koju funkciju  → `PermissionService.require(feature)` veže operaciju
    • cena i limiti          → `feature_registry` (krediti, dnevni/mesečni limit, cooldown)
    • rezervacija            → `UsageService` (atomični `deduct_n_credits`, migr. 107;
                               atomični `increment_feature_usage`, migr. 108)

  Operacija = jedan HTTP zahtev (ili jedan pozadinski posao). Pre PRVOG poziva
  provajdera u operaciji, brana rezerviše budžet funkcije kroz UsageService. Kada
  ruta kasnije pozove `consume()` (postojeći obrazac), to postaje NAMIRENJE iste
  operacije, ne druga naplata.

INVARIJANTE (svaka ima deterministički test, tests/test_ai_cost_protection.py)
  1. Nijedan poziv provajdera bez rezervacije (ne-founder korisnik).
  2. Rezervacija je atomična u bazi; 20 paralelnih zahteva ne može da potroši više
     nego što stanje pokriva.
  3. Greška baze pri rezervaciji BLOKIRA poziv (fail-closed), uključujući dnevni brojač.
  4. Identitet je uvek iz verifikovanog tokena; kontekst drugog korisnika u istoj
     operaciji se odbija.
  5. Svaki HTTP pokušaj ka provajderu (i SDK-ov interni retry) broji se u operaciju.
  6. Model, veličina ulaza i izlaza su ograničeni pre poziva.
  7. Founder i pozadinski poslovi ne plaćaju kredite, ali PROLAZE kroz iste granice
     modela/veličine/operacije i kroz projektni mesečni limit.
  8. Nepoznat ishod (timeout/prekid veze) se NE vraća korisniku automatski — zadržava
     se i beleži za ručno usklađivanje.

PODEŠAVANJE (env; podrazumevane vrednosti su predlog za pilot, menja ih osnivač)
  VINDEX_AI_BUDZET                 enforce | off   (off = hitno vraćanje, samo uz odluku)
  VINDEX_AI_MODELI                 dozvoljeni modeli, zarezom
  VINDEX_AI_MAX_ULAZ_TOKENA        procena ulaza po pozivu
  VINDEX_AI_MAX_IZLAZ_TOKENA       max_tokens po pozivu
  VINDEX_AI_MAX_POKUSAJA_OPERACIJE HTTP pokušaja ka provajderu po operaciji
  VINDEX_AI_MAX_USD_OPERACIJE      procenjen trošak po operaciji
  VINDEX_AI_PROJEKAT_MESECNI_USD   projektni mesečni limit U OVOM PROCESU (nije trajan —
                                   trajna granica je hard limit OpenAI projekta, v. A3)
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("vindex.ai_budget")

# Registry red za AI rad koji nije vezan za posebnu funkciju (ručna autentifikacija bez
# PermissionService, pozadinski poslovi). Migracija 146. Bez reda → rezervacija pada →
# poziv se odbija (fail-closed), nikad se ne pušta „jer ne znam cenu".
OSNOVNA_FUNKCIJA = "ai_osnovna_obrada"

_PODRAZUMEVANI_MODELI = (
    "gpt-4o,gpt-4o-mini,gpt-4o-2024-08-06,text-embedding-3-small,text-embedding-3-large,whisper-1,tts-1"
)

# USD po 1.000 tokena (ulaz, izlaz). Chat cene su iz shared/cost.py (jedan izvor);
# ovde se dodaju samo modaliteti koje cost.py ne pokriva. Nepoznat model se ovde
# nikad ne procenjuje — odbija ga lista dozvoljenih modela pre procene.
_DODATNE_CENE = {
    "gpt-4o-2024-08-06": {"input": 0.0025, "output": 0.0100},
    "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
    "text-embedding-3-large": {"input": 0.00013, "output": 0.0},
    # Whisper/TTS se ne naplaćuju po tokenu; procena po pozivu je namerno konzervativna.
    "whisper-1": {"po_pozivu": 0.05},
    "tts-1": {"po_pozivu": 0.05},
}


def _env_float(ime: str, podrazumevano: float) -> float:
    try:
        return float(os.getenv(ime, "") or podrazumevano)
    except ValueError:
        logger.error("[AI_BUDZET] %s nije broj — koristim %s", ime, podrazumevano)
        return podrazumevano


def rezim() -> str:
    v = (os.getenv("VINDEX_AI_BUDZET") or "enforce").strip().lower()
    return "off" if v == "off" else "enforce"


def dozvoljeni_modeli() -> set[str]:
    return {m.strip() for m in (os.getenv("VINDEX_AI_MODELI") or _PODRAZUMEVANI_MODELI).split(",") if m.strip()}


def max_ulaz() -> int:
    return int(_env_float("VINDEX_AI_MAX_ULAZ_TOKENA", 100_000))


def max_izlaz() -> int:
    return int(_env_float("VINDEX_AI_MAX_IZLAZ_TOKENA", 8_000))


def max_pokusaja() -> int:
    return int(_env_float("VINDEX_AI_MAX_POKUSAJA_OPERACIJE", 60))


def max_usd_operacije() -> float:
    return _env_float("VINDEX_AI_MAX_USD_OPERACIJE", 3.0)


def _granice(op: "Operacija") -> tuple[int, float]:
    """(pokušaja, USD) po operaciji. Sistemska operacija (cron dispečer koji obrađuje
    sve naloge) ima šire, ali i dalje konačne granice — i ide u projektni limit."""
    if op.sistemska:
        return (int(_env_float("VINDEX_AI_MAX_POKUSAJA_SISTEM", 600)),
                _env_float("VINDEX_AI_MAX_USD_SISTEM", 15.0))
    return max_pokusaja(), max_usd_operacije()


def projektni_limit_usd() -> float:
    return _env_float("VINDEX_AI_PROJEKAT_MESECNI_USD", 50.0)


class AIBudzetOdbijen(RuntimeError):
    """Poziv provajdera je odbijen PRE slanja ijednog tokena.

    Nasleđuje `RuntimeError`, ne `openai.APIError`: `shared/llm_retry.py` ponavlja
    samo provajderske greške, a ponavljanje odbijenog budžeta bi bilo petljanje.
    `api.py` ga prevodi u HTTP odgovor sa `status`/`detail`.
    """

    def __init__(self, kod: str, poruka: str, status: int = 402, detalj: Optional[dict] = None):
        super().__init__(f"{kod}: {poruka}")
        self.kod = kod
        self.poruka = poruka
        self.status = status
        self.detalj = {"code": kod, "message": poruka, **(detalj or {})}


@dataclass
class Operacija:
    user_id: Optional[str]
    email: str = ""
    feature: Optional[str] = None
    founder: bool = False
    sistemska: bool = False
    izvor: str = ""
    # rezervacija
    rezervisana: bool = False
    hold: int = 0                 # krediti oduzeti rezervacijom brane, još nenamireni
    namirena: bool = False        # consume() je namirio rezervaciju ove operacije
    # Multiplikator cene koji ruta izjavljuje PRE prvog poziva provajdera
    # (`ocekivani_multiplikator`). None = podrazumevani iz registra (`credit_multiplier`),
    # isti koji `consume()` naplaćuje kada ruta ne prosledi `multiplier=`.
    multiplikator: Optional[float] = None
    osnovna_cena: int = 0         # krediti × 1 — jedini deo koji se zadržava pri nepoznatom ishodu
    zatvorena: bool = False
    # brojači (svi pod _lock)
    pokusaja: int = 0
    usd_procena: float = 0.0
    usd_stvarno: float = 0.0
    tokena_ulaz: int = 0
    tokena_izlaz: int = 0
    stvarno_nedostupno: int = 0
    uspesnih: int = 0
    definitivnih_gresaka: int = 0
    nepoznatih: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _rez_u_toku: Optional[threading.Event] = field(default=None, repr=False)
    _rez_greska: Optional[AIBudzetOdbijen] = field(default=None, repr=False)


# Držač je PROMENLJIV dict koji middleware postavlja na početku zahteva. Kontekst se
# kopira u `asyncio.to_thread`, `create_task` i BaseHTTPMiddleware zadatke, ali svi
# vide ISTI dict — pa vezivanje u dependency-ju i rezervacija u niti pozadinskog
# posla pišu u istu operaciju, a middleware je na kraju vidi i namiruje.
_drzac: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("vindex_ai_budzet_drzac", default=None)
_tekuci_tiket: contextvars.ContextVar[Optional["Tiket"]] = contextvars.ContextVar("vindex_ai_budzet_tiket", default=None)


# ── Projektni mesečni limit (u procesu) ───────────────────────────────────────
# Produkcija je JEDAN uvicorn proces (izmereno, shared/ai_client.py S1-2), pa je ovo
# zbir celog servisa do restarta. NIJE trajno — restart ga nulira. Trajna projektna
# granica je hard limit OpenAI projekta (A3); ovo je brz, lokalni prekidač koji važi i
# za founder i za pozadinu i hvata odbeglu petlju pre nego što stigne do provajdera.
_projekat_lock = threading.Lock()
_projekat = {"mesec": "", "usd": 0.0}


def _mesec() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def projektna_potrosnja() -> float:
    with _projekat_lock:
        return _projekat["usd"] if _projekat["mesec"] == _mesec() else 0.0


def _dodaj_projektu(usd: float) -> None:
    """Dodaje procenu ili ispravku (stvarno − procena, može biti negativna); zbir ne pada ispod nule."""
    with _projekat_lock:
        m = _mesec()
        if _projekat["mesec"] != m:
            _projekat["mesec"], _projekat["usd"] = m, 0.0
        _projekat["usd"] = max(_projekat["usd"] + usd, 0.0)


def _resetuj_projekat_za_test() -> None:
    with _projekat_lock:
        _projekat["mesec"], _projekat["usd"] = "", 0.0


# ── Vezivanje operacije ───────────────────────────────────────────────────────

def otvori_zahtev(http: bool = True) -> contextvars.Token:
    """Middleware: svež držač po zahtevu (nema curenja operacije između zahteva)."""
    return _drzac.set({"op": None, "http": http})


def tekuca_operacija() -> Optional[Operacija]:
    d = _drzac.get()
    return d.get("op") if d else None


def vezi(user_id: str, email: str, feature: str, *, founder: bool) -> Optional[Operacija]:
    """Poziva `PermissionService.require` posle uspešne autorizacije.

    Prva vezana funkcija u operaciji ostaje vezana dok rezervacija ne nastane; drugi
    `require` u istom zahtevu (ruta sa dva dependency-ja) ne pravi drugu operaciju.
    Vezivanje za DRUGOG korisnika u istom držaču pravi novu operaciju — nikad ne
    meša budžete dva naloga.
    """
    d = _drzac.get()
    if d is None:
        d = {"op": None, "http": False}
        _drzac.set(d)
    op = d.get("op")
    if op is not None and op.user_id == user_id and not op.zatvorena:
        if not op.rezervisana and op.feature in (None, OSNOVNA_FUNKCIJA):
            op.feature = feature
        return op
    op = Operacija(user_id=user_id, email=email or "", feature=feature, founder=founder, izvor="permission")
    d["op"] = op
    return op


@contextmanager
def operacija(user_id: Optional[str], email: str = "", feature: Optional[str] = None, *,
              sistemska: bool = False, founder: bool = False, izvor: str = "pozadina"):
    """Jedna pozadinska/sistemska jedinica rada = jedna operacija sa sopstvenim
    granicama. Na izlazu se namiruje (`zatvori`). Za cron/sistem bez korisnika:
    `operacija(None, sistemska=True, izvor="cron:...")`."""
    op = Operacija(user_id=user_id, email=email or "", feature=feature or (None if sistemska else OSNOVNA_FUNKCIJA),
                   sistemska=sistemska, founder=founder, izvor=izvor)
    tok = _drzac.set({"op": op, "http": False})
    try:
        yield op
    finally:
        try:
            zatvori(op)
        finally:
            _drzac.reset(tok)


def sistemska(oznaka: str) -> Operacija:
    """Sistemska ruta (cron, admin dijagnostika) u HTTP zahtevu: bez korisnika, ali
    unutar istih granica i projektnog limita. Poziva se POSLE provere tajne/ključa."""
    d = _drzac.get()
    op = Operacija(user_id=None, sistemska=True, izvor=f"sistem:{oznaka}")
    if d is None:
        _drzac.set({"op": op, "http": False})
    else:
        d["op"] = op
    return op


# ── Procena ───────────────────────────────────────────────────────────────────

def _cena(model: str) -> dict:
    from shared.cost import _PRICES
    return _PRICES.get(model) or _DODATNE_CENE.get(model) or {}


def _procena_ulaza(vrsta: str, kwargs: dict) -> int:
    """Konzervativna procena ulaznih tokena (≈3 znaka po tokenu za srpski/JSON).
    Precizan broj zna tek provajder; ovde treba gornja granica PRE slanja."""
    if vrsta == "chat":
        sirovo = json.dumps(kwargs.get("messages") or [], ensure_ascii=False, default=str)
    elif vrsta == "embedding":
        ulaz = kwargs.get("input")
        sirovo = ulaz if isinstance(ulaz, str) else json.dumps(ulaz or [], ensure_ascii=False, default=str)
    elif vrsta == "tts":
        sirovo = str(kwargs.get("input") or "")
    else:
        return 0
    return len(sirovo) // 3 + 1


def _procena_usd(model: str, ulaz: int, izlaz: int) -> float:
    c = _cena(model)
    if "po_pozivu" in c:
        return float(c["po_pozivu"])
    return ulaz / 1000 * c.get("input", 0.0) + izlaz / 1000 * c.get("output", 0.0)


# ── Rezervacija ───────────────────────────────────────────────────────────────

def _pokreni(coro):
    """Izvrši korutinu sinhrono — i iz radne niti (bez petlje) i iz niti koja već ima
    petlju (sinhroni `create` pozvan direktno u async ruti)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    rezultat: dict = {}

    def _nit():
        try:
            rezultat["v"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 — prenosi se pozivaocu
            rezultat["e"] = exc

    t = threading.Thread(target=_nit, name="ai-budzet-rezervacija", daemon=True)
    t.start()
    t.join()
    if "e" in rezultat:
        raise rezultat["e"]
    return rezultat.get("v")


def _osiguraj_rezervaciju(op: Operacija) -> None:
    """Pre prvog poziva provajdera: rezerviši budžet funkcije kroz UsageService.

    Jedan let po operaciji: paralelni podpozivi iste operacije (asyncio.gather) čekaju
    isti ishod umesto da svaki rezerviše za sebe (dupla naplata).
    """
    if op.sistemska or op.founder:
        return
    with op._lock:
        if op.rezervisana:
            return
        cekaj = op._rez_u_toku
        if cekaj is None:
            op._rez_u_toku = threading.Event()
            op._rez_greska = None
    if cekaj is not None:
        cekaj.wait(timeout=60)
        if op.rezervisana:
            return
        raise op._rez_greska or AIBudzetOdbijen(
            "BUDZET_NEDOSTUPAN", "Budžet trenutno ne može da se potvrdi. Ništa nije naplaćeno.", 503)

    from fastapi import HTTPException

    from shared.usage import UsageService
    try:
        if not op.user_id or not op.feature:
            raise AIBudzetOdbijen("NEVEZANA_OPERACIJA", "AI obrada nije vezana za nalog i funkciju.", 403)
        held = _pokreni(UsageService.rezervisi_za_operaciju(op))
        with op._lock:
            op.hold = int(held or 0)
            op.rezervisana = True
        logger.info("[AI_BUDZET] rezervisano uid=%.8s feature=%s krediti=%d", op.user_id, op.feature, op.hold)
    except AIBudzetOdbijen as exc:
        op._rez_greska = exc
        raise
    except HTTPException as exc:
        det = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        greska = AIBudzetOdbijen(det.get("code") or "BUDZET_ODBIJEN", det.get("message") or "AI budžet nije dostupan.",
                                 exc.status_code, {k: v for k, v in det.items() if k not in ("code", "message")})
        op._rez_greska = greska
        raise greska from exc
    except Exception as exc:
        # Baza/registar nedostupni: NE PUŠTAJ. Ništa nije poslato provajderu.
        logger.error("[AI_BUDZET] rezervacija nije uspela uid=%.8s feature=%s: %s",
                     op.user_id or "?", op.feature, type(exc).__name__)
        greska = AIBudzetOdbijen("BUDZET_NEDOSTUPAN",
                                 "Budžet trenutno ne može da se potvrdi. Ništa nije naplaćeno ni izvršeno.", 503)
        op._rez_greska = greska
        raise greska from exc
    finally:
        with op._lock:
            ev, op._rez_u_toku = op._rez_u_toku, None
        if ev is not None:
            ev.set()


def ocekivani_multiplikator(n: float) -> None:
    """Ruta izjavljuje multiplikator cene PRE prvog poziva provajdera.

    Brana rezerviše PUNU cenu operacije (krediti × multiplikator) pre prvog poziva, da
    nalog koji nema punu cenu nikad ne pokrene plaćen poziv. Podrazumevani multiplikator
    je onaj iz registra (`credit_multiplier`); ruta koja naplaćuje drugačije — jedan
    modul (`multiplier=1`) ili gornju granicu dinamičke operacije (broj savetnika) — mora
    to da kaže ovde, pre poziva. Neiskorišćeni deo rezervacije vraća se na kraju operacije.
    """
    if rezim() == "off":
        return
    op = tekuca_operacija()
    if op is None or op.sistemska or op.founder:
        return
    with op._lock:
        if op.rezervisana:
            # Programska greška rute: cena je već rezervisana. Ne menja se naknadno —
            # namirenje i dalje naplaćuje stvarnu cenu iz `consume()`.
            logger.error("[AI_BUDZET] multiplikator %s izjavljen POSLE rezervacije uid=%.8s feature=%s — ignorisano",
                         n, op.user_id or "?", op.feature)
            return
        op.multiplikator = float(n)


def oznaci_rezervisano_kroz_consume(op: Operacija) -> None:
    """`consume()` je naplatio PRE AI poziva (pre-deduct obrazac) — brana ne sme da
    rezerviše još jednom u istoj operaciji."""
    with op._lock:
        op.rezervisana = True
        op.namirena = True


# ── Tiket jednog logičkog poziva ──────────────────────────────────────────────

@dataclass
class Tiket:
    vrsta: str
    model: str
    op: Optional[Operacija]
    usd_procena: float
    pokusaja: int = 0


def _razresi_operaciju() -> Optional[Operacija]:
    """Operacija kojoj ovaj poziv pripada. Može da napravi automatsku operaciju za
    autentifikovanog korisnika koji nije prošao kroz PermissionService."""
    d = _drzac.get()
    op = d.get("op") if d else None
    try:
        from shared.ai_provenance import current_context
        ctx_uid = (current_context() or {}).get("user_id")
    except Exception:
        ctx_uid = None
    if ctx_uid in ("", "cron-scheduler"):
        ctx_uid = None

    if op is not None:
        if ctx_uid and op.user_id and ctx_uid != op.user_id:
            raise AIBudzetOdbijen("IDENTITET_SE_NE_POKLAPA",
                                  "AI poziv pripada drugom nalogu od operacije. Odbijeno.", 403)
        if op.user_id is None and not op.sistemska and ctx_uid:
            op.user_id = ctx_uid
        return op

    if ctx_uid:
        # Autentifikovan korisnik bez PermissionService vezivanja (ručna autentifikacija,
        # pozadinski događaj): rezervacija ide na osnovnu AI funkciju iz registra.
        op = Operacija(user_id=ctx_uid, feature=OSNOVNA_FUNKCIJA, izvor="automatski")
        if d is not None:
            d["op"] = op
        return op

    if d is not None and d.get("http"):
        # HTTP zahtev bez korisnika i bez izričite sistemske oznake: javna ruta ne sme
        # da troši AI budžet.
        raise AIBudzetOdbijen("NEVEZAN_HTTP_POZIV", "AI obrada zahteva prijavljen nalog.", 401)

    # Van HTTP-a, bez korisnika: proces/startup posao. Sistemska operacija za ovaj poziv.
    return Operacija(user_id=None, sistemska=True, izvor="proces")


def _pripremi(vrsta: str, kwargs: dict) -> Tiket:
    model = str(kwargs.get("model") or "")
    if model not in dozvoljeni_modeli():
        raise AIBudzetOdbijen("MODEL_NIJE_DOZVOLJEN", f"Model '{model}' nije dozvoljen.", 403)

    ulaz = _procena_ulaza(vrsta, kwargs)
    if ulaz > max_ulaz():
        raise AIBudzetOdbijen("ULAZ_PREVELIK", "Dokument ili kontekst je prevelik za jednu AI obradu.", 413,
                              {"procena_tokena": ulaz, "limit": max_ulaz()})

    izlaz = 0
    if vrsta == "chat":
        trazeno = kwargs.get("max_completion_tokens") or kwargs.get("max_tokens")
        if trazeno is None:
            kwargs["max_tokens"] = max_izlaz()
            izlaz = max_izlaz()
        elif int(trazeno) > max_izlaz():
            raise AIBudzetOdbijen("IZLAZ_PREVELIK", "Traženi obim AI odgovora prelazi dozvoljeni.", 413,
                                  {"trazeno": int(trazeno), "limit": max_izlaz()})
        else:
            izlaz = int(trazeno)
        n = kwargs.get("n")
        if n not in (None, 1):
            raise AIBudzetOdbijen("IZLAZ_PREVELIK", "Više paralelnih odgovora po pozivu nije dozvoljeno.", 413)

    usd = _procena_usd(model, ulaz, izlaz)
    op = _razresi_operaciju()

    if projektna_potrosnja() + usd > projektni_limit_usd():
        logger.error("[AI_BUDZET] PROJEKTNI LIMIT: %.4f + %.4f > %.2f USD — poziv odbijen",
                     projektna_potrosnja(), usd, projektni_limit_usd())
        raise AIBudzetOdbijen("PROJEKTNI_LIMIT", "AI servis je privremeno dostigao mesečni limit.", 503)

    max_pok, max_usd = _granice(op)
    with op._lock:
        if op.pokusaja + 1 > max_pok:
            raise AIBudzetOdbijen("OPERACIJA_PREVELIKA", "AI operacija je prešla dozvoljen broj poziva.", 429)
        if op.usd_procena + usd > max_usd:
            raise AIBudzetOdbijen("OPERACIJA_PREVELIKA", "AI operacija je prešla dozvoljen trošak.", 429)
    return Tiket(vrsta=vrsta, model=model, op=op, usd_procena=usd)


def _zabelezi_pokusaj(retries_taken: int) -> None:
    """SDK `_build_request` hook: JEDAN HTTP pokušaj ka provajderu, uključujući SDK
    interne retry-je koje wrapper ne vidi."""
    if rezim() == "off":
        return
    t = _tekuci_tiket.get()
    if t is None:
        exc = AIBudzetOdbijen("NEGEJTOVAN_POZIV",
                              "Poziv provajdera ne prolazi kroz AI budžet. Odbijeno pre slanja.", 503)
        _zabelezi_odbijanje(exc)
        raise exc
    op = t.op
    max_pok, max_usd = _granice(op)
    with op._lock:
        if op.pokusaja + 1 > max_pok or (retries_taken > 0 and op.usd_procena + t.usd_procena > max_usd):
            exc = AIBudzetOdbijen("OPERACIJA_PREVELIKA", "AI operacija je prešla dozvoljen broj poziva.", 429)
            _zabelezi_odbijanje(exc)
            raise exc
        op.pokusaja += 1
        op.usd_procena += t.usd_procena
        t.pokusaja += 1
    if retries_taken > 0 and projektna_potrosnja() + t.usd_procena > projektni_limit_usd():
        exc = AIBudzetOdbijen("PROJEKTNI_LIMIT", "AI servis je privremeno dostigao mesečni limit.", 503)
        _zabelezi_odbijanje(exc)
        raise exc
    # Pokušaj koji je možda naplaćen, a čiji ishod još ne znamo, ulazi u projekat odmah;
    # stvarni trošak ga ispravlja u `_zavrsi`.
    _dodaj_projektu(t.usd_procena)


def _zavrsi(t: Tiket, response: Any, exc: Optional[BaseException]) -> None:
    op = t.op
    if exc is None:
        usage = getattr(response, "usage", None)
        p = getattr(usage, "prompt_tokens", None) if usage is not None else None
        c = getattr(usage, "completion_tokens", None) if usage is not None else None
        with op._lock:
            op.uspesnih += 1
            if p is None:
                op.stvarno_nedostupno += 1
            else:
                stvarno = _procena_usd(t.model, int(p or 0), int(c or 0))
                op.tokena_ulaz += int(p or 0)
                op.tokena_izlaz += int(c or 0)
                op.usd_stvarno += stvarno
                # projekat: procena poslednjeg pokušaja zamenjuje se stvarnim troškom
                _dodaj_projektu(stvarno - t.usd_procena)
        return
    if isinstance(exc, AIBudzetOdbijen) and t.pokusaja == 0:
        return
    try:
        import openai
        definitivno = isinstance(exc, openai.APIStatusError)
    except Exception:
        definitivno = False
    with op._lock:
        if definitivno:
            op.definitivnih_gresaka += 1
        elif t.pokusaja > 0:
            op.nepoznatih += 1


def _zabelezi_odbijanje(exc: AIBudzetOdbijen) -> None:
    """Pamti odbijanje u držaču zahteva. Mnoge rute hvataju `except Exception` i od
    odbijanja prave generičku 500; `api.py` 5xx granica ovim vraća stvarni razlog
    (402/429/503) umesto „greška servera". Trošak je zaštićen u oba slučaja."""
    d = _drzac.get()
    if d is not None:
        d["odbijanje"] = exc


def zabelezeno_odbijanje() -> Optional[AIBudzetOdbijen]:
    d = _drzac.get()
    return d.get("odbijanje") if d else None


def _osiguraj_brojac() -> None:
    """Brojač pokušaja (`_build_request` hook) MORA stajati na SDK klasama dok brana radi.

    Izmereno u CI-ju (nasumičan redosled testova): `_uninstall_prompt_guard()` skida
    hook, a wrapper koji je pozivalac sačuvao vrati se na klasu bez njega — chat
    wrapper i dalje radi, ali SDK retry-ji i neobavijeni resursi prolaze nebrojani.
    Zato se hook proverava pri svakom pozivu i vraća; ako ni to ne uspe — odbija se."""
    try:
        from openai._base_client import AsyncAPIClient, SyncAPIClient
        if (getattr(SyncAPIClient._build_request, "_vindex_guarded", False)
                and getattr(AsyncAPIClient._build_request, "_vindex_guarded", False)):
            return
        from shared.ai_client import _instaliraj_brojac_pokusaja
        _instaliraj_brojac_pokusaja()
        if not (getattr(SyncAPIClient._build_request, "_vindex_guarded", False)
                and getattr(AsyncAPIClient._build_request, "_vindex_guarded", False)):
            raise RuntimeError("hook nije postavljen")
        logger.warning("[AI_BUDZET] brojač pokušaja je nedostajao na SDK klasama — ponovo postavljen")
    except Exception as exc:
        raise AIBudzetOdbijen("BROJAC_NEDOSTUPAN",
                              "AI budžet ne može da prati pozive. Odbijeno pre slanja.", 503) from exc


def pre_poziva(vrsta: str, kwargs: dict):
    """Sinhrona brana pre JEDNOG logičkog poziva provajdera: granice → operacija →
    projektni limit → rezervacija. Diže `AIBudzetOdbijen` pre slanja ijednog tokena.
    Vraća stanje koje se OBAVEZNO predaje `posle_poziva` (i pri grešci)."""
    if rezim() == "off":
        return None
    try:
        _osiguraj_brojac()
        t = _pripremi(vrsta, kwargs)
        _osiguraj_rezervaciju(t.op)
    except AIBudzetOdbijen as exc:
        _zabelezi_odbijanje(exc)
        raise
    return t, _tekuci_tiket.set(t)


async def apre_poziva(vrsta: str, kwargs: dict):
    """Asinhrona varijanta — rezervacija ide u nit (UsageService koristi sinhroni klijent baze)."""
    if rezim() == "off":
        return None
    try:
        _osiguraj_brojac()
        t = _pripremi(vrsta, kwargs)
        op = t.op
        if not (op.sistemska or op.founder or op.rezervisana):
            await asyncio.to_thread(_osiguraj_rezervaciju, op)
    except AIBudzetOdbijen as exc:
        _zabelezi_odbijanje(exc)
        raise
    return t, _tekuci_tiket.set(t)


def posle_poziva(stanje, response: Any = None, exc: Optional[BaseException] = None) -> None:
    if stanje is None:
        return
    t, tok = stanje
    try:
        _zavrsi(t, response, exc)
    finally:
        _tekuci_tiket.reset(tok)


# ── Namirenje na kraju operacije ──────────────────────────────────────────────

def zatvori(op: Operacija) -> None:
    """Kraj operacije (kraj HTTP zahteva / pozadinskog posla).

    Rezervacija koju ruta nije namirila kroz `consume()`:
      • nepoznat ishod nekog poziva (timeout/prekid) → ZADRŽAVA se i beleži za ručno
        usklađivanje (nikad tiho vraćanje, v. invarijanta 8);
      • inače se vraća — ruta je odlučila da ovaj rad ne naplati (ili nije uspela), što je
        isto ponašanje kao pre brane. Dnevni brojač se NE vraća: upotreba se desila.
    """
    with op._lock:
        if op.zatvorena:
            return
        op.zatvorena = True
        hold, namirena = op.hold, op.namirena
    if op.rezervisana and hold > 0 and op.user_id:
        # Ostatak rezervacije: ili ruta nije naplatila ništa, ili je naplatila manje od
        # rezervisane gornje granice (delimičan uspeh). Nepoznat ishod BEZ ikakvog namirenja
        # zadržava osnovnu cenu (krediti × 1), kao pre rezervacije pune cene; ostatak se vraća.
        zadrzano = min(hold, op.osnovna_cena) if (not namirena and op.nepoznatih > 0) else 0
        if zadrzano:
            logger.error(
                "[AI_BUDZET_RECONCILE] uid=%.8s feature=%s: %d kredita ZADRŽANO — %d poziva sa nepoznatim "
                "ishodom (timeout/prekid); provajder je možda naplatio. Ručno usklađivanje.",
                op.user_id, op.feature, zadrzano, op.nepoznatih)
        vratiti = hold - zadrzano
        if vratiti > 0:
            from shared.deps import _refund_n_credits
            novo = _refund_n_credits(op.user_id, vratiti)
            if novo < 0:
                logger.error("[AI_BUDZET_RECONCILE] uid=%.8s feature=%s: povraćaj %d kredita NIJE uspeo — "
                             "korisnik je zadužen bez namirenja; ručno usklađivanje.", op.user_id, op.feature, vratiti)
            else:
                logger.info("[AI_BUDZET] %s rezervacije vraćen uid=%.8s feature=%s krediti=%d",
                            "nenamiren deo" if namirena else "nenamirena rezervacija", op.user_id, op.feature, vratiti)
        with op._lock:
            op.hold = 0
            if not namirena and not zadrzano:
                op.rezervisana = False
    if op.pokusaja:
        logger.info(
            "[AI_BUDZET] operacija zatvorena izvor=%s feature=%s pokusaja=%d uspesnih=%d nepoznatih=%d "
            "procena_usd=%.5f stvarno_usd=%s tokena=%d/%d",
            op.izvor, op.feature, op.pokusaja, op.uspesnih, op.nepoznatih, op.usd_procena,
            ("NEDOSTUPNO" if op.stvarno_nedostupno and not op.tokena_ulaz else f"{op.usd_stvarno:.5f}"),
            op.tokena_ulaz, op.tokena_izlaz)


class AIBudzetMiddleware:
    """Čist ASGI middleware: svež držač operacije po zahtevu + namirenje na kraju.

    Mora biti spoljašnji u odnosu na rute; `BaseHTTPMiddleware` slojevi ispod njega
    rade u kopiji konteksta, ali dele isti dict, pa je vezivanje vidljivo ovde.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        tok = otvori_zahtev(http=True)
        d = _drzac.get()
        pocet = {"v": False}

        async def _send(poruka):
            if poruka.get("type") == "http.response.start":
                pocet["v"] = True
            await send(poruka)

        try:
            try:
                await self.app(scope, receive, _send)
            except Exception:
                # Neuhvaćen izuzetak koji je nastao iz progutanog odbijanja budžeta (ruta
                # ga je umotala u drugi tip): odgovori stvarnim razlogom, ako odgovor
                # još nije počeo. Inače ga prepusti globalnom rukovaocu.
                odb = d.get("odbijanje") if d else None
                if odb is None or pocet["v"] or scope.get("type") != "http":
                    raise
                telo = json.dumps({"detail": odb.detalj}, ensure_ascii=False).encode("utf-8")
                await send({"type": "http.response.start", "status": odb.status,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"content-length", str(len(telo)).encode())]})
                await send({"type": "http.response.body", "body": telo})
        finally:
            op = d.get("op") if d else None
            if op is not None:
                try:
                    await asyncio.to_thread(zatvori, op)
                except Exception as exc:  # namirenje nikad ne obara odgovor
                    logger.error("[AI_BUDZET_RECONCILE] namirenje operacije nije uspelo: %s", exc)
            _drzac.reset(tok)


# ── Realtime glas (sirov WebSocket, mimo SDK-a) ───────────────────────────────
# OpenAI Realtime se plaća po minutu zvuka i NE prolazi kroz SDK patch iznad. Zato:
# rezervacija PRE otvaranja veze (UsageService, funkcija `voice`), procena za ceo
# dozvoljeni prozor ulazi u projektni limit, a sesija se tvrdo prekida posle
# VINDEX_AI_REALTIME_MAX_SEKUNDI.
_REALTIME_USD_PO_MINUTU = 0.30   # konzervativna procena (ulazni + izlazni zvuk), ne cena iz ugovora


def realtime_max_sekundi() -> int:
    return int(_env_float("VINDEX_AI_REALTIME_MAX_SEKUNDI", 600))


async def rezervisi_realtime(user: dict) -> None:
    if rezim() == "off":
        return
    usd = realtime_max_sekundi() / 60 * _REALTIME_USD_PO_MINUTU
    if projektna_potrosnja() + usd > projektni_limit_usd():
        raise AIBudzetOdbijen("PROJEKTNI_LIMIT", "AI servis je privremeno dostigao mesečni limit.", 503)
    from shared.deps import _is_founder
    email = (user or {}).get("email") or ""
    if not _is_founder(email):
        from fastapi import HTTPException

        from shared.usage import UsageService
        try:
            await UsageService.consume(user["user_id"], email, "voice")
        except HTTPException as exc:
            det = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            raise AIBudzetOdbijen(det.get("code") or "BUDZET_ODBIJEN",
                                  det.get("message") or "AI budžet nije dostupan.", exc.status_code) from exc
        except Exception as exc:
            raise AIBudzetOdbijen("BUDZET_NEDOSTUPAN", "Budžet trenutno ne može da se potvrdi.", 503) from exc
    _dodaj_projektu(usd)
