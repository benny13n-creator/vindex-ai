# -*- coding: utf-8 -*-
"""JWT-RISK-001 — matrica sintetičkih napada (CVE-2026-85394, python-jose ≤3.5.0) protiv SVIH dostižnih Vindex
verifikatora, uz pozitivne kontrole (pravi tokeni prolaze — univerzalno odbijanje se ne računa kao uspeh).

Verifikatori (inventar u docs/v2-recovery/JWT_RISK_001_FINAL_ASSESSMENT.md):
  api._verify_token (+ _verify_via_live_jwks) — api.get_current_user, _require_auth
  shared.deps._verify_token — shared.deps.get_current_user (routeri, permissions.require), WebSocket voice_realtime
  shared.deps.verify_token_local — rate-limit middleware (bucketing) i korak 2 iznad
SDK korak (`supa.auth.get_user`) pada u napadima (kao kad Supabase odbije/nije dostupan) → lokalni decode je ono
što CVE napada. Ključevi su SINTETIČKI (generisani u testu); produkcioni JAVNI ključ se koristi samo kao materijal
napadača. Ništa ne ide ka mreži ni ka produkciji.
"""
import base64
import hashlib
import hmac
import json
import os
import time

for _k, _v in (("OPENAI_API_KEY", "sk-fake-jwt001"), ("PINECONE_API_KEY", "fake-pinecone"),
               ("PINECONE_HOST", "https://fake.pinecone.io")):
    os.environ.setdefault(_k, _v)

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from shared import deps

PROD_JWK = dict(deps._JWKS_HARDCODED)          # javni produkcioni ključ (javno objavljen)
IZVESTAJ = os.environ.get("JWT001_IZVESTAJ")


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _int_b64(n: int, duzina: int | None = None) -> str:
    duzina = duzina or (n.bit_length() + 7) // 8
    return _b64u(n.to_bytes(duzina, "big"))


# ── sintetički ključevi ─────────────────────────────────────────────────────────────────────────────────────
EC_PRIV = ec.generate_private_key(ec.SECP256R1())
RSA_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_ecn = EC_PRIV.public_key().public_numbers()
_rsn = RSA_PRIV.public_key().public_numbers()
EC_JWK = {"kty": "EC", "alg": "ES256", "crv": "P-256", "use": "sig", "kid": "sint-ec",
          "x": _int_b64(_ecn.x, 32), "y": _int_b64(_ecn.y, 32)}
RSA_JWK = {"kty": "RSA", "alg": "RS256", "use": "sig", "kid": "sint-rsa", "e": _int_b64(_rsn.e), "n": _int_b64(_rsn.n)}
EC_PEM_PRIV = EC_PRIV.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
RSA_PEM_PRIV = RSA_PRIV.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
TAJNA = "sintetička-hs256-tajna-za-test-jwt-risk-001-dugacka"


def _prod_pub():
    x, y = int.from_bytes(_b64u_dec(PROD_JWK["x"]), "big"), int.from_bytes(_b64u_dec(PROD_JWK["y"]), "big")
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def _oblici(pub, jwk) -> dict:
    return {
        "pem": pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo),
        "der": pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo),
        "der_pkcs1": (pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.PKCS1)
                      if isinstance(pub, rsa.RSAPublicKey) else None),
        "jwk_json": json.dumps(jwk).encode(),
    }


def _claims(**izmene):
    c = {"sub": "napadac-0000", "email": "napadac@example.com", "role": "authenticated", "aud": "authenticated",
         "exp": int(time.time()) + 3600}
    c.update(izmene)
    return {k: v for k, v in c.items() if v is not None}


def _hmac_tok(header: dict, kljuc: bytes, claims=None) -> str:
    ulaz = _b64u(json.dumps(header).encode()) + "." + _b64u(json.dumps(claims or _claims()).encode())
    return ulaz + "." + _b64u(hmac.new(kljuc, ulaz.encode(), hashlib.sha256).digest())


def _sirov(header: dict, claims=None, potpis: str = "") -> str:
    return _b64u(json.dumps(header).encode()) + "." + _b64u(json.dumps(claims or _claims()).encode()) + "." + potpis


def _es(claims=None, kid="sint-ec", alg="ES256"):
    return jose_jwt.encode(claims or _claims(sub="pravi-ec"), EC_PEM_PRIV, algorithm=alg, headers={"kid": kid} if kid else None)


def _rs(claims=None, kid="sint-rsa", alg="RS256"):
    return jose_jwt.encode(claims or _claims(sub="pravi-rsa"), RSA_PEM_PRIV, algorithm=alg, headers={"kid": kid} if kid else None)


def _hs(claims=None, alg="HS256"):
    return jose_jwt.encode(claims or _claims(sub="pravi-hs"), TAJNA, algorithm=alg)


# ── slučajevi: (ime, token, sme_da_prođe) ────────────────────────────────────────────────────────────────────
def slucajevi() -> list[tuple[str, str, bool]]:
    s: list[tuple[str, str, bool]] = []
    # 1–5: javni ključ (RSA/EC, PEM/DER/JWK) kao HMAC tajna, pod raznim zaglavljima
    materijal = {"prod_ec": (_prod_pub(), PROD_JWK), "sint_ec": (EC_PRIV.public_key(), EC_JWK),
                 "sint_rsa": (RSA_PRIV.public_key(), RSA_JWK)}
    for mime, (pub, jwk) in materijal.items():
        for oblik, k in _oblici(pub, jwk).items():
            if k is None:
                continue
            for hdr in ({"alg": "HS256"}, {"alg": "HS256", "kid": jwk["kid"]}, {"alg": "ES256", "kid": jwk["kid"]},
                        {"alg": "RS256", "kid": jwk["kid"]}):
                s.append((f"1-5 hmac[{mime}/{oblik}] hdr={hdr['alg']}{'+kid' if 'kid' in hdr else ''}",
                          _hmac_tok({**hdr, "typ": "JWT"}, k), False))
    # 6: konfuzija algoritma kroz zaglavlje (potpis tajnom, ali drugi alg / oblik)
    for a in ("HS384", "HS512", "hs256", "Hs256", "ES384", "PS256", "EdDSA"):
        s.append((f"6 hdr alg={a} (HMAC tajnom)", _hmac_tok({"alg": a, "typ": "JWT"}, TAJNA.encode()), False))
    s.append(("6 hdr alg=[HS256,ES256] (lista)", _hmac_tok({"alg": ["HS256", "ES256"]}, TAJNA.encode()), False))
    s.append(("6 hdr alg=ES256 potpisan HMAC tajnom", _hmac_tok({"alg": "ES256", "kid": "sint-ec"}, TAJNA.encode()), False))
    s.append(("6 hdr alg=RS256 a potpisan EC ključem", _sirov({"alg": "RS256", "kid": "sint-ec"},
                                                             potpis=_es().split(".")[2]), False))
    # 7: alg=none
    for a in ("none", "None", "NONE"):
        s.append((f"7 alg={a}", _sirov({"alg": a, "typ": "JWT"}), False))
        s.append((f"7 alg={a} + lažan potpis", _sirov({"alg": a}, potpis="AAAA"), False))
    # 8: nedostaje / pokvaren alg
    s.append(("8 bez alg, HMAC prod javnim DER", _hmac_tok({"typ": "JWT"}, _oblici(_prod_pub(), PROD_JWK)["der"]), False))
    s.append(("8 bez alg, HMAC tajnom (pravi potpis)", _hmac_tok({"typ": "JWT"}, TAJNA.encode()), False))
    s.append(("8 alg=null", _hmac_tok({"alg": None}, TAJNA.encode()), False))
    s.append(("8 zaglavlje nije JSON", "bm90LWpzb24." + _b64u(json.dumps(_claims()).encode()) + ".AAAA", False))
    s.append(("8 dva dela", "a.b", False))
    s.append(("8 prazan token", "", False))
    # 9–11: kid
    s.append(("9 ES256 bez kid (pravi potpis)", _es(kid=None), True))
    s.append(("10 ES256 nepoznat kid (pravi potpis)", _es(kid="nepoznat"), True))
    s.append(("11 ES256 kid produkcionog ključa, potpis sint. ključem", _es(kid=PROD_JWK["kid"]), True))
    s.append(("11 RS256 kid=sint-ec (pogrešan kid)", _rs(kid="sint-ec"), True))
    s.append(("9-11 ES256 potpisan NEPOZNATIM ključem, kid=sint-ec",
              jose_jwt.encode(_claims(), ec.generate_private_key(ec.SECP256R1()).private_bytes(
                  serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
                  algorithm="ES256", headers={"kid": "sint-ec"}), False))
    # 16–18
    s.append(("16 HS256 istekao", _hs(_claims(exp=int(time.time()) - 60)), False))
    s.append(("16 ES256 istekao", _es(_claims(exp=int(time.time()) - 60)), False))
    s.append(("16 nbf u budućnosti", _hs(_claims(nbf=int(time.time()) + 3600)), False))
    t = _hs()
    s.append(("17 HS256 izmenjen potpis", t[:-4] + ("AAAA" if not t.endswith("AAAA") else "BBBB"), False))
    t = _es()
    s.append(("17 ES256 izmenjen payload (sub)", t.split(".")[0] + "." + _b64u(json.dumps(_claims(sub="tudji")).encode())
              + "." + t.split(".")[2], False))
    s.append(("18 HS256 bez sub", _hs(_claims(sub=None)), False))
    s.append(("18 ES256 bez sub", _es(_claims(sub=None)), False))
    s.append(("18 HS256 sub prazan", _hs(_claims(sub="")), False))
    # pozitivne kontrole
    s.append(("POZ HS256 tajnom", _hs(), True))
    s.append(("POZ ES256 sint. ključem", _es(), True))
    s.append(("POZ RS256 sint. ključem", _rs(), True))
    return s


SLUCAJEVI = slucajevi()


class _SdkPada:
    class auth:
        @staticmethod
        def get_user(_t):
            raise RuntimeError("SDK odbio (test)")


@pytest.fixture
def okruzenje(monkeypatch):
    """Lokalni verifikatori sa SINTETIČKOM HS tajnom i JWKS-om [EC, RSA]. api._verify_token zadržava produkcioni
    ugrađeni ES256 ključ (napadač nema privatni) → pozitivna ES/RS kontrola prolazi kroz `_verify_via_live_jwks`."""
    import api
    monkeypatch.setattr(deps, "SUPABASE_JWT_SECRET", TAJNA)
    monkeypatch.setattr(api, "SUPABASE_JWT_SECRET", TAJNA)
    monkeypatch.setattr(deps, "_get_supa", lambda: _SdkPada())
    monkeypatch.setattr(api, "_get_supa", lambda: _SdkPada())
    kljucevi = [dict(EC_JWK), dict(RSA_JWK)]
    for kes in (deps._JWKS_CACHE, api._jwks_cache):
        monkeypatch.setitem(kes, "keys", kljucevi)
        monkeypatch.setitem(kes, "fetched_at", 10 ** 12)
    monkeypatch.setattr(deps.time if hasattr(deps, "time") else deps, "__jwt001__", True, raising=False)
    import time as _t
    monkeypatch.setattr(_t, "monotonic", lambda: 10 ** 12 + 1)   # deps keš „svež“
    return api


def _verifikatori(api):
    return {
        "api._verify_token": api._verify_token,
        "deps._verify_token": deps._verify_token,
        "deps.verify_token_local": deps.verify_token_local,
    }


# NALAZ F1 (funkcionalni, nije bezbednosni): shared.deps._get_jwks_key vraća PRVI ključ sa kty EC/RSA bez obzira na
# `alg`, pa uz JWKS [EC, RSA] RS256 token u deps nikad ne prolazi (lažno odbijanje). Produkcioni JWKS ima samo EC/ES256.
DEPS_RS256_LAZNO_ODBIJA = {"deps._verify_token", "deps.verify_token_local"}


def _ocekivano(ime, sme, vime):
    if sme and "RS256" in ime and vime in DEPS_RS256_LAZNO_ODBIJA:
        return False
    return sme


def _izvrsi(fn, tok):
    try:
        r = fn(tok)
        return ("PRIHVAĆEN:" + str(r.get("sub"))) if r else "odbijen"
    except Exception as e:                 # izuzetak nije prihvatanje; beleži se kao defekt obrade grešaka
        return "IZUZETAK:" + type(e).__name__


def test_matrica_napada_i_pozitivnih_kontrola(okruzenje):
    api = okruzenje
    rezultati, lazno_prihvaceni, lazno_odbijeni, izuzeci = [], [], [], []
    for ime, tok, sme0 in SLUCAJEVI:
        for vime, fn in _verifikatori(api).items():
            sme = _ocekivano(ime, sme0, vime)
            ishod = _izvrsi(fn, tok)
            rezultati.append({"slucaj": ime, "verifikator": vime, "ocekivano": "prihvaćen" if sme else "odbijen",
                              "ishod": ishod})
            prihvacen = ishod.startswith("PRIHVAĆEN")
            if prihvacen and not sme:
                lazno_prihvaceni.append((ime, vime, ishod))
            if sme and not prihvacen:
                lazno_odbijeni.append((ime, vime, ishod))
            if ishod.startswith("IZUZETAK"):
                izuzeci.append((ime, vime, ishod))
    if IZVESTAJ:
        with open(IZVESTAJ, "w", encoding="utf-8") as f:
            json.dump(rezultati, f, ensure_ascii=False, indent=1)
    assert lazno_prihvaceni == [], lazno_prihvaceni            # HARD FAIL kriterijum
    assert lazno_odbijeni == [], lazno_odbijeni                # pozitivne kontrole moraju proći
    assert izuzeci == [], izuzeci


def test_sdk_putanja_prihvata_samo_ono_sto_server_potvrdi(okruzenje, monkeypatch):
    """SDK korak: identitet dolazi iz odgovora Supabase Auth servera (`resp.user`), ne iz tokena. Kad server odbije,
    lokalni korak važi isto kao gore; kad prihvati, `sub` je serverov, ne iz falsifikovanog tokena."""
    api = okruzenje

    class _SdkPrihvata:
        class auth:
            @staticmethod
            def get_user(_t):
                class U:
                    id, email = "server-korisnik", "s@example.com"
                return type("R", (), {"user": U})()
    monkeypatch.setattr(deps, "_get_supa", lambda: _SdkPrihvata())
    monkeypatch.setattr(api, "_get_supa", lambda: _SdkPrihvata())
    falsifikat = _hmac_tok({"alg": "HS256"}, b"bilo-sta", _claims(sub="napadac-hoće-ovo"))
    for fn in (api._verify_token, deps._verify_token):
        assert fn(falsifikat)["sub"] == "server-korisnik"


# ── JWKS nedostupan / pokvaren — STVARNI put dohvatanja (mreža zamenjena) ──────────────────────────────────────
@pytest.mark.parametrize("kvar", ["mreza_pada", "nije_json", "keys_nije_lista", "kljuc_smece", "prazan"])
def test_jwks_nedostupan_ili_pokvaren_fail_closed(monkeypatch, kvar):
    import api
    import requests
    import urllib.request as ur
    monkeypatch.setattr(deps, "SUPABASE_JWT_SECRET", TAJNA)
    monkeypatch.setattr(api, "SUPABASE_JWT_SECRET", TAJNA)
    monkeypatch.setattr(deps, "_get_supa", lambda: _SdkPada())
    monkeypatch.setattr(api, "_get_supa", lambda: _SdkPada())
    monkeypatch.setattr(deps, "SUPABASE_URL", "https://primer.invalid")
    monkeypatch.setattr(api, "SUPABASE_URL", "https://primer.invalid")
    for kes in (deps._JWKS_CACHE, api._jwks_cache):
        monkeypatch.setitem(kes, "keys", None)
        monkeypatch.setitem(kes, "fetched_at", 0.0)
    telo = {"nije_json": b"<html>", "keys_nije_lista": b'{"keys": "x"}', "kljuc_smece": b'{"keys": [{"kty": "EC"}, 5]}',
            "prazan": b'{"keys": []}'}.get(kvar)

    class _Odg:
        def __init__(self, b): self.b = b
        def read(self): return self.b
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def json(self): return json.loads(self.b)

    def _urlopen(*a, **k):
        if telo is None:
            raise OSError("mreža pada (test)")
        return _Odg(telo)

    def _get(*a, **k):
        if telo is None:
            raise requests.ConnectionError("mreža pada (test)")
        return _Odg(telo)
    monkeypatch.setattr(ur, "urlopen", _urlopen)
    monkeypatch.setattr(requests, "get", _get)
    napadi = [t for ime, t, sme in SLUCAJEVI if not sme]
    for tok in napadi + [_es(), _rs()]:           # ni sint. ES/RS: JWKS nema njihov ključ → odbijeni
        for vime, fn in _verifikatori(api).items():
            ishod = _izvrsi(fn, tok)
            assert not ishod.startswith("PRIHVAĆEN"), (kvar, vime, ishod)
    assert (deps.verify_token_local(_hs()) or {}).get("sub") == "pravi-hs"     # HS256 i dalje radi (kontrola)


# ── kty/alg nepodudaranje u JWKS-u ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ime,jwks", [
    ("ec_kljuc_alg_RS256", [{**EC_JWK, "alg": "RS256"}]),
    ("rsa_kljuc_alg_ES256", [{**RSA_JWK, "alg": "ES256"}]),
    ("ec_kljuc_alg_HS256", [{**EC_JWK, "alg": "HS256"}]),
    ("ec_bez_alg", [{k: v for k, v in EC_JWK.items() if k != "alg"}]),
    ("oct_kljuc_alg_ES256", [{"kty": "oct", "alg": "ES256", "kid": "oct", "k": _b64u(b"tajna-iz-jwks")}]),
    ("oct_bez_alg", [{"kty": "oct", "kid": "oct", "k": _b64u(b"tajna-iz-jwks")}]),
    ("ec_plus_oct", [dict(EC_JWK), {"kty": "oct", "alg": "HS256", "kid": "oct", "k": _b64u(b"tajna-iz-jwks")}]),
])
def test_jwks_kty_alg_nepodudaranje_ne_prihvata_falsifikat(monkeypatch, ime, jwks):
    import api
    monkeypatch.setattr(deps, "SUPABASE_JWT_SECRET", TAJNA)
    monkeypatch.setattr(api, "SUPABASE_JWT_SECRET", TAJNA)
    monkeypatch.setattr(deps, "_get_supa", lambda: _SdkPada())
    monkeypatch.setattr(api, "_get_supa", lambda: _SdkPada())
    import time as _t
    monkeypatch.setattr(_t, "monotonic", lambda: 10 ** 12 + 1)
    for kes in (deps._JWKS_CACHE, api._jwks_cache):
        monkeypatch.setitem(kes, "keys", jwks)
        monkeypatch.setitem(kes, "fetched_at", 10 ** 12)
    napadi = [(n, t) for n, t, sme in SLUCAJEVI if not sme]
    napadi.append(("hmac tajnom iz oct ključa, hdr ES256", _hmac_tok({"alg": "ES256", "kid": "oct"}, b"tajna-iz-jwks")))
    napadi.append(("hmac tajnom iz oct ključa, hdr RS256", _hmac_tok({"alg": "RS256", "kid": "oct"}, b"tajna-iz-jwks")))
    for n, tok in napadi:
        for vime, fn in _verifikatori(api).items():
            ishod = _izvrsi(fn, tok)
            assert not ishod.startswith("PRIHVAĆEN"), (ime, n, vime, ishod)


def test_nalaz_f2_jwks_samo_sa_simetricnim_kljucem(okruzenje):
    """NALAZ F2 (ojačavanje; van produkcione konfiguracije). Ako bi JWKS sadržao ISKLJUČIVO simetričan ključ
    (kty=oct, alg=HS256), shared.deps (rezerva `keys[0]` u `_get_jwks_key`) prihvata token sa zaglavljem ES256/RS256
    potpisan HMAC-om tim ključem: python-jose proverava `alg` iz zaglavlja, a potpis algoritmom OBJEKTA ključa.
    api.py odbija. Produkcioni JWKS (izmereno 2026-10-11) ima samo EC/ES256; napadač koji kontroliše JWKS već može da
    podmetne svoj EC ključ, pa ovo ne daje novu sposobnost. Test zaključava SADAŠNJE ponašanje — posle ispravke
    (odbaciti ključ čiji kty ne odgovara porodici algoritma, bez `keys[0]` rezerve) treba ga obrnuti."""
    api = okruzenje
    oct = {"kty": "oct", "alg": "HS256", "kid": "oct", "k": _b64u(b"tajna-iz-jwks")}
    for kes in (deps._JWKS_CACHE, api._jwks_cache):
        kes["keys"] = [oct]
        kes["fetched_at"] = 10 ** 12
    for hdr in ("ES256", "RS256"):
        tok = _hmac_tok({"alg": hdr, "kid": "oct"}, b"tajna-iz-jwks")
        assert _izvrsi(api._verify_token, tok) == "odbijen"
        assert _izvrsi(lambda t: api._verify_via_live_jwks(t, hdr), tok) == "odbijen"
        assert _izvrsi(deps.verify_token_local, tok).startswith("PRIHVAĆEN")     # sadašnje ponašanje (F2)
        assert _izvrsi(deps._verify_token, tok).startswith("PRIHVAĆEN")


# ── HTTP i WebSocket granica (stvarne zavisnosti) ──────────────────────────────────────────────────────────────
def test_http_zavisnosti_falsifikat_401_pravi_token_200(okruzenje):
    api = okruzenje
    app = FastAPI()

    @app.get("/deps")
    async def _d(u: dict = Depends(deps.get_current_user)):
        return {"id": u.get("user_id") or u.get("sub")}

    @app.get("/api")
    async def _a(u=Depends(api.get_current_user)):
        return {"id": (u.get("user_id") or u.get("sub")) if isinstance(u, dict) else getattr(u, "id", None)}

    k = TestClient(app, raise_server_exceptions=False)
    for ime, tok, sme in SLUCAJEVI:
        if not tok:
            continue
        for put in ("/deps", "/api"):
            r = k.get(put, headers={"Authorization": "Bearer " + tok})
            if sme and put == "/deps" and "RS256" in ime:      # F1
                sme_ovde = False
            else:
                sme_ovde = sme
            if sme_ovde:
                assert r.status_code == 200, (ime, put, r.status_code, r.text[:200])
            else:
                assert r.status_code in (401, 403), (ime, put, r.status_code, r.text[:200])


def test_websocket_glas_odbija_falsifikat(okruzenje):
    api = okruzenje
    from starlette.websockets import WebSocketDisconnect
    k = TestClient(api.app)
    for ime, tok, sme in SLUCAJEVI:
        if sme or not tok:
            continue
        with pytest.raises(WebSocketDisconnect) as ex:
            with k.websocket_connect(f"/api/voice/realtime/ws?token={tok}") as ws:
                ws.receive_text()
        assert ex.value.code == 4401, (ime, ex.value.code)   # routers/voice_realtime._POLICY_VIOLATION_CODE


# ── reprodukcija ranjivog ponašanja (namerno nebezbedna konfiguracija) ─────────────────────────────────────────
@pytest.mark.parametrize("mime", ["prod_ec", "sint_ec", "sint_rsa"])
def test_ranjiva_konfiguracija_reprodukuje_cve_der(mime):
    """Kontrola osetljivosti: `decode(token, JAVNI_DER, algorithms=["HS256"])` — oblik iz CVE-a — PRIHVATA falsifikat
    na instaliranoj python-jose. PEM oblik biblioteka odbija (stara CVE-2024-33663 zakrpa). Vindex ovakav poziv nema."""
    pub, jwk = {"prod_ec": (_prod_pub(), PROD_JWK), "sint_ec": (EC_PRIV.public_key(), EC_JWK),
                "sint_rsa": (RSA_PRIV.public_key(), RSA_JWK)}[mime]
    o = _oblici(pub, jwk)
    tok = _hmac_tok({"alg": "HS256"}, o["der"])
    try:
        assert jose_jwt.decode(tok, o["der"], algorithms=["HS256"], options={"verify_aud": False})["sub"] == "napadac-0000"
    except Exception as e:
        pytest.skip(f"python-jose više ne prihvata DER kao HMAC tajnu: {type(e).__name__}")
    with pytest.raises(Exception):
        jose_jwt.decode(_hmac_tok({"alg": "HS256"}, o["pem"]), o["pem"], algorithms=["HS256"], options={"verify_aud": False})
