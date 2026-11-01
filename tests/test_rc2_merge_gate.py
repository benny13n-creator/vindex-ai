# -*- coding: utf-8 -*-
"""PR #64 — završna kapija pred spajanje (nalazi nezavisnog pregleda diffa).

A (HIGH)   Brisanje ročišta: istorija nikad ne sme da predstavi POKUŠAJ ili NEUSPELO brisanje kao izvršeno; uspešno
           brisanje ostaje pripisano korisniku, sa prethodnim stanjem. Autoritativan dokaz brisanja je trajni događaj
           `SourceInvalidated` koji RPC 133 upisuje u ISTOJ transakciji sa brisanjem (deterministički id po ročištu).
B (MEDIUM) Izmena ročišta posle pada audita: kompenzacija vraća i `updated_at`, pa prethodno važeći token konkurentnosti
           ponovo važi. Kompenzacija je zaseban upis — nije transakcija; pad kompenzacije se kaže (503 „možda sačuvana“).
C (RISK)   Odbijena protivrečnost posle pada trajnog događaja: radnja „Razrešiti kontradikciju“ ne sme da ostane otvorena
           (direktno kanonsko usklađivanje, kao routers/predmeti_close.py).
Stvarne rute nad bazom u memoriji; RPC 133 nad PRAVIM PostgreSQL-om u test_rpc_133_*.
"""
import uuid

import pytest

from tests.test_n3_rocista import _predmet, lanac  # noqa: F401 — `lanac` je fixture
from tests.test_osb002_solo_tok import A, B, _do_kraja_dogadjaja, solo  # noqa: F401
from tests.test_s04_rociste_audit import _izmene, _zakazi
from tests.test_s02_kontradikcije_potvrda import URUCENJE, _akcije, _kon, _odluka, _po_labeli, predmet  # noqa: F401


def _audit(b, akcija, rid):
    return [x for x in b.tabele.get("audit_immutable", []) if x["action"] == akcija and x["resource_id"] == rid]


def _rpc_baze(b, *, pre=None, pad=False):
    """RPC 133 nad bazom u memoriji: briše SAMO red vlasnika i u istom koraku upisuje SourceInvalidated (isti id)."""
    from services.event_bus import _source_invalidation_event_id

    async def _rpc(rociste_id, user_id, correlation_id=None, supa=None):
        if pre:
            pre()
        if pad:
            raise RuntimeError("RPC pao posle upisa zahteva (test)")
        red = next((x for x in b.tabele["rocista"] if x["id"] == rociste_id and x["user_id"] == user_id), None)
        if red is None:
            return None, False
        b.tabele["rocista"].remove(red)
        b.tabele.setdefault("events", []).append({"id": _source_invalidation_event_id("rociste", rociste_id),
                                                  "event_type": "SourceInvalidated", "user_id": user_id,
                                                  "predmet_id": red.get("predmet_id"),
                                                  "payload": {"source_type": "rociste", "source_id": rociste_id}})
        return red.get("predmet_id"), True
    return _rpc


def _dogadjaji_brisanja(b, rid):
    return [e for e in b.tabele.get("events", []) if e.get("event_type") == "SourceInvalidated"
            and (e.get("payload") or {}).get("source_id") == rid]


# ── A ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_A_pad_brisanja_posle_upisa_istorije_ne_tvrdi_da_je_obrisano(lanac, monkeypatch):
    import services.event_bus as EB
    k, b = lanac
    r1 = _zakazi(k, _predmet(k), 10)
    monkeypatch.setattr(EB, "invalidate_rociste_atomic", _rpc_baze(b, pad=True))
    r = k.delete(f"/api/rocista/{r1['id']}", headers=A)
    assert r.status_code == 503, r.text            # ishod nepotvrđen: 503, ne neobrađen 500
    assert any(x["id"] == r1["id"] for x in b.tabele["rocista"]), "ročište nije obrisano"
    assert _audit(b, "rociste_delete", r1["id"]) == [], "istorija ne sme da kaže „obrisano“ za neuspelo brisanje"
    assert _dogadjaji_brisanja(b, r1["id"]) == []
    [zahtev] = _audit(b, "rociste_brisanje_zahtev", r1["id"])           # zahtev sa prethodnim stanjem jeste zabeležen
    assert zahtev["metadata"]["prethodno"]["datum"] == r1["datum"] and zahtev["user_id"] == "uid-A"


def test_A_istovremeno_brisanje_invalidated_false_nije_nase_brisanje(lanac, monkeypatch):
    """Drugi tok (drugi tab, brisanje izvornog dokumenta) obriše ročište između našeg čitanja i RPC-a → RPC vrati
    invalidated=false. Naš zahtev nije obrisao ništa: 404 i nijedan „rociste_delete“ od ovog zahteva."""
    import services.event_bus as EB
    k, b = lanac
    r1 = _zakazi(k, _predmet(k), 10)

    def _drugi_tok():
        red = next(x for x in b.tabele["rocista"] if x["id"] == r1["id"])
        b.tabele["rocista"].remove(red)
    monkeypatch.setattr(EB, "invalidate_rociste_atomic", _rpc_baze(b, pre=_drugi_tok))
    r = k.delete(f"/api/rocista/{r1['id']}", headers=A)
    assert r.status_code == 404, r.text
    assert _audit(b, "rociste_delete", r1["id"]) == []
    assert len(_audit(b, "rociste_brisanje_zahtev", r1["id"])) == 1


def test_A_uspesno_brisanje_pripisano_sa_prethodnim_stanjem_i_trajnim_dogadjajem(lanac, monkeypatch):
    import services.event_bus as EB
    k, b = lanac
    r1 = _zakazi(k, _predmet(k), 10)
    assert k.patch(f"/api/rocista/{r1['id']}", json={"napomena": "pre brisanja"}, headers=A).status_code == 200
    monkeypatch.setattr(EB, "invalidate_rociste_atomic", _rpc_baze(b))
    assert k.delete(f"/api/rocista/{r1['id']}", headers=A).status_code == 200
    assert not any(x["id"] == r1["id"] for x in b.tabele["rocista"])
    [z] = _audit(b, "rociste_delete", r1["id"])
    assert z["user_id"] == "uid-A" and z["metadata"]["prethodno"]["napomena"] == "pre brisanja"
    [e] = _dogadjaji_brisanja(b, r1["id"])
    assert z["metadata"]["dogadjaj_id"] == e["id"] and e["user_id"] == "uid-A"


def test_A_pad_istorije_zahteva_ne_brise(lanac, monkeypatch):
    import services.event_bus as EB
    import shared.audit_immutable as AUD
    k, b = lanac
    r1 = _zakazi(k, _predmet(k), 10)
    monkeypatch.setattr(EB, "invalidate_rociste_atomic", _rpc_baze(b))
    orig = AUD.log_action

    async def _pad(action, *a, **kw):
        return None if action == "rociste_brisanje_zahtev" else await orig(action, *a, **kw)
    monkeypatch.setattr(AUD, "log_action", _pad)
    assert k.delete(f"/api/rocista/{r1['id']}", headers=A).status_code == 503
    assert any(x["id"] == r1["id"] for x in b.tabele["rocista"]) and _dogadjaji_brisanja(b, r1["id"]) == []


# ── B ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _patch_sa_padom_audita(k, b, monkeypatch, rid, telo):
    """PATCH čiji audit ne uspe; vraća (odgovor, telo svakog UPDATE-a nad `rocista`)."""
    import shared.audit_immutable as AUD
    orig, pravi, upisi = AUD.log_action, b.table, []

    async def _pad(action, *a, **kw):
        return None if action == "rociste_izmena" else await orig(action, *a, **kw)

    def table(ime):
        q = pravi(ime)
        if ime == "rocista":
            upd = q.update

            def update(polja, *a, **kw):
                upisi.append(dict(polja))
                return upd(polja, *a, **kw)
            q.update = update
        return q
    monkeypatch.setattr(AUD, "log_action", _pad)
    monkeypatch.setattr(b, "table", table)
    r = k.patch(f"/api/rocista/{rid}", json=telo, headers=A)
    monkeypatch.setattr(b, "table", pravi)
    monkeypatch.setattr(AUD, "log_action", orig)
    return r, upisi


def test_B_pad_audita_izmene_vraca_poslovna_polja_i_trazi_stari_token(lanac, monkeypatch):
    """Kompenzacija vraća poslovna polja I šalje prethodni `updated_at`. Baza u memoriji (ns005_harness) emulira
    trigger koji pomera `updated_at` na SVAKI UPDATE — pod tim uslovom stari token dobija 409 (osveži), nikad tiho
    prepisivanje. Bez triggera (šema migracije 005) vraća se ceo red — test_B_rpc_kompenzacija_nad_postgresom."""
    k, b = lanac
    r1 = _zakazi(k, _predmet(k), 10)
    assert k.patch(f"/api/rocista/{r1['id']}", json={"napomena": "prva"}, headers=A).status_code == 200
    pre = dict(next(x for x in b.tabele["rocista"] if x["id"] == r1["id"]))
    r, upisi = _patch_sa_padom_audita(k, b, monkeypatch, r1["id"], {"status": "otkazano", "if_updated_at": pre["updated_at"]})
    assert r.status_code == 503, r.text
    assert len(upisi) == 2 and upisi[1] == {"status": pre["status"], "updated_at": pre["updated_at"]}, upisi
    posle = dict(next(x for x in b.tabele["rocista"] if x["id"] == r1["id"]))
    assert {c: posle.get(c) for c in pre if c != "updated_at"} == {c: pre.get(c) for c in pre if c != "updated_at"}
    assert _izmene(b, r1["id"])[-1]["metadata"]["novo"]["napomena"] == "prva"          # nijedan zapis o otkazivanju
    r2 = k.patch(f"/api/rocista/{r1['id']}", json={"status": "otkazano", "if_updated_at": pre["updated_at"]}, headers=A)
    if posle["updated_at"] == pre["updated_at"]:
        assert r2.status_code == 200, r2.text
    else:   # trigger pomerio token: 409, red netaknut
        assert r2.status_code == 409 and next(x for x in b.tabele["rocista"] if x["id"] == r1["id"])["status"] == pre["status"]


def test_B_rpc_kompenzacija_nad_postgresom():
    """Šema `rocista` iz migracije 005 (bez triggera): isti uslovni UPDATE kompenzacije vraća CEO red, uključujući
    `updated_at`, pa prethodno važeći token ponovo važi, a token neuspele izmene više ne važi."""
    from tests.ns007_pg import dostupan, sveza_baza
    if not dostupan():
        pytest.skip("ni VX_TEST_PG_DSN ni VINDEX_PG_TEST_DSN nije podešen")
    import psycopg
    u = str(uuid.uuid4())
    with sveza_baza() as dsn, psycopg.connect(dsn, autocommit=True) as c:
        c.execute("CREATE SCHEMA IF NOT EXISTS auth; CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY)")
        c.execute("INSERT INTO auth.users (id) VALUES (%s)", (u,))
        from tests.ns007_pg import migracija
        c.execute(migracija("005"))
        assert c.execute("SELECT count(*) FROM pg_trigger WHERE tgrelid = 'public.rocista'::regclass AND NOT tgisinternal"
                         ).fetchone()[0] == 0
        pid = c.execute("INSERT INTO predmeti (user_id, naziv) VALUES (%s,'B') RETURNING id", (u,)).fetchone()[0]
        rid = c.execute("INSERT INTO rocista (predmet_id, user_id, sud, datum) VALUES (%s,%s,'S','2026-12-01') RETURNING id",
                        (pid, u)).fetchone()[0]
        pre = c.execute("SELECT * FROM rocista WHERE id=%s", (rid,)).fetchone()
        stari = c.execute("SELECT updated_at FROM rocista WHERE id=%s", (rid,)).fetchone()[0]
        novi = c.execute("UPDATE rocista SET status='otkazano', updated_at=now() + interval '1 second' "
                         "WHERE id=%s AND updated_at=%s RETURNING updated_at", (rid, stari)).fetchone()[0]
        # kompenzacija (isti oblik kao routers/rocista.py): polja + updated_at, uslov = naš upis
        assert c.execute("UPDATE rocista SET status='zakazano', updated_at=%s WHERE id=%s AND user_id=%s AND updated_at=%s "
                         "RETURNING id", (stari, rid, u, novi)).fetchone() is not None
        assert c.execute("SELECT * FROM rocista WHERE id=%s", (rid,)).fetchone() == pre
        assert c.execute("UPDATE rocista SET status='odrzano' WHERE id=%s AND updated_at=%s RETURNING id", (rid, novi)).fetchone() is None
        assert c.execute("UPDATE rocista SET status='odrzano' WHERE id=%s AND updated_at=%s RETURNING id", (rid, stari)).fetchone() is not None


def test_B_pad_kompenzacije_se_kaze_i_ne_tvrdi_vracanje(lanac, monkeypatch):
    """Kompenzacija je zaseban upis (nema transakcije sa izmenom): ako i ona padne, izmena ostaje bez istorije — odgovor
    je 503 (globalni handler sakriva tekst), a log kaže „NIJE vraćena“. To je stvarna granica garancije."""
    import shared.audit_immutable as AUD
    k, b = lanac
    r1 = _zakazi(k, _predmet(k), 10)
    orig = AUD.log_action

    async def _pad(action, *a, **kw):
        return None if action == "rociste_izmena" else await orig(action, *a, **kw)
    monkeypatch.setattr(AUD, "log_action", _pad)
    pravi, broj = b.table, []

    def table(ime):
        q = pravi(ime)
        if ime == "rocista":
            upd = q.update

            def update(polja, *a, **kw):
                broj.append(1)
                if len(broj) >= 2:
                    raise RuntimeError("pad kompenzacije (test)")
                return upd(polja, *a, **kw)
            q.update = update
        return q
    monkeypatch.setattr(b, "table", table)
    r = k.patch(f"/api/rocista/{r1['id']}", json={"status": "otkazano"}, headers=A)
    monkeypatch.setattr(b, "table", pravi)
    assert r.status_code == 503
    assert next(x for x in b.tabele["rocista"] if x["id"] == r1["id"])["status"] == "otkazano"
    assert _izmene(b, r1["id"]) == []


# ── C ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_C_odbijena_posle_pada_dogadjaja_nema_otvorenu_radnju(predmet, monkeypatch):
    import services.event_bus as EB
    k, b, pid = predmet
    x = _po_labeli(_kon(k, pid)["za_pregled"])[URUCENJE[0]]
    assert _odluka(k, pid, x, "potvrdi").status_code == 200
    _do_kraja_dogadjaja(b, najvise=10)
    assert len(_akcije(b, pid)) == 1, "potvrđena protivrečnost ima radnju"

    async def _pad(*a, **kw):
        raise RuntimeError("trajni događaj nije upisan (test)")
    monkeypatch.setattr(EB, "emit_durable", _pad)
    akt = _po_labeli(_kon(k, pid)["aktivne"])[URUCENJE[0]]
    assert _odluka(k, pid, akt, "odbij").status_code == 200
    assert _akcije(b, pid) == [], "odbijena protivrečnost ne sme da ostane radnja za izvršenje"
    r = k.get(f"/api/case-actions/predmeti/{pid}", headers=A)
    otvorene = [a for a in (r.json().get("akcije") or r.json().get("actions") or [])
                if a.get("tip") == "RAZRESITI_KONTRADIKCIJU" and (a.get("status") or "open") == "open"]
    assert r.status_code == 200 and otvorene == [], r.text[:300]


# ── RPC 133 nad pravim PostgreSQL-om ─────────────────────────────────────────────────────────────────────────────
def _rpc_133_sql():
    import re
    from tests.ns007_pg import migracija
    s = migracija("133")
    m = re.search(r"CREATE OR REPLACE FUNCTION public\.invalidate_rociste_and_emit_event\(.*?\n\$\$;", s, re.S)
    assert m, "funkcija nije pronađena u migraciji 133"
    return m.group(0)


def test_rpc_133_brisanje_i_dogadjaj_su_jedna_transakcija():
    """Autoritativan dokaz uspešnog brisanja: posle RPC-a red ne postoji i postoji TAČNO jedan SourceInvalidated sa
    determinističkim id-em i user_id-em; drugi poziv (već obrisano / tuđe) vraća invalidated=false bez događaja; pad
    upisa događaja poništava i brisanje."""
    from tests.ns007_pg import dostupan, sveza_baza
    if not dostupan():
        pytest.skip("ni VX_TEST_PG_DSN ni VINDEX_PG_TEST_DSN nije podešen")
    import psycopg
    from services.event_bus import _source_invalidation_event_id
    u, tudji = str(uuid.uuid4()), str(uuid.uuid4())
    with sveza_baza() as dsn, psycopg.connect(dsn, autocommit=True) as c:
        c.execute("""CREATE TABLE public.rocista (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid NOT NULL,
                       user_id uuid NOT NULL, sud text, datum date);
                     CREATE TABLE public.events (id uuid PRIMARY KEY, event_type text NOT NULL, user_id uuid, predmet_id text,
                       payload jsonb, correlation_id text, created_at timestamptz DEFAULT now());""")
        c.execute(_rpc_133_sql())
        pid = str(c.execute("INSERT INTO predmeti (user_id, naziv) VALUES (%s,'RC2') RETURNING id", (u,)).fetchone()[0])
        rid = str(c.execute("INSERT INTO rocista (predmet_id, user_id, sud, datum) VALUES (%s,%s,'S','2026-12-01') RETURNING id",
                            (pid, u)).fetchone()[0])
        eid = _source_invalidation_event_id("rociste", rid)
        poziv = "SELECT predmet_id, invalidated FROM public.invalidate_rociste_and_emit_event(%s,%s,%s,NULL)"
        assert c.execute(poziv, (rid, tudji, eid)).fetchone() == (None, False)               # tuđe: ništa
        assert c.execute("SELECT count(*) FROM rocista").fetchone()[0] == 1
        assert c.execute(poziv, (rid, u, eid)).fetchone() == (pid, True)
        assert c.execute("SELECT count(*) FROM rocista").fetchone()[0] == 0
        assert c.execute("SELECT id::text, user_id::text, payload->>'source_id' FROM events").fetchall() == [(eid, u, rid)]
        assert c.execute(poziv, (rid, u, eid)).fetchone() == (None, False)                   # već obrisano
        assert c.execute("SELECT count(*) FROM events").fetchone()[0] == 1
        # pad upisa događaja (zauzet id drugim tipom → ne, ON CONFLICT ga guta) — pad tabele događaja poništava brisanje
        rid2 = str(c.execute("INSERT INTO rocista (predmet_id, user_id, sud, datum) VALUES (%s,%s,'S','2026-12-02') RETURNING id",
                             (pid, u)).fetchone()[0])
        c.execute("ALTER TABLE events ADD CONSTRAINT bez_novih CHECK (created_at < '2000-01-01') NOT VALID")
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(poziv, (rid2, u, _source_invalidation_event_id("rociste", rid2)))
        assert c.execute("SELECT count(*) FROM rocista WHERE id=%s", (rid2,)).fetchone()[0] == 1
