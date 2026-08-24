# -*- coding: utf-8 -*-
"""
P1-5 — BRISANJE PREDMETA. Fail-closed, po specifikaciji
`docs/beta_gate/P15_LIFECYCLE_SPECIFICATION.md`.

ZAŠTO POSTOJI

`DELETE /api/predmeti/{id}` nije postojao. Podaci predmeta žive u **61** tabeli;
samo **21** ima deklarisan FK ka `predmeti`, a od njih **16** je `CASCADE`,
**4** `SET NULL` i **1** `RESTRICT`. Preostalih **36** tabela nema FK — brisanje
oslonjeno samo na kaskadu ostavilo bi orphan redove, a vektori dokumenata ne bi
bili dodirnuti uopšte (curenje sadržaja iz `PINE-01` klase).

UGOVOR (isti kao `shared/vector_deletion.py`)

  DELETED             sve što politika kaže da se briše je dokazano uklonjeno
  ALREADY_ABSENT      predmet ne postoji (ili nije vlasnikov)
  BLOCKED             `billing_entries` (FK RESTRICT) postoji — ništa nije dirano
  REFUSED             nema prava pristupa — ništa nije dirano
  PERMANENT_FAILURE   tombstone se NE MOŽE upisati — ništa nije dirano
  RETRYABLE_FAILURE   tombstone je upisan, neki korak je pao — predmet je DELETING

Delimično brisanje se **nikad** ne sme prijaviti kao „obrisano" (invarijanta 1).

═══════════════════════════════════════════════════════════════════════════
BETA-DEL-001 — ZAŠTO JE REDOSLED PROMENJEN
═══════════════════════════════════════════════════════════════════════════

RANIJE su vektori bili korak 4, PRE brisanja redova. Obrazloženje je bilo:
„zaostao vektor uz obrisan red je curenje". To važi samo ako predmet nestane.

Mereno uživo 3/3 na `27cb670`: korak vektora uspe, brisanje `events` padne na
FK (`case_evolution_consequences.event_id`, migracija 096, bez `ON DELETE`),
red `predmeti` se ne obriše — i ostane **živ predmet sa nepovratno obrisanim
vektorima**. Advokat vidi predmet i dokument, ali odgovor više ne sadrži
činjenicu iz tog dokumenta. Poruka mu je govorila „operacija se može ponoviti",
što je bilo neistinito: identičan retry pada opet, zauvek.

SADA je nepovratna operacija POSLEDNJA destruktivna, a pre nje se upisuje
tombstone:

  1. autorizacija            (ništa se ne dira dok se ne dokaže vlasništvo)
  2. postojanje              (ponovljeni DELETE → ALREADY_ABSENT, ne „obrisano")
  3. blokade                 (RESTRICT → BLOCKED, ništa se ne dira)
  4. TOMBSTONE               (prvi upis; potpuno povratan; bez njega se STAJE)
  5. redovi bez FK           (deca sa dolaznom FK PRE roditelja)
  6. VEKTORI                 (nepovratno — ali predmet je već nevidljiv)
  7. `predmeti` red          (poslednji; CASCADE počisti svojih 16)

Orphan vektor time nije curenje: u trenutku brisanja vektora predmet POSTOJI,
ali je `DELETING` i isključen iz `shared/rag_acl.dozvoljeni_predmeti`, pa RAG
ne može da ga dohvati. Ako korak 6 padne, vektori ostaju uz tombstonovan
predmet i retry ih dokrajči.

INVARIANT: nijedan predmet ne može biti istovremeno vidljiv korisniku i lišen
svojih vektora.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("vindex.predmet_deletion")


class IshodPredmeta:
    """Eksplicitno stanje — nikad „uspeh jer nije bilo izuzetka"."""

    DELETED = "DELETED"
    ALREADY_ABSENT = "ALREADY_ABSENT"
    BLOCKED = "BLOCKED"
    REFUSED = "REFUSED"
    # BETA-DEL-001: jedan generički `PARTIAL_FAILURE` je pokrivao dve suprotne
    # semantike — „ništa nije dirano, pokušaj ponovo" i „pola je uklonjeno,
    # retry pada zauvek". Zato su razdvojeni.
    PERMANENT_FAILURE = "PERMANENT_FAILURE"   # ništa nije dirano; retry NE pomaže
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"   # predmet je DELETING; retry napreduje


# Tabele bez FK ka `predmeti` — baza ih NEĆE počistiti sama.
# Izvedeno merenjem (DDL ∪ produkcioni kod), v. §2 specifikacije.
# Namerno NE sadrži:
#   - 16 `CASCADE` tabela   (baza ih briše sama)
#   - 4 `SET NULL` tabele   (baza raskida vezu — namerna odluka šeme)
#   - `billing_entries`     (RESTRICT — blokada, v. korak 3)
#   - audit i finansijske   (RETAIN)
TABELE_BEZ_FK: tuple[str, ...] = (
    "ai_corrections", "case_actions", "case_intelligence_summaries",
    "client_portal_tokens", "client_portal_uploads", "commander_analize",
    "counterfactual_log", "decision_log", "email_notif_log", "events",
    "evidence_grafovi", "hearing_briefovi", "intake_jobs", "lessons_learned",
    "memory_graph_edges", "outcome_log", "portal_status_log", "praceni_predmeti",
    "predictor_analize", "predmet_genome_history", "predmet_saradnici",
    "privremeni_pristup", "proactive_alerts", "reasoning_confidence",
    "reasoning_edges", "reasoning_evidence", "reasoning_graph", "reasoning_nodes",
    "reasoning_sources", "recommendation_log", "staging_memory", "style_analize",
    "uploaded_documents", "vindex_memory", "workflow_instances", "zadaci",
)

# Tabele koje vise o `events(id)`, a NEMAJU `predmet_id` — dohvatljive su samo
# preko `event_id`. Brišu se PRE `events`, inače FK `NO ACTION` obara ceo korak.
#   `case_evolution_consequences`  096, event_id NOT NULL   ← dokazani blokator
#   `case_intelligence_summaries`  098, event_id NULLABLE
#   `case_actions`                 099, event_id NULLABLE
# Poslednje dve su i u `TABELE_BEZ_FK`; ovde se čiste po `event_id` jer po
# `predmet_id` nisu dohvatljive.
TABELE_DECA_DOGADJAJA: tuple[str, ...] = (
    "case_evolution_consequences",
    "case_intelligence_summaries",
    "case_actions",
)

# ═══════════════════════════════════════════════════════════════════════════
# BLK-2 — ISTA KLASA KVARA KAO `case_evolution_consequences`, DRUGO STABLO
# ═══════════════════════════════════════════════════════════════════════════
#
# `intake_jobs` je u `TABELE_BEZ_FK` (dakle PURGE), ali ga briše `.delete()`
# koji baza odbija: šest tabela ima DOLAZNU FK ka njemu, nijedna sa `ON DELETE`
# (sve `NO ACTION`). Politika je i ovde modelovala samo ODLAZNE FK ka
# `predmeti`, pa su ta deca bila nevidljiva jedinom predikatu (`predmet_id`) —
# `intake_documents`, `extracted_entities` i ostali nemaju tu kolonu uopšte.
#
# Mereno uživo na `57bec9d`, 3/3 (BLK-2 §14): predmet iz dokumenta uvek daje
# `409 RETRYABLE_FAILURE`, `neuspele_tabele: ["intake_jobs"]`,
# `vektori: NIJE_POKRENUTO`. Ponovljen pokušaj pada identično — zauvek.
# Kontrolna grupa (predmet bez dokumenta) daje `200 DELETED`.
#
# Redosled ispod je IZVEDEN IZ GRAFA, ne pogođen:
#   extracted_entities.document_id      → intake_documents   (074, NOT NULL)
#   intake_review_queue.document_id     → intake_documents   (074, nullable)
#   intake_review_queue.intake_job_id   → intake_jobs        (074, NOT NULL)
#   intake_processing_outcomes.segment_id → intake_job_segments (093, nullable)
#   intake_job_segments.document_id     → intake_documents   (093, nullable)
#   ⇒ outcomes PRE segments, segments PRE documents, entities PRE documents.
#
# `intake_audit_log` (073) nosi komentar „Nikad UPDATE/DELETE". Provereno:
# nema okidača, pravila ni REVOKE-a koji to iznuđuje — za razliku od
# `audit_immutable`, koji ima `trg_protect_audit_immutable` (mig. 043) i koji
# se ovde NE dira. Specifikacija (`P15_LIFECYCLE_SPECIFICATION.md` §2) izvodi
# `RETAIN` isključivo iz postojećih tehničkih odluka (DB okidač, FK RESTRICT),
# a ovde nijedna ne postoji. Šest sestrinskih tabela istog oblika
# (`decision_log`, `outcome_log`, `email_notif_log`, `portal_status_log`,
# `counterfactual_log`, `recommendation_log`) već su PURGE. Tenzija je ipak
# stvarna i prijavljena je u BLK-2-REMEDIATION-REPORT-001 §22 — nije prećutana.
TABELE_DECA_POSLOVA: tuple[tuple[str, str], ...] = (
    ("extracted_entities",         "document_id"),
    ("intake_review_queue",        "intake_job_id"),
    ("intake_processing_outcomes", "intake_job_id"),
    ("intake_job_segments",        "intake_job_id"),
    ("intake_audit_log",           "intake_job_id"),
    ("intake_documents",           "intake_job_id"),
)

# `predmet_dokumenti` pokazuje NA `intake_jobs` i `intake_job_segments`
# (migracije 095 i 094, obe kolone nullable). Red se NE sme obrisati ovde —
# korak 6 iz njega čita spisak dokumenata čije vektore treba ukloniti, a
# `ON DELETE CASCADE` sa `predmeti` ga ionako briše u koraku 7 (izmereno
# sondom: red nestaje sa `predmeti` redom). Zato se veza samo RASKIDA.
KOLONE_VEZE_KA_POSLOVIMA: tuple[str, ...] = (
    "source_intake_job_id",
    "source_intake_job_segment_id",
)

# PostgREST kodovi koji znače „nema šta da se briše", ne „brisanje nije uspelo".
_NEMA_OBJEKTA = ("PGRST205", "42P01", "42703", "does not exist",
                 "could not find the table", "schema cache")


@dataclass
class RezultatBrisanja:
    ishod: str
    razlog: str = ""
    obrisane_tabele: list = field(default_factory=list)
    preskocene_tabele: list = field(default_factory=list)   # tabela/kolona ne postoji
    neuspele_tabele: list = field(default_factory=list)
    vektori: str = "NIJE_POKRENUTO"
    tombstone: str = "NIJE_UPISAN"

    @property
    def uspeh(self) -> bool:
        return self.ishod in (IshodPredmeta.DELETED, IshodPredmeta.ALREADY_ABSENT)

    def kao_dict(self) -> dict:
        return {
            "ishod": self.ishod,
            "uspeh": self.uspeh,
            "razlog": self.razlog,
            "obrisane_tabele": list(self.obrisane_tabele),
            "preskocene_tabele": list(self.preskocene_tabele),
            "neuspele_tabele": list(self.neuspele_tabele),
            "vektori": self.vektori,
            "tombstone": self.tombstone,
        }


def _nema_objekta(greska: Exception) -> bool:
    t = str(greska).lower()
    return any(k.lower() in t for k in _NEMA_OBJEKTA)


def _predmet_postoji(supa, user_id: str, predmet_id: str) -> bool:
    r = (supa.table("predmeti").select("id")
         .eq("id", predmet_id).eq("user_id", user_id).execute())
    return bool(getattr(r, "data", None))


def _ima_naplate(supa, predmet_id: str) -> int:
    r = (supa.table("billing_entries").select("id")
         .eq("predmet_id", predmet_id).execute())
    return len(getattr(r, "data", None) or [])


def _upisi_tombstone(supa, user_id: str, predmet_id: str) -> None:
    """Označava predmet kao `DELETING`. Diže izuzetak ako ne uspe.

    Ovo je JEDINI korak koji sme da prethodi bilo čemu destruktivnom. Ako
    padne — najčešće zato što migracija 114 nije primenjena — pozivalac vraća
    `PERMANENT_FAILURE` i ne dira ništa. Time je deploy bezbedan u oba
    redosleda (kod pre migracije ili migracija pre koda).
    """
    from datetime import datetime, timezone
    (supa.table("predmeti")
     .update({"brisanje_zapoceto": datetime.now(timezone.utc).isoformat()})
     .eq("id", predmet_id).eq("user_id", user_id).execute())


def _obrisi_decu_dogadjaja(supa, predmet_id: str) -> list:
    """Briše redove koji preko `event_id` vise o `events` ovog predmeta.

    BETA-DEL-001 — KORENSKI UZROK. Politika je modelovala samo ODLAZNE FK
    (tabela → `predmeti`). `case_evolution_consequences` (migracija 096) ima
    `event_id UUID NOT NULL REFERENCES events(id)` BEZ `ON DELETE`, dakle
    `NO ACTION`, i **nema kolonu `predmet_id`** — pa je bila nedohvatljiva
    jedinom predikatu politike (`.eq("predmet_id", …)`). Zbog nje je brisanje
    `events` padalo trajno.

    Vraća listu tabela koje NISU očišćene (prazna = sve u redu).

    FK-ovi u migracijama 096/098/099 se NAMERNO NE menjaju — problem se rešava
    redosledom brisanja, ne izmenom šeme.
    """
    neuspele = []
    try:
        red = (supa.table("events").select("id")
               .eq("predmet_id", predmet_id).execute())
        event_ids = [r["id"] for r in (getattr(red, "data", None) or []) if r.get("id")]
    except Exception as exc:
        if _nema_objekta(exc):
            return []
        logger.error("[PREDMET-DELETE] spisak dogadjaja nije procitan p=%.8s: %s",
                     predmet_id, exc)
        return ["events"]

    if not event_ids:
        return []

    for tabela in TABELE_DECA_DOGADJAJA:
        try:
            # `in_` u jednom pozivu; PostgREST podnosi liste ove veličine, a
            # `events` po predmetu ih ionako ima malo.
            supa.table(tabela).delete().in_("event_id", event_ids).execute()
        except Exception as exc:
            if _nema_objekta(exc):
                continue
            logger.error("[PREDMET-DELETE] tabela %s (preko event_id) nije ociscena "
                         "p=%.8s: %s", tabela, predmet_id, exc)
            neuspele.append(tabela)
    return neuspele


def _obrisi_decu_poslova(supa, predmet_id: str) -> list:
    """Briše redove koji preko `intake_job_id`/`document_id` vise o intake
    poslovima ovog predmeta, i raskida vezu `predmet_dokumenti` → poslovi.

    BLK-2 — KORENSKI UZROK. Vraća listu tabela koje NISU očišćene (prazna = sve
    u redu). Kao i kod `_obrisi_decu_dogadjaja`, FK-ovi u migracijama
    073/074/093/094/095 se NAMERNO NE menjaju — problem se rešava redosledom
    brisanja, ne izmenom šeme. Razlog je isti onaj koji specifikacija već
    zahteva (invarijanta 8): dodavanje `ON DELETE CASCADE` na postojeću tabelu
    traži dokaz da nema orphan redova, a taj dokaz ovde ne postoji.
    """
    try:
        red = (supa.table("intake_jobs").select("id")
               .eq("predmet_id", predmet_id).execute())
        job_ids = [r["id"] for r in (getattr(red, "data", None) or []) if r.get("id")]
    except Exception as exc:
        if _nema_objekta(exc):
            return []
        logger.error("[PREDMET-DELETE] spisak intake poslova nije procitan p=%.8s: %s",
                     predmet_id, exc)
        return ["intake_jobs"]

    if not job_ids:
        return []

    neuspele = []

    # 1. RASKIDANJE VEZE (ne brisanje) — mora PRE `intake_job_segments`.
    #    Bez ovoga `predmet_dokumenti.source_intake_job_segment_id` drži
    #    segmente, a `source_intake_job_id` same poslove.
    for kolona in KOLONE_VEZE_KA_POSLOVIMA:
        try:
            (supa.table("predmet_dokumenti").update({kolona: None})
             .eq("predmet_id", predmet_id).execute())
        except Exception as exc:
            if _nema_objekta(exc):
                continue
            logger.error("[PREDMET-DELETE] veza predmet_dokumenti.%s nije raskinuta "
                         "p=%.8s: %s", kolona, predmet_id, exc)
            neuspele.append("predmet_dokumenti.%s" % kolona)

    # 2. Dokumenti posla — potrebni da bi se `extracted_entities` uopšte našli
    #    (ta tabela nema ni `predmet_id` ni `intake_job_id`).
    try:
        red_d = (supa.table("intake_documents").select("id")
                 .in_("intake_job_id", job_ids).execute())
        doc_ids = [r["id"] for r in (getattr(red_d, "data", None) or []) if r.get("id")]
    except Exception as exc:
        if _nema_objekta(exc):
            doc_ids = []
        else:
            logger.error("[PREDMET-DELETE] spisak intake dokumenata nije procitan "
                         "p=%.8s: %s", predmet_id, exc)
            return neuspele + ["intake_documents"]

    # 3. Deca, u redosledu izvedenom iz grafa (v. TABELE_DECA_POSLOVA).
    for tabela, kolona in TABELE_DECA_POSLOVA:
        kljucevi = doc_ids if kolona == "document_id" else job_ids
        if not kljucevi:
            continue
        try:
            supa.table(tabela).delete().in_(kolona, kljucevi).execute()
        except Exception as exc:
            if _nema_objekta(exc):
                continue
            logger.error("[PREDMET-DELETE] tabela %s (preko %s) nije ociscena p=%.8s: %s",
                         tabela, kolona, predmet_id, exc)
            neuspele.append(tabela)

    return neuspele


def obrisi_predmet(supa, index, *, user_id: str, predmet_id: str) -> RezultatBrisanja:
    """Briše predmet i sve što politika kaže da se briše — i ništa drugo.

    `index` je Pinecone indeks; sme biti `None` samo ako predmet nema dokumenata
    (tada se korak vektora preskače i to se eksplicitno prijavljuje).
    """
    from shared.vector_deletion import Ishod as VIshod, _sme_predmet, obrisi_vektore_dokumenta

    rez = RezultatBrisanja(IshodPredmeta.RETRYABLE_FAILURE)

    # ── 1. AUTORIZACIJA ─────────────────────────────────────────────────────
    try:
        if not _sme_predmet(supa, user_id, predmet_id):
            return RezultatBrisanja(IshodPredmeta.REFUSED, "nema pravo pristupa predmetu")
    except Exception as exc:
        logger.error("[PREDMET-DELETE] autorizacija nije izvrsena p=%.8s: %s", predmet_id, exc)
        return RezultatBrisanja(IshodPredmeta.REFUSED,
                                "provera prava nije izvrsena — nista nije dirano")

    # ── 2. POSTOJANJE ───────────────────────────────────────────────────────
    try:
        if not _predmet_postoji(supa, user_id, predmet_id):
            return RezultatBrisanja(IshodPredmeta.ALREADY_ABSENT, "predmet ne postoji")
    except Exception as exc:
        logger.error("[PREDMET-DELETE] provera postojanja nije izvrsena p=%.8s: %s",
                     predmet_id, exc)
        return RezultatBrisanja(IshodPredmeta.PERMANENT_FAILURE,
                                "provera postojanja nije izvrsena — nista nije dirano")

    # ── 3. BLOKADE (FK RESTRICT) ────────────────────────────────────────────
    try:
        n = _ima_naplate(supa, predmet_id)
    except Exception as exc:
        # Ne zna se ima li naplate → ne sme se brisati.
        logger.error("[PREDMET-DELETE] provera naplate nije izvrsena p=%.8s: %s",
                     predmet_id, exc)
        return RezultatBrisanja(IshodPredmeta.BLOCKED,
                                "provera stavki naplate nije izvrsena — nista nije dirano")
    if n:
        return RezultatBrisanja(
            IshodPredmeta.BLOCKED,
            f"predmet ima {n} stavki naplate (billing_entries, FK RESTRICT); "
            f"finansijski trag se ne brise automatski")

    # ── 4. TOMBSTONE (prvi upis; bez njega se ne dira NIŠTA) ────────────────
    # Od ovog trenutka predmet je `DELETING`: nestaje iz liste, iz pojedinačnog
    # dohvatanja i iz RAG retrieval-a. Tek sada sme da počne destrukcija.
    try:
        _upisi_tombstone(supa, user_id, predmet_id)
    except Exception as exc:
        logger.error("[PREDMET-DELETE] tombstone nije upisan p=%.8s: %s", predmet_id, exc)
        return RezultatBrisanja(
            IshodPredmeta.PERMANENT_FAILURE,
            "predmet nije oznacen za brisanje (migracija 114?) — nista nije dirano")
    rez.tombstone = "UPISAN"

    # ── 5. REDOVI ───────────────────────────────────────────────────────────
    # 5a. deca koja vise o `events(id)` — PRE `events`, inače FK obara korak.
    neuspela_deca = _obrisi_decu_dogadjaja(supa, predmet_id)
    if neuspela_deca:
        rez.ishod = IshodPredmeta.RETRYABLE_FAILURE
        rez.neuspele_tabele.extend(neuspela_deca)
        rez.razlog = ("zavisni redovi dogadjaja nisu uklonjeni; vektori NISU dirani "
                      "i predmet je oznacen za brisanje — ponovite operaciju")
        return rez

    # 5a-bis. deca koja vise o `intake_jobs(id)` — PRE `intake_jobs`, iz istog
    #         razloga iz kog deca događaja idu pre `events`. BLK-2.
    neuspela_deca_poslova = _obrisi_decu_poslova(supa, predmet_id)
    if neuspela_deca_poslova:
        rez.ishod = IshodPredmeta.RETRYABLE_FAILURE
        rez.neuspele_tabele.extend(neuspela_deca_poslova)
        rez.razlog = ("zavisni redovi intake poslova nisu uklonjeni; vektori NISU dirani "
                      "i predmet je oznacen za brisanje — ponovite operaciju")
        return rez

    # 5b. tabele bez FK ka `predmeti`
    for tabela in TABELE_BEZ_FK:
        try:
            supa.table(tabela).delete().eq("predmet_id", predmet_id).execute()
            rez.obrisane_tabele.append(tabela)
        except Exception as exc:
            if _nema_objekta(exc):
                rez.preskocene_tabele.append(tabela)
                continue
            logger.error("[PREDMET-DELETE] tabela %s nije ociscena p=%.8s: %s",
                         tabela, predmet_id, exc)
            rez.neuspele_tabele.append(tabela)

    if rez.neuspele_tabele:
        rez.ishod = IshodPredmeta.RETRYABLE_FAILURE
        rez.razlog = (f"{len(rez.neuspele_tabele)} tabela nije ocisceno; VEKTORI NISU "
                      f"DIRANI i predmet je oznacen za brisanje — ponovite operaciju")
        return rez

    # ── 6. VEKTORI (nepovratno — ali predmet je već nevidljiv) ──────────────
    try:
        dokumenti = (supa.table("predmet_dokumenti").select("id")
                     .eq("predmet_id", predmet_id).eq("user_id", user_id).execute())
        dok_ids = [d["id"] for d in (getattr(dokumenti, "data", None) or []) if d.get("id")]
    except Exception as exc:
        logger.error("[PREDMET-DELETE] spisak dokumenata nije procitan p=%.8s: %s",
                     predmet_id, exc)
        rez.ishod = IshodPredmeta.RETRYABLE_FAILURE
        rez.razlog = "spisak dokumenata nije procitan — vektori bi ostali"
        rez.vektori = "NEUSPEH"
        return rez

    if not dok_ids:
        rez.vektori = "NEMA_DOKUMENATA"
    elif index is None:
        rez.ishod = IshodPredmeta.RETRYABLE_FAILURE
        rez.razlog = "indeks nije dostupan, a predmet ima dokumente"
        rez.vektori = "NEUSPEH"
        return rez
    else:
        neuspeli = []
        for d_id in dok_ids:
            try:
                v = obrisi_vektore_dokumenta(supa, index, user_id=user_id,
                                             predmet_id=predmet_id, document_id=d_id)
            except Exception as exc:
                logger.error("[PREDMET-DELETE] vektori dok=%.8s izuzetak: %s", d_id, exc)
                neuspeli.append(d_id)
                continue
            if not v.uspeh and v.ishod != VIshod.ALREADY_ABSENT:
                neuspeli.append(d_id)
        if neuspeli:
            rez.ishod = IshodPredmeta.RETRYABLE_FAILURE
            rez.vektori = "NEUSPEH"
            rez.razlog = (f"vektori nisu uklonjeni za {len(neuspeli)} dokumenata; "
                          f"predmet je oznacen za brisanje — ponovite operaciju")
            return rez
        rez.vektori = "OBRISANI"

    # ── 7. PREDMET (poslednji; CASCADE cisti svojih 16) ─────────────────────
    try:
        supa.table("predmeti").delete().eq("id", predmet_id).eq("user_id", user_id).execute()
    except Exception as exc:
        logger.error("[PREDMET-DELETE] `predmeti` red nije obrisan p=%.8s: %s", predmet_id, exc)
        rez.ishod = IshodPredmeta.RETRYABLE_FAILURE
        rez.neuspele_tabele.append("predmeti")
        rez.razlog = "vezani podaci su uklonjeni, ali sam predmet nije obrisan"
        return rez

    rez.ishod = IshodPredmeta.DELETED
    rez.razlog = ""
    return rez
