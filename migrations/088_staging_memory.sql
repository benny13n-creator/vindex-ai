-- ============================================================================
-- Vindex AI — Migracija 088: Staging Memory (Institutional Memory V2)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 087.
--
-- Institutional Memory Architecture V2 (2026-07-26), STUB 1 — Quality Gate &
-- Staging Memory. AI-generisani nacrti/podnesci se VIŠE NE indeksiraju
-- direktno u produkcioni kancelarija_{id}/user_{id} Pinecone namespace (v.
-- prethodnu implementaciju u routers/drafting.py's _index_finalized_draft,
-- sada zamenjenu _stage_draft_for_review). Umesto toga, svaki finalizovan
-- nacrt prvo prolazi kroz automatski Quality Gate (services/quality_gate.py)
-- i čeka eksplicitnu potvrdu advokata (is_lawyer_approved) PRE nego što
-- ijedan vektor uđe u glavnu bazu znanja kancelarije -- sprečava "toksično
-- učenje" (AI koji uči iz sopstvenih neproverenih nacrta).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.staging_memory (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             text        NOT NULL,
    kancelarija_id      uuid,
    predmet_id          text        NOT NULL,
    tip                 text        NOT NULL,
    naziv               text        NOT NULL DEFAULT '',
    tekst               text        NOT NULL,

    -- Quality Gate rezultat (services/quality_gate.py) -- izračunat pri
    -- kreiranju, PRE bilo kakve advokatske akcije.
    confidence_score    numeric(3,2) NOT NULL DEFAULT 0.00
                        CHECK (confidence_score >= 0.00 AND confidence_score <= 1.00),
    quality_detail      jsonb       NOT NULL DEFAULT '{}'::jsonb,

    -- Eksplicitna potvrda advokata -- OBAVEZNA, ali NIJE dovoljna sama po sebi
    -- (v. STUB 1.3: promocija u Pinecone zahteva is_lawyer_approved=true I
    -- confidence_score >= 0.85, oba uslova, ne samo jedan).
    is_lawyer_approved  boolean     NOT NULL DEFAULT false,
    approved_by         text,
    approved_at         timestamptz,

    status              text        NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'approved', 'rejected')),

    -- Da li je stvarno promovisano u Pinecone (moze biti approved=true a
    -- pinecone_indexed=false ako je confidence_score < 0.85 -- v. gore).
    pinecone_indexed    boolean     NOT NULL DEFAULT false,
    pinecone_namespace  text,

    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_staging_memory_predmet ON public.staging_memory (predmet_id);
CREATE INDEX IF NOT EXISTS idx_staging_memory_user_status ON public.staging_memory (user_id, status);

ALTER TABLE public.staging_memory ENABLE ROW LEVEL SECURITY;

CREATE POLICY "staging_memory_sopstveni" ON public.staging_memory
    FOR ALL USING (auth.uid()::text = user_id) WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "staging_memory_service_role" ON public.staging_memory
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================================
-- Provera (opciono)
-- SELECT id, tip, confidence_score, is_lawyer_approved, status, pinecone_indexed
--   FROM public.staging_memory ORDER BY created_at DESC LIMIT 20;
-- ============================================================================
