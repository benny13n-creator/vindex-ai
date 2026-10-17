# -*- coding: utf-8 -*-
"""NS3-N15 — red koji ne postoji ne sme da postane HTTP 500 (supabase/postgrest 2.28.3).

`maybe_single().execute()` za 0 redova vraća `None` (ne objekat sa `.data = None`) — proveren izvor instalirane
biblioteke: `SyncMaybeSingleRequestBuilder.execute` → `return None`. Kod koji odmah čita `.data` tada diže
AttributeError → 500. Isti razred kao TENFRONTS-M02. Pet mesta dostupnih korisniku, izabranih po vrednosti:

  optional red (prazno stanje je ugovor):
    1. GET /api/gdpr/export — `korisnik_email_notif` (većina korisnika ga nema) → ceo GDPR izvoz 500
    2. GET whatsapp pretplata — `whatsapp_pretplate` → ruta već ima granu „nije registrovan“
  red vlasništva (namera koda je 404 — fail-closed ostaje, menja se samo pogrešan kod):
    3. `routers/copilot_ambient._proveri_vlasnistvo_predmeta` (koriste je /api/podnesak, copilot)
    4. GET /api/predmeti/{id}/case-dna (`routers/case_dna.get_case_dna`)
    5. POST /api/rokovi/lanac sa `predmet_id` (`routers/rokovi_lanac`)

Lažna baza modeluje TAČNO 2.28.3: `maybe_single()` sa 0 redova → `execute()` vraća None."""
import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException

UID, DRUGI, PID = "u-1", "u-2", "p-1"


class _R:
    def __init__(self, data):
        self.data = data


class _Upit:
    def __init__(self, redovi):
        self.redovi, self.jedan = list(redovi), False

    def select(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def eq(self, k, v):
        self.redovi = [r for r in self.redovi if r.get(k) == v]
        return self

    def maybe_single(self):
        self.jedan = True
        return self

    def execute(self):
        if self.jedan:
            return _R(self.redovi[0]) if self.redovi else None      # postgrest 2.28.3
        return _R(self.redovi)


class _Baza:
    def __init__(self, tabele):
        self.tabele = tabele

    def table(self, ime):
        return _Upit(self.tabele.get(ime, []))


PREDMET = {"id": PID, "user_id": UID, "naziv": "P", "case_dna": {"verzija": 3}}


# ── 1. GDPR izvoz bez reda email podešavanja ────────────────────────────────────────────────────

def _gdpr(tabele):
    import routers.gdpr as g
    from starlette.requests import Request
    req = Request({"type": "http", "method": "GET", "path": "/api/gdpr/export", "headers": [], "query_string": b"",
                   "client": ("127.0.0.1", 1), "server": ("testserver", 80), "scheme": "http"})
    from shared.rate import limiter
    with patch.object(g, "_get_supa", return_value=_Baza(tabele)), patch.object(limiter, "enabled", False):
        return asyncio.run(g.gdpr_export(req, user={"user_id": UID}))


def test_gdpr_izvoz_bez_email_podesavanja():
    import json
    r = _gdpr({"profiles": [{"id": UID, "email": "a@primer.test", "full_name": "A", "created_at": "2026-01-01"}]})
    d = json.loads(r.body)
    assert d["email_podesavanja"] == {} and d["profil"]["id"] == UID


def test_gdpr_izvoz_bez_reda_profila():
    import json
    d = json.loads(_gdpr({}).body)
    assert d["profil"] == {} and d["email_podesavanja"] == {}


def test_gdpr_izvoz_sa_podesavanjima_nepromenjen():
    import json
    d = json.loads(_gdpr({"korisnik_email_notif": [{"user_id": UID, "aktivan": True, "dan_7": True}]}).body)
    assert d["email_podesavanja"]["aktivan"] is True


# ── 2. WhatsApp pretplata ───────────────────────────────────────────────────────────────────────

def _wa(tabele):
    import routers.whatsapp_notif as w
    fn = next(getattr(w, n) for n in dir(w) if n == "get_pretplata")
    from starlette.requests import Request
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"",
                   "client": ("127.0.0.1", 1), "server": ("testserver", 80), "scheme": "http"})
    from shared.rate import limiter
    import inspect
    with patch.object(w, "_get_supa", return_value=_Baza(tabele)), patch.object(limiter, "enabled", False):
        kw = {"user": {"user_id": UID}}
        if "request" in inspect.signature(fn).parameters:
            kw["request"] = req
        return asyncio.run(fn(**kw))


def test_whatsapp_bez_pretplate_je_nije_registrovan():
    d = _wa({})
    assert d["registrovan"] is False and d["aktivan"] is False


def test_whatsapp_sa_pretplatom_nepromenjeno():
    d = _wa({"whatsapp_pretplate": [{"user_id": UID, "telefon": "+38160", "kanal": "whatsapp", "aktivan": True,
                                     "tip_notifikacija": [], "created_at": "2026-01-01"}]})
    assert d["registrovan"] is True


# ── 3–5. Provera vlasništva: tuđ/nepostojeći predmet → 404, ne 500 ────────────────────────────

def _vlasnistvo(uid, pid=PID):
    import routers.copilot_ambient as ca
    with patch.object(ca, "_get_supa", return_value=_Baza({"predmeti": [PREDMET]})):
        return asyncio.run(ca._proveri_vlasnistvo_predmeta(pid, uid))


def _case_dna(uid, pid=PID):
    import routers.case_dna as cd
    with patch.object(cd, "_get_supa", return_value=_Baza({"predmeti": [PREDMET]})):
        return asyncio.run(cd.get_case_dna(pid, user={"user_id": uid}))


def _lanac(uid, pid=PID):
    import routers.rokovi_lanac as rl
    from shared.rate import limiter
    from starlette.requests import Request
    req = Request({"type": "http", "method": "POST", "path": "/api/rokovi/lanac", "headers": [], "query_string": b"",
                   "client": ("127.0.0.1", 1), "server": ("testserver", 80), "scheme": "http"})
    tip = rl.lista_tipova_dogadjaja()[0]
    tip = tip.get("id") or tip.get("tip") or tip.get("kljuc") if isinstance(tip, dict) else tip
    body = rl.LanacReq(tip_dogadjaja=tip, datum_pocetka="2026-10-01", predmet_id=pid)
    with patch.object(rl, "_get_supa", return_value=_Baza({"predmeti": [PREDMET]})), patch.object(limiter, "enabled", False):
        return asyncio.run(rl.post_rokovi_lanac(body, req, user={"user_id": uid}))


@pytest.mark.parametrize("poziv", [_vlasnistvo, _case_dna, _lanac], ids=["podnesak_copilot", "case_dna", "rokovi_lanac"])
@pytest.mark.parametrize("uid,pid", [(DRUGI, PID), (UID, "p-ne-postoji")], ids=["tudji", "nepostojeci"])
def test_tudji_ili_nepostojeci_predmet_je_404(poziv, uid, pid):
    with pytest.raises(HTTPException) as e:
        poziv(uid, pid)
    assert e.value.status_code == 404


def test_kontrola_vlasnik_prolazi():
    assert _vlasnistvo(UID) is None
    assert _case_dna(UID)["predmet_id"] == PID
