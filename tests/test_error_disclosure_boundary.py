# -*- coding: utf-8 -*-
"""P2 — GRANICA OTKRIVANJA INTERNIH PODATAKA NA 5xx.

ORIGINALNI BUG, dokazan na produkciji `657818a5`:

    POST /api/firma-memorija/klijent/sacuvaj  {"rizik_profil": "NEPOSTOJECI_PROFIL"}
    → CHECK violation (SQLSTATE 23514)
    → routers/firm_memory.py:  raise HTTPException(500, str(e))
    → HTTP 500 telo je sadržalo:
        'details': 'Failing row contains (819b2085-…, 5add0312-…, null,
         KANARINAC-TAJNI-KLIJENT-9f3a, null, f, email, NEPOSTOJECI_PROFIL, …)'

    Kanarinac je prešao granicu BAZA → APLIKACIJA → HTTP → KORISNIK.

ZAŠTO globalni `Exception` handler nije pomogao: on eksplicitno propušta
`HTTPException` dalje, a handler za `HTTPException` nije bio registrovan nigde —
pa je Starlette-ov podrazumevani serijalizovao `detail` doslovno.

NOVA INVARIJANTA (mandat §15):
  I1  nijedna vrednost iz baze ne stiže u 5xx odgovor
  I2  nijedan naziv tabele/kolone ne stiže u 5xx odgovor
  I3  nijedan SQLSTATE/SQL ne stiže u 5xx odgovor
  I4  nijedan traceback ne stiže u 5xx odgovor
  I5  4xx ugovori ostaju nepromenjeni
  I6  server-side dijagnostika ostaje dostupna
"""
import logging
import os

import pytest
from fastapi import HTTPException

KANARINAC = "KANARINAC-TAJNI-KLIJENT-9f3a"
CANARY = "DISCLOSURE_CANARY_7b21f4e9"

# Doslovan payload greške koji je produkcija vraćala korisniku.
SIROVI_DB_DETALJ = (
    "{'message': 'new row for relation \"client_memory\" violates check constraint "
    "\"client_memory_rizik_profil_check\"', 'code': '23514', 'hint': None, 'details': "
    "'Failing row contains (819b2085-9d81-4b6b-8b53-3c2c68146c9b, "
    "5add0312-263f-4772-8829-f9f07ae6c428, null, " + KANARINAC + ", null, f, email, "
    "NEPOSTOJECI_PROFIL, [], null, {}, 2026-08-23 19:10:40.623353+00).'}"
)

ZABRANJENO = [
    KANARINAC, CANARY,
    "Failing row contains",
    "client_memory", "rizik_profil", "client_memory_rizik_profil_check",
    "23514", "SQLSTATE", "'code'", "'details'", "'hint'",
    "Traceback", "site-packages",
]


@pytest.fixture(scope="module")
def klijent():
    for k, v in [("SUPABASE_URL", "https://fake.supabase.co"),
                 ("SUPABASE_ANON_KEY", "fake-anon-key"),
                 ("SUPABASE_SERVICE_KEY", "fake-service-key"),
                 ("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok"),
                 ("OPENAI_API_KEY", "sk-fake"),
                 ("PINECONE_API_KEY", "fake-pinecone"),
                 ("PINECONE_HOST", "https://fake.pinecone.io")]:
        os.environ.setdefault(k, v)
    from fastapi.testclient import TestClient
    import api

    # Rute koje pokrivaju svaki obrazac iz mandata §10.
    @api.app.get("/__probe/plain-exception")
    async def _p_plain():
        raise RuntimeError(SIROVI_DB_DETALJ)

    @api.app.get("/__probe/httpexc-raw")
    async def _p_raw():
        raise HTTPException(status_code=500, detail=SIROVI_DB_DETALJ)

    @api.app.get("/__probe/httpexc-safe")
    async def _p_safe():
        raise HTTPException(status_code=500, detail="AI servis trenutno nedostupan.")

    @api.app.get("/__probe/httpexc-503")
    async def _p_503():
        raise HTTPException(status_code=503, detail=SIROVI_DB_DETALJ)

    @api.app.get("/__probe/namerni-503")
    async def _p_namerni():
        from shared.http_errors import NamerniHTTPException
        raise NamerniHTTPException(
            status_code=503,
            detail="Izveštaj nije izračunat — izvor „fakture” trenutno nije dostupan.")

    @api.app.get("/__probe/httpexc-400")
    async def _p_400():
        raise HTTPException(status_code=400, detail="Prioritet mora biti: hitno, visoko")

    @api.app.get("/__probe/httpexc-404")
    async def _p_404():
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    @api.app.get("/__probe/httpexc-403-headers")
    async def _p_403():
        raise HTTPException(status_code=403, detail="Nemate pravo pristupa.",
                            headers={"X-Proba": "1"})

    return TestClient(api.app, raise_server_exceptions=False)


def _telo(r):
    return r.text


# ══ META ════════════════════════════════════════════════════════════════════

def test_META_fixture_nosi_stvarni_payload():
    """Bez ovoga bi testovi ispod bili trivijalno zeleni."""
    assert KANARINAC in SIROVI_DB_DETALJ
    assert "Failing row contains" in SIROVI_DB_DETALJ
    assert "23514" in SIROVI_DB_DETALJ


# ══ §8 — ORIGINALNI BUG ═════════════════════════════════════════════════════

def test_originalni_bug_kanarinac_vise_ne_prelazi_granicu(klijent):
    """Reprodukcija originalnog produkcionog nalaza."""
    r = klijent.get("/__probe/httpexc-raw")
    assert r.status_code == 500, "mora ostati 5xx — ne sakrivamo grešku"
    assert KANARINAC not in _telo(r), "kanarinac i dalje prelazi granicu"


@pytest.mark.parametrize("igla", ZABRANJENO)
def test_I1_I4_nijedan_interni_trag_ne_izlazi(klijent, igla):
    """I1–I4: vrednost iz baze, metapodaci šeme, SQLSTATE, traceback."""
    for put in ("/__probe/httpexc-raw", "/__probe/plain-exception", "/__probe/httpexc-503"):
        assert igla not in _telo(klijent.get(put)), "%s curi na %s" % (igla, put)


# ══ §10 — SVE CETIRI PUTANJE ════════════════════════════════════════════════

def test_A_obican_exception_daje_sanitizovan_500(klijent):
    r = klijent.get("/__probe/plain-exception")
    assert r.status_code == 500
    assert KANARINAC not in _telo(r)


def test_B_httpexception_sa_sirovim_detaljem_je_sanitizovan(klijent):
    r = klijent.get("/__probe/httpexc-raw")
    assert r.status_code == 500
    assert r.json()["detail"] == "Interna greška servera. Pokušajte ponovo."


def test_C_httpexception_sa_bezbednim_detaljem_je_takodje_sanitizovan(klijent):
    """Mandat §5: za status >= 500 `detail` se IGNORIŠE — bez izuzetaka.

    Runtime ne može da dokaže da je neka niska „bezbedna"; jedini proverljiv
    ugovor je da 5xx nikad ne nosi detalj.
    """
    r = klijent.get("/__probe/httpexc-safe")
    assert r.status_code == 500
    assert r.json()["detail"] == "Interna greška servera. Pokušajte ponovo."


def test_svi_5xx_statusi_su_pokriveni_ne_samo_500(klijent):
    r = klijent.get("/__probe/httpexc-503")
    assert r.status_code == 503, "status se ne sme menjati"
    assert KANARINAC not in _telo(r)
    assert r.json()["detail"] == "Interna greška servera. Pokušajte ponovo."


# ══ I5 — 4xx UGOVORI NETAKNUTI ══════════════════════════════════════════════

def test_D_4xx_ugovor_ostaje_nepromenjen(klijent):
    r = klijent.get("/__probe/httpexc-400")
    assert r.status_code == 400
    assert r.json()["detail"] == "Prioritet mora biti: hitno, visoko"


def test_I5_404_poruka_ostaje_korisniku(klijent):
    r = klijent.get("/__probe/httpexc-404")
    assert r.status_code == 404
    assert r.json()["detail"] == "Predmet nije pronađen."


def test_I5_4xx_zaglavlja_se_cuvaju(klijent):
    r = klijent.get("/__probe/httpexc-403-headers")
    assert r.status_code == 403
    assert r.headers.get("X-Proba") == "1"
    assert r.json()["detail"] == "Nemate pravo pristupa."


def test_I5_validacija_422_ostaje_nepromenjena(klijent):
    """RequestValidationError ima sopstveni handler — ne sme biti dodirnut."""
    r = klijent.post("/api/pitanje", json={"pitanje": "x"})
    assert r.status_code in (401, 422), r.status_code


# ══ I6 — OBSERVABILITY ══════════════════════════════════════════════════════

def test_I6_originalni_detalj_ostaje_u_server_logu(klijent, caplog):
    """Sanitizacija odgovora NE SME uništiti dijagnostiku."""
    with caplog.at_level(logging.ERROR):
        r = klijent.get("/__probe/httpexc-raw")
    assert r.status_code == 500
    assert KANARINAC not in _telo(r), "curi klijentu"
    assert any(KANARINAC in rec.getMessage() for rec in caplog.records), \
        "original nije zabeležen server-side — dijagnostika uništena"


# ══ §13 — GRANICA JE CENTRALNA, NE PO RUTI ══════════════════════════════════

def test_granica_je_registrovana_centralno():
    import api
    from starlette.exceptions import HTTPException as _SHE
    h = api.app.exception_handlers.get(_SHE)
    assert h is not None, "nema centralnog HTTPException handlera — rupa je otvorena"
    assert h.__name__ == "_http_exception_boundary"


def test_globalni_exception_handler_i_dalje_postoji():
    import api
    assert Exception in api.app.exception_handlers


# ══ NAMERNI 5xx UGOVOR — opt-in, ne heuristika ══════════════════════════════
#
# Prva verzija ove granice sanitizovala je SVE 5xx i oborila 11 testova, među
# njima 9 iz B2 gate-a. Ti testovi brane poruku koja korisniku govori da iznos
# NIJE izračunat — bez nje se pao izvor ne razlikuje od „nula dinara".

def test_namerni_5xx_ugovor_stize_korisniku(klijent):
    r = klijent.get("/__probe/namerni-503")
    assert r.status_code == 503
    assert "nije izračunat" in r.json()["detail"],         "namerni korisnički ugovor je progutan sanitizacijom"


def test_obican_5xx_sa_istim_statusom_je_i_dalje_sanitizovan(klijent):
    """Opt-in ne sme da bude rupa: običan 503 se i dalje sanitizuje."""
    r = klijent.get("/__probe/httpexc-503")
    assert r.status_code == 503
    assert KANARINAC not in _telo(r)
    assert r.json()["detail"] == "Interna greška servera. Pokušajte ponovo."


def test_opt_in_se_NIKAD_ne_koristi_sa_DINAMICKIM_detaljem():
    """Zaštita od buduće zloupotrebe odobrenih vrata.

    `NamerniHTTPException` sme nositi SAMO ručno pisan tekst. Ako iko ikad
    prosledi vrednost izvedenu iz uhvaćenog izuzetka, curenje se vraća kroz
    jedina vrata koja granica propušta.

    OVA PROVERA JE NAMERNO STROGA: prva verzija je tražila imena promenljivih
    (`e`, `exc`) i mutacija `{r!r}` ju je PREŽIVELA. Zato se sada ne gleda ime
    promenljive nego OBLIK IZRAZA — `detail` sme biti isključivo konstanta ili
    f-string čiji su svi umetnuti izrazi jednostavna imena/atributi koji NISU
    izvedeni iz izuzetka, i nijedna konverzija (`!r`) nije dozvoljena.

    Provera ide nad PARSIRANIM kodom, ne nad niskama — komentar koji pominje
    `str(e)` ne sme da obori test (naučeno u B-U-007 i F1).
    """
    import ast
    import io as _io
    import os as _os

    def _bezbedan(det: ast.AST) -> tuple[bool, str]:
        if isinstance(det, ast.Constant):
            return True, ""
        if isinstance(det, ast.JoinedStr):
            for d in det.values:
                if isinstance(d, ast.Constant):
                    continue
                if not isinstance(d, ast.FormattedValue):
                    return False, "nepoznat deo f-stringa"
                # `!r` / `!s` na uhvacenom objektu je tacno M15 obrazac
                if d.conversion != -1:
                    return False, "konverzija !r/!s u f-stringu"
                v = d.value
                if not isinstance(v, ast.Name):
                    return False, "umetnut izraz nije prosto ime: %s" % ast.unparse(v)
            return True, ""
        if isinstance(det, ast.BinOp) or isinstance(det, ast.Call):
            return False, "izracunat detail: %s" % ast.unparse(det)[:60]
        return False, "nepoznat oblik: %s" % ast.unparse(det)[:60]

    prekrsaji = []
    putevi = ["api.py"]
    for baza in ("routers", "shared", "services", "security"):
        for r, _, fs in _os.walk(baza):
            if "__pycache__" in r:
                continue
            putevi += [_os.path.join(r, f) for f in fs if f.endswith(".py")]

    nadjeno = 0
    for put in putevi:
        try:
            drvo = ast.parse(_io.open(put, encoding="utf-8").read())
        except Exception:
            continue
        for n in ast.walk(drvo):
            if not isinstance(n, ast.Call):
                continue
            ime = getattr(n.func, "id", "") or getattr(n.func, "attr", "")
            if "Namerni" not in ime:
                continue
            det = None
            for kw in n.keywords:
                if kw.arg == "detail":
                    det = kw.value
            if det is None and len(n.args) > 1:
                det = n.args[1]
            if det is None:
                continue
            nadjeno += 1
            ok, razlog = _bezbedan(det)
            if not ok:
                prekrsaji.append("%s: %s" % (put, razlog))

    assert nadjeno >= 3, (
        "nisu nadjena mesta koja koriste opt-in (%d) — test bi bio prazan" % nadjeno)
    assert not prekrsaji, "opt-in nosi dinamican detalj: %s" % prekrsaji
