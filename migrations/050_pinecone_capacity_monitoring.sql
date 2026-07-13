-- ============================================================================
-- Vindex AI — Migracija 050: Pinecone Capacity Monitoring
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 049.
--
-- Kreira pinecone_capacity_snapshots — dnevni snapshot broja vektora i
-- procenjene veličine po Pinecone namespace-u, za praćenje trenda rasta
-- (nedeljno/mesečno) i ranu detekciju približavanja storage limitu.
-- Snapshot se upisuje pri svakoj poseti admin panela (najviše jednom dnevno
-- po namespace-u, preko UNIQUE constraint-a + upsert).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.pinecone_capacity_snapshots (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date    date        NOT NULL DEFAULT current_date,
    namespace        text        NOT NULL,
    vector_count     bigint      NOT NULL,
    estimated_bytes  bigint      NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snapshot_date, namespace)
);

CREATE INDEX IF NOT EXISTS idx_pinecone_snapshots_ns_date
    ON public.pinecone_capacity_snapshots (namespace, snapshot_date DESC);

ALTER TABLE public.pinecone_capacity_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "pinecone_capacity_snapshots_service_role" ON public.pinecone_capacity_snapshots
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================================
-- Provera (opciono)
-- SELECT namespace, vector_count, estimated_bytes, snapshot_date
--   FROM public.pinecone_capacity_snapshots
--   ORDER BY snapshot_date DESC, namespace LIMIT 20;
-- ============================================================================
