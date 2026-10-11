# -*- coding: utf-8 -*-
"""OSB003 Task 7 — PRAVI uvicorn sa PRAVIM `api.app` (primarni V2 /app) nad bazom u memoriji koja STVARNO upisuje.

Nije pytest test. Pokreće ga frontend-v2-ng/tests/live-solo-tok-e2e.mjs: `python tests/osb003_solo_server.py <port>`.
Okruženje je isto kao `tests/test_osb002_solo_tok.py::postavi_solo` (stvarne rute, stvaran intake worker, stvaran
dispečer događaja; simulirani su samo modeli, embedding/Pinecone i prijava). Za odgovor na pitanje i nacrt zamenjen je
samo poziv modela. Čuvar soketa iz tests/ns005_harness.py blokira svaku vezu van loopback-a.

Test ruta `POST /__osb003/obradi` (postoji SAMO u ovom procesu) pokreće worker i dispečer do kraja, da bi koraci
browser testa bili deterministički, bez pozadinskih niti. `GET /__osb003/stanje` vraća brojeve iz baze (bez sadržaja).
"""
import asyncio
import json
import os
import sys
import types

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4520
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k, _v in (("OPENAI_API_KEY", "sk-fake-osb003"), ("PINECONE_API_KEY", "fake"), ("PINECONE_HOST", "https://fake.pinecone.io"),
               ("FOUNDER_EMAILS", "ci@example.com"), ("SUPABASE_URL", "https://fake.supabase.co"), ("SUPABASE_SERVICE_KEY", "x"),
               ("SUPABASE_ANON_KEY", "x"), ("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok"),
               ("FIELD_ENCRYPTION_KEY", "a" * 64), ("VINDEX_V2_NG_PRIMARY_ENABLED", "1"),
               ("GIT_SHA", "5eedc0de5eedc0de5eedc0de5eedc0de5eedc0de")):
    os.environ.setdefault(_k, _v)

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

import pytest  # noqa: E402
import uvicorn  # noqa: E402

# Tokenizer (tiktoken `cl100k_base`, javni fajl) se pri prvom uvozu preuzima i kešira — PRE čuvara soketa, jer bi ga
# čuvar oborio na mašini bez keša (CI). To je JEDINA veza van loopback-a i nije poziv provajdera ni aplikacije;
# sve posle ove linije meri čuvar (provera „0 spoljnih veza" u browser testu).
import uploaded_doc.chunker  # noqa: E402,F401
from tests.ns005_harness import SPOLJNI_POKUSAJI  # noqa: E402  (čuvar soketa se instalira pri uvozu)
from tests.ns006_fake import dispecuj  # noqa: E402
from tests.test_osb002_solo_tok import postavi_solo  # noqa: E402

mp = pytest.MonkeyPatch()
_, BAZA = postavi_solo(mp)
# Kao produkcija danas: migracija 136 NIJE primenjena (PostgREST PGRST205 za tabele autonomije).
for _t in ("autonomy_cycles", "autonomy_work_items"):
    BAZA.greske[_t] = Exception('{"code": "PGRST205", "message": "Could not find the table public.%s in the schema cache"}' % _t)
import api  # noqa: E402
import shared.deps as _deps  # noqa: E402
api.app.dependency_overrides[_deps.get_current_user] = api.app.dependency_overrides[api.get_current_user]

POZIVI_MODELA = []


async def _pokreni(fn, pitanje_za_agenta, *a, **kw):
    POZIVI_MODELA.append("pitanje")
    return {"status": "success", "data": "--- PRAVNI ZAKLJUČAK\nSimuliran odgovor (OSB003).", "confidence": "HIGH", "top_score": 0.8,
            "confidence_detail": {"nivo": "HIGH"}, "izvori": [{"zakon": "zakon o radu", "clan": "Član 185"}]}


mp.setattr(api, "pokreni", _pokreni)
import routers.drafting as D  # noqa: E402
import services.quality_gate as QG  # noqa: E402
import app.services.retrieve as R  # noqa: E402


def _model(oai, **kw):
    POZIVI_MODELA.append("nacrt")
    sadrzaj = (json.dumps({"tuzilac": "Marko Petrovic", "tuzeni": "Gradnja Invest DOO"}) if kw.get("max_tokens") == 900
               else json.dumps({"pravni_osnov": "čl. 185 ZR"}))
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=sadrzaj))])


async def _kriticar(*a, **kw):
    return {"ima_izmisljenih_navoda": False}


async def _kvalitet(*a, **kw):
    return {"confidence_score": 0.5, "detail": {}}


mp.setattr(D, "_pozovi_drafting_api", _model)
# VCR001 T02: predlog iz opisa problema (POST /api/intake/ekstrakcija) — zamenjen je samo poziv modela.
import routers.intake as _INT  # noqa: E402
async def _ekstrakcija(opis, nalazi):
    POZIVI_MODELA.append("ekstrakcija")
    return {"predlog_naziva_predmeta": "Nikolic protiv Delta Promet — zarada", "protivna_strana": "Delta Promet DOO",
            "vrsta_spora": "radni spor", "vrednost_spora": "320.000 RSD", "prvi_rok": "2026-12-15",
            "rok_opis": "Rok za tuzbu", "potrebni_dokumenti": ["Ugovor o radu", "Platne liste"]}
mp.setattr(_INT, "_call_ekstrakcija", _ekstrakcija)
mp.setattr(D, "_pozovi_kriticara", _kriticar)
mp.setattr(QG, "evaluate_draft_quality", _kvalitet)
mp.setattr(R, "retrieve_documents", lambda *a, **kw: (["Zakon o radu, Član 185: Rešenje o otkazu se dostavlja zaposlenom..."], {}))
api.limiter.enabled = False

from fastapi.responses import JSONResponse  # noqa: E402


@api.app.post("/__osb003/obradi", include_in_schema=False)
async def _obradi():
    from shared.intake_worker import IntakeWorker
    poslova = 0
    while await IntakeWorker(worker_id="osb003-browser")._tick():
        poslova += 1
    rez = []
    for _ in range(8):
        r = await __import__("services.event_bus", fromlist=["x"]).dispatch_pending_events()
        rez.append(r)
        if not any(e.get("dispatched_at") is None for e in BAZA.tabele.get("events", [])):
            break
    return JSONResponse({"poslova": poslova, "greske": sum(x.get("greske", 0) for x in rez)})


@api.app.get("/__osb003/stanje", include_in_schema=False)
async def _stanje():
    t = BAZA.tabele
    return JSONResponse({
        "predmeti": len(t.get("predmeti", [])), "klijenti": len(t.get("klijenti", [])), "veze": len(t.get("predmet_klijenti", [])),
        "dokumenti": len(t.get("predmet_dokumenti", [])), "tvrdnje": len(t.get("predmet_dokazi", [])),
        "akcije_otvorene": len([a for a in t.get("case_actions", []) if a.get("status") == "open"]),
        "genome_verzije": sorted({(p.get("case_dna") or {}).get("verzija") for p in t.get("predmeti", []) if (p.get("case_dna") or {}).get("verzija")}),
        "vlasnici": sorted({r.get("user_id") or r.get("uploaded_by") for x in ("predmeti", "klijenti", "predmet_dokumenti", "predmet_dokazi")
                            for r in t.get(x, [])} - {None}),
        "nedispecovano": len([e for e in t.get("events", []) if e.get("dispatched_at") is None]),
        "hronologija": len(t.get("predmet_hronologija", [])),
        "dokumenti_po_predmetu": sorted([sum(1 for d in t.get("predmet_dokumenti", []) if d.get("predmet_id") == p.get("id"))
                                         for p in t.get("predmeti", [])]),
        "pozivi_modela": list(POZIVI_MODELA), "spoljni_pokusaji": len(SPOLJNI_POKUSAJI),
        "autonomy_upisi": len([z for z in BAZA.dnevnik if z["tabela"].startswith("autonomy")
                               and z["radnja"] in ("insert", "update", "upsert", "delete", "rpc")]),
    })


uvicorn.run(api.app, host="127.0.0.1", port=PORT, lifespan="off", log_level="warning", access_log=False)
