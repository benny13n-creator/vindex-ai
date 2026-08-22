# -*- coding: utf-8 -*-
"""B-U-007 — admin/osnivački identitet ne sme da zavisi od korisnički upisivog polja.

PRE-STATE (dokazano živim napadom nad sintetičkim nalogom, 2026-08-22):
  Pet mesta u kodu izvodilo je identitet iz tokena ovako:

      email = (payload.get("email")
               or payload.get("user_metadata", {}).get("email")
               or payload.get("email_claim") or "")

  `user_metadata` piše sam korisnik pozivom `supabase.auth.updateUser({data:…})`.
  Izmereno: običan korisnik je upisao osnivački email i ta vrednost se pojavila
  u POTPISANOM tokenu; stara logika ga je iz takvog payload-a (bez top-level
  `email` claim-a) proglašavala osnivačem.

  Taj `email` ulazi u SVAKU privilegovanu odluku proizvoda — `FOUNDER_EMAILS`,
  `PRO_EMAILS`, `_is_founder`, `_require_admin`, `_require_founder`,
  `_require_cron_or_founder` i `klijenti/permissions.py::_role_from_db`
  (osnivač → PARTNER). AST inventar: **62 privilegovane rute**, ne 18 kako je
  ULTIMATE gate procenio.

INVARIANT: USER-CONTROLLED DATA != TRUSTED IDENTITY.

Popravka je na JEDNOM mestu — `shared/deps.py::email_iz_tokena` — jer je granica
poverenja jedna, a rutā 62.
"""
import ast
import io
import re

import pytest

from shared.deps import email_iz_tokena, _is_founder, _is_pro, FOUNDER_EMAILS, PRO_EMAILS

OSNIVAC = sorted(FOUNDER_EMAILS)[0]
NAPADAC_SUB = "00000000-0000-0000-0000-0000000000aa"
OSNIVAC_SUB = "00000000-0000-0000-0000-0000000000ff"

# Pet mesta koja izvode identitet iz tokena. Svako od njih je granica poverenja
# za sve privilegovane rute koje kroz njega prolaze.
RESOLVERI = [
    ("shared/deps.py", "get_current_user"),
    ("api.py", "get_current_user"),
    ("api.py", "_auth_from_request"),
    ("routers/voice_realtime.py", None),
    ("klijenti/router.py", None),
]


# ── ATTACK A: user_metadata.email podignut na osnivački ──────────────────────

def test_A_user_metadata_email_ne_daje_privilegiju():
    """Tačan payload izmeren nad pravim Supabase nalogom posle
    `updateUser({data: {email: <osnivac>}})`, bez top-level `email` claim-a
    (anonimni/telefonski provajder, ili token bez tog claim-a)."""
    payload = {
        "sub": NAPADAC_SUB,
        "role": "authenticated",
        "user_metadata": {"email": OSNIVAC, "full_name": "Osnivac"},
        "app_metadata": {"provider": "email", "providers": ["email"]},
    }
    email = email_iz_tokena(payload)
    assert email == "", "user_metadata je ušao u identitet: %r" % email
    assert _is_founder(email) is False
    assert _is_pro(email) is False


def test_A2_user_metadata_ne_nadjacava_ni_kad_top_level_postoji():
    payload = {"sub": NAPADAC_SUB, "email": "napadac@primer.rs",
               "user_metadata": {"email": OSNIVAC}}
    assert email_iz_tokena(payload) == "napadac@primer.rs"
    assert _is_founder(email_iz_tokena(payload)) is False


# ── ATTACK B: email iz zahteva (body/query/header) ───────────────────────────

def test_B_email_iz_zahteva_ne_ulazi_u_identitet():
    """Helper prima ISKLJUČIVO verifikovan payload; ništa iz zahteva ne postoji
    kao ulaz. Ovaj test pribija da se takav ulaz ne uvede naknadno."""
    import inspect
    izvor = inspect.getsource(email_iz_tokena)
    for zabranjeno in ("request", "body", "query", "header", "form"):
        assert zabranjeno not in izvor.lower().split('"""')[-1], \
            "helper čita %r — identitet više ne dolazi samo iz tokena" % zabranjeno
    # nestandardni `email_claim` je bio treći fallback i uklonjen je
    assert email_iz_tokena({"sub": NAPADAC_SUB, "email_claim": OSNIVAC}) == ""


# ── ATTACK C: display/profile podaci ─────────────────────────────────────────

def test_C_display_podaci_ne_daju_privilegiju():
    for polje in ("full_name", "name", "preferred_username", "nickname", "profile"):
        payload = {"sub": NAPADAC_SUB, "user_metadata": {polje: OSNIVAC, "email": OSNIVAC}}
        assert _is_founder(email_iz_tokena(payload)) is False, polje


# ── ATTACK D: isti email, drugi authenticated subject ────────────────────────

def test_D_isti_email_drugi_subject():
    """Poklapanje email-a jeste model privilegije ovog proizvoda (`FOUNDER_EMAILS`
    je lista email-ova). Ono što se OVDE dokazuje je da poklapanje mora doći iz
    server-kontrolisanog claim-a: napadač sa svojim `sub` ne može da ga podmetne
    kroz `user_metadata`."""
    napadac = {"sub": NAPADAC_SUB, "user_metadata": {"email": OSNIVAC}}
    pravi = {"sub": OSNIVAC_SUB, "email": OSNIVAC}
    assert _is_founder(email_iz_tokena(napadac)) is False
    assert _is_founder(email_iz_tokena(pravi)) is True


# ── ATTACK E: privilegovani korisnik promeni email ───────────────────────────

def test_E_privilegovani_status_prati_pouzdan_izvor():
    """Status ostaje vezan za `auth.users.email` (server-kontrolisan claim), ne
    za bilo šta što korisnik može da upiše. Promena email-a kroz verifikovan
    Supabase tok menja upravo taj claim — što je namerno i ispravno."""
    pre = {"sub": OSNIVAC_SUB, "email": OSNIVAC}
    assert _is_founder(email_iz_tokena(pre)) is True
    # isti nalog, isti claim, dodato korisničko smeće u user_metadata
    posle = {"sub": OSNIVAC_SUB, "email": OSNIVAC,
             "user_metadata": {"email": "nesto@drugo.rs"}}
    assert _is_founder(email_iz_tokena(posle)) is True, \
        "korisnički upisiv podatak je oduzeo privilegiju pravom osnivaču"


# ── FAIL-CLOSED ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("payload", [
    None, {}, {"sub": NAPADAC_SUB}, {"email": None}, {"email": 123},
    {"email": {"v": OSNIVAC}}, {"email": [OSNIVAC]}, "nije-dict", 42,
])
def test_F_bez_pouzdanog_identiteta_je_DENY(payload):
    email = email_iz_tokena(payload)
    assert email == ""
    assert _is_founder(email) is False
    assert _is_pro(email) is False


def test_F2_prazan_email_nije_u_listama():
    """Fail-closed radi samo ako prazan string nije član nijedne liste."""
    assert "" not in FOUNDER_EMAILS
    assert "" not in PRO_EMAILS


# ── WIRING: svih pet resolvera koristi kanonsku granicu ──────────────────────

def _izvor(fajl):
    return io.open(fajl, encoding="utf-8").read()


def _samo_kod(fajl):
    """Vraća {broj_reda: kod} sa UKLONJENIM stringovima i komentarima.

    Bez ovoga bi skener prijavljivao sopstvene docstringove koji `user_metadata`
    pominju da bi objasnili zašto je zabranjen — a to je prose, ne ulaz u
    identitet. Tokenizacija je egzaktna; regex nad sirovim izvorom nije.
    """
    import tokenize
    redovi = {}
    with io.open(fajl, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT, tokenize.NL,
                            tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
                continue
            r = tok.start[0]
            redovi[r] = redovi.get(r, "") + " " + tok.string
    return redovi


def test_W1_nijedan_resolver_vise_ne_cita_user_metadata_za_email():
    """Strukturalna brana. Ako se fallback vrati bilo gde, ovo pada."""
    prekrsaji = []
    for fajl in ("shared/deps.py", "api.py", "routers/voice_realtime.py",
                 "klijenti/router.py", "shared/voice_tools.py", "routers/voice.py"):
        try:
            src = _izvor(fajl)
        except OSError:
            continue
        del src
        for i, kod in _samo_kod(fajl).items():
            if "user_metadata" in kod and "email" in kod:
                prekrsaji.append("%s:%d  %s" % (fajl, i, kod.strip()[:90]))
    assert prekrsaji == [], "user_metadata je i dalje ulaz u identitet:\n" + "\n".join(prekrsaji)


def test_W2_svih_pet_resolvera_zove_kanonsku_granicu():
    for fajl in ("shared/deps.py", "api.py", "routers/voice_realtime.py",
                 "klijenti/router.py"):
        src = _izvor(fajl)
        assert "email_iz_tokena(payload)" in src, \
            "%s ne prolazi kroz kanonsku granicu poverenja" % fajl
    # api.py ima DVA resolvera (get_current_user i _auth_from_request)
    assert _izvor("api.py").count("email_iz_tokena(payload)") == 2


def test_W3_granica_je_definisana_na_TACNO_jednom_mestu():
    definicije = []
    for fajl in ("shared/deps.py", "api.py", "routers/voice_realtime.py",
                 "klijenti/router.py"):
        drvo = ast.parse(_izvor(fajl))
        for cvor in ast.walk(drvo):
            if isinstance(cvor, (ast.FunctionDef, ast.AsyncFunctionDef)) \
               and cvor.name == "email_iz_tokena":
                definicije.append(fajl)
    assert definicije == ["shared/deps.py"], definicije


# ── WIRING: privilegovane rute stvarno vise o tom email-u ────────────────────

PRIVILEGOVANI_MARKERI = ("FOUNDER_EMAILS", "_FOUNDER_EMAILS", "PRO_EMAILS",
                         "_is_founder", "_require_admin", "_require_founder",
                         "_require_cron_or_founder")


def test_W4_privilegovane_odluke_koriste_iskljucivo_user_email():
    """Svaka privilegovana provera u repou poredi `user["email"]` (ili `email`
    izveden iz njega) sa listom — nijedna ne čita `user_metadata` direktno.
    Time jedna popravka granice pokriva svih 62 rute."""
    import os
    prekrsaji = []
    for koren in (".", "routers", "klijenti"):
        if not os.path.isdir(koren):
            continue
        for f in sorted(os.listdir(koren)):
            if not f.endswith(".py"):
                continue
            fp = f if koren == "." else os.path.join(koren, f)
            src = _izvor(fp)
            if not any(m in src for m in PRIVILEGOVANI_MARKERI):
                continue
            for i, kod in _samo_kod(fp).items():
                if "user_metadata" in kod and "email" in kod:
                    prekrsaji.append("%s:%d %s" % (fp, i, kod.strip()[:80]))
    assert prekrsaji == [], "\n".join(prekrsaji)


# Snimljeno AST inventarom 2026-08-22 nad 614 ruta. Broj je namerno pribijen:
# nova privilegovana ruta MORA da natera svesnu proveru da li prolazi kroz
# kanonsku granicu poverenja, umesto da se tiho pridruži.
_OCEKIVANO_PRIVILEGOVANIH = 62


def _privilegovane_rute():
    import os
    DEKORATORI = {"get", "post", "put", "patch", "delete", "websocket"}
    gejtovi, rute = set(), []
    for koren in (".", "routers", "klijenti"):
        if not os.path.isdir(koren):
            continue
        for f in sorted(os.listdir(koren)):
            if not f.endswith(".py"):
                continue
            fp = f if koren == "." else os.path.join(koren, f)
            try:
                src = _izvor(fp)
                drvo = ast.parse(src)
            except Exception:
                continue
            for cvor in ast.walk(drvo):
                if not isinstance(cvor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                telo = ast.get_source_segment(src, cvor) or ""
                priv = any(m in telo for m in PRIVILEGOVANI_MARKERI)
                putanje = [
                    (d.func.attr.upper(), a.value)
                    for d in cvor.decorator_list
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                    and d.func.attr in DEKORATORI
                    for a in d.args
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                ]
                if priv and not putanje:
                    gejtovi.add(cvor.name)
                for m, p in putanje:
                    if priv or any(("Depends(%s)" % g) in telo for g in gejtovi):
                        rute.append((fp, m, p, telo))
    return rute


def test_W5_svaka_privilegovana_ruta_vise_o_kanonskoj_granici():
    """Ne dokazuje se po ruti nego po ULAZU: privilegovana odluka sme da čita
    identitet samo iz `user`/`payload` koji dolaze iz autentifikacije. Ako bi
    neka ruta uzela email iz tela zahteva ili upita, ovde bi ispala."""
    rute = _privilegovane_rute()
    assert len(rute) == _OCEKIVANO_PRIVILEGOVANIH, (
        "broj privilegovanih ruta je %d, očekivano %d — nova privilegovana ruta "
        "mora da se proveri protiv granice poverenja pre nego što se broj ažurira"
        % (len(rute), _OCEKIVANO_PRIVILEGOVANIH))

    SUMNJIVI_ULAZI = ("body.get(\"email\")", "body[\"email\"]", "req.email",
                      "request.query_params.get(\"email\")", "payload.get(\"user_metadata\")")
    prekrsaji = [
        "%s %s %s" % (fp, m, p)
        for fp, m, p, telo in rute
        if any(s in telo for s in SUMNJIVI_ULAZI)
    ]
    assert prekrsaji == [], \
        "privilegovana ruta uzima identitet iz zahteva:\n" + "\n".join(prekrsaji)


# ── PONAŠANJE GEJTOVA: strukturalna provera nije dovoljna ────────────────────
#
# Mereno: mutacija „ukloni proveru iz jedne rute" (`if False:` u
# `law_upload._require_admin`) PREŽIVELA je sve statičke testove iznad. Gejt
# mora da se pozove i da stvarno odbije, ne samo da postoji.

GEJTOVI = [
    ("routers.batch_ingest", "_require_admin"),
    ("routers.law_upload", "_require_admin"),
    ("routers.product_intelligence", "_require_admin"),
    ("routers.smart_intake", "_require_founder"),
    ("routers.admin_dashboard", "_require_founder"),
]


def _pozovi(gate, user):
    import asyncio
    import inspect
    r = gate(user)
    return asyncio.run(r) if inspect.iscoroutine(r) else r


@pytest.mark.parametrize("modul,ime", GEJTOVI)
def test_G1_gejt_odbija_obicnog_korisnika(modul, ime):
    import importlib
    from fastapi import HTTPException
    gate = getattr(importlib.import_module(modul), ime)
    with pytest.raises(HTTPException) as ex:
        _pozovi(gate, {"user_id": NAPADAC_SUB, "email": "napadac@primer.rs"})
    assert ex.value.status_code == 403, "%s.%s ne odbija" % (modul, ime)


@pytest.mark.parametrize("modul,ime", GEJTOVI)
def test_G2_gejt_odbija_prazan_identitet(modul, ime):
    """Fail-closed: kad `email_iz_tokena` vrati `""`, gejt mora da odbije."""
    import importlib
    from fastapi import HTTPException
    gate = getattr(importlib.import_module(modul), ime)
    for user in ({"user_id": NAPADAC_SUB, "email": ""}, {"user_id": NAPADAC_SUB}):
        with pytest.raises(HTTPException) as ex:
            _pozovi(gate, user)
        assert ex.value.status_code == 403


@pytest.mark.parametrize("modul,ime", GEJTOVI)
def test_G3_gejt_propusta_osnivaca(modul, ime):
    """Kontrola: gejt koji uvek odbija bio bi „siguran" i beskoristan."""
    import importlib
    gate = getattr(importlib.import_module(modul), ime)
    _pozovi(gate, {"user_id": OSNIVAC_SUB, "email": OSNIVAC})
