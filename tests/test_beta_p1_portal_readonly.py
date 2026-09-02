# -*- coding: utf-8 -*-
"""
BETA-P1-PORTAL-READONLY — KLIJENTSKI PORTAL MORA DA SE OTVORI, I NIŠTA VIŠE.

ŠTA JE BILO — mereno protiv produkcije 2026-08-14, samo čitanjem

Postoje **dva** portala. Advokatov link je vodio u pogrešan.

  · Link koji advokat stvarno generiše (`POST /api/client-portal/token/{id}`)
    je HMAC token čiji se **heš** čuva u `client_portal_tokens`, a URL glasi
    `{APP_URL}/portal?token=…`.
  · `/portal` servira `client_portal.html`, koja je zvala
    **`/api/portal/predmet`** — rutu koja token traži u **`privremeni_pristup`**,
    sasvim drugoj tabeli, koju puni `saradnja.py`.

Dakle svaki klijentski link je završavao na **404 „Token nije pronađen"**, pre
nego što bi ijedan upit nad predmetom uopšte krenuo.

ISPRAVKA RANIJEG NALAZA

U izveštaju izlaznog gejta sam kao uzrok naveo poziv ka nepostojećoj tabeli
`rokovi` u `asyncio.gather` bez `return_exceptions` (`api.py:2634`). Taj poziv
**jeste** pokvaren — `rokovi` ne postoji (`PGRST205`, izmereno) — ali je
**nedostižan**, jer 404 na tokenu puca pre njega. Isti oblik greške kao P0-1 u
Tasku 1: prijavljen je mrtav kod.

DRUGI SLOJ — I KANONSKA RUTA JE BILA PUKLA

`/api/client-portal/view` bira `tip_roka` sa `predmet_hronologija`. Ta kolona
**ne postoji** (izmereno; tabela ima `akter, created_at, datum, datum_iso,
dogadjaj, dokument_naziv, id, predmet_id, user_id, vaznost`). PostgREST odbija
ceo upit sa `42703`, a poziv je u `asyncio.gather` **bez `return_exceptions`** —
dakle i da je stranica zvala pravu rutu, dobila bi 500.

Dokaz nije čitanje koda nego izvršenje istog upita nad produkcijom:

    ?select=dogadjaj,datum_iso,vaznost,tip_roka   → 400 / 42703
    ?select=dogadjaj,datum_iso,vaznost            → 200

READ-ONLY (M-1)

Portal upload je jedina od četiri putanje unosa dokumenata koja fajl **ne
šifruje**. Kapija je isključena podrazumevano — ne zato što je kod pogrešan,
nego zato što se ugovor poverljivosti bez šifrovanja ne može ispuniti.
"""
import asyncio
import io
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("SECRET_KEY", "test-secret-key-za-hmac")

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import routers.client_portal as cp  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# FAZA 6.5 — ROKOVI U OVIM FIXTURE-IMA SU POTVRDJENI
#
# Od 6.5 klijentski portal prikazuje ISKLJUCIVO potvrdjene rokove (nepotvrdjen
# AI rok je bio otkrivan trecem licu -- FAZA 6.4.3). Testovi u ovom fajlu ne
# mere TU granicu (nju meri `test_faza65_confirmation_disclosure_impl.py`) nego
# skrivanje internih beleski i oblik odgovora, sto su i dalje vazeci ugovori.
#
# Zato se modeluje advokat koji je rokove vec potvrdio.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _rokovi_su_potvrdjeni(monkeypatch):
    import routers.client_portal as _cp
    from shared.rok_potvrda import STANJE_POTVRDJEN
    if hasattr(_cp, "_odluke"):
        monkeypatch.setattr(
            _cp, "_odluke",
            lambda ids: {str(i): STANJE_POTVRDJEN for i in ids if i is not None})
    # Fixture redovi cesto nemaju `id`; politika bez `id` ne moze da ih uveze
    # sa odlukom, pa se ovde dodeljuje stabilan surogat -- isto sto baza radi.
    _orig = _cp._filtriraj_za

    def _sa_id(redovi, odl, **kw):
        redovi = [{**r, "id": r.get("id") or f"fx-{i}"} for i, r in enumerate(redovi or [])]
        return _orig(redovi, {r["id"]: STANJE_POTVRDJEN for r in redovi}, **kw)

    monkeypatch.setattr(_cp, "_filtriraj_za", _sa_id)


PRED = "pred-1"
ADVOKAT = "uid-advokat"

# Kolone koje tabele STVARNO imaju u produkciji (mereno preko OpenAPI korena).
SEMA = {
    "predmeti": {"broj_predmeta", "case_dna", "created_at", "id", "kanban_faza",
                 "naziv", "opis", "rizik", "status", "tip", "tuzeni", "tuzilac",
                 "updated_at", "user_id", "vrednost_spora"},
    "predmet_hronologija": {"akter", "created_at", "datum", "datum_iso",
                            "dogadjaj", "dokument_naziv", "id", "predmet_id",
                            "user_id", "vaznost"},
    "rocista": {"broj_predmeta_suda", "created_at", "datum", "id", "napomena",
                "predmet_id", "status", "sud", "sudnica", "updated_at",
                "user_id", "vreme"},
    "client_portal_tokens": {"created_at", "expires_at", "id", "is_active",
                             "klijent_email", "predmet_id", "token_hash",
                             "user_id"},
}


class _Supa:
    """Lažni Supabase koji STVARNO odbija nepostojeće kolone, kao PostgREST."""

    def __init__(self, token_red=None, redovi=None):
        self.token_red = token_red
        self.redovi = redovi or {}
        self.trazene_kolone = {}

    def table(self, ime):
        spolja = self

        class _Q:
            def __init__(self):
                self.ime = ime

            def select(self, izraz, *a, **k):
                kolone = {c.strip() for c in izraz.split(",") if c.strip()}
                spolja.trazene_kolone.setdefault(ime, set()).update(kolone)
                nepoznate = kolone - SEMA.get(ime, kolone)
                if nepoznate:
                    raise RuntimeError(
                        "column %s.%s does not exist (42703)"
                        % (ime, sorted(nepoznate)[0]))
                return self

            def eq(self, *a, **k):
                return self

            def gte(self, *a, **k):
                return self

            def lte(self, *a, **k):
                return self

            def in_(self, *a, **k):
                return self

            def order(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def maybe_single(self):
                return self

            def execute(self):
                if self.ime == "client_portal_tokens":
                    return MagicMock(data=spolja.token_red)
                return MagicMock(data=spolja.redovi.get(self.ime, []))
        return _Q()


def _token(predmet_id=PRED, advokat=ADVOKAT, sati=24):
    import time
    return cp._generiši_token(predmet_id, advokat, int(time.time()) + sati * 3600)


def _aktivan_token_red():
    return {"id": "t1", "is_active": True, "expires_at": "2026-12-31T00:00:00Z"}


def _pogled(supa, token=None):
    return asyncio.run(cp.client_portal_view.__wrapped__(
        request=MagicMock(), x_portal_token=token or _token()))


# ═══════════════════════════════════════════════════════════════════════════
# 1. SRŽ — PORTAL SE MORA OTVORITI
# ═══════════════════════════════════════════════════════════════════════════

def test_portal_se_otvara_na_STVARNOJ_semi():
    """NAJVAŽNIJI TEST U FAJLU.

    Lažni Supabase odbija kolone koje produkcija nema — isto kao PostgREST.
    Pre popravke je `tip_roka` obarao ceo `gather` i klijent je dobijao 500.
    """
    supa = _Supa(token_red=_aktivan_token_red(), redovi={
        "predmeti": {"naziv": "Spor", "opis": "Opis", "tip": "parnicni",
                     "status": "aktivan", "created_at": "2026-01-01"},
        "predmet_hronologija": [{"dogadjaj": "Rok: žalba", "datum_iso": "2026-09-01",
                                 "vaznost": "kritičan"}],
        "rocista": [{"sud": "Osnovni sud", "datum": "2026-09-05", "vreme": "10:00",
                     "sudnica": "12", "broj_predmeta_suda": "P 1/26",
                     "status": "zakazano"}],
    })
    with patch.object(cp, "_get_supa", return_value=supa):
        rez = _pogled(supa)
    assert rez["predmet"]["naziv"] == "Spor"
    assert rez["rocista"], "ročišta nisu vraćena"


def test_nijedna_trazena_kolona_ne_izlazi_iz_stvarne_seme():
    """Brava nad IZVOROM kvara, ne nad posledicom.

    Kvar nije nastao pogrešnim uslovom nego kolonom koja ne postoji. Ovaj test
    upoređuje svaki `select` sa izmerenom produkcionom šemom."""
    supa = _Supa(token_red=_aktivan_token_red(), redovi={
        "predmeti": {"naziv": "Spor"}, "predmet_hronologija": [], "rocista": []})
    with patch.object(cp, "_get_supa", return_value=supa):
        _pogled(supa)
    for tabela, kolone in supa.trazene_kolone.items():
        visak = kolone - SEMA[tabela]
        assert not visak, f"portal traži {tabela}.{sorted(visak)} — ne postoji"


def test_interne_beleske_ostaju_skrivene():
    """Postojeća zaštita poverljivosti ne sme da regresira uz popravku."""
    supa = _Supa(token_red=_aktivan_token_red(), redovi={
        "predmeti": {"naziv": "Spor"},
        "predmet_hronologija": [
            {"dogadjaj": "[INTERNI] klijent menja iskaz", "vaznost": "važan"},
            {"dogadjaj": "Podnet odgovor na tužbu", "vaznost": "važan"},
            {"dogadjaj": "Interna procena", "vaznost": "interni"},
        ],
        "rocista": [],
    })
    with patch.object(cp, "_get_supa", return_value=supa):
        rez = _pogled(supa)
    spojeno = str(rez["hronologija"])
    assert "[INTERNI]" not in spojeno
    assert "Interna procena" not in spojeno
    assert "Podnet odgovor" in spojeno


# ═══════════════════════════════════════════════════════════════════════════
# 2. AUTORIZACIJA — NE SME DA REGRESIRA
# ═══════════════════════════════════════════════════════════════════════════

def test_bez_tokena_je_401():
    with pytest.raises(HTTPException) as e:
        asyncio.run(cp.client_portal_view.__wrapped__(
            request=MagicMock(), x_portal_token=None))
    assert e.value.status_code == 401


def test_falsifikovan_potpis_je_401():
    """HMAC je jedina brana između klijenta i tuđeg predmeta."""
    lose = _token()[:-4] + "0000"
    with pytest.raises(HTTPException) as e:
        _pogled(_Supa(token_red=_aktivan_token_red()), token=lose)
    assert e.value.status_code == 401


def test_opozvan_token_je_401():
    supa = _Supa(token_red={"id": "t1", "is_active": False})
    with patch.object(cp, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as e:
            _pogled(supa)
    assert e.value.status_code == 401


def test_token_kog_nema_u_bazi_je_401():
    supa = _Supa(token_red=None)
    with patch.object(cp, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as e:
            _pogled(supa)
    assert e.value.status_code == 401


def test_predmet_se_cita_samo_za_advokata_iz_tokena():
    """Bez vezivanja na `user_id` iz tokena, token bi bio kljuc za bilo ciji
    predmet sa istim `predmet_id`."""
    izvor = io.open(os.path.join(_KOREN, "routers", "client_portal.py"),
                    encoding="utf-8").read()
    isecak = izvor[izvor.index("async def client_portal_view"):]
    isecak = isecak[:isecak.index("# ─── Klijent: upload")]
    assert isecak.count('.eq("user_id", advokat_uid)') >= 3, (
        "upiti portala nisu vezani za advokata iz tokena"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. READ-ONLY (M-1) — SLANJE DOKUMENATA JE ZATVORENO
# ═══════════════════════════════════════════════════════════════════════════

def test_upload_je_podrazumevano_ISKLJUCEN():
    """Jedina putanja unosa koja ne šifruje fajl. Za betu je zatvorena."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PORTAL_UPLOAD_ENABLED", None)
        with pytest.raises(HTTPException) as e:
            asyncio.run(cp.client_portal_upload.__wrapped__(
                request=MagicMock(), fajl=MagicMock(), napomena=None,
                x_portal_token=_token()))
    assert e.value.status_code == 503
    assert "isključeno" in str(e.value.detail)


def test_upload_kapija_puca_PRE_ijedne_provere_tokena():
    """Zatvorena kapija ne sme da zavisi od validnosti tokena — inače bi
    neispravan token davao drugačiji ishod od ispravnog."""
    os.environ.pop("PORTAL_UPLOAD_ENABLED", None)
    with pytest.raises(HTTPException) as e:
        asyncio.run(cp.client_portal_upload.__wrapped__(
            request=MagicMock(), fajl=MagicMock(), napomena=None,
            x_portal_token=None))
    assert e.value.status_code == 503, "kapija propušta zahtev bez tokena dalje"


def test_upload_se_otvara_samo_svesnom_odlukom():
    """Kapija mora biti stvarna, ne dekorativna: sa uključenom promenljivom
    tok ide dalje (i tamo pada na proveri tokena, ne na kapiji)."""
    with patch.dict(os.environ, {"PORTAL_UPLOAD_ENABLED": "1"}):
        with pytest.raises(HTTPException) as e:
            asyncio.run(cp.client_portal_upload.__wrapped__(
                request=MagicMock(), fajl=MagicMock(), napomena=None,
                x_portal_token=None))
    assert e.value.status_code == 401, "kapija se ne otvara ni kad vlasnik kaže"


# ═══════════════════════════════════════════════════════════════════════════
# 4. STRANICA ZOVE KANONSKU RUTU
# ═══════════════════════════════════════════════════════════════════════════

def test_portal_stranica_zove_kanonsku_rutu_sa_zaglavljem():
    html = io.open(os.path.join(_KOREN, "client_portal.html"),
                   encoding="utf-8").read()
    assert '"/api/client-portal/view"' in html, (
        "stranica ne zove kanonsku rutu — token bi se tražio u pogrešnoj tabeli"
    )
    assert "X-Portal-Token" in html, "token se ne šalje u zaglavlju"
    assert 'fetch("/api/portal/predmet' not in html


def test_portal_stranica_nema_slanje_dokumenata():
    """Read-only znači i da kontrola za slanje ne postoji na stranici."""
    html = io.open(os.path.join(_KOREN, "client_portal.html"),
                   encoding="utf-8").read()
    assert "type=\"file\"" not in html
    assert "client-portal/dokument" not in html
