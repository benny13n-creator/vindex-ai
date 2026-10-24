# -*- coding: utf-8 -*-
"""MIR001 TASK-08 — CASE_CHANGE_BRIEF nad PRAVIM PostgreSQL-om (izolovan klaster, VX_TEST_PG_DSN) sa STVARNOM migracijom
136: kandidat TAČNO onakav kakav pravi planer prolazi CHECK, isti ključ ne pravi drugi red, besplatan posao se zauzima
i pri limitu 0 bez trošenja budžeta, nepoznat tip se odbija."""
import uuid

import pytest

from tests.ns007_pg import sveza_baza, zahteva_pg
from tests.test_ns007_t1_t2_contract_pg import _predmet, _psy, _zauzmi

pytestmark = zahteva_pg


@pytest.fixture
def baza():
    with sveza_baza("136") as dsn:
        yield dsn


def _kandidat(c, uid, pid, v, work_type="CASE_CHANGE_BRIEF"):
    return c.execute(
        """INSERT INTO autonomy_work_items (user_id, predmet_id, agent_type, work_type, trigger_type, trigger_ref,
               dedupe_key, reason, cost_class, budget_key, max_attempts, source_version)
           VALUES (%s, %s, 'case_evolution', %s, 'GENOME_VERSION', %s, %s, 'U predmet je primljen nov dokument', 'FREE', %s, 2, %s)
           ON CONFLICT (user_id, dedupe_key) DO NOTHING RETURNING id""",
        (uid, pid, work_type, str(pid), f"{work_type}:{pid}:g{v}", f"solo:{uid}", v)).fetchone()


def test_kandidat_planera_prolazi_ugovor_136_bez_duplikata_i_bez_budzeta(baza):
    with _psy().connect(baza, autocommit=True) as c:
        uid = uuid.uuid4()
        pid = _predmet(c, uid)
        [wid] = _kandidat(c, uid, pid, 8)
        assert _kandidat(c, uid, pid, 8) is None                         # isti ključ → nijedan nov red
        assert c.execute("SELECT count(*) FROM autonomy_work_items WHERE user_id=%s", (uid,)).fetchone()[0] == 1
        r = _zauzmi(c, wid, limit=0)
        assert r["ishod"] == "CLAIMED", r                                # FREE: zauzima se i kad je budžet 0
        assert c.execute("SELECT budget_units FROM autonomy_work_items WHERE id=%s", (wid,)).fetchone()[0] == 0
        assert _kandidat(c, uid, pid, 9) is not None                     # nova verzija = nov ključ


def test_nepoznat_tip_posla_odbija_baza(baza):
    import psycopg
    with _psy().connect(baza, autocommit=True) as c:
        uid = uuid.uuid4()
        with pytest.raises(psycopg.errors.CheckViolation):
            _kandidat(c, uid, _predmet(c, uid), 1, work_type="CASE_SUMMARY_X")
