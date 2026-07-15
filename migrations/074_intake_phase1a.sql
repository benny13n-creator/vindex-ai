-- ============================================================================
-- Vindex AI — Migracija 074: Smart Intake Phase 1A — Classification, Extraction,
-- Confidence Graph, Review Queue, Processing Outcomes
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 073.
--
-- Founder-ov proizvodni Definition of Done za ovu fazu: advokat uploaduje
-- presudu, za manje od minut vidi klasifikaciju, ključne podatke, rok, jasan
-- nivo pouzdanosti — i ako postoji nesigurnost, VIDI SAMO nesigurna polja
-- (obicno 1-2, ne 20), ispravljiva za 10 sekundi. Case-matching NIJE u
-- ovom obimu (founder-ova eksplicitna uža lista za 1A) — dokument ostaje
-- nepovezan sa predmet_id kroz celu Fazu 1A.
--
-- Naučena lekcija iz migracije 073 (primenjena ovde unapred, ne posle
-- grešaka): CREATE POLICY dobija DROP POLICY IF EXISTS ispred, RPC koji
-- radi UPDATE/INSERT ... RETURNING pod RLS dobija SECURITY DEFINER.
--
-- Tabele:
--   intake_documents           — rezultat klasifikacije, 1:1 sa intake_jobs
--                                 u ovom obimu (jedan posao = jedan dokument).
--   extracted_entities          — Confidence Graph (ADR-0005) — SVAKO polje
--                                 (case_number/judge/deadline/...) ima
--                                 sopstveni confidence, ne jedan skor po
--                                 dokumentu.
--   intake_review_queue         — SAMO polja ispod praga, ne ceo dokument —
--                                 low_confidence_fields govori tacno UI-ju
--                                 koja polja da prikaze za ispravku.
--   intake_processing_outcomes  — founder-ov eksplicitan zahtev: čuva se
--                                 posle SVAKOG obrađenog dokumenta, ne za
--                                 analitiku danas nego za fino podešavanje
--                                 pragova/heuristika/UX-a za mesec dana.
-- ============================================================================

-- intake_jobs je nedostajao original_filename/mime_type — potreban je pravi
-- ekstenzija fajla da bi extract() (uploaded_doc/extractor.py) znao koji
-- parser da pozove (PDF/DOCX/TXT).
ALTER TABLE public.intake_jobs ADD COLUMN IF NOT EXISTS original_filename TEXT;
ALTER TABLE public.intake_jobs ADD COLUMN IF NOT EXISTS mime_type TEXT;


CREATE TABLE IF NOT EXISTS public.intake_documents (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intake_job_id            UUID NOT NULL REFERENCES public.intake_jobs(id),
    document_type            TEXT NOT NULL CHECK (document_type IN (
                                  'lawsuit', 'response', 'appeal', 'judgment', 'contract',
                                  'invoice', 'power_of_attorney', 'evidence', 'email',
                                  'court_decision', 'enforcement', 'legal_opinion', 'other'
                              )),
    classification_confidence NUMERIC NOT NULL,
    classification_method    TEXT NOT NULL CHECK (classification_method IN ('heuristic', 'llm')),
    ocr_confidence            NUMERIC,
    ocr_used                  BOOLEAN NOT NULL DEFAULT false,
    suggested_filename        TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.intake_documents IS
    'Rezultat klasifikacije jednog intake_jobs posla. 1:1 sa intake_jobs u Fazi 1A (nema batch-multi-document logike još). suggested_filename je predlog, nikad tiho ne prepisuje original.';

CREATE INDEX IF NOT EXISTS idx_intake_documents_job ON public.intake_documents(intake_job_id);

ALTER TABLE public.intake_documents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "intake_documents_service_role" ON public.intake_documents;
CREATE POLICY "intake_documents_service_role" ON public.intake_documents
    FOR ALL USING (auth.role() = 'service_role');


CREATE TABLE IF NOT EXISTS public.extracted_entities (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID NOT NULL REFERENCES public.intake_documents(id),
    entity_type         TEXT NOT NULL CHECK (entity_type IN (
                             'case_number', 'judge', 'plaintiff', 'defendant',
                             'court', 'deadline', 'amount', 'law_cited'
                         )),
    value               TEXT,
    confidence           NUMERIC NOT NULL,
    extraction_method    TEXT NOT NULL CHECK (extraction_method IN ('regex', 'heuristic', 'llm')),
    reviewed             BOOLEAN NOT NULL DEFAULT false,
    corrected_value      TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.extracted_entities IS
    'Confidence Graph (ADR-0005) — svaki entitet nezavisno ocenjen, ne jedan skor po dokumentu. reviewed/corrected_value se popunjava kroz 10-sekundnu ispravku (routers/smart_intake.py) — original value se NIKAD ne briše, corrected_value je dodatak.';

CREATE INDEX IF NOT EXISTS idx_extracted_entities_document ON public.extracted_entities(document_id);
CREATE INDEX IF NOT EXISTS idx_extracted_entities_low_confidence ON public.extracted_entities(document_id, confidence) WHERE reviewed = false;

ALTER TABLE public.extracted_entities ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "extracted_entities_service_role" ON public.extracted_entities;
CREATE POLICY "extracted_entities_service_role" ON public.extracted_entities
    FOR ALL USING (auth.role() = 'service_role');


CREATE TABLE IF NOT EXISTS public.intake_review_queue (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intake_job_id            UUID NOT NULL REFERENCES public.intake_jobs(id),
    document_id              UUID REFERENCES public.intake_documents(id),
    reason                   TEXT NOT NULL CHECK (reason IN (
                                  'low_confidence_extraction', 'ocr_failed', 'classification_uncertain'
                              )),
    low_confidence_fields     JSONB NOT NULL DEFAULT '[]'::jsonb,
    resolved_at               TIMESTAMPTZ,
    resolved_by               TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.intake_review_queue IS
    'low_confidence_fields je NIZ entity_type stringova ispod praga (npr. ["deadline"]) — ovo je ono što UI čita da pokaže "2 stavke", ne ceo dokument. Prazan niz + reason=ocr_failed znači ceo dokument nečitljiv (drugačija UX poruka).';

CREATE INDEX IF NOT EXISTS idx_intake_review_queue_unresolved ON public.intake_review_queue(created_at) WHERE resolved_at IS NULL;

ALTER TABLE public.intake_review_queue ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "intake_review_queue_service_role" ON public.intake_review_queue;
CREATE POLICY "intake_review_queue_service_role" ON public.intake_review_queue
    FOR ALL USING (auth.role() = 'service_role');


CREATE TABLE IF NOT EXISTS public.intake_processing_outcomes (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intake_job_id         UUID NOT NULL REFERENCES public.intake_jobs(id),
    document_type         TEXT,
    ocr_confidence         NUMERIC,
    entity_confidence      JSONB NOT NULL DEFAULT '{}'::jsonb,
    user_corrected         BOOLEAN NOT NULL DEFAULT false,
    fields_corrected       TEXT[] NOT NULL DEFAULT '{}',
    processing_time_ms     INTEGER,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.intake_processing_outcomes IS
    'Founder-ov eksplicitan zahtev (Faza 1A) — upisuje se posle SVAKOG obrađenog dokumenta, ne za analitiku danas nego za fino podešavanje pragova/heuristika/UX-a kada se nakupi realan volumen. Append-only, nikad UPDATE — ako korisnik naknadno ispravi entitet posle inicijalnog upisa, dodaje se NOV red preko routers/smart_intake.py korekcionog endpoint-a, stari red ostaje netaknut.';

CREATE INDEX IF NOT EXISTS idx_intake_processing_outcomes_job ON public.intake_processing_outcomes(intake_job_id);

ALTER TABLE public.intake_processing_outcomes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "intake_processing_outcomes_service_role" ON public.intake_processing_outcomes;
CREATE POLICY "intake_processing_outcomes_service_role" ON public.intake_processing_outcomes
    FOR ALL USING (auth.role() = 'service_role');
