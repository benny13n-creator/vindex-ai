-- Vindex AI — migration 094: Canonical Case Assimilation (Program Intake Sprint 006)
--
-- Sprint 005 proved one upload can contain multiple logical documents. Sprint
-- 006 proves each of those documents becomes part of a specific, correctly-
-- identified case (predmet) and client (klijent) — deterministically, never a
-- guess. This migration adds the three columns that make that provable:
--
-- 1. predmeti.broj_predmeta — until this migration, predmeti had NO
--    structured case-number column at all (Sprint 006 Phase 1 audit,
--    confirmed by grep across every migration and every predmeti insert
--    call site) — the extracted case number was written only as free text
--    inside `opis`, meaning no pipeline could ever recognize "this incoming
--    document's case number matches an already-open case." Nullable — most
--    existing rows and many new ones (no case number extracted) will never
--    have one; that is not a violation, it is the correct honest state.
--
-- 2. intake_job_segments.assimilation_status — Sprint 005's own `status`
--    column tracks CLASSIFICATION lifecycle (pending/processing/completed/
--    awaiting_review/failed). Ownership Resolution (Sprint 006) is a
--    genuinely different question asked AFTER classification succeeds —
--    "does this classified document belong to a specific case/client" — so
--    it gets its own orthogonal column, the same "one owner per concern"
--    reasoning Sprint 005 itself used to keep intake_job_segments' own
--    identity/lifecycle fields from being overloaded onto intake_documents.
--
-- 3. predmet_dokumenti.source_intake_job_segment_id — the one new lineage
--    FK that makes the full chain (upload → segment → classification →
--    ownership decision → final case placement) reconstructable via a
--    single JOIN, closing Sprint 001's long-open INTAKE-003 gap for
--    segmented jobs specifically. NULL for every document created before
--    this migration, and NULL for every single-document job after it
--    (Sprint 005's own invariant: a job that stayed one whole document
--    writes zero intake_job_segments rows, so there is nothing to link to)
--    — this is a structural absence, not a lost lineage.
--
-- The UNIQUE constraint below is Evidence Integrity's (Phase 6) concrete,
-- DB-enforced invariant: one segment can never produce two predmet_dokumenti
-- rows (no duplicates) — checkable independent of any application code.

ALTER TABLE public.predmeti
    ADD COLUMN IF NOT EXISTS broj_predmeta TEXT;

COMMENT ON COLUMN public.predmeti.broj_predmeta IS
    'Program Intake Sprint 006 — normalized court case number, populated at case-creation time when Ownership Resolution extracted one with high confidence. Nullable by design (most cases today, and any case opened without a recognizable case number, correctly have none). Used to auto-attach a later incoming document to this SAME case instead of creating a duplicate — never used to guess between 2+ matching cases (that routes to Review Required instead, see shared/case_assimilation.py).';

CREATE INDEX IF NOT EXISTS idx_predmeti_broj_predmeta
    ON public.predmeti(user_id, broj_predmeta)
    WHERE broj_predmeta IS NOT NULL;


ALTER TABLE public.intake_job_segments
    ADD COLUMN IF NOT EXISTS assimilation_status TEXT NOT NULL DEFAULT 'pending' CHECK (assimilation_status IN (
        'pending', 'resolved', 'review_required', 'failed'
    ));

COMMENT ON COLUMN public.intake_job_segments.assimilation_status IS
    'Program Intake Sprint 006 — Ownership Resolution''s own lifecycle, orthogonal to this table''s existing `status` column (classification lifecycle, Sprint 005). pending = not yet attempted; resolved = successfully registered into a predmet_dokumenti row; review_required = case/client evidence was insufficient, a human must confirm; failed = a technical error occurred during registration (distinct from review_required, which is an evidence-sufficiency outcome, not an error).';

CREATE INDEX IF NOT EXISTS idx_intake_job_segments_assimilation_status
    ON public.intake_job_segments(assimilation_status)
    WHERE assimilation_status IN ('pending', 'review_required', 'failed');


ALTER TABLE public.predmet_dokumenti
    ADD COLUMN IF NOT EXISTS source_intake_job_segment_id UUID REFERENCES public.intake_job_segments(id);

COMMENT ON COLUMN public.predmet_dokumenti.source_intake_job_segment_id IS
    'Program Intake Sprint 006 — lineage FK closing Sprint 001''s INTAKE-003 gap for segmented jobs: makes upload → segment → classification → ownership decision → case placement reconstructable via one JOIN. NULL for every document created before this migration and for every single-document job (Sprint 005''s own invariant — no intake_job_segments rows exist for those jobs at all, so NULL here is a structural absence, not a lost lineage).';

CREATE UNIQUE INDEX IF NOT EXISTS uq_predmet_dokumenti_source_segment
    ON public.predmet_dokumenti(source_intake_job_segment_id)
    WHERE source_intake_job_segment_id IS NOT NULL;

COMMENT ON INDEX public.uq_predmet_dokumenti_source_segment IS
    'Program Intake Sprint 006, Phase 6 (Evidence Integrity) — DB-enforced invariant: one segment can produce at most one predmet_dokumenti row, ever. A retry/replay that attempted to insert a second row for the same segment fails at the database level, not just by application-code discipline.';
