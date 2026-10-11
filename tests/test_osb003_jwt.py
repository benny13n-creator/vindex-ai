# -*- coding: utf-8 -*-
"""OSB003 Task 4 — python-jose CVE-2026-85394 pod varijantama JWKS-a koje NS006 test ne pokriva.

Verifikatori: api.py::_verify_token (+ _verify_via_live_jwks), shared/deps.py::verify_token_local / _verify_token.
Varijante JWKS-a: (1) produkcioni oblik (EC/ES256 sa `alg`), (2) isti ključ BEZ `alg`, (3) ključ sa `alg=HS256`
(van testiranih invarijanti — kompromitovan/izmenjen JWKS), (4) EC ključ + nepovezan RSA ključ.
Ni u jednoj varijanti falsifikat ne sme biti prihvaćen, a kroz HTTP mora dati 401, ne 500.
"""
import copy

import pytest
from fastapi.testclient import TestClient

from shared import deps
from tests.test_ns006_t1_jwt_alg_confusion import JWK, _falsifikati

_RSA = {"kty": "RSA", "alg": "RS256", "use": "sig", "kid": "rsa-x", "e": "AQAB",
        "n": "sXchDaQebHnPiGvyDOAT4saGEUetSyo9MKLOoWFsueri23bOdgWp4Dy1WlUzewbgBHod5pcM9H95GQRV3JDXboIRROSBigeC5yjU1hGzHHyXss8UDprecbAYxknTcQkhslANGRUZmdTOQ5qTRsLAt6BTYuyvVRdhS8exSZEy_c4gs_7svlJJQ4H9_NxsiIoLwAEk7-Q3UXERGYw_75IDrGA84-lA_-Ct4eTlXHBIY2EaV7t7LjJaynVJCpkv4LKjTTAumiGUIuQhrNhZLuF_RJLqHpM2kgWFLU7-VTdL1VbC2tejvcI2BlMkEpk1BzBZI0KQB0GaDWFLN-aEAw3vRw"}
JWKS = {
    "produkcija_es256": [JWK],
    "bez_alg": [{k: v for k, v in JWK.items() if k != "alg"}],
    "alg_hs256_van_invarijanti": [{**JWK, "alg": "HS256"}],
    "ec_plus_rsa": [_RSA, JWK],
}


class _Pada:
    class auth:
        @staticmethod
        def get_user(_t):
            raise RuntimeError("SDK nedostupan (test)")


@pytest.fixture(params=sorted(JWKS))
def jwks(request, monkeypatch):
    kljucevi = copy.deepcopy(JWKS[request.param])
    import api
    monkeypatch.setattr(deps, "_get_supa", lambda: _Pada())
    monkeypatch.setitem(deps._JWKS_CACHE, "keys", kljucevi)
    monkeypatch.setitem(deps._JWKS_CACHE, "fetched_at", 10 ** 12)
    monkeypatch.setattr(api, "_get_supa", lambda: _Pada())
    monkeypatch.setitem(api._jwks_cache, "keys", kljucevi)
    monkeypatch.setitem(api._jwks_cache, "fetched_at", 10 ** 12)
    return request.param, api


def _verifikatori(api):
    return {"api._verify_token": api._verify_token, "api._verify_via_live_jwks/ES256": lambda t: api._verify_via_live_jwks(t, "ES256"),
            "api._verify_via_live_jwks/RS256": lambda t: api._verify_via_live_jwks(t, "RS256"),
            "deps.verify_token_local": deps.verify_token_local, "deps._verify_token": deps._verify_token}


def test_nijedan_falsifikat_nije_prihvacen_ni_u_jednoj_varijanti_jwks(jwks):
    varijanta, api = jwks
    prihvaceni, izuzeci = [], []
    for fime, tok in _falsifikati().items():
        for vime, fn in _verifikatori(api).items():
            try:
                r = fn(tok)
            except Exception as e:      # izuzetak NIJE prihvatanje; beleži se zbog 500 provere ispod
                izuzeci.append((fime, vime, type(e).__name__))
                continue
            if r:
                prihvaceni.append((fime, vime))
    assert prihvaceni == [], (varijanta, prihvaceni)


def test_falsifikat_kroz_http_daje_401_ne_500(jwks):
    varijanta, api = jwks
    k = TestClient(api.app, raise_server_exceptions=False)
    statusi = {}
    for fime, tok in _falsifikati().items():
        for put in ("/api/predmeti", "/api/workspace"):
            r = k.get(put, headers={"Authorization": "Bearer " + tok})
            statusi[(fime, put)] = r.status_code
    lose = {x: s for x, s in statusi.items() if s not in (401, 403)}
    assert lose == {}, (varijanta, lose)
