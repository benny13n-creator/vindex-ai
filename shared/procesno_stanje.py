# -*- coding: utf-8 -*-
"""
Vindex AI — shared/procesno_stanje.py

MIR001 C3b STRUCTURAL — procesno stanje UTEMELJENO NA IZVORU, pre nacrta za sud.

Zašto: stvaran model je imao odluku suda doslovno (dvaput) i ipak pisao da je naložena dopuna nepotrebna, kasniji
podnesak stranke čitao kao odluku, rok prikazivao kao da teče i jednom izmislio uplatu (`MIR001_C3B_LEDGER.md`,
TASK-03). Tekst uputstva to nije promenio. Zato procesno stanje ne utvrđuje model: utvrđuje ga ovaj modul, iz teksta
dokumenata, i za svaku stavku kaže ŠTA je provereno, a šta NIJE.

DVE RAZLIČITE TVRDNJE PO STAVCI (GATE-01: ne smeju se mešati):
1. `klasa` = VERIFIED_SOURCE_FACT znači SAMO: identifikovan dokument ovog predmeta i korisnika (id, oznaka, sha256
   teksta) sadrži TAČNO ovaj izvod na ovom mestu (`potvrdi_izvod`). Ništa više.
2. `tumacenje` (ko je akter, da li je to odluka suda i kakva) je OBRAZAC nad tekstom — heuristika, nikad
   VERIFIED: `klasa_tumacenja` je UNKNOWN (kandidat) ili CONTESTED. Vrsta dokumenta ima sopstvenu klasu:
   HUMAN_CONFIRMED samo kad je advokat potvrdio vrstu i to stoji u `audit_immutable` (pozivalac daje
   `potvrde_vrste`); po naslovu je samo kandidat. `ai_tags` dokumenta se NE koristi: može ga upisati i izlaz modela
   (`routers/evidence.py` klasifikacija).

Modul nikad ne tvrdi pravno dejstvo kasnijeg akta ili podneska, važenje naloga, tok ili istek roka, izvršenje,
uplatu, ni autentičnost dokumenta. Odsustvo dokaza nije dokaz: „nije utvrđeno iz pročitanih dokumenata“.
Promašaj obrasca mora biti GLASAN: nerazvrstana rečenica suda, dokument nepoznate vrste, neobični znaci i narativ
ranije odluke idu u `nepoznato` sa izvodom.

Klase dokaza (konceptualne, za ovaj ugovor; NIJE enum baze): VERIFIED_SOURCE_FACT, HUMAN_CONFIRMED, CONTESTED, UNKNOWN.
Bez upisa, bez modela, bez mreže; nema novog trajnog entiteta. Ulaz su SAMO redovi `predmet_dokumenti` i potvrde
vrste iz audit traga — izlaz modela nema ulaz u ovaj ugovor.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable, Optional

VERIFIED = "VERIFIED_SOURCE_FACT"
HUMAN = "HUMAN_CONFIRMED"
CONTESTED = "CONTESTED"
UNKNOWN = "UNKNOWN"

_NEVIDLJIVI = re.compile("[​-‏⁠﻿­]")
_NELATINICA = re.compile("[Ѐ-ӿ]")
_LAT = str.maketrans({"č": "c", "ć": "c", "ž": "z", "š": "s", "đ": "dj", "Č": "C", "Ć": "C", "Ž": "Z", "Š": "S", "Đ": "Dj"})
_LAT_ISTA_DUZINA = str.maketrans({"č": "c", "ć": "c", "ž": "z", "š": "s", "đ": "d", "Č": "C", "Ć": "C", "Ž": "Z",
                                  "Š": "S", "Đ": "D"})


def _n(t: str) -> str:
    """Za poređenje: bez nevidljivih znakova, latinica bez dijakritika, mala slova, jedan razmak."""
    return " ".join(_NEVIDLJIVI.sub("", t or "").translate(_LAT).lower().split())


# ── Vrsta dokumenta: naslov = red koji POČINJE reči vrste (ne „Veza: … rešenje“, ne „Predmet: … zapisnik“) ────────
_GLAVA = 400
_NASLOV = (("SUD", re.compile(r"(?:zapisnik|resenje|presuda|zakljucak)\b")),
           ("STRANKA", re.compile(r"(?:podnesak|odgovor na tuzbu|tuzba|izjasnjenje|zalba|prigovor|predlog)\b")),
           ("VESTAK", re.compile(r"(?:nalaz|misljenje vestaka)\b")))
_VRSTA_SUD = {"court_decision", "judgment"}
_VRSTA_STRANKA = {"lawsuit", "response", "appeal"}


def _stranka_iz(t: str) -> str:
    t = _n(t)
    tuzeni, tuzilac = re.search(r"\btuzen\w*", t), re.search(r"\btuzil\w*|\btuzioc\w*", t)
    if tuzeni and not tuzilac:
        return "TUZENI"
    if tuzilac and not tuzeni:
        return "TUZILAC"
    return "STRANKA"


def vrsta_dokumenta(tekst: str, potvrdjena: Optional[str] = None) -> dict:
    """{"akter": SUD|TUZILAC|TUZENI|STRANKA|VESTAK|NEPOZNAT, "osnov": ADVOKAT|NASLOV|NEPOZNATO, "klasa",
    "naslov", "kraj_naslova"[, "sukob"]}.
    Naslov: red u prvih `_GLAVA` znakova koji (posle rednog broja/crtica) POČINJE reči vrste, kratak je (≤ 100) i ne
    završava tačkom. Bez takvog reda → NEPOZNAT. Po naslovu je vrsta samo KANDIDAT (klasa UNKNOWN); HUMAN_CONFIRMED
    samo uz `potvrdjena` — vrstu iz audit zapisa ljudske odluke (QA-02), koju daje pozivalac."""
    naslovi, poz = [], 0                                    # (vrsta, red, kraj reda) svakog reda glave koji liči na naslov
    for red in (tekst or "")[:_GLAVA].splitlines(keepends=True):
        s = red.strip()
        poz += len(red)
        if not s or len(s) > 100 or re.search(r"[.!?]$", s):
            continue
        r = re.sub(r"^[\W\d_]+", "", _n(s))
        vr = next((x for x, rx in _NASLOV if rx.match(r)), None)
        if vr:
            naslovi.append((vr, s, poz))
    v, naslov, kraj = naslovi[0] if naslovi else (None, "", 0)
    po_naslovu = ({"akter": _stranka_iz(naslov) if v == "STRANKA" else v, "osnov": "NASLOV", "klasa": UNKNOWN,
                   "naslov": naslov, "kraj_naslova": kraj} if v else
                  {"akter": "NEPOZNAT", "osnov": "NEPOZNATO", "klasa": UNKNOWN, "naslov": "", "kraj_naslova": 0})
    drugi = [s for vr, s, _ in naslovi[1:] if vr != v]
    if drugi:                                               # „Zaključak suda …“ iznad „PODNESAK TUŽENOG“: ne bira se
        po_naslovu.update(klasa=CONTESTED, sukob=f"dva naslova različite vrste: „{naslov[:60]}“ / „{drugi[0][:60]}“")
    if potvrdjena not in _VRSTA_SUD | _VRSTA_STRANKA:
        return po_naslovu
    sud = potvrdjena in _VRSTA_SUD
    out = {"akter": "SUD" if sud else (_stranka_iz(naslov) if v == "STRANKA" else "STRANKA"), "osnov": "ADVOKAT",
           "klasa": HUMAN, "naslov": naslov, "kraj_naslova": kraj}
    if any((vr == "SUD") != sud for vr, _, _ in naslovi):
        out["sukob"] = f"naslov: {po_naslovu['akter']}, advokat: {potvrdjena}"         # sukob se ne prećutkuje
        out["klasa"] = CONTESTED
    return out


# ── Jedinice teksta: rečenica može biti prelomljena (OCR); red velikim slovima je zasebna jedinica ────────────────
def _jedinice(tekst: str, od: int = 0) -> list:
    """[(početak, kraj)] u ORIGINALNOM tekstu, od položaja `od` (posle naslova — naslov se ne spaja sa telom):
    uzastopni redovi se spajaju dok red ne završi sa [.!?:]."""
    redovi, poz = [], 0
    for red in (tekst or "").splitlines(keepends=True):
        s = red.rstrip("\r\n")
        if poz >= od:
            redovi.append((poz + len(s) - len(s.lstrip()), poz + len(s.rstrip()), s.strip()) if s.strip() else None)
        poz += len(red)
    out, poc, kraj = [], None, None
    for r in redovi + [None]:
        if r is None or r[2].isupper():
            if poc is not None:
                out.append((poc, kraj))
            poc = None
            if r is not None:
                out.append((r[0], r[1]))
            continue
        poc = r[0] if poc is None else poc
        kraj = r[1]
        if re.search(r"[.!?:]$", r[2]):
            out.append((poc, kraj))
            poc = None
    return [deo for a, b in out for deo in _recenice_u(tekst, a, b)]


_RE_GRANICA_RECENICE = re.compile(r"[.!?]+\s+(?=[A-ZČĆŽŠĐ])")
_SKRACENICE = {"br", "cl", "čl", "str", "st", "tac", "tač", "npr", "tzv", "ul", "itd", "dr", "god", "red", "din",
               "dipl", "ing", "mr", "prof", "gosp", "g", "sl", "tj", "odn", "pom", "adv"}


def _recenice_u(tekst: str, a: int, b: int) -> list:
    """Jedinicu deli na rečenice („… uplati predujam. Konstatuje se …“ su DVE radnje). Ne seče posle broja ili datuma
    („15.07.2026. Sud …“ ostaje sa datumom samo kad sledi malo slovo) ni posle skraćenice („br. 5“)."""
    out, od = [], a
    for m in _RE_GRANICA_RECENICE.finditer(tekst, a, b):
        pre = re.search(r"(\S+)$", tekst[od:m.start()])
        rec = (pre.group(1) if pre else "").lstrip("(").lower()
        if rec[-1:].isdigit() or rec in _SKRACENICE or (len(rec) == 1 and rec.isalpha()):     # broj, skraćenica, inicijal
            continue
        kraj = m.start() + len(m.group().rstrip())
        out.append((od, kraj))
        od = m.end()
    if od < b:
        out.append((od, b))
    return out


# ── Rečenica sudskog dokumenta: ko govori i šta ───────────────────────────────────────────────────────────────────
_SUD = r"\bsud\s+(?:je\s+)?(?:vec\s+)?"
# Stranka kao SUBJEKAT: samo nominativ („Tuženi …“, „Punomoćnik …“), nikad dativ („Tuženom se nalaže“ je glas suda),
# i ne pasiv sa „se“ („Stranke se pozivaju“). GATE-01 2. prolaz N1: dativ i širok preneseni govor gutali su nalog.
_RE_SUBJEKAT_STRANKA = re.compile(r"^\W*(?:punomocnik|punomocnica|punomocnici|tuzilac|tuzilja|tuzioci|tuzeni|tuzena|"
                                  r"zastupnik|zastupnica|stranka|stranke|svedok|svedokinja|vestak|advokat|predlagac|"
                                  r"protivnik)\b(?!\s+se\b)")
# Preneseni govor: glagol govora stranke i POSLE njega „da (je) sud …“ — sud je tada u tuđem iskazu. „Nakon što je
# tuženi predložio …, sud prihvata“ i „Sud nalaže …, kako tužilac predlaže“ ostaju glas suda.
_RE_PRENESEN_GOVOR = re.compile(r"\b(?:predlaze|predlozio|predlozila|navodi|naveo|navela|tvrdi|istice|istakao|istakla|"
                                r"smatra|izjavljuje|izjavio|izjavila|trazi|trazio|trazila|osporava|ponavlja|prigovara)\b"
                                r"[^.;]*?\bda\s+(?:je\s+)?(?:vec\s+)?sud\b")
_RE_NEGACIJA_SUDA = re.compile(_SUD + r"(?:ni(?:je|su)\b|ne\s)|\bne\s+(?:prihvata|usvaja|nalaze|odbija|odbacuje)\s+se\b"
                               r"|\bse\s+ne\s+(?:prihvata|usvaja|nalaze|odbija|odbacuje)\b"
                               r"|\bda\s+ne\s+(?:prihvat|usvoj|naloz|odbi|odbac)\w*")
_RE_UKIDA = re.compile(r"\bukida\s+se\b|" + _SUD + r"ukid\w*|\bstavlja\s+se\s+van\s+snage\b|\bpreinacuje\s+se\b")
_RE_NARATIV = re.compile(r"\b(?:resenjem|zakljuckom|presudom|odlukom)\s+(?:od|broj|br)\b|\bukinut\w*|\bpreinacen\w*"
                         r"|\bvan\s+snage\b|\bna\s+ranijem\s+rocist\w*|\branije\s+donet\w*|\branij\w+\s+(?:resenj|zakljuc|presud)\w*")
_ODLUKE_SUDA = (
    # bezlični oblik u oba poretka: „Nalaže se tuženom …“ i „Tuženom se nalaže …“ (negacija je proverena pre ovoga)
    ("SUD_ODBIJA", re.compile(_SUD + r"(?:odbi|odbac)\w*|\b(?:odbija|odbacuje)\s+se\b|\bse\s+(?:odbija|odbacuje)\b"
                              r"|,\s*a\s+odbija\b")),
    ("SUD_PRIHVATA", re.compile(_SUD + r"(?:prihvat|usvaj|usvoj)\w*|\b(?:prihvata|usvaja)\s+se\b"
                                r"|\bse\s+(?:prihvata|usvaja)\b")),
    ("SUD_NALAZE", re.compile(_SUD + r"nal[ao][zg]\w*|\bnalaze\s+se\b|\bse\s+nalaze\b"
                              r"|\bse\s+obavezuje\b|\bobavezuje\s+se\b")),               # izreka: „Tuženi se obavezuje“
    ("SUD_ODREDJUJE", re.compile(_SUD + r"(?:odredj|ostavlj|prekid|odlaz|zakazuj)\w*"
                                 r"|\b(?:odredjuje|ostavlja|prekida|odlaze)\s+se\b"
                                 r"|\bse\s+(?:odredjuje|ostavlja|prekida|odlaze)\b")),
)
_RE_KONSTATUJE = re.compile(r"\bkonstatuje\s+se\b|\bsud\s+(?:je\s+)?konstat\w*")
_RE_ZAKAZANO = re.compile(r"\bzakazan\w*\s+(?:je\s+)?za\b")
_RE_SUDSKI_RECNIK = re.compile(r"\bsud\w*|\bnal[ao][zg]\w*|\bprihvat\w*|\bodbi\w*|\busvoj\w*|\busvaj\w*|\bodredj\w*"
                               r"|\bukid\w*|\bpredujam\w*|\bpredujm\w*|\buplat\w*|\broku?\b|\bdopun\w*")

_OBRASCI_STRANKE = (
    ("STRANKA_ODUSTAJE", re.compile(r"\b(?:odustaj|odusta|povlac|povuk)\w*")),
    ("STRANKA_NAVODI_IZVRSENJE", re.compile(r"\b(?:uplat|uplac|platio|platil|dostavlj|dostavio|dostavil|postupio|postupil)\w*")),
    ("STRANKA_NAVODI_O_SUDU", re.compile(r"\bsud\w*\s|\brocist\w*|\braspravlj\w*")),
    ("STRANKA_PREDLAZE", re.compile(r"\b(?:predlaz|ponavlja\s+predlog|trazi)\w*")),
    ("STRANKA_NAVODI", re.compile(r"\b(?:navodi|tvrdi|istice|osporava)\b")),
)
_RE_ROK = re.compile(r"\bu\s+roku\s+od\s+(\d{1,3})\s+dana(?:\s+(od\s+(?:dana\s+)?(?:prijema|dostav\w*|uruc\w*|"
                     r"pravnosnaz\w*|danas|odrzavanja)(?:\s+(?:zapisnika|resenja|presude|rocista|podneska))?))?")
_RE_PREDUJAM = re.compile(r"\b(?:predujam|predujm|uplat)\w*")
_RE_DATUM_ROCISTA = re.compile(r"rocist\w*\s+(?:odrzan\w*\s+)?(?:dana\s+)?(\d{1,2})\.(\d{1,2})\.(\d{4})")

# Datum dokumenta: SAMO oznaka na početku reda, i to oznaka sopstvene vrste („Datum rešenja:“ u podnesku nije datum
# podneska; „ročište održano dana“ u podnesku nije datum podneska).
# Red mora biti SAMO oznaka i datum (bez preloma reda u sredini): citat drugog dokumenta usred teksta nije oznaka.
_D = r"[ \t]*(\d{1,2})\.(\d{1,2})\.(\d{4})\.?(?:[ \t]+godine\.?)?[ \t\r]*$"
_DATUM_PO_VRSTI = {
    "SUD": re.compile(r"^[ \t]*(?:datum(?:[ \t]+(?:zapisnika|resenja|presude|odluke))?[ \t]*:|rociste[ \t]+(?:je[ \t]+)?"
                      r"odrzano[ \t]+dana|doneto[ \t]+dana|u[ \t]+[a-z]+,?[ \t]+dana)" + _D, re.M),
    "STRANKA": re.compile(r"^[ \t]*(?:datum(?:[ \t]+(?:podneska|odgovora|tuzbe|izjasnjenja|zalbe|prigovora|predloga))?"
                          r"[ \t]*:|u[ \t]+[a-z]+,?[ \t]+dana)" + _D, re.M),
    "VESTAK": re.compile(r"^[ \t]*(?:datum(?:[ \t]+nalaza)?[ \t]*:|u[ \t]+[a-z]+,?[ \t]+dana)" + _D, re.M),
}

# Predmet radnje: osnove reči ≥ 6 slova bez procesnih glagola i uloga (isti princip kao `_osnove` u multi_agent)
_STOP = {"prihvata", "prihvatio", "prihvatila", "usvaja", "usvojio", "nalaze", "nalozio", "odbija", "odbio",
         "odredjuje", "odredio", "zakazano", "zakazan", "tuzenom", "tuziocu", "tuzeni", "tuzilac", "tuzioca", "tuzenog",
         "dostavi", "dostavu", "predlog", "predloga", "predlogu", "predlaze", "sledece", "godine", "postupku",
         "ostavlja", "prekida", "odlaze", "odustaje", "povlaci", "navodi", "ponavlja", "njegovom", "rocistu",
         "rocista", "odrzanom", "raspravljano", "dinara", "iznosu", "konstatuje", "resenje", "resenja", "zakljucak",
         "zakljucka", "doneto"}


def _osnove(t: str) -> set:
    return {w[:5] for w in re.findall(r"[a-z]{6,}", _n(t)) if w not in _STOP}


def _datum(m) -> Optional[str]:
    d, mes, g = (int(x) for x in m.groups()[-3:])
    return f"{g:04d}-{mes:02d}-{d:02d}" if 1 <= d <= 31 and 1 <= mes <= 12 else None


def datum_dokumenta(tekst: str, akter: str) -> dict:
    """Datum dokumenta iz oznake na početku reda, sopstvene vrste (`_DATUM_PO_VRSTI`). Jedan različit kandidat →
    VERIFIED (izvod); više različitih → UNKNOWN (ne bira se); nijedan → UNKNOWN. Datum dokumenta NIJE datum
    događaja koji dokument pominje."""
    rx = _DATUM_PO_VRSTI.get("STRANKA" if akter in ("TUZILAC", "TUZENI", "STRANKA") else akter)
    kandidati: dict = {}
    norm = (tekst or "").translate(_LAT_ISTA_DUZINA).lower()          # ista dužina → isti položaji kao u originalu
    for m in (rx.finditer(norm) if rx else ()):
        d = _datum(m)
        if d:
            kandidati.setdefault(d, (m.start(), m.end()))
    if len(kandidati) != 1:
        return {"datum": None, "klasa": UNKNOWN, "razlog": "više različitih datuma" if kandidati else "datum nije označen"}
    d, (a, b) = next(iter(kandidati.items()))
    return {"datum": d, "klasa": VERIFIED, "izvod": tekst[a:b].strip()}


def sha256_teksta(tekst: str) -> str:
    return hashlib.sha256((tekst or "").encode("utf-8")).hexdigest()


def potvrdi_izvod(tekst: str, sha: str, pocetak: int, kraj: int, izvod: str) -> bool:
    """Izvod važi samo ako je tekst dokumenta ISTI (sha256) i na tom mestu stoji TAČNO taj izvod. Navod modela ili
    zastareo izvod (tekst dokumenta promenjen posle čitanja) ne prolazi."""
    return (type(pocetak) is int and type(kraj) is int and 0 <= pocetak < kraj <= len(tekst or "")
            and sha256_teksta(tekst) == sha and tekst[pocetak:kraj] == izvod)


def _recenica_suda(nj: str) -> tuple:
    """(vrsta, kandidati) za rečenicu SUDSKOG dokumenta, ili (None, []) kad nije radnja suda."""
    if _RE_SUBJEKAT_STRANKA.search(nj) or _RE_PRENESEN_GOVOR.search(nj):
        return "STRANKA_U_SUDSKOM_DOKUMENTU", []          # zapisnik beleži stranku — nije glas suda
    if _RE_NEGACIJA_SUDA.search(nj):
        return "SUD_NERAZVRSTANO", []
    if _RE_UKIDA.search(nj):
        return "SUD_UKIDA", []
    if _RE_NARATIV.search(nj):
        return "SUD_NARATIV", []                          # pominje raniju odluku: važenje se ne utvrđuje
    kandidati = [v for v, rx in _ODLUKE_SUDA if rx.search(nj)]
    if len(kandidati) > 1:
        return "SUD_VISESTRUKO", kandidati
    if kandidati:
        return kandidati[0], kandidati
    if _RE_KONSTATUJE.search(nj):
        return "SUD_KONSTATUJE", []
    if _RE_ZAKAZANO.search(nj):
        return "SUD_ZAKAZANO", []
    return None, []


_NALOZI = ("SUD_PRIHVATA", "SUD_NALAZE", "SUD_ODBIJA", "SUD_ODREDJUJE", "SUD_VISESTRUKO")


def utvrdi(dokumenti: Iterable[dict], *, predmet_id: str, user_id: str, neprocitani: Iterable[str] = (),
           potvrde_vrste: Optional[dict] = None) -> dict:
    """Procesno stanje iz izvornih dokumenata JEDNOG predmeta jednog korisnika.

    `dokumenti`: redovi `predmet_dokumenti` {id, predmet_id, user_id, oznaka, tekst (CEO `tekst_sadrzaj`)}; red drugog
    predmeta ili korisnika se odbacuje (odbrana u dubini; vlasništvo proverava pozivalac). `neprocitani`: oznake
    dokumenata čiji tekst NIJE (potpuno) pročitan → NEPOTPUNO. `potvrde_vrste`: {dokument_id: vrsta} iz audit zapisa
    ljudske odluke (`dokument_vrsta_ispravljena`) — jedini put do HUMAN_CONFIRMED.
    Vraća {"dogadjaji": [...], "nepoznato": [...], "potpunost", "odbaceni"}."""
    if not predmet_id or not user_id:
        raise ValueError("predmet_id i user_id su obavezni")
    potvrde = potvrde_vrste or {}
    dogadjaji, nepoznato, odbaceni, datumi_sudskih, sudski, spisak = [], [], [], set(), [], []

    def _nep(t: str) -> None:
        if t not in nepoznato:
            nepoznato.append(t)

    for d in dokumenti:
        if str(d.get("predmet_id")) != str(predmet_id) or str(d.get("user_id")) != str(user_id):
            odbaceni.append(d.get("oznaka") or "DOK-??")
            continue
        tekst, oz = d.get("tekst") or "", d["oznaka"]
        vrsta = vrsta_dokumenta(tekst, potvrde.get(d.get("id")))
        dat = datum_dokumenta(tekst, vrsta["akter"])
        sha = sha256_teksta(tekst)
        spisak.append({"oznaka": oz, "akter": vrsta["akter"]})       # koji dokumenti postoje i ko ih je (po naslovu) pisao
        if vrsta["akter"] == "NEPOZNAT":
            _nep(f"{oz}: vrsta dokumenta nije utvrđena (naslov nije prepoznat) — može sadržati odluku suda; "
                 "pročitati dokument ili potvrditi vrstu")
        if vrsta.get("sukob"):
            _nep(f"{oz}: vrsta dokumenta sporna ({vrsta['sukob']})")
        if vrsta["akter"] == "SUD":
            sudski.append(oz)
            if dat["datum"]:
                datumi_sudskih.add(dat["datum"])
            # GATE-01 3. prolaz R1: datum ročišta iz sudskog dokumenta i kad u redu sledi tekst („… godine, sa početkom
            # u 10 časova“) — inače bi se tvrdilo da zapisnika nema, a pročitan je
            datumi_sudskih.update(d for d in (_datum(m) for m in _RE_DATUM_ROCISTA.finditer(_n(tekst))) if d)
        for a, b in _jedinice(tekst, vrsta["kraj_naslova"]):
            if b <= vrsta["kraj_naslova"]:
                continue                                   # zaglavlje i naslov nisu radnja
            izvod = tekst[a:b]
            nj = _n(izvod)
            kandidati: list = []
            if _NELATINICA.search(izvod) and (vrsta["akter"] in ("SUD", "NEPOZNAT") or _RE_SUDSKI_RECNIK.search(nj)):
                vd = "NERAZVRSTANO_ZNACI"
                _nep(f"{oz}: rečenica sa ćiriličnim ili neobičnim znacima nije razvrstana — „{' '.join(izvod.split())[:120]}“")
            elif vrsta["akter"] == "SUD":
                vd, kandidati = _recenica_suda(nj)
                if vd is None and _RE_SUDSKI_RECNIK.search(nj):
                    _nep(f"{oz}: rečenica sudskog dokumenta nije razvrstana — „{' '.join(izvod.split())[:120]}“")
                elif vd in ("SUD_NERAZVRSTANO", "SUD_NARATIV", "SUD_VISESTRUKO"):
                    _nep(f"{oz}: rečenica suda — {vd.lower().replace('_', ' ')}, značenje i važenje nisu utvrđeni — "
                         f"„{' '.join(izvod.split())[:120]}“")
            elif vrsta["akter"] in ("TUZILAC", "TUZENI", "STRANKA"):
                vd = next((v for v, rx in _OBRASCI_STRANKE if rx.search(nj)), None)
            elif vrsta["akter"] == "NEPOZNAT":
                vd = "NEPOZNAT_AKTER" if _recenica_suda(nj)[0] not in (None, "STRANKA_U_SUDSKOM_DOKUMENTU") else None
            else:
                vd = None
            if not vd:
                continue
            akter = ("STRANKA" if vd == "STRANKA_U_SUDSKOM_DOKUMENTU" else
                     "NEPOZNAT" if vd in ("NEPOZNAT_AKTER", "NERAZVRSTANO_ZNACI") else vrsta["akter"])
            if vd == "STRANKA_U_SUDSKOM_DOKUMENTU":          # šta stranka radi (odustaje, navodi izvršenje …)
                kandidati = [next((v for v, rx in _OBRASCI_STRANKE if rx.search(nj)), "STRANKA_NAVODI")]
                if any(rx.search(nj) for _, rx in _ODLUKE_SUDA) or _RE_NEGACIJA_SUDA.search(nj):
                    # pripisano stranci, a liči na odluku: ako je obrazac pogrešio, ne sme biti tiho
                    _nep(f"{oz}: rečenica pripisana stranci pominje odluku suda — ko odlučuje, nije utvrđeno — "
                         f"„{' '.join(izvod.split())[:120]}“")
            dog = {"id": f"PS-{len(dogadjaji) + 1:02d}", "dokument_id": d.get("id"), "oznaka": oz,
                   "tekst_sha256": sha, "pocetak": a, "kraj": b, "izvod": izvod, "klasa": VERIFIED,
                   "akter": akter, "vrsta": vd, "kandidati": kandidati,
                   "klasa_tumacenja": CONTESTED if vrsta.get("sukob") else UNKNOWN,
                   "vrsta_dokumenta": {"akter": vrsta["akter"], "osnov": vrsta["osnov"], "klasa": vrsta["klasa"],
                                       "naslov": vrsta["naslov"]},
                   "datum_dokumenta": dat["datum"], "kasniji": [], "nepoznato": []}
            if vd in ("SUD_NALAZE", "SUD_VISESTRUKO"):
                rok = _RE_ROK.search(nj)
                if rok:
                    # Tok i istek roka se NE računaju: početak („od prijema zapisnika“) nije u spisu ili zavisi od
                    # pravila o računanju koje ovaj modul ne utvrđuje — samo trajanje iz izvoda.
                    dog["rok"] = {"trajanje_dana": int(rok.group(1)), "pocetak_iz_izvoda": rok.group(2),
                                  "tok_i_istek": UNKNOWN}
                    dog["nepoznato"].append(f"{oz}: da li rok od {rok.group(1)} dana teče ili je istekao — početak "
                                            "roka i pravilo računanja nisu utvrđeni iz spisa")
                if _RE_PREDUJAM.search(nj):
                    dog["uplata"] = UNKNOWN
                    dog["nepoznato"].append(f"{oz}: uplata nije utvrđena iz pročitanih dokumenata")
                dog["izvrsenje"] = UNKNOWN
                dog["nepoznato"].append(f"{oz}: da li je postupljeno po nalogu — nije utvrđeno iz pročitanih dokumenata")
            dogadjaji.append(dog)

    # Veze sa odlukom suda o ISTOM predmetu radnje (≥ 2 zajedničke osnove): stranka, konstatacija suda, drugi akt
    # suda. Dejstvo se NE utvrđuje; sve osim ranijeg podneska stranke čini odluku spornom.
    nalozi = [x for x in dogadjaji if x["akter"] == "SUD" and x["vrsta"] in _NALOZI]
    for o in nalozi:
        osn = _osnove(o["izvod"])
        for s in dogadjaji:
            if s is o or (s["akter"] == "SUD" and s["oznaka"] == o["oznaka"] and s["vrsta"] != "SUD_KONSTATUJE"):
                continue
            if s["akter"] == "NEPOZNAT" or len(_osnove(s["izvod"]) & osn) < 2:
                continue
            od, sd = o["datum_dokumenta"], s["datum_dokumenta"]
            odnos = ("NEPOZNAT_REDOSLED" if not (od and sd) else
                     "KASNIJE" if sd > od else "RANIJE" if sd < od else "ISTOG_DANA")
            if s["oznaka"] == o["oznaka"]:
                odnos = "ISTI_DOKUMENT"
            o["kasniji"].append({"id": s["id"], "oznaka": s["oznaka"], "vrsta": s["vrsta"], "odnos": odnos,
                                 "dejstvo": UNKNOWN})
            vrsta_s = s["kandidati"][0] if s["vrsta"] == "STRANKA_U_SUDSKOM_DOKUMENTU" else s["vrsta"]
            if (s["akter"] == "SUD" or odnos not in ("RANIJE", "ISTI_DOKUMENT")
                    or vrsta_s in ("STRANKA_ODUSTAJE", "STRANKA_NAVODI_IZVRSENJE")):
                o["stanje"] = CONTESTED
                o["nepoznato"].append(f"{o['oznaka']}: da li {s['oznaka']} ({s['vrsta'].lower()}, {odnos.lower()}) "
                                      "menja ovu odluku ili pokazuje postupanje — nije utvrđeno")
    # Akt suda koji ukida, a ne zna se šta: svaka druga odluka suda je sporna (ne pogađa se koja je ukinuta)
    for u in (x for x in dogadjaji if x["vrsta"] == "SUD_UKIDA"):
        for o in nalozi:
            if o["oznaka"] != u["oznaka"] and not any(k["id"] == u["id"] for k in o["kasniji"]):
                o["kasniji"].append({"id": u["id"], "oznaka": u["oznaka"], "vrsta": u["vrsta"],
                                     "odnos": "NEPOZNAT_PREDMET", "dejstvo": UNKNOWN})
                o["stanje"] = CONTESTED
                o["nepoznato"].append(f"{o['oznaka']}: {u['oznaka']} sadrži ukidanje odluke — koje odluke, nije utvrđeno")

    # Odustanak/navod o izvršenju koji tekstom nije vezan ni za jednu odluku (stranka je radnju opisala drugim rečima):
    # veza se ne pogađa, ali se ne prećutkuje.
    vezani = {k["id"] for o in nalozi for k in o["kasniji"]}
    for s in dogadjaji:
        vrsta_s = s["kandidati"][0] if s["vrsta"] == "STRANKA_U_SUDSKOM_DOKUMENTU" else s["vrsta"]
        if sudski and s["id"] not in vezani and vrsta_s in ("STRANKA_ODUSTAJE", "STRANKA_NAVODI_IZVRSENJE"):
            _nep(f"{s['oznaka']}: {vrsta_s.lower()} nije tekstom vezan ni za jednu odluku suda — da li se odnosi na "
                 f"neku od njih, nije utvrđeno — „{' '.join(s['izvod'].split())[:120]}“")

    # Navod stranke o ročištu za koje među pročitanim dokumentima nije PREPOZNAT sudski dokument istog datuma → ishod
    # ročišta NEPOZNAT. Ne tvrdi se da zapisnika nema — samo da ga sistem nije prepoznao.
    for s in (x for x in dogadjaji if x["vrsta"] == "STRANKA_NAVODI_O_SUDU"):
        for m in _RE_DATUM_ROCISTA.finditer(_n(s["izvod"])):
            dr = _datum(m)
            if dr and dr not in datumi_sudskih:
                s["nepoznato"].append(f"{s['oznaka']}: zapisnik sa ročišta od {m.group(1)}.{m.group(2)}.{m.group(3)} "
                                      "nije prepoznat među pročitanim dokumentima — ishod ročišta NEPOZNAT")
    nepr = list(neprocitani)
    if nepr:
        _nep("dokumenti čiji tekst nije (potpuno) pročitan mogu sadržati odluke suda: " + ", ".join(nepr))
    if not sudski:
        _nep("među pročitanim dokumentima nema dokumenta prepoznatog kao sudski")
    for oz in sudski:
        if not any(x["oznaka"] == oz and x["akter"] == "SUD" for x in dogadjaji):
            _nep(f"{oz}: sudski dokument u kom sistem nije prepoznao odluku — pročitati dokument")
    for x in dogadjaji:
        for n in x["nepoznato"]:
            _nep(n)
    return {"dogadjaji": dogadjaji, "nepoznato": nepoznato, "potpunost": "NEPOTPUNO" if nepr else "POTPUNO", "dokumenti": spisak,
            "odbaceni": odbaceni}
