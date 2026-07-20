-- ============================================================================
-- Vindex AI — Migracija 075: Uklanjanje vindex_memory (mrtav kod)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 074.
--
-- Zasto: routers/vindex_memory.py je registrovan u api.py ali GA NIKO NIJE
-- POZIVAO — nula poziva iz frontenda (static/vindex.js), nula poziva iz
-- ostatka backenda. firm_memory.py (routers/firm_memory.py, tabela
-- memory_entries) je stvarni, zivi sistem — vec ozicen u copilot chat
-- kontekst (_fetch_firm_memory_context, api.py). vindex_memory.py je
-- napusten paralelni pokusaj iste ideje.
--
-- OTKRIVENO PRI CISCENJU (2026-07-16): feature_registry red za
-- 'vindex_memory' je status=ACTIVE, visible=visible, chargeable=true,
-- dodeljen business_group_id za G5 (Znanje kancelarije) — sto znaci da se
-- "Vindex Memory" TRENUTNO prikazuje na javnoj cenovnoj matrici
-- (GET /api/plan/pricing-matrix) kao funkcija ukljucena u professional
-- tarifu, iako iza nje ne stoji nijedna zivi endpoint. Isti obrazac rizika
-- kao pricing mismatch iz migracije 068 — kupac vidi funkciju koja ne radi.
--
-- Redosled: prvo obrisati feature_registry red (da nestane sa cenovnika
-- odmah), zatim tabelu (nije deljena ni sa jednim drugim modulom — jedini
-- pisac/citac bio je routers/vindex_memory.py, sada obrisan).
--
-- NAPOMENA: Pinecone namespace-ovi mem_{uid}/mem_firma_{firma_id} koje je
-- vindex_memory.py pisao ostaju u Pinecone-u kao osiroceli vektori — ovo
-- nije SQL sema pa ova migracija to ne dira. Nizak prioritet (ne kosta
-- upisne jedinice, samo storage) — ciscenje po potrebi kroz Pinecone admin,
-- van obima ove migracije.
-- ============================================================================

DELETE FROM public.feature_registry WHERE feature_key = 'vindex_memory';

DROP TABLE IF EXISTS public.vindex_memory;
