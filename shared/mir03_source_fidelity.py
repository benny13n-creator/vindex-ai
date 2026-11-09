"""Uska provera pripisanih navoda u AI radnom nacrtu, pre naplate i čuvanja."""

import re

from shared import nacrt_za_sud as NZ
from shared import procesno_stanje as PS
from shared import usvajanje_nacrta as UN


class NepouzdanIzvor(ValueError):
    """Nacrt pripisuje navod izvoru koji ga ne potkrepljuje."""


_AKTER = r"tuzilac|tuzeni|vestak|sud"
_GENITIV = r"tuzioca|tuzenog|vestaka|suda"
_GLAGOL = (r"tvrdi|tvrdio|navodi|naveo|kaze|rekao|istice|istakao|zakljucuje|zakljucio|"
           r"utvrdjuje|utvrdio|konstatuje|konstatovao")
_DOK = re.compile(r"\bdok-(\d{1,4})\b")
_VEZAN_DOK = re.compile(r"\b(?:u|iz|prema)\s+(?:\w+\s+)?dok-(\d{1,4})\b")
_PS = re.compile(r"\[\[\s*(ps-\d{1,3})\s*\]\]")
_POZIV = re.compile(
    rf"\b(?:(?P<akter>{_AKTER})\s+(?:je\s+)?(?:u\s+(?:nalazu|podnesku|izjasnjenju|odgovoru|"
    rf"dopuni|odluci|zapisniku)\s+)?(?:(?P<negacija>ne\s+|nije\s+)?(?:{_GLAGOL})\s+da\s+"
    rf"|(?P<porice>porice)\s+da\s+|(?P<spor>osporava)\s+)"
    rf"|(?:tvrdnj\w*|navod\w*|zakljuc\w*)\s+(?P<pripisan>{_GENITIV})\s+da\s+"
    rf"|prema\s+(?:navodu|tvrdnji|zakljucku|nalazu)\s+(?P<prema>{_GENITIV})\s*[:,]?\s*"
    rf"|(?:navedeno|utvrdjeno|utvrdeno|izneto)\s+je\s+od\s+strane\s+(?P<pasiv>{_GENITIV})\s+da\s+)"
)
_POSLE = re.compile(
    rf"[,–—]\s*(?:(?:kako\s+)?(?:to\s+)?(?:{_GLAGOL})\s+(?:je\s+)?(?P<akter>{_AKTER})"
    rf"|prema\s+(?:navodu|tvrdnji|zakljucku)\s+(?P<pripisan>{_GENITIV}))\s*$"
)
_IMENA = dict(zip(_GENITIV.split("|"), _AKTER.split("|")))
_RAZDVOJ = re.compile(r"(;\s*|,\s+(?:jer|dok|ali|a|medjutim)\s+)")
_USLOV = re.compile(r"^(?:ako|ukoliko|kada)\s+(?:bi\s+)?$")
_ISKAZ = re.compile(r"\b(?:je|su|nije|nisu|bio|bila|utvrdjeno|utvrdeno)\b")
_HIPOTETICKI = re.compile(r"^(?:ako|ukoliko|nakon sto bude)\b[^,]*,\s*(?:proveriti|razmotriti)\b")
_NEGIRANA_DOSTAVA = re.compile(r"^\s*(?:vestakov nalaz|nalaz vestaka) nije (?:dostavljen|urucen)\b[^,;]*$")
_OSPORAVANI_NAVOD = re.compile(rf"navod\w*\s+({_GENITIV})")
_SUD_PRIHVATA = re.compile(r"^sud (?:je (?:vec )?prihvatio|prihvata)\b")
_NAPOMENA_AI = re.compile(
    r"^\W*ovaj nacrt generisala je ai i mora ga pregledati i potpisati ovlasceni advokat pre podnosenja sudu$"
)
_UPUT_ZA_PREGLED = re.compile(
    r"(?:pogledaj(?:te)?|videti|proveriti) dok-\d{1,4}(?:(?:,|\s+i)\s+dok-\d{1,4})*[.!]?"
)


def _bez_oznaka(tekst: str) -> str:
    tekst = re.sub(r"\b(?:u|iz)\s+(?=dok-\d+\b)", "", tekst)
    tekst = _PS.sub("", _DOK.sub("", tekst))
    return re.sub(r"\s+", " ", re.sub(r"\(\s*\)|\[\s*\]", "", tekst)).strip(" .,:;()„“\"")


def _navodi(tekst: str) -> list[tuple[str, str, str]]:
    """Razdvoji izveštaj o tuđem navodu od glasa koji ga prenosi."""
    pozivi = list(_POZIV.finditer(tekst))
    if not pozivi:
        posle = _POSLE.search(tekst)
        if posle:
            akter = posle["akter"] or _IMENA[posle["pripisan"]]
            return [(akter, "navod", tekst[:posle.start()])]
    rezultat = []
    for i, poziv in enumerate(pozivi):
        uvod = tekst[:poziv.start()].strip(" ,:")
        if _USLOV.fullmatch(uvod) and poziv["akter"] and not poziv["spor"]:
            continue
        akter = poziv["akter"] or _IMENA[poziv["pripisan"] or poziv["prema"] or poziv["pasiv"]]
        kraj = pozivi[i + 1].start() if i + 1 < len(pozivi) else len(tekst)
        sadrzaj = tekst[poziv.end():kraj].strip(" ,:\"„“")
        # Tekući prigovor citiranom navodu je argument u nacrtu. Ugnježden
        # navod se proverava kao zaseban iskaz svog govornika.
        if not sadrzaj and poziv["spor"] and i + 1 < len(pozivi) and pozivi[i + 1]["pripisan"]:
            continue
        radnja = "navod"
        if poziv["spor"]:
            radnja = "spor"
        elif poziv["porice"] or poziv["negacija"]:
            radnja = "porice" if poziv["porice"] else "nije_naveo"
        rezultat.append((akter, radnja, sadrzaj))
    return rezultat


def _sadrzaj(tekst: str) -> str:
    tekst = re.sub(r"\b(?:nakon sto je|nakon|posle)\b", "posle", tekst)
    tekst = re.sub(r"^sud je (?:vec )?prihvatio\b", "sud prihvata", tekst)
    return _bez_oznaka(tekst).strip(" \"„“«»")


def _podudaranje(navod: str, izvod: str, radnja: str, akter: str) -> bool:
    """Doslovan iskaz ili ograničena promena oblika koja čuva aktera i smer odnosa."""
    navod, izvod = _sadrzaj(navod), _sadrzaj(izvod)
    if navod == izvod:
        return bool(navod)
    if radnja == "spor":
        if navod == "nalaz":
            navod = "nalaz vestaka"
        return bool(re.fullmatch(re.escape(navod) + r"(?: od \d{1,2}\.\d{1,2}\.\d{4}\.?(?: godine)?)?", izvod))
    # Dopuna mesta u iskazu o uzroku može biti izostavljena; druge kvalifikacije ostaju.
    uzrok = re.fullmatch(r"je uzrok (\w+) (.+)", navod)
    if uzrok:
        posledica, razlog = uzrok.groups()
        if re.fullmatch(
            rf"uzrok {re.escape(posledica)} je {re.escape(razlog)}(?: na spoju \w+)?", izvod,
        ):
            return True
        return akter == "vestak" and bool(
            re.fullmatch(rf"uzrok \w+ je {re.escape(navod.removeprefix('je uzrok '))}", izvod)
        )
    # Aktivni iskaz o uzroku i ista relacija sa izričito navedenom ugradnjom.
    uzrok = re.fullmatch(r"su (\w+) (\w+) uzrok (\w+)", navod)
    if uzrok:
        pridev, imenica, posledica = uzrok.groups()
        if pridev.endswith("i") and imenica.endswith("i"):
            genitiv = f"{pridev[:-1]}ih {imenica[:-1]}a"
            posledica = posledica.removesuffix("a") + "e" if posledica.endswith("nja") else posledica
            return bool(re.fullmatch(
                rf"je {re.escape(posledica)} posledica ugradnje {re.escape(genitiv)}(?: od strane treceg lica)?",
                izvod,
            ))
    pasiv = re.fullmatch(r"(\w+) (\w+) nije ostecena (\w+) (\w+) (\w+)", navod)
    if pasiv:
        predmet, dodatak, nosilac, pridev, imenica = pasiv.groups()
        if predmet.endswith("a") and nosilac.endswith("ima"):
            return izvod == f"{nosilac[:-2]} {pridev} {imenica} nisu ostetili {predmet[:-1]}u {dodatak}"
    bez_datuma = re.sub(r"\s+tek dana \d{1,2}\.\d{1,2}\.\d{4}\.?(?: godine)?,?", "", izvod)
    return navod == bez_datuma and bez_datuma != izvod


def _dokazne_jedinice(izvor: dict) -> list[tuple[str, str, str]]:
    tekst = izvor["tekst"]
    vrsta = izvor["vrsta"]
    if vrsta.get("sukob"):
        return []
    autor = vrsta["akter"].lower()
    if autor == "stranka":
        naslov = NZ._n(vrsta["naslov"])
        if naslov.startswith("odgovor na tuzbu"):
            autor = "tuzeni"
        elif naslov.startswith("tuzba"):
            autor = "tuzilac"
    rezultat = []
    for a, b in PS._jedinice(tekst, vrsta["kraj_naslova"]):
        if tekst[a:b].lstrip().startswith(("„", '"', "«", "“")) or tekst[:a].rstrip().endswith(":"):
            continue
        recenica = NZ._n(tekst[a:b]).strip()
        navodi = _navodi(recenica)
        if navodi:
            # Jednostavan iskaz autora ili direktno zabeležen glas u sudskom zapisniku.
            pocetak = _POZIV.match(recenica)
            if len(navodi) == 1 and pocetak and pocetak["akter"]:
                akter, radnja, sadrzaj = navodi[0]
                potvrdjen_sud = autor == "sud" and vrsta["osnov"] == "ADVOKAT"
                if (akter == autor and akter != "sud") or potvrdjen_sud:
                    rezultat.append((akter, radnja, sadrzaj))
        elif autor == "vestak":
            rezultat.append((autor, "navod", recenica))
        if autor == "sud" and _SUD_PRIHVATA.match(recenica):
            rezultat.append((autor, "prihvata", recenica))
        rezultat.append(("", "navod", recenica))
    return rezultat


def proveri(tekst: str, izvori: dict, stanje: dict | None = None, *, proverena_dostava=None) -> set[str]:
    """Vrati oznake potkrepljujućih izvora za atomsku proveru identiteta i sadržaja.

    Nema zaključivanja o istinitosti navoda. Nepotkrepljen iskaz koji kapija
    prepozna traži novi nacrt. Proizvoljne parafraze nisu dokaz.
    """
    procesni_izvodi = {d["id"].lower(): d for d in (stanje or {}).get("dogadjaji", [])}
    jedinice = {}
    upotrebljeni = set()
    tekst = UN._RE_OZNAKA.sub(lambda m: f"DOK-{int(m[1]):02d}", tekst)
    prethodno_upucivanje = False
    for segment in NZ._segmenti(tekst):
        if not segment.strip():
            prethodno_upucivanje = False
            continue
        normalizovan = NZ._n(segment)
        if _UPUT_ZA_PREGLED.fullmatch(normalizovan):
            # Upućivanje na pregled ne tvrdi šta dokument sadrži.
            prethodno_upucivanje = True
            continue
        delovi = _RAZDVOJ.split(normalizovan)
        prethodno_citiran = False
        for i in range(0, len(delovi), 2):
            deo = delovi[i]
            oznake = {f"DOK-{int(broj):02d}" for broj in _DOK.findall(deo)}
            ps_izvodi = [procesni_izvodi[p] for p in _PS.findall(deo) if p in procesni_izvodi]
            ps_oznake = {d["oznaka"] for d in ps_izvodi}
            if not (oznake | ps_oznake) <= izvori.keys():
                raise NepouzdanIzvor
            upotrebljeni.update(ps_oznake)
            vezani = {f"DOK-{int(broj):02d}" for broj in _VEZAN_DOK.findall(deo)}
            cisto = re.sub(r"^\s*\d+[.)]\s*", "", _bez_oznaka(deo))
            navodi = _navodi(cisto)
            if not oznake and not ps_oznake:
                # Osporavanje može biti sadašnja pravna radnja u samom nacrtu.
                navodi = [navod for navod in navodi if navod[1] != "spor"]
            # Oznaka iz prethodne suprotstavljene tvrdnje ne potkrepljuje novu činjenicu.
            zasebna_tvrdnja = prethodno_upucivanje if i == 0 else (
                prethodno_citiran and not delovi[i - 1].startswith(", jer")
            )
            prethodno_citiran = prethodno_citiran or bool(oznake or ps_oznake)
            if not navodi and (oznake or ps_oznake) and _SUD_PRIHVATA.match(cisto):
                navodi = [("sud", "prihvata", cisto)]
            if not navodi and (oznake or zasebna_tvrdnja) and _ISKAZ.search(cisto) and not (
                _HIPOTETICKI.match(cisto) or _NEGIRANA_DOSTAVA.match(cisto)
                or (not oznake and _NAPOMENA_AI.fullmatch(cisto))
                or (proverena_dostava and proverena_dostava(deo))
            ):
                navodi = [("", "navod", cisto)]
            for akter, radnja, sadrzaj in navodi:
                kandidati = vezani or oznake
                if not kandidati and not ps_izvodi and akter in ("tuzilac", "tuzeni", "vestak"):
                    # Doslovan navod bez oznake vezuje se za pročitani izvor.
                    kandidati = izvori.keys()
                osporavani = _OSPORAVANI_NAVOD.fullmatch(sadrzaj) if radnja == "spor" else None
                podrska = set()
                for oznaka in sorted(kandidati):
                    if oznaka not in jedinice:
                        jedinice[oznaka] = _dokazne_jedinice(izvori[oznaka])
                    if osporavani and _IMENA[osporavani[1]] != akter:
                        # U ovom podnesku stranka osporava konkretan tuđi navod.
                        # Citat identifikuje osporavani iskaz, a ne dokaz ranijeg prigovora.
                        if any(govornik == _IMENA[osporavani[1]] for govornik, _, _ in jedinice[oznaka]):
                            podrska.add(oznaka)
                    elif any(
                        (govornik, vrsta) == (akter, radnja) and _podudaranje(sadrzaj, izvod, radnja, akter)
                        for govornik, vrsta, izvod in jedinice[oznaka]
                    ):
                        podrska.add(oznaka)
                if not kandidati:
                    for dogadjaj in ps_izvodi:
                        oznaka = dogadjaj["oznaka"]
                        izvor = izvori[oznaka]
                        jedinica = {"tekst": dogadjaj["izvod"], "vrsta": {**izvor["vrsta"], "kraj_naslova": 0}}
                        if oznaka not in jedinice:
                            jedinice[oznaka] = _dokazne_jedinice(izvor)
                        if any(
                            (govornik, vrsta) == (akter, radnja) and _podudaranje(sadrzaj, izvod, radnja, akter)
                            for govornik, vrsta, izvod in _dokazne_jedinice(jedinica)
                            if (govornik, vrsta, izvod) in jedinice[oznaka]
                        ):
                            podrska.add(oznaka)
                if not podrska or not vezani <= podrska:
                    raise NepouzdanIzvor
                upotrebljeni.update(podrska)
                if not osporavani:
                    prethodno_upucivanje = True
    return upotrebljeni
