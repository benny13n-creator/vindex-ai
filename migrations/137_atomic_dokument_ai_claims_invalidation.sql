-- ============================================================================
-- Migration 137 -- Brisanje dokumenta i povlačenje njegovih AI tvrdnji u
-- JEDNOJ transakciji (VCR002 Release Closure, FIX 1, 2026-10-12)
--
-- KVAR (dokazan testovima tests/test_vcr002_rc_fix1_brisanje_dokumenta.py nad
-- kodom 38ac5fcd): api.py::predmet_dokument_obrisi je relacioni red brisao
-- kroz invalidate_dokument_relational_and_emit_event (133), a AI tvrdnje tog
-- dokumenta povlačio ZASEBNIM, kasnijim UPDATE-om. FK
-- predmet_dokazi.dokument_id je ON DELETE SET NULL (016), pa:
--   * greška tog UPDATE-a -> API je ipak vraćao success: true;
--   * pad procesa između brisanja i UPDATE-a -> tvrdnje ostaju aktivne, a
--     veza sa dokumentom je već obrisana, pa ih ni ponovni pokušaj (404) ni
--     bilo koji kasniji posao više ne mogu naći. Trajno merodavne tvrdnje
--     obrisanog izvora.
--
-- ISPRAVKA: nova funkcija radi, u jednoj transakciji:
--   1. zaključava red dokumenta (FOR UPDATE: konkurentan upis tvrdnje koja
--      ga navodi -- FK traži KEY SHARE -- čeka ili pada, ne promakne);
--   2. meko briše (deleted_at) AI tvrdnje TOG dokumenta;
--   3. briše relacioni red dokumenta;
--   4. upisuje trajni SourceInvalidated događaj.
-- Sve ili ništa. Tvrdnje koje je uneo advokat (izvor_tvrdnje = 'covek') se
-- ne diraju; predikat je ISTI kao u api.py posle FIX-T03-1:
--   izvor_tvrdnje = 'ai_klasifikacija'
--   ILI (izvor_tvrdnje IS NULL AND nacin_pronalaska IN ('egzaktan','normalizovan'))
-- (NULL autor = red pre migracije 135; samo tvrdnja koju je lociranje našlo
-- u tekstu dokumenta je sigurno izvod dokumenta.)
--
-- Nova funkcija, NOVO IME (ne CREATE OR REPLACE 133-ice): stara funkcija
-- ostaje netaknuta, pa aplikacija radi i pre i posle ove migracije
-- (api.py pada nazad na stari put sa kompenzacijom samo kad nove funkcije
-- nema -- PGRST202/42883). Nema preklapanja potpisa ni PostgREST
-- dvosmislenosti (v. 133).
--
-- Zavisnosti: 016 (predmet_dokazi), 073 (events), 117 (nacin_pronalaska),
-- 135 (izvor_tvrdnje). Bez izmene podataka, bez nove kolone, bez backfill-a.
-- Ovlašćenje: kao 133 -- SECURITY DEFINER, search_path = '', vlasništvo se
-- proverava UNUTAR funkcije, EXECUTE samo service_role (u istom koraku).
-- ============================================================================

CREATE OR REPLACE FUNCTION public.invalidate_dokument_and_ai_claims_and_emit_event(
    p_dokument_id    UUID,
    p_predmet_id     UUID,
    p_user_id        UUID,
    p_event_id       UUID,
    p_correlation_id TEXT DEFAULT NULL
) RETURNS TABLE(invalidated BOOLEAN, tvrdnje_povucene INTEGER)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_dokument UUID;
    v_povuceno INTEGER := 0;
BEGIN
    SELECT pdoc.id INTO v_dokument
        FROM public.predmet_dokumenti AS pdoc
        WHERE pdoc.id = p_dokument_id
          AND pdoc.predmet_id = p_predmet_id
          AND pdoc.user_id = p_user_id
        FOR UPDATE;

    IF v_dokument IS NULL THEN
        RETURN QUERY SELECT FALSE, 0;
        RETURN;
    END IF;

    UPDATE public.predmet_dokazi AS pd
        SET deleted_at = now()
        WHERE pd.dokument_id = p_dokument_id
          AND pd.predmet_id = p_predmet_id
          AND pd.user_id = p_user_id
          AND pd.deleted_at IS NULL
          AND (pd.izvor_tvrdnje = 'ai_klasifikacija'
               OR (pd.izvor_tvrdnje IS NULL
                   AND pd.nacin_pronalaska IN ('egzaktan', 'normalizovan')));
    GET DIAGNOSTICS v_povuceno = ROW_COUNT;

    DELETE FROM public.predmet_dokumenti AS pdoc
        WHERE pdoc.id = p_dokument_id
          AND pdoc.predmet_id = p_predmet_id
          AND pdoc.user_id = p_user_id;

    INSERT INTO public.events (id, event_type, user_id, predmet_id, payload, correlation_id)
    VALUES (
        p_event_id, 'SourceInvalidated', p_user_id, p_predmet_id,
        jsonb_build_object('source_type', 'dokument', 'source_id', p_dokument_id,
                           'tvrdnje_povucene', v_povuceno, 'correlation_id', p_correlation_id),
        p_correlation_id
    )
    ON CONFLICT (id) DO NOTHING;

    RETURN QUERY SELECT TRUE, v_povuceno;
END;
$$;

COMMENT ON FUNCTION public.invalidate_dokument_and_ai_claims_and_emit_event(UUID, UUID, UUID, UUID, TEXT) IS
    'VCR002 FIX 1 (migracija 137) -- u jednoj transakciji: zaključava dokument, meko briše njegove AI tvrdnje (advokatove ne), briše relacioni red i upisuje SourceInvalidated. Zamenjuje dvokoračni put (133 + zaseban UPDATE) u kome je pad između koraka ostavljao AI tvrdnje obrisanog dokumenta trajno aktivne i bez veze sa izvorom.';

REVOKE EXECUTE ON FUNCTION public.invalidate_dokument_and_ai_claims_and_emit_event(UUID, UUID, UUID, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.invalidate_dokument_and_ai_claims_and_emit_event(UUID, UUID, UUID, UUID, TEXT)
    TO service_role;
