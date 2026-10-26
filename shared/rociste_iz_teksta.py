# -*- coding: utf-8 -*-
"""
Vindex AI — shared/rociste_iz_teksta.py

N3 (2026-10-26): ročište pročitano iz teksta sudskog dokumenta (poziv, zapisnik, rešenje) kao PREDLOG.

Deterministički, bez modela, po REČENICAMA. Rečenica je kandidat samo ako pominje ročište / glavnu raspravu.
U njoj se bira datum:
  * posle glagola zakazivanja („zakazuje se“, „zakazano je za“, „održaće se“, „će se održati“, „pristupi“…),
    ako takav glagol postoji — inače prvi datum rečenice („Poziva se tuženi da dana 15.11. pristupi na ročište“);
  * NIKAD datum uz „do / najkasnije do / u roku“ (rok za radnju, ne ročište);
  * ako rečenica kaže da ročište NIJE predstojeće (odlaže se / odloženo / neće se održati / otkazuje se /
    skida se sa dnevnog reda / održano / održanog / zaključena…), važi samo datum koji stoji POSLE poslednje
    takve oznake I posle glagola zakazivanja („odlaže se i zakazuje za 03.12.“); ostalo se ne predlaže.
Ništa se ne upisuje — pozivalac (`routers/rocista.py`) vraća predloge advokatu, koji ih proverava i sam
zakazuje. Uz svaki predlog ide doslovna rečenica iz dokumenta. Tekst na ćirilici se poredi preslovljen na
latinicu, pa je i citat na latinici.

Granice (svesne): broj predmeta i sud se čitaju na nivou dokumenta (prvo pojavljivanje); datum zapisan
rečima („dvanaestog novembra“) se ne prepoznaje; OCR koji pogrešno pročita cifru daje pogrešan ili nikakav
datum — zato je ovo predlog sa citatom, nikad ročište.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

_CIR = str.maketrans({
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ђ": "Đ", "Е": "E", "Ж": "Ž", "З": "Z", "И": "I", "Ј": "J",
    "К": "K", "Л": "L", "Љ": "Lj", "М": "M", "Н": "N", "Њ": "Nj", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T",
    "Ћ": "Ć", "У": "U", "Ф": "F", "Х": "H", "Ц": "C", "Ч": "Č", "Џ": "Dž", "Ш": "Š",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "đ", "е": "e", "ж": "ž", "з": "z", "и": "i", "ј": "j",
    "к": "k", "л": "l", "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "ћ": "ć", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "č", "џ": "dž", "ш": "š",
})

# „raspravljao“, „Raspravno veće“ nisu ročište — samo imenica rasprava u padežu.
_KLJUC = re.compile(r"ro[čc]i[šs]t\w*|\brasprav[aeiou]\b", re.IGNORECASE)
_MESECI = {"januar": 1, "februar": 2, "mart": 3, "april": 4, "maj": 5, "jun": 6, "jul": 7, "avgust": 8,
           "septembar": 9, "septembr": 9, "oktobar": 10, "oktobr": 10, "novembar": 11, "novembr": 11,
           "decembar": 12, "decembr": 12}
_DATUM = re.compile(r"(?<!\d)(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4})(?!\d)\.?")
_DATUM_REC = re.compile(r"(?<!\d)(\d{1,2})\s*\.\s*(" + "|".join(sorted(_MESECI, key=len, reverse=True)) + r")[a-z]*\s+(\d{4})(?!\d)\.?",
                        re.IGNORECASE)
_VREME = re.compile(r"(?:\bu\s*|po[čc]etkom\s+u\s*|od\s+)(\d{1,2})\s*[:.,]\s*(\d{2})(?!\d)"
                    r"|(?<!\d)(\d{1,2})\s*[:.,]\s*(\d{2})\s*(?:[čc]as|sat|h\b)"
                    r"|\bu\s*(\d{1,2})\s*(?:[čc]asova|[čc]as|sati|h\b)", re.IGNORECASE)
_SUDNICA = re.compile(r"sudnic\w*\s*(?:br(?:oj|\.)?\s*)?(\d{1,4}[a-zA-Z]?)\b", re.IGNORECASE)
# Glagol/izraz zakazivanja: datum POSLE njega je datum ročišta. „neće se održati“ se proverava kao oznaka NE.
_ZAKAZIVANJE = re.compile(r"zakaz\w*|odr[žz]a(?:će|ce)\s+se|(?<!ne)(?<!ne\s)(?:će|ce)\s+se\s+odr[žz]ati|"
                          r"bi(?:će|ce)\s+odr[žz]an\w*|pristupi(?:te|ti)?\b|pristupe\b|"
                          r"odr[žz]ava\s+se|poziva\w*\s+se|"
                          # „ročište se odlaže ZA 03.12.“ — novi datum posle oznake odlaganja
                          r"\b(?:za|na)\s+(?:dan\s+)?(?=\d{1,2}\s*\.)", re.IGNORECASE)
# Ročište koje NIJE predstojeće — oba redosleda reči („odlaže se“ / „se odlaže“), pre ili posle reči „ročište“.
# „otkazu/otkaza“ (otkaz ugovora o radu) je predmet spora, ne stanje ročišta, pa ga ovde nema.
_NIJE_PREDSTOJECE = re.compile(r"\b(?:odla[žz]\w*|odlo[žz]\w*|otkazuje|otkazan\w*|ne\s*(?:će|ce)\s+(?:se\s+)?odr[žz]a\w*|"
                               r"pomer\w*|prekida\w*|donet\w*|pristupi(?:o|la|li|lo)\b|prekinut\w*|umesto|ne\s+mo\w*\s+(?:se\s+)?odr[žz]a\w*|"
                               r"nij[ea]\s+(?:se\s+)?(?:\w+\s+)?odr[žz]a\w*|"
                               r"skida\s+se\s+sa\s+dnevnog\s+reda|(?<!će\s)(?<!ce\s)odr[žz]an\w*|zaklju[čc]en\w*|naknadno|neodre[đd]eno)\b",
                               re.IGNORECASE)
# Datum uz koji stoji rok za radnju, ne ročište.
# „rešenjem od 28.10.“, „podnesak od …“ — datum akta, ne ročišta.
_ROK_ZA_RADNJU = re.compile(r"(?:\bdo|\bnajkasnije|\bu\s+roku|\bpre|\bod)\s*(?:dana\s*)?$|\brok\w*\b[^.]{0,30}$", re.IGNORECASE)
_SUD = re.compile(r"\b(osnovni|vi[šs]i|privredni\s+apelacioni|privredni|apelacioni|upravni|prekr[šs]ajni)\s+sud\s+u\s+"
                  r"([A-ZČĆŠĐŽa-zčćšđž]+(?:\s+(?:Sadu|SADU|Pazaru|PAZARU|Mitrovici|MITROVICI|Milanovcu|MILANOVCU|Palanci|PALANCI))?)",
                  re.IGNORECASE)
_BROJ = re.compile(r"(?:posl\.?\s*br\.?|poslovni\s+broj|broj\s+predmeta|br\.\s*predmeta)\s*:?\s*"
                   r"([A-ZČĆŠĐŽ][A-Za-zčćšđž]{0,3}\.?\s*\d{1,6}\s*/\s*\d{2,4})", re.IGNORECASE)
# Kraj rečenice: prazan red, ili tačka/!/? pa razmak (i novi red) pa veliko slovo. Tačka u datumu
# („15.11.2026. godine“) nije kraj, a ni JEDAN prelom reda — tekstualni sloj PDF-a i OCR lome rečenice u redove.
_KRAJ_RECENICE = re.compile(r"\n\s*\n+|(?<=[.!?])\s+(?=[A-ZČĆŠĐŽ])")
# Skraćenice posle kojih tačka nije kraj rečenice („sudija dr. Jovan“, „br. 14“).
_SKRACENICA = re.compile(r"\b(?:dr|br|g|ul|čl|cl|st|tač|tac|posl|mr|prof|sl|tzv)\.\s*$", re.IGNORECASE)
# Bez glagola zakazivanja: datum mora odmah da sledi reč „ročište“ („Ročište: 15.11.“, „Ročište dana 15.11.“).
_ODMAH_UZ_KLJUC = re.compile(r"[\s:,\-–]*(?:dana\s*)?", re.IGNORECASE)


def _recenice(t: str) -> list[str]:
    delovi, tek = [], ""
    for deo in _KRAJ_RECENICE.split(t):
        if tek and _SKRACENICA.search(tek):
            tek = tek + " " + deo
        else:
            if tek:
                delovi.append(tek)
            tek = deo
    if tek:
        delovi.append(tek)
    return delovi


def preslovi(tekst: str) -> str:
    return (tekst or "").translate(_CIR)


def _datum(m) -> Optional[date]:
    try:
        if m.re is _DATUM_REC:
            mesec = next(v for k, v in _MESECI.items() if m.group(2).lower().startswith(k))
            return date(int(m.group(3)), mesec, int(m.group(1)))
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except (ValueError, StopIteration):
        return None


def _datumi(recenica: str) -> list:
    """Svi datumi rečenice rastuće po poziciji, bez datuma uz „do / najkasnije / u roku“."""
    out = []
    for m in sorted([*_DATUM.finditer(recenica), *_DATUM_REC.finditer(recenica)], key=lambda x: x.start()):
        if _ROK_ZA_RADNJU.search(recenica[max(0, m.start() - 35):m.start()]):
            continue
        out.append(m)
    return out


def sud_iz_teksta(tekst: str) -> Optional[str]:
    m = _SUD.search(preslovi(tekst))
    if not m:
        return None
    vrsta = m.group(1).lower().replace("visi", "viši").replace("prekrsajni", "prekršajni")
    mesto = " ".join(w[:1].upper() + w[1:].lower() for w in m.group(2).split())
    return f"{vrsta[:1].upper()}{vrsta[1:]} sud u {mesto}"


def broj_iz_teksta(tekst: str) -> Optional[str]:
    m = _BROJ.search(preslovi(tekst))
    if not m:
        return None
    oznaka = re.sub(r"\s*/\s*", "/", m.group(1).strip())
    return re.sub(r"^([A-Za-zČĆŠĐŽčćšđž]+\.?)\s*(\d)", r"\1 \2", oznaka)


def _citat(recenica: str, m) -> str:
    """Rečenica iz dokumenta; duga rečenica se seče oko izabranog datuma, na granici reči."""
    if len(re.sub(r"\s+", " ", recenica).strip()) <= 300:
        return re.sub(r"\s+", " ", recenica).strip()
    od, do = max(0, m.start() - 170), min(len(recenica), m.end() + 110)
    c = recenica[od:do]
    if od > 0 and " " in c:
        c = "… " + c[c.find(" ") + 1:]
    if do < len(recenica) and " " in c:
        c = c[:c.rfind(" ")] + " …"
    return re.sub(r"\s+", " ", c).strip()


def nadji_rocista(tekst: str) -> list[dict]:
    """Predlozi ročišta iz jednog teksta: `[{datum: date, vreme: 'HH:MM'|None, sudnica: str|None, citat: str}]`,
    bez ponavljanja istog (datum, vreme). Prošli datumi se NE odbacuju ovde (to radi pozivalac, uz broj)."""
    t = preslovi(tekst)
    out: list[dict] = []
    videni: set = set()
    recenice = [re.sub(r"\s+", " ", r) for r in _recenice(t)]
    for i, recenica in enumerate(recenice):
        if not _KLJUC.search(recenica):
            continue
        datumi = _datumi(recenica)
        if not datumi:
            continue
        # Oznaka stanja u SLEDEĆOJ rečenici bez datuma („… za 12.11. [prazan red] Odlaže se do daljeg.“) važi i ovde.
        dalje = recenice[i + 1] if i + 1 < len(recenice) else ""
        if dalje and not _datumi(dalje) and _NIJE_PREDSTOJECE.match(dalje.strip()):
            continue
        ne = list(_NIJE_PREDSTOJECE.finditer(recenica))
        granica = 0                                          # posle poslednje oznake „nije predstojeće“
        for n in ne:                                         # „umesto <staro ročište>, …“ gasi ceo deo do zareza
            granica = max(granica, recenica.find(",", n.end()) if n.group(0).lower() == "umesto" and "," in recenica[n.end():] else n.end())
        zak = [z for z in _ZAKAZIVANJE.finditer(recenica) if z.start() >= granica]
        if ne and not zak:
            continue                                         # samo stanje (odloženo / održano …), bez novog datuma
        izabrani = []
        if zak:                                              # po glagolu zakazivanja: prvi datum posle njega, pre sledećeg
            for j, z in enumerate(zak):
                do = zak[j + 1].start() if j + 1 < len(zak) else len(recenica)
                m = next((x for x in datumi if z.end() <= x.start() < do), None)
                if m and m not in izabrani:
                    izabrani.append(m)
        else:                                                # bez glagola: samo datum odmah uz reč „ročište“
            for k in _KLJUC.finditer(recenica):
                m = next((x for x in datumi if x.start() == _ODMAH_UZ_KLJUC.match(recenica, k.end()).end()), None)
                if m and m not in izabrani:
                    izabrani.append(m)
        for m in izabrani:
            _dodaj(out, videni, recenica, datumi, m)
    return out


def _dodaj(out: list, videni: set, recenica: str, datumi: list, m) -> None:
    if True:
        d = _datum(m)
        if not d or not (2000 <= d.year <= 2100):
            return
        sledeci = next((x.start() for x in datumi if x.start() > m.start()), len(recenica))
        v = _VREME.search(recenica[m.end():sledeci])
        vreme = None
        if v:
            h, mi = (v.group(1), v.group(2)) if v.group(1) else ((v.group(3), v.group(4)) if v.group(3) else (v.group(5), "00"))
            if 0 <= int(h) <= 23 and 0 <= int(mi) <= 59:
                vreme = f"{int(h):02d}:{int(mi):02d}"
        s = _SUDNICA.search(recenica)
        if (d, vreme) in videni:
            return
        videni.add((d, vreme))
        out.append({"datum": d, "vreme": vreme, "sudnica": s.group(1) if s else None, "citat": _citat(recenica, m)})
