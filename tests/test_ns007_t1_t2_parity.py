"""NS007 — paritet: lažna baza (tests/ns007_fake.py) i PRAVI PostgreSQL (migracija 136) daju ISTE ishode.

Isti scenario (sekvencijalno — konkurencija se dokazuje samo na Postgres-u) izvršava se kroz `services.autonomy`
nad lažnom bazom i kroz SQL nad pravom bazom; upoređuju se ishodi zauzimanja i završno stanje svakog posla.
Bez ovog testa bi testovi aplikacije nad lažnom bazom mogli da prolaze nad pravilima koja SQL ne sprovodi.
"""
import asyncio
import json
import uuid

import pytest

from tests.ns007_pg import sveza_baza, zahteva_pg

pytestmark = zahteva_pg

UID = "aaaaaaaa-0000-4000-8000-00000000000a"
PID = "bbbbbbbb-0000-4000-8000-00000000000b"
VLASNIK = "cccccccc-0000-4000-8000-00000000000c"
POSLOVI = [("p1", "PAID", "org:A", 2), ("p2", "PAID", "org:A", 2), ("p3", "PAID", "org:A", 1),
           ("f1", "FREE", "org:A", 2), ("b1", "PAID", "org:B", 2)]
# (posao, limit, istekni_zakup_pre)
KORACI = [("p1", 2, False), ("p1", 2, False), ("p2", 2, False), ("p3", 2, False), ("f1", 0, False),
          ("b1", 1, False), ("p1", 5, True), ("p1", 5, True), ("p3", 5, True), ("x", 5, False), ("b1", None, True)]


def _kandidat(kljuc, cost, bk, maks):
    return {"user_id": UID, "predmet_id": PID, "agent_type": "hearing_prep", "work_type": "HEARING_PREP",
            "trigger_type": "ROCISTE", "trigger_ref": "r", "dedupe_key": kljuc, "reason": "razlog",
            "cost_class": cost, "budget_key": bk, "max_attempts": maks}


def _lazna():
    import tests.ns007_fake as f7
    from services import autonomy as au
    baza = f7.Baza7({"predmeti": [{"id": PID, "user_id": UID}]})
    ids, ishodi = {}, []
    for k, c, bk, m in POSLOVI:
        ids[k] = asyncio.run(au.upisi_kandidata(baza, _kandidat(k, c, bk, m)))["id"]
    assert asyncio.run(au.upisi_kandidata(baza, _kandidat("p1", "PAID", "org:A", 2)))["ishod"] == "DUPLICATE"
    for k, limit, istekni in KORACI:
        wid = ids.get(k, str(uuid.uuid4()))
        if istekni:
            for r in baza.tabele["autonomy_work_items"]:
                if r["id"] == wid and r.get("lease_expires_at"):
                    r["lease_expires_at"] = "2000-01-01T00:00:00+00:00"
        ishodi.append(asyncio.run(au.zauzmi_posao(baza, wid, VLASNIK, limit=limit))["ishod"])
    stanje = {k: next((r["status"], r["attempt_count"], r["budget_units"]) for r in baza.tabele["autonomy_work_items"]
                      if r["id"] == ids[k]) for k in ids}
    return ishodi, stanje


def _prava():
    import psycopg
    with sveza_baza("136") as dsn, psycopg.connect(dsn, autocommit=True) as c:
        c.execute("INSERT INTO predmeti (id, user_id) VALUES (%s, %s)", (PID, UID))
        ids, ishodi = {}, []
        for k, cost, bk, m in POSLOVI:
            ids[k] = str(c.execute(
                """INSERT INTO autonomy_work_items (user_id, predmet_id, agent_type, work_type, trigger_type, trigger_ref,
                       dedupe_key, reason, cost_class, budget_key, max_attempts)
                   VALUES (%s,%s,'hearing_prep','HEARING_PREP','ROCISTE','r',%s,'razlog',%s,%s,%s) RETURNING id""",
                (UID, PID, k, cost, bk, m)).fetchone()[0])
        for k, limit, istekni in KORACI:
            wid = ids.get(k, str(uuid.uuid4()))
            if istekni:
                c.execute("UPDATE autonomy_work_items SET lease_expires_at = '2000-01-01' WHERE id=%s AND lease_expires_at IS NOT NULL", (wid,))
            r = c.execute("SELECT autonomy_claim_work_item(%s, %s, 300, %s)", (wid, VLASNIK, limit)).fetchone()[0]
            ishodi.append((r if isinstance(r, dict) else json.loads(r))["ishod"])
        stanje = {k: tuple(c.execute("SELECT status, attempt_count, budget_units FROM autonomy_work_items WHERE id=%s",
                                     (ids[k],)).fetchone()) for k in ids}
    return ishodi, stanje


def test_lazna_baza_i_postgres_daju_iste_ishode(monkeypatch):
    monkeypatch.setenv("AUTONOMY_LEASE_SECONDS", "300")
    lazni, prava = _lazna(), _prava()
    assert lazni[0] == prava[0], f"ishodi zauzimanja se razlikuju:\n lažna={lazni[0]}\n prava={prava[0]}"
    assert lazni[1] == prava[1], f"završno stanje se razlikuje:\n lažna={lazni[1]}\n prava={prava[1]}"
    # scenario zaista pokriva sve grane
    assert {"CLAIMED", "NOT_CLAIMABLE", "BUDGET_EXHAUSTED", "DEAD_LETTER", "NOT_FOUND", "BUDGET_UNKNOWN"} <= set(prava[0]), prava[0]
