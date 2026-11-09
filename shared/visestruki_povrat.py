"""N9 — višestruki povrat (Krivični zakonik čl. 55a): deterministička provera uslova i zakonski raspon kazne.

Bojan: „izračunavanje raspona kazne kod višestrukog povrata (KZ čl. 55a)“. Izmereno pre ove ispravke (stvarni tok,
model + Pinecone): opšte pitanje i pitanje sa činjenicama su BLOKIRANI bez odgovora, a model je u dva slučaja tvrdio da
su uslovi ispunjeni iako nisu (raniji zatvor od šest meseci; otpust pre sedam godina). Zato uslove i raspon računa kod,
ne model.

Izvori (doslovni citati):
  čl. 55a VAŽEĆI tekst — prečišćen tekst KZ na pravno-informacioni-sistem.rs (Sl. glasnik RS 85/2005 … 94/2024, 63/2026),
           proveren 27.10.2026; izmena iz zakona 63/2026 (objavljen 10.07.2026) primenjuje se od 18.07.2026 (napomena
           izdavača i čl. 5 tog zakona). Izmena: „polazeći od najmanje mere te kazne“, ranije osude „za ista ili istovrsna“
           dela i st. 2 (ranija osuda = pravnosnažna presuda domaćeg ili stranog suda). → CITAT_55A
  čl. 55a tekst DO 17.07.2026 — lokalni tekst zakona (data/laws/pdfs/krivicni_zakonik.pdf, zaključno sa 94/2024) →
           CITAT_55A_DO_63_2026. Baza zakona Vindex (Pinecone) još ima taj stari tekst.
  čl. 5: na učinioca se primenjuje zakon iz vremena izvršenja; ako je zakon posle izmenjen — zakon najblaži za učinioca.
  VKS Kzz 602/2022 od 14.06.2022 (vrh.sud.rs, proveren 27.10.2026): polovina = minimum + (maksimum − minimum)/2;
           raspon 3–12 g. → 7 g. 6 m.; kazna 7 g. 7 m. ocenjena kao pravilna. Odluka NIJE u bazi sudske prakse Vindex.
  čl. 45 st. 1: zatvor ne može biti kraći od trideset dana niti duži od dvadeset godina;
  čl. 45 st. 2: izriče se na pune godine i mesece, a do šest meseci i na dane.

GRANICE (namerno, ne pogađa se):
- Raspon je ZAKONSKI OKVIR, ne predviđanje kazne: kaznu u okviru odmerava sud (čl. 54).
- Odnos čl. 55a prema ublažavanju (čl. 56–57) i tumačenje „izrečene kazne“ kad ima više ranijih kazni NISU rešeni
  izvorom u bazi (nema teksta sudske prakse / stava Vrhovnog suda) — navode se kao otvorena pitanja, bez tvrdnje.
- Doživotni zatvor i kombinacije sa novčanom kaznom se ne računaju.
- Godina = 12 meseci; kad u rasponu učestvuju dani (opšti minimum od 30 dana), mesec se računa kao 30 dana i to se
  navodi u rezultatu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from shared.rociste_iz_teksta import preslovi

DA, NE, NEPOZNATO = "DA", "NE", "NEPOZNATO"

CITAT_55A = ("(1) Za krivično delo učinjeno sa umišljajem, za koje je propisana kazna zatvora, sud će izreći kaznu iznad "
             "polovine raspona propisane kazne polazeći od najmanje mere te kazne, pod sledećim uslovima: 1) ako je učinilac "
             "ranije dva puta osuđen za ista ili istovrsna krivična dela učinjena sa umišljajem na zatvor od najmanje jednu "
             "godinu; 2) ako od dana otpuštanja učinioca sa izdržavanja izrečene kazne do izvršenja novog krivičnog dela nije "
             "proteklo pet godina. (2) Pod ranijom osudom podrazumeva se osuda za krivično delo koja je utvrđena pravnosnažnom "
             "presudom domaćeg suda, odnosno suda strane države.")
IZVOR_55A = ("Krivični zakonik, prečišćen tekst (Sl. glasnik RS 85/2005 … 94/2024, 63/2026) — pravno-informacioni-sistem.rs; "
             "ovaj tekst čl. 55a primenjuje se od 18.07.2026 (izmena 63/2026)")
CITAT_55A_DO_63_2026 = ("Za krivično delo učinjeno sa umišljajem, za koje je propisana kazna zatvora, sud će izreći kaznu iznad "
                        "polovine raspona propisane kazne, pod sledećim uslovima: 1) ako je učinilac ranije dva puta osuđen za "
                        "krivična dela učinjena sa umišljajem na zatvor od najmanje jednu godinu; 2) ako od dana otpuštanja "
                        "učinioca sa izdržavanja izrečene kazne do izvršenja novog krivičnog dela nije proteklo pet godina.")
POCETAK_PRIMENE_55A = date(2019, 12, 1)  # Sl. glasnik RS 35/2019
POCETAK_PRIMENE_63_2026 = date(2026, 7, 18)
OPSTI_MINIMUM_DANA = 30          # čl. 45 st. 1
_NAPOMENA_POLOVINA = ("Način računanja: polovina raspona = minimum + (maksimum − minimum) / 2. Važeći tekst čl. 55a to izričito "
                      "određuje („polazeći od najmanje mere te kazne“, od 18.07.2026); isto pravilo primenio je Vrhovni kasacioni "
                      "sud u presudi Kzz 602/2022 od 14.06.2022 (raspon 3–12 godina: polovina 7 godina i 6 meseci, kazna od 7 "
                      "godina i 7 meseci ocenjena kao pravilna; tekst presude proveren na vrh.sud.rs — nije u bazi sudske prakse "
                      "Vindex).")
_NAPOMENA_BAZA = ("Napomena o izvoru: baza zakona Vindex sadrži tekst Krivičnog zakonika zaključno sa izmenom 94/2024 — izmena "
                  "63/2026 (čl. 55a) još nije u bazi. Navedeni citat je sadašnji tekst. Verzija merodavna za konkretno delo "
                  "utvrđuje se po čl. 5 KZ.")
_NAPOMENA_VREME = ("Vremensko važenje (čl. 5 KZ): od 01.12.2019 do izmene 63/2026 važio je tekst čl. 55a bez uslova "
                   "„ista ili istovrsna“ dela. Za delo izvršeno pre 18.07.2026 proverava se i kasniji blaži zakon (čl. 5 st. 2). "
                   "Kad ranija dela nisu ista ili istovrsna, blaži je važeći tekst (čl. 55a se ne primenjuje); koji je zakon "
                   "blaži kad postoji osuda stranog suda, procenjuje sud.")
_NAPOMENA_NAJNIZA = "Najniža kazna važi ako se kazna ne ublažava (vidi otvoreno pitanje)."
OPSTI_MAKSIMUM_MESECI = 20 * 12  # čl. 45 st. 1
_DANA_U_MESECU = 30              # samo kad raspon sadrži dane — navodi se u rezultatu


@dataclass
class RanijaOsuda:
    umisljaj: Optional[bool]
    zatvor_meseci: Optional[int]


@dataclass
class Uslov:
    oznaka: str
    stanje: str
    razlog: str


@dataclass
class Rezultat:
    uslovi: list[Uslov]
    primenjuje_se: str                    # DA / NE / NEPOZNATO
    raspon: Optional[dict] = None         # samo kad je primenjuje_se == DA i raspon je poznat
    napomene: list[str] = field(default_factory=list)
    nedostaje: list[str] = field(default_factory=list)


def _dani(meseci: int = 0, dana: int = 0) -> int:
    return meseci * _DANA_U_MESECU + dana


def format_trajanje(dana: int, genitiv: bool = False) -> str:
    g, ostatak = divmod(dana, 12 * _DANA_U_MESECU)
    m, d = divmod(ostatak, _DANA_U_MESECU)
    delovi = []
    jedan = lambda n: n % 10 == 1 and n % 100 != 11  # noqa: E731
    if g:
        delovi.append(f"{g} {'godine' if (g % 10 in (2, 3, 4) and not 12 <= g % 100 <= 14) or (genitiv and jedan(g)) else 'godina'}")
    if m:
        delovi.append(f"{m} {('meseca' if genitiv else 'mesec') if m == 1 else 'meseca' if m in (2, 3, 4) else 'meseci'}")
    if d:
        delovi.append(f"{d} {'dan' if jedan(d) and not genitiv else 'dana'}")
    if not delovi:
        return "0 dana"
    return delovi[0] if len(delovi) == 1 else ", ".join(delovi[:-1]) + " i " + delovi[-1]


def izracunaj(*, novo_delo_umisljaj: Optional[bool], propisan_min_dana: Optional[int], propisan_max_dana: Optional[int],
              ranije_osude: Optional[list[RanijaOsuda]], broj_ranijih_osuda: Optional[int] = None,
              proteklo_od_otpusta_meseci: Optional[float] = None, otpust: Optional[date] = None,
              novo_delo: Optional[date] = None, min_iz_opsteg_minimuma: bool = False,
              istovrsna: Optional[bool] = None, pravnosnaznost: Optional[str] = None,
              strana_osuda: bool = False) -> Rezultat:
    uslovi: list[Uslov] = []
    nedostaje: list[str] = []
    napomene: list[str] = []

    # Pretpostavke čl. 55a: novo delo sa umišljajem, propisan zatvor
    if novo_delo_umisljaj is True:
        uslovi.append(Uslov("novo delo učinjeno sa umišljajem", DA, "navedeno u pitanju"))
    elif novo_delo_umisljaj is False:
        uslovi.append(Uslov("novo delo učinjeno sa umišljajem", NE, "navedeno je da delo nije učinjeno sa umišljajem"))
    else:
        uslovi.append(Uslov("novo delo učinjeno sa umišljajem", NEPOZNATO, "nije navedeno ili nije prepoznato iz pitanja"))
        nedostaje.append("da li je novo delo učinjeno sa umišljajem")

    if propisan_max_dana is not None:
        uslovi.append(Uslov("za novo delo je propisana kazna zatvora", DA, "naveden propisan zatvor"))
    else:
        uslovi.append(Uslov("za novo delo je propisana kazna zatvora", NEPOZNATO, "propisana kazna nije navedena"))
        nedostaje.append("propisana kazna zatvora za novo delo (od–do)")

    # Uslov 1: dve ranije osude za umišljajna dela na zatvor od najmanje jednu godinu
    osude = ranije_osude or []
    kvalifikovane = sum(1 for o in osude if o.umisljaj is True and o.zatvor_meseci is not None and o.zatvor_meseci >= 12)
    neodredjene = sum(1 for o in osude if not (o.umisljaj is False or (o.zatvor_meseci is not None and o.zatvor_meseci < 12))
                      and not (o.umisljaj is True and o.zatvor_meseci is not None and o.zatvor_meseci >= 12))
    if broj_ranijih_osuda is not None and broj_ranijih_osuda > len(osude):
        neodredjene += broj_ranijih_osuda - len(osude)
    if kvalifikovane >= 2:
        uslovi.append(Uslov("1) dve ranije osude za umišljajna dela na zatvor od najmanje jednu godinu", DA,
                            f"{kvalifikovane} ranije osude ispunjavaju uslov"))
    elif kvalifikovane + neodredjene < 2 and (osude or broj_ranijih_osuda is not None):
        razlozi = []
        if any(o.zatvor_meseci is not None and o.zatvor_meseci < 12 for o in osude):
            razlozi.append("bar jedna ranija kazna zatvora je kraća od jedne godine")
        if any(o.umisljaj is False for o in osude):
            razlozi.append("bar jedno ranije delo nije umišljajno")
        if (broj_ranijih_osuda or len(osude)) < 2:
            razlozi.append("navedena je manje od dve ranije osude")
        uslovi.append(Uslov("1) dve ranije osude za umišljajna dela na zatvor od najmanje jednu godinu", NE,
                            "; ".join(razlozi) or "uslov nije ispunjen"))
    else:
        uslovi.append(Uslov("1) dve ranije osude za umišljajna dela na zatvor od najmanje jednu godinu", NEPOZNATO,
                            "nisu navedeni broj ranijih osuda, vrsta krivice ili visina izrečenih kazni"))
        nedostaje.append("broj ranijih osuda, da li su dela bila umišljajna i visina izrečenih kazni zatvora")

    # Uslov 2: od otpuštanja do novog dela nije proteklo pet godina
    if otpust and novo_delo:
        pet_godina = _plus_godina(otpust, 5)
        if novo_delo < pet_godina:
            uslovi.append(Uslov("2) od otpuštanja sa izdržavanja kazne do novog dela nije proteklo pet godina", DA,
                                f"otpust {otpust:%d.%m.%Y}, novo delo {novo_delo:%d.%m.%Y} (rok bi istekao {pet_godina:%d.%m.%Y})"))
        else:
            uslovi.append(Uslov("2) od otpuštanja sa izdržavanja kazne do novog dela nije proteklo pet godina", NE,
                                f"otpust {otpust:%d.%m.%Y}, novo delo {novo_delo:%d.%m.%Y} — proteklo je pet godina ili više"))
    elif proteklo_od_otpusta_meseci is not None:
        # navod „pre N godina“ je približan: tačno na granici od pet godina se ne odlučuje
        if proteklo_od_otpusta_meseci < 54:
            uslovi.append(Uslov("2) od otpuštanja sa izdržavanja kazne do novog dela nije proteklo pet godina", DA,
                                f"prema navodu iz pitanja proteklo je oko {format_trajanje(int(proteklo_od_otpusta_meseci * _DANA_U_MESECU))}"))
        elif proteklo_od_otpusta_meseci > 66:
            uslovi.append(Uslov("2) od otpuštanja sa izdržavanja kazne do novog dela nije proteklo pet godina", NE,
                                f"prema navodu iz pitanja proteklo je oko {format_trajanje(int(proteklo_od_otpusta_meseci * _DANA_U_MESECU))}"))
        else:
            uslovi.append(Uslov("2) od otpuštanja sa izdržavanja kazne do novog dela nije proteklo pet godina", NEPOZNATO,
                                "navedeno vreme je blizu granice od pet godina — potrebni su tačni datumi otpusta i novog dela"))
            nedostaje.append("tačan datum otpuštanja sa izdržavanja kazne i datum izvršenja novog dela")
    else:
        uslovi.append(Uslov("2) od otpuštanja sa izdržavanja kazne do novog dela nije proteklo pet godina", NEPOZNATO,
                            "datum ili vreme otpuštanja sa izdržavanja kazne nije naveden ili nije prepoznat iz pitanja"))
        nedostaje.append("datum otpuštanja sa izdržavanja kazne i datum izvršenja novog dela")

    # Uslov 1b (važeći tekst, 63/2026): ranija dela ISTA ili ISTOVRSNA kao novo. KZ istovrsnost ne definiše — sistem je
    # ne procenjuje; DA/NE samo kad je u pitanju izričito navedeno (noćni sprint S3).
    if istovrsna is True:
        uslovi.append(Uslov("1b) ranija dela su ista ili istovrsna kao novo delo", DA, "navedeno u pitanju"))
    elif istovrsna is False:
        uslovi.append(Uslov("1b) ranija dela su ista ili istovrsna kao novo delo", NE,
                            "navedeno je da ranija dela nisu ista ni istovrsna kao novo"))
    else:
        uslovi.append(Uslov("1b) ranija dela su ista ili istovrsna kao novo delo", NEPOZNATO,
                            "nije navedeno; Krivični zakonik ne definiše istovrsnost — ocenjuje je sud"))
        nedostaje.append("da li su ranija krivična dela ista ili istovrsna kao novo delo")
    if pravnosnaznost in (NE, NEPOZNATO):
        oznaka = "1c) dovoljan broj ranijih osuda utvrđen je pravnosnažnim presudama"
        if pravnosnaznost == NE and novo_delo and novo_delo >= POCETAK_PRIMENE_63_2026:
            uslovi.append(Uslov(oznaka, NE, "iz pitanja sledi da nema dve pravnosnažne ranije osude"))
        else:
            uslovi.append(Uslov(oznaka, NEPOZNATO, "pravnosnažnost ili vremenski merodavan tekst KZ nisu utvrđeni"))
            nedostaje.append("pravnosnažnost ranijih presuda i, ako nije utvrđen, datum novog dela")
    if novo_delo is not None and novo_delo < POCETAK_PRIMENE_55A:
        uslovi.append(Uslov("vremenski merodavan zakon", NEPOZNATO, "čl. 55a još nije bio na snazi na dan novog dela"))
        nedostaje.append("koji je zakon vremenski merodavan prema čl. 5 KZ")
    elif strana_osuda and novo_delo is not None and novo_delo < POCETAK_PRIMENE_63_2026:
        # Kzz 144/2024: strane presude su uzete u obzir uz dokaze o osudama i izvršenim kaznama u inostranstvu.
        # Za konkretno delo pre izmene nije dovoljan podatak da je presudu doneo strani sud.
        uslovi.append(Uslov("vremenski merodavan zakon", NEPOZNATO,
                            "uračunavanje strane osude po tadašnjem tekstu i blaži zakon (čl. 5 KZ) zahtevaju proveru spisa"))
        nedostaje.append("dokazi o stranoj osudi i ocena vremenski merodavnog zakona prema čl. 5 KZ")
    elif novo_delo is None and pravnosnaznost is not None:
        uslovi.append(Uslov("vremenski merodavan zakon", NEPOZNATO, "datum izvršenja novog dela nije utvrđen"))
        nedostaje.append("datum izvršenja novog dela")
    if novo_delo is None or novo_delo < POCETAK_PRIMENE_63_2026:
        napomene.append(_NAPOMENA_VREME)

    stanja = [u.stanje for u in uslovi]
    primenjuje = NE if NE in stanja else (DA if all(s == DA for s in stanja) else NEPOZNATO)

    raspon = None
    if primenjuje == DA and propisan_max_dana is not None:
        mn = propisan_min_dana if propisan_min_dana is not None else OPSTI_MINIMUM_DANA
        if propisan_min_dana is None or min_iz_opsteg_minimuma:
            napomene.append("Najmanja mera nije propisana za delo — primenjen je opšti minimum zatvora od 30 dana (čl. 45 st. 1).")
        polovina = mn + (propisan_max_dana - mn) / 2
        sadrzi_dane = (mn % _DANA_U_MESECU) or (propisan_max_dana % _DANA_U_MESECU) or (polovina % _DANA_U_MESECU)
        # čl. 45 st. 2: preko šest meseci — pune godine i meseci; najniža kazna IZNAD polovine
        if polovina >= 6 * _DANA_U_MESECU:
            najniza = (int(polovina) // _DANA_U_MESECU + 1) * _DANA_U_MESECU
        else:
            najniza = int(polovina) + 1
        raspon = {
            "propisano_od_dana": mn, "propisano_do_dana": propisan_max_dana,
            "polovina_raspona_dana": polovina, "najniza_dozvoljena_dana": min(najniza, propisan_max_dana),
            "najvisa_dana": propisan_max_dana, "mesec_30_dana": bool(sadrzi_dane),
        }
        if sadrzi_dane:
            napomene.append("U proračunu učestvuju dani — mesec je računat kao 30 dana.")
    return Rezultat(uslovi=uslovi, primenjuje_se=primenjuje, raspon=raspon, napomene=napomene, nedostaje=nedostaje)


def _plus_godina(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:      # 29. februar
        return d.replace(year=d.year + n, day=28)




# ── Prepoznavanje činjenica iz pitanja ───────────────────────────────────────────────────────────────────────────────
# Načelo (posle nezavisne revizije N9): parser NIKAD ne bira između više mogućih čitanja — kad tekst nije jednoznačan
# (negacija krivice, mešovita krivica ranijih dela, druga osoba, uslovna osuda/otpust, više pomena otpusta, više
# propisanih raspona), činjenica ostaje None → NEPOZNATO. Pogrešno „DA/NE“ je gore od „nepoznato“.
_BROJEVI = {"jedan": 1, "jedna": 1, "jedne": 1, "jednu": 1, "jednom": 1, "dva": 2, "dve": 2, "dvije": 2, "tri": 3, "cetiri": 4,
            "pet": 5, "sest": 6, "sedam": 7, "osam": 8, "devet": 9, "deset": 10, "jedanaest": 11, "dvanaest": 12,
            "petnaest": 15, "dvadeset": 20}
_JED_TXT = r"(?:godin\w*|mesec\w*|dan\w*)"
# jedno trajanje kao tekst; vrednost računa `_dur_dana`
_DUR = (r"(?:\w+\s+i\s+po\s+godin\w*|godinu\s+i\s+po|pola\s+godine|godinu\s+dana|"
        rf"\w+\s+{_JED_TXT}(?:\s+i\s+\w+\s+(?:mesec\w*|dan\w*))?)")
_DATUM = r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})"


def _norm(t: str) -> str:
    t = preslovi(t or "").lower()
    for a, b in {"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z"}.items():
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t)


def _broj(rec: str) -> Optional[int]:
    rec = (rec or "").strip().rstrip(".,")
    if rec.isdigit():
        return int(rec)
    return _BROJEVI.get(rec)


def _jedinica_dana(j: str) -> Optional[int]:
    return 12 * _DANA_U_MESECU if j.startswith("godin") else _DANA_U_MESECU if j.startswith("mesec") else 1 if j.startswith("dan") else None


def _dur_dana(s: str) -> Optional[int]:
    s = (s or "").strip()
    if re.fullmatch(r"godinu\s+i\s+po", s):
        return 18 * _DANA_U_MESECU
    if re.fullmatch(r"pola\s+godine", s):
        return 6 * _DANA_U_MESECU
    if re.fullmatch(r"godinu\s+dana", s):
        return 12 * _DANA_U_MESECU
    m = re.fullmatch(r"(\w+)\s+i\s+po\s+godin\w*", s)
    if m:
        n = _broj(m.group(1))
        return None if n is None else n * 12 * _DANA_U_MESECU + 6 * _DANA_U_MESECU
    m = re.fullmatch(rf"(\w+)\s+({_JED_TXT})(?:\s+i\s+(\w+)\s+(mesec\w*|dan\w*))?", s)
    if not m:
        return None
    n = 1 if m.group(1) == "godinu" else _broj(m.group(1))
    if n is None:
        return None
    ukupno = n * _jedinica_dana(m.group(2))
    if m.group(3):
        n2 = _broj(m.group(3))
        if n2 is None:
            return None
        ukupno += n2 * _jedinica_dana(m.group(4))
    return ukupno


def _krivica(seg: str) -> Optional[bool]:
    """True = umišljaj, False = nehat/negiran umišljaj, None = nije navedeno ili je mešovito."""
    negacija = (
        r"\bbez\s+umisljaj\w*|\bneumisljaj\w*|\bne\s+umisljaj\w*|\bnehat\w*"
        r"|\bnije\s+(?:bilo\s+)?(?:\w+\s+)?umisljaj\w*"
        r"|\bnisu\s+(?:bila\s+)?(?:\w+\s+)?umisljaj\w*"
        r"|\b(?:nije|nisu)\s+(?:ucin|izvrs)\w*\s+sa?\s+umisljaj\w*"
    )
    neg = bool(re.search(negacija, seg))
    poz = bool(re.search(r"umisljaj", re.sub(negacija, " ", seg)))
    if neg and poz:
        return None
    return False if neg else (True if poz else None)


_SIDRO_NOVOG = r"\b(?:sada|sad|ponovo|novo\s+delo|novog\s+dela|potom|nakon\s+toga|posle\s+toga|zatim)\b"
_RASPON = (r"(?:propisan\w*|predvidj\w*|zaprecen\w*)\s+(?:je\s+)?(?:kazna\s+)?zatvor\w*\s+od\s+(" + _DUR + r"|\w+)\s+do\s+(" + _DUR + r")"
           r"|\(\s*zatvor\w*\s+od\s+(" + _DUR + r"|\w+)\s+do\s+(" + _DUR + r")\s*\)")
_SAMO_DO = r"(?:propisan\w*|predvidj\w*|zaprecen\w*)\s+(?:je\s+)?(?:kazna\s+)?zatvor\w*\s+do\s+(" + _DUR + r")"
_DRUGA_OSOBA = r"saucesni\w*|saokrivljen\w*|drug\w*\s+okrivljen\w*|nije\s+(?:ranije\s+)?(?:bio\s+)?osudjivan|neosudjivan|nema\s+ranij\w*\s+osud"
_STRANI_SUD = r"(?:(?:stran|inostran)(?:i|og|oga|om|im|ih)\s+sud\w*|sud\w*\s+(?:strane\s+drzave|u\s+inostranstvu))"
_STRANA_OSUDA_RE = re.compile(
    rf"\bosud\w*[^.!?;]{{0,100}}\b{_STRANI_SUD}\b|\b{_STRANI_SUD}\b[^.!?;]{{0,100}}\b(?:osud|presud)\w*"
    r"|\b(?:stran|inostran)\w*\s+(?:osud|presud)\w*|\bosudjen\w*\s+u\s+inostranstvu\b"
)


def _raspon(odlomak: str) -> tuple[Optional[int], Optional[int], bool]:
    m = re.search(_RASPON, odlomak)
    if m:
        a_txt, b_txt = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        b = _dur_dana(b_txt)
        a = _dur_dana(a_txt)
        if a is None and b is not None and _broj(a_txt) is not None:        # „od jedne do osam godina“: jedinica iz drugog dela
            jed = re.search(_JED_TXT, b_txt)
            a = _broj(a_txt) * _jedinica_dana(jed.group(0)) if jed else None
        if re.search(r"novcan", odlomak[m.end(): m.end() + 40]):          # „… ili/i novčana kazna“ — ne računa se
            return None, None, False
        return a, b, False
    m = re.search(_SAMO_DO, odlomak)
    if m and not re.search(r"novcan", odlomak[m.end(): m.end() + 40]):
        return None, _dur_dana(m.group(1)), True
    return None, None, False


_NEGACIJA_BROJA_OSUDA_RE = re.compile(
    r"\b(?:ne|nije|nisu|nisam|nisi|nismo|niste)\s+"
    r"(?:(?:ranije|nikada?|bio|bila|bilo|bili|bile|pravnosnazno)\s+)*$"
)


def _broj_osuda(q: str):
    for obrazac in (r"\b(dva|dvaput|tri|triput|cetiri)\s*(?:puta\s+)?(?:je\s+)?(?:ranije\s+)?(?:pravnosnazno\s+)?osudj\w*",
                    r"\b(\d{1,2})\s+puta\s+(?:je\s+)?(?:ranije\s+)?(?:pravnosnazno\s+)?osudj\w*",
                    r"\bosudj\w*\s+(?:je\s+)?(?:ranije\s+)?(dva|dvaput|tri|triput|cetiri|\d{1,2})\s*puta",
                    r"\b(jednom)\s+(?:je\s+)?(?:ranije\s+)?(?:bio\s+)?osudj\w*",
                    r"\b(?:ima\s+)?(dve|tri|cetiri|\d{1,2})\s+ranij\w*\s+osud\w*"):
        m = re.search(obrazac, q)
        if m:
            if _NEGACIJA_BROJA_OSUDA_RE.search(q[:m.start()]):
                return None, None
            return _broj(m.group(1).replace("put", "")), m
    return None, None


# S1: posebne vrste ranije osude — da li se računaju za čl. 55a nije rešeno izvorom u bazi
# bilo gde u pitanju, ali samo jednoznačni izrazi (ne „izvod iz kaznene evidencije“, ne „na štetu maloletnog lica“)
_POSEBNA_OSUDA = (r"brisan\w*|maloletnick\w*\s+zatvor\w*|kao\s+maloletn\w*|vaspitn\w*\s+mer\w*|rad\w*\s+u\s+javnom\s+interesu|"
                  r"zamenjen\w*")
_GLAGOL_DELA = r"(?:izvrs|ucin)\w*"
_GODINA = r"(?<![/\d.])\b(?:19|20)\d{2}\b(?!\s*/)"        # godina, ali ne „94/2016“ (broj Službenog glasnika) ni deo datuma


_NOVO_DELO_U_INTERVALU = r"do\s+nov\w*\s+(?P<krivica>(?:umisljajn|nehatn)\w*\s+)?(?:krivicn\w*\s+)?del\w*"
_SAMOSTALAN_PROCESNI_DATUM = re.compile(
    r"(?<=[.!?])\s+(?:presuda je doneta|zalba je izjavljena)\s+" + _DATUM + r"(?:\.\s+godine)?(?=\.(?:\s|$)|$)"
)
_SAMOSTALAN_DATUM_NOVOG_DELA = re.compile(
    rf"(?:^|(?<=[.!?])\s+)novo delo (?:je )?{_GLAGOL_DELA} (?:je )?{_DATUM}"
    r"(?:\.\s+godine)?(?=\.(?:\s|$)|$)"
)
_NEUTVRDJEN_DATUM_NOVOG_DELA = re.compile(
    r"\bdatum(?:\s+izvrsenja)?(?:\s+(?:novog\s+)?dela)?(?:\s+u\s+spisu)?"
    r"\s+(?:nije\s+(?:utvrdjen|poznat|potvrdjen)|je\s+sporan)\b"
)
_OGRADA_DATUMA_NOVOG_DELA = re.compile(
    r"\b(?:ako|ukoliko|da li|pretpostav\w*|hipotetic\w*|navodn\w*|tvrd\w*|navodi|sporn\w*|osporav\w*|"
    r"(?:nije|nisu)\s+(?:utvrdj\w*|poznat\w*|potvrdj\w*|tacn\w*|ucin\w*|izvrs\w*))\b"
)
_GRANICA_RECENICE = re.compile(r"[.!?;](?=\s|$)")


def _datum_novog_dela(pitanje: str, pocetak_novog: Optional[int]):
    """Datum novog dela mora biti jednoznačan i uz glagol izvršenja."""
    if pocetak_novog is None:
        return None
    # Samostalne rečenice sa datumom presude ili žalbe ne menjaju datum izvršenja.
    novo = _SAMOSTALAN_PROCESNI_DATUM.sub(lambda m: " " * len(m[0]), pitanje[pocetak_novog:])
    datumi = list(re.finditer(_DATUM, novo))
    godine = re.findall(_GODINA, re.sub(_DATUM, " ", novo))
    if len(datumi) != 1 or godine:
        return None
    d = datumi[0]
    blizu = novo[max(0, d.start() - 60):d.start()] + " " + novo[d.end():d.end() + 25]
    if not re.search(_GLAGOL_DELA, blizu):
        return None

    # Klauzula ispred sidra može sadržati „pretpostavimo da je“ ili početak citata.
    od, do = pocetak_novog + d.start(), pocetak_novog + d.end()
    if any(citat.start() <= od < citat.end() for citat in _NAVOD_RE.finditer(pitanje)):
        return None
    prethodne_granice = list(_GRANICA_RECENICE.finditer(pitanje, 0, od))
    pocetak = prethodne_granice[-1].end() if prethodne_granice else 0
    godina = re.match(r"\.\s+godine\b", pitanje[do:])
    kraj = _GRANICA_RECENICE.search(pitanje, do + (godina.end() if godina else 0))
    if ((kraj and kraj.group() == "?")
            or _OGRADA_DATUMA_NOVOG_DELA.search(pitanje[pocetak:kraj.start() if kraj else None])
            or _NEUTVRDJEN_DATUM_NOVOG_DELA.search(_NAVOD_RE.sub(" [citat] ", pitanje))):
        return None
    return d


def _novo_delo_ima_svoje_vreme(novo: str) -> bool:
    """S1: „otpušten pre N“ meri vreme od otpusta do DANAS; ako novo delo ima svoje vreme („izvršio pre dve godine“,
    datum, godina, „pre otpusta“), vreme od otpusta do novog dela nije navedeno."""
    if not novo:
        return False
    # revizija S1: rečenica/klauza o otpustu iza sidra („…, a otpušten je pre tri godine“) nije vreme novog dela
    n = re.sub(r"otpust\w*[^.;,]*", " ", novo)
    return bool(re.search(r"\bpre\s+(?:vise\s+od\s+)?" + _DUR, n) or re.search(_DATUM, n) or re.search(_GODINA, n)
                # „sada mu se sudi“ / „tereti se“ je vreme SUĐENJA, ne dela (4. krug revizije)
                or re.search(r"\bsud\w*\s+(?:mu|joj|im)\s+se\b|\b(?:mu|joj|im)\s+se\s+sudi|sudjenj\w*|optuz\w*|tereti\s+se|"
                             r"pre\s+otpust|prosl\w*\s+godin|ove\s+godine|\blane\b|tokom\s+izdrzavanj|na\s+izdrzavanju|"
                             r"dok\s+je\s+(?:jos\s+)?(?:bio|bila)\s+u\s+zatvor", n))


def _izricito_bez_osuda_uz_saucesnika(q: str) -> bool:
    q = _NAVOD_RE.sub(" [citat] ", q)
    if re.search(r"\b(?:prv|drug|trec)\w*\s+okrivljen\w*\b", q):
        return False
    navodi = [rec.strip() for rec in re.split(r"(?<=[.!?;])\s+", q) if re.search(r"\b(?:osud|presud)\w*", rec)]
    if len(navodi) != 2:
        return False
    neosudjivan = r"okrivljen[ia] nije ranije osudjivan[a]?\."
    saucesnik = r"saucesni(?:k|ca) je (?:dva puta|dvaput|\d+ puta) pravnosnazno osudjen[a]?(?: za [^.!?;]+)?\."
    return any(re.fullmatch(neosudjivan, rec) for rec in navodi) and any(
        re.fullmatch(saucesnik, rec) and not re.search(r"\b(?:okrivljen|optuzen|ali\b|medjutim\b|dok\b)", rec)
        for rec in navodi
    )


def analiza(pitanje: str) -> tuple[dict, list[str]]:
    """(činjenice za `izracunaj`, napomene o prepoznavanju). Šta nije jednoznačno ostaje None (NEPOZNATO)."""
    q = _norm(pitanje)
    # Izričito označen hipotetički primer nije navod o okrivljenom.
    q = re.sub(r"\bhipotetick\w*\s+primer\s*:\s*(?:" + _NAVOD_RE.pattern + ")", " ", q)
    out: dict = {"novo_delo_umisljaj": None, "propisan_min_dana": None, "propisan_max_dana": None, "ranije_osude": None,
                 "broj_ranijih_osuda": None, "proteklo_od_otpusta_meseci": None, "otpust": None, "novo_delo": None,
                 "min_iz_opsteg_minimuma": False, "istovrsna": None}
    napomene: list[str] = []
    broj, m_osude = _broj_osuda(q)
    sidro = re.search(_SIDRO_NOVOG, q[m_osude.end():]) if m_osude else re.search(_SIDRO_NOVOG, q)
    granica = (m_osude.end() + sidro.start()) if (m_osude and sidro) else (sidro.start() if sidro else None)
    ranije = q[:granica] if granica is not None else q
    novo = q[granica:] if granica is not None else ""

    # propisana kazna za NOVO delo: iz dela posle sidra; bez sidra samo ako je u pitanju tačno jedan raspon
    svi = list(re.finditer(_RASPON, q)) + list(re.finditer(_SAMO_DO, q))
    izvor = novo if (novo and re.search(_RASPON + "|" + _SAMO_DO, novo)) else (q if len(svi) == 1 else "")
    if re.search(r"dozivotn", izvor or q):
        izvor = ""
    if izvor:
        mn, mx, opsti = _raspon(izvor)
        if mx is not None and mx <= OPSTI_MAKSIMUM_MESECI * _DANA_U_MESECU and (mn is None and opsti or (mn is not None and mn < mx)):
            out["propisan_min_dana"], out["propisan_max_dana"], out["min_iz_opsteg_minimuma"] = mn, mx, opsti

    # krivica novog dela
    if novo:
        out["novo_delo_umisljaj"] = _krivica(novo)

    # S3 (63/2026): istovrsnost ranijih dela — samo IZRIČIT, izjavni navod. Završna revizija (M1): prefiks naziva dela
    # („nasilje“/„nasilničko“) i rečenice sa negacijom, pitanjem ili spornom tvrdnjom su davale lažno DA → uklonjeno.
    out["istovrsna"] = _istovrsnost_iz_navoda(pitanje)
    strana_osuda = out["strana_osuda"] = bool(_STRANA_OSUDA_RE.search(q))
    if strana_osuda:
        napomene.append("Pitanje pominje osudu stranog suda. Po važećem tekstu (st. 2) i ona može biti ranija osuda ako je "
                        "utvrđena pravnosnažnom presudom. Za delo pre 18.07.2026 koji je zakon blaži procenjuje sud (čl. 5 st. 2).")

    druga_osoba = bool(re.search(_DRUGA_OSOBA, q))
    uslovno = bool(re.search(r"uslovn\w*", q))
    if druga_osoba and _izricito_bez_osuda_uz_saucesnika(q):
        out["broj_ranijih_osuda"] = 0
    elif druga_osoba:
        napomene.append("Pitanje pominje i drugu osobu ili neosuđivanost — ranije osude se ne pripisuju; potrebno je navesti "
                        "osude okrivljenog posebno.")
    if uslovno:
        napomene.append("Pitanje pominje uslovnu osudu ili uslovni otpust — da li se tada ispunjavaju uslovi čl. 55a (osuda „na zatvor“, "
                        "„otpuštanje sa izdržavanja“) nije rešeno izvorom u bazi; ti uslovi ostaju nepoznati.")

    # ranije osude
    if broj is not None and not druga_osoba:
        out["broj_ranijih_osuda"] = broj
        seg = re.sub(_RASPON + "|" + _SAMO_DO, " ", ranije)                   # propisani rasponi ranijih dela nisu kazne
        # S1 (3. krug revizije): krivica ranijih dela SAMO iz rečenice osude (pre uklanjanja zagrada, do sidra novog dela).
        # Bilo koja DRUGA oznaka krivice van te rečenice i van dela o novom delu („Jedno od tih dela je bilo iz nehata.“,
        # „Krađu je izvršio sa umišljajem.“ bez sidra) — ako se ne slaže, ili ako rečenica osude krivicu ne kaže — NEPOZNATO.
        _p = m_osude.start() if m_osude else 0
        _poc = max(max(q.rfind(x, 0, _p) for x in (". ", "; ", "? ", "! ")) + 2, 0)
        _kraj = min([i for i in (q.find(x, _p) for x in (". ", "; ", "? ", "! ")) if i >= 0]
                    + ([granica] if granica is not None and granica > _p else []) or [len(q)])
        ranija_krivica = re.sub(
            rf"\b{_NOVO_DELO_U_INTERVALU}\b", lambda m: " " * len(m[0]), ranije
        )
        kriv = _krivica(re.sub(_RASPON + "|" + _SAMO_DO, " ", ranija_krivica[_poc:_kraj]))
        _ostalo = ranija_krivica[:_poc] + " " + ranija_krivica[_kraj:]
        _sa_krivicom = [s for s in re.split(r"[.;?!](?:\s|$)", _ostalo) if re.search(r"umisljaj\w*|nehat\w*", s)]
        _o_ranijim = [s for s in _sa_krivicom if re.search(r"\b(?:oba|obe|ranij\w*|te\s+osud\w*|osudj\w*)\b", s)]
        _drugo = [s for s in _sa_krivicom if s not in _o_ranijim]
        _k_ranije = _krivica(" ".join(_o_ranijim)) if _o_ranijim else None
        if kriv is None:
            # „Oba dela su učinjena sa umišljajem.“ — samo rečenica koja IZRIČITO govori o ranijim delima, i nijedna druga
            kriv = _k_ranije if (_o_ranijim and not _drugo) else None
        elif (_o_ranijim and _k_ranije != kriv) or any(_krivica(s) != kriv for s in _drugo):
            kriv = None
        seg = re.sub(r"\([^)]*\)", " ", seg)
        po = (re.search(r"zatvor\w*\s+od\s+po\s+(" + _DUR + ")", seg)
              or re.search(r"\bna\s+po\s+(" + _DUR + r")\s+zatvor\w*\b", q[_poc:_kraj]))
        par = re.search(r"zatvor\w*\s+od\s+(\w+)\s+i\s+(\w+)\s+(" + _JED_TXT + ")", seg)
        pojedinacno = [x for x in re.findall(r"zatvor\w*\s+od\s+(" + _DUR + ")", seg) if not x.startswith("po ")]
        trajanja: Optional[list] = None
        if po and _dur_dana(po.group(1)) is not None:
            trajanja = [_dur_dana(po.group(1))] * broj
        elif par and broj == 2 and _broj(par.group(1)) is not None and _broj(par.group(2)) is not None:
            j = _jedinica_dana(par.group(3))
            trajanja = [_broj(par.group(1)) * j, _broj(par.group(2)) * j]
        elif len(pojedinacno) == broj and all(_dur_dana(x) is not None for x in pojedinacno):
            trajanja = [_dur_dana(x) for x in pojedinacno]
        if uslovno:
            trajanja = None
        if re.search(_POSEBNA_OSUDA, q):
            kriv, trajanja = None, None
            napomene.append("Pitanje pominje brisanu osudu, maloletnički zatvor ili zamenu kazne — da li se takva osuda računa "
                            "za čl. 55a nije rešeno izvorom u bazi; uslov o ranijim osudama ostaje nepoznat.")
        out["ranije_osude"] = [RanijaOsuda(kriv, (t // _DANA_U_MESECU) if t is not None else None)
                               for t in (trajanja or [None] * broj)]

    # otpust: tačno jedan pomen; datumi (novo delo posle otpusta) ili „pre N“
    pomeni = re.findall(r"otpust\w*", q)
    recenica_otpusta = next((x for x in re.split(r"(?<=[.;?!])\s+", q) if "otpust" in x), "")
    mo_poz = re.search(r"otpust\w*", q)
    # datumi od pomena otpusta do kraja te rečenice (datum presude ispred otpusta se ne broji)
    kraj_rec = re.search(r"[.;?!](?:\s|$)", q[mo_poz.start():]) if mo_poz else None
    # … i samo do sidra novog dela („…, a novo delo izvršio je 15.01.2025“ nije drugi datum otpusta)
    kraj_sidro = re.search(_SIDRO_NOVOG, q[mo_poz.start():]) if mo_poz else None
    kraj = min(x.start() for x in (kraj_rec, kraj_sidro) if x) if (kraj_rec or kraj_sidro) else 70
    datumi_uz_otpust = len(re.findall(_DATUM, q[mo_poz.start(): mo_poz.start() + kraj])) if mo_poz else 0
    vise_vremena = len(re.findall(r"\bpre\s+(?:vise\s+od\s+)?" + _DUR, recenica_otpusta)) + datumi_uz_otpust > 1
    if len(pomeni) == 1 and vise_vremena:
        napomene.append("Uz otpust je navedeno više vremena (npr. za više kazni) — za uslov od pet godina potreban je jedan datum.")
    if len(pomeni) == 1 and not uslovno and not vise_vremena:
        mo = re.search(r"otpust\w*[^.]{0,60}?" + _DATUM, q)
        mn_ = _datum_novog_dela(q, granica)
        datum_dela = None
        try:
            if mn_:
                datum_dela = date(int(mn_.group(3)), int(mn_.group(2)), int(mn_.group(1)))
            if mo and datum_dela:
                o = date(int(mo.group(3)), int(mo.group(2)), int(mo.group(1)))
                if datum_dela > o:
                    out["otpust"], out["novo_delo"] = o, datum_dela
        except ValueError:
            pass
        if not out["otpust"] and not mo:
            mp = (re.search(r"otpust\w*[^.,;]{0,40}?\bpre\s+(vise\s+od\s+)?(" + _DUR + ")", q)
                  or re.search(r"\bpre\s+(vise\s+od\s+)?(" + _DUR + r")\s+(?:je\s+)?(?:bio\s+)?otpust", q))
            # Cela izjavna klauza mora dati jedan interval od otpusta do novog dela.
            # Negacije, hipoteze i alternative nisu činjenični navodi.
            interval = re.fullmatch(
                r"od\s+(?:dana\s+)?(?:poslednj\w*\s+)?otpust\w*"
                r"(?:\s+iz\s+(?:zavoda|zatvora)|\s+sa\s+izdrzavanja\s+kazne)?"
                rf"\s+{_NOVO_DELO_U_INTERVALU}"
                r"\s+(?:prosl\w*\s+su|protek\w*\s+je)\s+(?P<trajanje>" + _DUR + r")",
                recenica_otpusta.strip().removesuffix("."),
            )
            if not mp and interval and not druga_osoba:
                dani = _dur_dana(interval["trajanje"])
                if dani is not None:
                    out["proteklo_od_otpusta_meseci"] = dani / _DANA_U_MESECU
                    krivica_intervala = _krivica(interval["krivica"] or "")
                    if krivica_intervala is not None:
                        if not re.search(r"umisljaj|nehat", novo):
                            out["novo_delo_umisljaj"] = krivica_intervala
                        elif out["novo_delo_umisljaj"] != krivica_intervala:
                            out["novo_delo_umisljaj"] = None
                    # Poznat datum izvršenja određuje verziju zakona i kada je otpust dat samo intervalom.
                    if datum_dela and _SAMOSTALAN_DATUM_NOVOG_DELA.search(q):
                        out["novo_delo"] = datum_dela
            # bez sidra novog dela — tekst posle rečenice o otpustu („Prošle godine je izvršio …“)
            _posle = q[mo_poz.start():] if mo_poz else ""          # 4. krug: i ostatak rečenice o otpustu („…, a krađu je izvršio 2022.“)
            # 3. krug revizije: ceo tekst posle rečenice o otpustu („Otpušten je pre 6 g. Krađu je izvršio pre 4 g. Sada …“)
            if mp and _dur_dana(mp.group(2)) is not None and not _novo_delo_ima_svoje_vreme(novo + " " + _posle):
                meseci = _dur_dana(mp.group(2)) / _DANA_U_MESECU
                if not mp.group(1):
                    out["proteklo_od_otpusta_meseci"] = meseci
                elif meseci >= 60:                                            # „pre više od pet godina“
                    out["proteklo_od_otpusta_meseci"] = 67.0
    elif len(pomeni) > 1:
        napomene.append("Otpust se pominje više puta — za uslov od pet godina potreban je jedan datum otpusta sa izdržavanja kazne.")
    pravnosnaznost = None if druga_osoba else _pravnosnaznost_iz_navoda(q, broj)
    if pravnosnaznost is None and any(v is not None and v is not False for v in out.values()):
        if strana_osuda or out["novo_delo"] is None or out["novo_delo"] >= POCETAK_PRIMENE_63_2026:
            pravnosnaznost = NEPOZNATO
    out["pravnosnaznost"] = pravnosnaznost
    return out, napomene


def _pravnosnaznost_iz_navoda(pitanje: str, broj_osuda: Optional[int]) -> Optional[str]:
    """Nedostatak ili spor izričito naveden u pitanju ne može dati kategorično DA."""
    ishodi = set()
    for rec in re.split(r"(?<=[.?!;])\s+", _norm(pitanje)):
        if not (re.search(r"\b(?:ne)?pravn?osnazn\w*", rec) and re.search(r"\b(?:presud|osud)\w*", rec)):
            continue
        if not re.search(r"\b(?:ranij\w*|prethodn\w*|obe|obje|prv[aeu]|drug[aeu]|nijedn\w*)\b", rec):
            continue
        if rec.endswith("?") or re.search(r"\b(?:da li|nije jasno|nije poznato|nije tacno|ne zna se|nejasn\w*|"
                                          r"sporn\w*|osporav\w*|navodn\w*|tvrd\w*|mozda|verovatn\w*|"
                                          r"ako|ukoliko|pod uslovom|u slucaju da|pretpostav\w*)\b", rec):
            return NEPOZNATO
        negativno = re.search(r"\b(?:nepravn?osnazn\w*|(?:nije|nisu)\s+(?:jos\s+)?(?:bil[aeo]\s+)?"
                              r"(?:sve\s+)?pravn?osnazn\w*)", rec)
        obe = re.search(r"\b(?:obe|obje)\b", rec)
        nijedna = re.search(r"\bnijedn\w*\b", rec)
        samo_jedna = re.search(r"\bsamo\s+(?:jedn[aeu]|prv[aeu]|drug[aeu])\b[^,.]{0,65}\bje\s+pravn?osnazn\w*", rec)
        if samo_jedna or (negativno and (nijedna or (obe and broj_osuda == 2))):
            ishodi.add(NE)
        elif negativno:
            ishodi.add(NEPOZNATO)
        elif (re.search(r"\b(?:obe|obje|sve)\s+(?:ranij\w*|prethodn\w*)\s+(?:presud|osud)\w*\s+"
                        r"(?:su|jesu)\s+(?:(?:vec|bile|postale)\s+)?pravn?osnazne\b", rec)
              or (broj_osuda == 2
                  and re.search(r"\b(?:dva puta|dvaput)\b.{0,35}\bpravn?osnazno\s+osudj\w*", rec))):
            ishodi.add(DA)
    if NEPOZNATO in ishodi or len(ishodi) > 1:
        return NEPOZNATO
    return next(iter(ishodi), None)


_ISTOVRSNO_RE = re.compile(r"\bistovrsn\w*|\b(?:ista|isto)\s+(?:takv\w*\s+)?(?:krivicn\w*\s+)?del\w*")
_NEGACIJA_RE = re.compile(r"\b(?:ne|nije|nisu|ni|nema|nijedno|nikako)\b|\bneistovrsn")
_OGRADA_RE = re.compile(r"\bda\s+li\b|\bsva\b|\bsvi\b|\bsve\b|osporav|tvrd\w*|navodn|mozda|verovatn|sporn|ali\b|"
                        r"\bili\b|nejasn|nije\s+poznat|\b(?:ako|ukoliko|pretpostav\w*|hipotetic\w*|u\s+slucaju\s+da)\b")
_NAVOD_RE = re.compile(r'„[^“”]*[“”]|“[^”]*”|"[^"]*"|«[^»]*»|»[^«]*«')
_CISTA_NEGACIJA_RE = re.compile(r"^(?:\w+\s+){0,4}?(?:nisu|nije|ne\s+radi\s+se\s+o|nije\s+rec\s+o)\s+(?:bil[aio]\s+)?"
                                r"(?:ista|isto|istovrsn\w*)\b")


def _istovrsnost_iz_navoda(pitanje: str) -> Optional[bool]:
    """DA samo iz izjavne rečenice bez negacije i ograde („Ranija dela su istovrsna sa novim.“); NE samo iz čiste negacije
    („Ranija dela nisu istovrsna.“); pitanje, hipoteza, citat, delimičnost ili više nesaglasnih rečenica → None."""
    q = _norm(pitanje)
    if any(_ISTOVRSNO_RE.search(navod.group()) for navod in _NAVOD_RE.finditer(q)):
        return None
    ishodi = set()
    for rec in re.split(r"(?<=[.?!;])\s+", q):
        if not _ISTOVRSNO_RE.search(rec):
            continue
        if rec.rstrip().endswith("?") or _OGRADA_RE.search(rec):
            return None
        if _NEGACIJA_RE.search(rec):
            if not _CISTA_NEGACIJA_RE.search(re.sub(r"^\W+", "", rec)) and not re.search(r"\bneistovrsn", rec):
                return None
            ishodi.add(False)
        else:
            ishodi.add(True)
    return ishodi.pop() if len(ishodi) == 1 else None


def iz_pitanja(pitanje: str) -> dict:
    return analiza(pitanje)[0]


def je_pitanje_o_povratu(pitanje: str) -> bool:
    q = _norm(pitanje)
    if re.search(r"\b55\s?a\b|visestruk\w*\s+povrat|recidiv|povratni(?:k|ka|ku|kom|ci|cima)\b|(?:specijaln|opst)\w*\s+povrat", q):
        return True
    # „povrat“ (ne „povratak“) samo uz krivičnopravni kontekst odmeravanja — ne povrat novca, poreza, avansa, predmeta
    if re.search(r"\bpovrat(?:a|u|om)?\b", q) and re.search(r"osudj|otezavaj|odmer\w*\s+kazn|\bkz\b|krivicn\w*\s+zakonik|krivicn\w*\s+del", q):
        return True
    return bool((re.search(r"(?:ranije|dva\s+puta|dvaput|tri\s+puta|triput|\d{1,2}\s+puta)[^.]{0,40}osudj|osudj\w*[^.]{0,30}"
                           r"(?:dva|tri|\d{1,2})\s+puta|\b(?:dve|tri|cetiri|\d{1,2})\s+ranij\w*\s+osud", q))
                and re.search(r"raspon|kazn|odmer|zatvor", q))


def _kz_clanovi() -> set:
    from pathlib import Path
    try:
        t = (Path(__file__).resolve().parent.parent / "data" / "laws" / "pdfs" / "krivicni_zakonik.pdf").read_text(encoding="utf-8")
    except Exception:
        return set()
    return {m.lower() for m in re.findall(r"^Član (\d+[a-zA-Z]?)\s*$", t, re.M)}


def _nepostojeci_clanovi_kz(pitanje: str) -> list[str]:
    q = _norm(pitanje)
    if not re.search(r"\bkz\b|krivicn\w*\s+zakonik", q):
        return []
    postoje = _kz_clanovi()
    navedeni = re.findall(r"(?:clan\w*|cl\.)\s*(\d+[a-z]?)\b", q)
    return [n for n in navedeni if postoje and n not in postoje]


def _kazna_txt(dana: int) -> str:
    return "30 dana" if dana == OPSTI_MINIMUM_DANA else format_trajanje(dana)


def _prepoznato(c: dict) -> str:
    delovi = []
    if c["ranije_osude"]:
        opis = []
        for o in c["ranije_osude"]:
            k = {True: "umišljaj", False: "bez umišljaja", None: "krivica nepoznata"}[o.umisljaj]
            z = format_trajanje(o.zatvor_meseci * _DANA_U_MESECU) if o.zatvor_meseci is not None else "kazna nepoznata"
            opis.append(f"{z} ({k})")
        delovi.append("ranije osude: " + "; ".join(opis))
    if c["otpust"]:
        delovi.append(f"otpust {c['otpust']:%d.%m.%Y}, novo delo {c['novo_delo']:%d.%m.%Y}")
    elif c["proteklo_od_otpusta_meseci"] is not None:
        delovi.append(f"od otpusta oko {format_trajanje(int(c['proteklo_od_otpusta_meseci'] * _DANA_U_MESECU))}")
    if c["propisan_max_dana"]:
        od = "30 dana (opšti minimum)" if c["min_iz_opsteg_minimuma"] else _kazna_txt(c["propisan_min_dana"])
        delovi.append(f"propisano za novo delo: {od} do {format_trajanje(c['propisan_max_dana'])}")
    if c["novo_delo_umisljaj"] is not None:
        delovi.append("novo delo: " + ("umišljaj" if c["novo_delo_umisljaj"] else "bez umišljaja"))
    return "Prepoznato iz pitanja: " + ("; ".join(delovi) if delovi else "—") + ". Ako je nešto pogrešno prepoznato, proračun ne važi."


def blok(pitanje: str) -> Optional[tuple[str, Rezultat]]:
    """Deterministički blok za odgovor na pitanje o višestrukom povratu; None ako pitanje nije o povratu."""
    if not je_pitanje_o_povratu(pitanje):
        return None
    cinjenice, napomene_parsera = analiza(pitanje)
    r = izracunaj(**cinjenice)
    redovi = ["--- PRORAČUN: VIŠESTRUKI POVRAT (KZ čl. 55a — računa sistem, ne AI)"]
    for n in _nepostojeci_clanovi_kz(pitanje):
        redovi.append(f"Član {n} nije pronađen u lokalnom tekstu Krivičnog zakonika. Proverite vremenski merodavan tekst. "
                      "Višestruki povrat uređuje čl. 55a.")
    redovi.append(f"Izvor ({IZVOR_55A}): „{CITAT_55A}“")
    redovi.append(_NAPOMENA_BAZA)
    bez_cinjenica = all(v in (None, False) for v in cinjenice.values())
    if not bez_cinjenica:
        redovi.append(_prepoznato(cinjenice))
        redovi.append("Uslovi prema činjenicama iz pitanja:")
        for u in r.uslovi:
            redovi.append(f"[{u.stanje}] {u.oznaka} — {u.razlog}")
    redovi += napomene_parsera
    if bez_cinjenica:
        redovi.append("Posledica: kad su uslovi ispunjeni, sud mora izreći kaznu iznad polovine raspona propisane kazne, a najviše do "
                      "propisanog maksimuma (raspon propisane kazne se ne prekoračuje). Za proveru uslova i proračun raspona navedite: "
                      + "; ".join(r.nedostaje) + ".")
    elif r.primenjuje_se == DA:
        redovi.append("Zaključak: uslovi iz čl. 55a su ispunjeni — sud MORA izreći kaznu iznad polovine raspona propisane kazne.")
        if r.raspon:
            rs = r.raspon
            pravilo = ("čl. 45 st. 2: preko šest meseci kazna se izriče na pune godine i mesece" if rs["polovina_raspona_dana"] >= 180
                       else "čl. 45 st. 2: do šest meseci kazna se izriče i na dane")
            redovi.append(f"Propisana kazna: {_kazna_txt(rs['propisano_od_dana'])} do {format_trajanje(rs['propisano_do_dana'])} zatvora. "
                          f"Polovina raspona (sredina minimuma i maksimuma — vidi način računanja): "
                          f"{format_trajanje(int(rs['polovina_raspona_dana']))}.")
            redovi.append(f"Zakonski okvir po čl. 55a: više od {format_trajanje(int(rs['polovina_raspona_dana']), genitiv=True)}, najviše "
                          f"{format_trajanje(rs['najvisa_dana'])} zatvora; najniža takva kazna ({pravilo}): "
                          f"{format_trajanje(rs['najniza_dozvoljena_dana'])}.")
    elif r.primenjuje_se == NE:
        neispunjeni = [u.oznaka for u in r.uslovi if u.stanje == NE]
        tekst = "Zaključak: čl. 55a se NE primenjuje — nije ispunjeno: " + "; ".join(neispunjeni) + "."
        if not any(u.stanje == NE and u.oznaka.startswith("novo delo") for u in r.uslovi):
            tekst += " Ranija osuda i dalje može biti otežavajuća okolnost po čl. 55 (povrat), ako su ispunjeni njegovi uslovi."
        redovi.append(tekst)
    else:
        redovi.append("Zaključak: primena čl. 55a se ne može utvrditi bez sledećih činjenica: " + "; ".join(r.nedostaje) + ".")
        datum_dela = cinjenice.get("novo_delo")
        if cinjenice.get("propisan_max_dana") and (datum_dela is None or datum_dela >= POCETAK_PRIMENE_55A):
            mn = cinjenice.get("propisan_min_dana") or OPSTI_MINIMUM_DANA
            pol = mn + (cinjenice["propisan_max_dana"] - mn) / 2
            dodatak = " (najmanja mera nije propisana — opšti minimum 30 dana, čl. 45 st. 1)" if cinjenice.get("min_iz_opsteg_minimuma") else ""
            redovi.append(f"Ako se uslovi utvrde: kazna bi morala biti veća od {format_trajanje(int(pol), genitiv=True)}, najviše "
                          f"{format_trajanje(cinjenice['propisan_max_dana'])} zatvora{dodatak}.")
    if any(x.startswith(("Zakonski okvir po čl. 55a", "Ako se uslovi utvrde")) for x in redovi):
        # V4: zakon kaže samo „iznad polovine raspona propisane kazne“ — način računanja je tumačenje, ne tekst zakona
        redovi.append(_NAPOMENA_POLOVINA)
    if any(x.startswith("Zakonski okvir po čl. 55a") for x in redovi):
        redovi.append(_NAPOMENA_NAJNIZA)
    redovi += r.napomene
    redovi.append("Ovo je zakonski okvir, NE predviđanje kazne: konkretnu kaznu u tom okviru odmerava sud prema svim okolnostima (čl. 54).")
    redovi.append("Proverite i da li je neka ranija osuda brisana rehabilitacijom — tada se osuđeni smatra neosuđivanim (čl. 97 st. 1).")
    redovi.append("Otvoreno pitanje (nije rešeno izvorom u bazi, stav sudske prakse nije naveden): odnos čl. 55a prema ublažavanju kazne "
                  "(čl. 56–57) i koja se kazna uzima kao „izrečena kazna“ kad ih ima više.")
    return "\n".join(redovi), r
