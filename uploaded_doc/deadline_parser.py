# -*- coding: utf-8 -*-
"""
P3.1/P3.2 / Phase 4.1 — Deadline/rok ekstrakcija iz pravnih dokumenata.

Funkcija `ekstrahuj_rokove` parsira srpske datume i relativne rokove
iz pravnog teksta i vraća strukturirane dict-ove sa kontekstom i kategorijom.

Phase 4.1 dodaci:
  - `_extract_datum_dokumenta` — auto-detekcija datuma dokumenta (bez datuma prijema/dostave, N03-FD4)
  - `_kalkulisi_rok`           — odbrojavanje SAMO za apsolutni datum; relativni rok se ne racuna (N03-FD3)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

#: N03-FD3 — razlog zasto relativni rok nema konkretan datum: okidac (npr. dostava),
#: pravna kvalifikacija i pravilo racunanja nisu provereni. Ranija konverzija
#: `_parse_trajanje_dana` (mesec = 30 dana, radni dani kao kalendarski) je uklonjena.
RACUN_IZOSTAVLJEN_RELATIVNI = "relativni_rok_okidac_i_pravilo_nisu_provereni"

# ─── Meseci na srpskom ────────────────────────────────────────────────────────
_MESECI_GEN = {
    "januara": "01", "februara": "02", "marta": "03", "aprila": "04",
    "maja": "05", "juna": "06", "jula": "07", "avgusta": "08",
    "septembra": "09", "oktobra": "10", "novembra": "11", "decembra": "12",
}

_MESECI_NOM = {
    "januar": "01", "februar": "02", "mart": "03", "april": "04",
    "maj": "05", "jun": "06", "jul": "07", "avgust": "08",
    "septembar": "09", "oktobar": "10", "novembar": "11", "decembar": "12",
}

# ─── Redni brojevi na srpskom (za "petnaestog maja") ─────────────────────────
_REDNI = {
    "prvog": "01", "drugog": "02", "trećeg": "03", "treća": "03",
    "četvrtog": "04", "petog": "05", "šestog": "06", "sedmog": "07",
    "osmog": "08", "devetog": "09", "desetog": "10", "jedanaestog": "11",
    "dvanaestog": "12", "trinaestog": "13", "četrnaestog": "14",
    "petnaestog": "15", "šesnaestog": "16", "sedamnaestog": "17",
    "osamnaestog": "18", "devetnaestog": "19", "dvadesetog": "20",
    "dvadeset prvog": "21", "dvadeset drugog": "22", "dvadeset trećeg": "23",
    "dvadeset četvrtog": "24", "dvadeset petog": "25", "dvadeset šestog": "26",
    "dvadeset sedmog": "27", "dvadeset osmog": "28", "dvadeset devetog": "29",
    "tridesetog": "30", "trideset prvog": "31",
}

# ─── Kategorije ───────────────────────────────────────────────────────────────
# Ćirilica MORA biti paralelno navedena — srpski pravni dokumenti (presude,
# rešenja) su često isključivo na ćirilici, a bez ovoga _kategorija() nikad
# ne prepoznaje "жалба"/"тужба"/itd., pa sve ćirilične kategorije tiho padaju
# na "ostalo". Otkriveno uživo (Faza 1A): rok za žalbu na ćiriličnoj presudi
# je pogrešno biran kao "ostalo" umesto "zalba", što je uzrokovalo da se
# datum PRESUDE (prvi pomenut) izabere umesto stvarnog roka za žalbu
# (pomenut kasnije, u odeljku pravne pouke) — shared/intake_extract.py
# preferira ne-"ostalo" kategorije baš zbog ovog scenarija.
_KATEGORIJE: list[tuple[str, str]] = [
    (r"zastar|застар",                                              "zastarelost"),
    (r"otkaz|otkazn|отказ|отказн",                                  "otkaz"),
    (r"žalb|zalb|žalba|жалб",                                       "zalba"),
    (r"podnes|tužb|tuzb|tužilac|tuzilac|поднес|тужб|тужилац|тужилаца", "podnesak"),
    (r"uplat|isplat|plat|уплат|исплат|плат",                        "isplata"),
]

_CONTEXT_RADIUS = 100  # chars on each side


def _kategorija(kontekst: str) -> str:
    k = kontekst.lower()
    for pattern, cat in _KATEGORIJE:
        if re.search(pattern, k):
            return cat
    return "ostalo"


def _snippet(tekst: str, pos: int, end: int) -> str:
    start = max(0, pos - _CONTEXT_RADIUS)
    stop  = min(len(tekst), end + _CONTEXT_RADIUS)
    return tekst[start:stop].strip()


# ─── Phase 4.1: Auto-detekcija datuma dokumenta ──────────────────────────────

def _extract_datum_dokumenta(tekst: str) -> Optional[str]:
    """
    Detektuje datum dokumenta iz prvih 500 karaktera teksta.
    Vraća "DD.MM.YYYY" string ili None.

    Traži tipične pravne fraze: "doneta ...", "zaključen dana ...", "datum
    presude: ...", "Dana ...", "Beograd, ..." i sl. Fallback: prvi DD.MM.YYYY u
    prvih 500 chars.

    N03-FD4: datum PRIJEMA / DOSTAVE / URUČENJA nije datum dokumenta. Ranije je
    prvi „dana DD.MM.YYYY" pobedjivao, pa je pečat „Primljeno dana 25.03.2025"
    iznad presude donete 17.03.2025 postajao „datum presude". Sada se izričite
    fraze izdavanja (donet, zaključen, datum presude) traže PRE generičkog
    „dana", a datum kome u istom redu prethodi reč prijema/dostave se nikad ne
    vraća. Kad je jedini datum datum prijema, rezultat je `None` (nepoznato),
    ne pogodak.
    """
    probe = tekst[:500]

    def _datum_prijema(pocetak: int, kraj: int) -> bool:
        """Da li je pecat prijema/dostave/ekspedicije VEZAN BAS ZA OVAJ datum.

        Vezan je kada:
          1. u istom redu, izmedju prethodnog datuma (ili pocetka reda) i ovog datuma,
             stoji rec pecata („Primljeno dana 25.03.2025");
          2. rec pecata stoji ODMAH posle datuma, kao njegov predikat („25.03.2025
             PRIMLJENO") — ne posle zareza, gde opisuje odluku („doneta 17.03.2025,
             dostavljena strankama");
          3. prethodni NEPRAZAN red je kratak natpis pecata BEZ sopstvenog datuma
             („PRIMLJENO" iznad datuma) — BEZ OBZIRA na reci u redu datuma: pecat
             cesto sadrzi „Dana: ..." ili „Mesto, ...", pa fraza izdavanja tu nije dokaz
             da je datum datum dokumenta. Cena: „Dostava:\nBeograd, 17.03.2025" daje
             `None` umesto 17.03 — nepoznato, nikad pogresno.
        Pecat sa sopstvenim datumom ne prenosi se na sledeci red. Kad pravila ne mogu
        da odluce, pozivalac vraca `None` — nepoznat datum je bolji od pogresnog."""
        red_pocetak = probe.rfind("\n", 0, pocetak) + 1
        pre = probe[red_pocetak:pocetak]
        prethodni_datumi = list(_DATUM_RE.finditer(pre))
        if prethodni_datumi:
            pre = pre[prethodni_datumi[-1].end():]
        if _PRIJEM_RE.search(pre):
            return True
        if _PRIJEM_POSLE_RE.match(probe[kraj:kraj + 30]):
            return True
        prethodni = [r.strip() for r in probe[:red_pocetak].split("\n")]
        while prethodni and not prethodni[-1]:
            prethodni.pop()
        if not prethodni:
            return False
        natpis = prethodni[-1]
        return (len(natpis) <= _NATPIS_PECATA_MAX and not _DATUM_RE.search(natpis)
                and bool(_PRIJEM_RE.search(natpis)))

    # Fraze koje prethode datumu dokumenta (redosled je bitan — specifičnije pre generičnih)
    phrase_patterns = [
        # "datum presude/zaključenja/ugovora/dokumenta: DD.MM.YYYY"
        r"\bdatum\s+(?:presude|zaklju[čc][ie]?nja|ugovora|dokumenta)\s*[:\s]+(\d{1,2}\.\d{1,2}\.\d{4})\b",
        # "zaključen/zaključena dana DD.MM.YYYY"
        r"\bzaklju[čc]en[ao]?\s+(?:dana\s+)?(\d{1,2}\.\d{1,2}\.\d{4})\b",
        # "doneta/doneto/donet dana DD.MM.YYYY"
        r"\bdonet[ao]?\s+(?:dana\s+)?(\d{1,2}\.\d{1,2}\.\d{4})\b",
        # ćirilica: "донета/донето/донет (дана) DD.MM.YYYY"
        r"(?<!\w)донет[аои]?\s+(?:дана\s+)?(\d{1,2}\.\d{1,2}\.\d{4})\b",
        # "Dana DD.MM.YYYY" / "dana DD.MM.YYYY" (i ćirilica „дана")
        r"\bdana\s+(\d{1,2}\.\d{1,2}\.\d{4})\b",
        r"(?<!\w)дана\s+(\d{1,2}\.\d{1,2}\.\d{4})\b",
        # "Grad/Mesto, DD.MM.YYYY" — npr. "Beograd, 01.03.2025"
        r"\b[A-ZŠĐŽČĆ][a-zšđžčćA-ZŠĐŽČĆ]{2,20},\s*(\d{1,2}\.\d{1,2}\.\d{4})\b",
    ]

    for pat in phrase_patterns:
        for m in re.finditer(pat, probe, re.IGNORECASE):
            if _datum_prijema(m.start(), m.end(1)):
                continue
            raw = m.group(1)
            parts = raw.split(".")
            if len(parts) == 3 and _valid_date_parts(parts):
                return f"{parts[0].zfill(2)}.{parts[1].zfill(2)}.{parts[2]}"

    # Fallback: prvi DD.MM.YYYY u prvih 500 chars koji nije datum prijema/dostave
    for m in re.finditer(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", probe):
        if _datum_prijema(m.start(), m.end()):
            continue
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if _valid_date_parts([d, mo, y]):
            return f"{d.zfill(2)}.{mo.zfill(2)}.{y}"

    return None


#: N03-FD4 — TAČNI oblici pečata prijema, dostave, uručenja, ekspedicije i otpravka
#: (latinica i ćirilica). Takav datum je činjenica o kretanju pismena, ne datum
#: dokumenta. Kraj reči je obavezan: „Rešenje o prijemu u radni odnos" nije pečat.
#: Početak reči NIJE ograničen — „neuručeno", „nedostavljeno" su takođe beleška o
#: kretanju pismena, pa je isključenje takvog datuma ispravno.
_PECAT = (
    r"primljen[oa]?|zaprimljen[oa]?|prijem|prijema|prijemni|dostavljen[oa]?|dostava|dostave|"
    r"dostavnic[aie]?|uru[čc]en[oa]?|ekspedovan[oa]?|ekspedicij[ae]|otpravljen[oa]?|pristigl[oa]?|"
    r"примљен[оа]?|запримљен[оа]?|пријем|пријема|пријемни|достављен[оа]?|достава|доставе|"
    r"доставниц[аие]?|уручен[оа]?|експедован[оа]?|експедициј[ае]|отправљен[оа]?|пристигл[оа]?"
)
_PRIJEM_RE = re.compile(r"(" + _PECAT + r")(?!\w)", re.IGNORECASE)
#: Pečat kao PREDIKAT datuma: odmah posle datuma, bez zareza („25.03.2025 PRIMLJENO").
_PRIJEM_POSLE_RE = re.compile(r"[\s.]*(" + _PECAT + r")(?!\w)", re.IGNORECASE)
_DATUM_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b")
#: Natpis pečata je kratak red („PRIMLJENO", „Prijemni štambilj"); duži red je tekst,
#: ne pečat, i ne sme da poništi datum ispod sebe.
_NATPIS_PECATA_MAX = 40


def _valid_date_parts(parts: list) -> bool:
    """Osnovna validacija datumskih delova (nije puna validacija)."""
    try:
        d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
        return 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2100
    except (ValueError, IndexError):
        return False


# ─── Phase 4.1: Kalkulacija konkretnog datuma i countdowna ───────────────────

def _kalkulisi_rok(vrednost: str, tip: str, datum_dokumenta: Optional[str]) -> dict:
    """
    Vraća dict sa:
      konkretan_datum: "DD.MM.YYYY" | None
      istekao:         bool
      dana_do_roka:    int | None  (negativno = isteklo pre N dana)
    """
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    if tip == "apsolutni":
        try:
            rok_dt = datetime.strptime(vrednost, "%d.%m.%Y")
            delta  = (rok_dt - today).days
            return {
                "konkretan_datum":     vrednost,
                "konkretan_datum_iso": rok_dt.strftime("%Y-%m-%d"),
                "istekao":             delta < 0,
                "dana_do_roka":        delta,
            }
        except ValueError:
            return {"konkretan_datum": None, "konkretan_datum_iso": None, "istekao": False, "dana_do_roka": None}

    elif tip == "relativni":
        # N03-FD3: relativni rok OSTAJE relativan. Ranije se ovde racunalo
        # `datum dokumenta + N dana` (mesec = 30 dana, godina = 365, radni dani
        # kao kalendarski), a „datum dokumenta" je bio automatski pogodjen. Rok
        # ne tece od datuma dokumenta nego od okidaca (npr. dostave), a pravilo
        # racunanja (pocetni dan, mesec po kalendaru, neradni dani) zavisi od
        # pravne kvalifikacije koju sistem ovde nema. Zato NEMA datuma ni
        # odbrojavanja, ni kad je datum dokumenta uneo korisnik — izraz ostaje
        # kandidat za pregled, a razlog je eksplicitan.
        return {"konkretan_datum": None, "konkretan_datum_iso": None, "istekao": False, "dana_do_roka": None,
                "racun_izostavljen": RACUN_IZOSTAVLJEN_RELATIVNI}

    return {"konkretan_datum": None, "konkretan_datum_iso": None, "istekao": False, "dana_do_roka": None}


# ─── Glavna funkcija ──────────────────────────────────────────────────────────

def ekstrahuj_rokove(tekst: str, datum_dokumenta: Optional[str] = None, dedup_konteksta: bool = True) -> list[dict]:
    """
    Parsira srpske datume i relativne rokove iz pravnog teksta.

    Returns list of dicts:
      {
        "tip":            "apsolutni" | "relativni",
        "vrednost":       "15.11.2025" | "8 dana",
        "kontekst":       "...tekst oko roka...",
        "kategorija":     "zastarelost" | "otkaz" | "zalba" | "podnesak" | "isplata" | "ostalo",
        "konkretan_datum": "DD.MM.YYYY" | None,
        "istekao":        True | False,
        "dana_do_roka":   int | None
      }
    """
    if not tekst or not tekst.strip():
        return []

    results: list[dict] = []
    seen_positions: set[int] = set()

    def _add(tip: str, vrednost: str, pos: int, end: int) -> None:
        if pos in seen_positions:
            return
        seen_positions.add(pos)
        ctx = _snippet(tekst, pos, end)
        results.append({
            "tip":       tip,
            "vrednost":  vrednost,
            "kontekst":  ctx,
            "kategorija": _kategorija(ctx),
            # BLK-1 (2026-08-24): `kontekst` je centriran isečak ±100 znakova i
            # iz njega se NE može pouzdano rekonstruisati gde je datum stajao u
            # originalnom tekstu (isečak se strip-uje, a tekstualni datumi se
            # normalizuju pa se `vrednost` u tekstu doslovno ni ne pojavljuje).
            # Bez tačne pozicije nijedan pozivalac ne može da proveri ŠTA stoji
            # neposredno PRE datuma — a upravo to je jedina razlika između
            # "Rok za žalbu ističe 25.08.2026" i "primljeno dana 25.08.2026".
            # Polja su čisto aditivna: nijedan postojeći ključ nije promenjen.
            "pozicija":  pos,
            "kraj":      end,
        })

    # ─── 1. Apsolutni datum DD.MM.YYYY ──────────────────────────────────────
    for m in re.finditer(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", tekst):
        day, month, year = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        _add("apsolutni", f"{day}.{month}.{year}", m.start(), m.end())

    # ─── 2. Tekstualni datum: "15. maja 2026" / "15 maja 2026" ──────────────
    meseci_pattern = "|".join(list(_MESECI_GEN) + list(_MESECI_NOM))
    pat_tekstualni = re.compile(
        rf"\b(\d{{1,2}})\.?\s+({meseci_pattern})\s+(\d{{4}})\b",
        re.IGNORECASE,
    )
    for m in pat_tekstualni.finditer(tekst):
        day  = m.group(1).zfill(2)
        mon  = (_MESECI_GEN.get(m.group(2).lower()) or _MESECI_NOM.get(m.group(2).lower(), "??"))
        year = m.group(3)
        _add("apsolutni", f"{day}.{mon}.{year}", m.start(), m.end())

    # ─── 3. Redni broj + mesec: "petnaestog maja 2026" ───────────────────────
    for redni_str, day_str in _REDNI.items():
        pat = re.compile(
            rf"\b{re.escape(redni_str)}\s+({meseci_pattern})\s+(\d{{4}})\b",
            re.IGNORECASE,
        )
        for m in pat.finditer(tekst):
            mon  = (_MESECI_GEN.get(m.group(1).lower()) or _MESECI_NOM.get(m.group(1).lower(), "??"))
            year = m.group(2)
            _add("apsolutni", f"{day_str}.{mon}.{year}", m.start(), m.end())

    # ─── 4. Relativni rok: "u roku od N dana/meseci/godina" ─────────────────
    pat_relativni = re.compile(
        r"u\s+roku\s+od\s+(\d+)\s+(dan[a]?|dana|radnih?\s+dana|mesec[a]?|meseci|godin[ae]?|nedeljno|nedelj[ae]?)",
        re.IGNORECASE,
    )
    for m in pat_relativni.finditer(tekst):
        vrednost = f"{m.group(1)} {m.group(2).strip()}"
        _add("relativni", vrednost, m.start(), m.end())

    # ─── 5. "narednog radnog dana" ───────────────────────────────────────────
    for m in re.finditer(r"\bnarednog\s+radnog\s+dana\b", tekst, re.IGNORECASE):
        _add("relativni", "narednog radnog dana", m.start(), m.end())

    # ─── 6. "u roku od N radnih dana" (fallback ako nije uhvaćen gore) ───────
    for m in re.finditer(r"\bu\s+roku\s+od\s+(\d+)\s+radnih?\s+dana\b", tekst, re.IGNORECASE):
        vrednost = f"{m.group(1)} radnih dana"
        _add("relativni", vrednost, m.start(), m.end())

    # ─── 7. "rok od N dana" (skraćena forma) ─────────────────────────────────
    for m in re.finditer(r"\brok\s+od\s+(\d+)\s+(dan[a]?|dana|mesec[a]?|meseci)\b", tekst, re.IGNORECASE):
        vrednost = f"{m.group(1)} {m.group(2)}"
        _add("relativni", vrednost, m.start(), m.end())

    # ─── 8. "u roku od N meseca" ─────────────────────────────────────────────
    for m in re.finditer(r"\bu\s+roku\s+od\s+(\d+)\s+mesec[ia]?\b", tekst, re.IGNORECASE):
        vrednost = f"{m.group(1)} meseci"
        _add("relativni", vrednost, m.start(), m.end())

    # ─── 9. "N dana od" / "je N dana" (skraćena forma bez "u roku od") ───────
    for m in re.finditer(r"\b(?:je|iznosi|traje)\s+(\d+)\s+dan(?:a)?\b", tekst, re.IGNORECASE):
        vrednost = f"{m.group(1)} dana"
        _add("relativni", vrednost, m.start(), m.end())

    for m in re.finditer(r"\b(\d+)\s+dan(?:a)?\s+od\b", tekst, re.IGNORECASE):
        vrednost = f"{m.group(1)} dana"
        _add("relativni", vrednost, m.start(), m.end())

    # ─── Deduplikacija: isti vrednost + prvih 50 chars konteksta ─────────────
    # BA-01: `dedup_konteksta=False` traži `shared/intake_extract.py::dokazani_rokovi` — u kratkom dokumentu dva
    # RAZLIČITA roka istog datuma imaju isti isečak (počinje od 0) i ovaj korak bi drugi tiho izbacio. Ta funkcija
    # sama razlikuje obaveze po dokaznoj frazi; isti položaj se i dalje ne broji dvaput (`seen_positions`).
    seen_keys: set[str] = set()
    deduped: list[dict] = []
    for r in results:
        key = r["vrednost"] + "|" + (r["kontekst"][:50] if dedup_konteksta else str(r["pozicija"]))
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(r)

    # ─── Sortiranje: apsolutni hronološki → relativni leksikografski ─────────
    def _sort_key(r: dict) -> tuple:
        if r["tip"] == "apsolutni":
            parts = r["vrednost"].split(".")
            if len(parts) == 3:
                return (0, f"{parts[2]}-{parts[1]}-{parts[0]}")
            return (0, r["vrednost"])
        return (1, r["vrednost"])

    deduped.sort(key=_sort_key)

    # ─── Phase 4.1: Dodaj kalkulisana polja na svaki rok ─────────────────────
    for r in deduped:
        kalk = _kalkulisi_rok(r["vrednost"], r["tip"], datum_dokumenta)
        r["konkretan_datum"] = kalk["konkretan_datum"]
        r["istekao"]         = kalk["istekao"]
        r["dana_do_roka"]    = kalk["dana_do_roka"]
        if kalk.get("racun_izostavljen"):
            r["racun_izostavljen"] = kalk["racun_izostavljen"]

    return deduped
