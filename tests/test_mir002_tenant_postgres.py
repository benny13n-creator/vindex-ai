"""Real HTTP context builder, isolated PostgreSQL child rows, synthetic auth/model."""
from types import SimpleNamespace

import pytest

from tests.ns007_pg import sveza_baza, zahteva_pg
from tests.test_mir002_litigation_procesno_stanje import _pitaj, lit  # noqa: F401
from tests.test_osb002_solo_tok import solo  # noqa: F401


@zahteva_pg
def test_service_role_prompt_reads_require_child_ownership(lit, monkeypatch):
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    from tests.ns006_fake import Upit6

    client, _, pid, _, captured = lit
    tables = ("predmet_dokumenti", "rocista", "billing_entries")
    with sveza_baza() as dsn:
        with psycopg.connect(dsn) as db:
            # Other fixtures can create this cluster-wide role without BYPASSRLS.
            db.execute("ALTER ROLE service_role BYPASSRLS")
            db.execute("""
                CREATE TABLE predmet_dokumenti (
                    id text, user_id text, predmet_id text, naziv_fajla text,
                    redni_broj int, velicina_kb int, tekst_sadrzaj text
                );
                CREATE TABLE rocista (
                    user_id text, predmet_id text, sud text, datum text, status text, napomena text
                );
                CREATE TABLE billing_entries (
                    user_id text, predmet_id text, opis text, kolicina int, jedinica text,
                    cena_po_jedinici int, ukupno int, datum text, fakturisano bool
                );
                ALTER TABLE predmet_dokumenti ENABLE ROW LEVEL SECURITY;
                ALTER TABLE rocista ENABLE ROW LEVEL SECURITY;
                ALTER TABLE billing_entries ENABLE ROW LEVEL SECURITY;
                GRANT SELECT ON predmet_dokumenti, rocista, billing_entries TO service_role;
            """)
            db.execute("""
                INSERT INTO predmet_dokumenti VALUES
                    ('a','uid-A',%s,'Zapisnik sa rocista.pdf',1,1,'Sud prihvata predlog.'),
                    ('b','uid-B',%s,'TAJNI-NAZIV-B.pdf',2,1,'Sud nalaze TAJNI-TEKST-B.');
            """, (pid, pid))
            db.execute("""
                INSERT INTO rocista VALUES
                    ('uid-A',%s,'SOPSTVENI-SUD-A','2026-11-10','aktivno','SOPSTVENA-NAPOMENA-A'),
                    ('uid-B',%s,'TAJNI-SUD-B','2026-11-11','aktivno','TAJNA-NAPOMENA-B')
            """, (pid, pid))
            db.execute("""
                INSERT INTO billing_entries VALUES
                    ('uid-A',%s,'SOPSTVENA-STAVKA-A',1,'h',17,17,'2026-11-10',false),
                    ('uid-B',%s,'TAJNA-STAVKA-B',1,'h',977,977,'2026-11-11',false)
            """, (pid, pid))

        original = Upit6.execute

        def execute(query):
            if query.t not in tables or query.radnja[0] != "select":
                return original(query)
            cols = sql.SQL(",").join(sql.Identifier(col.strip()) for col in query.kol.split(","))
            stmt = sql.SQL("SELECT {} FROM {} WHERE TRUE").format(cols, sql.Identifier(query.t))
            values = []
            for op, field, value in query.filt:
                condition = {"eq": " AND {} = %s", "in": " AND {} = ANY(%s)"}[op]
                stmt += sql.SQL(condition).format(sql.Identifier(field))
                values.append(value)
            if query.redosled:
                column, desc = query.redosled
                stmt += sql.SQL(" ORDER BY {} " + ("DESC" if desc else "ASC")).format(sql.Identifier(column))
            if query.opseg:
                first, last = query.opseg
                stmt += sql.SQL(" LIMIT %s OFFSET %s")
                values.extend((last - first + 1, first))
            with psycopg.connect(dsn, row_factory=dict_row, options="-c role=service_role") as db:
                assert db.execute("SELECT current_user").fetchone()["current_user"] == "service_role"
                rows = db.execute(stmt, values).fetchall()
                return SimpleNamespace(data=rows, count=len(rows))

        monkeypatch.setattr(Upit6, "execute", execute)
        for agent in ("litigation", "deadline", "billing"):
            result = _pitaj(client, pid, agent=agent)
            packet = str(captured[-1]) + str(result["izvori_predmeta"])
            assert "SOPSTVENI-SUD-A" in packet
            assert all(marker not in packet for marker in (
                "TAJNI-NAZIV-B", "TAJNI-TEKST-B", "TAJNI-SUD-B", "TAJNA-NAPOMENA-B", "TAJNA-STAVKA-B", "977 RSD",
            ))
            if agent == "deadline":
                assert "STVARNI ROKOVI IZ PREDMETA" in packet
            if agent == "billing":
                assert "SOPSTVENA-STAVKA-A" in packet
