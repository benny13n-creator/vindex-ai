-- Vindex AI — migration 093: Canonical Document Segmentation (Program Intake Sprint 005)
--
-- One uploaded file is not always one legal document. This migration adds
-- the identity + lifecycle table for segments produced by
-- shared/intake_segment.py::segment_document() — the single canonical
-- segmentation engine (Phase 3). Every segment gets its own row here BEFORE
-- it is ever classified, matching the founder's own "Segment Identity"
-- requirement (Phase 4): unique id, parent upload id, order, start/end
-- page, segmentation reason, confidence, and its own status lifecycle
-- (Phase 6, partial failure recovery — one segment's failure must not be
-- indistinguishable from another's success, and must not abort siblings).
--
-- Design note (synthesis of two independent fork proposals during this
-- sprint): intake_documents/extracted_entities/intake_review_queue need
-- ZERO new columns — they already scope correctly via document_id, and a
-- segment's own intake_documents row is created the same way a
-- single-document job's row always has been (Phase 5: segments hand off to
-- the EXISTING classification pipeline unchanged). Only
-- intake_processing_outcomes is job-scoped (not document-scoped) today, so
-- it alone gets a new nullable segment_id column — without it, multiple
-- segments' outcomes under one job would collide/be ambiguous.
--
-- Scope boundary (explicit, not an oversight): this migration does NOT add
-- a new terminal 'partially_failed' status to intake_jobs, and does NOT
-- change claim/complete/fail RPCs. A segment that permanently fails after
-- its bounded in-process retries routes its job to the EXISTING
-- 'awaiting_review' status via a new intake_review_queue reason
-- ('processing_failed') — whether a job with M-1-of-M completed segments
-- may ever be finalized into a case is a founder product decision, left
-- open on purpose (see Mission Report, Deferred).

CREATE TABLE IF NOT EXISTS public.intake_job_segments (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intake_job_id            UUID NOT NULL REFERENCES public.intake_jobs(id),
    segment_index            INTEGER NOT NULL,
    start_page               INTEGER NOT NULL,
    end_page                 INTEGER NOT NULL,
    segmentation_reason      TEXT NOT NULL,
    segmentation_confidence  NUMERIC,
    segmentation_method      TEXT NOT NULL DEFAULT 'deterministic_signals_v1',
    boundary_signals         JSONB NOT NULL DEFAULT '[]'::jsonb,
    status                   TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                                  'pending', 'processing', 'completed', 'awaiting_review', 'failed'
                              )),
    document_id              UUID REFERENCES public.intake_documents(id),
    attempts                 INTEGER NOT NULL DEFAULT 0,
    max_attempts              INTEGER NOT NULL DEFAULT 2,
    last_error                TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT intake_job_segments_order_valid CHECK (end_page >= start_page),
    CONSTRAINT intake_job_segments_unique_index UNIQUE (intake_job_id, segment_index)
);

COMMENT ON TABLE public.intake_job_segments IS
    'Program Intake Sprint 005 — one row per canonical legal document found inside one uploaded file by shared/intake_segment.py::segment_document(). Only ever populated for jobs that segmented into 2+ documents; a job that stayed one whole document (the overwhelmingly common case) writes no rows here at all, matching pre-Sprint-005 behavior byte-for-byte.';
COMMENT ON COLUMN public.intake_job_segments.segmentation_reason IS
    'Which signal(s) confirmed this segment boundary — e.g. heading_keyword, case_number_change, combined_signals, or single_document for the sole-segment degenerate case. See docs/architecture segmentation signal spec.';
COMMENT ON COLUMN public.intake_job_segments.boundary_signals IS
    'Full SegmentSignal list (kind/strength/page_number/detail) that justified this cut — audit trail for why the engine split (or did not split) here.';
COMMENT ON COLUMN public.intake_job_segments.max_attempts IS
    'Bounded in-process retry count (default 2), not a cross-run backoff schedule — a genuinely new cross-run retry-claim RPC is out of this sprint''s bounded scope (see Mission Report, Deferred).';

CREATE INDEX IF NOT EXISTS idx_intake_job_segments_job ON public.intake_job_segments(intake_job_id, segment_index);
CREATE INDEX IF NOT EXISTS idx_intake_job_segments_status ON public.intake_job_segments(status) WHERE status IN ('pending', 'processing', 'failed');

ALTER TABLE public.intake_job_segments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "intake_job_segments_service_role" ON public.intake_job_segments;
CREATE POLICY "intake_job_segments_service_role" ON public.intake_job_segments
    FOR ALL USING (auth.role() = 'service_role');


ALTER TABLE public.intake_processing_outcomes
    ADD COLUMN IF NOT EXISTS segment_id UUID REFERENCES public.intake_job_segments(id);

COMMENT ON COLUMN public.intake_processing_outcomes.segment_id IS
    'Program Intake Sprint 005 — nullable. NULL for every outcome written before this sprint and for every single-segment job after it (identical to before). Set only when a job segmented into 2+ documents, so each segment''s outcome under one job_id is distinguishable, not ambiguous.';


ALTER TABLE public.intake_review_queue DROP CONSTRAINT IF EXISTS intake_review_queue_reason_check;
ALTER TABLE public.intake_review_queue ADD CONSTRAINT intake_review_queue_reason_check CHECK (reason IN (
    'low_confidence_extraction', 'ocr_failed', 'classification_uncertain',
    'segmentation_uncertain', 'processing_failed'
));

COMMENT ON CONSTRAINT intake_review_queue_reason_check ON public.intake_review_queue IS
    'segmentation_uncertain (Sprint 005) — engine found evidence of a possible extra document but not enough to auto-split safely (mission mandate: an incorrect split is worse than an unsplit document, so thin evidence routes to a human instead of guessing). processing_failed (Sprint 005) — a segment permanently failed after its bounded in-process retries; sibling segments in the same job were not affected.';
