# -*- coding: utf-8 -*-
"""S02 / B7 — odluka advokata o spornoj tački nad PRAVIM PostgreSQL-om (izolovan lokalni klaster, `VX_TEST_PG_DSN`).

Dokazuje SQL koji odluka A koristi bez migracije: migracije 119–125 (stvarni `v2_persist_observation_package` i
`v2_persist_contradiction`) i uslovni upis statusa koji radi `routers/sporna_tacka.py`:
  * odbijena tačka (`RESOLVED`/`WITHDRAWN`) se ponovnim opažanjem istih tvrdnji NE vraća: RPC je pronalazi po otisku
    početnog skupa (120) i ne menja joj status — nijedna nova sporna tačka, ista kontradikcija;
  * potvrđena (`CONFIRMED`) ostaje potvrđena kroz nastavak i kroz kompletno opažanje koje je ne vidi;
  * dva istovremena uslovna upisa odluke → tačno jedan prolazi;
  * opažanje doneto PRE ljudske odluke (stari `xmin`) se odbija (55000) — odluka se ne pregazi.
Šema tabela van 119–125 je minimalna (isti tipovi i FK kao 016 i auth). Bez DSN-a test se preskače.
"""
import json
import threading
import uuid

import pytest

from tests.ns007_pg import migracija, sveza_baza, zahteva_pg

pytestmark = zahteva_pg

_SEMA = """
CREATE TABLE auth.users (id uuid PRIMARY KEY);
CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS
  $$ SELECT COALESCE(NULLIF(current_setting('request.jwt.claim.role', true), ''), current_user::text) $$;
GRANT EXECUTE ON FUNCTION auth.role() TO anon, authenticated, service_role;
CREATE TABLE public.predmet_dokazi (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), predmet_id uuid NOT NULL REFERENCES public.predmeti(id) ON DELETE CASCADE,
  user_id uuid NOT NULL, tvrdnja text NOT NULL, identitet text, deleted_at timestamptz);
"""
A = str(uuid.uuid4())


@pytest.fixture
def baza():
    import psycopg
    with sveza_baza() as dsn:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(_SEMA)
            c.execute("INSERT INTO auth.users (id) VALUES (%s)", (A,))
            for m in ("119", "120", "121", "122", "123", "124", "125"):
                c.execute(migracija(m))
        yield dsn


def _predmet(c, tvrdnji=4):
    pid = str(c.execute("INSERT INTO predmeti (user_id, naziv) VALUES (%s,'S02') RETURNING id", (A,)).fetchone()[0])
    ids = [str(c.execute("INSERT INTO predmet_dokazi (predmet_id, user_id, tvrdnja) VALUES (%s,%s,%s) RETURNING id",
                         (pid, A, f"tvrdnja {i}")).fetchone()[0]) for i in range(tvrdnji)]
    return pid, ids


def _paket(c, pid, stavke, kompletno=True, verzija=None):
    v = c.execute("SELECT observation_version FROM predmeti WHERE id=%s", (pid,)).fetchone()[0] if verzija is None else verzija
    c.execute("SET ROLE service_role")
    try:
        return c.execute("SELECT out_indeks, out_issue_id, out_contradiction_id, out_created_issue "
                         "FROM public.v2_persist_observation_package(%s,%s,%s,%s,%s,%s::jsonb)",
                         (pid, A, None, v, kompletno, json.dumps(stavke))).fetchall()
    finally:
        c.execute("RESET ROLE")


def _stavka(i, dokazi, ref=None, xmin=None):
    return {"indeks": i, "issue_ref": str(ref) if ref else None, "label": f"tema {i}", "relation_type": "cinjenica_cinjenica", "tezina": "vazna",
            "fingerprint": "fp-" + "-".join(sorted(dokazi)), "dokaz_ids": sorted(dokazi), "claim_identiteti": [None] * len(dokazi),
            "expected_xmin": xmin}


_VIDJENO: dict = {}      # obuhvat poslednje odluke po temi — ruta ga upisuje u audit zapis odluke (`obuhvat`)


def _sadrzaj(c, issue):
    """Šta advokat VIDI: otvorene / za pregled kontradikcije teme i njihove aktivne tvrdnje (`obuhvat_sadrzaja`)."""
    from shared.issue_v2 import obuhvat_sadrzaja
    kon = c.execute("SELECT id::text FROM predmet_contradictions WHERE issue_id=%s AND state IN ('OPEN','REVIEW_REQUIRED')",
                    (issue,)).fetchall()
    return obuhvat_sadrzaja([{"id": kid, "claim_ids": [r[0] for r in c.execute(
        "SELECT dokaz_id::text FROM predmet_contradiction_claims WHERE contradiction_id=%s AND removed_at IS NULL", (kid,)).fetchall()]}
        for (kid,) in kon])


def _odluka(c, issue, staro, novo, close_reason=None):
    """Isti upis kao routers/sporna_tacka.py (PostgREST UPDATE … WHERE id AND user_id AND status = očekivani); obuhvat
    onoga što je advokat video ide u `_VIDJENO` (ruta: audit zapis odluke)."""
    vidjeno = _sadrzaj(c, issue)
    r = c.execute("UPDATE predmet_issues SET status=%s, close_reason=%s, closed_at=CASE WHEN %s::text IS NULL THEN NULL ELSE now() END, "
                  "updated_at=now() WHERE id=%s AND user_id=%s AND status=%s RETURNING id",
                  (novo, close_reason, close_reason, issue, A, staro)).fetchall()
    if r:
        _VIDJENO[str(issue)] = {"vazi": "POTVRDJENA" if novo == "CONFIRMED" else "ODBIJENA", "obuhvat": vidjeno}
    return len(r)


def test_odbijena_se_ne_vraca_a_potvrdjena_ostaje_kroz_ponovna_opazanja(baza):
    import psycopg
    with psycopg.connect(baza, autocommit=True) as c:
        pid, d = _predmet(c)
        [(_, odb, k_odb, nova1), (_, pot, k_pot, nova2)] = sorted(_paket(c, pid, [_stavka(0, d[:2]), _stavka(1, d[2:])]))
        assert nova1 and nova2
        assert _odluka(c, odb, "DISCOVERED", "RESOLVED", "WITHDRAWN") == 1
        assert _odluka(c, pot, "DISCOVERED", "CONFIRMED") == 1

        # Domen (shared/issue_v2) ne nudi RESOLVED temu kao kandidata za nastavak → isto opažanje stiže kao NOVA tema
        # (issue_ref=None); potvrđena je otvorena tema → nastavak sa `xmin` posle odluke.
        xmin_pot = c.execute("SELECT xmin::text FROM predmet_issues WHERE id=%s", (pot,)).fetchone()[0]
        rez = sorted(_paket(c, pid, [_stavka(0, d[:2]), _stavka(1, d[2:], ref=pot, xmin=xmin_pot)]))
        assert [(str(r[1]), str(r[2]), r[3]) for r in rez] == [(str(odb), str(k_odb), False), (str(pot), str(k_pot), False)]
        stanje = dict(c.execute("SELECT id::text, status || '/' || coalesce(close_reason,'') FROM predmet_issues").fetchall())
        assert stanje == {str(odb): "RESOLVED/WITHDRAWN", str(pot): "CONFIRMED/"}             # nijedna nova, odluke netaknute

        # Kompletno opažanje bez potvrđene: kontradikcija NOT_OBSERVED, ali odluka advokata (status teme) ostaje.
        _paket(c, pid, [_stavka(0, d[:2])])
        assert c.execute("SELECT status FROM predmet_issues WHERE id=%s", (pot,)).fetchone()[0] == "CONFIRMED"
        assert c.execute("SELECT state FROM predmet_contradictions WHERE id=%s", (k_pot,)).fetchone()[0] == "NOT_OBSERVED"
        assert c.execute("SELECT count(*) FROM predmet_issues").fetchone()[0] == 2


def test_dve_istovremene_odluke_prolazi_tacno_jedna(baza):
    import psycopg
    with psycopg.connect(baza, autocommit=True) as c:
        pid, d = _predmet(c, 2)
        [(_, issue, _, _)] = _paket(c, pid, [_stavka(0, d)])
    rezultati, kapija = [], threading.Barrier(2)

    def _radnik(novo, razlog):
        with psycopg.connect(baza, autocommit=True) as c2:
            kapija.wait()
            rezultati.append((novo, _odluka(c2, issue, "DISCOVERED", novo, razlog)))
    niti = [threading.Thread(target=_radnik, args=a) for a in (("CONFIRMED", None), ("RESOLVED", "WITHDRAWN"))]
    [n.start() for n in niti]
    [n.join(30) for n in niti]
    assert sorted(r for _, r in rezultati) == [0, 1]
    pobednik = next(n for n, r in rezultati if r == 1)
    with psycopg.connect(baza, autocommit=True) as c:
        assert c.execute("SELECT status FROM predmet_issues WHERE id=%s", (issue,)).fetchone()[0] == pobednik


def test_opazanje_doneto_pre_odluke_ne_pregazi_odluku(baza):
    import psycopg
    with psycopg.connect(baza, autocommit=True) as c:
        pid, d = _predmet(c, 3)
        [(_, issue, _, _)] = _paket(c, pid, [_stavka(0, d[:2])])
        xmin_pre = c.execute("SELECT xmin::text FROM predmet_issues WHERE id=%s", (issue,)).fetchone()[0]
        assert _odluka(c, issue, "DISCOVERED", "CONFIRMED") == 1                          # advokat odluči u međuvremenu
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            _paket(c, pid, [_stavka(0, d, ref=issue, xmin=xmin_pre)])
        assert c.execute("SELECT status FROM predmet_issues WHERE id=%s", (issue,)).fetchone()[0] == "CONFIRMED"


def _efektivno(c, issue):
    """`shared/issue_v2.efektivna_odluka` nad stvarnim redovima: tema + svaka njena otvorena kontradikcija."""
    from shared.issue_v2 import efektivna_odluka
    st, close, odl = c.execute("SELECT status, close_reason, updated_at FROM predmet_issues WHERE id=%s", (issue,)).fetchone()
    out = {}
    for kid, rel, created in c.execute("SELECT id, relation_type, created_at FROM predmet_contradictions "
                                       "WHERE issue_id=%s AND state='OPEN'", (issue,)).fetchall():
        cl = c.execute("SELECT dokaz_id::text, observed_at FROM predmet_contradiction_claims "
                       "WHERE contradiction_id=%s AND removed_at IS NULL", (kid,)).fetchall()
        out[rel] = efektivna_odluka({"id": str(kid), "issue_status": st, "issue_close_reason": close, "issue_odluka_at": odl.isoformat(),
                                     "created_at": created.isoformat(), "clanovi_od": [t.isoformat() for _, t in cl],
                                     "claim_ids": [d for d, _ in cl], "odluka_obuhvat": _VIDJENO.get(str(issue))})
    return out


def test_odluka_ne_vazi_za_sadrzaj_nastao_posle_nje(baza):
    """M1 (nezavisni pregled): RPC posle potvrde nastavlja temu NADSKUPOM (nova tvrdnja), a posle odbijanja vezuje NOVU
    relaciju za odbijenu temu (otisak). Odluka advokata ne sme da važi za taj sadržaj — ponovo „čeka odluku“."""
    import psycopg
    import time
    with psycopg.connect(baza, autocommit=True) as c:
        pid, d = _predmet(c, 6)
        [(_, pot, _, _), (_, odb, _, _)] = sorted(_paket(c, pid, [_stavka(0, d[:2]), _stavka(1, d[2:4])]))
        assert _odluka(c, pot, "DISCOVERED", "CONFIRMED") == 1
        assert _odluka(c, odb, "DISCOVERED", "RESOLVED", "WITHDRAWN") == 1
        assert _efektivno(c, pot) == {"cinjenica_cinjenica": "POTVRDJENA"}
        assert _efektivno(c, odb) == {"cinjenica_cinjenica": "ODBIJENA"}
        time.sleep(0.01)
        xmin = c.execute("SELECT xmin::text FROM predmet_issues WHERE id=%s", (pot,)).fetchone()[0]
        nova_rel = {**_stavka(1, d[2:4]), "relation_type": "cinjenica_norma"}
        _paket(c, pid, [_stavka(0, d[:2] + [d[4]], ref=pot, xmin=xmin), nova_rel], kompletno=False)
        assert c.execute("SELECT status FROM predmet_issues WHERE id=%s", (pot,)).fetchone()[0] == "CONFIRMED"   # RPC ne dira
        assert _efektivno(c, pot) == {"cinjenica_cinjenica": "CEKA_ODLUKU"}                      # nova tvrdnja posle potvrde
        assert _efektivno(c, odb) == {"cinjenica_cinjenica": "ODBIJENA", "cinjenica_norma": "CEKA_ODLUKU"}


def test_paket_pre_odluke_ne_dodaje_sadrzaj_pod_odluku(baza):
    """R3-M1 (nezavisni pregled): opažanje pročitano PRE „Ipak potvrdi“ odbijene teme stiže POSLE odluke sa novom
    relacijom nad istim tvrdnjama. Adapter (services/v2_contradiction_persistence) temu istog otiska imenuje i šalje
    njen `xmin` — baza odbija ustajalo opažanje (55000); ništa nije dodato pod potvrdu."""
    import psycopg
    with psycopg.connect(baza, autocommit=True) as c:
        pid, d = _predmet(c, 2)
        [(_, issue, _, _)] = _paket(c, pid, [_stavka(0, d)])
        assert _odluka(c, issue, "DISCOVERED", "RESOLVED", "WITHDRAWN") == 1
        xmin_pre = c.execute("SELECT xmin::text FROM predmet_issues WHERE id=%s", (issue,)).fetchone()[0]   # adapter čita
        assert _odluka(c, issue, "RESOLVED", "CONFIRMED") == 1                                           # „Ipak potvrdi“
        nova_rel = {**_stavka(0, d, ref=issue, xmin=xmin_pre), "relation_type": "cinjenica_norma"}
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            _paket(c, pid, [nova_rel], kompletno=False)
        assert c.execute("SELECT count(*) FROM predmet_contradictions WHERE relation_type='cinjenica_norma'").fetchone()[0] == 0


def test_ozivljena_kontradikcija_ne_nasledjuje_odluku(baza):
    """RC pregled (HIGH): kompletno opažanje zatvori relaciju teme (NOT_OBSERVED), advokat zatim odluči o temi videvši
    SAMO preostalu otvorenu relaciju; kasnije opažanje ponovo otvori zatvorenu relaciju NA ISTOM REDU (122) — sa starim
    `created_at` i starim članovima. Ta relacija ne sme da nasledi odluku: advokat je nije video."""
    import psycopg
    import time
    with psycopg.connect(baza, autocommit=True) as c:
        pid, d = _predmet(c, 2)
        [(_, issue, k1, _)] = _paket(c, pid, [_stavka(0, d)])
        druga = lambda: {**_stavka(1, d, ref=issue, xmin=c.execute("SELECT xmin::text FROM predmet_issues WHERE id=%s",
                                                                    (issue,)).fetchone()[0]), "relation_type": "cinjenica_norma"}
        prva = lambda: _stavka(0, d, ref=issue, xmin=c.execute("SELECT xmin::text FROM predmet_issues WHERE id=%s",
                                                                (issue,)).fetchone()[0])
        _paket(c, pid, [prva(), druga()], kompletno=False)
        k2 = c.execute("SELECT id FROM predmet_contradictions WHERE issue_id=%s AND relation_type='cinjenica_norma'", (issue,)).fetchone()[0]
        _paket(c, pid, [prva()])                                                            # kompletno, bez druge relacije
        assert c.execute("SELECT state FROM predmet_contradictions WHERE id=%s", (k2,)).fetchone()[0] == "NOT_OBSERVED"
        for staro, novo, razlog in (("DISCOVERED", "CONFIRMED", None), ("CONFIRMED", "RESOLVED", "WITHDRAWN")):
            assert _odluka(c, issue, staro, novo, razlog) == 1                              # advokat vidi samo prvu relaciju
            vazi = "POTVRDJENA" if novo == "CONFIRMED" else "ODBIJENA"
            assert _efektivno(c, issue) == {"cinjenica_cinjenica": vazi}
            time.sleep(0.01)
            _paket(c, pid, [prva(), druga()])                                               # druga relacija oživi
            assert c.execute("SELECT state FROM predmet_contradictions WHERE id=%s", (k2,)).fetchone()[0] == "OPEN"
            # potvrda je ne aktivira, odbijanje je ne skriva — čeka odluku
            assert _efektivno(c, issue) == {"cinjenica_cinjenica": vazi, "cinjenica_norma": "CEKA_ODLUKU"}
            _paket(c, pid, [prva()])                                                        # pa opet nestane
