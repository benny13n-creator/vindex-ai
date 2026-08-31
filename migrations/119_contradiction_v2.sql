-- ═══════════════════════════════════════════════════════════════════════════
-- Vindex AI — Migration 119: CONTRADICTION V2 — sporna tačka kao entitet
-- Run in: Supabase Dashboard → SQL Editor → New query → Run All
-- Idempotent: safe to re-run
--
-- ADITIVNA. Ne dira `predmeti.case_dna`, `predmet_dokazi`, `case_actions` ni
-- ijedan postojeći red. Stari model ostaje netaknut i nastavlja da radi;
-- V2 živi paralelno dok se potrošači ne prevedu (zasebno odobrenje).
--
-- ZAŠTO POSTOJI (forenzički utvrđeno, A005–A008):
--   * A005: dve nezavisne kontradikcije nad istim parom dokumenata dobijaju
--     ISTI `dedupe_key` (9/9 merenja) i jedna se TIHO gubi u
--     `services/case_evolution.py:1052`. Promena DB ograničenja to ne rešava —
--     gubitak nastaje PRE upisa.
--   * A006: model opisuje GDE se dokumenti sudaraju, ne OKO ČEGA.
--   * A008: identitet sporne tačke se NE SME izvoditi iz teksta —
--     kanonizacija nad sinonimima daje 5 različitih identiteta od 7 ulaza
--     koji znače isti spor, a spaja dva različita spora sa istim labelom.
--
-- ŠTA IDENTITET NAMERNO NE SADRŽI:
--   label · tekst tvrdnje · dokument · lokaciju · tip relacije · dedupe_key ·
--   bilo koji LLM izlaz. `id` je `gen_random_uuid()` — vlasnik je baza.
-- ═══════════════════════════════════════════════════════════════════════════

-- ─── 1. SPORNA TAČKA ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.predmet_issues (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id    UUID        NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
    user_id       UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    -- Prikazni naziv. NIJE identitet (A008 §13): sme da se menja, i menja se.
    label         TEXT,
    status        TEXT        NOT NULL DEFAULT 'DISCOVERED'
                  CHECK (status IN ('DISCOVERED','CONFIRMED','RESOLVED','REOPENED','MERGED')),
    -- Popunjeno samo za status='MERGED'. Spojena tema OSTAJE u tabeli kao
    -- tombstone sa pokazivačem — istorijski zapisi moraju i dalje da se
    -- razrešavaju (invarijanta I7: identitet ne sme tiho mutirati). Isti
    -- obrazac koji BLK-2 već koristi za brisanje predmeta.
    merged_into   UUID        REFERENCES public.predmet_issues(id) ON DELETE SET NULL,
    -- Zašto je zatvorena. A006 §9: bez ovog polja pet različitih domenskih
    -- događaja daju identičan zapis, pa „izostalo iz izlaza" postaje „razrešeno".
    close_reason  TEXT        CHECK (close_reason IN
                  ('RESOLVED','NOT_OBSERVED','SUPERSEDED','MERGED','WITHDRAWN')),
    closed_at     TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_issues_predmet        ON public.predmet_issues(predmet_id);
CREATE INDEX IF NOT EXISTS idx_issues_predmet_status ON public.predmet_issues(predmet_id, status);

COMMENT ON TABLE public.predmet_issues IS
  'Sporna tacka = pitanje o predmetu koje ima medjusobno iskljucive kandidat-odgovore. Nosilac KONTINUITETA. id generise baza i nikad se ne preracunava (A008 I12).';
COMMENT ON COLUMN public.predmet_issues.label IS
  'Prikazni naziv, verzionisan u predmet_issue_labels. NIJE identitet -- promena labela NE stvara novu spornu tacku.';

-- ─── 2. ISTORIJA LABELA ─────────────────────────────────────────────────────
-- Odvojena tabela, a ne kolona: prepisivanje labela bi izgubilo činjenicu da
-- se naziv spora menjao, što je samo po sebi auditni podatak.
CREATE TABLE IF NOT EXISTS public.predmet_issue_labels (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id   UUID        NOT NULL REFERENCES public.predmet_issues(id) ON DELETE CASCADE,
    label      TEXT        NOT NULL,
    izvor      TEXT        NOT NULL DEFAULT 'producer'
               CHECK (izvor IN ('producer','advokat','sistem')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_issue_labels_issue ON public.predmet_issue_labels(issue_id, created_at);

-- ─── 3. KONTRADIKCIJA ───────────────────────────────────────────────────────
-- 1 sporna tacka : N kontradikcija, diskriminisano TIPOM RELACIJE (A008 §6).
-- Ista sporna tacka („zakonitost otkaza") sme nositi i cinjenica↔cinjenica i
-- cinjenica↔norma — dva razlicita puta razresenja.
CREATE TABLE IF NOT EXISTS public.predmet_contradictions (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id      UUID        NOT NULL REFERENCES public.predmet_issues(id) ON DELETE CASCADE,
    relation_type TEXT        NOT NULL CHECK (relation_type IN ('cinjenica_cinjenica','cinjenica_norma')),
    state         TEXT        NOT NULL DEFAULT 'OPEN'
                  CHECK (state IN ('OPEN','RESOLVED','NOT_OBSERVED','SUPERSEDED','REVIEW_REQUIRED')),
    state_reason  TEXT,
    tezina        TEXT        CHECK (tezina IN ('kriticna','vazna','manja')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Najviše JEDNA otvorena kontradikcija po (sporna tacka, tip relacije).
-- Partial UNIQUE, isti obrazac kao idx_case_actions_open_dedupe (mig. 099) --
-- ali opseg je sporna tacka, NE par dokumenata: upravo ta razlika je ono sto
-- A005 lazno spajanje cini nemogucim.
CREATE UNIQUE INDEX IF NOT EXISTS idx_contradiction_open_per_issue_relation
    ON public.predmet_contradictions(issue_id, relation_type)
    WHERE state = 'OPEN';

CREATE INDEX IF NOT EXISTS idx_contradictions_issue ON public.predmet_contradictions(issue_id);

-- ─── 4. ČLANSTVO TVRDNJI ────────────────────────────────────────────────────
-- Clanovi su PROMENLJIVI. Tvrdnja koja izostane iz sledeceg posmatranja dobija
-- `removed_at` i razlog `NOT_OBSERVED` -- NIKAD se ne brise i NIKAD se ne
-- tumaci kao razresena (A005: dodavanje dokumenta uklanja nalaze 3/3).
CREATE TABLE IF NOT EXISTS public.predmet_contradiction_claims (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    contradiction_id UUID        NOT NULL REFERENCES public.predmet_contradictions(id) ON DELETE CASCADE,
    -- Referenca na POSTOJECI primitiv tvrdnje (A007). `identitet` se NE
    -- reimplementira i formula iz migracije 116 se NE dira.
    dokaz_id         UUID        NOT NULL REFERENCES public.predmet_dokazi(id) ON DELETE RESTRICT,
    -- Snimak `predmet_dokazi.identitet` u trenutku ulaska u spor. Redundantan
    -- namerno: omogucava auditno poredjenje clanstva bez JOIN-a i bez rizika da
    -- kasnija promena reda promeni istorijski zapis.
    claim_identitet  TEXT,
    observed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    removed_at       TIMESTAMPTZ,
    removed_reason   TEXT        CHECK (removed_reason IN
                     ('NOT_OBSERVED','RESOLVED','SUPERSEDED','REVIEW_REQUIRED'))
);

-- Jedna AKTIVNA clanska veza po (kontradikcija, tvrdnja). Ponovljeni identican
-- proizvodjacev izlaz zato ne pravi duplikat -- idempotencija je u bazi, ne u
-- aplikacionoj logici.
CREATE UNIQUE INDEX IF NOT EXISTS idx_contradiction_claim_active
    ON public.predmet_contradiction_claims(contradiction_id, dokaz_id)
    WHERE removed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_contradiction_claims_kontr
    ON public.predmet_contradiction_claims(contradiction_id);

-- ─── 5. RLS — isti obrazac kao ostale tabele predmeta ───────────────────────
ALTER TABLE public.predmet_issues                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predmet_issue_labels          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predmet_contradictions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predmet_contradiction_claims  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "issues_service_role" ON public.predmet_issues;
CREATE POLICY "issues_service_role" ON public.predmet_issues
    FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "issues_owner_select" ON public.predmet_issues;
CREATE POLICY "issues_owner_select" ON public.predmet_issues
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "issue_labels_service_role" ON public.predmet_issue_labels;
CREATE POLICY "issue_labels_service_role" ON public.predmet_issue_labels
    FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "contradictions_service_role" ON public.predmet_contradictions;
CREATE POLICY "contradictions_service_role" ON public.predmet_contradictions
    FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "contradiction_claims_service_role" ON public.predmet_contradiction_claims;
CREATE POLICY "contradiction_claims_service_role" ON public.predmet_contradiction_claims
    FOR ALL USING (auth.role() = 'service_role');

-- ═══════════════════════════════════════════════════════════════════════════
-- GRANICA MIGRACIJE
--
-- Postojeci `case_dna.kontradikcije[]` zapisi se NE prevode automatski u V2.
-- Razlog: stari zapisi nemaju spornu tacku i ona se iz njih NE MOZE izvesti
-- (A006 §7, A008 §10) -- svako automatsko tumacenje bilo bi izmisljanje.
-- Legacy podaci ostaju legacy dok se ne odobri zasebna migracija podataka.
--
-- ROLLBACK: tabele su nove i nepovezane sa postojecim tokovima. Uklanjanje je
--   DROP TABLE IF EXISTS public.predmet_contradiction_claims;
--   DROP TABLE IF EXISTS public.predmet_contradictions;
--   DROP TABLE IF EXISTS public.predmet_issue_labels;
--   DROP TABLE IF EXISTS public.predmet_issues;
-- bez posledica po postojece podatke.
-- ═══════════════════════════════════════════════════════════════════════════
