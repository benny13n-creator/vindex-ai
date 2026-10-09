"""NS007 Task 1–2 — trajni ugovor autonomije, dokazan na PRAVOM PostgreSQL-u (migracija 136 iz repoa).

  • migracija se primenjuje i drugi put bez greške (aditivna, ponovljiva);
  • 20 istovremenih zauzimanja istog prozora ciklusa → TAČNO 1 pobednik, ostali 23505;
  • 20 istovremenih zauzimanja istog posla → TAČNO 1 CLAIMED;
  • isti okidač upisan dvaput → 1 logički posao (UNIQUE user_id + dedupe_key);
  • 10 istovremenih plaćenih poslova iste organizacije, budžet 3 → TAČNO 3 CLAIMED (rezervacija pre modela);
  • budžet je po organizaciji i po danu; neplaćen posao ne troši budžet; nepoznat limit → BUDGET_UNKNOWN;
  • pad posle zauzimanja: zakup važi → NOT_CLAIMABLE; zakup istekao → ponovo CLAIMED;
  • iscrpljeni pokušaji → DEAD_LETTER (vidljivo, bez beskonačnog ponavljanja);
  • rezultat upisuje SAMO vlasnik zakupa, u istoj naredbi sa READY_FOR_REVIEW;
  • RLS: korisnik vidi samo svoje redove, ne može da upiše/izmeni/obriše ni da pozove funkciju zauzimanja;
    anon ne vidi ništa; ciklusi nisu vidljivi korisnicima.
"""
import threading
import uuid

import pytest

from tests.ns007_pg import migracija, sveza_baza, zahteva_pg

pytestmark = zahteva_pg


def _psy():
    import psycopg
    return psycopg


@pytest.fixture
def baza():
    with sveza_baza("136") as dsn:
        yield dsn


def _istovremeno(dsn, n, posao):
    """n niti, svaka sa svojom konekcijom, kreću ZAJEDNO (barijera)."""
    psycopg = _psy()
    barijera = threading.Barrier(n)
    rezultati = [None] * n

    def nit(i):
        with psycopg.connect(dsn, autocommit=True) as c:
            barijera.wait()
            try:
                rezultati[i] = posao(c, i)
            except Exception as e:  # sudar ključa i sl. — beleži se kao ishod
                rezultati[i] = e
    niti = [threading.Thread(target=nit, args=(i,)) for i in range(n)]
    for t in niti:
        t.start()
    for t in niti:
        t.join()
    return rezultati


def _predmet(c, uid):
    return c.execute("INSERT INTO predmeti (user_id, naziv) VALUES (%s, 'P') RETURNING id", (uid,)).fetchone()[0]


def _posao(c, uid, pid, kljuc, cost="PAID", budget_key=None, max_attempts=2):
    return c.execute(
        """INSERT INTO autonomy_work_items (user_id, predmet_id, agent_type, work_type, trigger_type, trigger_ref,
               dedupe_key, reason, cost_class, budget_key, max_attempts)
           VALUES (%s, %s, 'hearing_prep', 'HEARING_PREP', 'ROCISTE', 'r1', %s, 'Ročište za 1 dan', %s, %s, %s)
           RETURNING id""",
        (uid, pid, kljuc, cost, budget_key or f"solo:{uid}", max_attempts)).fetchone()[0]


def _zauzmi(c, wid, owner=None, lease=60, limit=10):
    import json
    r = c.execute("SELECT autonomy_claim_work_item(%s, %s, %s, %s)", (wid, owner or uuid.uuid4(), lease, limit)).fetchone()[0]
    return r if isinstance(r, dict) else json.loads(r)


def test_migracija_je_ponovljiva(baza):
    psycopg = _psy()
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute(migracija("136"))
        assert c.execute("SELECT count(*) FROM pg_tables WHERE tablename LIKE 'autonomy_%'").fetchone()[0] == 2


def test_20_istovremenih_zauzimanja_prozora_tacno_jedan_pobednik(baza):
    def claim(c, i):
        return c.execute("INSERT INTO autonomy_cycles (window_key, run_id) VALUES ('2026-10-10T03', %s) RETURNING run_id",
                         (f"run{i}",)).fetchone()[0]
    rez = _istovremeno(baza, 20, claim)
    pobednici = [r for r in rez if isinstance(r, str)]
    gubitnici = [r for r in rez if isinstance(r, Exception)]
    assert len(pobednici) == 1 and len(gubitnici) == 19
    assert all(getattr(e, "sqlstate", None) == "23505" for e in gubitnici), {type(e).__name__ for e in gubitnici}
    with _psy().connect(baza) as c:
        assert c.execute("SELECT count(*), max(run_id) FROM autonomy_cycles").fetchone() == (1, pobednici[0])


def test_20_istovremenih_zauzimanja_posla_tacno_jedan(baza):
    with _psy().connect(baza, autocommit=True) as c:
        uid = uuid.uuid4()
        wid = _posao(c, uid, _predmet(c, uid), "k1")
    rez = _istovremeno(baza, 20, lambda c, i: _zauzmi(c, wid)["ishod"])
    assert rez.count("CLAIMED") == 1 and rez.count("NOT_CLAIMABLE") == 19, rez
    with _psy().connect(baza) as c:
        assert c.execute("SELECT status, attempt_count, budget_units FROM autonomy_work_items").fetchone() == ("RUNNING", 1, 1)


def test_isti_okidac_jedan_logicki_posao(baza):
    with _psy().connect(baza, autocommit=True) as c:
        uid = uuid.uuid4()
        pid = _predmet(c, uid)
        _posao(c, uid, pid, "rociste:x:v3")
        with pytest.raises(Exception) as e:
            _posao(c, uid, pid, "rociste:x:v3")
        assert e.value.sqlstate == "23505"
        # isti ključ kod DRUGOG korisnika nije isti logički posao
        uid_b = uuid.uuid4()
        _posao(c, uid_b, _predmet(c, uid_b), "rociste:x:v3")
        assert c.execute("SELECT count(*) FROM autonomy_work_items").fetchone()[0] == 2


def test_10_istovremenih_placenih_budzet_3(baza):
    with _psy().connect(baza, autocommit=True) as c:
        uid = uuid.uuid4()
        pid = _predmet(c, uid)
        ids = [_posao(c, uid, pid, f"k{i}", budget_key="kancelarija:K1") for i in range(10)]
    rez = _istovremeno(baza, 10, lambda c, i: _zauzmi(c, ids[i], limit=3)["ishod"])
    assert rez.count("CLAIMED") == 3 and rez.count("BUDGET_EXHAUSTED") == 7, rez
    with _psy().connect(baza) as c:
        assert c.execute("SELECT sum(budget_units) FROM autonomy_work_items").fetchone()[0] == 3
        assert c.execute("SELECT count(*) FROM autonomy_work_items WHERE status='QUEUED'").fetchone()[0] == 7


def test_budzet_po_organizaciji_besplatan_ne_trosi_nepoznat_limit_zatvara(baza):
    with _psy().connect(baza, autocommit=True) as c:
        a, b = uuid.uuid4(), uuid.uuid4()
        pa, pb = _predmet(c, a), _predmet(c, b)
        a1, a2 = _posao(c, a, pa, "a1", budget_key="org:A"), _posao(c, a, pa, "a2", budget_key="org:A")
        b1 = _posao(c, b, pb, "b1", budget_key="org:B")
        f1 = _posao(c, a, pa, "f1", cost="FREE", budget_key="org:A")
        nep = _posao(c, a, pa, "n1", budget_key="org:N")
        assert _zauzmi(c, a1, limit=1)["ishod"] == "CLAIMED"
        assert _zauzmi(c, a2, limit=1)["ishod"] == "BUDGET_EXHAUSTED"
        assert _zauzmi(c, b1, limit=1)["ishod"] == "CLAIMED", "druga organizacija ima svoj budžet"
        assert _zauzmi(c, f1, limit=0)["ishod"] == "CLAIMED", "besplatan (deterministički) posao ne troši budžet"
        assert c.execute("SELECT budget_units FROM autonomy_work_items WHERE id=%s", (f1,)).fetchone()[0] == 0
        r = c.execute("SELECT autonomy_claim_work_item(%s, %s, 60, NULL)", (nep, uuid.uuid4())).fetchone()[0]
        assert r["ishod"] == "BUDGET_UNKNOWN", "nepoznat limit nije „neograničeno“"
        assert c.execute("SELECT status FROM autonomy_work_items WHERE id=%s", (nep,)).fetchone()[0] == "QUEUED"


def test_zakup_pad_ponovno_zauzimanje_i_dead_letter(baza):
    with _psy().connect(baza, autocommit=True) as c:
        uid = uuid.uuid4()
        wid = _posao(c, uid, _predmet(c, uid), "k", max_attempts=2)
        assert _zauzmi(c, wid, lease=60)["ishod"] == "CLAIMED"
        assert _zauzmi(c, wid)["ishod"] == "NOT_CLAIMABLE", "važeći zakup se ne otima"
        c.execute("UPDATE autonomy_work_items SET lease_expires_at = now() - interval '1 second' WHERE id=%s", (wid,))
        r = _zauzmi(c, wid)
        assert r["ishod"] == "CLAIMED" and r["item"]["attempt_count"] == 2, "pad radnika → oporavak posle isteka zakupa"
        c.execute("UPDATE autonomy_work_items SET lease_expires_at = now() - interval '1 second' WHERE id=%s", (wid,))
        assert _zauzmi(c, wid)["ishod"] == "DEAD_LETTER"
        row = c.execute("SELECT status, safe_error_code, budget_units FROM autonomy_work_items WHERE id=%s", (wid,)).fetchone()
        assert row == ("DEAD_LETTER", "ATTEMPTS_EXHAUSTED", 2), "najviše 2 rezervacije = najviše 2 izvršenja modela"
        assert _zauzmi(c, wid)["ishod"] == "NOT_CLAIMABLE"


def test_rezultat_upisuje_samo_vlasnik_zakupa(baza):
    import json
    with _psy().connect(baza, autocommit=True) as c:
        uid = uuid.uuid4()
        wid = _posao(c, uid, _predmet(c, uid), "k")
        vlasnik = uuid.uuid4()
        _zauzmi(c, wid, owner=vlasnik)
        upis = """UPDATE autonomy_work_items SET status='READY_FOR_REVIEW', title='T', summary='S', content_json=%s,
                         quality_state='AI_PREPARED_FOR_REVIEW', ready_at=now(), lease_owner=NULL, lease_expires_at=NULL
                   WHERE id=%s AND status='RUNNING' AND lease_owner=%s"""
        assert c.execute(upis, (json.dumps({"a": 1}), wid, uuid.uuid4())).rowcount == 0, "tuđi zakup ne upisuje"
        assert c.execute(upis, (json.dumps({"a": 1}), wid, vlasnik)).rowcount == 1
        with pytest.raises(Exception):   # READY bez proizvoda krši ograničenje
            c.execute("UPDATE autonomy_work_items SET status='READY_FOR_REVIEW', content_json=NULL WHERE id=%s", (wid,))


def test_rls_i_prava(baza):
    psycopg = _psy()
    with psycopg.connect(baza, autocommit=True) as c:
        a, b = uuid.uuid4(), uuid.uuid4()
        wa = _posao(c, a, _predmet(c, a), "ka")
        _posao(c, b, _predmet(c, b), "kb")
        c.execute("INSERT INTO autonomy_cycles (window_key, run_id) VALUES ('w', 'r')")
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute("SET ROLE authenticated")
        c.execute("SELECT set_config('request.jwt.claim.sub', %s, false)", (str(a),))
        assert [r[0] for r in c.execute("SELECT id FROM autonomy_work_items").fetchall()] == [wa], "samo svoji redovi"
        for upit in ("UPDATE autonomy_work_items SET status='ACCEPTED'",
                     "DELETE FROM autonomy_work_items",
                     f"INSERT INTO autonomy_work_items (user_id, predmet_id, agent_type, work_type, trigger_type, trigger_ref, dedupe_key, reason, cost_class, budget_key) VALUES ('{a}', gen_random_uuid(), 'hearing_prep','HEARING_PREP','ROCISTE','r','x','r','FREE','b')",
                     "SELECT * FROM autonomy_cycles",
                     f"SELECT autonomy_claim_work_item('{wa}', gen_random_uuid(), 60, 10)"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(upit)
    with psycopg.connect(baza, autocommit=True) as c:
        # prva brava: pravo izvršavanja (druga je SECURITY INVOKER + nedostatak UPDATE prava nad tabelom)
        f = "public.autonomy_claim_work_item(uuid,uuid,integer,integer)"
        assert c.execute(f"SELECT has_function_privilege('authenticated', '{f}', 'EXECUTE'), has_function_privilege('anon', '{f}', 'EXECUTE'), "
                         f"has_function_privilege('service_role', '{f}', 'EXECUTE')").fetchone() == (False, False, True)
        assert c.execute("SELECT has_table_privilege('authenticated', 'autonomy_work_items', 'INSERT'), "
                         "has_table_privilege('authenticated', 'autonomy_work_items', 'UPDATE'), "
                         "has_table_privilege('authenticated', 'autonomy_cycles', 'SELECT')").fetchone() == (False, False, False)
    with psycopg.connect(baza, autocommit=True) as c:
        c.execute("SET ROLE anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT * FROM autonomy_work_items")


def test_brisanje_predmeta_brise_radne_proizvode(baza):
    """Ista politika kao agent_recommendations / P15 brisanje predmeta (v. migraciju 136)."""
    with _psy().connect(baza, autocommit=True) as c:
        uid = uuid.uuid4()
        pid = _predmet(c, uid)
        _posao(c, uid, pid, "k")
        c.execute("DELETE FROM predmeti WHERE id=%s", (pid,))
        assert c.execute("SELECT count(*) FROM autonomy_work_items").fetchone()[0] == 0
