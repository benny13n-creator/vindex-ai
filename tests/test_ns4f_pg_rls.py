# -*- coding: utf-8 -*-
"""NS4 O1 — direktan Data API pristup poverljivoj memoriji kancelarije, nad STVARNIM PostgreSQL-om.

Dve baze sa istim podacima: BEZ i SA migracijom 138. Uloge kao PostgREST (`SET ROLE` + `request.jwt.claim.sub`).
Svet: kancelarija K (admin X; ACTIVE A i B; SUSPENDED C; REMOVED D; INVITED E), kancelarija K2 (admin Y). A ima
belešku uz svoj predmet i klijenta, profil klijenta, vezu grafa sa ishodom i tok rada predmeta.

Dokazuje se:
  • PRE 138: admin X (bez ikakve autorizacije za A-ov predmet) čita A-ove poverljive redove direktno — rupa
    (grana `admin_uid` u RLS); grana članstva `'aktivan'` je mrtva (B ne vidi ništa) — zato ZAMENA u 'ACTIVE'
    NIJE ispravka (proverava se: otvorila bi sve redove svakom članu).
  • POSLE 138: nijedna korisnička uloga (anon, authenticated: vlasnik, član, admin, suspendovan, uklonjen,
    pozvan, druga kancelarija) nema direktan pristup — 42501; `service_role` (backend) i dalje čita sve
    (autorizaciju predmeta/klijenta tada sprovodi backend: tests/test_rh001_legacy_memory_acl.py, NS4 O2).
  • `zadaci` i `workflow_templates` (namerno izvan 138) i dalje rade kroz RLS za sopstvene redove.
Lokalni dokaz (VINDEX_PG_TEST_DSN) — bez promenljive se preskače.
"""
import uuid

import pytest

import tests.ns4f_pg as P

U = {ko: str(uuid.UUID(int=i)) for i, ko in enumerate("AXBCDEYS", start=1)}
K, K2 = str(uuid.uuid4()), str(uuid.uuid4())
PRED_A = str(uuid.uuid4())
TABELE_138 = ["memory_entries", "memory_graph_edges", "client_memory", "partner_profiles", "judge_patterns",
              "firm_style_profile", "workflow_instances", "workflow_steps"]


def _psy():
    import psycopg
    return psycopg


def _napuni(dsn):
    with _psy().connect(dsn, autocommit=True) as c:
        c.execute("INSERT INTO public.kancelarije (id, admin_uid) VALUES (%s,%s),(%s,%s)", (K, U["X"], K2, U["Y"]))
        for ko, st in (("A", "ACTIVE"), ("B", "ACTIVE"), ("C", "SUSPENDED"), ("D", "REMOVED"), ("E", "INVITED")):
            c.execute("INSERT INTO public.kancelarija_clanovi (kancelarija_id, user_id, status) VALUES (%s,%s,%s)",
                      (K, U[ko], st))
        c.execute("INSERT INTO public.memory_entries (kancelarija_id, user_id, entity_type, entity_id, tip, sadrzaj) "
                  "VALUES (%s,%s,'predmet',%s,'napomena','TAJNO predmet A'), (%s,%s,'klijent','kl-a','napomena',"
                  "'TAJNO klijent A')", (K, U["A"], PRED_A, K, U["A"]))
        c.execute("INSERT INTO public.client_memory (kancelarija_id, klijent_ime, napomene) VALUES (%s,'klijent:x',"
                  "'TAJNO profil')", (K,))
        c.execute("INSERT INTO public.memory_graph_edges (kancelarija_id, from_type, from_id, to_type, to_id, relacija,"
                  " predmet_id, ishod) VALUES (%s,'argument','a','predmet',%s,'pobedio_pred',%s,'pobeda')",
                  (K, PRED_A, PRED_A))
        c.execute("INSERT INTO public.partner_profiles (kancelarija_id, partner_uid) VALUES (%s,%s)", (K, U["A"]))
        c.execute("INSERT INTO public.judge_patterns (kancelarija_id, sudija_ime) VALUES (%s,'Petrović')", (K,))
        c.execute("INSERT INTO public.firm_style_profile (kancelarija_id) VALUES (%s)", (K,))
        wi = c.execute("INSERT INTO public.workflow_instances (kancelarija_id, predmet_id, naziv, kreirao_uid) VALUES "
                       "(%s,%s,'Tok predmeta A',%s) RETURNING id", (K, PRED_A, U["A"])).fetchone()[0]
        c.execute("INSERT INTO public.workflow_steps (workflow_id, kancelarija_id, naziv, step_idx) VALUES "
                  "(%s,%s,'Korak',1)", (wi, K))
        c.execute("INSERT INTO public.zadaci (kancelarija_id, kreirao_uid, naziv) VALUES (%s,%s,'Moj zadatak')",
                  (K, U["A"]))


@pytest.fixture(scope="module")
def baze():
    P.potreban_pg()
    pre, posle = P.nova_baza(sa_ns4=False), P.nova_baza(sa_ns4=True)
    for d in (pre, posle):
        _napuni(d)
    yield pre, posle
    for d in (pre, posle):
        P.obrisi_bazu(d)


def _citaj(dsn, uloga, ko, tabela):
    """Broj vidljivih redova ili 'ODBIJENO' (42501)."""
    with _psy().connect(dsn) as c:
        try:
            with c.transaction():
                if uloga == "service_role":
                    c.execute("SET LOCAL ROLE service_role")
                else:
                    P.kao(c, uloga, U.get(ko))
                return c.execute(f"SELECT count(*) FROM public.{tabela}").fetchone()[0]
        except Exception as e:
            if getattr(e, "sqlstate", "") == "42501":
                return "ODBIJENO"
            raise


def test_pre_138_admin_kancelarije_cita_tudje_poverljive_redove(baze):
    pre, _ = baze
    assert _citaj(pre, "authenticated", "X", "memory_entries") == 2, "rupa iz grane admin_uid nije reprodukovana"
    assert _citaj(pre, "authenticated", "X", "client_memory") == 1
    assert _citaj(pre, "authenticated", "X", "workflow_instances") == 1
    assert _citaj(pre, "authenticated", "B", "memory_entries") == 0, "grana 'aktivan' nije mrtva kako je tvrđeno"


def test_zamena_aktivan_u_active_bi_prosirila_pristup(baze):
    """Kontraprimer naivnoj ispravci O1: oživljena grana članstva daje SVAKOM članu sve beleške kancelarije.
    Izmena politike se izvodi u transakciji koja se UVEK poništava (`force_rollback`)."""
    pre, _ = baze
    with _psy().connect(pre) as c:
        with c.transaction(force_rollback=True):
            c.execute("""ALTER POLICY "memory_firma_read" ON public.memory_entries USING (
                kancelarija_id IN (SELECT kancelarija_id FROM kancelarija_clanovi
                                   WHERE user_id = auth.uid()::text AND status = 'ACTIVE'))""")
            P.kao(c, "authenticated", U["B"])
            assert c.execute("SELECT count(*) FROM public.memory_entries").fetchone()[0] == 2,                 "naivna ispravka: B (bez delegacije) vidi belešku uz A-ov predmet"
    assert _citaj(pre, "authenticated", "B", "memory_entries") == 0, "politika nije vraćena"


@pytest.mark.parametrize("tabela", TABELE_138)
@pytest.mark.parametrize("uloga,ko", [("anon", None), ("authenticated", "A"), ("authenticated", "B"),
                                      ("authenticated", "X"), ("authenticated", "C"), ("authenticated", "D"),
                                      ("authenticated", "E"), ("authenticated", "Y"), ("authenticated", "S")])
def test_posle_138_nema_direktnog_pristupa(baze, tabela, uloga, ko):
    _, posle = baze
    assert _citaj(posle, uloga, ko, tabela) == "ODBIJENO"


@pytest.mark.parametrize("tabela", TABELE_138)
def test_posle_138_upis_takodje_odbijen(baze, tabela):
    _, posle = baze
    with _psy().connect(posle) as c:
        with pytest.raises(Exception) as e:
            with c.transaction():
                P.kao(c, "authenticated", U["X"])
                c.execute(f"DELETE FROM public.{tabela}")
        assert getattr(e.value, "sqlstate", "") == "42501"


@pytest.mark.parametrize("tabela", TABELE_138)
def test_backend_service_role_i_dalje_cita(baze, tabela):
    _, posle = baze
    assert _citaj(posle, "service_role", None, tabela) >= 1


def test_tabele_izvan_138_rade_kao_ranije(baze):
    pre, posle = baze
    for d in (pre, posle):
        assert _citaj(d, "authenticated", "A", "zadaci") == 1          # sopstveni zadatak (kreirao_uid)
        assert _citaj(d, "authenticated", "B", "zadaci") == 0
        assert _citaj(d, "anon", None, "workflow_templates") >= 1        # sistemski šabloni (059)
