# -*- coding: utf-8 -*-
"""
Vindex AI — shared/issue_v2.py

CONTRADICTION V2 — DOMENSKO JEZGRO (čist modul, bez baze i bez LLM-a).

Zamenjuje model koji je forenzički oboren u A005–A008:

    STARO:  kontradikcija = par LOKACIJA dokumenata
            identitet = sha256("kontradikcija|lokacija_1|lokacija_2")
            → A005: dve nezavisne kontradikcije nad istim parom dokumenata
              dobijaju ISTI ključ (9/9 merenja) i jedna se TIHO gubi u
              `services/case_evolution.py:1052`.

    NOVO:   SPORNA TAČKA (ISSUE) je nosilac kontinuiteta.
            Kontradikcija je STANJE nespojivosti pod tom spornom tačkom.
            Tvrdnje su ČLANOVI, promenljivi kroz vreme.

Definicija sporne tačke (A008, izvedena i testirana negativnim primerima):

    ISSUE = pitanje o predmetu koje ima međusobno isključive kandidat-odgovore
            i koje predmet ne može zaobići dok se ne razreši.

## Šta je ovde NAMERNO odsutno

* Nema heša teksta kao identiteta. A008 je izmerio da postojeći kanonizator nad
  sinonimima daje 5 različitih identiteta od 7 ulaza koji znače isti spor, a
  istovremeno spaja dva različita spora sa istim labelom (`"visina duga"`).
  `CANONICALIZATION != SEMANTIC IDENTITY`.
* Nema poklapanja po pragu preklapanja („isto ako dele 2 od 3 tvrdnje"),
  nema sličnosti stringova, nema embeddinga, nema LLM-poređenja. Svaki od tih
  mehanizama rekonstruiše A005 kvar u sofisticiranijem obliku.
* Nema `dedupe_key`-a. On u postojećem sistemu nosi PET pojmova sa TRI različita
  opsega jedinstvenosti (A006) i ne sme postati novi univerzalni identitet.

## Šta jeste identitet

`issue_id` je UUID koji generiše SISTEM pri prvom nastanku sporne tačke i koji
se posle toga NIKAD ne preračunava. Ne izvodi se iz labela, teksta tvrdnje,
dokumenata, lokacije, tipa relacije ni iz ijednog LLM izlaza.

Isti presedan već postoji u repou: `predmet_dokazi.identitet` (migracija 116) je
SKLADIŠTENA kolona baš zato da promena pravila kanonizacije ne prepiše postojeće
identitete.

## Pravilo kontinuiteta — deterministički skupovni odnos, ne prag

Za dolazeći skup tvrdnji `U` i postojeće otvorene sporne tačke `T_i` sa
tekućim članstvom `S_i`, kandidat je svaka tema za koju važi:

    S_i == U   ili   S_i ⊆ U   ili   U ⊆ S_i

    tačno 1 kandidat  → CONTINUATION
    0 kandidata       → NEW_ISSUE
    ≥ 2 kandidata     → REVIEW_REQUIRED   (fail-closed, nikad pogađanje)

Ovo NIJE prag preklapanja: `{C1,C2,C3}` i `{C2,C3,C4}` **nisu** u odnosu
podskupa ni u jednom smeru, pa se ne spajaju iako dele dva člana (A005 §22).

### Poznato ograničenje, namerno ostavljeno otvoreno

Zamena člana (`{C1,C2} → {C1,C2'}`) nije ni podskup ni nadskup, pa daje
`NEW_ISSUE` ili `REVIEW_REQUIRED`, ne tihi kontinuitet. To je svesna odluka:
ne postoji deterministički dokaz da je to isti spor, a izmišljanje kontinuiteta
je tačno klasa greške koju ovaj modul postoji da spreči.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Iterable, Optional

# ─── Domen tipa relacije ─────────────────────────────────────────────────────
# Samo dva oblika su dokazana produkcionim podacima (A007 §9): sudar dve
# činjenice, i sudar činjenice sa normom (`e0a54af1` v1: DOK-01 ↔ "Zakon o radu
# cl. 179"). Šira ontologija se NE uvodi bez dokaza.
RELACIJA_CINJENICA_CINJENICA = "cinjenica_cinjenica"
RELACIJA_CINJENICA_NORMA     = "cinjenica_norma"
RELACIJE: frozenset[str] = frozenset({RELACIJA_CINJENICA_CINJENICA, RELACIJA_CINJENICA_NORMA})

# ─── Životni ciklus sporne tačke ─────────────────────────────────────────────
STATUS_OTKRIVENA  = "DISCOVERED"   # provizorna: vidljiva, ali bez trajnih posledica
STATUS_POTVRDJENA = "CONFIRMED"    # advokat potvrdio — tek tada sme nositi akcije
STATUS_RAZRESENA  = "RESOLVED"
STATUS_PONOVO     = "REOPENED"
STATUS_SPOJENA    = "MERGED"
STATUSI: frozenset[str] = frozenset(
    {STATUS_OTKRIVENA, STATUS_POTVRDJENA, STATUS_RAZRESENA, STATUS_PONOVO, STATUS_SPOJENA}
)
STATUSI_OTVORENI: frozenset[str] = frozenset({STATUS_OTKRIVENA, STATUS_POTVRDJENA, STATUS_PONOVO})

# ─── Stanje kontradikcije ────────────────────────────────────────────────────
# `NOT_OBSERVED` postoji zato što je A006 §9 dokazao da sistem danas pet
# različitih domenskih događaja zapisuje identično (`closed`), i time tiho
# proglašava razrešenim ono što je samo izostalo iz izlaza.
STANJE_OTVORENA     = "OPEN"
STANJE_RAZRESENA    = "RESOLVED"
STANJE_NIJE_VIDJENA = "NOT_OBSERVED"
STANJE_PREVAZIDJENA = "SUPERSEDED"
STANJE_PREGLED      = "REVIEW_REQUIRED"
STANJA: frozenset[str] = frozenset(
    {STANJE_OTVORENA, STANJE_RAZRESENA, STANJE_NIJE_VIDJENA, STANJE_PREVAZIDJENA, STANJE_PREGLED}
)

# ─── Ishodi razrešavanja kontinuiteta ────────────────────────────────────────
ODLUKA_NOVA        = "NEW_ISSUE"
ODLUKA_NASTAVAK    = "CONTINUATION"
ODLUKA_PREGLED     = "REVIEW_REQUIRED"
ODLUKA_NEISPRAVNO  = "INVALID"
ODLUKA_DUPLIKAT    = "DUPLICATE"

# Kontradikcija traži najmanje dve MEĐUSOBNO RAZLIČITE tvrdnje. Jedna tvrdnja
# nije spor — to je samo tvrdnja.
MIN_TVRDNJI = 2


def otisak_pocetnog_skupa(claim_set) -> str:
    """A010 -- OTISAK POCETNOG SKUPA TVRDNJI. NIJE identitet.

    Identitet sporne tacke ostaje UUID koji generise baza. Ovo je iskljucivo
    zastita od duplikata pri ISTOVREMENOM kreiranju (migracija 120): dva
    paralelna Genome refresh-a nad istim ulazom oba vide "0 kandidata" jer ne
    vide tudji jos-neupisani red, pa oba kreiraju novu spornu tacku.

    Ulaz su `predmet_dokazi.id` vrednosti -- identiteti IZ BAZE, ne tekst,
    ne label, ne LLM izlaz. Zato ovo ne krsi A008 I12 ("identitet sporne tacke
    ne sme biti izveden iz LLM izlaza"): heš se ne koristi KAO identitet, nego
    kao jedinstvenost na nivou baze.

    Deterministicki i nezavisan od redosleda -- skup se sortira pre hesiranja."""
    uredjeni = sorted(str(x) for x in (claim_set or ()) if x)
    if not uredjeni:
        raise GreskaTeme("Otisak trazi bar jednu tvrdnju.")
    return hashlib.sha256(("|".join(uredjeni)).encode("utf-8")).hexdigest()


class GreskaTeme(ValueError):
    """Ulaz koji se ne sme prihvatiti. Namerno `ValueError`, ne `HTTPException`:
    `shared/` ne sme da zna za HTTP sloj (isti obrazac kao `GreskaDokaza`)."""

    def __init__(self, poruka: str, *, razlog: str = ODLUKA_NEISPRAVNO):
        super().__init__(poruka)
        self.poruka = poruka
        self.razlog = razlog


# ═══════════════════════════════════════════════════════════════════════════
# 1. IDENTITET — vlasnik je sistem, nikad proizvođač
# ═══════════════════════════════════════════════════════════════════════════

def novi_issue_id() -> str:
    """JEDINI generator identiteta sporne tačke.

    Namerno `uuid4`, a NE heš sadržaja: identitet ne sme zavisiti ni od jednog
    polja koje se može promeniti (label, tvrdnje, dokumenti, lokacija, tip
    relacije). Sve to su podaci O spornoj tački, a ne ona sama.

    Posledica koju ovo garantuje, a heš ne bi: promena labela iz
    „datum prestanka radnog odnosa" u „dan prestanka zaposlenja" NE stvara novu
    spornu tačku."""
    return str(uuid.uuid4())


def novi_kontradikcija_id() -> str:
    """Identitet kontradikcije. Odvojen od identiteta sporne tačke jer jedna
    sporna tačka sme nositi više kontradikcija — po tipu relacije (A008 §6)."""
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════════
# 2. VALIDACIJA PROIZVOĐAČEVOG IZLAZA
# ═══════════════════════════════════════════════════════════════════════════

def _kao_lista(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else []


def validiraj_claim_ref(
    ref: Any, predmet_id: str, poznati_dokazi: dict[str, dict]
) -> Optional[str]:
    """Razrešava JEDNU referencu na tvrdnju u `predmet_dokazi.id`.

    Vraća `id` ako je referenca dokaziva, inače `None`. NIKAD ne pogađa i nikad
    ne pada nazad na naziv dokumenta, lokaciju ili tekst — isti fail-closed
    obrazac koji A002 već primenjuje na `DOK-NN`.

    Sintaksno ispravan UUID koji proizvođač izmisli NIJE dovoljan: red mora
    postojati, pripadati OVOM predmetu i ne sme biti obrisan. Time je zatvoren
    i cross-case napad — referenca iz tuđeg predmeta se ne razrešava."""
    if not isinstance(ref, str) or not ref.strip():
        return None
    red = poznati_dokazi.get(ref.strip())
    if not isinstance(red, dict):
        return None
    if red.get("predmet_id") != predmet_id:
        return None                       # cross-case / cross-tenant — odbij
    if red.get("deleted_at") is not None:
        return None                       # obrisana tvrdnja nije član spora
    return ref.strip()


def validiraj_predlog_teme(
    predlog: Any, predmet_id: str, poznati_dokazi: dict[str, dict]
) -> dict:
    """Validira JEDAN predlog sporne tačke iz proizvođačevog izlaza.

    Vraća `{"ok": bool, "razlog": str, "claim_set": frozenset, "label": str|None,
             "relation_type": str|None, "odbacene_reference": list}`.

    Label sme biti `None` — identitet ne zavisi od njega (A008 §13). Prikazni
    naziv se u tom slučaju izvodi kasnije, i to je stvar prikaza, ne domena."""
    if not isinstance(predlog, dict):
        return {"ok": False, "razlog": "predlog nije objekat", "claim_set": frozenset(),
                "label": None, "relation_type": None, "odbacene_reference": []}

    # `isinstance` PRE provere članstva: neheširana vrednost (dict/list) bi na
    # `in RELACIJE` podigla `TypeError` umesto da padne zatvoreno. Isti obrazac
    # koji `shared/contradiction_identity.py::normalize_tezina` već primenjuje
    # nad slobodnim GPT izlazom — JSON bez šeme sme vratiti bilo šta.
    rel = predlog.get("relation_type")
    if not isinstance(rel, str) or rel not in RELACIJE:
        return {"ok": False, "razlog": f"nepoznat relation_type: {rel!r}",
                "claim_set": frozenset(), "label": None, "relation_type": None,
                "odbacene_reference": []}

    sirove = _kao_lista(predlog.get("claim_refs"))
    razresene: list[str] = []
    odbacene: list[Any] = []
    for r in sirove:
        v = validiraj_claim_ref(r, predmet_id, poznati_dokazi)
        (razresene if v else odbacene).append(v if v else r)

    # Dupli unos iste tvrdnje nije dva člana. Skup je i nosilac nezavisnosti od
    # redosleda: `[C1, C2]` i `[C2, C1]` daju identičan `claim_set`.
    claim_set = frozenset(razresene)
    if len(claim_set) < MIN_TVRDNJI:
        return {"ok": False,
                "razlog": f"manje od {MIN_TVRDNJI} razlicite validne tvrdnje "
                          f"({len(claim_set)} razresenih, {len(odbacene)} odbacenih)",
                "claim_set": claim_set, "label": None, "relation_type": rel,
                "odbacene_reference": odbacene}

    lab = predlog.get("issue_label")
    lab = lab.strip() if isinstance(lab, str) and lab.strip() else None

    return {"ok": True, "razlog": "", "claim_set": claim_set, "label": lab,
            "relation_type": rel, "odbacene_reference": odbacene}


# ═══════════════════════════════════════════════════════════════════════════
# 3. DETERMINISTIČKO RAZREŠAVANJE KONTINUITETA
# ═══════════════════════════════════════════════════════════════════════════

def _kandidati(claim_set: frozenset, postojece: Iterable[dict]) -> list[dict]:
    """Postojeće sporne tačke u odnosu podskupa/nadskupa sa dolazećim skupom.

    Prazno članstvo se PRESKAČE: prazan skup je podskup svega, pa bi tema bez
    članova postala kandidat za svaki dolazeći predlog."""
    out = []
    for t in postojece:
        if t.get("status") not in STATUSI_OTVORENI:
            continue
        s = frozenset(t.get("claim_set") or ())
        if not s:
            continue
        if s == claim_set or s <= claim_set or claim_set <= s:
            out.append(t)
    return out


def razresi_kontinuitet(claim_set: frozenset, postojece_teme: Iterable[dict]) -> dict:
    """Odlučuje da li dolazeći skup tvrdnji nastavlja postojeću spornu tačku.

    `postojece_teme` MORA već biti ograničeno na jedan predmet — opseg je deo
    identiteta (A008 I1), i ovaj modul ga ne proširuje.

    Vraća `{"odluka": …, "issue_id": str|None, "kandidati": [id, …]}`.

    Odnos podskupa nije prag: dodavanje člana (`{C1,C2} ⊆ {C1,C2,C3}`) i
    izostanak člana (`{C1,C2} ⊆ {C1,C2,C3}`) jesu kontinuitet, a preklapanje
    bez sadržavanja (`{C1,C2,C3}` vs `{C2,C3,C4}`) nije."""
    if not claim_set:
        return {"odluka": ODLUKA_NEISPRAVNO, "issue_id": None, "kandidati": []}

    postojece = list(postojece_teme)
    kand = _kandidati(claim_set, postojece)
    ids = sorted(str(t.get("issue_id")) for t in kand)   # sortirano: nezavisno od redosleda ulaza

    if len(kand) == 1:
        return {"odluka": ODLUKA_NASTAVAK, "issue_id": str(kand[0].get("issue_id")),
                "kandidati": ids}
    if len(kand) > 1:
        # Više branjivih kandidata — sistem NE ZNA koji je. To je ispravan
        # ishod, ne neuspeh (A008 §14).
        return {"odluka": ODLUKA_PREGLED, "issue_id": None, "kandidati": ids}

    # Nula kandidata po sadržavanju. Pre nego što se proglasi NOVA tema,
    # proveri deli li dolazeći skup ijednu tvrdnju sa nekom otvorenom temom.
    # Presek NIJE dokaz istovetnosti i ovde NIKAD ne uspostavlja identitet — on
    # samo sprečava TIHO cepanje spora kada je zamenjen član (`{C1,C2}` →
    # `{C1,C2'}`). Takav slučaj ide na ljudski pregled.
    #
    # Ovo je izričito dozvoljena upotreba preklapanja: kao signal za
    # `REVIEW_REQUIRED`, ne kao identitet.
    dodiruju = sorted(
        str(t.get("issue_id")) for t in postojece
        if t.get("status") in STATUSI_OTVORENI
        and frozenset(t.get("claim_set") or ()) & claim_set
    )
    if dodiruju:
        return {"odluka": ODLUKA_PREGLED, "issue_id": None, "kandidati": dodiruju}

    # Nijedna zajednička tvrdnja ni sa jednom otvorenom temom → nema osnova ni
    # za kontinuitet ni za sumnju. Nova tema nastaje kao PROVIZORNA
    # (`DISCOVERED`) i ne nosi trajne posledice dok je advokat ne potvrdi.
    return {"odluka": ODLUKA_NOVA, "issue_id": None, "kandidati": []}


def razresi_paket(
    predlozi: Any, predmet_id: str, poznati_dokazi: dict[str, dict],
    postojece_teme: Iterable[dict],
) -> list[dict]:
    """Razrešava CEO proizvođačev paket, čuvajući mnogostrukost.

    Ovo je mesto na kojem je stari sistem gubio podatke: `{a["dedupe_key"]: a}`
    je dva predloga sa istim ključem svodio na jedan, tiho i bez traga
    (`services/case_evolution.py:1052`). Ovde se svaki predlog razrešava
    ZASEBNO i svaki dobija sopstveni ishod — ništa se ne sažima.

    Duplikat unutar istog paketa (identičan `claim_set`) se prijavljuje kao
    `DUPLICATE`, ne kao tihi gubitak. Dva predloga sa sličnim labelima a
    različitim skupovima tvrdnji ostaju DVA predloga — nema spajanja po tekstu."""
    postojece = list(postojece_teme)
    rezultati: list[dict] = []
    # A016.7: ključ je (skup tvrdnji, TIP RELACIJE), ne samo skup tvrdnji.
    #
    # Uži ključ je spajao dve RAZLIČITE kontradikcije u jednu (izmereno: dva
    # predloga nad istim tvrdnjama, jedan `cinjenica_cinjenica` i jedan
    # `cinjenica_norma`, davali su 1 upisiv umesto 2). To je ista klasa gubitka
    # zbog koje je `dedupe_key` i uklonjen — samo pomerena jedan sloj dublje.
    #
    # Širi ključ nije izabran nego IZVEDEN iz već kanonskog ugovora baze:
    # `idx_contradiction_open_per_issue_relation` je UNIQUE nad
    # `(issue_id, relation_type) WHERE state='OPEN'` (migracija 119:89), a
    # `v2_persist_contradiction` traži postojeću kontradikciju baš po tom paru.
    # Python i baza sada dedupliciraju po ISTOM ključu.
    #
    # Sporna tačka ostaje jedna: drugi predlog se razrešava kao CONTINUATION nad
    # temom koju je prvi stvorio, pa nastaje 1 ISSUE sa 2 KONTRADIKCIJE — tačno
    # ono što model ISSUE 1:N CONTRADICTION i propisuje.
    videni: dict[tuple[frozenset, str], int] = {}

    for i, p in enumerate(_kao_lista(predlozi)):
        v = validiraj_predlog_teme(p, predmet_id, poznati_dokazi)
        if not v["ok"]:
            rezultati.append({"indeks": i, "odluka": ODLUKA_NEISPRAVNO, "issue_id": None,
                              "claim_set": v["claim_set"], "label": v["label"],
                              "relation_type": v["relation_type"], "kandidati": [],
                              "razlog": v["razlog"], "odbacene_reference": v["odbacene_reference"]})
            continue

        cs = v["claim_set"]
        kljuc = (cs, v["relation_type"])
        if kljuc in videni:
            rezultati.append({"indeks": i, "odluka": ODLUKA_DUPLIKAT, "issue_id": None,
                              "claim_set": cs, "label": v["label"],
                              "relation_type": v["relation_type"], "kandidati": [],
                              "razlog": f"identican skup tvrdnji I tip relacije kao predlog #{videni[kljuc]}",
                              "odbacene_reference": v["odbacene_reference"]})
            continue
        videni[kljuc] = i

        r = razresi_kontinuitet(cs, postojece)
        rezultati.append({"indeks": i, "odluka": r["odluka"], "issue_id": r["issue_id"],
                          "claim_set": cs, "label": v["label"],
                          "relation_type": v["relation_type"], "kandidati": r["kandidati"],
                          "razlog": "", "odbacene_reference": v["odbacene_reference"]})

        # Novonastala tema ulazi u skup kandidata za ostatak istog paketa, da
        # dva predloga u istom pozivu ne bi nezavisno stvorila dve teme nad
        # skupovima koji su u odnosu sadržavanja.
        if r["odluka"] == ODLUKA_NOVA:
            postojece.append({"issue_id": f"__nova__{i}", "status": STATUS_OTKRIVENA,
                              "claim_set": cs})

    return rezultati


# ═══════════════════════════════════════════════════════════════════════════
# 4. PROMENA ČLANSTVA — šta je izostalo, a šta je razrešeno
# ═══════════════════════════════════════════════════════════════════════════

def delta_clanstva(staro: Iterable[str], novo: Iterable[str]) -> dict:
    """Razlika u članstvu tvrdnji između dva posmatranja iste sporne tačke.

    Izostala tvrdnja se označava kao `NOT_OBSERVED`, NIKAD kao `RESOLVED`.
    Razlog je izmeren, ne pretpostavljen: A005 je pokazao da dodavanje trećeg
    dokumenta uklanja nalaze koje je korpus od dva dokumenta davao 3/3 — dakle
    izostanak iz izlaza nije dokaz da je spor rešen."""
    s, n = frozenset(staro or ()), frozenset(novo or ())
    return {"dodate": sorted(n - s), "izostale": sorted(s - n), "zadrzane": sorted(s & n),
            "izostale_stanje": STANJE_NIJE_VIDJENA}
