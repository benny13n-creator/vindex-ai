# -*- coding: utf-8 -*-
"""
PRG-P1-NIGHT-001 / T10 — `POST /api/register` je radio tacno JEDNOM po procesu.

Uzrok (dokazan izvrsavanjem nad stvarnim Supabase-om, ne citanjem):
`supabase/_sync/client.py::_listen_to_auth_events` na dogadjaj SIGNED_IN radi

    self.options.headers["Authorization"] = auth_header
    self.auth._headers["Authorization"]   = auth_header

a `auth._headers` JE ISTI OBJEKAT kao `auth.admin._headers`. Posto `register`
zove `sign_in_with_password` na procesnom singltonu `_get_supa()`, prvi uspesan
register truje taj singlton korisnikovim JWT-om. Od tog trenutka:

  * `admin.create_user` salje korisnicki token -> AuthApiError "User not allowed"
    -> generic except -> HTTP 500 za SVAKU sledecu registraciju na tom radniku;
  * `_postgrest` se nulira i svaki sledeci upit ide kao TAJ korisnik. Izmereno
    nad stvarnom bazom: profiles 3->1 reda, predmeti 3->0, klijenti 3->0.
    Drugi advokati koje opsluzi taj radnik vide PRAZNE predmete i klijente.

Laznjaci ispod SPROVODE taj ugovor (deljeni recnik zaglavlja + admin poziv koji
odbija sve sto nije servisni kljuc). Da su „ljubazni", bag ne bi bio vidljiv.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SERVISNI = "servisni-kljuc-sinteticki"


class _AdminAPI:
    """Odbija svaki poziv koji ne nosi servisni kljuc — kao pravi GoTrue admin."""

    def __init__(self, headers, dnevnik):
        self._headers = headers
        self._dnevnik = dnevnik

    def create_user(self, attributes):
        if self._headers.get("Authorization") != f"Bearer {SERVISNI}":
            raise RuntimeError("AuthApiError: User not allowed")
        uid = f"uid-{len(self._dnevnik['kreirani'])}"
        self._dnevnik["kreirani"].append(attributes["email"])
        return type("R", (), {"user": type("U", (), {"id": uid})()})()


class _Auth:
    def __init__(self, dnevnik):
        # KLJUCNO: admin deli ISTI recnik, kao u supabase-py 2.28.3
        self._headers = {"Authorization": f"Bearer {SERVISNI}"}
        self.admin = _AdminAPI(self._headers, dnevnik)
        self._dnevnik = dnevnik

    def sign_in_with_password(self, credentials):
        self._dnevnik["prijave"].append(credentials["email"])
        # `_listen_to_auth_events` na SIGNED_IN prepisuje zaglavlje
        self._headers["Authorization"] = "Bearer korisnicki-jwt"
        sess = type("S", (), {"access_token": "korisnicki-jwt"})()
        return type("R", (), {"session": sess})()


class _Tabela:
    def __init__(self, headers):
        self._headers = headers

    def upsert(self, *a, **k):
        return self

    def execute(self):
        return type("R", (), {"data": []})()


class _Klijent:
    def __init__(self, dnevnik):
        self.auth = _Auth(dnevnik)

    def table(self, ime):
        return _Tabela(self.auth._headers)


def test_deljeni_recnik_zaglavlja_je_stvaran_ugovor_biblioteke():
    """Ako ovo padne, laznjak vise ne opisuje pravu biblioteku i test ne vredi."""
    supabase = pytest.importorskip("supabase")
    cl = supabase.create_client("https://primer.invalid", "lazan")
    assert cl.auth._headers is cl.auth.admin._headers, (
        "supabase-py vise ne deli recnik zaglavlja izmedju auth i admin — "
        "reprodukcija ispod je zastarela, proveri da li je popravka jos potrebna")


@pytest.mark.anyio
async def test_registracija_radi_i_drugi_put(monkeypatch):
    """Dve uzastopne registracije u ISTOM procesu moraju obe uspeti."""
    import api

    dnevnik = {"kreirani": [], "prijave": []}
    klijent = _Klijent(dnevnik)                      # deljeni singlton — JEDAN objekat
    monkeypatch.setattr(api, "_get_supa", lambda: klijent)
    # Svaki `create_client` daje NOV klijent sa SOPSTVENIM recnikom zaglavlja —
    # tako se ponasa i prava biblioteka. Trovanje ostaje u tom kratkotrajnom
    # objektu i ne dodiruje singlton.
    monkeypatch.setattr(api, "create_client", lambda url, key: _Klijent(dnevnik))
    monkeypatch.setattr(api, "_sb_ensure_credits_row", lambda *a, **k: None)
    monkeypatch.setattr(api, "send_welcome_email", lambda *a, **k: None)

    async def _bez_pozadine(*a, **k):
        return None
    monkeypatch.setattr(api, "_setup_trial", _bez_pozadine)
    monkeypatch.setattr("shared.bg.spawn", lambda coro, name=None: coro.close())

    zahtev = type("Req", (), {"client": type("C", (), {"host": "127.0.0.1"})(),
                              "headers": {}})()

    for i in (1, 2):
        req = api.RegisterReq(email=f"sinteticki-{i}@example.com", password="lozinka-123")
        rez = await api.register.__wrapped__(req, zahtev)
        assert rez["status"] == "ok", f"registracija {i} nije uspela: {rez}"
        assert rez["user_id"], f"registracija {i} nije vratila user_id"
        # "ok" bez tokena je lazan uspeh — korisnik ostaje bez sesije.
        assert rez["access_token"], f"registracija {i} vratila 'ok' bez access_token-a"
        assert rez["credits_remaining"] == api.BESPLATNI_KREDITI

    assert dnevnik["kreirani"] == ["sinteticki-1@example.com", "sinteticki-2@example.com"]


def test_prijava_nikad_ne_ide_na_deljeni_singlton():
    """Strukturni katanac nad CELIM produkcionim kodom.

    `sign_in_with_password` postavlja sesiju na klijentu i time prepisuje
    `Authorization` i za `auth.admin` i za PostgREST. Na deljenom `_get_supa()`
    singltonu to obara registraciju i prazni podatke svim korisnicima tog
    radnika. Zato taj poziv sme samo na kratkotrajnom, zasebnom klijentu.
    """
    import io as _io
    import os as _os

    koren = _os.path.join(_os.path.dirname(__file__), "..")
    preskoci = {"tests", "scripts", "data", "docs", "migrations",
                "vindex_scraper_output", "node_modules", ".git", "__pycache__"}
    prekrsaji = []
    for dp, dn, fn in _os.walk(koren):
        dn[:] = [d for d in dn if d not in preskoci and not d.startswith(".")]
        for f in fn:
            if not f.endswith(".py"):
                continue
            put = _os.path.join(dp, f)
            try:
                izvor = _io.open(put, encoding="utf-8").read()
            except Exception:
                continue
            for br, red in enumerate(izvor.splitlines(), 1):
                if "sign_in_with_password" not in red or red.lstrip().startswith("#"):
                    continue
                if "create_client(" in red:      # svez, kratkotrajan klijent — dozvoljeno
                    continue
                prekrsaji.append("%s:%d %s" % (_os.path.relpath(put, koren), br, red.strip()))
    assert not prekrsaji, (
        "prijava se zove na klijentu koji nije svez — to truje Authorization "
        "zaglavlje za ceo proces: " + " | ".join(prekrsaji))


# ── T12: regresija registracije — uspeh nije jedini ugovor ───────────────────

def _postavi(monkeypatch, api, dnevnik, klijent):
    monkeypatch.setattr(api, "_get_supa", lambda: klijent)
    monkeypatch.setattr(api, "create_client", lambda url, key: _Klijent(dnevnik))
    monkeypatch.setattr(api, "send_welcome_email", lambda *a, **k: None)
    monkeypatch.setattr("shared.bg.spawn", lambda coro, name=None: coro.close())
    return type("Req", (), {"client": type("C", (), {"host": "127.0.0.1"})(), "headers": {}})()


@pytest.mark.anyio
async def test_registracija_upisuje_kredite_i_profil(monkeypatch):
    """`status: ok` ne sme da znaci samo 'auth korisnik postoji'."""
    import api
    dnevnik = {"kreirani": [], "prijave": [], "krediti": [], "profili": []}

    class _TabelaP(_Tabela):
        def __init__(self, headers, ime, dnevnik):
            super().__init__(headers)
            self._ime, self._d, self._red = ime, dnevnik, None

        def upsert(self, red, *a, **k):
            self._red = red
            return self

        def execute(self):
            if self._red is not None and self._ime == "profiles":
                self._d["profili"].append(self._red)
            return type("R", (), {"data": []})()

    class _K(_Klijent):
        def table(self, ime):
            return _TabelaP(self.auth._headers, ime, dnevnik)

    klijent = _K(dnevnik)
    monkeypatch.setattr(api, "_sb_ensure_credits_row",
                        lambda uid, n=None: dnevnik["krediti"].append((uid, n)))
    zahtev = _postavi(monkeypatch, api, dnevnik, klijent)

    req = api.RegisterReq(email="upis@example.com", password="lozinka-123")
    rez = await api.register.__wrapped__(req, zahtev)

    assert rez["status"] == "ok"
    assert dnevnik["krediti"], "user_credits red nije kreiran"
    assert dnevnik["krediti"][0][1] == api.BESPLATNI_KREDITI
    assert dnevnik["profili"], "profil nije kreiran"
    assert dnevnik["profili"][0]["email"] == "upis@example.com"


@pytest.mark.anyio
async def test_vec_registrovan_email_daje_409_a_ne_500(monkeypatch):
    import api
    from fastapi import HTTPException
    dnevnik = {"kreirani": [], "prijave": []}

    class _AdminPostojeci(_AdminAPI):
        def create_user(self, attributes):
            raise RuntimeError("User already registered")

    klijent = _Klijent(dnevnik)
    klijent.auth.admin = _AdminPostojeci(klijent.auth._headers, dnevnik)
    zahtev = _postavi(monkeypatch, api, dnevnik, klijent)
    monkeypatch.setattr(api, "_sb_ensure_credits_row", lambda *a, **k: None)

    req = api.RegisterReq(email="postoji@example.com", password="lozinka-123")
    with pytest.raises(HTTPException) as exc:
        await api.register.__wrapped__(req, zahtev)
    assert exc.value.status_code == 409, f"ocekivan 409, dobijen {exc.value.status_code}"


@pytest.mark.anyio
async def test_privremeni_email_odbijen_pre_svakog_upisa(monkeypatch):
    import api
    from fastapi import HTTPException
    dnevnik = {"kreirani": [], "prijave": []}
    klijent = _Klijent(dnevnik)
    zahtev = _postavi(monkeypatch, api, dnevnik, klijent)
    monkeypatch.setattr(api, "_sb_ensure_credits_row", lambda *a, **k: None)

    req = api.RegisterReq(email="neko@mailinator.com", password="lozinka-123")
    with pytest.raises(HTTPException) as exc:
        await api.register.__wrapped__(req, zahtev)
    assert exc.value.status_code == 400
    assert not dnevnik["kreirani"], "korisnik je kreiran uprkos odbijenoj validaciji"


@pytest.mark.anyio
async def test_neuspeh_prijave_ne_sme_da_prodje_kao_uspeh(monkeypatch):
    """Ako `admin.create_user` prodje a prijava padne, to NIJE 'ok'."""
    import api
    from fastapi import HTTPException
    dnevnik = {"kreirani": [], "prijave": []}
    klijent = _Klijent(dnevnik)

    class _PadaPrijava(_Klijent):
        def __init__(self, d):
            super().__init__(d)

            def _pada(_creds):
                raise RuntimeError("AuthApiError: invalid grant")
            self.auth.sign_in_with_password = _pada

    import api as _api
    monkeypatch.setattr(_api, "_get_supa", lambda: klijent)
    monkeypatch.setattr(_api, "create_client", lambda url, key: _PadaPrijava(dnevnik))
    monkeypatch.setattr(_api, "send_welcome_email", lambda *a, **k: None)
    monkeypatch.setattr(_api, "_sb_ensure_credits_row", lambda *a, **k: None)
    monkeypatch.setattr("shared.bg.spawn", lambda coro, name=None: coro.close())
    zahtev = type("Req", (), {"client": type("C", (), {"host": "127.0.0.1"})(), "headers": {}})()

    req = api.RegisterReq(email="prijava-pada@example.com", password="lozinka-123")
    with pytest.raises(HTTPException) as exc:
        await api.register.__wrapped__(req, zahtev)
    assert exc.value.status_code == 500
