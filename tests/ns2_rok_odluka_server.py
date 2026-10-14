# -*- coding: utf-8 -*-
"""Night Sprint II / A2 — PRAVI uvicorn sa PRAVIM `api.app` (primarni V2 /app) za tok odluke o roku.

Nije pytest test. Pokreće ga frontend-v2-ng/tests/live-rok-odluka-e2e.mjs: `python tests/ns2_rok_odluka_server.py <port>`.
Okruženje je isto kao tests/osb003_solo_server.py (`postavi_solo`: stvarne rute, baza u memoriji koja STVARNO upisuje,
simulirana samo prijava i modeli), uz jednu razliku: radi STVARAN `shared.audit_immutable.log_action` (hash-lanac,
`seq`), jer je lanac odluka o roku poslovni upis koji se ovde dokazuje. Čuvar soketa blokira svaku vezu van loopback-a.

Test rute (postoje SAMO u ovom procesu):
  POST /__ns2/umetni   — upis reda hronologije kakav proizvodi pisac (npr. A1 sa `vrsta='rok'`, ili zatečen pisac bez nje)
  POST /__ns2/kvar     — {"tabela", "radnja": "insert"|"select"|"*", "ukljucen"} → PostgREST statement timeout
  POST /__ns2/opozovi  — {"token"} → token više ne važi (istekla sesija → 401)
  GET  /__ns2/stanje   — lanac odluka o rokovima i redovi hronologije (sintetički podaci)
"""
import os
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4531
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k, _v in (("OPENAI_API_KEY", "sk-fake-ns2a2"), ("PINECONE_API_KEY", "fake"), ("PINECONE_HOST", "https://fake.pinecone.io"),
               ("FOUNDER_EMAILS", "ci@example.com"), ("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "x"),
               ("SUPABASE_ANON_KEY", "x"), ("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok"),
               ("FIELD_ENCRYPTION_KEY", "a" * 64), ("VINDEX_V2_NG_PRIMARY_ENABLED", "1"),
               ("GIT_SHA", "5eedc0de5eedc0de5eedc0de5eedc0de5eedc0de")):
    os.environ.setdefault(_k, _v)

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402
import uvicorn  # noqa: E402

import uploaded_doc.chunker  # noqa: E402,F401  (tiktoken keš pre čuvara soketa, kao osb003)
from tests import ns005_harness as _H  # noqa: E402  (čuvar soketa se instalira pri uvozu)
from tests.test_osb002_solo_tok import postavi_solo  # noqa: E402
import shared.audit_immutable as _AUD  # noqa: E402

_PRAVI_LOG = _AUD.log_action
mp = pytest.MonkeyPatch()
_, BAZA = postavi_solo(mp)
mp.setattr(_AUD, "log_action", _PRAVI_LOG)   # harness ga gasi; ovde je lanac odluka ono što se dokazuje
import api  # noqa: E402
import shared.deps as _deps  # noqa: E402
api.app.dependency_overrides[_deps.get_current_user] = api.app.dependency_overrides[api.get_current_user]
api.limiter.enabled = False

from fastapi.responses import JSONResponse  # noqa: E402

_KVAR: dict = {}
_izvrsi = _H._Upit.execute


def _izvrsi_sa_kvarom(self):
    k = _KVAR.get(self.t)
    if k and (k == "*" or self.radnja[0] == k):
        raise Exception('{"code": "57014", "message": "canceling statement due to statement timeout"}')
    return _izvrsi(self)


mp.setattr(_H._Upit, "execute", _izvrsi_sa_kvarom)


@api.app.post("/__ns2/umetni", include_in_schema=False)
async def _umetni(z: dict):
    r = BAZA.table("predmet_hronologija").insert(z).execute()
    return JSONResponse({"id": (r.data or [{}])[0].get("id")})


@api.app.post("/__ns2/kvar", include_in_schema=False)
async def _kvar(z: dict):
    if z.get("ukljucen"):
        _KVAR[z["tabela"]] = z.get("radnja") or "*"
    else:
        _KVAR.pop(z.get("tabela"), None)
    return JSONResponse({"kvarovi": sorted(_KVAR)})


@api.app.post("/__ns2/opozovi", include_in_schema=False)
async def _opozovi(z: dict):
    _H.TOKENI.pop(str(z.get("token")), None)
    return JSONResponse({"ok": True})


@api.app.get("/__ns2/stanje", include_in_schema=False)
async def _stanje():
    t = BAZA.tabele
    return JSONResponse({
        "odluke": [{"akcija": a.get("action"), "rok": a.get("resource_id"), "korisnik": a.get("user_id"), "seq": a.get("seq")}
                   for a in sorted(t.get("audit_immutable", []), key=lambda x: x.get("seq") or 0)
                   if a.get("resource_type") == "rok"],
        "hronologija": [{"id": h.get("id"), "predmet_id": h.get("predmet_id"), "korisnik": h.get("user_id"), "vrsta": h.get("vrsta"),
                         "izvor": h.get("izvor"), "dogadjaj": h.get("dogadjaj"), "datum_iso": h.get("datum_iso")}
                        for h in t.get("predmet_hronologija", [])],
        "spoljni_pokusaji": len(_H.SPOLJNI_POKUSAJI),
    })


uvicorn.run(api.app, host="127.0.0.1", port=PORT, lifespan="off", log_level="warning", access_log=False)
