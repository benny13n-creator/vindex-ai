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
# DEFAULT-i iz migracije 088 (baza u memoriji ih inače ne zna; prava baza ih upisuje sama) — isto kao t06 fixture
BAZA.podrazumevano.setdefault("staging_memory", {}).update({"status": "pending", "is_lawyer_approved": False,
                                                           "pinecone_indexed": False, "quality_detail": {}, "naziv": ""})
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
    from tests.nacrt_json_zamena import kao_json as _kao_json  # noqa: E402
    mp.setattr(_MA, "_pozovi_nacrt_api", _kao_json(_agent_sync, bez_pravila=True))   # C3b: nacrt iz spisa = JSON
    if os.environ.get("VX_NACRT_C3B") == "1":
        # MIR001 C3b FINAL CLOSURE (live-c3b-usvajanje-e2e.mjs): AI predlog sa AUTENTIČNIM izvodom iz DOK-07 („Sud prihvata
        # predlog za dopunu vestacenja.“) i POGREŠNIM tumačenjem (sud „odbio“), tačnom stavkom i upozorenjem AI.
        import re as _re  # noqa: E402

        def _nacrt_c3b(client, system, user_msg):
            POZIVI_MODELA.append("agent:drafting:c3b")
            m = _re.search(r"\[\[(PS-\d+)\]\] DOK-07 \| akter po tekstu: SUD \| vrsta \(kandidat\): SUD_PRIHVATA", user_msg)
            tekst = "\n\n".join([
                "PRIVREDNOM SUDU U PRIMERGRADU\nBroj predmeta: P 9901/2026",
                "Vestak u nalazu navodi da je uzrok prokisnjavanja neodgovarajuce izvedena hidroizolacija na spoju atike (DOK-05).",
                "Kako je sud odbio predlog za dopunu vestacenja [[%s]], dopuna vestacenja nije potrebna i tuzilac je ne predlaze."
                % (m.group(1) if m else "PS-99"),
                "Tuzilac osporava navode tuzenog iz izjasnjenja na nalaz (DOK-06) i smatra da je nalaz vestaka potpun i jasan.",
                "⚠️ Ovaj nacrt je izradila AI; mora ga pregledati advokat."])
            telo = json.dumps({"tekst_za_sud": tekst, "napomene_za_advokata": ["Proveriti iznos zahteva."]}, ensure_ascii=False)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=telo),
                                                                        finish_reason="stop")])
        mp.setattr(_MA, "_pozovi_nacrt_api", _nacrt_c3b)
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
        # QA-02: vrsta po dokumentu (naziv fajla je sintetički) + da li nosi oznaku ljudske odluke; broj audit zapisa ispravke.
        "vrste_predmeta": sorted("%s=%s%s" % (d.get("naziv_fajla"), d.get("tip_dokaza"),
                                              "*" if isinstance(d.get("ai_tags"), dict) and d["ai_tags"].get("_vrsta_advokat") else "")
                                 for d in t.get("predmet_dokumenti", [])),
        "vrste_prijema": sorted(str(d.get("document_type")) for d in t.get("intake_documents", [])),
        "ispravke_vrste_audit": len([a for a in t.get("audit_immutable", []) if a.get("action") == "dokument_vrsta_ispravljena"]),
        # MIR001 C3b: nacrti na pregledu — tip, status, sha256 teksta i zapis usvajanja (bez sadržaja teksta)
        "nacrti": [{"id": x.get("id"), "tip": x.get("tip"), "status": x.get("status"),
                    "sha256": __import__("hashlib").sha256((x.get("tekst") or "").encode("utf-8")).hexdigest(),
                    "usvajanje": {k: v for k, v in ((x.get("quality_detail") or {}).get("usvajanje") or {}).items()
                                  if k in ("verzija", "odobreno", "stavke", "procesne_tacke")},
                    "pinecone_indexed": x.get("pinecone_indexed")} for x in t.get("staging_memory", [])],
        "vektori": len(getattr(BAZA, "vektori", []) or []),
        "autonomy_upisi": len([z for z in BAZA.dnevnik if z["tabela"].startswith("autonomy")
                               and z["radnja"] in ("insert", "update", "upsert", "delete", "rpc")]),
    })


@api.app.get("/__osb003/zlatni", include_in_schema=False)
async def _zlatni():
    """N1 Golden Intake: relacije koje browser test proverava u bazi (identiteti i oznake, bez sadržaja dokumenata).
    `marker` je sintetička oznaka iz opisa spora, da se proveri da je opis sačuvan bez vraćanja celog teksta."""
    t = BAZA.tabele
    marker = "ZLATNI-7731"
    dok_posla = {d.get("id"): d.get("intake_job_id") for d in t.get("intake_documents", [])}
    return JSONResponse({
        "predmeti": [{"id": p.get("id"), "user_id": p.get("user_id"), "naziv": p.get("naziv"),
                      "opis_sacuvan": marker in (p.get("opis") or "")} for p in t.get("predmeti", [])],
        "klijenti": [{"id": k.get("id"), "user_id": k.get("user_id")} for k in t.get("klijenti", [])],
        "veze": [{"predmet_id": v.get("predmet_id"), "klijent_id": v.get("klijent_id")} for v in t.get("predmet_klijenti", [])],
        "dokumenti": [{"id": d.get("id"), "predmet_id": d.get("predmet_id"), "user_id": d.get("user_id"), "naziv_fajla": d.get("naziv_fajla"),
                       "posao": d.get("source_intake_job_id"), "ima_tekst": bool((d.get("tekst_sadrzaj") or "").strip())}
                      for d in t.get("predmet_dokumenti", [])],
        "poslovi": [{"id": j.get("id"), "uploaded_by": j.get("uploaded_by"), "status": j.get("status"), "predmet_id": j.get("predmet_id"),
                     "prikacen": bool(j.get("assimilation_complete")), "ime": j.get("original_filename")} for j in t.get("intake_jobs", [])],
        "prijem_dokumenti": [{"posao": d.get("intake_job_id"), "ocr_used": d.get("ocr_used")} for d in t.get("intake_documents", [])],
        "ispravke": [{"entity_id": e.get("id"), "posao": dok_posla.get(e.get("document_id")), "tip": e.get("entity_type"),
                      "original": e.get("value"), "ispravka": e.get("corrected_value")}
                     for e in t.get("extracted_entities", []) if e.get("corrected_value")],
        "rokovi": [{"predmet_id": h.get("predmet_id"), "vrsta": h.get("vrsta"), "stanje": h.get("stanje"), "izvor": h.get("izvor")}
                   for h in t.get("predmet_hronologija", [])],
    })


# QA-03: opcioni sintetički „stari zapisi“ ({tabela: [redovi]} iz JSON fajla u VX_OSB003_SEME), upisani pre pokretanja —
# za browser proveru prikaza naziva nad podacima kakvi već postoje u bazi. `GET /__osb003/seme` vraća iste kolone tih
# redova posle testa (dokaz da prikaz ništa nije menjao). Bez promenljive: ponašanje servera je nepromenjeno.
_SEME_PUT = os.environ.get("VX_OSB003_SEME")
if _SEME_PUT:
    with open(_SEME_PUT, encoding="utf-8") as _f:
        _SEME = json.load(_f)
    for _t, _redovi in _SEME.items():
        BAZA.table(_t).insert(_redovi).execute()

    @api.app.get("/__osb003/seme", include_in_schema=False)
    async def _seme():
        return JSONResponse({t: [{k: r.get(k) for k in redovi[0]} for r in BAZA.tabele.get(t, [])
                                 if r.get("id") in {x["id"] for x in redovi}] for t, redovi in _SEME.items()})


uvicorn.run(api.app, host="127.0.0.1", port=PORT, lifespan="off", log_level="warning", access_log=False)
