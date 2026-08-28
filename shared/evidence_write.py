# -*- coding: utf-8 -*-
"""
Evidence Vault — JEDINSTVENA PUTANJA UPISA u `predmet_dokazi`.

IMPLEMENTATION TASK 001 (2026-08-27). Uzrok postojanja ovog modula:

`predmet_dokazi` je do sada imao DVA nezavisna pisca sa nespojivom semantikom
kolone `snaga`:

  1. `routers/evidence.py::klasifikuj_i_sacuvaj` (automatska ekstrakcija) —
     IZVODIO je `snaga` iz `_snaga_iz_lokacije`, tj. iz toga da li je tvrdnja
     doslovno pronađena u izvornom dokumentu.
  2. `routers/evidence.py::add_dokaz` (ručni unos) — PREPISIVAO je `snaga`
     pravo iz tela HTTP zahteva, bez ikakve provere.

`snaga` se zatim čita na 9 mesta i u SVIM slučajevima završava u istoj funkciji
`services/risk_engine.py::calculate_procesni_rizik` (DC-001), koja broji
jaka/srednja/slaba i iz tog odnosa računa dokaznu snagu predmeta koju advokat
vidi kao „Jaka / Srednja / Slaba". Dva pisca su, dakle, punila JEDNU skalu sa
DVE različite mere.

`docs/architecture/DECISION_REGISTRY.md` je već proglasio kanonski izvor te
odluke — **DC-005 = `_snaga_iz_lokacije`** — ali je kao potrošača naveo samo
`klasifikuj_i_sacuvaj`. `add_dokaz` je bio NEPRIJAVLJEN drugi autor iste
odluke. Ovaj modul ne izmišlja novu semantiku: on SPROVODI onu koja je već
proglašena, i čini je nemogućom za tiho zaobilaženje.

──────────────────────────────────────────────────────────────────────────────
KANONSKO ZNAČENJE `snaga` (DC-005, prošireno na oba pisca)
──────────────────────────────────────────────────────────────────────────────

`snaga` = dokazna snaga tvrdnje. Određuje je ISKLJUČIVO `odredi_snagu()`, po
jednoj politici sa jednom dokumentovanom granom:

  AKO je izvorni tekst dokumenta dostupan za ovu tvrdnju:
      snaga = snaga_iz_lokacije(...)          → DC-005 je merodavan.
      Vrednost koju je poslao pozivalac se IGNORIŠE (i to se eksplicitno
      prijavljuje kroz `snaga_prepisana=True`, nikad tiho).

  INAČE (nema izvornog teksta — sistem nema šta da proveri):
      snaga = vrednost koju tvrdi čovek, validirana po CHECK enum-u.
      Advokat je domenski autoritet tamo gde mašina nema ulaz.
      Ako je ni čovek nije dao → "srednja" (podrazumevana vrednost iz
      migracije 016, koja znači „neutralno/nepoznato", ne „potvrđeno srednje").

To je JEDNO značenje sa jednim algoritmom, a ne dva značenja: grana se bira na
osnovu toga da li ulaz za proveru uopšte postoji, i bira je OVAJ modul, nikad
pozivalac.

Zašto ručni unos bez dokumenta ne prolazi kroz DC-005: `snaga_iz_lokacije`
vraća samo "jaka" ili "srednja" — nikada "slaba". Prisiljavanje ručnog unosa
kroz nju bi advokatu trajno oduzelo mogućnost da dokaz označi kao slab, što je
stvaran gubitak funkcije, a ne ispravka.

──────────────────────────────────────────────────────────────────────────────
ŠTA `predmet_dokazi` JESTE (utvrđeno, ne pretpostavljeno)
──────────────────────────────────────────────────────────────────────────────

Nije zapis o dokumentu (to je `predmet_dokumenti`), nije fragment izvora (tekst
se ne kopira), i NIJE pun Fact model (nema vremenske važnosti, nema zamene
zastarele tvrdnje, nema potvrde čoveka, nema kontradikcije kao relacije).

Jeste: **registar dokaznih stavki, gde je stavka tvrdnja (`tvrdnja`) opciono
utemeljena u izvornom dokumentu.** Migracija 016 to i kaže doslovno
(„Evidence items — specific facts/claims extracted from documents"), a
`kategorija` ima ŠEST vrednosti od kojih je `cinjenica` samo jedna.

Zato se primitiv zove `upisi_dokaz`, a ne `upisi_cinjenicu`: „činjenica" je
podvrsta, ne entitet.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Optional

logger = logging.getLogger("vindex.evidence_write")

# ── Domen iz migracije 016 (CHECK ograničenja) ───────────────────────────────
KATEGORIJE: frozenset[str] = frozenset(
    {"cinjenica", "dokaz", "svedok", "vestacenje", "pravni_osnov", "ostalo"}
)
SNAGE: frozenset[str] = frozenset({"jaka", "srednja", "slaba"})
SNAGA_PODRAZUMEVANA = "srednja"

# ── IDENTITET TVRDNJE (TASK 001) ─────────────────────────────────────────────
# Verzija KANONIZACIJE, ne verzija ekstraktora. Ulazi u ključ identiteta da bi
# promena pravila normalizacije proizvela NOVE identitete, a stare ostavila
# netaknutima -- zato se identitet SKLADIŠTI, nikad ne preračunava pri čitanju.
# `EXTRACTION_VERSION` (shared/vector_identity.py) NAMERNO nije deo ključa:
# nadogradnja ekstraktora ne sme prekinuti nijednu postojeću relaciju.
CANON_VERSION = "c1"

# Kolone koje je dodala migracija 080 — drže se izdvojeno da bi se pri
# neuspehu upisa mogao ponoviti pokušaj bez njih (v. `_insert_sa_fallback`).
KOLONE_GROUNDING: tuple[str, ...] = ("stranica", "paragraf", "start_offset", "end_offset")

# Kolona iz migracije 116. Izdvojena iz istog razloga kao grounding kolone:
# okruženje koje migraciju nije pokrenulo ne sme izgubiti ceo upis.
KOLONA_IDENTITET = "identitet"

# Kolona iz migracije 117 (TASK 002A). Odvojena od `KOLONE_GROUNDING` i od
# `KOLONA_IDENTITET` jer potiče iz TREĆE, nezavisne migracije -- okruženje sme
# imati 116 a ne 117, pa degradacija mora ići kolona-po-kolona, najnovija prva.
KOLONA_NACIN = "nacin_pronalaska"

# Dozvoljene vrednosti `nacin_pronalaska`. Nema četvrte, nema `None` kao vrednosti:
# `lociraj_tvrdnju` uvek vraća tačno jednu od ove tri.
NACIN_EGZAKTAN     = "egzaktan"
NACIN_NORMALIZOVAN = "normalizovan"
NACIN_NIJE         = "nije_pronadjen"
NACINI: frozenset[str] = frozenset({NACIN_EGZAKTAN, NACIN_NORMALIZOVAN, NACIN_NIJE})

# ── TASK 003B — PROVENIJENCIJA ODLUKE O SNAZI (migracija 118) ────────────────
# `snaga` kaže KOLIKA je snaga. `izvor_snage` kaže DA LI je iko o njoj odlučio.
# To su dve različite činjenice i nijedna se ne sme izvoditi iz druge: kolona
# `snaga` je `NOT NULL DEFAULT 'srednja'`, pa njena vrednost NIKAD ne dokazuje
# da je procena izvršena.
KOLONA_IZVOR_SNAGE = "izvor_snage"

IZVOR_COVEK         = "covek"          # pozivalac je EKSPLICITNO poslao `snaga`
IZVOR_DC005         = "dc005"          # DC-005 je tvrdnju NAŠAO i izveo `jaka`
IZVOR_PODRAZUMEVANO = "podrazumevano"  # niko nije odlučio (uklj. DC-005 „nije našao")
IZVORI: frozenset[str] = frozenset({IZVOR_COVEK, IZVOR_DC005, IZVOR_PODRAZUMEVANO})

# Jedini skup koji znači „procena se dogodila". `NULL` (legacy) NIJE ovde --
# fail-closed: odsustvo dokaza o proceni nije dokaz o proceni.
IZVORI_PROCENJENO: frozenset[str] = frozenset({IZVOR_COVEK, IZVOR_DC005})

# Stanja pokrivenosti procene. Četvrto (`EVIDENCE_PARTIAL`) je obavezno: bez
# njega je predmet sa 1 procenjenom od 100 tvrdnji nerazlučiv od predmeta sa
# jednom jedinom procenjenom tvrdnjom.
POKRIVENOST_NEMA_TVRDNJI = "NO_CLAIMS"
POKRIVENOST_NEPROCENJENO = "EVIDENCE_UNASSESSED"
POKRIVENOST_DELIMICNO    = "EVIDENCE_PARTIAL"
POKRIVENOST_PROCENJENO   = "EVIDENCE_ASSESSED"

# ── Konstante utemeljenja (preseljene iz routers/evidence.py, nepromenjene) ──
_CHARS_PO_STRANICI = 2500  # gruba procena (12pt font, A4, standardni razmak)
_PROBE_MAX_LEN = 100  # lociraj_tvrdnju proverava SAMO prvih ovoliko karaktera tvrdnje
_SNAGA_MIN_TVRDNJA_LEN = 20  # ispod ovoga, substring poklapanje je previse opste (npr. samo ime stranke) da bi bio pouzdan signal

_PRAZNA_LOKACIJA: dict[str, Any] = {
    "stranica": None, "paragraf": None, "start_offset": None, "end_offset": None,
    "nacin": NACIN_NIJE,
}


def izracunaj_identitet(predmet_id: str, tvrdnja: str) -> str:
    """JEDINI generator identiteta tvrdnje.

        identitet = sha256(predmet_id | CANON_VERSION | normalize_ws(tvrdnja))

    Osobine dokazane napadom pre implementacije (v. IMPL-001-REPORT.md):
      * deterministička — čista funkcija, 100/100 istih poziva isti rezultat
      * neosetljiva na: višestruke razmake, vodeće/prateće razmake, CRLF, TAB,
        Unicode NFD/NFC, veličinu slova
      * osetljiva na: drugi predmet, drugi tekst, drugu `CANON_VERSION`
      * NE sadrži: offset, stranicu, paragraf, GPT ID, embedding,
        `EXTRACTION_VERSION`

    `_normalize_ws` se UVOZI, ne reimplementira -- druga implementacija istog
    pravila bila bi drugi autor istog koncepta. Ako uvoz padne, upis pada
    (fail-closed): tvrdnja bez identiteta ne sme nastati."""
    from analiza.validator import _normalize_ws
    if not predmet_id:
        raise GreskaDokaza("Identitet tvrdnje traži predmet_id.")
    osnova = f"{predmet_id}|{CANON_VERSION}|{_normalize_ws(tvrdnja or '')}"
    return hashlib.sha256(osnova.encode("utf-8")).hexdigest()


class GreskaDokaza(ValueError):
    """Ulaz koji se ne sme upisati.

    Namerno je `ValueError`, a ne `HTTPException`: `shared/` ne sme da zna za
    HTTP sloj. Ruter je mapira na 400/404 (v. routers/evidence.py)."""

    def __init__(self, poruka: str, *, status: int = 400):
        super().__init__(poruka)
        self.poruka = poruka
        self.status = status


# ═══════════════════════════════════════════════════════════════════════════
# 1. UTEMELJENJE (provenance) — INVARIANT 2
# ═══════════════════════════════════════════════════════════════════════════

def lociraj_tvrdnju(tekst: str, tvrdnja: str) -> dict:
    """AKCIJA 2 (2026-07-24): programski pronalazi GDE se tvrdnja nalazi u
    izvornom dokumentu -- isti substring-matching princip kao
    analiza/validator.py::validate_clause_excerpts (ne teoretsko poverenje
    LLM-u), primenjen na Evidence Vault. Ako tvrdnja nije doslovno
    pronađena (GPT je parafrazirao umesto citirao), vraća sve None --
    kolone su NULLABLE upravo zbog ovoga (fail-soft, nikad izmišljena
    lokacija samo da bi polje bilo popunjeno).

    IMPLEMENTATION TASK 001: preseljena iz routers/evidence.py u shared/ bez
    ijedne izmene ponašanja, da bi jedinstveni primitiv upisa mogao da je
    pozove bez cirkularnog importa. routers/evidence.py je re-eksportuje pod
    starim imenom `_lociraj_tvrdnju` (DC-005 + postojeći testovi)."""
    if not tekst or not tvrdnja:
        return dict(_PRAZNA_LOKACIJA)

    probe = re.sub(r"\.{2,}$|…$", "", tvrdnja.strip()).rstrip()[:_PROBE_MAX_LEN]
    if not probe:
        return dict(_PRAZNA_LOKACIJA)

    # Pokušaj 1: tačan (case-insensitive) substring na ORIGINALNOM tekstu --
    # daje TAČAN offset kad GPT citira sa istim razmacima kao izvor.
    pos = tekst.lower().find(probe.lower())
    if pos >= 0:
        start_offset, end_offset = pos, pos + len(probe)
    else:
        # Pokušaj 2: whitespace-normalizovano pretraživanje (isti obrazac
        # kao validate_clause_excerpts), sa proporcionalnim mapiranjem
        # nazad na originalni tekst -- aproksimacija, dovoljno dobra za
        # "otprilike koja stranica/segment", ne za karakter-precizan offset.
        try:
            from analiza.validator import _normalize_ws
            tekst_norm = _normalize_ws(tekst)
            probe_norm = _normalize_ws(probe)
            npos = tekst_norm.find(probe_norm)
        except Exception:
            npos = -1
        if npos < 0:
            return dict(_PRAZNA_LOKACIJA)
        razmera = len(tekst) / max(len(tekst_norm), 1)
        start_offset = int(npos * razmera)
        end_offset = int((npos + len(probe_norm)) * razmera)

    stranica = (start_offset // _CHARS_PO_STRANICI) + 1

    paragraf = None
    try:
        from analiza.segmenter import segment_document
        segmented = segment_document(tekst)
        for seg in segmented.segments:
            if seg.start_offset >= 0 and seg.start_offset <= start_offset < seg.end_offset:
                paragraf = seg.id
                break
    except Exception:
        pass

    # TASK 002A: način se određuje ISKLJUČIVO proverom invarijante nad
    # rezultatom, NE time koja je grana koda uspela. Pokušaj 1 je
    # case-insensitive (`tekst.lower().find(probe.lower())`), pa pogodak koji se
    # razlikuje samo po veličini slova NIJE doslovan substring -- klasifikuje se
    # kao `normalizovan`. Time invarijanta iz §4 važi bez izuzetka:
    #     nacin == "egzaktan"  =>  tekst[start_offset:end_offset] == probe
    # Nijedna nova normalizacija nije uvedena; ovo je samo poređenje rezultata.
    nacin = NACIN_EGZAKTAN if tekst[start_offset:end_offset] == probe else NACIN_NORMALIZOVAN

    return {
        "stranica": stranica,
        "paragraf": paragraf,
        "start_offset": start_offset,
        "end_offset": end_offset,
        "nacin": nacin,
    }


def snaga_iz_lokacije(tvrdnja: str, lokacija: dict) -> str:
    """Program Beta (2026-08-04) — `snaga` je ranije bila fiksna "srednja" za
    SVAKU tvrdnju, bez obzira da li je lociraj_tvrdnju uopšte mogla da je
    pronađe u izvornom dokumentu -- odbačen već-izračunat signal (isti obrazac
    kao shared/genome_validator.py::compute_snaga_score, treći potvrđeni
    slučaj istog principa u ovom repou). Tvrdnja pronađena doslovno u izvoru
    je genuinely jača dokazna osnova nego neverifikovana -- ali "nije
    pronađeno" NE znači nužno "netačno" (GPT je mogao parafrazirati), zato
    default za neverifikovano ostaje neutralno "srednja", ne "slaba".

    Olympus Faza 10 governance nalaz (2026-08-04, AI Grounding + AI Quality
    Auditor nezavisno potvrdili isti rizik): "jaka" se dodeljuje SAMO kad je
    CELA tvrdnja duž provere -- ne prekratka (generička fraza kao samo ime
    stranke može slučajno poklopiti nepovezano mesto u tekstu) i ne duža od
    _PROBE_MAX_LEN (lociraj_tvrdnju proverava SAMO prvih 100 karaktera --
    duža tvrdnja čiji je REP izmišljen/parafraziran bi inače dobila "jaka" na
    osnovu poklapanja samo prefiksa, nikad proveravajući ostatak).

    IMPLEMENTATION TASK 001: preseljena iz routers/evidence.py bez izmene
    ponašanja. Ovo je i dalje DC-005 -- ali se od sada poziva iz JEDNOG mesta
    (`odredi_snagu`), umesto direktno iz jednog od dva pisca."""
    if lokacija.get("start_offset") is None:
        return "srednja"
    duzina = len((tvrdnja or "").strip())
    if duzina < _SNAGA_MIN_TVRDNJA_LEN or duzina > _PROBE_MAX_LEN:
        return "srednja"
    return "jaka"


# ═══════════════════════════════════════════════════════════════════════════
# 2. KANONSKA ODLUKA O `snaga` — INVARIANT 3
# ═══════════════════════════════════════════════════════════════════════════

def odredi_snagu(
    tvrdnja: str,
    lokacija: dict,
    *,
    izvor_dostupan: bool,
    snaga_tvrdi_covek: Optional[str] = None,
) -> tuple[str, str]:
    """JEDINI donosilac odluke o `snaga` za ceo Evidence Vault.

    Vraća `(snaga, izvor_odluke)` gde je `izvor_odluke` jedno od:
      "dc005"          — izvedeno iz utemeljenja u izvornom dokumentu
      "covek"          — advokat je tvrdio vrednost, izvora za proveru nema
      "podrazumevano"  — nema ni izvora ni tvrdnje čoveka

    `izvor_odluke` se vraća pozivaocu (a ne upisuje u bazu — nova kolona bi
    tražila migraciju, a ovaj zadatak je namerno mali) da bi svaki upis mogao
    da bude revidiran caller → primitiv → baza bez pogađanja.

    `izvor_dostupan` mora biti True SAMO kad je stvaran tekst dokumenta bio
    prosleđen na proveru. Prazan/nedostajući tekst NIJE dostupan izvor --
    inače bi svaka tvrdnja bez teksta tiho dobila "srednja" kao da je
    proverena i nije prošla, umesto kao nepoznata."""
    if izvor_dostupan:
        return snaga_iz_lokacije(tvrdnja, lokacija), "dc005"
    if snaga_tvrdi_covek is not None:
        s = str(snaga_tvrdi_covek).strip().lower()
        if s not in SNAGE:
            raise GreskaDokaza(
                f"Nepoznata snaga '{snaga_tvrdi_covek}'. Dozvoljeno: {', '.join(sorted(SNAGE))}."
            )
        return s, "covek"
    return SNAGA_PODRAZUMEVANA, "podrazumevano"


def izvor_snage_iz_odluke(izvor_odluke: str, snaga: str) -> str:
    """TASK 003B — prevodi odluku `odredi_snagu` u PERZISTIRANU provenijenciju.

    `odredi_snagu` vraća `"dc005"` čim je izvorni tekst uopšte bio dostupan --
    i onda kada tvrdnju NIJE našla. U tom slučaju `snaga_iz_lokacije` vraća
    `"srednja"`, a to je fallback za NEVERIFIKOVANO, ne procena (v. njen
    komentar: „default za neverifikovano"). Zato se ovde `dc005` čuva SAMO za
    ishod u kome je tvrdnja stvarno nađena, a jedini takav ishod je `jaka`:
    `snaga_iz_lokacije` vraća `jaka` isključivo kada `start_offset is not None`
    i kada je dužina u opsegu. Sve ostalo pod `dc005` je `podrazumevano`.

    Ova funkcija NE menja ni `snaga`, ni DC-005, ni `snaga_iz_lokacije` -- ona
    samo imenuje ono što je već odlučeno."""
    if izvor_odluke == IZVOR_COVEK:
        return IZVOR_COVEK
    if izvor_odluke == IZVOR_DC005 and snaga == "jaka":
        return IZVOR_DC005
    return IZVOR_PODRAZUMEVANO


def pokrivenost_procene(redovi: list[dict]) -> dict:
    """TASK 003B — deterministička pokrivenost procene za skup dokaznih redova.

    Broji ISKLJUČIVO po `izvor_snage`. `snaga`, `nacin_pronalaska`,
    `start_offset` i vreme upisa se NE gledaju -- svaki od njih je pojedinačno
    nedovoljan (dokazano u gate-ovima 004/005), a legacy red bez provenijencije
    (`NULL`) se broji kao NEPROCENJEN.

    Vraća {"status", "broj_tvrdnji", "broj_procenjenih", "broj_neprocenjenih"}."""
    ukupno = len(redovi)
    procenjenih = sum(1 for r in redovi if (r or {}).get(KOLONA_IZVOR_SNAGE) in IZVORI_PROCENJENO)
    if ukupno == 0:
        status = POKRIVENOST_NEMA_TVRDNJI
    elif procenjenih == 0:
        status = POKRIVENOST_NEPROCENJENO
    elif procenjenih < ukupno:
        status = POKRIVENOST_DELIMICNO
    else:
        status = POKRIVENOST_PROCENJENO
    return {
        "status":             status,
        "broj_tvrdnji":       ukupno,
        "broj_procenjenih":   procenjenih,
        "broj_neprocenjenih": ukupno - procenjenih,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. JEDINSTVENA PUTANJA UPISA
# ═══════════════════════════════════════════════════════════════════════════

def _proveri_vlasnistvo(supa, predmet_id: str, user_id: str) -> None:
    """INVARIANT 1 — upis uvek pripada TAČNO jednom predmetu, i taj predmet
    mora pripadati korisniku koji upisuje."""
    r = supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", user_id).limit(1).execute()
    if not (r.data or []):
        raise GreskaDokaza("Predmet nije pronađen.", status=404)


def _proveri_dokument(supa, dokument_id: str, predmet_id: str) -> None:
    """INVARIANT 1 — dokument-izvor mora pripadati ISTOM predmetu.

    Ranije ponašanje `add_dokaz`-a je bilo da tuđi/nepostojeći `dokument_id`
    TIHO postavi na NULL i vrati `{"ok": True}`. Cross-case upis time jeste bio
    sprečen, ali je korisnik dobijao potvrdu da je dokaz vezan za dokument koji
    u bazi nije vezan ni za šta -- isti obrazac lažnog uspeha koji je ovaj repo
    već zatvarao na drugim mestima (v. delete_dokaz / F-V41-002). Sada se
    odbija eksplicitno."""
    r = supa.table("predmet_dokumenti").select("id").eq("id", dokument_id).eq("predmet_id", predmet_id).limit(1).execute()
    if not (r.data or []):
        raise GreskaDokaza("Dokument ne pripada ovom predmetu.", status=400)


def _insert_sa_fallback(supa, redovi: list[dict]) -> list[dict]:
    """Jedini `INSERT` u `predmet_dokazi` u celoj aplikaciji.

    TASK 003B: najnovija kolona je `izvor_snage` (migracija 118), pa je ona
    PRVA koja se odbacuje. Ostatak lanca je nepromenjen -- okruženje sme imati
    117 a ne 118, i tada `nacin_pronalaska` i `identitet` NE SMEJU biti
    odbačeni bez potrebe. Nijedno postojeće polje se ne zamenjuje izmišljenom
    vrednošću; jedino se izostavlja kolona koje u toj bazi nema."""
    try:
        res = supa.table("predmet_dokazi").insert(redovi).execute()
        return res.data or []
    except Exception as exc:
        logger.warning(
            "[EVIDENCE_WRITE] Insert neuspešan (%s) — pokušavam bez kolone `%s`",
            exc, KOLONA_IZVOR_SNAGE,
        )
        bez_izvora = [{k: v for k, v in r.items() if k != KOLONA_IZVOR_SNAGE} for r in redovi]
        upisani = _insert_bez_izvora_snage(supa, bez_izvora)
        # Glasno: redovi su upisani BEZ provenijencije procene, pa ih svaka
        # buduća pokrivenost mora brojati kao NEPROCENJENE (fail-closed).
        logger.warning(
            "[EVIDENCE_WRITE] Upisano %d tvrdnji BEZ provenijencije procene — migracija 118 nije pokrenuta",
            len(bez_izvora),
        )
        return upisani


def _insert_bez_izvora_snage(supa, redovi: list[dict]) -> list[dict]:
    """Lanac degradacije za kolone starije od `izvor_snage` (nepromenjen).

    Zadržan fallback bez grounding kolona: migracija 080 JESTE primenjena u
    produkciji (provereno 2026-08-27 -- PostgREST vraća sve četiri kolone bez
    greške 42703), ali okruženja koja je nisu pokrenula ne smeju da izgube ceo
    upis. Isti fail-soft princip kao i ostatak Evidence Vault-a."""
    try:
        res = supa.table("predmet_dokazi").insert(redovi).execute()
        return res.data or []
    except Exception as exc:
        # Korak 1: možda nedostaje kolona `nacin_pronalaska` (migracija 117).
        # Degradira se KOLONA PO KOLONA, najnovija prva -- okruženje sme imati
        # 116 a ne 117, i tada `identitet` NE SME biti odbačen bez potrebe.
        logger.warning(
            "[EVIDENCE_WRITE] Insert neuspešan (%s) — pokušavam bez kolone `%s`",
            exc, KOLONA_NACIN,
        )
        bez_nacina = [{k: v for k, v in r.items() if k != KOLONA_NACIN} for r in redovi]
        try:
            res = supa.table("predmet_dokazi").insert(bez_nacina).execute()
            logger.warning(
                "[EVIDENCE_WRITE] Upisano %d tvrdnji BEZ načina pronalaska — migracija 117 nije pokrenuta",
                len(bez_nacina),
            )
            return res.data or []
        except Exception as exc_nacin:
            logger.warning(
                "[EVIDENCE_WRITE] Insert neuspešan (%s) — pokušavam i bez kolone `%s`",
                exc_nacin, KOLONA_IDENTITET,
            )
        bez_ident = [
            {k: v for k, v in r.items() if k not in (KOLONA_NACIN, KOLONA_IDENTITET)}
            for r in redovi
        ]
        try:
            res = supa.table("predmet_dokazi").insert(bez_ident).execute()
            # Glasno, jer je red upisan BEZ identiteta -- takva tvrdnja ne može
            # biti kraj nijedne buduće relacije dok se migracija ne pokrene.
            logger.warning(
                "[EVIDENCE_WRITE] Upisano %d tvrdnji BEZ identiteta — migracija 116 nije pokrenuta",
                len(bez_ident),
            )
            return res.data or []
        except Exception as exc_grounding:
            # Korak 2: možda nedostaju i grounding kolone (migracija 080).
            logger.warning(
                "[EVIDENCE_WRITE] Insert sa grounding kolonama neuspešan (%s) — pokušavam bez njih",
                exc_grounding,
            )
            legacy = [
                {k: v for k, v in r.items()
                 if k not in KOLONE_GROUNDING and k not in (KOLONA_IDENTITET, KOLONA_NACIN)}
                for r in redovi
            ]
            res = supa.table("predmet_dokazi").insert(legacy).execute()
            return res.data or []


def upisi_dokaze(
    supa,
    *,
    predmet_id: str,
    user_id: str,
    stavke: list[dict],
    izvor_tekst: Optional[str] = None,
    proveri_vlasnistvo: bool = True,
) -> dict:
    """Upisuje jednu ili više dokaznih stavki kroz JEDNU kanonsku putanju.

    `stavke` — lista dict-ova sa ključevima:
        tvrdnja           (obavezno)
        kategorija        (podrazumevano "cinjenica")
        dokument_id       (opciono)
        pravni_element    (opciono)
        napomena          (opciono)
        snaga             (opciono — TVRDNJA ČOVEKA; ignoriše se ako
                           `izvor_tekst` postoji, v. `odredi_snagu`)

    `izvor_tekst` — pun tekst izvornog dokumenta. Ako je prosleđen, svaka
    tvrdnja se u njemu traži (`lociraj_tvrdnju`) i `snaga` se izvodi po DC-005.

    Vraća: {"redovi": [...], "odluke": [{"snaga":..., "izvor_odluke":...,
            "lokacija_poznata":bool, "snaga_prepisana":bool}, ...]}

    NE radi deduplikaciju (INVARIANT 4): idempotentnost ovog toka već drži
    `predmet_dokumenti.klasifikovan_at`, koji `services/case_evolution.py::
    _consequence_evidence_classify` proverava PRE poziva. Drugi, konkurentan
    sistem idempotentnosti bi se sa njim nadmetao, a za njegovu potrebu ne
    postoji dokaz.

    NE dira `deleted_at` (INVARIANT 5): ovo je isključivo putanja upisa; soft
    delete ostaje u `routers/evidence.py::delete_dokaz`, nepromenjen."""
    if not predmet_id or not user_id:
        raise GreskaDokaza("Nedostaje predmet_id ili user_id.")
    if not stavke:
        return {"redovi": [], "odluke": []}

    if proveri_vlasnistvo:
        _proveri_vlasnistvo(supa, predmet_id, user_id)

    izvor_dostupan = bool(izvor_tekst and izvor_tekst.strip())
    provereni_dokumenti: set[str] = set()

    redovi: list[dict] = []
    odluke: list[dict] = []

    for st in stavke:
        tvrdnja = (st.get("tvrdnja") or "").strip()
        if not tvrdnja:
            raise GreskaDokaza("Tvrdnja ne sme biti prazna.")

        kategorija = (st.get("kategorija") or "cinjenica").strip().lower()
        if kategorija not in KATEGORIJE:
            raise GreskaDokaza(
                f"Nepoznata kategorija '{kategorija}'. Dozvoljeno: {', '.join(sorted(KATEGORIJE))}."
            )

        dokument_id = st.get("dokument_id") or None
        if dokument_id and proveri_vlasnistvo and dokument_id not in provereni_dokumenti:
            _proveri_dokument(supa, dokument_id, predmet_id)
            provereni_dokumenti.add(dokument_id)

        # INVARIANT 2 — lokacija se NIKAD ne izmišlja. Bez izvornog teksta
        # ostaju sve četiri kolone NULL.
        lokacija = lociraj_tvrdnju(izvor_tekst, tvrdnja) if izvor_dostupan else dict(_PRAZNA_LOKACIJA)

        snaga_covek = st.get("snaga")
        snaga, izvor_odluke = odredi_snagu(
            tvrdnja, lokacija, izvor_dostupan=izvor_dostupan, snaga_tvrdi_covek=snaga_covek,
        )
        # TASK 003B: provenijencija se PERZISTIRA. Ranije se računala i bacala
        # (v. `odredi_snagu` docstring), pa se iz baze nije moglo dokazati da
        # li je iko procenio snagu.
        _izvor_snage = izvor_snage_iz_odluke(izvor_odluke, snaga)

        # TASK 002A: `nacin` se NE prosleđuje kroz `**lokacija` -- ime ključa i
        # ime kolone se razlikuju, a grounding kolone moraju ostati tačno one
        # četiri koje `KOLONE_GROUNDING` nabraja.
        _nacin = lokacija.pop("nacin", NACIN_NIJE)

        redovi.append({
            # TASK 001: identitet se računa TAČNO JEDNOM, ovde, i skladišti.
            # Nijedno čitanje ga ne preračunava.
            KOLONA_IDENTITET: izracunaj_identitet(predmet_id, tvrdnja),
            # TASK 002A: način pronalaska, izveden iz invarijante u
            # `lociraj_tvrdnju`. Ne utiče ni na `snaga` ni na `identitet`.
            KOLONA_NACIN:     _nacin,
            # TASK 003B: DA LI je procena izvršena. Nikad izvedeno iz `snaga`.
            KOLONA_IZVOR_SNAGE: _izvor_snage,
            "predmet_id":     predmet_id,
            "user_id":        user_id,
            "dokument_id":    dokument_id,
            "tvrdnja":        tvrdnja,
            "kategorija":     kategorija,
            "snaga":          snaga,
            "pravni_element": st.get("pravni_element"),
            "napomena":       st.get("napomena"),
            **lokacija,
        })
        odluke.append({
            "snaga":            snaga,
            "izvor_odluke":     izvor_odluke,
            "izvor_snage":      _izvor_snage,
            "lokacija_poznata": lokacija.get("start_offset") is not None,
            # Eksplicitno, nikad tiho: pozivalac je poslao `snaga`, a DC-005 je
            # bio merodavan i pregazio je.
            "snaga_prepisana":  bool(izvor_dostupan and snaga_covek is not None and str(snaga_covek).strip().lower() != snaga),
        })

    upisani = _insert_sa_fallback(supa, redovi)
    return {"redovi": upisani, "odluke": odluke}


def upisi_dokaz(
    supa,
    *,
    predmet_id: str,
    user_id: str,
    tvrdnja: str,
    kategorija: str = "cinjenica",
    snaga: Optional[str] = None,
    dokument_id: Optional[str] = None,
    pravni_element: Optional[str] = None,
    napomena: Optional[str] = None,
    izvor_tekst: Optional[str] = None,
    proveri_vlasnistvo: bool = True,
) -> dict:
    """Jednostavka omotač oko `upisi_dokaze` — isti kod, ista pravila.

    Vraća {"red": dict|None, "odluka": dict}."""
    rez = upisi_dokaze(
        supa,
        predmet_id=predmet_id,
        user_id=user_id,
        izvor_tekst=izvor_tekst,
        proveri_vlasnistvo=proveri_vlasnistvo,
        stavke=[{
            "tvrdnja": tvrdnja, "kategorija": kategorija, "snaga": snaga,
            "dokument_id": dokument_id, "pravni_element": pravni_element,
            "napomena": napomena,
        }],
    )
    return {
        "red":    (rez["redovi"] or [None])[0],
        "odluka": (rez["odluke"] or [{}])[0],
    }
