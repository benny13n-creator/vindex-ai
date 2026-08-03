-- ============================================================================
-- Vindex AI — Migracija 090: Ledger Correlation ID (Mission Ledger)
-- ============================================================================
-- Pokrenuti u: Supabase Dashboard → SQL Editor, posle 089.
--
-- Kontekst: Mission Ledger (2026-08-03) unifikuje correlation_id kao
-- prvoklasan koncept koji povezuje HTTP zahtev → Event Bus ('events') →
-- AI Provenance ('ai_forensics', migracija 089) → Audit ('audit_immutable').
-- ai_forensics već ima correlation_id (089); ova migracija dodaje istu
-- kolonu na preostala dva sistema koja je nemaju.
--
-- Kod je već napisan da radi ISPRAVNO i bez ove migracije (svaki upis prvo
-- pokušava sa correlation_id kolonom, pa bez nje ako ne postoji — isti
-- "probaj široko, padni na usko" idiom kao 089) — dok se ova migracija ne
-- pokrene, correlation_id putuje samo kroz payload/metadata JSONB polja
-- (nazad-kompatibilno), ne kao indeksirana kolona za brze upite.
-- ============================================================================

ALTER TABLE public.events           ADD COLUMN IF NOT EXISTS correlation_id TEXT;
ALTER TABLE public.audit_immutable  ADD COLUMN IF NOT EXISTS correlation_id TEXT;

-- correlation_id NIJE deo audit_immutable's hash-chain računice
-- (_compute_entry_hash u shared/audit_immutable.py hešuje samo prev_hash/
-- user_id/action/created_at/resource_type/resource_id — isti tretman kao
-- postojeća 'metadata' kolona) -- dodavanje ove kolone ne menja, ne
-- nevalidira, i ne zahteva ponovni obračun ni jednog postojećeg zapisa.

CREATE INDEX IF NOT EXISTS idx_events_correlation_id          ON public.events (correlation_id);
CREATE INDEX IF NOT EXISTS idx_audit_immutable_correlation_id  ON public.audit_immutable (correlation_id);

COMMENT ON COLUMN public.events.correlation_id IS
    'Mission Ledger (2026-08-03) — isti id kao ai_forensics.correlation_id i audit_immutable.correlation_id '
    'za istu logičku poslovnu akciju. Upisuje se preko services/event_bus.py::emit() '
    '(auto-popunjeno iz shared/ai_provenance.py ako nije eksplicitno prosleđeno).';

COMMENT ON COLUMN public.audit_immutable.correlation_id IS
    'Mission Ledger (2026-08-03) — isti id kao events.correlation_id i ai_forensics.correlation_id '
    'za istu logičku poslovnu akciju. Upisuje se preko shared/audit_immutable.py::log_action '
    '(auto-popunjeno iz shared/ai_provenance.py ako nije eksplicitno prosleđeno). Van hash-chain '
    'računice — vidi napomenu iznad.';

-- ─── Potvrda ─────────────────────────────────────────────────────────────────

DO $$
BEGIN
    RAISE NOTICE 'Migracija 090 završena: correlation_id dodat na events i audit_immutable.';
    RAISE NOTICE 'Posle ovoga: SELECT * FROM events e JOIN audit_immutable a USING (correlation_id) '
                 'JOIN ai_forensics f USING (correlation_id) WHERE e.correlation_id = ''<id>'' '
                 'rekonstruiše kompletan lanac za bilo koju poslovnu akciju.';
END $$;
