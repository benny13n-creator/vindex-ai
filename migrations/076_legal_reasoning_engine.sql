-- ============================================================================
-- Migration 076 — Legal Reasoning Engine, Phase 0
--
-- Six relational tables, per explicit founder decision (2026-07-23,
-- docs/architecture/LEGAL_REASONING_ARCHITECTURE.md Sec 5a/5b): jsonb is
-- NOT the canonical store for the Reasoning Graph — queries like "find
-- every argument based on Article 154" or "find every claim with
-- confidence < 0.6" must be real SQL, not application-side JSON parsing.
--
-- No foreign keys — same pattern as every other migration in this repo
-- (migration 057's documented incident: FK type mismatches against
-- possibly-pre-existing tables with TEXT instead of UUID columns caused
-- "operator does not exist: text = uuid" failures). Integrity is enforced
-- at the application layer (services/legal_reasoning_engine.py), same as
-- predmet_dokazi/predmet_hronologija/predmet_genome_history etc.
--
-- Phase 0 scope reminder (binding, not just documentation): this schema
-- is written to be read by nothing else yet. No other table, router, or
-- event handler references these tables in this migration or in the
-- Phase 0 code that reads it.
-- ============================================================================

-- reasoning_graph — one row per (predmet_id, verzija): the version header.
CREATE TABLE IF NOT EXISTS public.reasoning_graph (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id     uuid        NOT NULL,
    user_id        uuid        NOT NULL,
    verzija        int         NOT NULL DEFAULT 1,
    genome_verzija int,
    trigger_event  text        NOT NULL DEFAULT 'manual_generate',
    status         text        NOT NULL DEFAULT 'generating',
    greska         text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reasoning_graph_predmet ON public.reasoning_graph(predmet_id, verzija DESC);
ALTER TABLE public.reasoning_graph ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi reasoning graf svojih predmeta" ON public.reasoning_graph;
CREATE POLICY "Korisnik vidi reasoning graf svojih predmeta" ON public.reasoning_graph
    FOR SELECT USING (user_id::text = auth.uid()::text);
DROP POLICY IF EXISTS "Korisnik upisuje reasoning graf svojih predmeta" ON public.reasoning_graph;
CREATE POLICY "Korisnik upisuje reasoning graf svojih predmeta" ON public.reasoning_graph
    FOR INSERT WITH CHECK (user_id::text = auth.uid()::text);
DROP POLICY IF EXISTS "Korisnik azurira reasoning graf svojih predmeta" ON public.reasoning_graph;
CREATE POLICY "Korisnik azurira reasoning graf svojih predmeta" ON public.reasoning_graph
    FOR UPDATE USING (user_id::text = auth.uid()::text);


-- reasoning_nodes — Fact | LegalElement | Norm | Claim, typed rows.
CREATE TABLE IF NOT EXISTS public.reasoning_nodes (
    id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    graph_id             uuid        NOT NULL,
    predmet_id           uuid        NOT NULL,
    user_id              uuid        NOT NULL,
    node_type            text        NOT NULL,  -- 'Fact' | 'LegalElement' | 'Norm' | 'Claim'
    label                text        NOT NULL,
    detalji              jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_from_event_id text,
    created_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reasoning_nodes_graph ON public.reasoning_nodes(graph_id);
CREATE INDEX IF NOT EXISTS idx_reasoning_nodes_predmet_type ON public.reasoning_nodes(predmet_id, node_type);
ALTER TABLE public.reasoning_nodes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi reasoning cvorove svojih predmeta" ON public.reasoning_nodes;
CREATE POLICY "Korisnik vidi reasoning cvorove svojih predmeta" ON public.reasoning_nodes
    FOR SELECT USING (user_id::text = auth.uid()::text);
DROP POLICY IF EXISTS "Korisnik upisuje reasoning cvorove svojih predmeta" ON public.reasoning_nodes;
CREATE POLICY "Korisnik upisuje reasoning cvorove svojih predmeta" ON public.reasoning_nodes
    FOR INSERT WITH CHECK (user_id::text = auth.uid()::text);


-- reasoning_edges — supports | satisfies | creates, references two nodes.
CREATE TABLE IF NOT EXISTS public.reasoning_edges (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    graph_id     uuid        NOT NULL,
    predmet_id   uuid        NOT NULL,
    user_id      uuid        NOT NULL,
    edge_type    text        NOT NULL,  -- 'supports' | 'satisfies' | 'creates'
    from_node_id uuid        NOT NULL,
    to_node_id   uuid        NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reasoning_edges_graph ON public.reasoning_edges(graph_id);
CREATE INDEX IF NOT EXISTS idx_reasoning_edges_from ON public.reasoning_edges(from_node_id);
CREATE INDEX IF NOT EXISTS idx_reasoning_edges_to ON public.reasoning_edges(to_node_id);
ALTER TABLE public.reasoning_edges ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi reasoning veze svojih predmeta" ON public.reasoning_edges;
CREATE POLICY "Korisnik vidi reasoning veze svojih predmeta" ON public.reasoning_edges
    FOR SELECT USING (user_id::text = auth.uid()::text);
DROP POLICY IF EXISTS "Korisnik upisuje reasoning veze svojih predmeta" ON public.reasoning_edges;
CREATE POLICY "Korisnik upisuje reasoning veze svojih predmeta" ON public.reasoning_edges
    FOR INSERT WITH CHECK (user_id::text = auth.uid()::text);


-- reasoning_evidence — links a Fact node to its source (predmet_dokazi row
-- or predmet_dokumenti row) -- the "was this actually in the case file"
-- check that evidence_coverage (Sec 10a) is computed from.
CREATE TABLE IF NOT EXISTS public.reasoning_evidence (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id      uuid        NOT NULL,
    predmet_id   uuid        NOT NULL,
    user_id      uuid        NOT NULL,
    dokaz_id     uuid,
    dokument_id  uuid,
    napomena     text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reasoning_evidence_node ON public.reasoning_evidence(node_id);
ALTER TABLE public.reasoning_evidence ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi reasoning dokaze svojih predmeta" ON public.reasoning_evidence;
CREATE POLICY "Korisnik vidi reasoning dokaze svojih predmeta" ON public.reasoning_evidence
    FOR SELECT USING (user_id::text = auth.uid()::text);
DROP POLICY IF EXISTS "Korisnik upisuje reasoning dokaze svojih predmeta" ON public.reasoning_evidence;
CREATE POLICY "Korisnik upisuje reasoning dokaze svojih predmeta" ON public.reasoning_evidence
    FOR INSERT WITH CHECK (user_id::text = auth.uid()::text);


-- reasoning_sources — links a Norm node to its retrieval source (proves a
-- cited article was actually returned by retrieve.py, not invented) -- the
-- "retrieval_agreement" check that Sec 10a's confidence formula reads.
CREATE TABLE IF NOT EXISTS public.reasoning_sources (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id          uuid        NOT NULL,
    predmet_id       uuid        NOT NULL,
    user_id          uuid        NOT NULL,
    zakon            text,
    clan             text,
    retrieval_score  float8,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reasoning_sources_node ON public.reasoning_sources(node_id);
ALTER TABLE public.reasoning_sources ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi reasoning izvore svojih predmeta" ON public.reasoning_sources;
CREATE POLICY "Korisnik vidi reasoning izvore svojih predmeta" ON public.reasoning_sources
    FOR SELECT USING (user_id::text = auth.uid()::text);
DROP POLICY IF EXISTS "Korisnik upisuje reasoning izvore svojih predmeta" ON public.reasoning_sources;
CREATE POLICY "Korisnik upisuje reasoning izvore svojih predmeta" ON public.reasoning_sources
    FOR INSERT WITH CHECK (user_id::text = auth.uid()::text);


-- reasoning_confidence — one row per Claim node, the weighted formula's
-- components (Sec 10a) stored separately, not collapsed until display —
-- keeps the formula itself auditable/re-weightable without regeneration.
CREATE TABLE IF NOT EXISTS public.reasoning_confidence (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id             uuid        NOT NULL,
    predmet_id          uuid        NOT NULL,
    user_id             uuid        NOT NULL,
    evidence_coverage   float8      NOT NULL DEFAULT 0,
    retrieval_agreement float8      NOT NULL DEFAULT 0,
    precedent_support   float8      NOT NULL DEFAULT 0,
    model_certainty     float8      NOT NULL DEFAULT 0,
    confidence_total    float8      NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reasoning_confidence_node ON public.reasoning_confidence(node_id);
ALTER TABLE public.reasoning_confidence ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Korisnik vidi reasoning pouzdanost svojih predmeta" ON public.reasoning_confidence;
CREATE POLICY "Korisnik vidi reasoning pouzdanost svojih predmeta" ON public.reasoning_confidence
    FOR SELECT USING (user_id::text = auth.uid()::text);
DROP POLICY IF EXISTS "Korisnik upisuje reasoning pouzdanost svojih predmeta" ON public.reasoning_confidence;
CREATE POLICY "Korisnik upisuje reasoning pouzdanost svojih predmeta" ON public.reasoning_confidence
    FOR INSERT WITH CHECK (user_id::text = auth.uid()::text);
