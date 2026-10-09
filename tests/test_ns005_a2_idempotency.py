# -*- coding: utf-8 -*-
"""NS005 Gate A2 — trajna idempotencija V2 upisa (shared/idempotency.py + migracija 134).

Deo 1 (uvek): stvarni `api.app` + stvarne rute + PRODUKCIONI `SupabaseSkladiste` nad lažnim
Supabase-om koji sprovodi PRIMARY KEY (user_id, idempotency_key) kao Postgres (23505).
Deo 2 (stvaran PostgreSQL, 127.0.0.1:55432 ili $VINDEX_TEST_PG_DSN): migracija 134 DOSLOVNO,
zauzimanje pod pravom konkurencijom, RLS/grantovi, ograničenja stanja, samo vlasnik završava,
istek ≠ dozvola, šifrovan odgovor kroz bazu, konkurentan duplikat kroz aplikaciju, i granica
procesa (dva OS procesa, isto skladište; memorijsko rešenje mora da padne, bazno da prođe).
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.ns005_harness import pripremi, ocisti, zaglavlje, SPOLJNI_POKUSAJI

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PA, PB = "pred-A-1", "pred-B-1"
TAB = "v2_mutation_idempotency"
ODGOVOR = {"status": "success", "data": "--- PRAVNI ZAKLJUČAK\nTAJNI PRAVNI ODGOVOR.", "confidence": "HIGH", "top_score": 0.8,
           "confidence_detail": {"nivo": "HIGH"}, "izvori": [{"zakon": "zakon o obligacionim odnosima", "clan": "Član 200"}]}


def K():
    return str(uuid.uuid4())


def _baza():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Predmet A", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan"}],
        "billing_entries": [], "timer_sessions": [], "tarifne_stavke_custom": [], "fakture": [],
        "predmet_istorija": [], "predmet_beleske": [], TAB: [],
    }


def _sa_kljucem(tok, kljuc):
    return {**zaglavlje(tok), "Idempotency-Key": kljuc}


@pytest.fixture
def ok(monkeypatch):
    k, b = pripremi(monkeypatch, _baza())
    import api
    import shared.idempotency as idem
    import shared.permissions as perm
    import shared.usage as us
    brojaci = {"model": 0, "kredit": 0}

    async def _politika(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free"}

    async def _nista(*a, **kw):
        return None

    async def _kredit(*a, **kw):
        brojaci["kredit"] += 1
        return 10

    async def _pokreni(fn, *a, **kw):
        brojaci["model"] += 1
        time.sleep(brojaci.get("kasnjenje", 0))
        return dict(ODGOVOR)

    monkeypatch.setattr(perm, "get_policy", _politika)
    monkeypatch.setattr(perm, "_check_dependencies", _nista)
    monkeypatch.setattr(us.UsageService, "consume", staticmethod(_kredit))
    monkeypatch.setattr(us.UsageService, "refund", staticmethod(_nista))
    monkeypatch.setattr(api, "_fetch_firm_memory_context", _nista, raising=False)
    monkeypatch.setattr(api, "_get_firma_namespace", _nista, raising=False)
    monkeypatch.setattr(api, "klasifikuj_pitanje", lambda *a, **kw: "opste", raising=False)
    monkeypatch.setattr(api, "pokreni", _pokreni)
    idem.postavi_skladiste(idem.SupabaseSkladiste)
    yield k, b, brojaci
    idem.postavi_skladiste(idem.SupabaseSkladiste)
    ocisti()


def _stavka(k, tok, kljuc, opis="Sastav tužbe", iznos=3000):
    h = _sa_kljucem(tok, kljuc) if kljuc else zaglavlje(tok)
    return k.post("/billing/entries", json={"predmet_id": PA if tok == "A" else PB, "opis": opis, "iznos_rsd": iznos}, headers=h)


# ─── Deo 1: stvarne rute, produkciono skladište nad lažnim Supabase-om ──────

def test_A_jedan_zahtev_jedno_izvrsavanje_i_zapis_completed(ok):
    k, b, _ = ok
    kljuc = K()
    r = _stavka(k, "A", kljuc)
    assert r.status_code == 200, r.text
    assert len(b.tabele["billing_entries"]) == 1
    red = b.tabele[TAB][0]
    assert red["state"] == "COMPLETED" and red["status_code"] == 200 and red["user_id"] == "uid-A" and red["idempotency_key"] == kljuc
    assert r.headers.get("idempotent-replayed") is None


def test_B_H_duplikat_posle_zavrsetka_isti_odgovor_jedna_stavka(ok):
    k, b, _ = ok
    kljuc = K()
    r1, r2 = _stavka(k, "A", kljuc), _stavka(k, "A", kljuc)
    assert r1.status_code == r2.status_code == 200
    assert r2.json() == r1.json() and r2.headers.get("idempotent-replayed") == "true"
    assert len(b.tabele["billing_entries"]) == 1


def test_D_isti_kljuc_drugo_telo_409_bez_efekta(ok):
    k, b, _ = ok
    kljuc = K()
    assert _stavka(k, "A", kljuc, opis="Prvo").status_code == 200
    r = _stavka(k, "A", kljuc, opis="Drugo")
    assert r.status_code == 409 and r.json()["kod"] == "IDEMPOTENCY_CONFLICT"
    assert [x["opis"] for x in b.tabele["billing_entries"]] == ["Prvo"]


def test_E_J_isti_kljuc_drugi_korisnik_nezavisan_bez_curenja(ok):
    k, b, _ = ok
    kljuc = K()
    ra = _stavka(k, "A", kljuc, opis="TAJNA stavka A")
    rb = _stavka(k, "B", kljuc, opis="Stavka B")
    assert ra.status_code == rb.status_code == 200
    assert "TAJNA" not in rb.text and rb.headers.get("idempotent-replayed") is None
    assert rb.json()["entry"]["user_id"] == "uid-B"
    assert sorted(x["user_id"] for x in b.tabele["billing_entries"]) == ["uid-A", "uid-B"]
    # B ponavlja SVOJ ključ → dobija SVOJ odgovor, nikad A-ov.
    rb2 = _stavka(k, "B", kljuc, opis="Stavka B")
    assert rb2.json() == rb.json() and "TAJNA" not in rb2.text


def test_G_pitanje_jedan_kredit_jedan_model_jedna_istorija_isti_odgovor(ok):
    k, b, br = ok
    kljuc = K()
    telo = {"pitanje": "Kako dokazati štetu?", "predmet_id": PA}
    r1 = k.post("/api/pitanje", json=telo, headers=_sa_kljucem("A", kljuc))
    r2 = k.post("/api/pitanje", json=telo, headers=_sa_kljucem("A", kljuc))
    assert r1.status_code == r2.status_code == 200, r1.text
    assert br["model"] == 1 and br["kredit"] == 1
    assert len(b.tabele["predmet_istorija"]) == 1
    assert r2.json() == r1.json() and r2.headers.get("idempotent-replayed") == "true"


def test_I_timer_stop_jedna_stavka_i_drugi_ne_kaze_lazno_nista(ok):
    k, b, _ = ok
    assert k.post("/billing/timer/start", json={"predmet_id": PA, "opis": "Priprema"}, headers=_sa_kljucem("A", K())).status_code == 200
    kljuc = K()
    r1 = k.post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=_sa_kljucem("A", kljuc))
    r2 = k.post("/billing/timer/stop", json={"kreiraj_entry": True}, headers=_sa_kljucem("A", kljuc))
    assert r1.status_code == 200 and r2.status_code == 200, r2.text   # bez zaštite drugi bi bio 404 „Nema aktivnog tajmera“
    assert r2.json() == r1.json() and r1.json()["entry"]["opis"] == "Priprema"
    assert len(b.tabele["billing_entries"]) == 1


def test_bez_kljuca_legacy_ponasanje_nepromenjeno(ok):
    k, b, _ = ok
    assert _stavka(k, "A", None).status_code == 200 and _stavka(k, "A", None).status_code == 200
    assert len(b.tabele["billing_entries"]) == 2 and b.tabele[TAB] == []


def test_neispravan_kljuc_400_bez_efekta(ok):
    k, b, _ = ok
    for los in ("abc", "' OR 1=1 --", str(uuid.uuid4()).upper(), str(uuid.uuid1()), "x" * 300):
        r = _stavka(k, "A", los)
        assert r.status_code == 400 and r.json()["kod"] == "IDEMPOTENCY_KEY_INVALID", los
    assert b.tabele["billing_entries"] == [] and b.tabele[TAB] == []


def test_bez_identiteta_401_bez_efekta(ok):
    k, b, _ = ok
    r = k.post("/billing/entries", json={"predmet_id": PA, "opis": "x", "iznos_rsd": 1},
               headers={"Authorization": "Bearer nepostojeci", "Idempotency-Key": K()})
    assert r.status_code == 401 and b.tabele["billing_entries"] == [] and b.tabele[TAB] == []


def test_prolazna_greska_identiteta_fail_closed_ruta_se_ne_izvrsava(ok, monkeypatch):
    # Provera identiteta u zaštiti padne (npr. prolazna JWKS/mrežna greška), a sledeća provera
    # u samoj ruti uspe: zahtev SA ključem se ipak ne sme izvršiti nezaštićen.
    k, b, _ = ok
    import shared.deps as deps
    pravi, stanje = deps._verify_token, {"n": 0}

    def _jednom_padne(t):
        stanje["n"] += 1
        if stanje["n"] == 1:
            raise RuntimeError("prolazna greska provere tokena")
        return pravi(t)
    monkeypatch.setattr(deps, "_verify_token", _jednom_padne)
    r = _stavka(k, "A", K())
    assert r.status_code == 401 and r.json()["kod"] == "AUTH_REQUIRED"
    assert b.tabele["billing_entries"] == [] and b.tabele[TAB] == []


def test_skladiste_nedostupno_503_fail_closed_bez_efekta(ok):
    k, b, br = ok
    b.greske[TAB] = Exception("db down")
    r = _stavka(k, "A", K())
    assert r.status_code == 503 and r.json()["kod"] == "IDEMPOTENCY_UNAVAILABLE"
    r2 = k.post("/api/pitanje", json={"pitanje": "Rok?"}, headers=_sa_kljucem("A", K()))
    assert r2.status_code == 503 and br["model"] == 0 and br["kredit"] == 0
    assert b.tabele["billing_entries"] == []


def _red_unapred(b, kljuc, telo, **polja):
    import shared.idempotency as idem
    fp = idem.otisak("POST", "/billing/entries", b"", json.dumps(telo).encode())
    red = {"user_id": "uid-A", "idempotency_key": kljuc, "method": "POST", "path": "/billing/entries",
           "request_fingerprint": fp, "state": "IN_PROGRESS", "owner_token": str(uuid.uuid4())}
    red.update(polja)
    b.tabele[TAB].append(red)


def test_in_progress_409_bez_izvrsavanja(ok):
    k, b, _ = ok
    kljuc, telo = K(), {"predmet_id": PA, "opis": "Sastav tužbe", "iznos_rsd": 3000}
    _red_unapred(b, kljuc, telo)
    r = k.post("/billing/entries", content=json.dumps(telo), headers={**_sa_kljucem("A", kljuc), "Content-Type": "application/json"})
    assert r.status_code == 409 and r.json()["kod"] == "IDEMPOTENCY_IN_PROGRESS" and r.headers.get("retry-after") == "5"
    assert b.tabele["billing_entries"] == []


def test_zastareo_in_progress_se_nikad_ne_preuzima(ok):
    k, b, _ = ok
    kljuc, telo = K(), {"predmet_id": PA, "opis": "Sastav tužbe", "iznos_rsd": 3000}
    _red_unapred(b, kljuc, telo, created_at="2020-01-01T00:00:00+00:00", expires_at="2020-01-02T00:00:00+00:00")
    r = k.post("/billing/entries", content=json.dumps(telo), headers={**_sa_kljucem("A", kljuc), "Content-Type": "application/json"})
    assert r.status_code == 409 and r.json()["kod"] == "IDEMPOTENCY_IN_PROGRESS"
    assert b.tabele["billing_entries"] == []


def test_necitljiv_sacuvan_odgovor_se_ne_ponavlja_i_ne_izvrsava(ok):
    k, b, _ = ok
    telo = {"predmet_id": PA, "opis": "Sastav tužbe", "iznos_rsd": 3000}
    for los in ("enc_v1:k1:AAAAovojenijesifrovano", "b64:eyJvayI6IHRydWV9", ""):
        kljuc = K()
        _red_unapred(b, kljuc, telo, state="COMPLETED", status_code=200, response_content_type="application/json", response_payload_enc=los)
        r = k.post("/billing/entries", content=json.dumps(telo), headers={**_sa_kljucem("A", kljuc), "Content-Type": "application/json"})
        assert r.status_code == 503 and r.json()["kod"] == "IDEMPOTENCY_REPLAY_UNAVAILABLE", los
    assert b.tabele["billing_entries"] == []


def test_sacuvan_odgovor_sifrovan_bez_tela_zahteva_i_tokena(ok):
    k, b, _ = ok
    r = k.post("/api/pitanje", json={"pitanje": "TAJNO PITANJE KLIJENTA"}, headers=_sa_kljucem("A", K()))
    assert r.status_code == 200
    red = b.tabele[TAB][0]
    sirovo = json.dumps(red, ensure_ascii=False)
    assert red["response_payload_enc"].startswith("enc_v1:")
    for zabranjeno in ("TAJNI PRAVNI ODGOVOR", "TAJNO PITANJE", "tok-A", "Bearer"):
        assert zabranjeno not in sirovo, zabranjeno
    assert set(red) >= {"user_id", "idempotency_key", "method", "path", "request_fingerprint", "state", "owner_token"}
    assert not ({"body", "request_body", "authorization", "headers"} & set(red))


def test_nezasticene_rute_ignorisu_kljuc(ok):
    k, b, _ = ok
    k.post("/api/praksa/search", json={"query": "naknada štete"}, headers=_sa_kljucem("A", K()))
    k.post("/api/nacrti/export/docx", json={"tekst": "x", "naslov": "x", "tip": "x"}, headers=_sa_kljucem("A", K()))
    assert b.tabele[TAB] == []


def test_samo_vlasnik_zavrsava_produkciono_skladiste(ok):
    k, b, _ = ok
    import shared.idempotency as idem
    s = idem.SupabaseSkladiste()
    red = {"user_id": "uid-A", "idempotency_key": K(), "method": "POST", "path": "/billing/entries",
           "request_fingerprint": "0" * 64, "state": "IN_PROGRESS", "owner_token": str(uuid.uuid4())}
    assert s.zauzmi(dict(red)) is True and s.zauzmi(dict(red)) is False
    polja = {"state": "COMPLETED", "status_code": 200, "response_content_type": "application/json",
             "response_payload_enc": "enc_v1:k1:x", "completed_at": "2026-10-09T00:00:00+00:00"}
    assert s.zavrsi("uid-A", red["idempotency_key"], str(uuid.uuid4()), dict(polja)) is False
    assert s.zavrsi("uid-A", red["idempotency_key"], red["owner_token"], dict(polja)) is True
    assert s.zavrsi("uid-A", red["idempotency_key"], red["owner_token"], dict(polja)) is False


def test_rad_bez_kljuca_ne_dodiruje_tabelu_i_ne_zavisi_od_nje(ok):
    # Gate C: aplikacija i zahtevi BEZ ključa ne čitaju ni ne pišu v2_mutation_idempotency — ni pri
    # pokretanju ni u radu. Skladište koje puca na SVAKI poziv ne sme ništa da obori.
    k, b, _ = ok
    import shared.idempotency as idem

    class _Puca:
        def __getattr__(self, ime):
            raise AssertionError("skladište ključeva ne sme biti dodirnuto bez Idempotency-Key")
    idem.postavi_skladiste(_Puca)
    assert _stavka(k, "A", None).status_code == 200
    assert k.get("/billing/entries", params={"predmet_id": PA}, headers=zaglavlje("A")).status_code == 200
    assert not [z for z in b.dnevnik if z["tabela"] == TAB]


def test_nema_spoljne_mreze():
    assert SPOLJNI_POKUSAJI == []


# ─── Deo 2: stvaran PostgreSQL ───────────────────────────────────────────────

psycopg = pytest.importorskip("psycopg")


def _server():
    for dsn in [os.getenv("VINDEX_TEST_PG_DSN")] if os.getenv("VINDEX_TEST_PG_DSN") else ["host=127.0.0.1 port=55432 user=postgres dbname=postgres"]:
        try:
            with psycopg.connect(dsn, connect_timeout=3):
                return dsn
        except Exception:
            continue
    return None


_SRV = _server()
pg = pytest.mark.skipif(_SRV is None, reason="nema PostgreSQL servera (127.0.0.1:55432 ili $VINDEX_TEST_PG_DSN) — dokaz migracije 134 preskočen")


@pytest.fixture(scope="module")
def pgdb():
    from tests.ns005_pg_skladiste import primeni_migraciju_134, obrisi_bazu
    ime, dsn = primeni_migraciju_134(_SRV, REPO)
    yield dsn
    obrisi_bazu(_SRV, ime)


@pytest.fixture
def ok_pg(ok, pgdb):
    import shared.idempotency as idem
    from tests.ns005_pg_skladiste import PgSkladiste
    idem.postavi_skladiste(lambda: PgSkladiste(pgdb))
    yield ok + (pgdb,)


@pg
def test_pg_struktura_i_primarni_kljuc(pgdb):
    with psycopg.connect(pgdb) as c:
        kol = {r[0] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (TAB,))}
        pk = [r[0] for r in c.execute(
            "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = 'public.v2_mutation_idempotency'::regclass AND i.indisprimary ORDER BY a.attnum")]
    assert {"user_id", "idempotency_key", "method", "path", "request_fingerprint", "state", "status_code",
            "response_payload_enc", "created_at", "completed_at", "expires_at", "owner_token"} <= kol
    assert not ({"body", "request_body", "authorization", "token"} & kol)
    assert pk == ["user_id", "idempotency_key"]


@pg
def test_pg_konkurentno_zauzimanje_tacno_jedan_vlasnik(pgdb):
    from tests.ns005_pg_skladiste import PgSkladiste
    s, kljuc, n = PgSkladiste(pgdb), K(), 24
    kapija, rez = threading.Barrier(n), []

    def radi():
        red = {"user_id": "uid-A", "idempotency_key": kljuc, "method": "POST", "path": "/api/pitanje",
               "request_fingerprint": "a" * 64, "state": "IN_PROGRESS", "owner_token": str(uuid.uuid4())}
        kapija.wait()
        rez.append(s.zauzmi(red))
    niti = [threading.Thread(target=radi) for _ in range(n)]
    [t.start() for t in niti]
    [t.join() for t in niti]
    assert rez.count(True) == 1 and rez.count(False) == n - 1


@pg
def test_pg_rls_i_grantovi_samo_service_role(pgdb):
    with psycopg.connect(pgdb, autocommit=True) as c:
        pr = {u: {p: c.execute("SELECT has_table_privilege(%s, 'public.v2_mutation_idempotency', %s)", (u, p)).fetchone()[0]
                  for p in ("SELECT", "INSERT", "UPDATE", "DELETE")} for u in ("anon", "authenticated", "service_role")}
        rls = c.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.v2_mutation_idempotency'::regclass").fetchone()[0]
        politike = c.execute("SELECT count(*) FROM pg_policies WHERE tablename = %s", (TAB,)).fetchone()[0]
        javno = c.execute("SELECT has_table_privilege('public', 'public.v2_mutation_idempotency', 'SELECT')").fetchone()[0]
        for uloga in ("anon", "authenticated"):
            c.execute(f'SET ROLE "{uloga}"')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("SELECT 1 FROM public.v2_mutation_idempotency LIMIT 1")
            c.execute("RESET ROLE")
    assert pr["anon"] == pr["authenticated"] == {"SELECT": False, "INSERT": False, "UPDATE": False, "DELETE": False}
    assert pr["service_role"] == {"SELECT": True, "INSERT": True, "UPDATE": True, "DELETE": False}
    assert rls is True and politike == 0 and javno is False


@pg
def test_pg_ogranicenja_stanja_i_formata(pgdb):
    osnova = {"user_id": str(uuid.uuid4()), "idempotency_key": K(), "method": "POST", "path": "/api/pitanje",
              "request_fingerprint": "b" * 64, "state": "IN_PROGRESS", "owner_token": str(uuid.uuid4()),
              "status_code": None, "response_payload_enc": None, "completed_at": None}
    lose = [dict(osnova, state="COMPLETED"),                                                    # COMPLETED bez statusa/odgovora
            dict(osnova, state="COMPLETED", status_code=200, completed_at=datetime.now(timezone.utc), response_payload_enc="ČIST TEKST"),
            dict(osnova, request_fingerprint="nije-sha256"), dict(osnova, method="DELETE"), dict(osnova, state="FAILED"),
            dict(osnova, status_code=200)]                                                      # IN_PROGRESS sa statusom
    sql = ("INSERT INTO public.v2_mutation_idempotency (user_id, idempotency_key, method, path, request_fingerprint, state, owner_token, "
           "status_code, response_payload_enc, completed_at) VALUES (%(user_id)s, %(idempotency_key)s, %(method)s, %(path)s, "
           "%(request_fingerprint)s, %(state)s, %(owner_token)s, %(status_code)s, %(response_payload_enc)s, %(completed_at)s)")
    with psycopg.connect(pgdb, autocommit=True) as c:
        for red in lose:
            with pytest.raises(psycopg.errors.CheckViolation):
                c.execute(sql, dict(red, idempotency_key=K()))
        c.execute(sql, osnova)
        istek = c.execute("SELECT expires_at - created_at FROM public.v2_mutation_idempotency WHERE idempotency_key = %s",
                          (osnova["idempotency_key"],)).fetchone()[0]
    assert istek == timedelta(hours=24)


@pg
def test_pg_samo_vlasnik_zavrsava(pgdb):
    from tests.ns005_pg_skladiste import PgSkladiste
    s, kljuc, vlasnik = PgSkladiste(pgdb), K(), str(uuid.uuid4())
    assert s.zauzmi({"user_id": "uid-A", "idempotency_key": kljuc, "method": "POST", "path": "/billing/entries",
                     "request_fingerprint": "c" * 64, "state": "IN_PROGRESS", "owner_token": vlasnik})
    polja = {"state": "COMPLETED", "status_code": 200, "response_content_type": "application/json",
             "response_payload_enc": "enc_v1:k1:x", "completed_at": datetime.now(timezone.utc)}
    assert s.zavrsi("uid-A", kljuc, str(uuid.uuid4()), polja) is False
    assert s.zavrsi("uid-A", kljuc, vlasnik, polja) is True
    assert s.zavrsi("uid-A", kljuc, vlasnik, polja) is False


@pg
def test_pg_aplikacija_ponavlja_sifrovan_odgovor_iz_baze(ok_pg):
    k, b, br, dsn = ok_pg
    kljuc = K()
    r1 = k.post("/api/pitanje", json={"pitanje": "Rok zastarelosti?"}, headers=_sa_kljucem("A", kljuc))
    r2 = k.post("/api/pitanje", json={"pitanje": "Rok zastarelosti?"}, headers=_sa_kljucem("A", kljuc))
    assert r1.status_code == r2.status_code == 200 and r2.json() == r1.json() and br["model"] == 1 and br["kredit"] == 1
    with psycopg.connect(dsn) as c:
        st, enc = c.execute("SELECT state, response_payload_enc FROM public.v2_mutation_idempotency WHERE idempotency_key = %s", (kljuc,)).fetchone()
    assert st == "COMPLETED" and enc.startswith("enc_v1:") and "TAJNI PRAVNI ODGOVOR" not in enc


@pg
def test_pg_istekao_in_progress_ostaje_zatvoren(ok_pg):
    k, b, br, dsn = ok_pg
    from tests.ns005_pg_skladiste import _uid
    import shared.idempotency as idem
    kljuc, telo = K(), json.dumps({"pitanje": "Rok?"}).encode()
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("INSERT INTO public.v2_mutation_idempotency (user_id, idempotency_key, method, path, request_fingerprint, state, owner_token, "
                  "created_at, expires_at) VALUES (%s, %s, 'POST', '/api/pitanje', %s, 'IN_PROGRESS', %s, now() - interval '3 days', now() - interval '2 days')",
                  (_uid("uid-A"), kljuc, idem.otisak("POST", "/api/pitanje", b"", telo), str(uuid.uuid4())))
    r = k.post("/api/pitanje", content=telo, headers={**_sa_kljucem("A", kljuc), "Content-Type": "application/json"})
    assert r.status_code == 409 and r.json()["kod"] == "IDEMPOTENCY_IN_PROGRESS" and br["model"] == 0 and br["kredit"] == 0


@pg
def test_C_konkurentan_duplikat_tacno_jedno_izvrsavanje(ok_pg):
    k, b, br, dsn = ok_pg
    br["kasnjenje"] = 1.0
    kljuc, rez = K(), []
    kapija = threading.Barrier(2)

    def posalji():
        kapija.wait()
        rez.append(k.post("/api/pitanje", json={"pitanje": "Rok?"}, headers=_sa_kljucem("A", kljuc)))
    niti = [threading.Thread(target=posalji) for _ in range(2)]
    [t.start() for t in niti]
    [t.join() for t in niti]
    statusi = sorted(r.status_code for r in rez)
    assert statusi == [200, 409], statusi
    assert [r for r in rez if r.status_code == 409][0].json()["kod"] == "IDEMPOTENCY_IN_PROGRESS"
    assert br["model"] == 1 and br["kredit"] == 1


def _proces(vrsta, dsn, kljuc, kasnjenje, dir_):
    izlaz = os.path.join(dir_, f"{uuid.uuid4().hex}.json")
    p = subprocess.Popen([sys.executable, os.path.join(REPO, "tests", "ns005_a2_proces.py"), vrsta, dsn or "-", kljuc, str(kasnjenje), izlaz],
                         cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return p, izlaz


def _sacekaj(par):
    p, izlaz = par
    _, err = p.communicate(timeout=300)
    assert p.returncode == 0, err.decode("utf-8", "replace")[-1500:]
    return json.load(open(izlaz, encoding="utf-8"))


@pg
def test_F_granica_procesa_baza_prolazi_memorija_pada(pgdb):
    with tempfile.TemporaryDirectory() as d:
        # Bazno skladište: drugi PROCES sa istim ključem ne izvršava rutu (ponavlja sačuvan odgovor).
        kljuc = K()
        a = _sacekaj(_proces("pg", pgdb, kljuc, 0, d))
        b = _sacekaj(_proces("pg", pgdb, kljuc, 0, d))
        assert a["status"] == 200 and a["model"] == 1 and a["kredit"] == 1
        assert b["status"] == 200 and b["model"] == 0 and b["kredit"] == 0 and b["replay"] == "true"
        # Bazno skladište, ISTOVREMENO u dva procesa: tačno jedno izvršavanje.
        kljuc = K()
        p1, p2 = _proces("pg", pgdb, kljuc, 2.0, d), _proces("pg", pgdb, kljuc, 2.0, d)
        x, y = _sacekaj(p1), _sacekaj(p2)
        assert x["model"] + y["model"] == 1 and x["kredit"] + y["kredit"] == 1
        assert sorted([x["status"], y["status"]]) == [200, 409]
        # Negativna kontrola: memorija procesa NE vidi ključ drugog procesa → dvostruko izvršavanje.
        kljuc = K()
        m1 = _sacekaj(_proces("mem", None, kljuc, 0, d))
        m2 = _sacekaj(_proces("mem", None, kljuc, 0, d))
        assert m1["model"] + m2["model"] == 2, "memorijsko rešenje bi ovde moralo da padne (dvostruko izvršavanje)"
