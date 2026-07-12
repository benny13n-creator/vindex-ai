-- ============================================================================
-- Vindex AI -- Migracija 059: Workflow Engine -- solo advokati + sistemski predlosci
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard -> SQL Editor, posle 058.
--
-- Kontekst: routers/workflow.py (migriran u 047, ali NIKAD ozicen na frontend)
-- je bio potpuno neupotrebljiv za solo advokate -- svaki endpoint je
-- zahtevao clanstvo u kancelariji (firma) i bacao 403/prazan odgovor bez
-- toga. Vecina korisnika trenutno NEMA kancelariju (opciono, kreira se
-- rucno). Ova migracija:
--
--   1. Dozvoljava kancelarija_id = NULL na workflow_instances/workflow_steps
--      (solo advokat -- vlasnistvo se prati preko kreirao_uid/workflow_id
--      umesto kancelarija_id). Servisni kljuc (shared/deps.py _get_supa)
--      zaobilazi RLS u potpunosti, pa je ovo defense-in-depth, ne stvarna
--      app-logika -- app logika je popravljena direktno u workflow.py.
--   2. Dodaje 3 sistemska predloska (kancelarija_id = NULL, vec podrzano
--      postojecom "wt_firma_read" RLS politikom iz migracije 047) --
--      Parnicni postupak, Izvrsni postupak, Zalbeni postupak -- plus
--      "Prazan workflow" kao minimalni fallback. Idempotentno (WHERE NOT
--      EXISTS), sigurno za ponovno pokretanje.
-- ============================================================================

ALTER TABLE public.workflow_instances ALTER COLUMN kancelarija_id DROP NOT NULL;
ALTER TABLE public.workflow_steps     ALTER COLUMN kancelarija_id DROP NOT NULL;

DROP POLICY IF EXISTS "wi_firma_read" ON public.workflow_instances;
CREATE POLICY "wi_firma_read" ON public.workflow_instances FOR SELECT
    USING (
        (kancelarija_id IS NOT NULL AND (
            kancelarija_id IN (
                SELECT kancelarija_id FROM kancelarija_clanovi
                WHERE user_id = auth.uid()::text AND status = 'aktivan'
            )
            OR kancelarija_id IN (
                SELECT id FROM kancelarije WHERE admin_uid = auth.uid()::text
            )
        ))
        OR (kancelarija_id IS NULL AND kreirao_uid = auth.uid()::text)
    );

DROP POLICY IF EXISTS "ws_firma_read" ON public.workflow_steps;
CREATE POLICY "ws_firma_read" ON public.workflow_steps FOR SELECT
    USING (
        (kancelarija_id IS NOT NULL AND (
            kancelarija_id IN (
                SELECT kancelarija_id FROM kancelarija_clanovi
                WHERE user_id = auth.uid()::text AND status = 'aktivan'
            )
            OR kancelarija_id IN (
                SELECT id FROM kancelarije WHERE admin_uid = auth.uid()::text
            )
        ))
        OR (kancelarija_id IS NULL AND workflow_id IN (
            SELECT id FROM workflow_instances WHERE kreirao_uid = auth.uid()::text
        ))
    );

-- ─── Sistemski predlosci (kancelarija_id = NULL -- vidljivi svima) ───────────

INSERT INTO public.workflow_templates (kancelarija_id, naziv, tip_predmeta, opis, koraci)
SELECT NULL, 'Prazan workflow', NULL,
       'Minimalni okvir za praćenje napretka na predmetu.',
       '[
         {"naziv":"Rad na predmetu","opis":"Opšti okvir za praćenje napretka.","rok_dana":30,"eskalacija_dana":10}
       ]'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM public.workflow_templates WHERE kancelarija_id IS NULL AND naziv = 'Prazan workflow'
);

INSERT INTO public.workflow_templates (kancelarija_id, naziv, tip_predmeta, opis, koraci)
SELECT NULL, 'Parnični postupak', 'gradjansko',
       'Standardni tok gradjanske parnice od pripreme tužbe do presude.',
       '[
         {"naziv":"Priprema tužbe","rok_dana":7,"eskalacija_dana":3},
         {"naziv":"Podnošenje tužbe","rok_dana":2,"eskalacija_dana":1},
         {"naziv":"Prijem odgovora na tužbu","rok_dana":30,"eskalacija_dana":5},
         {"naziv":"Pripremno ročište","rok_dana":20,"eskalacija_dana":5},
         {"naziv":"Glavna rasprava","rok_dana":45,"eskalacija_dana":5},
         {"naziv":"Prijem presude","rok_dana":30,"eskalacija_dana":5}
       ]'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM public.workflow_templates WHERE kancelarija_id IS NULL AND naziv = 'Parnični postupak'
);

INSERT INTO public.workflow_templates (kancelarija_id, naziv, tip_predmeta, opis, koraci)
SELECT NULL, 'Izvršni postupak', NULL,
       'Tok izvršnog postupka od predloga za izvršenje do naplate.',
       '[
         {"naziv":"Priprema predloga za izvršenje","rok_dana":5,"eskalacija_dana":2},
         {"naziv":"Podnošenje predloga","rok_dana":2,"eskalacija_dana":1},
         {"naziv":"Rešenje o izvršenju","rok_dana":20,"eskalacija_dana":5},
         {"naziv":"Sprovođenje izvršenja","rok_dana":45,"eskalacija_dana":7},
         {"naziv":"Naplata / okončanje postupka","rok_dana":20,"eskalacija_dana":5}
       ]'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM public.workflow_templates WHERE kancelarija_id IS NULL AND naziv = 'Izvršni postupak'
);

INSERT INTO public.workflow_templates (kancelarija_id, naziv, tip_predmeta, opis, koraci)
SELECT NULL, 'Žalbeni postupak', NULL,
       'Tok izjavljivanja žalbe do odluke drugostepenog suda.',
       '[
         {"naziv":"Priprema žalbe","rok_dana":10,"eskalacija_dana":3},
         {"naziv":"Podnošenje žalbe","rok_dana":2,"eskalacija_dana":1},
         {"naziv":"Čekanje na odluku drugostepenog suda","rok_dana":90,"eskalacija_dana":14},
         {"naziv":"Prijem odluke po žalbi","rok_dana":15,"eskalacija_dana":3}
       ]'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM public.workflow_templates WHERE kancelarija_id IS NULL AND naziv = 'Žalbeni postupak'
);
