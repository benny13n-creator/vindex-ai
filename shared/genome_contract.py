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
        """`"DOK-NN str.X"` → `{dokument_id, strana, oznaka}`. Strana je ono što je model
        naveo (nije proverena), i to samo ako je ceo broj."""
        oznaka = _tekst(tekst, 200)
        if not oznaka:
            return {"dokument_id": None, "strana": None, "oznaka": None}
        m = _DOK.search(oznaka)
        if not m:
            self.nerazreseno.append({"polje": polje, "razlog": "lokacija bez DOK-NN oznake"})
            return {"dokument_id": None, "strana": None, "oznaka": oznaka}
        kandidati = self.po_rb.get(int(m.group(1)), [])
        if len(kandidati) != 1:
            self.nerazreseno.append({"polje": polje, "razlog": f"DOK-{int(m.group(1)):02d} ne odgovara tačno jednom dokumentu ovog predmeta"})
        strana = m.group(2)
        strana_br = int(strana) if strana and strana.rstrip(".,;").isdigit() and int(strana.rstrip(".,;")) > 0 else None
        return {"dokument_id": kandidati[0] if len(kandidati) == 1 else None,
                "strana": strana_br, "oznaka": oznaka}


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

IZVOR_TVRDNJE_COVEK = "covek"
IZVOR_TVRDNJE_AI = "ai_klasifikacija"


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
        lokacija = {"dokument_id": dok_id, "strana": red.get("stranica"), "paragraf": red.get("paragraf"),
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

    def dodaj(kljuc, vrednost, klasa, znacenje):
        out.append({"kljuc": kljuc, "vrednost": vrednost, "klasa": klasa, "znacenje": znacenje,
                    "napomena": _NIJE_ISHOD})

    if "snaga_predmeta_procent" in g:
        dodaj("snaga_predmeta_procent", g.get("snaga_predmeta_procent"), MIXED,
              "zbir uticaja faktora koje je naveo model, sabran pravilom u backend-u (compute_snaga_score)")
    for k, v in sorted((g.get("heatmap") or {}).items()) if isinstance(g.get("heatmap"), dict) else []:
        dodaj(f"heatmap.{k}", v, MODEL_DERIVED, "ocena dimenzije koju je dao model (0–100)")
    nt = g.get("najslabija_tacka")
    if isinstance(nt, dict) and "kriticnost" in nt:
        dodaj("najslabija_tacka.kriticnost", nt.get("kriticnost"), MODEL_DERIVED, "procena modela (0–100)")
    for i, d in enumerate(g.get("dokazi_rang") or []):
        if isinstance(d, dict) and "snaga_score" in d:
            dodaj(f"dokazi_rang[{i}].snaga_score", d.get("snaga_score"), MODEL_DERIVED, "ocena dokumenta koju je dao model")
    if "genome_kompletnost" in g:
        dodaj("genome_kompletnost", g.get("genome_kompletnost"), MODEL_DERIVED, "samoprocena modela")
    osnov = g.get("_analiza_osnov")
    if isinstance(osnov, dict):
        for k in ("dokumenata", "cinjenica", "pravnih_elemenata"):
            if k in osnov:
                dodaj(f"_analiza_osnov.{k}", osnov.get(k), DETERMINISTIC, "prebrojano iz baze u trenutku analize")
    for k in ("_genome_docs_count", "_genome_docs_preskoceno"):
        if k in g:
            dodaj(k, g.get(k), DETERMINISTIC, "prebrojano pri sastavljanju analize")
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
    for s in (g.get("stranke") or []) if ima_genome else []:
        if not isinstance(s, dict) or not _tekst(s.get("ime"), 300):
            odbaceno += 1
            continue
        uloga = (s.get("uloga") or "").strip().lower()
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
