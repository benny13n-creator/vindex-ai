"""NS006 Task 1 — python-jose CVE-2026-85394 protiv STVARNOG Vindex verifikatora.

CVE: python-jose ≤3.5.0 prihvata DER javni ključ kao HMAC tajnu. Napadač koji ima
javni ključ servisa može da potpiše HS256 token tim ključem — ako verifikator
poziva `jwt.decode(token, JAVNI_KLJUČ, algorithms=[..."HS256"...])`.

Vindex ima DVA verifikatora (api.py::_verify_token i shared/deps.py::
verify_token_local/_verify_token). Ovaj test ih napada direktno, sa SDK putem koji
pada (kao kad Supabase nije dostupan), u svim oblicima javnog ključa koje
napadač može da dobije: PEM, DER (oblik iz CVE-a), JWK JSON, sirov x||y.

Pozitivna kontrola: pravi HS256 token potpisan tajnom PROLAZI — test nije prazan.
Kontrola osetljivosti: ranjiva konfiguracija (DER javni ključ + HS256) mora da
PRIHVATI falsifikat na ovoj verziji biblioteke — inače test ne bi umeo da vidi napad.
"""
import base64
import hashlib
import hmac
import json
import os
import time

# Lažne vrednosti (samo ako nisu postavljene) — api.py ih traži pri uvozu (isto kao ns005_harness).
for _k, _v in (("OPENAI_API_KEY", "sk-fake-ns006"), ("PINECONE_API_KEY", "fake-pinecone"),
               ("PINECONE_HOST", "https://fake.pinecone.io")):
    os.environ.setdefault(_k, _v)

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from shared import deps

JWK = deps._JWKS_HARDCODED


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _javni_kljuc():
    x, y = int.from_bytes(_b64u_dec(JWK["x"]), "big"), int.from_bytes(_b64u_dec(JWK["y"]), "big")
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def _oblici_javnog_kljuca() -> dict[str, bytes]:
    pub = _javni_kljuc()
    return {
        "pem": pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo),
        "der": pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo),
        "jwk_json": json.dumps(JWK).encode(),
        "xy": _b64u_dec(JWK["x"]) + _b64u_dec(JWK["y"]),
    }


def _token(header: dict, kljuc: bytes, sub: str = "napadac-0000") -> str:
    payload = {"sub": sub, "email": "napadac@example.com", "role": "authenticated", "exp": int(time.time()) + 3600}
    ulaz = _b64u(json.dumps(header).encode()) + "." + _b64u(json.dumps(payload).encode())
    potpis = hmac.new(kljuc, ulaz.encode(), hashlib.sha256).digest()
    return ulaz + "." + _b64u(potpis)


def _falsifikati() -> dict[str, str]:
    out = {}
    for ime, k in _oblici_javnog_kljuca().items():
        out[f"hs256/{ime}"] = _token({"alg": "HS256", "typ": "JWT"}, k)
        out[f"es256-zaglavlje/{ime}"] = _token({"alg": "ES256", "typ": "JWT", "kid": JWK["kid"]}, k)
        out[f"rs256-zaglavlje/{ime}"] = _token({"alg": "RS256", "typ": "JWT"}, k)
    ulaz = _b64u(json.dumps({"alg": "none", "typ": "JWT"}).encode()) + "." + _b64u(json.dumps({"sub": "napadac-0000"}).encode())
    out["none"] = ulaz + "."
    return out


@pytest.fixture
def bez_sdk(monkeypatch):
    """SDK `get_user` pada -> verifikator ide na lokalni decode (put koji CVE napada).
    JWKS se ne dohvata sa mreže: keš se puni hardkodovanim javnim ključem."""
    class _Pada:
        class auth:
            @staticmethod
            def get_user(_t):
                raise RuntimeError("SDK nedostupan (test)")
    monkeypatch.setattr(deps, "_get_supa", lambda: _Pada())
    monkeypatch.setitem(deps._JWKS_CACHE, "keys", [JWK])
    monkeypatch.setitem(deps._JWKS_CACHE, "fetched_at", 10 ** 12)
    import api
    monkeypatch.setattr(api, "_get_supa", lambda: _Pada())
    monkeypatch.setitem(api._jwks_cache, "keys", [JWK])
    monkeypatch.setitem(api._jwks_cache, "fetched_at", 10 ** 12)
    return api


@pytest.mark.parametrize("ime", sorted(_falsifikati()))
def test_falsifikat_odbijen_u_svim_verifikatorima(bez_sdk, ime):
    api = bez_sdk
    t = _falsifikati()[ime]
    assert deps.verify_token_local(t) is None, ime
    assert deps._verify_token(t) is None, ime
    assert api._verify_token(t) is None, ime


def test_pozitivna_kontrola_pravi_token_prolazi(bez_sdk):
    api = bez_sdk
    t = _token({"alg": "HS256", "typ": "JWT"}, deps.SUPABASE_JWT_SECRET.encode(), sub="pravi-korisnik")
    assert (deps.verify_token_local(t) or {}).get("sub") == "pravi-korisnik"
    assert (api._verify_token(t) or {}).get("sub") == "pravi-korisnik"


def test_kontrola_osetljivosti_ranjiva_konfiguracija_bi_prihvatila():
    """Na instaliranoj python-jose verziji, RANJIVA konfiguracija (javni DER ključ kao
    HMAC tajna) prihvata falsifikat. Ako ovo jednog dana padne (biblioteka ispravljena),
    test iznad i dalje važi; ovaj samo dokazuje da napad nije izmišljen."""
    from jose import jwt as jose_jwt
    der = _oblici_javnog_kljuca()["der"]
    t = _token({"alg": "HS256", "typ": "JWT"}, der)
    try:
        payload = jose_jwt.decode(t, der, algorithms=["HS256"], options={"verify_aud": False})
    except Exception as exc:  # biblioteka je u međuvremenu ispravljena
        pytest.skip(f"python-jose više ne prihvata DER kao HMAC tajnu: {type(exc).__name__}")
    assert payload["sub"] == "napadac-0000"
