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
    r = (supa.table("outcome_log").select(OUTCOME_KOLONE)
         .in_("predmet_id", sorted(po_id)).execute())
    out: dict = {}
    for red in (r.data or []):
        pid = str(red.get("predmet_id") or "")
        if pid in po_id and _ishod_pripada(po_id[pid], red):
            out[pid] = red
    return out
