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
# VCR001 T03 (samo uz VX_GENOME_IZVORI=1): Genome navodi IZVOR („DOK-01“) za ključni datum i za jedan aktivan rok
# za 5 dana — da browser test vidi izvor u hronologiji i akciju „rok čeka potvrdu“. Ostali e2e ostaju nepromenjeni.
if os.environ.get("VX_GENOME_IZVORI") == "1":
    import copy as _copy, datetime as _dt  # noqa: E402
    import routers.case_dna as _CD  # noqa: E402
    from tests import ns006_realni_predmet as _RP  # noqa: E402
    async def _genome_izvori(client, combined, n):
        g = _copy.deepcopy(_RP._genome(0, False, 0, 0))
        for _p in ("verzija", "_analiza_osnov", "_genome_docs_count", "_genome_docs_preskoceno", "_dokumenti_bez_teksta", "_verifikacija"):
            g.pop(_p, None)
        g["datumi_kljucni"] = [{"opis": "Uručenje rešenja o otkazu", "datum": "2025-03-17", "znacaj": "kriticno", "lokacija": "DOK-01 str.1"}]
        _rok = (_dt.date.today() + _dt.timedelta(days=5)).isoformat()
        g["rokovi_kriticni"] = [{"naziv": "Rok za žalbu", "datum": _rok, "opis": "Žalba na rešenje", "status": "aktivan", "lokacija": "DOK-01 str.1"}]
        return json.dumps(g, ensure_ascii=False)
    mp.setattr(_CD, "_pozovi_genome_api", _genome_izvori)
# VCR002 T07 (samo uz VX_AGENTI=1): savetnici — zamenjen je SAMO poziv modela (/run i niz: `_pozovi_agent_api`,
# paralelno: `_pozovi_para_api`). Beleži se agent i da li je izlaz prethodnog koraka stigao unutar granice poverenja.
# Kredit: politika 1 kredit po pozivu i stanje 100 (bez ovoga lažna baza nema `user_credits`, pa provera budžeta = 402).
if os.environ.get("VX_AGENTI") == "1":
    import routers.multi_agent as _MA  # noqa: E402
    import shared.usage as _US  # noqa: E402

    def _agent_odgovor(system):
        ag = next(a for a, c in _MA._AGENTS.items() if c["system"] == system)
        return ag, {"research": "## OSNOV\nOdgovornost poslodavca uređuje član 185 Zakona o radu.",
                    "litigation": "## SLABOSTI\nProtivnik će osporiti dostavu; videti član 999 Zakona o radu.",
                    "intake": "## TIP PREDMETA\nRadni spor — poništaj rešenja o otkazu.",
                    "drafting": "## NACRT\nTUŽBA radi poništaja rešenja o otkazu.\n⚠️ Ovaj nacrt generisala je AI."}.get(ag, "Odgovor.")

    def _agent_sync(client, system, user_msg):
        ag, t = _agent_odgovor(system)
        POZIVI_MODELA.append("agent:%s:%s" % (ag, "granica" if "VINDEX_NEPOVERLJIVO_IZLAZ_PRETHODNOG_SAVETNIKA" in user_msg else "-"))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=t))])

    async def _agent_async(oai, system, base_msg):
        ag, t = _agent_odgovor(system)
        POZIVI_MODELA.append("para:%s" % ag)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=t))])

    async def _politika_agenti(feature):
        return {"aktivno": True, "status": "ACTIVE", "feature_type": "CORE", "min_plan": "free", "krediti": 1}

    async def _stanje_kredita(uid, email):
        return 100
    mp.setattr(_MA, "_pozovi_agent_api", _agent_sync)
    mp.setattr(_MA, "_pozovi_para_api", _agent_async)
    mp.setattr(_US, "get_policy", _politika_agenti)
    mp.setattr(_US.UsageService, "balance", staticmethod(_stanje_kredita))
    BAZA.naplaceno_jedinica = []
    _consume_harness = _US.UsageService.consume

    async def _naplati_jedinice(*a, **kw):
        BAZA.naplaceno_jedinica.append(int(kw.get("multiplier") or 1))
        return await _consume_harness(*a, **kw)
    mp.setattr(_US.UsageService, "consume", staticmethod(_naplati_jedinice))
mp.setattr(D, "_pozovi_kriticara", _kriticar)
mp.setattr(QG, "evaluate_draft_quality", _kvalitet)
mp.setattr(R, "retrieve_documents", lambda *a, **kw: (["Zakon o radu, Član 185: Rešenje o otkazu se dostavlja zaposlenom..."], {}))
api.limiter.enabled = False
# VCR001 T03: harness gasi `log_action`; lanac odluka o rokovima (FAZA 6.5) JE audit_immutable (INSERT-only, `seq`) —
# bez upisa potvrda roka vraća 503. Ovde se upisuje u bazu u memoriji (harness emulira `seq`).
import shared.audit_immutable as _AUD  # noqa: E402
async def _log_action(action, user_id=None, resource_type=None, resource_id=None, ip=None, metadata=None, correlation_id=None):
    r = BAZA.table("audit_immutable").insert({"action": action, "user_id": user_id, "resource_type": resource_type,
                                              "resource_id": resource_id, "metadata": metadata or {}}).execute()
    return (r.data or [{}])[0].get("id") or "ok"
mp.setattr(_AUD, "log_action", _log_action)

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


# OCR001 — kvarovi na granici baze za browser test oporavka prikačivanja (frontend-v2-ng/tests/live-prijem-oporavak-e2e.mjs).
# `kvar`: {"tabela", "radnja": "insert"|"*", "ukljucen"} → PostgREST statement timeout za tu radnju nad tom tabelom.
# `zauzece`: {"starost_s"} → poslednjem intake poslu postavlja `finalizing_at` (kao proces ubijen posle zauzeća).
from tests import ns005_harness as _H  # noqa: E402
_KVAR: dict = {}
_izvrsi = _H._Upit.execute


def _izvrsi_sa_kvarom(self):
    k = _KVAR.get(self.t)
    if k and (k == "*" or self.radnja[0] == k):
        raise Exception('{"code": "57014", "message": "canceling statement due to statement timeout"}')
    return _izvrsi(self)


mp.setattr(_H._Upit, "execute", _izvrsi_sa_kvarom)


@api.app.post("/__osb003/kvar", include_in_schema=False)
async def _kvar(z: dict):
    if z.get("ukljucen"):
        _KVAR[z["tabela"]] = z.get("radnja") or "*"
    else:
        _KVAR.pop(z.get("tabela"), None)
    return JSONResponse({"kvarovi": sorted(_KVAR)})


@api.app.post("/__osb003/zauzece", include_in_schema=False)
async def _zauzece(z: dict):
    from datetime import datetime, timedelta, timezone
    poslovi = BAZA.tabele.get("intake_jobs", [])
    if not poslovi:
        return JSONResponse({"ok": False})
    posao = sorted(poslovi, key=lambda j: j.get("created_at") or "")[-1]
    posao["finalizing_at"] = (datetime.now(timezone.utc) - timedelta(seconds=int(z.get("starost_s", 0)))).isoformat()
    return JSONResponse({"ok": True})


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
        "poslovi_prikaceni": len([j for j in t.get("intake_jobs", []) if j.get("assimilation_complete")]),
        "poslovi_zauzeti": len([j for j in t.get("intake_jobs", []) if j.get("finalizing_at") and not j.get("assimilation_complete")]),
        "hronologija": len(t.get("predmet_hronologija", [])),
        "dokumenti_po_predmetu": sorted([sum(1 for d in t.get("predmet_dokumenti", []) if d.get("predmet_id") == p.get("id"))
                                         for p in t.get("predmeti", [])]),
        "pozivi_modela": list(POZIVI_MODELA), "spoljni_pokusaji": len(SPOLJNI_POKUSAJI),
        "naplate": len(getattr(BAZA, "naplate", [])),
        "naplaceno_jedinica": sum(getattr(BAZA, "naplaceno_jedinica", [])),
        "idempotencija": sorted("%s:%s" % (z.get("path"), z.get("state")) for z in t.get("v2_mutation_idempotency", [])
                                if str(z.get("path", "")).startswith("/api/agents/")),
        "autonomy_upisi": len([z for z in BAZA.dnevnik if z["tabela"].startswith("autonomy")
                               and z["radnja"] in ("insert", "update", "upsert", "delete", "rpc")]),
    })


uvicorn.run(api.app, host="127.0.0.1", port=PORT, lifespan="off", log_level="warning", access_log=False)
