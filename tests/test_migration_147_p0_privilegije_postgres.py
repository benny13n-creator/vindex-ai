# -*- coding: utf-8 -*-
"""
Migracija 147 (P0: SECURITY DEFINER view-ovi + interni worker RPC-ji) nad STVARNIM PostgreSQL-om.

Baza se gradi kao Supabase projekat:
  - uloge anon / authenticated / service_role (BYPASSRLS), auth.uid()/auth.role() čitaju
    `request.jwt.claims` tačno kao kod PostgREST-a (identitet korisnika A i B je stvaran JWT kontekst,
    ne samo SET ROLE);
  - Supabase podrazumevane privilegije u šemi public (GRANT ALL ... TO anon, authenticated, service_role)
    — to je dokazani uzrok;
  - migracije 073, 091, 092, 095, 123, 130 se izvršavaju DOSLOVNO; view-ovi iz 045/002/065 se izvlače
    doslovno iz fajla; osnovne tabele su minimalni stub-ovi sa RLS vlasničkim politikama.

Pokretanje: VINDEX_TEST_PG_DSN ili throwaway klaster (`python scripts/test_db.py up`).
Bez servera se preskače — to je činjenica okruženja, ne dokaz.
"""
import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg", reason="psycopg nije instaliran")

REPO = Path(__file__).resolve().parent.parent
MIG = REPO / "migrations"
M147 = MIG / "147_p0_definer_view_rpc_lockdown.sql"

VIEWOVI = ("case_profitability", "klijenti_retention_candidates", "feature_analytics",
           "intake_queue_metrics", "events_outbox_metrics", "v_manual_queue", "v_qualified_jobs")
AUTO_UPDATABLE = ("klijenti_retention_candidates", "v_manual_queue", "v_qualified_jobs")
WORKER_RPC = {
    "enqueue_intake_job": "SELECT public.enqueue_intake_job('dropzone','sha','x/y.pdf',%(uid)s,NULL,NULL)",
    "claim_intake_job": "SELECT * FROM public.claim_intake_job('received','failed')",
    "complete_intake_job": "SELECT public.complete_intake_job(%(job)s)",
    "fail_intake_job": "SELECT public.fail_intake_job(%(job)s,'lazni neuspeh',99,5,NULL)",
    "claim_pending_events": "SELECT * FROM public.claim_pending_events(25,30)",
    "claim_intake_finalize": "SELECT * FROM public.claim_intake_finalize(%(job)s,0)",
}


def _server():
    for dsn in [os.getenv("VINDEX_TEST_PG_DSN") or "", "host=127.0.0.1 port=55432 user=postgres dbname=postgres"]:
        if not dsn:
            continue
        try:
            with psycopg.connect(dsn, connect_timeout=3):
                return dsn
        except Exception:
            continue
    return None


_DSN = _server()
pytestmark = pytest.mark.skipif(_DSN is None, reason="nema PostgreSQL test servera ($VINDEX_TEST_PG_DSN / 55432)")

_SUPABASE = """
CREATE SCHEMA auth;
CREATE TABLE auth.users (id uuid PRIMARY KEY);
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
  $$ SELECT nullif(current_setting('request.jwt.claims', true)::jsonb->>'sub', '')::uuid $$;
CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS
  $$ SELECT current_setting('request.jwt.claims', true)::jsonb->>'role' $$;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA auth TO anon, authenticated, service_role;
CREATE SCHEMA storage;
CREATE TABLE storage.buckets (id text PRIMARY KEY, name text, public boolean);
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
-- Supabase obrazac (uzrok): svaki novi objekat u public dobija direktan grant za anon/authenticated.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES    TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
"""

_STUBOVI = """
CREATE TABLE public.predmeti (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL,
  naziv text, tip text, status text, created_at timestamptz DEFAULT now());
CREATE TABLE public.billing_entries (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL,
  predmet_id uuid, iznos_rsd numeric, sati numeric, obracunato boolean, created_at timestamptz DEFAULT now());
CREATE TABLE public.klijenti (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL,
  ime text, prezime text, firma text, tip text, status text, aktivan boolean,
  datum_poslednje_aktivnosti timestamptz, pravni_osnov_obrade text);
CREATE TABLE public.feature_registry (feature_key text PRIMARY KEY, naziv text, kategorija text, priority int);
CREATE TABLE public.feature_usage_log (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid,
  feature_key text, krediti_potroseni int, estimated_cost_usd numeric, latency_ms int,
  tokens_prompt int, tokens_completion int, created_at timestamptz DEFAULT now());
CREATE TABLE public.predmet_dokumenti (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid);
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['predmeti','billing_entries','klijenti','feature_usage_log','predmet_dokumenti'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY vlasnik ON public.%I FOR ALL TO authenticated '
                   'USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())', t);
  END LOOP;
END $$;
ALTER TABLE public.feature_registry ENABLE ROW LEVEL SECURITY;
-- V2 (123): minimalne tabele za proveru kontradikcije.
CREATE TABLE public.predmet_issues (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid);
CREATE TABLE public.predmet_contradictions (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), issue_id uuid, state text);
CREATE TABLE public.predmet_dokazi (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid, deleted_at timestamptz);
CREATE TABLE public.predmet_contradiction_claims (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contradiction_id uuid, dokaz_id uuid, removed_at timestamptz);
-- Strani sistem u istom projektu (Security Advisor: v_manual_queue / v_qualified_jobs).
CREATE TABLE public.jobs (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text, kvalifikovan boolean);
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
CREATE VIEW public.v_qualified_jobs AS SELECT id, title FROM public.jobs WHERE kvalifikovan;
CREATE VIEW public.v_manual_queue AS SELECT id AS application_id, title FROM public.jobs WHERE NOT kvalifikovan;
"""


def _view_iz_migracije(fajl: str, ime: str) -> str:
    tekst = (MIG / fajl).read_text(encoding="utf-8")
    m = re.search(r"CREATE OR REPLACE VIEW\s+(?:public\.)?" + ime + r"\s+AS.*?;", tekst, re.S)
    assert m, f"{ime} nije nađen u {fajl}"
    return m.group(0)


def _izgradi(veza) -> None:
    veza.execute(_SUPABASE)
    veza.execute(_STUBOVI)
    for fajl in ("073_intake_foundations.sql", "091_event_bus_atomic_claim.sql",
                 "092_finalize_atomic_claim.sql", "095_intake_bulletproofing.sql",
                 "123_v2_lifecycle_trigger_fix.sql", "130_events_outbox_dead_letter_metrics.sql"):
        veza.execute((MIG / fajl).read_text(encoding="utf-8"))                     # DOSLOVNO
    veza.execute(_view_iz_migracije("045_firm_intelligence.sql", "case_profitability"))
    veza.execute(_view_iz_migracije("002_klijenti_crm.sql", "klijenti_retention_candidates"))
    veza.execute(_view_iz_migracije("065_feature_registry_v2.sql", "feature_analytics"))


def _seed(veza) -> dict:
    a, b = uuid.uuid4(), uuid.uuid4()
    veza.execute("INSERT INTO auth.users VALUES (%s), (%s)", (a, b))
    pa = veza.execute("INSERT INTO public.predmeti (user_id, naziv, tip, status) VALUES "
                      "(%s,'Sinteticki A','parnica','aktivan') RETURNING id", (a,)).fetchone()[0]
    pb = veza.execute("INSERT INTO public.predmeti (user_id, naziv, tip, status) VALUES "
                      "(%s,'Sinteticki B','krivica','aktivan') RETURNING id", (b,)).fetchone()[0]
    veza.execute("INSERT INTO public.billing_entries (user_id, predmet_id, iznos_rsd, sati, obracunato) VALUES "
                 "(%s,%s,1000,2,true), (%s,%s,500,1,false), (%s,%s,7000,5,true)", (a, pa, a, pa, b, pb))
    veza.execute("INSERT INTO public.klijenti (user_id, ime, prezime, status, aktivan, datum_poslednje_aktivnosti) "
                 "VALUES (%s,'Ana','A','aktivan',true, now() - interval '6 years'), "
                 "(%s,'Boris','B','aktivan',true, now() - interval '6 years')", (a, b))
    veza.execute("INSERT INTO public.feature_registry VALUES ('f1','F1','k',1)")
    veza.execute("INSERT INTO public.feature_usage_log (user_id, feature_key, krediti_potroseni, estimated_cost_usd) "
                 "VALUES (%s,'f1',1,0.01), (%s,'f1',2,0.02)", (a, b))
    veza.execute("INSERT INTO public.jobs (title, kvalifikovan) VALUES ('j1', true), ('j2', false)")
    job = veza.execute("SELECT public.enqueue_intake_job('dropzone','sha-a','a/doc.pdf',%s,NULL,'idem-a')",
                       (str(a),)).fetchone()[0]
    return {"a": a, "b": b, "pa": pa, "pb": pb, "job": job}


@pytest.fixture
def db():
    ime = f"vindex_m147_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(_DSN, autocommit=True) as c:
        for uloga, extra in (("anon", ""), ("authenticated", ""), ("service_role", " BYPASSRLS")):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (uloga,)).fetchone():
                c.execute(f'CREATE ROLE "{uloga}" NOLOGIN{extra}')
        c.execute(f'CREATE DATABASE "{ime}"')
    dsn = _DSN.replace("dbname=postgres", f"dbname={ime}")
    veza = psycopg.connect(dsn, autocommit=True)
    try:
        _izgradi(veza)
        veza.info_dsn = dsn
        veza.seed = _seed(veza)
        yield veza
    finally:
        veza.close()
        with psycopg.connect(_DSN, autocommit=True) as c:
            c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (ime,))
            c.execute(f'DROP DATABASE IF EXISTS "{ime}"')


@contextmanager
def kao(veza, uloga: str, sub=None):
    """PostgREST-ov kontekst: SET LOCAL ROLE + request.jwt.claims (sub = korisnik)."""
    with veza.transaction():
        veza.execute(f"SET LOCAL ROLE {uloga}")
        claims = {"role": uloga} | ({"sub": str(sub)} if sub else {})
        veza.execute("SELECT set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
        yield veza


def _primeni_147(veza, tekst: str | None = None) -> None:
    veza.execute(tekst if tekst is not None else M147.read_text(encoding="utf-8"))


def _stanje(veza) -> tuple:
    return (veza.execute("SELECT id, status, attempts, claimed_at, finalizing_at FROM public.intake_jobs ORDER BY id").fetchall(),
            veza.execute("SELECT count(*), count(claimed_at) FROM public.events").fetchone(),
            veza.execute("SELECT count(*) FROM public.intake_audit_log").fetchone()[0])


# ── 1. Reprodukcija produkcionog nalaza PRE 147 (falsifikacija/uzrok) ────────

def test_pre_147_anon_cita_finansije_svih_korisnika_kroz_view(db):
    with kao(db, "anon") as v:
        assert v.execute("SELECT count(*) FROM public.predmeti").fetchone()[0] == 0
        assert v.execute("SELECT count(*) FROM public.billing_entries").fetchone()[0] == 0
        redovi = v.execute("SELECT DISTINCT user_id FROM public.case_profitability").fetchall()
    assert {r[0] for r in redovi} == {db.seed["a"], db.seed["b"]}       # view zaobilazi RLS


def test_pre_147_korisnik_b_vidi_finansije_korisnika_a(db):
    with kao(db, "authenticated", db.seed["b"]) as v:
        assert v.execute("SELECT count(*) FROM public.predmeti").fetchone()[0] == 1   # RLS osnovne tabele radi
        tudji = v.execute("SELECT ukupno_naplaceno_rsd FROM public.case_profitability WHERE user_id = %s",
                          (db.seed["a"],)).fetchone()
    assert tudji is not None and tudji[0] == 1500


def test_pre_147_uzrok_revoke_from_public_ne_uklanja_direktne_grantove(db):
    for fn in ("public.claim_intake_job(text,text)", "public.claim_intake_finalize(uuid,integer)",
               "public.claim_pending_events(integer,integer)"):
        acl = db.execute("SELECT proacl::text FROM pg_proc WHERE oid = %s::regprocedure", (fn,)).fetchone()[0]
        assert "anon=X" in acl and "authenticated=X" in acl, acl                 # direktan grant
        assert not re.search(r"(^|[{,])=X", acl), acl                            # PUBLIC jeste uklonjen
        assert db.execute("SELECT has_function_privilege('anon', %s, 'EXECUTE')", (fn,)).fetchone()[0]


def test_pre_147_anon_brise_klijenta_kroz_auto_updatable_retention_view(db):
    """Nalaz šireg obima od Advisor-a: view nad jednom tabelom je auto-updatable, a default ACL daje ALL."""
    with kao(db, "anon") as v:
        obrisano = v.execute("DELETE FROM public.klijenti_retention_candidates RETURNING id").fetchall()
    assert len(obrisano) == 2
    assert db.execute("SELECT count(*) FROM public.klijenti").fetchone()[0] == 0


def test_pre_147_anon_menja_tudji_posao_kroz_worker_rpc(db):
    with kao(db, "anon") as v:
        oteto = v.execute("SELECT id, uploaded_by, storage_path FROM public.claim_intake_job('received','failed')").fetchall()
    assert oteto and str(oteto[0][1]) == str(db.seed["a"]) and oteto[0][2] == "a/doc.pdf"
    assert db.execute("SELECT status FROM public.intake_jobs WHERE id = %s", (db.seed["job"],)).fetchone()[0] == "failed"


# ── 2. Posle 147: zatvoreno za anon/authenticated ────────────────────────────

@pytest.mark.parametrize("view", VIEWOVI)
@pytest.mark.parametrize("akter", ["anon", "A", "B"])
def test_147_view_odbijen_za_anon_i_korisnike(db, view, akter):
    _primeni_147(db)
    uloga, sub = ("anon", None) if akter == "anon" else ("authenticated", db.seed[akter.lower()])
    upiti = [f"SELECT * FROM public.{view}"]
    if view in AUTO_UPDATABLE:                    # samo ovi view-ovi uopšte primaju DELETE (pre 147: uspeva)
        upiti.append(f"DELETE FROM public.{view}")
    for sql in upiti:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with kao(db, uloga, sub) as v:
                v.execute(sql)
    assert db.execute("SELECT count(*) FROM public.klijenti").fetchone()[0] == 2


@pytest.mark.parametrize("fn", sorted(WORKER_RPC) + ["v2_proveri_kontradikciju"])
@pytest.mark.parametrize("akter", ["anon", "A"])
def test_147_interni_rpc_odbijen_bez_promene_stanja(db, fn, akter):
    _primeni_147(db)
    db.execute("INSERT INTO public.events (event_type, payload) VALUES ('Test', '{}')")
    pre = _stanje(db)
    sql = WORKER_RPC.get(fn, "SELECT public.v2_proveri_kontradikciju(%(job)s)")
    uloga, sub = ("anon", None) if akter == "anon" else ("authenticated", db.seed["a"])
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with kao(db, uloga, sub) as v:
            v.execute(sql, {"uid": str(db.seed["b"]), "job": db.seed["job"]})
    assert _stanje(db) == pre


def test_147_rls_osnovnih_tabela_i_dalje_izoluje_a_od_b(db):
    _primeni_147(db)
    for ja, on in (("a", "b"), ("b", "a")):
        with kao(db, "authenticated", db.seed[ja]) as v:
            vidim = {r[0] for r in v.execute("SELECT user_id FROM public.predmeti").fetchall()}
            vidim |= {r[0] for r in v.execute("SELECT user_id FROM public.billing_entries").fetchall()}
            assert vidim == {db.seed[ja]}
            assert v.execute("UPDATE public.predmeti SET naziv = 'x' WHERE user_id = %s RETURNING id",
                             (db.seed[on],)).fetchall() == []


# ── 3. Legitimni backend (service_role) radi, matematika nepromenjena ────────

def test_147_service_role_profitabilnost_identicna_i_filtrirana(db):
    upit = "SELECT * FROM public.case_profitability ORDER BY predmet_id"
    with kao(db, "service_role") as v:
        pre = v.execute(upit).fetchall()
    _primeni_147(db)
    with kao(db, "service_role") as v:
        posle = v.execute(upit).fetchall()
        samo_a = v.execute("SELECT ukupno_naplaceno_rsd, fakturisano_rsd, nefakturisano_rsd, ukupno_sati, broj_unosa "
                           "FROM public.case_profitability WHERE user_id = %s", (db.seed["a"],)).fetchall()
        for view in VIEWOVI:
            v.execute(f"SELECT * FROM public.{view}").fetchall()
    assert pre == posle
    assert samo_a == [(1500, 1000, 500, 3, 2)]


def test_147_worker_tok_enqueue_claim_finalize_complete_fail_outbox(db):
    _primeni_147(db)
    a = str(db.seed["a"])
    with kao(db, "service_role") as v:
        assert v.execute("SELECT public.enqueue_intake_job('dropzone','sha-a','a/doc.pdf',%s,NULL,'idem-a')",
                         (a,)).fetchone()[0] == db.seed["job"]                       # idempotentno
        j2 = v.execute("SELECT public.enqueue_intake_job('mobile','sha-2','a/2.pdf',%s,NULL,'idem-2')", (a,)).fetchone()[0]
        j3 = v.execute("SELECT public.enqueue_intake_job('mobile','sha-3','a/3.pdf',%s,NULL,'idem-3')", (a,)).fetchone()[0]
    with kao(db, "service_role") as v:
        prvi = v.execute("SELECT id FROM public.claim_intake_job('received','preprocessing')").fetchone()[0]
        assert v.execute("SELECT count(*) FROM public.claim_intake_finalize(%s, 120)", (prvi,)).fetchone()[0] == 1
        assert v.execute("SELECT count(*) FROM public.claim_intake_finalize(%s, 120)", (prvi,)).fetchone()[0] == 0
        v.execute("SELECT public.complete_intake_job(%s)", (prvi,))
        v.execute("SELECT public.fail_intake_job(%s,'privremeno',1,5,now())", (j2,))
        v.execute("SELECT public.fail_intake_job(%s,'trajno',5,5,NULL)", (j3,))
        dogadjaji = v.execute("SELECT event_type FROM public.claim_pending_events(100, 30)").fetchall()
        assert v.execute("SELECT count(*) FROM public.claim_pending_events(100, 30)").fetchone()[0] == 0   # bez duplog
    status = dict(db.execute("SELECT id, status FROM public.intake_jobs").fetchall())
    assert status[prvi] == "completed" and status[j2] == "received" and status[j3] == "failed"
    assert db.execute("SELECT attempts, last_error FROM public.intake_jobs WHERE id = %s", (j2,)).fetchone() == (1, "privremeno")
    tipovi = sorted(r[0] for r in dogadjaji)
    assert tipovi.count("DocumentJobEnqueued") == 3
    assert "DocumentJobCompleted" in tipovi and "DocumentJobFailed" in tipovi
    audit = [r[0] for r in db.execute("SELECT event_type FROM public.intake_audit_log").fetchall()]
    assert {"job_created", "job_completed", "job_retry_scheduled", "job_dead_lettered"} <= set(audit)


def test_147_dva_konkurentna_workera_ne_preuzimaju_isti_posao(db):
    _primeni_147(db)
    with kao(db, "service_role") as v:
        v.execute("SELECT public.enqueue_intake_job('mobile','sha-2','a/2.pdf',%s,NULL,'idem-2')", (str(db.seed["a"]),))
    k1, k2 = psycopg.connect(db.info_dsn), psycopg.connect(db.info_dsn)
    try:
        dobijeno = []
        for k in (k1, k2):                       # k1 drži zaključan red dok k2 traži posao
            k.execute("SET ROLE service_role")
            dobijeno.append(k.execute("SELECT id FROM public.claim_intake_job('received','preprocessing')").fetchone()[0])
        k1.commit(); k2.commit()
    finally:
        k1.close(); k2.close()
    assert len(set(dobijeno)) == 2


# ── 4. Trigger funkcije i V2 provera ─────────────────────────────────────────

def _kontradikcija(v, predmet, broj_tvrdnji: int):
    issue = v.execute("INSERT INTO public.predmet_issues (predmet_id) VALUES (%s) RETURNING id", (predmet,)).fetchone()[0]
    k = v.execute("INSERT INTO public.predmet_contradictions (issue_id, state) VALUES (%s,'OPEN') RETURNING id",
                  (issue,)).fetchone()[0]
    for _ in range(broj_tvrdnji):
        d = v.execute("INSERT INTO public.predmet_dokazi (predmet_id) VALUES (%s) RETURNING id", (predmet,)).fetchone()[0]
        v.execute("INSERT INTO public.predmet_contradiction_claims (contradiction_id, dokaz_id) VALUES (%s,%s)", (k, d))


def test_147_v2_trigger_i_dalje_primenjuje_pravilo_bez_direktnog_execute(db):
    _primeni_147(db)
    assert not db.execute("SELECT has_function_privilege('authenticated','public.v2_proveri_kontradikciju(uuid)','EXECUTE')").fetchone()[0]
    with kao(db, "authenticated", db.seed["a"]) as v:
        _kontradikcija(v, db.seed["pa"], 2)                                       # validno → commit
    with pytest.raises(psycopg.errors.CheckViolation):
        with kao(db, "authenticated", db.seed["a"]) as v:
            _kontradikcija(v, db.seed["pa"], 1)                                   # OPEN sa 1 tvrdnjom → odbijeno
    assert db.execute("SELECT count(*) FROM public.predmet_contradictions").fetchone()[0] == 1


@pytest.mark.parametrize("fn", ["v2_trg_kontradikcija", "v2_trg_clanstvo"])
def test_trigger_funkcija_se_ne_moze_pozvati_direktno(db, fn):
    with pytest.raises(psycopg.errors.FeatureNotSupported):
        with kao(db, "anon") as v:
            v.execute(f"SELECT public.{fn}()")


def test_trigger_radi_i_kad_pozivalac_nema_execute_na_trigger_funkciji(db):
    """Karakterizacija za S04-B: EXECUTE na trigger funkciji se ne proverava pri okidanju."""
    db.execute("REVOKE ALL ON FUNCTION public.v2_trg_kontradikcija(), public.v2_trg_clanstvo() "
               "FROM PUBLIC, anon, authenticated")
    with pytest.raises(psycopg.errors.CheckViolation):
        with kao(db, "authenticated", db.seed["a"]) as v:
            _kontradikcija(v, db.seed["pa"], 0)


# ── 5. Svojstva same migracije ───────────────────────────────────────────────

def _acl(veza) -> list:
    return veza.execute(
        "SELECT oid::regprocedure::text, proacl::text FROM pg_proc WHERE pronamespace = 'public'::regnamespace "
        "UNION ALL SELECT relname::text, relacl::text FROM pg_class WHERE relnamespace = 'public'::regnamespace "
        "ORDER BY 1").fetchall()


def test_147_idempotentna(db):
    _primeni_147(db)
    prvi = _acl(db)
    _primeni_147(db)
    assert _acl(db) == prvi


def test_147_pada_i_ne_menja_nista_ako_potpis_ne_postoji(db):
    db.execute("DROP FUNCTION public.claim_pending_events(integer, integer)")
    pre = _acl(db)
    with pytest.raises(psycopg.errors.UndefinedFunction):
        _primeni_147(db)
    db.execute("ROLLBACK")
    assert _acl(db) == pre
    assert db.execute("SELECT has_table_privilege('anon','public.case_profitability','SELECT')").fetchone()[0]


def test_147_samoprovera_hvata_overload_koji_ostaje_otvoren(db):
    db.execute("CREATE FUNCTION public.claim_intake_job(p text) RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'")
    with pytest.raises(psycopg.errors.RaiseException, match="claim_intake_job\\(text\\)"):
        _primeni_147(db)
    db.execute("ROLLBACK")
    assert db.execute("SELECT has_function_privilege('anon','public.claim_intake_job(text,text)','EXECUTE')").fetchone()[0]


@pytest.mark.parametrize("ukloni", [
    "REVOKE ALL ON TABLE public.case_profitability            FROM PUBLIC, anon, authenticated;",
    "REVOKE ALL ON FUNCTION public.claim_intake_job(TEXT, TEXT)                                 FROM PUBLIC, anon, authenticated;",
    "GRANT EXECUTE ON FUNCTION public.claim_pending_events(INTEGER, INTEGER)                     TO service_role;",
])
def test_147_samoprovera_hvata_izostavljenu_naredbu(db, ukloni):
    tekst = M147.read_text(encoding="utf-8")
    assert ukloni in tekst
    if ukloni.startswith("GRANT"):
        db.execute("REVOKE ALL ON FUNCTION public.claim_pending_events(integer,integer) FROM service_role")
    with pytest.raises(psycopg.errors.RaiseException, match="Migracija 147"):
        _primeni_147(db, tekst.replace(ukloni, ""))
    db.execute("ROLLBACK")


def test_147_samoprovera_vidi_grant_na_nivou_kolone(db):
    """Red-team RT-01: has_table_privilege ne vidi kolonske grantove — samoprovera mora i njih."""
    db.execute("REVOKE ALL ON public.case_profitability FROM anon; "
               "GRANT SELECT (user_id, ukupno_naplaceno_rsd) ON public.case_profitability TO anon")
    assert not db.execute("SELECT has_table_privilege('anon','public.case_profitability','SELECT')").fetchone()[0]
    tekst = M147.read_text(encoding="utf-8").replace(
        "REVOKE ALL ON TABLE public.case_profitability            FROM PUBLIC, anon, authenticated;", "")
    with pytest.raises(psycopg.errors.RaiseException, match="anon pristup"):
        _primeni_147(db, tekst)
    db.execute("ROLLBACK")
    _primeni_147(db)                                    # pravi REVOKE ALL uklanja i kolonske grantove
    assert not db.execute("SELECT has_any_column_privilege('anon','public.case_profitability','SELECT')").fetchone()[0]


def test_create_or_replace_posle_147_ne_vraca_javni_pristup(db):
    _primeni_147(db)
    db.execute((MIG / "095_intake_bulletproofing.sql").read_text(encoding="utf-8"))          # CREATE OR REPLACE FUNCTION
    db.execute((MIG / "130_events_outbox_dead_letter_metrics.sql").read_text(encoding="utf-8"))  # CREATE OR REPLACE VIEW
    assert not db.execute("SELECT has_function_privilege('anon','public.claim_intake_finalize(uuid,integer)','EXECUTE')").fetchone()[0]
    assert not db.execute("SELECT has_table_privilege('anon','public.events_outbox_metrics','SELECT')").fetchone()[0]


def test_nova_funkcija_sa_samo_revoke_from_public_ostaje_javna(db):
    """S05: preostali rizik je u podrazumevanim privilegijama — budući objekat mora imenovati anon/authenticated."""
    db.execute("CREATE FUNCTION public.novi_interni() RETURNS int LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'; "
               "REVOKE ALL ON FUNCTION public.novi_interni() FROM PUBLIC;")
    assert db.execute("SELECT has_function_privilege('anon','public.novi_interni()','EXECUTE')").fetchone()[0]
    db.execute("REVOKE ALL ON FUNCTION public.novi_interni() FROM anon, authenticated")
    assert not db.execute("SELECT has_function_privilege('anon','public.novi_interni()','EXECUTE')").fetchone()[0]
