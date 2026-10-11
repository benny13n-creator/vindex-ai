# -*- coding: utf-8 -*-
"""
Vindex AI — shared/genome_contract.py

NS006 Task 3 — PROFESIONALNI UGOVOR ŽIVOG PREDMETA (čitanje, aditivno).

## Šta je ovo

Čista funkcija koja od VEĆ UČITANIH izvora (predmet, `predmeti.case_dna`, dokumenti,
tvrdnje) sastavlja jedan stabilan V2 ugovor predmeta. Ne piše ništa, ne zove model,
ne dohvata ništa sama. Vlasnik Genome-a ostaje `routers/case_dna.py`; ovo je njegov
pomoćnik za čitanje, kao `shared/genome_validator.py` za proveru.

## Granica sirove analize i pouzdanog ugovora (Task 3A)

`predmeti.case_dna` je SIROV izlaz modela (uz backend-računate dodatke). Ugovor ga ne
prepisuje u celini: uzima samo poznata polja, a svaka stavka nosi klasu porekla.
Ništa iz `case_dna` ne postaje `SOURCE_FACT` ni `HUMAN_CONFIRMED` — model je model.

Reference se razrešavaju ZATVORENO:
  * `DOK-NN` važi samo ako tačno jedan dokument OVOG predmeta ima `redni_broj` NN;
  * `dokument_id` koji je Genome upisao važi samo ako je i sada dokument ovog predmeta;
  * `CLAIM-NNN` oznake iz `case_dna.kontradikcije[].claim_refs` se NE razrešavaju pri
    čitanju: katalog je efemeran (shared/claim_catalog.py — oznaka nije identitet i
    pomera se kad se doda tvrdnja). Trajni identitet tvrdnji nose samo perzistirane V2
    kontradikcije (Task 5).
Nerazrešeno = `None` + zapis u `nesigurnost`. Nikad najbliži dokument, nikad po nazivu.

Neispravan datum ili vrednost van dozvoljenog skupa → vrednost se obara (`None` /
neutralna) i to se beleži. Neispravna SAVETODAVNA sekcija ne obara ceo ugovor.

## Pravni izvori (Task 3B)

U kodu NE postoji mehanizam koji potvrđuje par (zakon, član) kao važeći izvor prava
(`analiza/validator.py::validate_law_refs` proverava samo naziv zakona;
`services/quality_gate.py::_verify_citation` samo da li neki „Član N" postoji u
korpusu, bez obzira na zakon). Zato je svaki pravni osnov iz Genome-a
`UNVERIFIED_AI_ANALYSIS`, a lista potvrđenih izvora je prazna sa navedenim razlogom.

## Brojevi (Task 3C)

Stara brojčana polja se ne brišu. Ugovor ih KLASIFIKUJE (deterministic / model_derived /
mixed / unknown) i nijedan ne naziva verovatnoćom ishoda.
"""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import date
from typing import Any, Iterable, Optional

SCHEMA_VERSION = "pg-1"

# ── Klase porekla (Task 8 iz mandata) ──────────────────────────────────────────
SOURCE_FACT = "SOURCE_FACT"
HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"
AI_ANALYSIS = "AI_ANALYSIS"
UNKNOWN = "UNKNOWN"
KLASE_POREKLA = (SOURCE_FACT, HUMAN_CONFIRMED, DETERMINISTIC_DERIVATION, AI_ANALYSIS, UNKNOWN)

UNVERIFIED_AI_ANALYSIS = "UNVERIFIED_AI_ANALYSIS"

# ── Stanje sekcije ────────────────────────────────────────────────────────────
OK = "OK"
PRAZNO = "EMPTY"            # izvor pročitan, nema ničega
NEPOZNATO = "UNKNOWN"       # izvor ne postoji (npr. Genome nikad izračunat)
DEGRADIRANO = "DEGRADED"    # izvor NIJE pročitan (greška) — nikad se ne prikazuje kao prazno
NEISPRAVNO = "INVALID"      # izvor pročitan, oblik neupotrebljiv

# ── Klase metrika (Task 3C) ──────────────────────────────────────────────────
DETERMINISTIC = "deterministic"
MODEL_DERIVED = "model_derived"
MIXED = "mixed"
METRIKA_NEPOZNATA = "unknown"

_ULOGE = {"tuzilac", "tuzeni", "svedok", "vestak", "zastupnik", "ostalo"}
_ZNACAJ = {"kriticno", "bitno", "informativno"}
_HITNOST = {"kriticno", "vazno", "pozeljno"}
_DOK = re.compile(r"\bDOK-0*(\d+)\b(?:\s*str\.?\s*(\S+))?", re.IGNORECASE)

# ── Ključ tvrdnje i dokumenta ─────────────────────────────────────────────────


def _tekst(v: Any, maks: int = 4000) -> Optional[str]:
    if not isinstance(v, str):
        return None
    s = v.strip()
    return s[:maks] if s else None


def kljuc_sadrzaja(sekcija: str, *delovi: Any) -> str:
    """Identitet stavke KOJA NEMA izvorni identitet (stavke modela): heš normalizovanog
    sadržaja. Isti sadržaj → isti ključ; preformulisan sadržaj → nov ključ (to je
    istina: tekst se promenio). Nikad se ne predstavlja kao identitet izvora —
    `id_vrsta` je uvek `sadrzaj`."""
    norm = "|".join(re.sub(r"\s+", " ", str(d or "")).strip().lower() for d in delovi)
    return "ai:" + hashlib.sha256(f"{sekcija}|{norm}".encode("utf-8")).hexdigest()[:16]


class Razresavac:
    """Zatvoreno razrešavanje referenci na dokumente JEDNOG predmeta."""

    def __init__(self, dokumenti: Iterable[dict]):
        self.po_id: dict[str, dict] = {}
        po_rb: dict[int, list[str]] = {}
        for d in dokumenti or []:
            if not isinstance(d, dict) or not d.get("id"):
                continue
            self.po_id[str(d["id"])] = d
            rb = d.get("redni_broj")
            if str(rb or "").isdigit():
                po_rb.setdefault(int(rb), []).append(str(d["id"]))
        self.po_rb = po_rb
        self.nerazreseno: list[dict] = []

    def dokument_id(self, vrednost: Any, polje: str) -> Optional[str]:
        """Postojeći `dokument_id` (Genome ga je razrešio pri upisu) važi samo ako je i
        SADA dokument ovog predmeta."""
        if vrednost in (None, ""):
            return None
        if str(vrednost) in self.po_id:
            return str(vrednost)
        self.nerazreseno.append({"polje": polje, "razlog": "dokument nije deo ovog predmeta (obrisan ili tuđ)"})
        return None

    def lokacija(self, tekst: Any, polje: str) -> dict:
        """`"DOK-NN str.X"` → `{dokument_id, strana_po_analizi, oznaka}`. Strana je ono što je
        model naveo (NIJE proverena — zato i ime polja), i to samo ako je ceo broj."""
        oznaka = _tekst(tekst, 200)
        if not oznaka:
            return {"dokument_id": None, "strana_po_analizi": None, "oznaka": None}
        m = _DOK.search(oznaka)
        if not m:
            self.nerazreseno.append({"polje": polje, "razlog": "lokacija bez DOK-NN oznake"})
            return {"dokument_id": None, "strana_po_analizi": None, "oznaka": oznaka}
        kandidati = self.po_rb.get(int(m.group(1)), [])
        if len(kandidati) != 1:
            self.nerazreseno.append({"polje": polje, "razlog": f"DOK-{int(m.group(1)):02d} ne odgovara tačno jednom dokumentu ovog predmeta"})
        strana = m.group(2)
        strana_br = int(strana) if strana and strana.rstrip(".,;").isdigit() and int(strana.rstrip(".,;")) > 0 else None
        return {"dokument_id": kandidati[0] if len(kandidati) == 1 else None,
                "strana_po_analizi": strana_br, "oznaka": oznaka}


def _datum(v: Any) -> Optional[str]:
    s = _tekst(v, 40)
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10]).isoformat() if len(s) >= 10 else None
    except ValueError:
        return None


def _stavka(sekcija: str, poreklo: str, vrednost: Any, *, id_: Optional[str] = None, **dodatno) -> dict:
    out = {"id": id_ or kljuc_sadrzaja(sekcija, vrednost), "id_vrsta": "izvor" if id_ else "sadrzaj",
           "poreklo": poreklo, "vrednost": vrednost}
    out.update(dodatno)
    return out


def _sekcija(stanje: str, stavke: Optional[list] = None, **dodatno) -> dict:
    out = {"stanje": stanje, "stavke": stavke or []}
    out.update(dodatno)
    return out


# ── Klasifikacija porekla tvrdnje ─────────────────────────────────────────────

# Jedan vlasnik vokabulara: jedini pisac kolone (migracija 135).
from shared.evidence_write import IZVOR_TVRDNJE_AI, IZVOR_TVRDNJE_COVEK  # noqa: E402


def poreklo_tvrdnje(red: dict) -> tuple[str, str]:
    """(klasa porekla, obrazloženje) za jedan red `predmet_dokazi`.

    Redosled je bitan i namerno strog:
      1. `izvor_tvrdnje = covek` (migracija 135)                  → HUMAN_CONFIRMED
      2. `izvor_snage = covek` (migracija 118): jedini pisac te
         vrednosti je ručni unos bez izvornog dokumenta              → HUMAN_CONFIRMED
      3. tvrdnja je pronađena u tekstu svog dokumenta
         (`nacin_pronalaska` egzaktan/normalizovan, `dokument_id`)  → SOURCE_FACT
      4. `izvor_tvrdnje = ai_klasifikacija`, nije pronađena         → AI_ANALYSIS
      5. ništa od navedenog (stari redovi)                           → UNKNOWN
    """
    izv = (red.get("izvor_tvrdnje") or "").strip()
    if izv == IZVOR_TVRDNJE_COVEK:
        return HUMAN_CONFIRMED, "uneo advokat"
    if (red.get("izvor_snage") or "") == "covek":
        return HUMAN_CONFIRMED, "uneo advokat (sa sopstvenom procenom snage)"
    if red.get("dokument_id") and red.get("nacin_pronalaska") in ("egzaktan", "normalizovan"):
        return SOURCE_FACT, "pronađeno u tekstu izvornog dokumenta"
    if izv == IZVOR_TVRDNJE_AI:
        return AI_ANALYSIS, "izvukao model; u tekstu dokumenta nije pronađeno"
    return UNKNOWN, "poreklo nije zabeleženo"


def tvrdnja_u_stavku(red: dict, raz: Razresavac) -> dict:
    poreklo, zasto = poreklo_tvrdnje(red)
    dok_id = raz.dokument_id(red.get("dokument_id"), "tvrdnja.dokument_id") if red.get("dokument_id") else None
    lokacija = None
    if dok_id and red.get("start_offset") is not None:
        # `stranica` je PROCENA (shared/evidence_write.py::lociraj_tvrdnju: offset // 2500 + 1),
        # ne stvarna strana dokumenta — zato se tako i zove.
        lokacija = {"dokument_id": dok_id, "strana_procena": red.get("stranica"), "paragraf": red.get("paragraf"),
                    "start": red.get("start_offset"), "kraj": red.get("end_offset"),
                    "nacin": red.get("nacin_pronalaska")}
    return _stavka("tvrdnja", poreklo, _tekst(red.get("tvrdnja")), id_=str(red["id"]),
                   obrazlozenje_porekla=zasto, kategorija=red.get("kategorija"),
                   pravni_element=_tekst(red.get("pravni_element"), 200),
                   dokument_id=dok_id, lokacija=lokacija,
                   snaga=red.get("snaga") if (red.get("izvor_snage") in ("covek", "dc005")) else None,
                   snaga_procenjena=red.get("izvor_snage") in ("covek", "dc005"),
                   identitet=red.get("identitet"), azurirano=red.get("created_at"))


# ── Metrike (Task 3C) ─────────────────────────────────────────────────────────

_NIJE_ISHOD = "analitička vrednost — NIJE verovatnoća ishoda ni predviđanje suda"


def klasifikuj_metrike(case_dna: dict) -> list[dict]:
    """Svaka postojeća brojčana vrednost iz Genome-a, sa klasom i značenjem."""
    g = case_dna or {}
    out: list[dict] = []

    def dodaj(kljuc, vrednost, klasa, znacenje, naziv):
        # `naziv` je ljudska oznaka sa SKALOM (NS006 Task 20): sam broj pored „snaga predmeta" se lako čita kao šansa.
        out.append({"kljuc": kljuc, "naziv": naziv, "vrednost": vrednost, "klasa": klasa, "znacenje": znacenje,
                    "napomena": _NIJE_ISHOD})

    if "snaga_predmeta_procent" in g:
        dodaj("snaga_predmeta_procent", g.get("snaga_predmeta_procent"), MIXED,
              "zbir uticaja faktora koje je naveo model, sabran pravilom u backend-u (compute_snaga_score)",
              "Snaga predmeta (analitička ocena, 0–100)")
    for k, v in sorted((g.get("heatmap") or {}).items()) if isinstance(g.get("heatmap"), dict) else []:
        dodaj(f"heatmap.{k}", v, MODEL_DERIVED, "ocena dimenzije koju je dao model (0–100)",
              f"Dimenzija „{str(k).replace('_', ' ')}“ (ocena modela, 0–100)")
    nt = g.get("najslabija_tacka")
    if isinstance(nt, dict) and "kriticnost" in nt:
        dodaj("najslabija_tacka.kriticnost", nt.get("kriticnost"), MODEL_DERIVED, "procena modela (0–100)",
              "Kritičnost najslabije tačke (ocena modela, 0–100)")
    for i, d in enumerate(g.get("dokazi_rang") or []):
        if isinstance(d, dict) and "snaga_score" in d:
            dodaj(f"dokazi_rang[{i}].snaga_score", d.get("snaga_score"), MODEL_DERIVED, "ocena dokumenta koju je dao model",
                  f"Ocena dokaza „{_tekst(d.get('naziv') or d.get('dokument'), 120) or str(i + 1)}“ (ocena modela)")
    if "genome_kompletnost" in g:
        dodaj("genome_kompletnost", g.get("genome_kompletnost"), MODEL_DERIVED, "samoprocena modela",
              "Kompletnost analize (samoprocena modela)")
    osnov = g.get("_analiza_osnov")
    if isinstance(osnov, dict):
        for k in ("dokumenata", "cinjenica", "pravnih_elemenata"):
            if k in osnov:
                dodaj(f"_analiza_osnov.{k}", osnov.get(k), DETERMINISTIC, "prebrojano iz baze u trenutku analize",
                      {"dokumenata": "Dokumenata u osnovu analize", "cinjenica": "Činjenica u osnovu analize",
                       "pravnih_elemenata": "Pravnih elemenata u osnovu analize"}[k])
    for k in ("_genome_docs_count", "_genome_docs_preskoceno"):
        if k in g:
            dodaj(k, g.get(k), DETERMINISTIC, "prebrojano pri sastavljanju analize",
                  {"_genome_docs_count": "Dokumenata u analizi", "_genome_docs_preskoceno": "Dokumenata preskočeno pri analizi"}[k])
    return out


# ── Sastavljanje ugovora ──────────────────────────────────────────────────────

def _strane(predmet: dict, g: dict, ima_genome: bool) -> dict:
    stavke = []
    for uloga in ("tuzilac", "tuzeni"):
        ime = _tekst(predmet.get(uloga), 300)
        if ime:
            stavke.append(_stavka("stranka.predmet", HUMAN_CONFIRMED, ime, id_=f"predmet:{uloga}",
                                  uloga=uloga, obrazlozenje_porekla="evidencija predmeta"))
    odbaceno = 0
    # NS006 Task 20: stranka koju je analiza samo PONOVILA (isto ime, ista uloga) nije druga stranka — prikazuje
    # se jednom, sa poreklom advokata, uz oznaku da se analiza slaže. Različita uloga ostaje vidljiva (neslaganje).
    def _kljuc(ime, uloga):
        return (" ".join(re.sub(r"[\"'„“”.,]", " ", ime or "").casefold().split()), uloga)
    ljudske = {_kljuc(x["vrednost"], x.get("uloga")): x for x in stavke}
    for s in (g.get("stranke") or []) if ima_genome else []:
        if not isinstance(s, dict) or not _tekst(s.get("ime"), 300):
            odbaceno += 1
            continue
        uloga = (s.get("uloga") or "").strip().lower()
        isti = ljudske.get(_kljuc(_tekst(s.get("ime"), 300), uloga))
        if isti is not None:
            isti["potvrdjeno_analizom"] = True
            continue
        stavke.append(_stavka("stranka.genome", AI_ANALYSIS, _tekst(s.get("ime"), 300),
                              uloga=uloga if uloga in _ULOGE else None,
                              uloga_neispravna=uloga not in _ULOGE))
    if not stavke:
        return _sekcija(PRAZNO if ima_genome else NEPOZNATO, odbaceno=odbaceno)
    return _sekcija(OK, stavke, odbaceno=odbaceno)


def _pravna_pitanja(g: dict, ima_genome: bool) -> dict:
    if not ima_genome:
        return _sekcija(NEPOZNATO, potvrdjeni_pravni_izvori=[], potvrda_izvora=_bez_potvrde())
    pt = g.get("pravna_teorija")
    if pt is not None and not isinstance(pt, dict):
        return _sekcija(NEISPRAVNO, potvrdjeni_pravni_izvori=[], potvrda_izvora=_bez_potvrde())
    pt = pt or {}
    stavke = []
    for polje, naslov in (("sustina_spora", "Suština spora"), ("osnov_odgovornosti", "Osnov odgovornosti"),
                          ("uzrocna_veza", "Uzročna veza"), ("visina_stete", "Visina štete")):
        v = _tekst(pt.get(polje), 2000)
        if v:
            stavke.append(_stavka(f"pitanje.{polje}", AI_ANALYSIS, v, vrsta=polje, naslov=naslov))
    osnovi = []
    zakoni = pt.get("relevantni_zakoni") or []
    if isinstance(zakoni, list):
        from analiza.validator import validate_law_refs
        from shared.genome_validator import _validate_clan_brojevi
        tekstovi = [z for z in (_tekst(x, 300) for x in zakoni) if z]
        prepoznati = {f.get("law_ref"): not f.get("unverified_law_ref")
                      for f in validate_law_refs({"findings": [{"law_ref": t} for t in tekstovi]}).get("findings", [])}
        tvrdo, _ = _validate_clan_brojevi({"pravna_teorija": {"relevantni_zakoni": tekstovi}})
        nemoguci = {f.get("stavka") for f in tvrdo}
        for t in tekstovi:
            osnovi.append(_stavka("pravni_osnov", AI_ANALYSIS, t, poverenje=UNVERIFIED_AI_ANALYSIS,
                                  naziv_zakona_prepoznat=bool(prepoznati.get(t)),
                                  broj_clana_moguc=t not in nemoguci))
    return _sekcija(OK if (stavke or osnovi) else PRAZNO, stavke, pravni_osnovi_neprovereni=osnovi,
                    potvrdjeni_pravni_izvori=[], potvrda_izvora=_bez_potvrde())


def _bez_potvrde() -> dict:
    return {"stanje": "NIJE_DOSTUPNA",
            "razlog": "U sistemu ne postoji provera koja par (zakon, član) potvrđuje kao važeći izvor; "
                      "pravni osnovi iz analize su predlozi modela, ne potvrđeno pravo."}


def _hronologija(g: dict, ima_genome: bool) -> dict:
    if not ima_genome:
        return _sekcija(NEPOZNATO)
    stavke, neispravni = [], 0
    for d in g.get("datumi_kljucni") or []:
        if not isinstance(d, dict) or not _tekst(d.get("opis"), 500):
            neispravni += 1
            continue
        datum = _datum(d.get("datum"))
        znacaj = (d.get("znacaj") or "").strip().lower()
        if d.get("datum") and not datum:
            neispravni += 1
        stavke.append(_stavka("datum", AI_ANALYSIS, _tekst(d.get("opis"), 500), datum=datum,
                              datum_neispravan=bool(d.get("datum")) and not datum,
                              znacaj=znacaj if znacaj in _ZNACAJ else None))
    stavke.sort(key=lambda s: (s["datum"] or "9999-99-99", s["id"]))
    return _sekcija(OK if stavke else PRAZNO, stavke, neispravnih=neispravni)


def _strategija(g: dict, ima_genome: bool, raz: Razresavac) -> dict:
    if not ima_genome:
        return _sekcija(NEPOZNATO)
    stavke = []
    st = g.get("strategija")
    if isinstance(st, dict):
        for polje in ("primarni_cilj", "rezervni_plan"):
            v = _tekst(st.get(polje), 1500)
            if v:
                stavke.append(_stavka(f"strategija.{polje}", AI_ANALYSIS, v, vrsta=polje))
        for sc in st.get("scenariji") or []:
            if isinstance(sc, dict) and _tekst(sc.get("uslov")) and _tekst(sc.get("odgovor")):
                stavke.append(_stavka("strategija.scenario", AI_ANALYSIS,
                                      {"uslov": _tekst(sc.get("uslov"), 600), "odgovor": _tekst(sc.get("odgovor"), 600)},
                                      vrsta="scenario"))
    for polje in ("strategija_osnova", "zakljucak"):
        v = _tekst(g.get(polje), 1500)
        if v:
            stavke.append(_stavka(f"strategija.{polje}", AI_ANALYSIS, v, vrsta=polje))
    for polje in ("argumenti_za", "argumenti_protiv"):
        for a in g.get(polje) or []:
            v = _tekst(a, 800)
            if v:
                stavke.append(_stavka(f"strategija.{polje}", AI_ANALYSIS, v, vrsta=polje))
    nt = g.get("najslabija_tacka")
    if isinstance(nt, dict) and _tekst(nt.get("rizik")):
        lok = raz.lokacija(nt.get("lokacija"), "najslabija_tacka.lokacija") if nt.get("lokacija") else None
        stavke.append(_stavka("strategija.najslabija_tacka", AI_ANALYSIS, _tekst(nt.get("rizik"), 800),
                              vrsta="najslabija_tacka", preporuka=_tekst(nt.get("preporuka"), 800), lokacija=lok))
    return _sekcija(OK if stavke else PRAZNO, stavke)


def _nedostaje_iz_genome(g: dict, ima_genome: bool) -> list[dict]:
    if not ima_genome:
        return []
    out = []
    for n in g.get("nedostaje") or []:
        if not isinstance(n, dict) or not _tekst(n.get("dokument"), 300):
            continue
        h = (n.get("hitnost") or "").strip().lower()
        out.append(_stavka("nedostaje.genome", AI_ANALYSIS, _tekst(n.get("dokument"), 300),
                           hitnost=h if h in _HITNOST else None, opis=_tekst(n.get("opis"), 800)))
    return out


def sastavi(*, predmet: dict, case_dna: Optional[dict], dokumenti: Optional[list], dokazi: Optional[list],
            izvori: Optional[dict] = None, osvezeno: Optional[str] = None) -> dict:
    """Profesionalni ugovor predmeta. ČISTA funkcija: isti ulaz → isti izlaz, ulaz se ne menja.

    `izvori`: `{"dokumenti": "OK"|"GRESKA", "dokazi": ..., "genome": ...}` — izvor koji NIJE
    pročitan daje sekciju `DEGRADED`, nikad praznu."""
    izvori = dict(izvori or {})
    predmet = copy.deepcopy(predmet or {})
    g_sirov = case_dna if isinstance(case_dna, dict) else {}
    g = copy.deepcopy(g_sirov)
    genome_greska = izvori.get("genome") == "GRESKA"
    ima_genome = bool(g) and "greska" not in g and not genome_greska
    dok_ok = izvori.get("dokumenti", "OK") == "OK"
    dz_ok = izvori.get("dokazi", "OK") == "OK"
    raz = Razresavac(dokumenti if dok_ok else [])

    # Činjenice = perzistirane tvrdnje (predmet_dokazi), sa poreklom. Sortirane po id-u.
    if not dz_ok:
        cinjenice = _sekcija(DEGRADIRANO)
    else:
        redovi = sorted((d for d in (dokazi or []) if isinstance(d, dict) and d.get("id") and d.get("deleted_at") is None),
                        key=lambda d: str(d["id"]))
        st = [tvrdnja_u_stavku(r, raz) for r in redovi]
        po_poreklu = {k: sum(1 for s in st if s["poreklo"] == k) for k in KLASE_POREKLA}
        cinjenice = _sekcija(OK if st else PRAZNO, st, po_poreklu=po_poreklu)

    nedostaje = _nedostaje_iz_genome(g, ima_genome)
    sekcije = {
        "identitet": {
            "predmet_id": predmet.get("id"),
            "naziv": _stavka("identitet.naziv", HUMAN_CONFIRMED, _tekst(predmet.get("naziv"), 300), id_="predmet:naziv"),
            "tip": predmet.get("tip"),
            "status": predmet.get("status"),
            "pravni_identitet": (_stavka("identitet.pravni", AI_ANALYSIS,
                                         _tekst((g.get("pravna_teorija") or {}).get("pravni_identitet")
                                                if isinstance(g.get("pravna_teorija"), dict) else None, 600))
                                 if ima_genome else None),
        },
        "cinjenice": cinjenice,
        "stranke": _strane(predmet, g, ima_genome),
        "pravna_pitanja": _pravna_pitanja(g, ima_genome),
        "hronologija": _hronologija(g, ima_genome),
        "strategija": _strategija(g, ima_genome, raz),
        "nedostaje": _sekcija(NEPOZNATO if not ima_genome else (OK if nedostaje else PRAZNO), nedostaje),
        "metrike": klasifikuj_metrike(g) if ima_genome else [],
    }

    # Nesigurnost — eksplicitno, nikad prećutano.
    nes: list[dict] = []
    if genome_greska:
        nes.append({"vrsta": "genome_nije_procitan", "opis": "Analiza predmeta trenutno nije dostupna (greška čitanja)."})
    elif not g:
        nes.append({"vrsta": "genome_nije_izracunat", "opis": "Analiza predmeta još nije izračunata."})
    elif "greska" in g:
        nes.append({"vrsta": "genome_greska", "opis": "Poslednja analiza nije uspela; prikazuje se samo evidencija."})
    if not dok_ok:
        nes.append({"vrsta": "izvor_nedostupan", "izvor": "dokumenti", "opis": "Dokumenti predmeta nisu pročitani."})
    if not dz_ok:
        nes.append({"vrsta": "izvor_nedostupan", "izvor": "dokazi", "opis": "Tvrdnje predmeta nisu pročitane."})
    if ima_genome:
        bez = g.get("_dokumenti_bez_teksta") or []
        if bez:
            nes.append({"vrsta": "dokumenti_bez_teksta", "kolicina": len(bez),
                        "opis": "Dokumenti bez čitljivog teksta nisu analizirani."})
        if g.get("_genome_docs_preskoceno"):
            nes.append({"vrsta": "dokumenti_izostavljeni", "kolicina": g.get("_genome_docs_preskoceno"),
                        "opis": "Deo dokumenata nije ušao u analizu (ograničenje veličine)."})
        ver = g.get("_verifikacija") or {}
        if ver.get("odluka") == "require_review":
            nes.append({"vrsta": "analiza_trazi_pregled", "kolicina": len(ver.get("hard_flags") or []),
                        "opis": "Automatska provera analize je našla probleme koje advokat treba da pregleda."})
        if (sekcije["pravna_pitanja"].get("pravni_osnovi_neprovereni") or []):
            nes.append({"vrsta": "pravni_osnovi_nepotvrdjeni",
                        "kolicina": len(sekcije["pravna_pitanja"]["pravni_osnovi_neprovereni"]),
                        "opis": "Pravni osnovi iz analize nisu potvrđeni u izvorima prava."})
        neisp = sekcije["hronologija"].get("neispravnih") or 0
        if neisp:
            nes.append({"vrsta": "neispravni_datumi", "kolicina": neisp, "opis": "Deo datuma iz analize nije ispravan i nije prikazan kao datum."})
    if raz.nerazreseno:
        nes.append({"vrsta": "nerazresene_reference", "kolicina": len(raz.nerazreseno),
                    "opis": "Deo referenci na dokumente nije mogao da se veže za dokument ovog predmeta.",
                    "detalji": raz.nerazreseno[:20]})

    broj_dok = len(dokumenti or []) if dok_ok else None
    analizirano = g.get("_genome_docs_count") if ima_genome else None
    if not ima_genome:
        kompletnost = NEPOZNATO
    elif not dok_ok or not dz_ok:
        kompletnost = DEGRADIRANO
    elif (g.get("_dokumenti_bez_teksta") or g.get("_genome_docs_preskoceno")
          or (broj_dok is not None and analizirano is not None and analizirano < broj_dok)):
        kompletnost = "PARTIAL"
    else:
        kompletnost = "COMPLETE"

    return {
        "schema_verzija": SCHEMA_VERSION,
        "predmet_id": predmet.get("id"),
        "metapodaci": {
            "genome_verzija": g.get("verzija") if ima_genome else None,
            "osvezeno": osvezeno if ima_genome else None,
            "dokumenata_u_predmetu": broj_dok,
            "dokumenata_analizirano": analizirano,
            "dokumenata_izostavljeno": g.get("_genome_docs_preskoceno") if ima_genome else None,
            "dokumenata_bez_teksta": len(g.get("_dokumenti_bez_teksta") or []) if ima_genome else None,
            "provera_analize": (g.get("_verifikacija") or {}).get("odluka") if ima_genome else None,
            "kompletnost": kompletnost,
            "izvori": izvori,
        },
        **sekcije,
        "nesigurnost": nes,
    }


# ── Kontradikcije (NS006 Task 5) ──────────────────────────────────────────────
#
# Izvor istine je PERZISTIRANA V2 kontradikcija (migracije 119–125): sporna tačka
# (`predmet_issues`), relacija, stanje i članovi = trajni `predmet_dokazi.id`. Identitet
# odlučuje domen (shared/issue_v2.py) pri upisu; ovde se samo prikazuje.
#
# Isto pravilo „ili-ili" kao Case Actions (services/case_evolution.py, A015): ako predmet
# ima OTVORENE V2 kontradikcije, aktivne su one; inače su aktivne kontradikcije iz analize
# (`case_dna.kontradikcije`) — kao AI_ANALYSIS, BEZ tvrdnji (CLAIM oznake su efemerne) i
# sa dokumentima samo ako se zatvoreno razreše. Zatvorene V2 kontradikcije su istorija.

STANJE_KONTRADIKCIJE = {
    "OPEN": "AKTIVNA",
    "REVIEW_REQUIRED": "ZA_PREGLED",
    "RESOLVED": "RAZRESENA",
    "NOT_OBSERVED": "VISE_SE_NE_OPAZA",
    "SUPERSEDED": "ZAMENJENA",
}
_RELACIJE = {"cinjenica_cinjenica", "cinjenica_norma"}
_TEZINE = {"kriticna", "vazna", "manja"}


def _ucesnik(clan: dict, dokazi_po_id: dict, raz: Razresavac) -> dict:
    red = dokazi_po_id.get(str(clan.get("dokaz_id")))
    if not red:
        # Član postoji u V2, ali tvrdnja nije među pročitanim (obrisana ili van granice čitanja).
        return {"tvrdnja_id": str(clan.get("dokaz_id")), "tvrdnja": None, "poreklo": UNKNOWN,
                "dokument_id": None, "lokacija": None, "uklonjen": bool(clan.get("uklonjen")),
                "nepoznato": "tvrdnja nije dostupna"}
    s = tvrdnja_u_stavku(red, raz)
    return {"tvrdnja_id": s["id"], "tvrdnja": s["vrednost"], "poreklo": s["poreklo"],
            "dokument_id": s["dokument_id"], "lokacija": s["lokacija"], "uklonjen": bool(clan.get("uklonjen"))}


def sastavi_kontradikcije(*, v2: Optional[list], case_dna: Optional[dict], dokazi: Optional[list],
                          dokumenti: Optional[list], izvori: Optional[dict] = None) -> dict:
    izvori = dict(izvori or {})
    if v2 is None or izvori.get("kontradikcije", "OK") != "OK":
        return {"stanje": DEGRADIRANO, "izvor": None, "aktivne": [], "za_pregled": [], "zatvorene": [],
                "sazetak": None, "razlog": "Kontradikcije nisu pročitane."}
    raz = Razresavac(dokumenti if izvori.get("dokumenti", "OK") == "OK" else [])
    po_id = {str(d["id"]): d for d in (dokazi or []) if isinstance(d, dict) and d.get("id")}

    def _v2_stavka(k: dict) -> dict:
        ucesnici = [_ucesnik(c, po_id, raz) for c in (k.get("clanovi") or [])]
        aktivni = [u for u in ucesnici if not u["uklonjen"]]
        dok_ids = sorted({u["dokument_id"] for u in aktivni if u["dokument_id"]})
        relacija = k.get("relation_type") if k.get("relation_type") in _RELACIJE else None
        return {
            "id": str(k["id"]), "id_vrsta": "izvor", "poreklo": AI_ANALYSIS, "reference_proverene": True,
            "sporna_tacka": _tekst(k.get("issue_label"), 300), "sporna_tacka_id": str(k.get("issue_id") or ""),
            "relacija": relacija, "tezina": k.get("tezina") if k.get("tezina") in _TEZINE else None,
            "stanje": STANJE_KONTRADIKCIJE.get(k.get("state"), UNKNOWN), "razlog_stanja": _tekst(k.get("state_reason"), 300),
            "ucesnici": aktivni, "povuceni_ucesnici": len(ucesnici) - len(aktivni),
            "dokumenti": dok_ids,
            "bez_izvora": [u["tvrdnja_id"] for u in aktivni if not u["dokument_id"]],
            "nastala": k.get("created_at"), "promenjena": k.get("updated_at"),
        }

    v2_stavke = [_v2_stavka(k) for k in sorted(v2, key=lambda x: str(x.get("id")))]
    aktivne_v2 = [s for s in v2_stavke if s["stanje"] == "AKTIVNA"]
    za_pregled = [s for s in v2_stavke if s["stanje"] == "ZA_PREGLED"]
    zatvorene = [s for s in v2_stavke if s["stanje"] not in ("AKTIVNA", "ZA_PREGLED")]

    legacy_sirove = (case_dna or {}).get("kontradikcije") if isinstance(case_dna, dict) and "greska" not in (case_dna or {}) else None
    legacy = []
    if not aktivne_v2 and isinstance(legacy_sirove, list):
        for i, k in enumerate(legacy_sirove):
            if not isinstance(k, dict):
                continue
            tacka = _tekst(k.get("issue_label"), 300) or _tekst(k.get("opis"), 300)
            if not tacka:
                continue
            strane = []
            for lok_polje, id_polje in (("lokacija_1", "dokument_id_1"), ("lokacija_2", "dokument_id_2")):
                lok = raz.lokacija(k.get(lok_polje), f"kontradikcije[{i}].{lok_polje}") if k.get(lok_polje) else \
                    {"dokument_id": None, "strana_po_analizi": None, "oznaka": None}
                upisan = raz.dokument_id(k.get(id_polje), f"kontradikcije[{i}].{id_polje}") if k.get(id_polje) else None
                # Upisani id (A002, razrešen pri upisu) ima prednost samo ako se SLAŽE sa oznakom ili oznake nema.
                if upisan and lok["dokument_id"] and upisan != lok["dokument_id"]:
                    lok = {**lok, "dokument_id": None, "neslaganje": True}
                elif upisan and not lok["dokument_id"]:
                    lok = {**lok, "dokument_id": upisan}
                strane.append(lok)
            relacija = k.get("relation_type") if k.get("relation_type") in _RELACIJE else None
            legacy.append({
                "id": kljuc_sadrzaja("kontradikcija.analiza", tacka, k.get("lokacija_1"), k.get("lokacija_2")),
                "id_vrsta": "sadrzaj", "poreklo": AI_ANALYSIS, "reference_proverene": False,
                "sporna_tacka": tacka, "opis": _tekst(k.get("opis"), 1200), "relacija": relacija,
                "tezina": k.get("tezina") if k.get("tezina") in _TEZINE else None,
                "stanje": "NEPOTVRDJENA_TVRDNJAMA", "ucesnici": [],
                "lokacije": strane, "dokumenti": sorted({s["dokument_id"] for s in strane if s["dokument_id"]}),
                "napomena": "Analiza navodi ovu kontradikciju, ali ona nije vezana za tvrdnje predmeta.",
            })

    izvor = "v2" if aktivne_v2 else ("analiza" if legacy else ("v2" if v2_stavke else None))
    aktivne = aktivne_v2 if aktivne_v2 else legacy
    sve = aktivne + za_pregled + zatvorene
    return {
        "stanje": OK if sve else PRAZNO,
        "izvor": izvor,
        "aktivne": aktivne,
        "za_pregled": za_pregled,
        "zatvorene": zatvorene,
        "nerazresene_reference": raz.nerazreseno[:20],
        "sazetak": {
            "aktivnih": len(aktivne), "za_pregled": len(za_pregled), "zatvorenih": len(zatvorene),
            "kriticnih_aktivnih": sum(1 for s in aktivne if s["tezina"] == "kriticna"),
            "aktivnih_bez_veze_na_tvrdnje": sum(1 for s in aktivne if not s["reference_proverene"]),
        },
    }


# ── Promene između verzija Genome-a (NS006 Task 6) ────────────────────────────
#
# Deterministička razlika dva SNIMKA `case_dna` (trenutni i prethodni iz
# `predmet_genome_history.genome_data`). Bez modela. Pravila:
#   • porede se samo STRUKTURNE stavke sa trajnim identitetom; slobodan tekst modela
#     (opis, strategija, najslabija tačka) se NE poredi — preformulacija nije promena;
#   • kontradikcije po `claim_ids` (trajni `predmet_dokazi.id`, A008 pravilo sadržavanja
#     iz shared/contradiction_identity.py); bez njih u bilo kojoj verziji → `nepoznato`;
#   • rokovi iz analize po (dokument, datum); „promenjen" samo kad dokument ima tačno
#     jedan rok u obe verzije;
#   • procene modela (snaga, kritičnost, broj nedostajućih) idu ODVOJENO u `analiticke`.

def _rokovi_kljucevi(g: dict) -> dict:
    out: dict[tuple, dict] = {}
    for r in g.get("rokovi_kriticni") or []:
        if not isinstance(r, dict):
            continue
        datum = _datum(r.get("datum"))
        if not datum:
            continue
        out[(str(r.get("dokument_id") or ""), datum)] = r
    return out


def promene_genome(stari: Optional[dict], novi: Optional[dict]) -> dict:
    from shared.contradiction_identity import (
        contradiction_identity_stable, identitet_seme_stabilna, razdvoji_kontradikcije)
    if not isinstance(novi, dict) or not novi or "greska" in novi:
        return {"stanje": NEPOZNATO, "promene": [], "analiticke": [], "nepoznato": [
            {"oblast": "genome", "razlog": "Trenutna analiza ne postoji ili nije uspela."}]}
    if not isinstance(stari, dict) or not stari or "greska" in stari:
        return {"stanje": "PRVA_VERZIJA", "promene": [], "analiticke": [], "nepoznato": []}

    promene: list[dict] = []
    analiticke: list[dict] = []
    nepoznato: list[dict] = []

    def dodaj(lista, vrsta, oznaka, opis, kljuc, poreklo, staro=None, novo=None, **dod):
        lista.append({"vrsta": vrsta, "oznaka": oznaka, "opis": opis, "kljuc": kljuc, "poreklo": poreklo,
                      "staro": staro, "novo": novo, **dod})

    # 1. Kontradikcije — trajni identitet ili ništa.
    sk = [k for k in (stari.get("kontradikcije") or []) if isinstance(k, dict)]
    nk = [k for k in (novi.get("kontradikcije") or []) if isinstance(k, dict)]
    if sk or nk:
        if identitet_seme_stabilna(sk, nk):
            r = razdvoji_kontradikcije(sk, nk, contradiction_identity_stable)
            for k in r["nove"]:
                rel, ids = contradiction_identity_stable(k)
                dodaj(promene, "kontradikcija_dodata", "+", "Nova kontradikcija: " + (_tekst(k.get("issue_label"), 200) or "sporna tačka"),
                      "kontradikcija:" + rel + ":" + ",".join(ids), AI_ANALYSIS, tvrdnje=list(ids))
            for k in r["eliminisane"]:
                rel, ids = contradiction_identity_stable(k)
                dodaj(promene, "kontradikcija_nestala", "✓", "Kontradikcija se više ne opaža: " + (_tekst(k.get("issue_label"), 200) or "sporna tačka"),
                      "kontradikcija:" + rel + ":" + ",".join(ids), AI_ANALYSIS, tvrdnje=list(ids))
        else:
            nepoznato.append({"oblast": "kontradikcije",
                              "razlog": "Bar jedna verzija nema trajne veze kontradikcija na tvrdnje; poređenje po oznakama bi dalo lažne promene."})

    # 2. Brojevi iz analize (deterministički prebrojani u trenutku analize).
    for kljuc, opis in (("_genome_docs_count", "Dokumenata u analizi"),):
        a, b = stari.get(kljuc), novi.get(kljuc)
        if isinstance(a, int) and isinstance(b, int) and a != b:
            dodaj(promene, "dokumenti_analize", "+" if b > a else "−", f"{opis}: {a} → {b}", kljuc,
                  DETERMINISTIC_DERIVATION, a, b)
    sa, na = stari.get("_analiza_osnov") or {}, novi.get("_analiza_osnov") or {}
    if isinstance(sa, dict) and isinstance(na, dict):
        a, b = sa.get("cinjenica"), na.get("cinjenica")
        if isinstance(a, int) and isinstance(b, int) and a != b:
            dodaj(promene, "tvrdnje_analize", "+" if b > a else "−", f"Tvrdnji u analizi: {a} → {b}",
                  "_analiza_osnov.cinjenica", DETERMINISTIC_DERIVATION, a, b)

    # 3. Rokovi iz analize — po (dokument, datum).
    sr, nr = _rokovi_kljucevi(stari), _rokovi_kljucevi(novi)
    po_dok_s: dict[str, list] = {}
    po_dok_n: dict[str, list] = {}
    for (d, dat) in sr:
        po_dok_s.setdefault(d, []).append(dat)
    for (d, dat) in nr:
        po_dok_n.setdefault(d, []).append(dat)
    promenjeni_dok = {d for d in po_dok_s if d and len(po_dok_s[d]) == 1 and len(po_dok_n.get(d, [])) == 1
                      and po_dok_s[d] != po_dok_n[d]}
    for d in sorted(promenjeni_dok):
        dodaj(promene, "rok_promenjen", "!", f"Rok iz analize promenjen: {po_dok_s[d][0]} → {po_dok_n[d][0]}",
              "rok:" + d, AI_ANALYSIS, po_dok_s[d][0], po_dok_n[d][0], dokument_id=d)
    for (d, dat) in sorted(set(nr) - set(sr)):
        if d in promenjeni_dok:
            continue
        dodaj(promene, "rok_dodat", "+", f"Nov rok u analizi: {dat}", f"rok:{d}:{dat}", AI_ANALYSIS, None, dat, dokument_id=d or None)
    for (d, dat) in sorted(set(sr) - set(nr)):
        if d in promenjeni_dok:
            continue
        dodaj(promene, "rok_uklonjen", "−", f"Rok više nije u analizi: {dat}", f"rok:{d}:{dat}", AI_ANALYSIS, dat, None, dokument_id=d or None)

    # 4. Ishod automatske provere analize (deterministički validator).
    vs, vn = (stari.get("_verifikacija") or {}).get("odluka"), (novi.get("_verifikacija") or {}).get("odluka")
    if vs and vn and vs != vn:
        dodaj(promene, "provera_analize", "!" if vn == "require_review" else "✓",
              f"Provera analize: {vs} → {vn}", "_verifikacija.odluka", DETERMINISTIC_DERIVATION, vs, vn)

    # 5. Procene modela — odvojeno, nikad kao činjenica.
    a, b = stari.get("snaga_predmeta_procent"), novi.get("snaga_predmeta_procent")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a != b:
        dodaj(analiticke, "analiticka_ocena", "~", f"Analitička ocena (nije verovatnoća ishoda): {a} → {b}",
              "snaga_predmeta_procent", AI_ANALYSIS, a, b, klasa=MIXED)
    a, b = len(stari.get("nedostaje") or []), len(novi.get("nedostaje") or [])
    if a != b:
        dodaj(analiticke, "nedostajuce_po_analizi", "~", f"Nedostajućih stavki po analizi: {a} → {b}",
              "nedostaje", AI_ANALYSIS, a, b, klasa=MODEL_DERIVED)

    promene.sort(key=lambda p: (p["vrsta"], p["kljuc"]))
    analiticke.sort(key=lambda p: (p["vrsta"], p["kljuc"]))
    return {"stanje": OK, "promene": promene, "analiticke": analiticke, "nepoznato": nepoznato}
