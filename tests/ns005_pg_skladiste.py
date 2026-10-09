# -*- coding: utf-8 -*-
"""NS005 Gate A2 — skladišta za testove trajne idempotencije (nije pytest test).

PgSkladiste    — STVARAN PostgreSQL (psycopg) nad tabelom iz migracije 134, iste semantike
                 kao produkcioni `shared.idempotency.SupabaseSkladiste`: zauzimanje = INSERT
                 (PRIMARY KEY odlučuje; sudar = UniqueViolation), završetak = UPDATE samo za
                 IN_PROGRESS + owner_token.
                 Test identiteti (`uid-A`…) nisu UUID-ovi; mapiraju se na stabilan UUID5 jer
                 je `user_id` u tabeli UUID (u produkciji je `sub` već UUID).
MemorijaSkladiste — NEGATIVNA KONTROLA: ono što bi bilo rešenje „u memoriji procesa“.
                 Mora da PADNE test granice procesa (svaki proces ima svoju memoriju).
"""
import threading
import uuid

import psycopg
from psycopg import errors

_NS = uuid.UUID("6f1c2c64-6a0e-4a8b-9a0a-5a9d0e3b1c01")


def _uid(u):
    try:
        return str(uuid.UUID(str(u)))
    except ValueError:
        return str(uuid.uuid5(_NS, str(u)))


class PgSkladiste:
    def __init__(self, dsn):
        self.dsn = dsn

    def _c(self):
        return psycopg.connect(self.dsn, autocommit=True)

    def zauzmi(self, red):
        r = dict(red, user_id=_uid(red["user_id"]))
        with self._c() as c:
            try:
                c.execute(
                    "INSERT INTO public.v2_mutation_idempotency "
                    "(user_id, idempotency_key, method, path, request_fingerprint, state, owner_token) "
                    "VALUES (%(user_id)s, %(idempotency_key)s, %(method)s, %(path)s, %(request_fingerprint)s, %(state)s, %(owner_token)s)", r)
            except errors.UniqueViolation:
                return False
        return True

    def procitaj(self, user_id, kljuc):
        with self._c() as c:
            row = c.execute(
                "SELECT state, request_fingerprint, status_code, response_content_type, response_payload_enc "
                "FROM public.v2_mutation_idempotency WHERE user_id = %s AND idempotency_key = %s",
                (_uid(user_id), kljuc)).fetchone()
        if not row:
            return None
        return dict(zip(("state", "request_fingerprint", "status_code", "response_content_type", "response_payload_enc"), row))

    def zavrsi(self, user_id, kljuc, owner_token, polja):
        with self._c() as c:
            r = c.execute(
                "UPDATE public.v2_mutation_idempotency SET state = %(state)s, status_code = %(status_code)s, "
                "response_content_type = %(response_content_type)s, response_payload_enc = %(response_payload_enc)s, "
                "completed_at = %(completed_at)s "
                "WHERE user_id = %(u)s AND idempotency_key = %(k)s AND state = 'IN_PROGRESS' AND owner_token = %(o)s",
                dict(polja, u=_uid(user_id), k=kljuc, o=owner_token))
            return r.rowcount == 1


class MemorijaSkladiste:
    _redovi = {}
    _brava = threading.Lock()

    def zauzmi(self, red):
        with self._brava:
            k = (red["user_id"], red["idempotency_key"])
            if k in self._redovi:
                return False
            self._redovi[k] = dict(red)
            return True

    def procitaj(self, user_id, kljuc):
        return self._redovi.get((user_id, kljuc))

    def zavrsi(self, user_id, kljuc, owner_token, polja):
        with self._brava:
            r = self._redovi.get((user_id, kljuc))
            if not r or r["state"] != "IN_PROGRESS" or r["owner_token"] != owner_token:
                return False
            r.update(polja)
            return True


def primeni_migraciju_134(dsn_admin, repo_root):
    """Pravi izolovanu bazu, uloge koje migracija referiše (NOLOGIN) i izvršava 134 DOSLOVNO."""
    import pathlib
    ime = f"vindex_idem_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(dsn_admin, autocommit=True) as c:
        for uloga in ("anon", "authenticated", "service_role"):
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (uloga,)).fetchone():
                c.execute(f'CREATE ROLE "{uloga}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{ime}"')
    dsn = dsn_admin.replace("dbname=postgres", f"dbname={ime}")
    with psycopg.connect(dsn, autocommit=True) as c:
        # Verno Supabase-u: podrazumevane privilegije daju ALL nad svakom NOVOM tabelom u
        # `public` ulogama anon/authenticated/service_role. Bez ovoga bi test grantova prošao
        # i kad migracija NE bi oduzela pristup (vanilla Postgres ne daje ništa sam).
        c.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role")
    sql = (pathlib.Path(repo_root) / "migrations" / "134_v2_mutation_idempotency.sql").read_text(encoding="utf-8")
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(sql)
    return ime, dsn


def obrisi_bazu(dsn_admin, ime):
    with psycopg.connect(dsn_admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{ime}" WITH (FORCE)')
