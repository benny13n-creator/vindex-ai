# -*- coding: utf-8 -*-
"""
Vindex AI — services/law_brain.py

NS008 — Law Brain: kanonski sloj ČITANJA + POVERENJA + SINTEZE nad postojećim vlasnicima domena.
Nije nova baza znanja, nije drugi Genome, nije drugi Pinecone univerzum. Ništa ovde ne poseduje istinu:
svaka stavka nosi referencu na pravi izvorni red (`source_ref`) i lanac porekla (`lineage`).

PRAVILA
  • Klasa poverenja je zaključan skup (TRUST_CLASSES). `human_verified` se NE prosleđuje — izvodi se iz klase,
    pa AI klasa nikad ne može da bude „ljudski proverena" greškom pozivaoca.
  • Validnost se ne izmišlja: bez podatka o važenju → UNKNOWN. Izvor bez porekla → UNKNOWN_LEGACY.
  • Deterministično: isti ulaz = isti izlaz (bez modela, bez slučajnosti, bez trenutnog vremena osim ako ga
    pozivalac ne prosledi).
  • Law Brain NIJE pravni autoritet: iskustvo kancelarije ≠ zakon/sudska praksa (AUTHORITY_NOTICE).
  • Izvod (`excerpt`) je ograničen; pun sadržaj ostaje u izvoru.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

# ─── Klase poverenja (zaključane direktivom NS008) ──────────────────────────
HUMAN_CONFIRMED_OUTCOME = "HUMAN_CONFIRMED_OUTCOME"
LAWYER_VERIFIED_ARTIFACT = "LAWYER_VERIFIED_ARTIFACT"
HUMAN_MEMORY_NOTE = "HUMAN_MEMORY_NOTE"
HUMAN_CORRECTION = "HUMAN_CORRECTION"
EXPLICIT_GRAPH_RELATION = "EXPLICIT_GRAPH_RELATION"
SOURCE_CASE_FACT = "SOURCE_CASE_FACT"
AI_CANDIDATE_LESSON = "AI_CANDIDATE_LESSON"
AI_WORK_PRODUCT = "AI_WORK_PRODUCT"
UNKNOWN_LEGACY = "UNKNOWN_LEGACY"

TRUST_CLASSES = (
    HUMAN_CONFIRMED_OUTCOME, LAWYER_VERIFIED_ARTIFACT, HUMAN_MEMORY_NOTE, HUMAN_CORRECTION,
    EXPLICIT_GRAPH_RELATION, SOURCE_CASE_FACT, AI_CANDIDATE_LESSON, AI_WORK_PRODUCT, UNKNOWN_LEGACY,
)

# Ljudski čin stoji iza stavke. SOURCE_CASE_FACT je činjenica iz predmeta (metapodatak), ne ljudska
# potvrda institucionalnog znanja; UNKNOWN_LEGACY nema dokazano poreklo.
HUMAN_CLASSES = frozenset({
    HUMAN_CONFIRMED_OUTCOME, LAWYER_VERIFIED_ARTIFACT, HUMAN_MEMORY_NOTE, HUMAN_CORRECTION,
    EXPLICIT_GRAPH_RELATION,
})
AI_CLASSES = frozenset({AI_CANDIDATE_LESSON, AI_WORK_PRODUCT})

# ─── Validnost ──────────────────────────────────────────────────────────────
CURRENT, STALE, DEPRECATED, UNKNOWN = "CURRENT", "STALE", "DEPRECATED", "UNKNOWN"
VALIDITY_STATES = (CURRENT, STALE, DEPRECATED, UNKNOWN)

# ─── Stanja sekcija (API) ───────────────────────────────────────────────────
OK, EMPTY, DEGRADED, NOT_AUTHORIZED = "OK", "EMPTY", "DEGRADED", "NOT_AUTHORIZED"
SECTION_STATES = (OK, EMPTY, UNKNOWN, DEGRADED, NOT_AUTHORIZED)

# ─── Opseg ──────────────────────────────────────────────────────────────────
SCOPE_USER = "USER"        # vidljivo samo vlasniku (i ACL-om delegiranima za predmet)
SCOPE_OFFICE = "OFFICE"    # izričito deljeno u kancelariji (ljudski upis u memoriju kancelarije)
SCOPES = (SCOPE_USER, SCOPE_OFFICE)

EXCERPT_MAX = 400

AUTHORITY_NOTICE = (
    "Iskustvo kancelarije nije pravni izvor. Zakon i sudsku praksu proverite u zvaničnim izvorima."
)


def safe_excerpt(text: Optional[str], limit: int = EXCERPT_MAX) -> str:
    """Kratak, jednoredni izvod. Nikad ceo dokument."""
    s = " ".join(str(text or "").split())
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def _as_date(value) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def validity_from(
    *,
    today: date,
    deprecated: bool = False,
    stale: bool = False,
    valid_until=None,
    has_validity_data: bool = True,
) -> str:
    """Deterministička validnost. `today` je obavezan (nema skrivenog sata).

    Redosled: DEPRECATED (izričito povučeno/odbijeno) → STALE (označeno zastarelim ili istekao rok) →
    CURRENT samo ako izvor uopšte nosi podatak o važenju, inače UNKNOWN."""
    if deprecated:
        return DEPRECATED
    if stale:
        return STALE
    vu = _as_date(valid_until)
    if vu is not None and vu < today:
        return STALE
    if not has_validity_data:
        return UNKNOWN
    return CURRENT


@dataclass(frozen=True)
class LawBrainItem:
    """Jedna stavka institucionalnog znanja. Nije istina — pokazivač na istinu sa oznakom poverenja."""

    source_kind: str                    # npr. "outcome", "artifact", "lesson", "memory_note", "graph_edge"
    source_owner: str                   # tabela koja POSEDUJE izvor (npr. "outcome_log")
    source_id: str                      # ID reda u toj tabeli
    scope: str                          # SCOPE_USER | SCOPE_OFFICE
    trust_class: str
    validity: str
    title: str = ""
    excerpt: str = ""
    predmet_id: Optional[str] = None    # samo kad je pozivalac autorizovan za taj predmet
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    lineage: tuple = ()                 # npr. ("AI_GENERATED", "LAWYER_VERIFIED")
    outcome_ref: Optional[str] = None   # outcome_log.id kad postoji ljudski ishod
    state: Optional[str] = None         # tačno stanje izvora (npr. "APPROVED_NOT_INDEXED"), bez ulepšavanja
    attrs: tuple = field(default=())    # dodatni deterministički atributi kao (ključ, vrednost) parovi

    def __post_init__(self):
        if self.trust_class not in TRUST_CLASSES:
            raise ValueError(f"nepoznata klasa poverenja: {self.trust_class!r}")
        if self.validity not in VALIDITY_STATES:
            raise ValueError(f"nepoznato stanje validnosti: {self.validity!r}")
        if self.scope not in SCOPES:
            raise ValueError(f"nepoznat opseg: {self.scope!r}")
        if not self.source_kind or not self.source_owner or not self.source_id:
            raise ValueError("stavka mora imati izvor (source_kind, source_owner, source_id)")
        if self.trust_class == HUMAN_CONFIRMED_OUTCOME and not self.outcome_ref:
            raise ValueError("ljudski ishod mora imati outcome_ref")
        object.__setattr__(self, "excerpt", safe_excerpt(self.excerpt))
        object.__setattr__(self, "title", safe_excerpt(self.title, 160))
        object.__setattr__(self, "lineage", tuple(str(x) for x in (self.lineage or ())))

    @property
    def id(self) -> str:
        """Stabilan ID: isti izvorni red = isti ID, uvek."""
        return f"{self.source_kind}:{self.source_id}"

    @property
    def human_verified(self) -> bool:
        return self.trust_class in HUMAN_CLASSES

    @property
    def trusted(self) -> bool:
        """Sme da se prikaže kao institucionalno znanje kancelarije: ljudska klasa I nije povučeno."""
        return self.human_verified and self.validity != DEPRECATED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_kind": self.source_kind,
            "source_owner": self.source_owner,
            "source_ref": {"table": self.source_owner, "id": self.source_id},
            "scope": self.scope,
            "predmet_id": self.predmet_id,
            "title": self.title,
            "excerpt": self.excerpt,
            "trust_class": self.trust_class,
            "human_verified": self.human_verified,
            "validity": self.validity,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "lineage": list(self.lineage),
            "outcome_ref": self.outcome_ref,
            "attrs": {k: v for k, v in self.attrs},
        }


def order_items(items) -> list:
    """Deterministički redosled: poverenje (ljudsko pre AI), validnost (važeće pre zastarelog), novije pre
    starijeg, pa stabilan ID. Višeprolazno stabilno sortiranje — bez parsiranja vremena."""
    trust_rank = {c: i for i, c in enumerate(TRUST_CLASSES)}
    validity_rank = {CURRENT: 0, UNKNOWN: 1, STALE: 2, DEPRECATED: 3}
    out = sorted(items, key=lambda it: it.id)
    out.sort(key=lambda it: it.updated_at or it.created_at or "", reverse=True)
    out.sort(key=lambda it: (trust_rank[it.trust_class], validity_rank[it.validity]))
    return out


_IN_DEO = 200   # najviše ID-eva po `in_` upitu (dužina PostgREST URL-a); broj upita = ceil(N / 200) po izvoru


def _in_upit(supa, tabela: str, kolone: str, kljuc: str, ids) -> list:
    ids = sorted({str(i) for i in ids if i})
    out: list = []
    for i in range(0, len(ids), _IN_DEO):
        r = supa.table(tabela).select(kolone).in_(kljuc, ids[i:i + _IN_DEO]).execute()
        out.extend(r.data or [])
    return out


# ─── Task 2: ljudski ishod predmeta (jedini izvor: outcome_log) ─────────────
# Status predmeta, hronologija, AI sažeci i Genome se NIKAD ne čitaju kao ishod. Zatvoren predmet bez
# reda u outcome_log ima OUTCOME_UNKNOWN — ne „pobedu" ni „poraz".
ISHODI = ("pobeda", "poraz", "nagodba", "odustajanje")       # = CHECK u migraciji 037
OUTCOME_RECORDED = "RECORDED"
OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
OUTCOME_NOT_TERMINAL = "NOT_TERMINAL"
OUTCOME_REOPENED = "RECORDED_MATTER_REOPENED"   # ishod postoji, ali je predmet ponovo aktivan
OUTCOME_KOLONE = "id,predmet_id,user_id,ishod,presudni_faktori,trajanje_meseci,created_at,updated_at"


def _terminalni_statusi() -> tuple:
    from shared.constants import TERMINALNI_STATUSI_PREDMETA
    return tuple(TERMINALNI_STATUSI_PREDMETA)


def je_terminalan(predmet: dict) -> bool:
    return (predmet.get("status") or "") in _terminalni_statusi()


def _ishod_pripada(predmet: dict, red: Optional[dict]) -> bool:
    """Red ishoda važi samo za TAJ predmet i TOG vlasnika, sa ishodom iz dozvoljenog skupa."""
    if not red:
        return False
    return (str(red.get("predmet_id") or "") == str(predmet.get("id") or "")
            and str(red.get("user_id") or "") == str(predmet.get("user_id") or "")
            and bool(predmet.get("user_id"))
            and red.get("ishod") in ISHODI)


def outcome_view(predmet: dict, red: Optional[dict]) -> dict:
    """Deterministički pogled na ishod jednog (autorizovanog) predmeta."""
    pid = str(predmet.get("id") or "")
    terminalan = je_terminalan(predmet)
    if not _ishod_pripada(predmet, red):
        return {"predmet_id": pid, "status": OUTCOME_UNKNOWN if terminalan else OUTCOME_NOT_TERMINAL,
                "ishod": None, "item": None}
    stanje = OUTCOME_RECORDED if terminalan else OUTCOME_REOPENED
    item = LawBrainItem(
        source_kind="outcome", source_owner="outcome_log", source_id=str(red["id"]),
        scope=SCOPE_USER, trust_class=HUMAN_CONFIRMED_OUTCOME,
        validity=CURRENT if terminalan else STALE,
        title=f"Ishod: {red['ishod']}",
        excerpt=f"Ishod zabeležio advokat: {red['ishod']}",
        predmet_id=pid, created_at=red.get("created_at"), updated_at=red.get("updated_at"),
        lineage=("HUMAN_OUTCOME",), outcome_ref=str(red["id"]), state=stanje,
        attrs=(("ishod", red["ishod"]),
               ("presudni_faktori", tuple(sorted(str(x) for x in (red.get("presudni_faktori") or [])))),
               ("trajanje_meseci", red.get("trajanje_meseci"))),
    )
    return {"predmet_id": pid, "status": stanje, "ishod": red["ishod"], "item": item}


def ucitaj_ishode(supa, predmeti: list) -> dict:
    """{predmet_id: outcome_log red} za VEĆ autorizovane predmete. Greška baze se NE guta (pozivalac
    označava sekciju kao DEGRADED). Red tuđeg vlasnika se odbacuje i kad bi upit ga vratio."""
    po_id = {str(p.get("id")): p for p in predmeti if p.get("id")}
    if not po_id:
        return {}
    out: dict = {}
    for red in _in_upit(supa, "outcome_log", OUTCOME_KOLONE, "predmet_id", po_id):
        pid = str(red.get("predmet_id") or "")
        if pid in po_id and _ishod_pripada(po_id[pid], red):
            out[pid] = red
    return out


# ─── Task 4: advokatski overeni artefakti (jedini izvor: staging_memory, migracija 088) ─────────────
# Tok: AI nacrt → staging_memory (Quality Gate skor) → izričita advokatska potvrda (`is_lawyer_approved`,
# `approved_by`, `approved_at`, status `approved`) → promocija u Pinecone SAMO ako je skor ≥ prag
# (`pinecone_indexed`). „Odobreno" i „indeksirano" su dva različita stanja i prikazuju se tačno.
ART_INDEXED = "APPROVED_INDEXED"
ART_APPROVED_NOT_INDEXED = "APPROVED_NOT_INDEXED"
ART_PENDING = "PENDING_REVIEW"
ART_REJECTED = "REJECTED"
ART_REJECTED_STILL_INDEXED = "REJECTED_STILL_INDEXED"   # odbijen posle promocije — vektor još postoji
ART_INCONSISTENT = "INCONSISTENT"                       # npr. status approved bez advokatske potvrde
ARTEFAKT_KOLONE = ("id,user_id,predmet_id,tip,naziv,tekst,confidence_score,is_lawyer_approved,approved_at,"
                   "status,pinecone_indexed,created_at")


def artifact_item(red: dict, predmet: dict) -> Optional[LawBrainItem]:
    """Normalizuje jedan staging red za (autorizovan) predmet. Red drugog predmeta/vlasnika → None."""
    if str(red.get("predmet_id") or "") != str(predmet.get("id") or ""):
        return None
    if not predmet.get("user_id") or str(red.get("user_id") or "") != str(predmet.get("user_id")):
        return None
    status = red.get("status")
    odobren = red.get("is_lawyer_approved") is True
    indeksiran = red.get("pinecone_indexed") is True
    if status == "approved" and odobren and red.get("approved_at"):
        stanje = ART_INDEXED if indeksiran else ART_APPROVED_NOT_INDEXED
        klasa, validnost = LAWYER_VERIFIED_ARTIFACT, CURRENT
        loza = ("AI_GENERATED", "LAWYER_VERIFIED")
    elif status == "rejected":
        stanje = ART_REJECTED_STILL_INDEXED if indeksiran else ART_REJECTED
        klasa, validnost, loza = AI_WORK_PRODUCT, DEPRECATED, ("AI_GENERATED", "REJECTED")
    elif status == "pending" and not odobren:
        stanje, klasa, validnost, loza = ART_PENDING, AI_WORK_PRODUCT, UNKNOWN, ("AI_GENERATED",)
    else:
        stanje, klasa, validnost, loza = ART_INCONSISTENT, AI_WORK_PRODUCT, UNKNOWN, ("AI_GENERATED",)
    return LawBrainItem(
        source_kind="artifact", source_owner="staging_memory", source_id=str(red["id"]),
        scope=SCOPE_USER, trust_class=klasa, validity=validnost,
        title=red.get("naziv") or red.get("tip") or "Nacrt", excerpt=red.get("tekst") or "",
        predmet_id=str(predmet["id"]), created_at=red.get("created_at"),
        updated_at=red.get("approved_at") or red.get("created_at"), lineage=loza, state=stanje,
        attrs=(("tip", red.get("tip")), ("confidence_score", red.get("confidence_score")),
               ("pinecone_indexed", indeksiran)),
    )


def ucitaj_artefakte(supa, predmeti: list) -> list:
    """Svi staging redovi (sa tačnim stanjem) za VEĆ autorizovane predmete. Greška baze se propušta."""
    po_id = {str(p.get("id")): p for p in predmeti if p.get("id")}
    if not po_id:
        return []
    out = []
    for red in _in_upit(supa, "staging_memory", ARTEFAKT_KOLONE, "predmet_id", po_id):
        it = artifact_item(red, po_id.get(str(red.get("predmet_id") or ""), {}))
        if it is not None:
            out.append(it)
    return order_items(out)


def trusted(items) -> list:
    """Samo ono što sme da se prikaže kao institucionalno znanje (ljudska klasa, nije povučeno)."""
    return [it for it in items if it.trusted]


# ─── Task 5: izveden profil (zatvorenog) predmeta — NIJE nova istina ────────────────────────────────
# Gradi se pri čitanju iz vlasnika domena, ograničenim brojem upita bez obzira na broj predmeta (po jedan
# upit po izvoru, `in_` nad autorizovanim ID-evima). Ne kopira dokumente ni tekst tvrdnji — samo kategorije
# i brojeve. Razdvaja: činjenice iz predmeta / ljudski ishod / AI analizu / nepoznato.
PROFILE_DERIVATION = "lb-profile-1"
_ISSUE_ZIVI = ("DISCOVERED", "CONFIRMED", "REOPENED")


def _brojac(vrednosti) -> dict:
    out: dict = {}
    for v in vrednosti:
        if v:
            out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items()))


def matter_profile(predmet: dict, *, ishod_red: Optional[dict], dokazi: list, rocista: list,
                   issues: list, kontradikcije: list, artefakti: list) -> dict:
    """Čista funkcija: isti ulaz → isti profil. Ulazi su već filtrirani na ovaj predmet i vlasnika."""
    g = predmet.get("case_dna") if isinstance(predmet.get("case_dna"), dict) else {}
    g_verzija = g.get("verzija") if isinstance(g.get("verzija"), int) else None
    ishod = outcome_view(predmet, ishod_red)
    poverljivi = [a for a in artefakti if a.trusted]
    cinjenice = {
        "tip": predmet.get("tip") or None,
        "oblast": predmet.get("oblast") or None,
        "status": predmet.get("status") or None,
        "sudovi": sorted({str(r.get("sud")).strip() for r in rocista if r.get("sud")}),
        "dokazi_po_kategoriji": _brojac(d.get("kategorija") for d in dokazi if not d.get("deleted_at")),
        "broj_rocista": len(rocista),
    }
    ai = {
        "trust_class": AI_WORK_PRODUCT,
        "genome_verzija": g_verzija,
        "pravna_pitanja_po_statusu": _brojac(i.get("status") for i in issues),
        "kontradikcije_po_vrsti": _brojac(k.get("relation_type") for k in kontradikcije),
        "kontradikcije_po_tezini": _brojac(k.get("tezina") for k in kontradikcije),
    }
    nepoznato = sorted(
        [k for k, v in (("tip", cinjenice["tip"]), ("oblast", cinjenice["oblast"])) if not v]
        + (["sud"] if not cinjenice["sudovi"] else [])
        + (["genome"] if g_verzija is None else [])
        + (["ishod"] if ishod["status"] == OUTCOME_UNKNOWN else [])
    )
    return {
        "predmet_id": str(predmet.get("id")),
        "terminalan": je_terminalan(predmet),
        "cinjenice": {"trust_class": SOURCE_CASE_FACT, **cinjenice},
        "ljudski_ishod": {"status": ishod["status"], "ishod": ishod["ishod"],
                          "item": ishod["item"].to_dict() if ishod["item"] else None},
        "ai_analiza": ai,
        "overeni_artefakti": [a.to_dict() for a in poverljivi],
        "nepoznato": nepoznato,
        "poreklo": {
            "derivation_version": PROFILE_DERIVATION,
            "genome_verzija": g_verzija,
            "outcome_ref": str(ishod_red["id"]) if ishod["item"] else None,
            "outcome_updated_at": (ishod_red or {}).get("updated_at") if ishod["item"] else None,
        },
    }


def _po_predmetu(redovi, kljuc="predmet_id") -> dict:
    out: dict = {}
    for r in redovi or []:
        out.setdefault(str(r.get(kljuc) or ""), []).append(r)
    return out


def ucitaj_profile(supa, predmeti: list) -> dict:
    """{predmet_id: profil} za VEĆ autorizovane predmete. 6 upita po delu od 200 predmeta (ne po predmetu).
    Red čiji `user_id` nije vlasnik predmeta se odbacuje (kontradikcije nemaju user_id — vezane su preko
    pitanja koje je već filtrirano). Greška bilo kog izvora se propušta (pozivalac → DEGRADED)."""
    po_id = {str(p.get("id")): p for p in predmeti if p.get("id")}
    if not po_id:
        return {}
    ids = sorted(po_id)

    def _svoje(redovi):
        return [r for r in (redovi or [])
                if str(r.get("predmet_id") or "") in po_id
                and str(r.get("user_id") or "") == str(po_id[str(r.get("predmet_id"))].get("user_id") or "-")]

    ishodi = ucitaj_ishode(supa, list(po_id.values()))
    dokazi = _po_predmetu(_svoje(_in_upit(supa, "predmet_dokazi", "predmet_id,user_id,kategorija,deleted_at",
                                          "predmet_id", ids)))
    rocista = _po_predmetu(_svoje(_in_upit(supa, "rocista", "predmet_id,user_id,sud,status", "predmet_id", ids)))
    issues_svi = _svoje(_in_upit(supa, "predmet_issues", "id,predmet_id,user_id,status", "predmet_id", ids))
    issues_svi = [i for i in issues_svi if i.get("status") in _ISSUE_ZIVI]
    issue_predmet = {str(i["id"]): str(i["predmet_id"]) for i in issues_svi}
    kontr = []
    if issue_predmet:
        for k in _in_upit(supa, "predmet_contradictions", "issue_id,relation_type,tezina,state", "issue_id",
                          issue_predmet):
            if k.get("state") in ("OPEN", "REVIEW_REQUIRED") and str(k.get("issue_id")) in issue_predmet:
                kontr.append({**k, "predmet_id": issue_predmet[str(k["issue_id"])]})
    kontr_po = _po_predmetu(kontr)
    issues_po = _po_predmetu(issues_svi)
    artefakti_po: dict = {}
    for a in ucitaj_artefakte(supa, list(po_id.values())):
        artefakti_po.setdefault(a.predmet_id, []).append(a)
    return {pid: matter_profile(p, ishod_red=ishodi.get(pid), dokazi=dokazi.get(pid, []),
                                rocista=rocista.get(pid, []), issues=issues_po.get(pid, []),
                                kontradikcije=kontr_po.get(pid, []), artefakti=artefakti_po.get(pid, []))
            for pid, p in sorted(po_id.items())}


# ─── Task 6: objašnjiva sličnost predmeta ───────────────────────────────────────────────────────────
# Kandidati = SAMO predmeti koje kanonska autorizacija (`shared/rag_acl.dozvoljeni_predmeti`: vlasnik +
# aktivno delegiranje) već dozvoljava pozivaocu, i to u završnom statusu. Ista kancelarija NIJE dozvola.
# Ishod NIJE ulaz u sličnost (nema samoispunjavajuće pristrasnosti) — gleda se tek POSLE pronalaska.
# Bodovi su deterministička retrieval podudarnost po imenovanim dimenzijama, NIKAD verovatnoća uspeha.
SIMILARITY_VERSION = "lb-sim-1"
SIMILARITY_NOTICE = ("Bodovi pokazuju koliko se predmeti poklapaju po navedenim osobinama. "
                     "Nisu procena šanse za uspeh.")
_TEZINE = {"tip": 3, "oblast": 2, "sud": 1, "dokazi": 1, "kontradikcije": 1}
_MIN_BODOVA = 2
_MAX_PO_DIMENZIJI = 3
MAX_KANDIDATA = 1000
# Redom pokušaja: pun skup → bez `oblast` (nije ni u jednoj migraciji u repozitorijumu) → bez tombstone kolone (114).
PREDMET_KOLONE_POKUSAJI = (
    "id,user_id,naziv,tip,oblast,status,case_dna,brisanje_zapoceto,updated_at",
    "id,user_id,naziv,tip,status,case_dna,brisanje_zapoceto,updated_at",
    "id,user_id,naziv,tip,status,case_dna,updated_at",
)


def ucitaj_predmete(supa, ids) -> list:
    """Redovi predmeta za date (VEĆ autorizovane) ID-eve. Na grešku NEPOSTOJEĆE kolone prelazi na uži skup
    kolona; svaka druga greška se propušta."""
    from shared.audit_immutable import _is_missing_column_error
    for n, kolone in enumerate(PREDMET_KOLONE_POKUSAJI):
        try:
            return _in_upit(supa, "predmeti", kolone, "id", ids)
        except Exception as e:
            if not _is_missing_column_error(e) or n == len(PREDMET_KOLONE_POKUSAJI) - 1:
                raise
    return []


def similarity(trenutni: dict, kandidat: dict) -> dict:
    """Čista funkcija nad DVA PROFILA (Task 5). Čita samo `cinjenice` i vrste kontradikcija — nikad ishod."""
    a, b = trenutni["cinjenice"], kandidat["cinjenice"]
    razlozi = []

    def _dodaj(dim, vrednost, bodovi):
        razlozi.append({"dimenzija": dim, "vrednost": vrednost, "bodovi": bodovi})

    if a.get("tip") and a.get("tip") == b.get("tip"):
        _dodaj("tip", a["tip"], _TEZINE["tip"])
    if a.get("oblast") and a.get("oblast") == b.get("oblast"):
        _dodaj("oblast", a["oblast"], _TEZINE["oblast"])
    for sud in sorted(set(a.get("sudovi") or []) & set(b.get("sudovi") or []))[:1]:
        _dodaj("sud", sud, _TEZINE["sud"])
    zaj = sorted(set(a.get("dokazi_po_kategoriji") or {}) & set(b.get("dokazi_po_kategoriji") or {}))
    if zaj:
        _dodaj("dokazi", zaj, _TEZINE["dokazi"] * min(len(zaj), _MAX_PO_DIMENZIJI))
    ka = set((trenutni.get("ai_analiza") or {}).get("kontradikcije_po_vrsti") or {})
    kb = set((kandidat.get("ai_analiza") or {}).get("kontradikcije_po_vrsti") or {})
    zk = sorted(ka & kb)
    if zk:
        _dodaj("kontradikcije", zk, _TEZINE["kontradikcije"] * min(len(zk), _MAX_PO_DIMENZIJI))
    return {"bodovi": sum(r["bodovi"] for r in razlozi), "razlozi": razlozi}


def _objasnjenje(razlozi: list) -> str:
    delovi = []
    for r in razlozi:
        v = ", ".join(r["vrednost"]) if isinstance(r["vrednost"], list) else r["vrednost"]
        delovi.append({"tip": f"isti tip predmeta ({v})", "oblast": f"ista oblast ({v})", "sud": f"isti sud ({v})",
                       "dokazi": f"iste vrste dokaza ({v})",
                       "kontradikcije": f"iste vrste protivrečnosti ({v})"}[r["dimenzija"]])
    return "Sličan jer: " + "; ".join(delovi) + "."


def slicni_predmeti(supa, user_id: str, predmet_id: str, *, limit: int = 10) -> dict:
    """Objašnjivo slični ZAVRŠENI predmeti koje `user_id` sme da vidi. Bez modela, bez upisa."""
    from shared.rag_acl import dozvoljeni_predmeti
    dozvoljeni = set(dozvoljeni_predmeti(supa, user_id))       # greška baze → izuzetak (fail-closed)
    if str(predmet_id) not in dozvoljeni:
        return {"stanje": NOT_AUTHORIZED, "stavke": []}
    redovi = {str(p["id"]): p for p in ucitaj_predmete(supa, dozvoljeni) if p.get("id")}
    trenutni = redovi.get(str(predmet_id))
    if trenutni is None:
        return {"stanje": NOT_AUTHORIZED, "stavke": []}
    kandidati = [p for pid, p in redovi.items()
                 if pid != str(predmet_id) and pid in dozvoljeni and je_terminalan(p)
                 and not p.get("brisanje_zapoceto")]
    kandidati.sort(key=lambda p: (str(p.get("updated_at") or ""), str(p["id"])), reverse=True)
    pretrazeno = kandidati[:MAX_KANDIDATA]
    profili = ucitaj_profile(supa, [trenutni] + pretrazeno)
    pt = profili[str(predmet_id)]
    stavke = []
    for p in pretrazeno:
        prof = profili[str(p["id"])]
        sl = similarity(pt, prof)
        if sl["bodovi"] < _MIN_BODOVA:
            continue
        stavke.append({
            "predmet_id": str(p["id"]),
            "naziv": p.get("naziv") or "",
            "sopstveni": str(p.get("user_id")) == str(user_id),
            "bodovi": sl["bodovi"],
            "razlozi": sl["razlozi"],
            "zasto": _objasnjenje(sl["razlozi"]),
            "ishod": prof["ljudski_ishod"],             # posle pronalaska; nikad ulaz u bodove
            "overeni_artefakti": len(prof["overeni_artefakti"]),
        })
    stavke.sort(key=lambda s: (-s["bodovi"], s["predmet_id"]))
    return {
        "stanje": OK if stavke else EMPTY,
        "stavke": stavke[:max(1, min(int(limit), 50))],
        "pretrazeno_zavrsenih": len(pretrazeno),
        "ukupno_slicnih": len(stavke),
        "verzija": SIMILARITY_VERSION,
        "napomena": SIMILARITY_NOTICE,
    }
