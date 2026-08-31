# -*- coding: utf-8 -*-
"""
Vindex AI — Genome Verification Layer (Faza 1.3, 90-dnevni plan 2026-07-18)

Advisory, non-blocking, deterministicka provera Case Genome-a PRE snimanja.
Nula GPT/LLM poziva — cisto proverava strukturu i reference genoma naspram
podataka koji su vec ucitani (dokumenti predmeta), ne AI kritičar. Design
note: docs/architecture/PHASE_1_EXECUTION_CHECKLIST_2026-07-18.md, stavka 1.3.

Scope napomena (Program Beta, 2026-08-04, Olympus Faza 10 governance nalaz --
Architecture Review): modul je nastao Genome-specificno, ali `validate_dok_
reference()` je generalizovan i namerno NIJE Genome-specifican -- koristi ga
i `routers/case_dna.py::compare_docs` (Case Genome-adjacentna, ali odvojena
funkcija). Buduci treci pozivalac van case_dna.py je legitimna upotreba, ne
scope violation.

Obrazac (arhitektonski, ne kod) preuzet iz analiza/validator.py: nikad ne
baca izuzetak, uvek vraca validan dict, sumnjive stavke se premestaju u
flag liste umesto da se tiho odbace. validate_law_refs se REUSE-uje
direktno (import), ne kopira.

Namerno iskljuceno iz v1 (nije zaboravljeno, procenjeno i odlozeno):
- argumenti_za/argumenti_protiv provenance — Genome nema clause_excerpt
  polje kao analiza/validator.py, provera bi trazila izmenu Genome sheme.
- stranke/svedoci/vestaci cross-referencing protiv teksta dokumenta —
  visok rizik laznih pozitiva (OCR varijante, srpska deklinacija imena).
- datumi_kljucni/rokovi_kriticni tekstualno poklapanje — visok rizik
  laznih pozitiva (datumi se cesto preformatiraju u ekstrakciji).

v2 dodaci (Reliability Patch, 2026-07-18, posle CASE_GENOME_REALITY_
VALIDATION_REPORT.md nalaza na 6 sintetickih predmeta):

1. compute_snaga_score() — snaga_predmeta_procent/snaga_predmeta se sada
   RACUNAJU backend-om iz snaga_faktori, ne uzimaju se GPT-ovo samo-
   prijavljenu vrednost. Uzrok originalnog nalaza (svih 6 predmeta vratilo
   IDENTICNIH 65%/"srednja"): sistem prompt u case_dna.py je imao
   BUKVALAN brojcani primer ("snaga_predmeta_procent": 65) u JSON sablonu
   — GPT anchor-uje/kopira taj primer umesto da racuna po predmetu (poznat
   prompt-anchoring bug, potvrdjen time sto se identican obrazac ponovio u
   svih 6 slucajeva na temperaturi 0.1). Isti obrazac (backend racuna
   score, ne trazi se od LLM-a) vec postoji u analiza/validator.py Sloj 10
   (compute_executive_summary) — ovo je nastavak istog principa, ne nova
   ideja.
2. _validate_clan_brojevi() — proverava da broj clana u pravnim citatima
   nije OCIGLEDNO nemoguc (generic gornja granica po tipu zakona), NE
   potvrdjuje da tacan clan stvarno postoji (to bi zahtevalo pravni
   korpus/graf, eksplicitno van obima — "Do not build a graph database,
   do not create a new legal reasoning engine"). Ako je naveden stav,
   dodaje se transparentna napomena da stav nivo nije proveravan.
"""
from __future__ import annotations

import re
import time
from typing import Any, Optional

from analiza.validator import validate_law_refs

_CLAN_PATTERN = re.compile(r"(?:čl\.?|clan|član)\s*0*(\d+)", re.IGNORECASE)
_STAV_PATTERN = re.compile(r"stav\w*\s*0*(\d+)", re.IGNORECASE)

# Namerno siroke/konzervativne aproksimacije, NE precizna pravna baza po
# zakonu — precizne granice po svakom zakonu bi zahtevale pravni korpus/
# graf (eksplicitno van obima v2). Cilj je da uhvati OCIGLEDNO nemoguc broj
# clana (npr. izmisljen clan 5000), ne da potvrdi da tacan broj postoji —
# ta granica ostaje 'nepotvrdjeno' (soft), isto kao ranije.
_USTAV_MAX_CLAN_APPROX = 250
_ZAKON_MAX_CLAN_APPROX = 1200


def _neto_uticaj(faktori: list[dict]) -> int:
    """Zbir svih uticaj vrednosti iz snaga_faktori (npr. '+18', '-8' -> 18, -8).
    Deljeno izmedju compute_snaga_score i _validate_snaga_konzistentnost."""
    neto = 0
    for f in faktori:
        if not isinstance(f, dict):
            continue
        try:
            neto += int(str(f.get("uticaj", "0")).replace("+", ""))
        except (ValueError, TypeError):
            continue
    return neto

_DOK_PATTERN = re.compile(r"DOK-0*(\d+)", re.IGNORECASE)


def _validate_dokazi_rang(genome: dict, docs: list[dict]) -> list[dict]:
    """Hard-flag: dokazi_rang.naziv mora odgovarati stvarnom dokumentu predmeta."""
    poznati_nazivi = {(d.get("naziv_fajla") or "").strip().lower() for d in docs}
    flags = []
    for stavka in genome.get("dokazi_rang") or []:
        naziv = (stavka.get("naziv") or "").strip().lower()
        if naziv and naziv not in poznati_nazivi:
            flags.append({
                "polje": "dokazi_rang",
                "razlog": f"dokument '{stavka.get('naziv')}' ne postoji medju dokumentima predmeta",
                "stavka": stavka.get("naziv"),
            })
    return flags


from shared.contradiction_identity import contradiction_identity  # noqa: E402

def _validate_kontradikcije_lokacije(genome: dict, docs: list[dict]) -> list[dict]:
    """Hard-flag: DOK-XX reference u kontradikcijama moraju odgovarati stvarnim
    redni_broj vrednostima medju dokumentima predmeta."""
    poznati_brojevi = {
        int(d["redni_broj"]) for d in docs
        if str(d.get("redni_broj") or "").isdigit()
    }
    flags = []
    for k in genome.get("kontradikcije") or []:
        for polje in ("lokacija_1", "lokacija_2"):
            vrednost = k.get(polje) or ""
            m = _DOK_PATTERN.search(vrednost)
            if not m:
                continue
            broj = int(m.group(1))
            if broj not in poznati_brojevi:
                flags.append({
                    "polje": f"kontradikcije.{polje}",
                    "razlog": f"'{vrednost}' referencira DOK-{broj:02d} koji ne postoji medju dokumentima predmeta",
                    "stavka": vrednost,
                })
    return flags


def _validate_najslabija_tacka_lokacija(genome: dict, docs: list[dict]) -> list[dict]:
    """Hard-flag: najslabija_tacka.lokacija's DOK-XX reference must match a
    real document. Program Tau, Master Sprint 004 (2026-08-06) -- Legal
    Reasoning Verification found najslabija_tacka/snaga_predmeta_procent were
    the only 2 major Genome fields with zero grounding requirement at all
    (unlike kontradikcije, which already had this exact check). Reuses
    _validate_kontradikcije_lokacije's own pattern verbatim (same DOK_PATTERN,
    same known-document-number set, same hard-flag shape) rather than
    inventing a new mechanism, per this mission's own "no parallel systems"
    rule. An EMPTY lokacija is not an error -- najslabija_tacka is often a
    legitimately holistic judgment with no single grounding document; only a
    reference to a DOK-XX number that doesn't exist is flagged."""
    poznati_brojevi = {
        int(d["redni_broj"]) for d in docs
        if str(d.get("redni_broj") or "").isdigit()
    }
    vrednost = (genome.get("najslabija_tacka") or {}).get("lokacija") or ""
    m = _DOK_PATTERN.search(vrednost)
    if not m:
        return []
    broj = int(m.group(1))
    if broj not in poznati_brojevi:
        return [{
            "polje": "najslabija_tacka.lokacija",
            "razlog": f"'{vrednost}' referencira DOK-{broj:02d} koji ne postoji medju dokumentima predmeta",
            "stavka": vrednost,
        }]
    return []


def _validate_relevantni_zakoni(genome: dict) -> list[dict]:
    """Soft-flag: reuse analiza/validator.py validate_law_refs preko adaptera —
    Genome ima list[str], validate_law_refs ocekuje findings sa law_ref kljucem."""
    zakoni = ((genome.get("pravna_teorija") or {}).get("relevantni_zakoni")) or []
    if not zakoni:
        return []
    adapted = {"findings": [{"law_ref": z} for z in zakoni if z]}
    checked = validate_law_refs(adapted)
    flags = []
    for f in checked.get("findings", []):
        if f.get("unverified_law_ref"):
            flags.append({
                "polje": "pravna_teorija.relevantni_zakoni",
                "razlog": f"'{f.get('law_ref')}' nije prepoznat u poznatoj listi zakona (soft check — moze biti tacan, samo nepotvrdjen)",
                "stavka": f.get("law_ref"),
            })
    return flags


def _validate_clan_brojevi(genome: dict) -> tuple[list[dict], list[dict]]:
    """v2 (Reliability Patch, 2026-07-18) — proverava da broj clana u
    relevantni_zakoni citatima nije OCIGLEDNO nemoguc za tip zakona (Ustav
    ima znatno manje clanova od obicnog zakona). NE potvrdjuje da tacan
    clan stvarno postoji — to bi zahtevalo pravni korpus/graf, van obima.
    Ako je naveden i stav/paragraf, dodaje se soft napomena da taj nivo
    nije proveravan (transparentno, ne cutke ignorisano)."""
    hard: list[dict] = []
    soft: list[dict] = []
    zakoni = ((genome.get("pravna_teorija") or {}).get("relevantni_zakoni")) or []
    for z in zakoni:
        if not z:
            continue
        m = _CLAN_PATTERN.search(z)
        if not m:
            continue
        broj = int(m.group(1))
        is_ustav = "ustav" in z.lower()
        gornja_granica = _USTAV_MAX_CLAN_APPROX if is_ustav else _ZAKON_MAX_CLAN_APPROX
        if broj <= 0 or broj > gornja_granica:
            hard.append({
                "polje": "pravna_teorija.relevantni_zakoni",
                "razlog": f"'{z}' navodi član {broj}, van uobičajenog opsega za ovaj tip zakona (0 < član <= {gornja_granica}) — verovatno izmišljen broj.",
                "stavka": z,
            })
        stav_m = _STAV_PATTERN.search(z)
        if stav_m:
            soft.append({
                "polje": "pravna_teorija.relevantni_zakoni",
                "razlog": f"'{z}' navodi stav {stav_m.group(1)} — nivo stava nije proveravan (van obima v2, samo broj člana).",
                "stavka": z,
            })
    return hard, soft


def compute_snaga_score(genome: dict) -> dict:
    """v2 (Reliability Patch, 2026-07-18) — backend-racunata, objasnjiva
    zamena za GPT-ovo samo-prijavljeno snaga_predmeta_procent/snaga_predmeta.

    Zasto: Reality Validation batch (6 sintetickih predmeta, 2026-07-18)
    pokazao je da SVIH 6 predmeta vraca IDENTICNIH 65%/"srednja" bez obzira
    na dramaticno razlicit sadrzaj predmeta — uzrok je bio bukvalan brojcani
    primer u system promptu koji GPT anchor-uje/kopira. Ovde se procenat
    RACUNA iz vec ekstrahovanih snaga_faktori (koji SU specificni po
    predmetu, potvrdjeno istim batch-om), ne trazi se od LLM-a — isti
    princip kao analiza/validator.py Sloj 10 (compute_executive_summary).

    Formula: baseline 50 (neutralno, ista konvencija kao STROGA PRAVILA u
    system promptu) + neto uticaj snaga_faktori, umanjeno za penal ako je
    genome_kompletnost niska (nedovoljno dokaza za pouzdanu procenu — ovaj
    penal je i sam dodat kao vidljiv, objasnjiv faktor, ne skriveno
    podesavanje). Kategorija (jaka/srednja/slaba) izvedena iz istog broja
    prema vec postojecim pragovima (75+ jaka, <35 slaba, izmedju srednja).

    Vraca {"snaga_predmeta_procent": int, "snaga_predmeta": str,
    "snaga_faktori": list} — snaga_faktori se vraca NAZAD (mozda sa dodatim
    kompletnost-penalom) da explainability ostane tacna za konacan broj."""
    raw_faktori = genome.get("snaga_faktori")
    faktori = list(raw_faktori) if isinstance(raw_faktori, list) else []

    # Operation Single Brain (2026-08-07), AI Boundary gap #8: the exact-string check
    # this replaced (`== "niska"`) only fired for the literal value "niska" -- Genome's
    # own prompt asks for exactly "visoka|srednja|niska" but nothing validated GPT
    # actually returned one of those 3. A synonym/typo ("vrlo niska", wrong case, a
    # stray int) silently skipped the -15 penalty, i.e. treated genuinely-uncertain
    # completeness as if it were fine -- overstating case strength. A genuinely ABSENT
    # field (genome_kompletnost not in the dict at all) is left alone, matching this
    # function's pre-existing, tested baseline-with-no-penalty behavior -- that's a
    # "we don't have a signal" state already priced into the neutral 50 baseline, not
    # a corrupted signal.
    _raw_kompletnost = genome.get("genome_kompletnost")
    if _raw_kompletnost not in (None, ""):
        _s = str(_raw_kompletnost).strip().lower()
        _kompletnost = _s if _s in ("visoka", "srednja", "niska") else "niska"
    else:
        _kompletnost = None

    if _kompletnost == "niska":
        faktori.append({
            "faktor": "Kompletnost dokaznog materijala",
            "uticaj": "-15",
            "opis": "Genome kompletnost ocenjena kao niska — nedovoljno dokumenata za pouzdanu procenu snage predmeta.",
        })

    neto = _neto_uticaj(faktori)
    procent = max(0, min(100, 50 + neto))

    if procent >= 75:
        kategorija = "jaka"
    elif procent < 35:
        kategorija = "slaba"
    else:
        kategorija = "srednja"

    return {
        "snaga_predmeta_procent": procent,
        "snaga_predmeta": kategorija,
        "snaga_faktori": faktori,
    }


def _validate_snaga_konzistentnost(genome: dict) -> tuple[list[dict], list[dict]]:
    """Interna konzistentnost (ne provenance protiv dokumenata):
    - snaga_predmeta_procent ne sme da protivreci neto smeru snaga_faktori.
    - dokazi_rang.zvezdice ne sme daleko odstupati od round(snaga_score/20),
      formula koju sam ekstrakcioni prompt definise ali nikad ne proverava."""
    hard: list[dict] = []
    soft: list[dict] = []

    procent = genome.get("snaga_predmeta_procent")
    faktori = genome.get("snaga_faktori") or []
    if isinstance(procent, (int, float)) and faktori:
        neto = _neto_uticaj(faktori)
        if procent >= 65 and neto < 0:
            hard.append({
                "polje": "snaga_predmeta_procent",
                "razlog": f"procenat je visok ({procent}%) ali je neto uticaj snaga_faktori negativan ({neto})",
                "stavka": procent,
            })
        elif procent <= 35 and neto > 0:
            hard.append({
                "polje": "snaga_predmeta_procent",
                "razlog": f"procenat je nizak ({procent}%) ali je neto uticaj snaga_faktori pozitivan ({neto})",
                "stavka": procent,
            })

    for stavka in genome.get("dokazi_rang") or []:
        score = stavka.get("snaga_score")
        zvezdice = stavka.get("zvezdice")
        if isinstance(score, (int, float)) and isinstance(zvezdice, (int, float)):
            ocekivano = round(score / 20)
            if abs(ocekivano - zvezdice) >= 2:
                soft.append({
                    "polje": "dokazi_rang.zvezdice",
                    "razlog": f"'{stavka.get('naziv')}' ima {zvezdice} zvezdica ali score={score} implicira ~{ocekivano}",
                    "stavka": stavka.get("naziv"),
                })

    return hard, soft


def validate_dok_reference(text: Optional[str], poznati_brojevi: set[int], polje: str = "koji_je_jaci_dokaz") -> list[dict]:
    """Program Beta (2026-08-04) — generalization of _validate_kontradikcije_
    lokacije's principle (a DOK-XX reference must point to a document that
    actually exists in scope) for Compare's DOK-XX-bearing free-text fields
    (`koji_je_jaci_dokaz`, and per Olympus Faza 10 governance nalaz --
    AI Grounding -- also `kontradikcije`/`razlike_kljucne`, which use the
    same convention but as list-of-string fields; caller iterates and passes
    `polje` per item). Not Genome-specific: reusable by any caller with a
    small known set of DOK-XX numbers. No DOK-XX pattern in the text (e.g.
    "ravnopravni") is not an error — only a reference to a DOK-XX number
    OUTSIDE the known set is flagged (an invented document).

    Olympus Faza 10 governance nalaz (2026-08-04, Backend Reliability): ne
    pretpostavlja da je `text` string samo zato sto prompt schema to trazi --
    `response_format=json_object` garantuje samo validan JSON objekat na
    vrhu, ne tip svakog polja. Non-string ulaz (npr. GPT vratio listu/dict
    umesto stringa) se tiho ignorise (prazna lista), ne baca TypeError."""
    if not isinstance(text, str) or not text:
        return []
    flags = []
    for m in _DOK_PATTERN.finditer(text):
        broj = int(m.group(1))
        if broj not in poznati_brojevi:
            flags.append({
                "polje": polje,
                "razlog": f"'{text}' referencira DOK-{broj:02d} koji nije medju uporedjenim dokumentima — moguc izmisljen dokument.",
                "stavka": text,
            })
    return flags


def validate_graph_edge_references(nodes: list, edges: list) -> list[dict]:
    """Program Gamma (2026-08-04) — same principle as validate_dok_reference
    ("a referenced entity must actually exist in scope, not be invented"),
    extended to Evidence Graph's node-id scheme (freeform strings like
    'dok_ugovor', not DOK-NN numbers, so validate_dok_reference's regex does
    not apply directly — the underlying check is identical: does the edge's
    izvor/cilj match a real node.id in the same graph). Catches a GPT-invented
    edge endpoint (e.g. an OSPORAVA contradiction edge pointing at a node.id
    that was never actually extracted) — the same "hallucinated reference"
    shape validate_dok_reference already proved out for Compare/Genome, not a
    new invention. Never raises; malformed nodes/edges are skipped, not
    fatal (same fail-soft convention as verify_genome)."""
    try:
        poznati_id = {n.get("id") for n in (nodes or []) if isinstance(n, dict) and n.get("id")}
    except Exception:
        return []
    flags = []
    for e in (edges or []):
        if not isinstance(e, dict):
            continue
        for polje in ("izvor", "cilj"):
            vrednost = e.get(polje)
            if vrednost and vrednost not in poznati_id:
                flags.append({
                    "polje": f"edges.{polje}",
                    "razlog": f"grana '{e.get('tip_veze','?')}' referencira cvor '{vrednost}' koji ne postoji medju ekstrahovanim entitetima — moguc izmisljen entitet.",
                    "stavka": vrednost,
                })
    return flags


def validate_predmet_reference(predmet_id_prefix: Optional[str], poznati: dict, predmet_naziv: Optional[str] = None) -> list[dict]:
    """Program Gamma (2026-08-04) — same "referenced entity must exist in
    scope" principle as validate_dok_reference/validate_graph_edge_references,
    applied to Case Commander's cross-case findings, which reference a
    predmet by its ID prefix (`nalaz.predmet_id_prefix`) rather than a DOK-NN
    number or a graph node id. `poznati` maps prefix -> real naziv (not a
    bare set) so a SECOND check is possible.

    Olympus Faza 10 governance nalaz (2026-08-04, Evidence Integrity): the
    original v1 only checked existence (prefix in known set) -- a finding
    with a REAL prefix but a MISATTRIBUTED name/facts (GPT confused two
    predmeti in the same portfolio) was architecturally invisible. Now also
    checks predmet_naziv against the real naziv for that prefix when both
    are present -- fuzzy (substring, case-insensitive) not exact, since
    minor paraphrasing of a case name is not itself a defect."""
    if not isinstance(predmet_id_prefix, str) or not predmet_id_prefix:
        return []
    if predmet_id_prefix not in poznati:
        return [{
            "polje": "predmet_id_prefix",
            "razlog": f"nalaz referencira predmet ID prefiks '{predmet_id_prefix}' koji nije medju analiziranim predmetima — moguc izmisljen/pogresno pripisan nalaz.",
            "stavka": predmet_id_prefix,
        }]
    stvarni_naziv = (poznati.get(predmet_id_prefix) or "").strip().lower()
    if isinstance(predmet_naziv, str) and predmet_naziv.strip() and stvarni_naziv:
        dati_naziv = predmet_naziv.strip().lower()
        if dati_naziv not in stvarni_naziv and stvarni_naziv not in dati_naziv:
            return [{
                "polje": "predmet_naziv",
                "razlog": f"nalaz referencira predmet ID prefiks '{predmet_id_prefix}' sa nazivom '{predmet_naziv}', ali stvaran naziv tog predmeta je '{poznati.get(predmet_id_prefix)}' — moguc pogresno pripisan nalaz (pomesan predmet).",
                "stavka": predmet_naziv,
            }]
    return []



def _validate_kontradikcije_oblik(genome: dict) -> tuple[list[dict], list[dict]]:
    """A009 -- MNOGOSTRUKOST I OBLIK LISTE KONTRADIKCIJA.

    A005 je izmerio da isti par dokumenata moze nositi dve nezavisne sporne
    tacke, i da ih proizvodjac ume da spoji u jedan zapis. Producer ugovor je
    zato dopunjen eksplicitnom kardinalnoscu (`routers/case_dna.py`,
    _GENOME_SYSTEM). Ova provera je deterministicki deo tog ugovora: proverava
    OBLIK, nikad znacenje.

    Sta se NAMERNO ne proverava: da li su dve stavke "zapravo ista sporna
    tacka" i da li jedna stavka "zapravo pokriva dve". To bi trazilo semanticko
    poredjenje, koje je A008 oborio (`CANONICALIZATION != SEMANTIC IDENTITY`) i
    koje pripada V2 domenskom sloju (`shared/issue_v2.py`), ne validatoru.

    Izolacija po stavci je obavezna: jedna neispravna kontradikcija sme dati
    flag samo za sebe i NE SME oboriti niti sakriti ispravne susede -- inace bi
    validacija postala nov izvor tihog gubitka, tacno onaj koji A009 zatvara.

    Prazna lista je VALIDNA -- predmet bez kontradikcije je legitiman ishod."""
    hard: list[dict] = []
    soft: list[dict] = []
    if "kontradikcije" not in genome:
        return hard, soft

    stavke = genome.get("kontradikcije")
    if stavke is None:
        return hard, soft
    if not isinstance(stavke, list):
        return ([{
            "polje": "kontradikcije",
            "razlog": f"mora biti lista, dobijeno {type(stavke).__name__} -- skalarni izlaz "
                      f"strukturno onemogucava vise od jedne kontradikcije",
            "stavka": str(stavke)[:120],
        }], soft)

    videni: dict[tuple, int] = {}
    for i, k in enumerate(stavke):
        if not isinstance(k, dict):
            hard.append({
                "polje": f"kontradikcije[{i}]",
                "razlog": f"stavka nije objekat nego {type(k).__name__}",
                "stavka": str(k)[:120],
            })
            continue

        opis = (k.get("opis") or "").strip() if isinstance(k.get("opis"), str) else ""
        lok = [k.get(p) for p in ("lokacija_1", "lokacija_2")]
        ima_lok = any(isinstance(x, str) and x.strip() for x in lok)
        if not opis and not ima_lok:
            hard.append({
                "polje": f"kontradikcije[{i}]",
                "razlog": "stavka nema ni opis ni ijednu lokaciju -- prazan nalaz",
                "stavka": "",
            })
            continue

        # Doslovan duplikat: identicna kontradikcija zapisana dvaput. Poredi se
        # SAMO na tacnu jednakost normalizovanog opisa i vec postojeceg
        # identiteta lokacija -- bez slicnosti, bez pragova.
        kljuc = (contradiction_identity(k), " ".join(opis.lower().split()))
        if kljuc in videni:
            soft.append({
                "polje": f"kontradikcije[{i}]",
                "razlog": f"doslovan duplikat stavke #{videni[kljuc]} (isti opis i iste lokacije)",
                "stavka": opis[:120],
            })
        else:
            videni[kljuc] = i

    return hard, soft

def verify_genome(genome: dict, docs: list[dict]) -> dict[str, Any]:
    """Glavna ulazna tacka — Faza 1.3. Nula GPT poziva, nula I/O (docs je vec
    ucitan od strane pozivaoca). Nikad ne baca izuzetak — greska u jednoj
    proveri se preskace (logovana implicitno kroz prazan rezultat te
    provere), ne obara ostatak niti glavni zahtev.

    Vraca advisory rezultat — poziv ga upisuje u genome["_verifikacija"] i
    NASTAVLJA da snima genom bez obzira na odluku. 'require_review' je
    status, ne blokada."""
    start = time.monotonic()
    hard: list[dict] = []
    soft: list[dict] = []

    for fn, bucket in (
        (lambda: _validate_dokazi_rang(genome, docs), hard),
        (lambda: _validate_kontradikcije_lokacije(genome, docs), hard),
        (lambda: _validate_najslabija_tacka_lokacija(genome, docs), hard),
        (lambda: _validate_relevantni_zakoni(genome), soft),
    ):
        try:
            bucket.extend(fn())
        except Exception:
            pass

    try:
        o_hard, o_soft = _validate_kontradikcije_oblik(genome)
        hard.extend(o_hard)
        soft.extend(o_soft)
    except Exception:
        pass

    try:
        k_hard, k_soft = _validate_snaga_konzistentnost(genome)
        hard.extend(k_hard)
        soft.extend(k_soft)
    except Exception:
        pass

    try:
        c_hard, c_soft = _validate_clan_brojevi(genome)
        hard.extend(c_hard)
        soft.extend(c_soft)
    except Exception:
        pass

    if hard:
        odluka = "require_review"
    elif soft:
        odluka = "approve_with_warning"
    else:
        odluka = "approve"

    return {
        "odluka": odluka,
        "hard_flags": hard,
        "soft_flags": soft,
        "provereno_u_ms": round((time.monotonic() - start) * 1000, 2),
    }
