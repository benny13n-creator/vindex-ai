# -*- coding: utf-8 -*-
"""
Vindex AI — shared/usvajanje_nacrta.py

MIR001 C3b FINAL CLOSURE TASK-01 — ugovor IZRIČITOG USVAJANJA: AI radni predlog → dokument za sud.

Granica odgovornosti (zadatak osnivača, „AI WORKING PROPOSAL → EXPLICIT HUMAN ADOPTION → COURT-FACING DOCUMENT“):

- AI RADNI PREDLOG (`staging_memory.tip = nacrt_iz_spisa`): tekst modela, ceo i nepromenljiv. Pri izradi server
  beleži snimak (`quality_detail.predlog`): stavke (pasusi) sa sha256, dokumente spisa i procesne tačke sa DOSLOVNIM
  izvodima kao kandidatima za proveru. Ništa u predlogu nije „potvrđeno“ — ni rečenica uz koju stoji tačan citat
  (izvod je ono što je model izabrao; da li podržava tvrdnju, server ne zna).
- DOKUMENT ZA SUD (`tip = dokument_za_sud`): poseban red. Tekst nastaje SAMO od (a) stavki koje je advokat izričito
  usvojio (server kopira tekst iz snimka predloga, po id-u i sha256) i (b) teksta koji je advokat sam napisao ili
  izmenio. Svaka od osam procesnih tačaka ima advokatovu odluku (potvrđeno / ispravljeno / nepoznato / nije
  primenljivo) — sistem je nikad ne popunjava. Odobrava se tačno određen tekst (sha256); DOCX izvozi samo taj tekst.
- Ljudsko usvajanje NIJE `SOURCE_VERIFIED`: zapis kaže ko je šta usvojio i kada, ne da je tvrdnja istinita.

Ovaj modul ne tumači tekst: nema detektora reči ni semantičkih pravila. Provere su strukturne (identitet stavke,
sha256, potpunost odluka, serverski natpisi i nerazrešena mesta, doslovna AI stavka koja nije usvojena).
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

TIP_PREDLOGA = "nacrt_iz_spisa"
TIP_DOKUMENTA_ZA_SUD = "dokument_za_sud"
STATUS_PREDLOGA = "AI_RADNI_PREDLOG"

# Osam procesnih tačaka koje advokat mora da razreši pre odobrenja (obuhvat iz zadatka osnivača, TASK-01).
TACKE = (
    ("OSNOVNI_ZAHTEV", "Osnovni iznos tužbenog zahteva"),
    ("DODATNI_ZAHTEV", "Dodatni (proširen ili preinačen) zahtev"),
    ("POVLACENJE_IZMENA", "Povlačenje ili izmena zahteva"),
    ("ODLUKE_SUDA", "Odluke suda i njihovo mesto u toku postupka"),
    ("NALOG", "Nalog suda za postupanje"),
    ("UPLATA", "Dokaz o uplati — ili da ga u raspoloživim spisima nema"),
    ("ROK", "Rok — poznat ili nepoznat"),
    ("NEDOSTAJUCI_DOKUMENT", "Nedostajući ili nečitljiv dokument"),
)
KLJUCEVI_TACAKA = tuple(k for k, _ in TACKE)
ODLUKE_TACKE = ("POTVRDJENO", "ISPRAVLJENO", "NEPOZNATO", "NIJE_PRIMENLJIVO")
ODLUKE_STAVKE = ("USVOJENO", "ODBACENO")
_MAKS_TEKST_TACKE = 2000
_MAKS_STAVKI = 200
_MIN_DOSLOVNO = 60                    # kraća AI stavka (zaglavlje, „S poštovanjem,“) se ne traži doslovno u tekstu

_RE_DOK = re.compile(r"\bDOK-\d{1,4}\b")
# GATE-R1 N1: svaki zapis interne oznake spisa — velikim slovima (latinica ili ćirilica) uz bilo koji razdvajač
# („DOK-05“, „DOK 05“, „ДОК‑05“, „DOK–05“, „DOK-00005“), ili bilo kojim slovima uz crticu („dok-06“). Mala slova bez
# crtice se ne broje: „dok 15 dana“ je srpska reč, ne oznaka.
_RE_OZNAKA = re.compile(r"(?<![\w])(?:(?:DOK|ДОК)[ \t\u00a0.\-\u2010-\u2015\u2212]*|(?i:dok|док)[\-\u2010-\u2015\u2212])0*(\d{1,5})(?!\d)")


def oznake_u(tekst: str) -> list:
    """Interne oznake spisa u tekstu, svedene na oblik spiska dokumenata („DOK-05“), bez ponavljanja, po broju."""
    return sorted({f"DOK-{int(n):02d}" for n in _RE_OZNAKA.findall(tekst or "")}, key=lambda x: int(x.split("-")[1]))
# Serverski natpisi i nerazrešena mesta koja ne smeju u odobren dokument za sud (strukturno, ne po smislu)
_ZABRANJENO = (
    (re.compile(r"═══ VINDEX — INTERNE NAPOMENE"), "granica internih napomena"),
    (re.compile(r"\[\s*izostavljeno\b", re.IGNORECASE), "nerazrešeno mesto [IZOSTAVLJENO …]"),
    (re.compile(r"\[PROVERITI\b", re.IGNORECASE), "nerazrešeno mesto [PROVERITI …]"),
    (re.compile(r"\[\[\s*PS-"), "nerazrešena oznaka procesnog stanja [[PS-…]]"),
    (re.compile(r"[⁣⁤]"), "nevidljiv serverski znak"),
    # MIR001 FINAL RELEASE R1: interna oznaka spisa (Vindex numeracija dokumenata) — sud je ne poznaje. Ne briše se iz
    # teksta (to bi bilo „čišćenje“); odobrenje i izvoz se zaustavljaju dok je advokat ne zameni.
    (_RE_OZNAKA, "internu oznaku spisa DOK-nn (Vindex numeracija; sud je ne poznaje) — zamenite je nazivom dokumenta"),
)
VERZIJA_UGOVORA = 2               # 2 = stavka nosi `tekst_za_dokument` (R1); snimak 1 se više ne usvaja


def sha(tekst: str) -> str:
    return hashlib.sha256((tekst or "").encode("utf-8")).hexdigest()


def _norm(t: str) -> str:
    return " ".join((t or "").split())


def stavke(tekst: str) -> list:
    """Predlog → stavke (pasusi odvojeni praznim redom; tekst bez praznih redova → redovi). Strukturno, bez tumačenja."""
    delovi = [d.strip() for d in re.split(r"\n[ \t]*\n", (tekst or "").strip()) if d.strip()]
    if len(delovi) == 1 and "\n" in delovi[0]:
        delovi = [r.strip() for r in delovi[0].split("\n") if r.strip()]
    out = []
    for i, d in enumerate(delovi[:_MAKS_STAVKI], start=1):
        out.append({"id": f"S-{i:02d}", "tekst": d, "sha256": sha(d), "izvori": oznake_u(d),
                    "status": STATUS_PREDLOGA})
    return out


def _kandidat(d: dict) -> dict:
    return {"ps": d["id"], "oznaka": d["oznaka"], "dokument_id": d.get("dokument_id"),
            "izvod": " ".join((d.get("izvod") or "").split()), "akter_po_tekstu": d.get("akter"),
            "vrsta_kandidat": d.get("vrsta"), "nije_utvrdjeno": list(d.get("nepoznato") or []),
            "kasnije": [f"{k['oznaka']} {k['vrsta'].lower()} ({k['odnos'].lower()}, dejstvo NEUTVRĐENO)"
                        for k in d.get("kasniji") or []]}


def procesne_tacke(stanje: Optional[dict], dokumenti: list) -> list:
    """Osam tačaka sa KANDIDATIMA iz serverskog procesnog stanja (doslovni izvodi; vrsta i akter su kandidati,
    značenje i važenje nisu utvrđeni). Raspored po vrsti događaja je samo pomoć za pronalaženje izvora — ne tvrdnja."""
    dog = list((stanje or {}).get("dogadjaji") or [])

    def vrsta_s(d):
        return (d.get("kandidati") or [d["vrsta"]])[0] if d["vrsta"] == "STRANKA_U_SUDSKOM_DOKUMENTU" else d["vrsta"]
    po = {
        "OSNOVNI_ZAHTEV": [], "DODATNI_ZAHTEV": [],
        "POVLACENJE_IZMENA": [d for d in dog if vrsta_s(d) == "STRANKA_ODUSTAJE"],
        "ODLUKE_SUDA": [d for d in dog if d.get("akter") == "SUD"],
        "NALOG": [d for d in dog if "izvrsenje" in d],
        "UPLATA": [d for d in dog if "uplata" in d or vrsta_s(d) == "STRANKA_NAVODI_IZVRSENJE"],
        "ROK": [d for d in dog if "rok" in d],
        "NEDOSTAJUCI_DOKUMENT": [],
    }
    nedostaje = [x for x in dokumenti if x.get("stanje") != "PROCITAN"]
    pomoc = {
        "OSNOVNI_ZAHTEV": "Sistem ne izdvaja iznose zahteva. Proverite tužbu i podneske stranaka.",
        "DODATNI_ZAHTEV": "Sistem ne izdvaja dodatni, proširen ni preinačen zahtev. Proverite podneske stranaka.",
        "NEDOSTAJUCI_DOKUMENT": ("Dokumenti koji nisu (potpuno) pročitani: "
                                 + ", ".join(f"{x['oznaka']} ({x.get('stanje', '').lower()})" for x in nedostaje)
                                 if nedostaje else "Sistem nije zabeležio nepročitan dokument; to ne znači da u spisu "
                                                   "ne nedostaje dokument."),
    }
    return [{"kljuc": k, "naziv": naziv, "kandidati": [_kandidat(d) for d in po[k][:20]],
             "pomoc": pomoc.get(k, "")} for k, naziv in TACKE]


def snimak_predloga(tekst_predloga: str, stanje: Optional[dict], dokumenti: list,
                    tekst_za_dokument: Optional[str] = None) -> dict:
    """Zapis AI radnog predloga u trenutku izrade (`staging_memory.quality_detail.predlog`). Svaka stavka nosi `tekst`
    (za pregled: izvod sa oznakom DOK-nn) i `tekst_za_dokument` (ono što usvajanje unosi u dokument za sud: isti tekst,
    izvod bez interne oznake spisa — R1). Obe verzije nastaju iz istog teksta modela, pa imaju iste stavke."""
    sv = stavke(tekst_predloga)
    zd = stavke(tekst_za_dokument if tekst_za_dokument is not None else tekst_predloga)
    if len(zd) != len(sv):                       # odbrana u dubini: bez poklapanja nema verzije za dokument
        raise ValueError("stavke predloga i teksta za dokument se ne poklapaju")
    for s, z in zip(sv, zd):
        s["tekst_za_dokument"], s["sha256_za_dokument"] = z["tekst"], z["sha256"]
    return {"verzija_ugovora": VERZIJA_UGOVORA, "status_teksta": STATUS_PREDLOGA, "sha256": sha(tekst_predloga),
            "stavke": sv, "dokumenti": dokumenti,
            "procesne_tacke": procesne_tacke(stanje, dokumenti),
            "nije_utvrdjeno": list((stanje or {}).get("nepoznato") or [])[:60],
            "potpunost": (stanje or {}).get("potpunost") or "NEPOZNATO"}


def proveri_odluku_tacke(kljuc: str, o: dict, poznati_dokumenti: set) -> Optional[str]:
    """None ako je odluka advokata o tački ispravna, inače razlog."""
    if kljuc not in KLJUCEVI_TACAKA:
        return f"nepoznata procesna tačka {kljuc!r}"
    if not isinstance(o, dict) or o.get("odluka") not in ODLUKE_TACKE:
        return f"{kljuc}: odluka mora biti jedna od {', '.join(ODLUKE_TACKE)}"
    tekst = o.get("tekst") if isinstance(o.get("tekst"), str) else ""
    if len(tekst) > _MAKS_TEKST_TACKE:
        return f"{kljuc}: opis je duži od {_MAKS_TEKST_TACKE} znakova"
    if o["odluka"] in ("POTVRDJENO", "ISPRAVLJENO") and not tekst.strip():
        return f"{kljuc}: uz „potvrđeno“ ili „ispravljeno“ upišite stanje kako ga vi utvrđujete"
    izvori = o.get("izvori") or []
    if not isinstance(izvori, list) or any(not isinstance(x, str) or x not in poznati_dokumenti for x in izvori):
        return f"{kljuc}: izvor mora biti dokument ovog spisa"
    return None


def nedozvoljen_sadrzaj(tekst: str) -> list:
    """Serverski natpisi i nerazrešena mesta u tekstu (strukturno, ne po smislu) — ne smeju u dokument za sud."""
    return [f"Tekst sadrži {opis}." for rx, opis in _ZABRANJENO if rx.search(tekst or "")]


def _oblici(s: dict) -> list:
    return [x for x in (s.get("tekst"), s.get("tekst_za_dokument")) if x]


def razlozi_protiv_odobrenja(tekst: str, usvajanje: dict, predlog: dict) -> list:
    """Strukturni razlozi zbog kojih se dokument za sud NE sme odobriti (prazno = sme)."""
    r = []
    if not (tekst or "").strip():
        r.append("Dokument za sud je prazan.")
    r += nedozvoljen_sadrzaj(tekst)
    nazivi = {d.get("oznaka"): d.get("naziv") or "" for d in predlog.get("dokumenti") or []}
    oznake = oznake_u(tekst)
    if oznake:
        r.append("Interne oznake u tekstu: " + "; ".join(f"{o} = {nazivi.get(o) or 'dokument spisa'}" for o in oznake) + ".")
    tacke = usvajanje.get("procesne_tacke") or {}
    fale = [naziv for k, naziv in TACKE if (tacke.get(k) or {}).get("odluka") not in ODLUKE_TACKE]
    if fale:
        r.append("Procesne tačke bez vaše odluke: " + "; ".join(fale) + ".")
    usvojene = {x["id"] for x in usvajanje.get("stavke") or [] if x.get("odluka") == "USVOJENO"}
    t = _norm(tekst)
    for s in predlog.get("stavke") or []:
        if s["id"] not in usvojene and any(len(_norm(x)) >= _MIN_DOSLOVNO and _norm(x) in t for x in _oblici(s)):
            r.append(f"Tekst doslovno sadrži AI stavku {s['id']} koju niste usvojili — usvojite je ili je izmenite.")
    return r


def stanje_stavki(tekst: str, usvajanje: dict, predlog: dict) -> list:
    """Za prikaz: svaka AI stavka — odluka advokata i da li je usvojeni tekst i dalje doslovno u dokumentu."""
    zapis = {x["id"]: x for x in usvajanje.get("stavke") or []}
    t = _norm(tekst)
    out = []
    for s in predlog.get("stavke") or []:
        z = zapis.get(s["id"]) or {}
        ut = _norm(s.get("tekst_za_dokument") or s["tekst"])
        out.append({"id": s["id"], "odluka": z.get("odluka"), "u_tekstu_doslovno": bool(ut) and ut in t})
    return out
