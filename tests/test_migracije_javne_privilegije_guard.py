# -*- coding: utf-8 -*-
"""
Čuvar klase P0 (migracija 147): Supabase podrazumevane privilegije daju svakom NOVOM view-u i svakoj
NOVOJ funkciji u šemi public direktan grant za `anon` i `authenticated`. `REVOKE ... FROM PUBLIC` to ne
uklanja (dokazano u tests/test_migration_147_p0_privilegije_postgres.py).

Pravilo za svaku migraciju od 147 nadalje:
  - SECURITY DEFINER funkcija (CREATE ili ALTER), view i materijalizovani view moraju imati
    `REVOKE ALL ... FROM` koji imenuje i `anon` i `authenticated` (view sme umesto toga imati
    security_invoker = true; materijalizovani view ne može);
  - nijedan GRANT ne sme ciljati `anon`, `authenticated` ili `PUBLIC` osim izričito pregledanih
    izuzetaka u DOZVOLJENI_GRANTOVI.

Ograničenja (namerna, dokumentovana): ovo je leksička kočnica, ne parser. Ne razlikuje overload-e istog
imena i ne vidi objekte napravljene van migracija. Stvarno stanje privilegija dokazuje samoprovera u
samoj migraciji (katalog, svaki overload) i PostgreSQL testovi.
"""
import re
from pathlib import Path

import pytest

MIG = Path(__file__).resolve().parent.parent / "migrations"
PRVA = 147
DOZVOLJENI_GRANTOVI: set[tuple[str, str]] = set()      # (fajl, normalizovana naredba) — samo posle pregleda
_IME = r'(?:"?public"?\s*\.\s*)?"?(\w+)"?'
_JAVNE = re.compile(r"\b(anon|authenticated|public)\b", re.I)


def _ocisti(sql: str) -> str:
    """Uklanja komentare, a sadržaj stringova i $$-tela zamenjuje praznim — svestan literala."""
    izlaz, i, n = [], 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith("--", i):
            i = sql.find("\n", i)
            i = n if i < 0 else i
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'" and j + 1 < n and sql[j + 1] == "'":
                    j += 2
                elif sql[j] == "'":
                    break
                else:
                    j += 1
            izlaz.append("''")
            i = j + 1
        elif c == "$" and (m := re.match(r"\$([A-Za-z_]\w*)?\$", sql[i:])):
            oznaka = m.group(0)
            j = sql.find(oznaka, i + len(oznaka))
            izlaz.append("$$telo$$")
            i = n if j < 0 else j + len(oznaka)
        else:
            izlaz.append(c)
            i += 1
    return "".join(izlaz)


def _naredbe(sql: str) -> list[str]:
    return [" ".join(n.split()) for n in _ocisti(sql).split(";") if n.strip()]


def _zatvoreno(naredbe: list[str], ime: str) -> bool:
    pokrivene = set()
    for n in naredbe:
        m = re.match(rf"REVOKE\s+ALL(?:\s+PRIVILEGES)?\s+ON\s+(?:FUNCTION\s+|TABLE\s+|MATERIALIZED\s+VIEW\s+)?{_IME}\b(.*)",
                     n, re.I)
        if m and m.group(1).lower() == ime.lower():
            ciljevi = re.split(r"\bFROM\b", m.group(2), flags=re.I)[-1]
            pokrivene |= {u.lower() for u in re.findall(r"\b(anon|authenticated)\b", ciljevi, re.I)}
    return pokrivene == {"anon", "authenticated"}


def prekrsaji(sql: str, fajl: str = "") -> list[str]:
    naredbe = _naredbe(sql)
    greske = []
    for n in naredbe:
        f = (re.match(rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+{_IME}", n, re.I)
             or re.match(rf"ALTER\s+FUNCTION\s+{_IME}", n, re.I))
        if f and re.search(r"\bSECURITY\s+DEFINER\b", n, re.I) and not re.search(r"\bRETURNS\s+TRIGGER\b", n, re.I):
            if not _zatvoreno(naredbe, f.group(1)):
                greske.append(f"funkcija {f.group(1)}")
        v = re.match(rf"CREATE\s+(?:OR\s+REPLACE\s+)?(MATERIALIZED\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?{_IME}", n, re.I)
        if v:
            invoker = not v.group(1) and re.search(r"security_invoker\s*=\s*'?(true|on)\b", n, re.I)
            if not invoker and not _zatvoreno(naredbe, v.group(2)):
                greske.append(f"view {v.group(2)}")
        g = re.match(r"GRANT\b(.*)\bTO\b(.*)", n, re.I)
        if g and _JAVNE.search(g.group(2)) and (fajl, n) not in DOZVOLJENI_GRANTOVI:
            greske.append(f"grant javnoj ulozi: {n[:80]}")
    return greske


def _nove_migracije():
    for p in sorted(MIG.glob("*.sql")):
        m = re.match(r"(\d+)_", p.name)
        if m and int(m.group(1)) >= PRVA:
            yield p


@pytest.mark.parametrize("putanja", list(_nove_migracije()), ids=lambda p: p.name)
def test_nova_migracija_ne_ostavlja_javne_privilegije(putanja):
    assert prekrsaji(putanja.read_text(encoding="utf-8"), putanja.name) == []


ZATVORI = "\nREVOKE ALL ON {k} public.x FROM PUBLIC, anon, authenticated;"


@pytest.mark.parametrize("sql", [
    # samo PUBLIC — dokazani uzrok
    "CREATE OR REPLACE FUNCTION public.x(a int) RETURNS int LANGUAGE sql SECURITY DEFINER AS $$ SELECT 1; $$;\n"
    "REVOKE ALL ON FUNCTION public.x(int) FROM PUBLIC;",
    "CREATE VIEW leak AS SELECT 1;",                                            # nekvalifikovano ime (stil 002/045)
    'CREATE VIEW "public"."leak" AS SELECT 1;',                                 # navodnici
    "CREATE MATERIALIZED VIEW public.leak AS SELECT 1;",
    "ALTER FUNCTION public.f() SECURITY DEFINER;",
    "CREATE VIEW public.v AS SELECT 1;\nREVOKE SELECT ON public.v FROM anon, authenticated;",   # delimičan REVOKE
    "CREATE VIEW public.v AS SELECT 'security_invoker = true';",                # tekst u literalu ne važi
    "GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO anon;",
    "GRANT SELECT ON public.t TO authenticated;",
    "GRANT EXECUTE ON FUNCTION public.f() TO PUBLIC;",
    "CREATE FUNCTION f() RETURNS int LANGUAGE sql SECURITY DEFINER AS $$ SELECT 1 $$;",
])
def test_cuvar_hvata_poznate_zaobilaznice(sql):
    assert prekrsaji(sql) != []


@pytest.mark.parametrize("sql", [
    "CREATE OR REPLACE FUNCTION public.x(a int) RETURNS int LANGUAGE sql SECURITY DEFINER AS $$ SELECT 1; $$;" + ZATVORI.format(k="FUNCTION"),
    "CREATE FUNCTION public.x() RETURNS int LANGUAGE sql SECURITY DEFINER AS $$ SELECT 1 $$;\n"
    "REVOKE ALL ON FUNCTION public.x() FROM anon;\nREVOKE ALL ON FUNCTION public.x() FROM authenticated;",
    "CREATE VIEW public.x WITH (security_invoker = true) AS SELECT 1;",
    "CREATE VIEW public.x AS SELECT '-- nije komentar';" + ZATVORI.format(k="TABLE"),
    "CREATE FUNCTION public.t() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$ BEGIN RETURN NULL; END $$;",
    "CREATE FUNCTION public.f() RETURNS int LANGUAGE sql AS $$ SELECT 1 $$;",
    "GRANT SELECT ON public.t TO service_role;",
    "-- GRANT SELECT ON public.t TO anon;\nSELECT 1;",
])
def test_cuvar_propusta_ispravne_obrasce(sql):
    assert prekrsaji(sql) == []
