# -*- coding: utf-8 -*-
"""
Vindex AI — Copilot (Faza 4)

Orkestrator koji advokatu daje jedinstven chat interfejs nad svim postojećim
modulima. Ne dodaje nove AI modele — poziva postojeće servise interno.

POST /copilot/chat
  - Prihvata poruku + opcioni predmet_id
  - Detektuje nameru (intent detection)
  - Rutira na odgovarajući servis
  - Vraća strukturiran odgovor

Podržane namere:
  PRAVNO_PITANJE    → /api/pitanje (RAG zakon)
  SUDSKA_PRAKSA     → /api/praksa/search
  NACRT             → /api/nacrt (generisanje dokumenta)
  ANALIZA_PREDMETA  → /api/analiza
  ROKOVI            → /zastarelost/kalkulisi
  PRETRAGA          → /api/search
  STRATEGIJA        → /strategija/litigation (PRO)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService

logger = logging.getLogger("vindex.copilot")
router = APIRouter(tags=["copilot"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


@llm_retry
async def _pozovi_gpt4o_mini(oai, **kwargs):
    """Zajednički retry-zaštićeni poziv za sve GPT-4o-mini pozive u Copilot-u.

    FAZA CELINA 3 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške; 400/401 se NE ponavljaju.
    """
    return await oai.chat.completions.create(**kwargs)

_INTENT_SYSTEM = """Ti si detektor namere za srpski pravni AI asistent za advokate.
Na osnovu korisničke poruke, vrati SAMO jednu od sledećih reči (bez ikakvog drugog teksta):

PRAVNO_PITANJE — korisnik pita šta zakon kaže, koji član, kakvo je pravo, opšte pravno istraživanje
SUDSKA_PRAKSA — korisnik traži sudske odluke, presude, praksu VKS, apelacionih sudova
NACRT — korisnik traži da se napiše, generiše ili napravi dokument (tužba, ugovor, žalba, dopis, odluka...)
ANALIZA_PREDMETA — korisnik traži analizu, procenu predmeta, strategiju, šanse uspeha
PLAN — korisnik traži plan, korake, šta dalje, akcioni plan, naredne korake, šta treba uraditi
DODAJ_ROK — korisnik želi da doda, upiše ili zabeleži rok, ročište, termin, rok za dostavu
KREIRAJ_BELEŠKU — korisnik želi da napiše, zabeleži ili sačuva belešku, napomenu, podsetnik
POVEZI_KLIJENTA — korisnik želi da poveže, doda ili veže klijenta, stranku, protivnu stranu
ROKOVI — korisnik pita o rokovima, kalendarskim terminima (pitanje, ne akcija)
ZASTARELOST — korisnik pita o zastarelosti potraživanja, rokovima zastarelosti, da li je potraživanje zastarelo
CONFLICT_CHECK — korisnik pita o konfliktu interesa, suprotnoj strani, da li može da zastupa
BILLING_SAVET — korisnik pita o naplati, tarifi, bodovima, honoraru, koliko može da naplati
ROCISTE_PRIPREMA — korisnik traži pripremu za ročište, brifing, šta da kaže na sudu, cross-exam
IZVRSENJE — korisnik pita o izvršnom postupku, prinudnoj naplati, pljenidbi, izvršnom dužniku
NASLEDSTVO — korisnik pita o nasleđu, ostavini, testamentu, naslednicima, deobi zaostavštine
RADNI_SPOR — korisnik pita o otkazу, radnom pravu, mobbingu, otpremnini, radnom sporu
PRETRAGA — korisnik traži određenu osobu, predmet ili dokument u sistemu
PREDLOZI — korisnik pita šta treba da uradi sledeće, koji su prioriteti, šta mu nedostaje, pregled zadataka
NAPLATI_RADNJU — korisnik želi da naplati, obračuna, upiše radnju, sate, honorar, tarifa stavku
PRIKAŽI_TARIFU — korisnik pita koliko košta neka pravna radnja, tarifa, bodovi, cena, honorar AKS
OSTALO — ništa od navedenog

Primeri:
"Da li je zastarelo potraživanje iz 2019?" → ZASTARELOST
"Mogu li da zastupam i tužioca i tuženog?" → CONFLICT_CHECK
"Koliko mogu da naplatim za zastupanje na ročištu?" → BILLING_SAVET
"Pripremi me za sutra" → ROCISTE_PRIPREMA
"Kako da naplatim dug prinudno?" → IZVRSENJE
"Moj klijent je naslednik — šta može da zahteva?" → NASLEDSTVO
"Klijent je dobio otkaz — šta da radimo?" → RADNI_SPOR

Vrati SAMO jednu reč, ništa više."""

_INTENT_CHOICES = {
    "PRAVNO_PITANJE", "SUDSKA_PRAKSA", "NACRT",
    "ANALIZA_PREDMETA", "PLAN",
    "DODAJ_ROK", "KREIRAJ_BELEŠKU", "POVEZI_KLIJENTA",
    "ROKOVI", "ZASTARELOST", "CONFLICT_CHECK",
    "BILLING_SAVET", "ROCISTE_PRIPREMA", "IZVRSENJE",
    "NASLEDSTVO", "RADNI_SPOR",
    "PRETRAGA", "PREDLOZI",
    "NAPLATI_RADNJU", "PRIKAŽI_TARIFU",
    "OSTALO",
}

INTENT_LABELS = {
    "PRAVNO_PITANJE":  "Pravno istraživanje",
    "SUDSKA_PRAKSA":   "Sudska praksa",
    "NACRT":           "Generisanje dokumenta",
    "ANALIZA_PREDMETA":"Analiza predmeta",
    "PLAN":            "Akcioni plan",
    "DODAJ_ROK":       "Dodavanje roka",
    "KREIRAJ_BELEŠKU": "Kreiranje beleške",
    "POVEZI_KLIJENTA": "Povezivanje klijenta",
    "ROKOVI":          "Rokovi i termini",
    "ZASTARELOST":     "Zastarelost potraživanja",
    "CONFLICT_CHECK":  "Provera konflikta interesa",
    "BILLING_SAVET":   "Savet o naplati",
    "ROCISTE_PRIPREMA":"Priprema za ročište",
    "IZVRSENJE":       "Izvršni postupak",
    "NASLEDSTVO":      "Nasleđivanje i ostavina",
    "RADNI_SPOR":      "Radno pravo i spor",
    "PRETRAGA":        "Pretraga sistema",
    "PREDLOZI":        "Predlozi sledećih akcija",
    "NAPLATI_RADNJU":  "Unos naplatne radnje",
    "PRIKAŽI_TARIFU":  "AKS tarifa",
    "OSTALO":          "Opšto pitanje",
}

async def _oai_parse_json(system_prompt: str, user_content: str) -> str:
    """Patchable wrapper za GPT-4o-mini JSON parse pozive."""
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    r = await _pozovi_gpt4o_mini(
        oai,
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content[:500]},
        ],
        temperature=0,
        max_tokens=150,
        response_format={"type": "json_object"},
    )
    return r.choices[0].message.content or "{}"


_NAPLATA_PARSE_SYSTEM = """Iz korisničke poruke izvuci podatke za fakturisanje i vrati SAMO validan JSON.
Polja:
{
  "sati": <broj ili null — broj sati rada ako je naveden>,
  "tarifa_sifra": <"T01"–"T71" ili null — AKS šifra ako se prepoznaje>,
  "opis": <string — kratak opis radnje>,
  "iznos_rsd": <integer ili null — ako je korisnik naveo eksplicitan iznos u RSD/din>
}
Primeri mapiranja:
"naplati 2h konsultacija" → {"sati":2,"tarifa_sifra":"T17","opis":"Konsultacije","iznos_rsd":null}
"upiši tužbu" → {"sati":null,"tarifa_sifra":"T01","opis":"Tužba za novčano potraživanje","iznos_rsd":null}
"naplati 15000 din za ročište" → {"sati":null,"tarifa_sifra":"T10","opis":"Zastupanje na ročištu","iznos_rsd":15000}
"1.5 sat savetovanje" → {"sati":1.5,"tarifa_sifra":"T17","opis":"Usmena konsultacija","iznos_rsd":null}
Ako opis nije jasan stavi "Pravna radnja". Vrati SAMO JSON, bez objašnjenja."""


class CopilotReq(BaseModel):
    poruka: str = Field(..., min_length=3, max_length=4000)
    predmet_id: Optional[str] = None
    session_id: Optional[str] = None
    history: list[dict] = Field(default_factory=list, max_length=5)


async def _detect_intent(poruka: str) -> str:
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        r = await _pozovi_gpt4o_mini(
            oai,
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user",   "content": poruka[:500]},
            ],
            temperature=0,
            max_tokens=20,
        )
        intent = (r.choices[0].message.content or "").strip().upper()
        # NIGHT-008 (2026-08-09): this used to default to "OSTALO" — the LEAST
        # guarded branch. PRAVNO_PITANJE routes to ask_agent, which has
        # confidence gating, LOW-confidence refusal, the citation structural
        # guard, _verifikuj_pravne_greske and the mandatory DISCLAIMER. OSTALO
        # is bare gpt-4o-mini with none of that. So a garbled or truncated
        # classifier reply on a genuine legal question produced an ungrounded
        # answer, possibly with an invented article number, no source block and
        # no legal notice — visually identical to a guarded answer.
        #
        # The except branch below already fails toward PRAVNO_PITANJE; the
        # success branch defaulted the opposite way. Both now fail safe.
        return intent if intent in _INTENT_CHOICES else "PRAVNO_PITANJE"
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[COPILOT] intent detection greška: %s — fallback PRAVNO_PITANJE", e)
        return "PRAVNO_PITANJE"


async def _load_predmet_context(predmet_id: str, user_id: str) -> str:
    """Učitava naziv+opis predmeta za kontekst copilota."""
    try:
        supa = _get_supa()
        r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("naziv, opis, tip, status")
                .eq("id", predmet_id)
                .eq("user_id", user_id)
                .single()
                .execute()
        )
        if r.data:
            d = r.data
            return f"[Predmet: {d.get('naziv','')} | {d.get('tip','')} | {d.get('status','')}]\n{d.get('opis','')}"
    except Exception as e:
        _sentry_capture(e)
    return ""


async def _handle_pravno_pitanje(poruka: str, predmet_ctx: str, user: dict, history: list | None = None) -> dict:
    """Poziva RAG zakon pipeline direktno. ask_agent interno radi retrieve — ne pre-fetchujemo."""
    from main import ask_agent as _ask
    from shared.ai_provenance import case_context as _ai_case_ctx
    try:
        q = f"{predmet_ctx}\n\n{poruka}".strip() if predmet_ctx else poruka
        # Project Phoenix (2026-08-03) — Phase 8: main.py::ask_agent was one
        # of Mission Migration's 3 deferred items ("too deep/large to
        # migrate safely"); re-verified this mission as a single flat
        # function, no case scope by design (matches Strategy Engine's own
        # precedent of calling case_context() with predmet_id=None) --
        # migrated here since Phoenix's own reliability work touched this
        # exact call site.
        with _ai_case_ctx(module_name="ask_agent", operation_name="pravno_pitanje"):
            rezultat = await asyncio.to_thread(_ask, q, history or None)
        if isinstance(rezultat, dict):
            odgovor = rezultat.get("data") or rezultat.get("message") or ""
            uspesno = rezultat.get("status") != "error"
        else:
            odgovor = str(rezultat)
            uspesno = True
        if not odgovor.strip():
            odgovor = "Sistem nije mogao da obradi pitanje. Pokušajte ponovo."
        if uspesno and odgovor.strip():
            from shared.audit_immutable import log_action
            asyncio.create_task(log_action(
                action="copilot_pravno_pitanje", user_id=user.get("user_id"),
                resource_type="pravno_pitanje", resource_id=None,
            ))
        # BLACKSWAN-HIGH-005: "uspesno" surfaced in the return dict (not just a local var)
        # so copilot_chat can refund on a genuine ask_agent failure instead of charging a
        # credit for a disclaimer message dressed up as a real answer, HTTP 200 either way.
        return {"tip": "PRAVNO_PITANJE", "odgovor": odgovor, "uspesno": uspesno}
    except Exception as e:
        _sentry_capture(e)
        logger.error("[COPILOT] pravno_pitanje greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri pravnom istraživanju.")


async def _handle_sudska_praksa(poruka: str) -> dict:
    """Poziva Pinecone praksa namespace."""
    from app.services.retrieve import retrieve_sudska_praksa as _rp
    try:
        results = await asyncio.to_thread(_rp, poruka, top_k=5)
        return {"tip": "SUDSKA_PRAKSA", "presude": results}
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[COPILOT] sudska_praksa greška: %s — fallback", e)
        return {
            "tip": "SUDSKA_PRAKSA",
            "odgovor": "Upotrebite modul Sudska praksa za detaljnu pretragu.",
            "presude": [],
        }


async def _handle_nacrt(poruka: str, predmet_ctx: str, user: dict) -> dict:
    """Vraća uputstvo za nacrt — korisnik mora otvoriti modul za draft."""
    return {
        "tip": "NACRT",
        "odgovor": (
            "Prepoznao sam zahtev za generisanje dokumenta. "
            "Otvorite tab **Nacrte** i odaberite tip dokumenta — sistem će "
            "iskoristiti kontekst ovog predmeta automatski."
        ),
        "akcija": "otvori_nacrt",
    }


async def _handle_pretraga(poruka: str, user_id: str) -> dict:
    """Cross-entity search."""
    supa = _get_supa()
    q = poruka[:100]
    results = []
    for table, fields, tip, url_prefix in [
        ("klijenti",          "id, ime, prezime, firma", "klijent",  "/klijenti/"),
        ("predmeti",          "id, naziv",                "predmet",  "/predmeti/"),
        ("predmet_beleske",   "id, sadrzaj, predmet_id",  "beleska",  "/predmeti/"),
    ]:
        try:
            filter_col = "sadrzaj" if table == "predmet_beleske" else ("naziv" if table == "predmeti" else "ime")
            r = await asyncio.to_thread(
                lambda t=table, f=fields, c=filter_col: supa.table(t).select(f).eq("user_id", user_id).ilike(c, f"%{q}%").limit(3).execute()
            )
            for row in (r.data or []):
                naziv = row.get("naziv") or row.get("sadrzaj","")[:80] or f"{row.get('ime','')} {row.get('prezime','')}".strip()
                url = url_prefix + row.get("predmet_id", row.get("id", ""))
                results.append({"tip": tip, "naziv": naziv, "url": url})
        except Exception as e:
            _sentry_capture(e)
    return {"tip": "PRETRAGA", "rezultati": results}


async def _handle_analiza_predmeta(poruka: str, predmet_id: str, user_id: str) -> dict:
    """
    Orkestrator za analizu predmeta — automatski učitava workspace podatke i
    sintetiše procenu snage pozicije bez da korisnik zna koji endpoint se zove.
    """
    supa = _get_supa()

    # Parallel fetch of all case data
    # Project Synapse (2026-08-03): "case_dna" added to this select -- a full
    # cognitive audit found this handler was a 4th independent case-strength
    # synthesis path (alongside Case Genome, the AI Briefing, and Matter
    # Intelligence), never reading the Case Genome analysis that's often
    # already been computed for the exact same case. This lets the one GPT
    # call below build on that existing analysis instead of re-deriving it
    # from raw rows blind to it -- purely additive context, no restructuring.
    # Program Tau, Master Sprint 002 (2026-08-06) -- Phase 1's own
    # CONTEXT_BUILDER_REGISTRY.md found this handler's document query selected
    # `naziv_fajla,status` ONLY -- GPT knew filenames existed but never saw a
    # single word of content. Extended to fetch real text so the Document
    # Visibility Engine (shared/case_context.py) below can build real excerpts
    # -- genome/case_actions logic (Sigma Sprint 003/004) is unchanged, that
    # was not the gap this sprint found here.
    # Lambda Certification 003 (2026-08-06) -- Horizontal Privilege
    # Escalation fork found (NEEDS-DEEPER-LOOK, not exploitable today,
    # upheld by the Adversarial Certification fork's own independent
    # re-trace) that the ownership-scoped `predmeti` query used to run
    # INSIDE the same asyncio.gather() as the 4 sibling queries below --
    # another tenant's full document text/notes/timeline transited this
    # process's memory for every guessed predmet_id before the
    # `if not pred:` check ran, even though it was already discarded on a
    # miss. Ownership is now checked first, alone; siblings only fire once
    # confirmed.
    try:
        pred_r = await asyncio.to_thread(
            lambda: supa.table("predmeti").select("naziv,opis,tip,status,case_dna").eq("id", predmet_id).eq("user_id", user_id).single().execute()
        )
        pred = pred_r.data or {}
    except Exception:
        # .single() raises (PostgREST 0-rows error) for a foreign/missing
        # predmet_id -- same as the pre-fix return_exceptions=True path.
        pred = {}
    if not pred:
        return {
            "tip": "ANALIZA_PREDMETA",
            "odgovor": "Predmet nije pronađen ili nemate pristup. Proverite da li ste otvorili predmet pre analize.",
        }

    beleske_r, dok_r, hron_r, istorija_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_beleske").select("sadrzaj").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(5).execute()),
        # Program Lambda, Certification 006 (2026-08-07) -- Chaos Engineer
        # fork found this query pulled `tekst_sadrzaj` (full document text)
        # for EVERY document in the case, unconditionally, before
        # `_select_documents()` below ever bounds the set to ~5 -- the exact
        # unbounded-resource-exhaustion pattern `shared/case_context.py::
        # _fetch_raw` already fixed for its own callers (Lambda Master
        # Sprint 001). Metadata-only here now; text is fetched separately,
        # below, only for the bounded subset actually selected -- reusing
        # that same fix's own `_fetch_document_texts` helper, not a new one.
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("id, naziv_fajla, created_at, status, redni_broj").eq("predmet_id", predmet_id).order("redni_broj").execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select("dogadjaj,datum_iso,vaznost").eq("predmet_id", predmet_id).order("datum_iso").limit(8).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija").select("pitanje,odgovor").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(2).execute()),
        return_exceptions=True,
    )

    beleske = beleske_r.data if not isinstance(beleske_r, Exception) else []
    dok = dok_r.data if not isinstance(dok_r, Exception) else []
    hron = hron_r.data if not isinstance(hron_r, Exception) else []
    istorija = istorija_r.data if not isinstance(istorija_r, Exception) else []

    # Program Tau, Master Sprint 003 (2026-08-06) -- "Canonical AI Decision
    # Boundary". AI_DECISION_SURFACE_MAP.md found "slabosti" (risk, never
    # cross-checked against identify_case_problems) and "verovatnoca_uspeha"
    # (an independently GPT-invented case-strength number duplicating
    # Genome's own snaga_predmeta_procent) had zero canonical owner. Both
    # removed from what GPT is asked -- computed deterministically below from
    # Genome instead (see the override block after the GPT call). "nedostaju"/
    # "sledeci_korak" stay in the schema because they're still asked of GPT
    # as a fallback shape, but are unconditionally overridden below too (Sigma
    # 003/004's own overrides were conditional -- this sprint closes that gap).
    _SYNTH_SYSTEM = (
        "Ti si iskusni srpski pravni strateg. Sintetiši sve dostupne podatke i vrati ISKLJUČIVO JSON bez teksta van JSON-a:\n"
        '{"procena": str (1 konkretna rečenica — ocena snage pozicije),\n'
        ' "prednosti": [str] (max 4, konkretni faktori)}\n'
        "Ne halucinuj zakone ni činjenice koje nisu u podacima. "
        "Ako je dole dat CASE GENOME (već izračunata analiza ovog predmeta), gradi na njemu — "
        "ne ponavljaj istu analizu iz nule i ne izmišljaj suprotnu ocenu bez razloga."
    )

    # Project Synapse (2026-08-03) — vidi napomenu iznad. Kompaktan rezime
    # Case Genome-a (ako postoji i nije greška) kao dodatni kontekst.
    genome = (pred.get("case_dna") or {}) if pred else {}
    genome_ctx = ""
    if genome and not genome.get("greska"):
        _gi = genome.get("pravna_teorija") or {}
        _nt = genome.get("najslabija_tacka") or {}
        _snaga = genome.get("snaga_predmeta_procent")
        _delovi = []
        if _gi.get("sustina_spora"):
            _delovi.append(f"Suština: {_gi['sustina_spora']}")
        if _snaga is not None:
            _delovi.append(f"Snaga predmeta: {_snaga}% ({genome.get('snaga_predmeta','')})")
        if _nt.get("rizik"):
            _delovi.append(f"Najslabija tačka: {_nt['rizik']}")
        _ned = genome.get("nedostaje") or []
        if _ned:
            _delovi.append("Nedostajući dokazi: " + "; ".join(n.get("dokument", "") for n in _ned[:3] if n.get("dokument")))
        if _delovi:
            genome_ctx = "CASE GENOME (već izračunata analiza ovog predmeta):\n" + "\n".join(_delovi)

    # Program Tau, Master Sprint 002 -- Document Visibility Engine reused
    # (shared/case_context.py), not a parallel sampler: Layer 4 selection
    # picks which documents to show (recency + stride sample across ALL of
    # them, not a static head-slice), Layer 4 within-doc excerpting reuses
    # cross_doc.py's own stride sampler. Any document not selected here is
    # still individually retrievable via get_document_full_text -- never
    # permanently invisible, just not in THIS prompt's bounded budget.
    from shared.case_context import _select_documents, _excerpt, _fetch_document_texts
    _dok_included, _dok_not_included = _select_documents(dok)
    _dok_included = _dok_included[:5]  # copilot is a lightweight assistant, not a full case dossier -- smaller budget than case_commander's own
    if _dok_included:
        _tekst_by_id = await _fetch_document_texts([d["id"] for d in _dok_included if d.get("id")], predmet_id, supa)
        _dok_delovi = []
        for _d in _dok_included:
            _izvod, _ = _excerpt(_tekst_by_id.get(_d.get("id"), ""), budget=800)
            _dok_delovi.append(f"  - {_d.get('naziv_fajla','')}: {_izvod}" if _izvod else f"  - {_d.get('naziv_fajla','')} (bez teksta)")
        dokumenti_blok = "Dokumenti u dosijeu:\n" + "\n".join(_dok_delovi)
        if _dok_not_included:
            dokumenti_blok += f"\n  (+ još {len(_dok_not_included)} dokumenata u dosijeu, nisu prikazani ovde)"
    else:
        dokumenti_blok = "Dokumenti u dosijeu: nema"

    ctx = "\n".join([
        f"Predmet: {pred.get('naziv','')} | Tip: {pred.get('tip','')} | Status: {pred.get('status','')}",
    ] + ([genome_ctx] if genome_ctx else []) + [
        f"Opis: {(pred.get('opis') or '')[:500]}",
        dokumenti_blok,
        f"Beleške: {' | '.join((b.get('sadrzaj','') or '')[:80] for b in beleske[:3]) or 'nema'}",
        f"Hronologija: {' | '.join((h.get('dogadjaj','') or '')[:80]+((' ('+h.get('datum_iso','')+')') if h.get('datum_iso') else '') for h in hron[:5]) or 'nema'}",
        f"Pitanje: {poruka}",
    ] + ([f"Prethodna analiza: {istorija[0].get('odgovor','')[:300]}"] if istorija else []))

    from openai import AsyncOpenAI
    import json as _json
    from shared.ai_provenance import case_context as _ai_case_ctx
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        with _ai_case_ctx(
            predmet_id=predmet_id, module_name="copilot", operation_name="analiza_predmeta",
            knowledge_sources=([d.get("naziv_fajla") for d in dok] if dok else []),
        ):
            resp = await _pozovi_gpt4o_mini(
                oai,
                model="gpt-4o-mini", temperature=0.1, max_tokens=1200,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYNTH_SYSTEM},
                    {"role": "user",   "content": ctx},
                ],
            )
        result = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        _sentry_capture(e)
        logger.error("[COPILOT-ANALIZA] OpenAI greška: %s", e)
        return {"tip": "ANALIZA_PREDMETA", "odgovor": "Greška pri generisanju analize."}

    # Mission Ledger (2026-08-03) — Audit Link Completion (Phase 4): trajan
    # audit trag za ovaj AI poziv, correlation_id automatski nasleđen iz istog
    # case_context() koji je gore već omotao GPT poziv (isti id kao AI
    # Provenance red za ovaj poziv).
    from shared.audit_immutable import log_action
    asyncio.create_task(log_action(
        action="copilot_analiza_predmeta", user_id=user_id,
        resource_type="predmet", resource_id=predmet_id,
    ))

    # Program Sigma, Master Sprint 003 (2026-08-06) — Forensic Discovery
    # finding, fixed immediately: this handler's own "nedostaju" field was an
    # INDEPENDENT GPT-generated list, the 2nd of 3 competing "what's missing"
    # generators found this sprint (alongside Genome's own case_dna.nedostaje
    # and _handle_plan_predmeta's own, below) — a live violation of this
    # program's own "jedan mehanizam postaje vlasnik" rule. Genome's own
    # nedostaje[] is already read into this prompt's own context (genome_ctx
    # above) for the GPT-generated fields that legitimately benefit from it
    # (procena/prednosti/slabosti/sledeci_korak) — but "nedostaju" itself is
    # now sourced DIRECTLY from Genome via shared/gap_engine.py, matching
    # routers/case_intelligence.py's own AI Briefing (already correctly reads
    # genome.get("nedostaje") directly, never re-derives). Falls back to the
    # GPT's own result only when Genome hasn't run yet for this case (no
    # canonical source available) — never silently empty for an established case.
    from shared.gap_engine import missing_evidence_labels
    _genome_nedostaju = missing_evidence_labels(genome, limit=4)

    # Program Tau, Master Sprint 003 (2026-08-06) -- Sigma 004's own override
    # below was CONDITIONAL: GPT's own "hitan|normalan" guess survived
    # whenever case_actions had nothing open. AI_DECISION_SURFACE_MAP.md
    # named this the exact "GPT may never redefine" gap this sprint exists to
    # close -- the override is now unconditional; an honest "no open action"
    # state replaces the GPT fallback (GPT is no longer even asked for this
    # field -- see the narrowed _SYNTH_SYSTEM above).
    from shared.case_readiness import top_open_action
    _oa_r = await asyncio.to_thread(
        lambda: supa.table("case_actions").select("razlog,prioritet,rok,status")
            .eq("predmet_id", predmet_id).eq("status", "open").execute()
    )
    _top = top_open_action(_oa_r.data or [])
    if _top:
        _sledeci_korak = {
            "opis": _top.get("razlog") or "",
            "rok": _top.get("rok") or "",
            "prioritet": "hitan" if _top.get("prioritet") in ("critical", "high") else "normalan",
        }
    else:
        _sledeci_korak = {"opis": "Nema otvorenih akcija u Case Actions za ovaj predmet.", "rok": "", "prioritet": "normalan"}

    # "slabosti" (risk, was pure GPT invention, never cross-checked) and
    # "verovatnoca_uspeha" (duplicated Genome's own snaga_predmeta_procent
    # under a different name) -- both computed from Genome directly now,
    # reusing shared/gap_engine.py rather than a new detector. Honestly empty/
    # None when Genome hasn't run, never a GPT guess filling the gap.
    from shared.gap_engine import gaps_from_contradictions, gaps_from_genome_nedostaje
    _weakness_gaps = gaps_from_contradictions(genome) + gaps_from_genome_nedostaje(genome)
    _slabosti = [g["razlog"] for g in _weakness_gaps[:4] if g.get("razlog")]
    _verovatnoca_uspeha = genome.get("snaga_predmeta_procent") if genome and not genome.get("greska") else None

    # Operation Living System (Wave 1, AI reasoning chain, reproduced): unlike
    # digital_twin.py/court_predictor.py/hearing_cc.py's own success-probability fields,
    # this one was never capped to shared/case_readiness.py's CAP_BY_READINESS -- a case
    # with an open critical case_actions row (canonical readiness=CRITICAL_GAP, capped at
    # 50 everywhere else) could still show this field at Genome's own uncapped
    # snaga_predmeta_procent (e.g. 82%), a direct, reproducible contradiction between two
    # AI surfaces a lawyer would consult back-to-back for the same case. Reuses _oa_r
    # (already fetched above for _sledeci_korak) -- no new query, no new algorithm.
    if isinstance(_verovatnoca_uspeha, (int, float)):
        from shared.case_readiness import compute_case_readiness, CAP_BY_READINESS
        _readiness_status = compute_case_readiness(_oa_r.data or []).get("status")
        _cap = CAP_BY_READINESS.get(_readiness_status)
        if _cap is not None and _verovatnoca_uspeha > _cap:
            _verovatnoca_uspeha = _cap

    return {
        "tip":               "ANALIZA_PREDMETA",
        "predmet":           pred.get("naziv", ""),
        "procena":           result.get("procena", ""),
        "prednosti":         result.get("prednosti", []),
        "slabosti":          _slabosti,
        "nedostaju":         _genome_nedostaju if _genome_nedostaju else result.get("nedostaju", []),
        "sledeci_korak":     _sledeci_korak,
        "verovatnoca_uspeha": _verovatnoca_uspeha,
    }


async def _handle_plan_predmeta(poruka: str, predmet_id: str, user_id: str) -> dict:
    """
    Agentic PLAN — interno poziva rokove, praksu i strategiju,
    a zatim sintetiše strukturiran akcioni plan sa fazama i koracima.
    """
    supa = _get_supa()

    # Program Sigma, Master Sprint 003 (2026-08-06): case_dna added to this
    # select -- this handler previously had ZERO Genome awareness (unlike
    # _handle_analiza_predmeta above, which already reads it), making its own
    # "nedostaje" field the 3rd fully-independent GPT "what's missing"
    # generator found this sprint. Same fix as that handler: read below.
    # Program Tau, Master Sprint 002 (2026-08-06): same fix as
    # _handle_analiza_predmeta above -- real document text instead of
    # filenames only.
    # Lambda Certification 003 (2026-08-06) -- same fix as
    # _handle_analiza_predmeta above: ownership check hoisted out of the
    # gather so sibling queries never fire for an unowned predmet_id.
    try:
        pred_r = await asyncio.to_thread(
            lambda: supa.table("predmeti").select("naziv,opis,tip,status,case_dna").eq("id", predmet_id).eq("user_id", user_id).single().execute()
        )
        pred = pred_r.data or {}
    except Exception:
        pred = {}
    if not pred:
        return {"tip": "PLAN", "odgovor": "Predmet nije pronađen. Otvorite predmet pre kreiranja plana."}

    beleske_r, dok_r, hron_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_beleske").select("sadrzaj").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(4).execute()),
        # Program Lambda, Certification 006 (2026-08-07) -- same fix as
        # _handle_analiza_predmeta above: metadata-only, text fetched
        # separately for the bounded selected subset only.
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("id, naziv_fajla, created_at, status, redni_broj").eq("predmet_id", predmet_id).order("redni_broj").execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select("dogadjaj,datum_iso,vaznost").eq("predmet_id", predmet_id).order("datum_iso").execute()),
        return_exceptions=True,
    )

    dok = dok_r.data if not isinstance(dok_r, Exception) else []
    hron = hron_r.data if not isinstance(hron_r, Exception) else []
    beleske = beleske_r.data if not isinstance(beleske_r, Exception) else []

    from datetime import date
    today_iso = date.today().isoformat()
    urgentni = [h for h in hron if h.get("vaznost") == "kritičan" and (h.get("datum_iso") or "") >= today_iso]
    nadolazeci = sorted([h for h in hron if (h.get("datum_iso") or "") >= today_iso], key=lambda x: x.get("datum_iso", ""))[:6]

    # Alat 1: Sudska praksa (Pinecone)
    praksa_kontekst = ""
    try:
        from app.services.retrieve import retrieve_sudska_praksa as _rp
        _q = f"{pred.get('naziv','')} {pred.get('tip','')} {(pred.get('opis') or '')[:200]}"
        _matches = await asyncio.wait_for(asyncio.to_thread(_rp, _q, 5), timeout=6.0)
        if _matches:
            praksa_kontekst = "\n".join(
                f"- {m.get('metadata',{}).get('decision_number','?')}: {(m.get('metadata',{}).get('izreka_preview') or '')[:100]}"
                for m in _matches[:3]
            )
    except Exception as _pe:
        _sentry_capture(_pe)
        logger.warning("[COPILOT-PLAN] praksa greška: %s", _pe)

    # Program Tau, Master Sprint 003 (2026-08-06): "kriticni_rokovi" and
    # "upozorenja" removed from the schema below. AI_DECISION_SURFACE_MAP.md
    # found real predmet_hronologija rows (urgentni/nadolazeci, computed
    # above) were already fetched into context but the field RETURNED to the
    # caller was GPT's own restatement, not the real rows -- and "upozorenja"
    # overlapped Genome's own upozorenja[]/nedostaje[] domain with zero
    # cross-check. Both now computed deterministically below (see the
    # override block after the GPT call), reusing the same rows/Genome
    # fields already in this function rather than asking GPT to re-derive them.
    _PLAN_SYSTEM = (
        "Ti si srpski pravni strateg. Na osnovu stanja predmeta kreiraj konkretan akcioni plan. "
        "Vrati ISKLJUČIVO JSON bez teksta van JSON-a:\n"
        '{"cilj": str,\n'
        ' "faze": [{"naziv": str, "trajanje": str, "koraci": [\n'
        '   {"korak": str, "prioritet": "hitan|normalan|odlozen", "rok": str, "alat": "dokument|sud|klijent|praksa|interno"}]}],\n'
        ' "nedostaje": [{"stavka": str, "hitnost": "visoka|srednja|niska"}]}\n'
        "Maks 3 faze, maks 4 koraka po fazi. Ne koristi generičke fraze — budi konkretan za ovaj predmet."
    )

    # Program Tau, Master Sprint 002 -- Document Visibility Engine reused
    # (shared/case_context.py), see _handle_analiza_predmeta above for the
    # same pattern and its own rationale comment.
    from shared.case_context import _select_documents, _excerpt, _fetch_document_texts
    _plan_dok_included, _plan_dok_not_included = _select_documents(dok)
    _plan_dok_included = _plan_dok_included[:5]
    if _plan_dok_included:
        _plan_tekst_by_id = await _fetch_document_texts([d["id"] for d in _plan_dok_included if d.get("id")], predmet_id, supa)
        _plan_dok_delovi = []
        for _d in _plan_dok_included:
            _izvod, _ = _excerpt(_plan_tekst_by_id.get(_d.get("id"), ""), budget=800)
            _plan_dok_delovi.append(f"  - {_d.get('naziv_fajla','')}: {_izvod}" if _izvod else f"  - {_d.get('naziv_fajla','')} (bez teksta)")
        dokumenti_blok = "Dokumenti:\n" + "\n".join(_plan_dok_delovi)
        if _plan_dok_not_included:
            dokumenti_blok += f"\n  (+ još {len(_plan_dok_not_included)} dokumenata u dosijeu, nisu prikazani ovde)"
    else:
        dokumenti_blok = "Dokumenti: nema"

    ctx = "\n".join([
        f"Predmet: {pred.get('naziv','')} | Tip: {pred.get('tip','')} | Status: {pred.get('status','')}",
        f"Opis: {(pred.get('opis') or '')[:400]}",
        dokumenti_blok,
        f"Beleške: {' | '.join((b.get('sadrzaj','') or '')[:60] for b in beleske[:3]) or 'nema'}",
        f"Hitni rokovi: {' | '.join((h.get('dogadjaj','') or '')+'('+h.get('datum_iso','')+')' for h in urgentni[:3]) or 'nema'}",
        f"Nadolazeći: {' | '.join((h.get('dogadjaj','') or '')+'('+h.get('datum_iso','')+')' for h in nadolazeci[:5]) or 'nema'}",
        f"Relevantna praksa VKS: {praksa_kontekst or 'nije pronađena'}",
        f"Zahtev advokata: {poruka}",
    ])

    from openai import AsyncOpenAI
    import json as _json
    from shared.ai_provenance import case_context as _ai_case_ctx
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        with _ai_case_ctx(predmet_id=predmet_id, module_name="copilot", operation_name="plan_predmeta"):
            resp = await _pozovi_gpt4o_mini(
                oai,
                model="gpt-4o-mini", temperature=0.1, max_tokens=2000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _PLAN_SYSTEM},
                    {"role": "user",   "content": ctx},
                ],
            )
        result = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        _sentry_capture(e)
        logger.error("[COPILOT-PLAN] OpenAI greška: %s", e)
        return {"tip": "PLAN", "odgovor": "Greška pri generisanju plana."}

    # Mission Migration (2026-08-03) -- Audit Link Coverage: trajan audit trag,
    # correlation_id automatski nasleđen (v. case_context iznad).
    from shared.audit_immutable import log_action
    asyncio.create_task(log_action(
        action="copilot_plan_predmeta", user_id=user_id,
        resource_type="predmet", resource_id=predmet_id,
    ))

    # Program Sigma, Master Sprint 003 (2026-08-06) — same fix as
    # _handle_analiza_predmeta above: "nedostaje" now sourced from Genome via
    # shared/gap_engine.py instead of this handler's own previously fully
    # Genome-blind, independently-generated GPT list (the 3rd of 3 competing
    # "what's missing" generators found this sprint). Fallback to GPT's own
    # result only when Genome hasn't run yet for this case.
    from shared.gap_engine import missing_evidence_plan_items, gaps_from_contradictions, gaps_from_genome_nedostaje
    genome_pred = (pred.get("case_dna") or {}) if pred else {}
    _genome_nedostaje = missing_evidence_plan_items(genome_pred, limit=6)

    # "kriticni_rokovi" -- was GPT's own restatement of rows already fetched
    # above (urgentni/nadolazeci, both from predmet_hronologija). Now the real
    # rows themselves, formatted, not a GPT paraphrase of them.
    _rok_rows, _seen_dogadjaj = [], set()
    for h in (urgentni + nadolazeci):
        key = (h.get("dogadjaj"), h.get("datum_iso"))
        if key in _seen_dogadjaj:
            continue
        _seen_dogadjaj.add(key)
        _rok_rows.append({
            "naziv": h.get("dogadjaj") or "Rok",
            "datum": h.get("datum_iso") or "",
            "posledica_propustanja": "Kritičan rok -- moguć gubitak prava/roka." if h.get("vaznost") == "kritičan" else "",
        })
    _kriticni_rokovi = _rok_rows[:5]

    # "upozorenja" -- was GPT-invented, overlapping Genome's own
    # upozorenja[]/nedostaje[]/kontradikcije[] domain with zero cross-check.
    # Same Genome-derived treatment as _handle_analiza_predmeta's own
    # "slabosti" fix above.
    _upozorenja_gaps = gaps_from_contradictions(genome_pred) + gaps_from_genome_nedostaje(genome_pred)
    _upozorenja = [g["razlog"] for g in _upozorenja_gaps[:4] if g.get("razlog")]

    return {
        "tip":              "PLAN",
        "predmet":          pred.get("naziv", ""),
        "alati_koristeni":  ["rokovi", "sudska_praksa_vks", "strategija"],
        "cilj":             result.get("cilj", ""),
        "faze":             result.get("faze", []),
        "kriticni_rokovi":  _kriticni_rokovi,
        "nedostaje":        _genome_nedostaje if _genome_nedostaje else result.get("nedostaje", []),
        "upozorenja":       _upozorenja,
    }


async def _handle_akcija_rok(poruka: str, predmet_id: str, user_id: str) -> dict:
    """Extrahuje rok iz prirodnog jezika i upisuje u predmet_hronologija."""
    import json as _json
    from openai import AsyncOpenAI
    from datetime import date

    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    # Operation Living System (Wave 5, Red Team, REPRODUCED HIGH): this prompt asked GPT for
    # "kritičan|bitan|normalan", a vocabulary that does not match predmet_hronologija.vaznost's
    # actual CHECK constraint ('kritičan','važan','informativan' -- supabase_setup.sql). 2 of the
    # 3 possible GPT outputs, and this code's own literal fallback ("bitan"), always violated the
    # constraint and threw on insert -- a guaranteed, not rare, failure for any deadline not
    # phrased as critical. Prompt now asks for the real vocabulary; the insert below also
    # enum-validates the result (fail-safe to "informativan") in case GPT still drifts.
    _EX_SYS = (
        "Iz srpskog teksta izvuci podatke o roku. Vrati ISKLJUČIVO JSON:\n"
        '{"dogadjaj": str (naziv/opis roka), "datum_iso": str|null (YYYY-MM-DD), '
        '"vaznost": "kritičan|važan|informativan"}\n'
        f"Danas je {date.today().isoformat()}. Relativne datume pretvori u apsolutne."
    )
    try:
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(predmet_id=predmet_id, module_name="copilot", operation_name="akcija_rok"):
            resp = await _pozovi_gpt4o_mini(
                oai,
                model="gpt-4o-mini", temperature=0, max_tokens=150,
                response_format={"type": "json_object"},
                messages=[{"role":"system","content":_EX_SYS},{"role":"user","content":poruka}],
            )
        ext = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        _sentry_capture(e)
        logger.error("[COPILOT-ROK] ekstrakcija greška: %s", e)
        return {"tip":"DODAJ_ROK","uspeh":False,"odgovor":"Nisam uspeo da prepoznam rok. Pokušajte: 'Dodaj rok — ročište 20. jula 2026.'"}

    if not (ext.get("dogadjaj") or "").strip():
        return {"tip":"DODAJ_ROK","uspeh":False,"odgovor":"Naziv roka nije prepoznat. Pokušajte eksplicitno: 'Dodaj rok za pripremu do 15. jula.'"}

    supa = _get_supa()
    pred_ok = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", user_id).maybe_single().execute()
    )
    if not pred_ok.data:
        return {"tip":"DODAJ_ROK","uspeh":False,"odgovor":"Predmet nije pronađen."}
    _vaznost = ext.get("vaznost")
    if _vaznost not in ("kritičan", "važan", "informativan"):
        _vaznost = "informativan"
    try:
        await asyncio.to_thread(lambda: supa.table("predmet_hronologija").insert({
            "predmet_id": predmet_id,
            "user_id":    user_id,
            "dogadjaj":   ext["dogadjaj"][:200],
            "datum":      ext.get("datum_iso",""),
            "datum_iso":  ext.get("datum_iso",""),
            "vaznost":    _vaznost,
            "akter":      "Copilot (AI)",
        }).execute())
    except Exception as e:
        _sentry_capture(e)
        logger.error("[COPILOT-ROK] insert greška: %s", e)
        return {"tip":"DODAJ_ROK","uspeh":False,"odgovor":"Greška pri čuvanju roka. Pokušajte ponovo."}

    from shared.audit_immutable import log_action
    asyncio.create_task(log_action(
        action="copilot_dodaj_rok", user_id=user_id,
        resource_type="predmet", resource_id=predmet_id,
    ))

    return {
        "tip":     "DODAJ_ROK",
        "uspeh":   True,
        "dogadjaj": ext["dogadjaj"],
        "datum":   ext.get("datum_iso",""),
        "vaznost": ext.get("vaznost","bitan"),
        "odgovor": f"Rok dodat: {ext['dogadjaj']}" + (f" ({ext['datum_iso']})" if ext.get("datum_iso") else ""),
    }


async def _handle_akcija_beleska(poruka: str, predmet_id: str, user_id: str) -> dict:
    """Izvlači sadržaj beleške iz prirodnog jezika i upisuje u predmet_beleske."""
    import json as _json
    from openai import AsyncOpenAI

    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    _EX_SYS = (
        "Korisnik šalje komandu za kreiranje beleške u srpskim pravnom sistemu. "
        "Izvuci SAMO sadržaj beleške — bez prefixa 'zabeleži', 'napiši', 'sačuvaj' itd.\n"
        'Vrati ISKLJUČIVO JSON: {"sadrzaj": str}'
    )
    try:
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(predmet_id=predmet_id, module_name="copilot", operation_name="akcija_beleska"):
            resp = await _pozovi_gpt4o_mini(
                oai,
                model="gpt-4o-mini", temperature=0, max_tokens=400,
                response_format={"type": "json_object"},
                messages=[{"role":"system","content":_EX_SYS},{"role":"user","content":poruka}],
            )
        ext     = _json.loads(resp.choices[0].message.content or "{}")
        sadrzaj = (ext.get("sadrzaj") or "").strip()
    except Exception as e:
        _sentry_capture(e)
        sadrzaj = poruka.strip()

    if len(sadrzaj) < 3:
        return {"tip":"KREIRAJ_BELEŠKU","uspeh":False,"odgovor":"Sadržaj beleške je prazan. Navedite šta želite da zabeležite."}

    supa = _get_supa()
    pred_ok = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", user_id).maybe_single().execute()
    )
    if not pred_ok.data:
        return {"tip":"KREIRAJ_BELEŠKU","uspeh":False,"odgovor":"Predmet nije pronađen."}
    try:
        await asyncio.to_thread(lambda: supa.table("predmet_beleske").insert({
            "predmet_id": predmet_id,
            "user_id":    user_id,
            "sadrzaj":    sadrzaj[:2000],
        }).execute())
    except Exception as e:
        _sentry_capture(e)
        logger.error("[COPILOT-BELESKA] insert greška: %s", e)
        return {"tip":"KREIRAJ_BELEŠKU","uspeh":False,"odgovor":"Greška pri čuvanju beleške."}

    from shared.audit_immutable import log_action
    asyncio.create_task(log_action(
        action="copilot_kreiraj_belesku", user_id=user_id,
        resource_type="predmet", resource_id=predmet_id,
    ))

    preview = sadrzaj[:80] + ("…" if len(sadrzaj)>80 else "")
    return {
        "tip":     "KREIRAJ_BELEŠKU",
        "uspeh":   True,
        "sadrzaj": sadrzaj[:120],
        "odgovor": f"Beleška sačuvana: {preview}",
    }


async def _handle_akcija_povezi_klijenta(poruka: str, predmet_id: str, user_id: str) -> dict:
    """Traži klijenta po imenu i linkuje ga na predmet."""
    import json as _json
    from openai import AsyncOpenAI

    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    _EX_SYS = (
        "Iz srpskog teksta izvuci ime klijenta koji treba da se poveže sa predmetom.\n"
        'Vrati ISKLJUČIVO JSON: {"ime_klijenta": str, "uloga": "stranka|protivna_stranka|svedok|ostalo"}'
    )
    try:
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(predmet_id=predmet_id, module_name="copilot", operation_name="akcija_povezi_klijenta"):
            resp = await _pozovi_gpt4o_mini(
                oai,
                model="gpt-4o-mini", temperature=0, max_tokens=100,
                response_format={"type": "json_object"},
                messages=[{"role":"system","content":_EX_SYS},{"role":"user","content":poruka}],
            )
        ext = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        _sentry_capture(e)
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":"Nisam uspeo da prepoznam ime klijenta."}

    ime = (ext.get("ime_klijenta") or "").strip()
    if not ime:
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":"Navedite ime klijenta kojeg treba da povežem sa predmetom."}

    supa = _get_supa()

    pred_ok = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", user_id).maybe_single().execute()
    )
    if not pred_ok.data:
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":"Predmet nije pronađen."}

    try:
        found_r = await asyncio.to_thread(
            lambda: supa.table("klijenti")
                .select("id,ime,prezime,firma")
                .eq("user_id", user_id)
                .or_(f"ime.ilike.%{ime}%,prezime.ilike.%{ime}%,firma.ilike.%{ime}%")
                .limit(3)
                .execute()
        )
    except Exception as e:
        _sentry_capture(e)
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":"Greška pri pretražvanju klijenta."}

    if not (found_r.data):
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":f"Klijent \"{ime}\" nije pronađen u CRM-u. Proverite ime ili kreirajte novog klijenta."}

    kl    = found_r.data[0]
    naziv = ((kl.get("ime","")+" "+kl.get("prezime","")).strip()) or kl.get("firma","")
    uloga = ext.get("uloga","stranka")

    # Night Shift M-012 (2026-08-02): predmet_klijenti has no `id` column
    # (composite PK: predmet_id, klijent_id -- see supabase_setup.sql) and no
    # `user_id` column either (ownership derived transitively via
    # predmet_id -> predmeti.user_id, per Mission 001's architecture
    # decision, 2026-08-02). Both bugs found here, same root cause as
    # Mission 001's 5 fixed call sites -- this is a 6th, missed during that
    # sweep because that mission checked this SELECT's column but not this
    # INSERT's payload.
    existing = await asyncio.to_thread(
        lambda: supa.table("predmet_klijenti").select("predmet_id").eq("predmet_id",predmet_id).eq("klijent_id",kl["id"]).execute()
    )
    if existing.data:
        return {"tip":"POVEZI_KLIJENTA","uspeh":True,"odgovor":f"{naziv} je već vezan za ovaj predmet."}

    try:
        await asyncio.to_thread(lambda: supa.table("predmet_klijenti").insert({
            "predmet_id":     predmet_id,
            "klijent_id":     kl["id"],
            "uloga_klijenta": uloga,
        }).execute())
    except Exception as e:
        # Project Phoenix (2026-08-03): check-then-insert TOCTOU race on the
        # (predmet_id, klijent_id) composite PK -- two near-simultaneous
        # requests (double-click, or a retried request after a slow
        # response) can both pass the `existing.data` check above before
        # either INSERTs; the losing request previously got a generic
        # failure message even though the link WAS created (by the winning
        # request) -- a false-negative outcome for an action that actually
        # succeeded. Reuses the same duplicate-key detection
        # shared/audit_immutable.py already established, rather than
        # inventing a new check.
        from shared.audit_immutable import _is_unique_violation
        if _is_unique_violation(e):
            return {"tip": "POVEZI_KLIJENTA", "uspeh": True, "odgovor": f"{naziv} je već vezan za ovaj predmet."}
        _sentry_capture(e)
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":"Greška pri povezivanju klijenta."}

    from shared.audit_immutable import log_action
    asyncio.create_task(log_action(
        action="copilot_povezi_klijenta", user_id=user_id,
        resource_type="predmet", resource_id=predmet_id,
    ))

    return {
        "tip":        "POVEZI_KLIJENTA",
        "uspeh":      True,
        "klijent":    naziv,
        "klijent_id": kl["id"],
        "uloga":      uloga,
        "odgovor":    f"Klijent {naziv} vezan za predmet (uloga: {uloga}).",
    }


async def _handle_predlozi(predmet_id: str | None, user_id: str) -> dict:
    """
    Proaktivni agent — analizira stanje predmeta (ili celog portfolia)
    i vraca strukturirane predloge sledecih akcija.
    """
    from datetime import date, timedelta
    supa = _get_supa()
    today     = date.today()
    today_iso = today.isoformat()
    in_7_iso  = (today + timedelta(days=7)).isoformat()
    ago_30    = (today - timedelta(days=30)).isoformat()

    predlozi: list[dict] = []

    if predmet_id:
        # ── Predlozi za konkretan predmet ─────────────────────────────────────
        pred_r = await asyncio.to_thread(lambda: supa.table("predmeti")
            .select("naziv, opis, tip, status")
            .eq("id", predmet_id).eq("user_id", user_id)
            .maybe_single().execute())
        if not pred_r.data:
            return {"tip": "PREDLOZI", "uspeh": False, "odgovor": "Predmet nije pronađen."}
        pred = pred_r.data

        hron_r, dok_r, bel_r = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("dogadjaj, datum_iso, vaznost")
                .eq("predmet_id", predmet_id)
                .gte("datum_iso", today_iso)
                .lte("datum_iso", in_7_iso)
                .order("datum_iso").limit(10).execute()),
            asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
                .select("naziv_fajla, status")
                .eq("predmet_id", predmet_id).execute()),
            asyncio.to_thread(lambda: supa.table("predmet_beleske")
                .select("created_at")
                .eq("predmet_id", predmet_id)
                .gte("created_at", ago_30).execute()),
            return_exceptions=True,
        )

        rokovi = hron_r.data if not isinstance(hron_r, Exception) else []
        dok    = dok_r.data if not isinstance(dok_r, Exception) else []
        bel    = bel_r.data if not isinstance(bel_r, Exception) else []

        for r in rokovi:
            hitan = (r.get("datum_iso") or "") <= (today + timedelta(days=2)).isoformat()
            predlozi.append({
                "tip":       "rok",
                "prioritet": "hitan" if hitan else "normalan",
                "akcija":    f"{'⚠ HITAN — ' if hitan else ''}Rok: {r.get('dogadjaj', '')} ({r.get('datum_iso', '')})",
                "predmet_id": predmet_id,
            })

        cekaju = [d for d in dok if d.get("status") in ("na_cekanju", "greska")]
        if cekaju:
            predlozi.append({
                "tip":       "dokument",
                "prioritet": "normalan",
                "akcija":    f"{len(cekaju)} dokument{'a' if len(cekaju) != 1 else ''} čeka obradu: {', '.join(d.get('naziv_fajla','') for d in cekaju[:3])}",
                "predmet_id": predmet_id,
            })

        if not bel:
            predlozi.append({
                "tip":       "neaktivnost",
                "prioritet": "info",
                "akcija":    "Nema beleški u poslednje 30 dana — dodajte napomenu o statusu.",
                "predmet_id": predmet_id,
            })

        naziv = pred.get("naziv", "predmet")
        if not predlozi:
            predlozi.append({
                "tip":       "status",
                "prioritet": "info",
                "akcija":    f"Predmet '{naziv}' je ažuran — nema hitnih akcija.",
                "predmet_id": predmet_id,
            })

        return {
            "tip":       "PREDLOZI",
            "kontekst":  "predmet",
            "predmet":   naziv,
            "predlozi":  predlozi,
            "odgovor":   f"Pronašao sam {len(predlozi)} predlog{'a' if len(predlozi) != 1 else ''} za predmet '{naziv}'.",
        }

    else:
        # ── Firma-level predlozi (bez predmet_id) ─────────────────────────────
        rokovi_r, pred_r, hron_r, bel_r = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("predmet_id, dogadjaj, datum_iso, vaznost")
                .eq("user_id", user_id)
                .gte("datum_iso", today_iso)
                .lte("datum_iso", in_7_iso)
                .order("datum_iso").limit(20).execute()),
            asyncio.to_thread(lambda: supa.table("predmeti")
                .select("id, naziv, status")
                .eq("user_id", user_id).execute()),
            asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("predmet_id")
                .eq("user_id", user_id)
                .gte("created_at", ago_30).execute()),
            asyncio.to_thread(lambda: supa.table("predmet_beleske")
                .select("predmet_id")
                .eq("user_id", user_id)
                .gte("created_at", ago_30).execute()),
            return_exceptions=True,
        )

        predmeti_map = {}
        if not isinstance(pred_r, Exception) and pred_r.data:
            predmeti_map = {p["id"]: p for p in pred_r.data}

        if not isinstance(rokovi_r, Exception):
            for r in (rokovi_r.data or []):
                pid = r.get("predmet_id", "")
                naziv = predmeti_map.get(pid, {}).get("naziv", "Predmet")
                hitan = (r.get("datum_iso") or "") <= (today + timedelta(days=2)).isoformat()
                predlozi.append({
                    "tip":       "rok",
                    "prioritet": "hitan" if hitan else "normalan",
                    "akcija":    f"{'⚠ ' if hitan else ''}{naziv}: {r.get('dogadjaj','')} ({r.get('datum_iso','')})",
                    "predmet_id": pid,
                })

        active = set()
        if not isinstance(hron_r, Exception):
            active |= {r["predmet_id"] for r in (hron_r.data or [])}
        if not isinstance(bel_r, Exception):
            active |= {r["predmet_id"] for r in (bel_r.data or [])}

        for pid, p in predmeti_map.items():
            if p.get("status") in ("zatvoren", "arhiviran"):
                continue
            if pid not in active:
                predlozi.append({
                    "tip":       "neaktivnost",
                    "prioritet": "info",
                    "akcija":    f"Predmet '{p.get('naziv','')}' nema aktivnosti 30+ dana.",
                    "predmet_id": pid,
                })

        hitni   = [p for p in predlozi if p["prioritet"] == "hitan"]
        predlozi = sorted(predlozi, key=lambda x: 0 if x["prioritet"] == "hitan" else 1 if x["prioritet"] == "normalan" else 2)

        return {
            "tip":      "PREDLOZI",
            "kontekst": "portfolio",
            "predlozi": predlozi[:15],
            "hitnih":   len(hitni),
            "odgovor":  f"Portfolio: {len(predlozi)} prioritet{'a' if len(predlozi) != 1 else ''}. {len(hitni)} hitno.",
        }


async def _handle_ostalo(poruka: str, predmet_ctx: str) -> dict:
    """Generalni odgovor bez RAG — kratki savet."""
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    ctx_line = f"\nKontekst predmeta: {predmet_ctx}" if predmet_ctx else ""
    try:
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(module_name="copilot", operation_name="ostalo"):
            r = await _pozovi_gpt4o_mini(
                oai,
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": (
                        "Ti si pravni asistent za srpsko pravo. Daj kratak, konkretan odgovor. "
                        "Ako ne znaš tačan zakon, kaži to otvoreno." + ctx_line
                    )},
                    {"role": "user", "content": poruka},
                ],
                temperature=0.2,
                max_tokens=600,
            )
        return {"tip": "OSTALO", "odgovor": r.choices[0].message.content or ""}
    except Exception as e:
        _sentry_capture(e)
        logger.error("[COPILOT] ostalo greška: %s", e)
        return {"tip": "OSTALO", "odgovor": "Molim precizite pitanje."}


async def _handle_naplati_radnju(poruka: str, predmet_id: str | None, uid: str) -> dict:
    """Billing Faza 2 — parsira poruku i kreira billing_entry u Supabase."""
    import json as _json

    try:
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(predmet_id=predmet_id, module_name="copilot", operation_name="naplati_radnju"):
            raw = await _oai_parse_json(_NAPLATA_PARSE_SYSTEM, poruka)
        parsed = _json.loads(raw)
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[COPILOT-NAPLATA] parse greška: %s", e)
        parsed = {}

    sati        = parsed.get("sati")
    tarifa_sifra= parsed.get("tarifa_sifra")
    opis        = parsed.get("opis") or "Pravna radnja"
    iznos_rsd   = parsed.get("iznos_rsd")

    # Izračunaj iznos
    from routers.billing import AKS_TARIFA
    _BOD_RSD = 50

    if iznos_rsd:
        iznos_final = int(iznos_rsd)
        tip = "manual"
    elif tarifa_sifra and tarifa_sifra in AKS_TARIFA:
        stavka = AKS_TARIFA[tarifa_sifra]
        if stavka.get("fiksno_rsd"):
            iznos_final = stavka["fiksno_rsd"]
            if sati:
                iznos_final = int(stavka["fiksno_rsd"] * sati)
        else:
            iznos_final = int((stavka.get("bodovi") or 6) * _BOD_RSD)
        tip = "tarifa"
        opis = stavka["naziv"] if not parsed.get("opis") else opis
    elif sati:
        iznos_final = int(sati * 7500)
        tip = "satnica"
        tarifa_sifra = "T71"
    else:
        return {
            "tip":     "NAPLATI_RADNJU",
            "odgovor": "Nisam razumeo šta treba naplatiti. Recite npr: 'naplati 2h konsultacija' ili 'upiši tužbu'.",
            "status":  "nije_kreirana",
        }

    supa = _get_supa()
    entry = {
        "user_id":      uid,
        "opis":         opis[:500],
        "tip":          tip,
        "iznos_rsd":    iznos_final,
        "obracunato":   False,
    }
    if predmet_id:
        pred_ok = await asyncio.to_thread(
            lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", uid).maybe_single().execute()
        )
        if pred_ok.data:
            entry["predmet_id"] = predmet_id
    if tarifa_sifra:
        entry["tarifa_sifra"] = tarifa_sifra
    if sati:
        entry["sati"] = float(sati)

    try:
        res = await asyncio.to_thread(
            lambda: supa.table("billing_entries").insert(entry).execute()
        )
        kreirana_id = (res.data[0].get("id") if res.data else None)
    except Exception as e:
        _sentry_capture(e)
        logger.error("[COPILOT-NAPLATA] DB greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri čuvanju radnje.")

    from shared.audit_immutable import log_action
    asyncio.create_task(log_action(
        action="copilot_naplati_radnju", user_id=uid,
        resource_type="billing_entry", resource_id=kreirana_id,
    ))

    sati_prikaz = f" ({sati}h)" if sati else ""
    return {
        "tip":        "NAPLATI_RADNJU",
        "odgovor":    f"✅ Upisana radnja: **{opis}**{sati_prikaz} — **{iznos_final:,} RSD**.",
        "status":     "kreirana",
        "entry_id":   kreirana_id,
        "iznos_rsd":  iznos_final,
        "opis":       opis,
        "tarifa_sifra": tarifa_sifra,
    }


async def _handle_prikazi_tarifu(poruka: str) -> dict:
    """Billing Faza 2 — prikazuje relevantne AKS tarifa stavke za datu radnju."""
    from routers.billing import AKS_TARIFA
    _BOD_RSD = 50

    # Keyword match na AKS_TARIFA
    poruka_lower = poruka.lower()
    matches = []
    for sifra, stavka in AKS_TARIFA.items():
        naziv_lower = stavka["naziv"].lower()
        # Check key words overlap
        words = [w for w in poruka_lower.split() if len(w) > 3]
        if any(w in naziv_lower for w in words):
            if stavka.get("fiksno_rsd"):
                rsd = stavka["fiksno_rsd"]
                prikaz = f"{rsd:,} RSD/sat"
            else:
                bodovi = stavka.get("bodovi") or 0
                rsd = bodovi * _BOD_RSD
                prikaz = f"{bodovi} bodova = {rsd:,} RSD"
            matches.append({
                "sifra":  sifra,
                "naziv":  stavka["naziv"],
                "iznos":  prikaz,
                "rsd":    rsd,
            })

    if not matches:
        # Vrati sve ako nema match-a
        matches = [
            {
                "sifra": s,
                "naziv": v["naziv"],
                "iznos": (f"{v['fiksno_rsd']:,} RSD/sat"
                          if v.get("fiksno_rsd")
                          else f"{v.get('bodovi', 0) * _BOD_RSD:,} RSD"),
                "rsd": v.get("fiksno_rsd") or (v.get("bodovi", 0) * _BOD_RSD),
            }
            for s, v in AKS_TARIFA.items()
        ]
        odgovor = f"AKS tarifa — {len(matches)} stavki (1 bod = {_BOD_RSD} RSD):"
    else:
        odgovor = f"Pronašao sam {len(matches)} relevantnih AKS stavki:"

    return {
        "tip":      "PRIKAŽI_TARIFU",
        "odgovor":  odgovor,
        "stavke":   matches[:10],
        "napomena": "Tarifa po AKS (Sl. gl. RS 56/2025) — 1 bod = 50 RSD.",
    }


async def _handle_zastarelost(poruka: str, predmet_ctx: str, user: dict, history: list | None = None) -> dict:
    """Zastarelost — RAG pipeline sa zastarelost kontekstom."""
    enriched = f"[Oblast: zastarelost potraživanja, rokovi zastarelosti ZOO]\n{predmet_ctx}\n\n{poruka}".strip()
    result = await _handle_pravno_pitanje(enriched, "", user, history)
    result["tip"] = "ZASTARELOST"
    result["akcija"] = "otvori_zastarelost"
    return result


async def _handle_conflict_check(poruka: str, predmet_id: str | None, user_id: str) -> dict:
    """Conflict check — upućuje na modul ili daje savet."""
    return {
        "tip":    "CONFLICT_CHECK",
        "odgovor": (
            "Prepoznao sam pitanje o konfliktu interesa. "
            + ("Otvorite predmet → dugme **Conflict Check** za automatsku proveru u svim vašim predmetima i klijentima. "
               if predmet_id else
               "Koristite **Intake Wizard** (+ dugme) koji automatski proverava konflikt pri kreiranju novog predmeta. ")
            + "Zakonska osnova: Zakon o advokaturi čl. 23 — zabrana zastupanja suprotnih interesa."
        ),
        "akcija": "otvori_conflict_check",
        "predmet_id": predmet_id,
    }


async def _handle_billing_savet(poruka: str) -> dict:
    """Billing savet — prikazuje relevantne AKS stavke + opšti savet."""
    tarife_result = await _handle_prikazi_tarifu(poruka)
    tarife_result["tip"] = "BILLING_SAVET"
    tarife_result["napomena"] = (
        "Tarifa po AKS (Sl. gl. RS 56/2025) — 1 bod = 50 RSD. "
        "Možete naplatiti više ako ste ugovorili veću nagradu sa klijentom (čl. 14 ZA). "
        "Koristite tab **Naplata** u predmetu za unos stavki i generisanje fakture."
    )
    return tarife_result


async def _handle_rociste_priprema(poruka: str, predmet_id: str | None) -> dict:
    """Ročište — upućuje na Hearing CC modul."""
    return {
        "tip":    "ROCISTE_PRIPREMA",
        "odgovor": (
            "Prepoznao sam zahtev za pripremu ročišta. "
            + (f"Otvorite predmet → tab **Rokovi** → **Priprema za ročište** za kompletan brifing u 12 sekcija "
               "(pravna osnova, dokazi, taktika, rizici, cross-exam pitanja)."
               if predmet_id else
               "Otvorite predmet koji se tiče ročišta, zatim tab **Rokovi** → **Priprema za ročište**.")
        ),
        "akcija":    "otvori_hearing_cc",
        "predmet_id": predmet_id,
    }


async def _handle_izvrsenje(poruka: str, predmet_ctx: str, user: dict, history: list | None = None) -> dict:
    """Izvršni postupak — RAG sa izvršno pravo kontekstom."""
    enriched = f"[Oblast: izvršni postupak, prinudna naplata, ZIO]\n{predmet_ctx}\n\n{poruka}".strip()
    result = await _handle_pravno_pitanje(enriched, "", user, history)
    result["tip"] = "IZVRSENJE"
    return result


async def _handle_nasledstvo(poruka: str, predmet_ctx: str, user: dict, history: list | None = None) -> dict:
    """Nasledno pravo — RAG sa nasledno pravo kontekstom."""
    enriched = f"[Oblast: nasledno pravo, ostavina, testament, Zakon o nasleđivanju]\n{predmet_ctx}\n\n{poruka}".strip()
    result = await _handle_pravno_pitanje(enriched, "", user, history)
    result["tip"] = "NASLEDSTVO"
    return result


async def _handle_radni_spor(poruka: str, predmet_ctx: str, user: dict, history: list | None = None) -> dict:
    """Radno pravo — RAG sa radno pravo kontekstom."""
    enriched = f"[Oblast: radno pravo, otkaz, radni spor, Zakon o radu]\n{predmet_ctx}\n\n{poruka}".strip()
    result = await _handle_pravno_pitanje(enriched, "", user, history)
    result["tip"] = "RADNI_SPOR"
    return result


@router.post("/copilot/chat")
@limiter.limit("30/minute")
async def copilot_chat(
    req: CopilotReq,
    request: Request,
    user: dict = Depends(PermissionService.require("copilot")),
):
    """
    Vindex Copilot — orkestrator svih modula.
    Detektuje nameru i automatski rutira na odgovarajući servis.
    """
    uid      = user["user_id"]
    email    = user.get("email", "")
    predmet_ctx = ""

    await UsageService.consume(uid, email, "copilot")

    if req.predmet_id:
        predmet_ctx = await _load_predmet_context(req.predmet_id, uid)

    intent = await _detect_intent(req.poruka)
    logger.info("[COPILOT] uid=%.8s intent=%s predmet=%s", uid, intent, req.predmet_id or "-")

    _hist = (req.history or [])[-5:]
    handlers = {
        "PRAVNO_PITANJE":   lambda: _handle_pravno_pitanje(req.poruka, predmet_ctx, user, _hist),
        "SUDSKA_PRAKSA":    lambda: _handle_sudska_praksa(req.poruka),
        "NACRT":            lambda: _handle_nacrt(req.poruka, predmet_ctx, user),
        "ANALIZA_PREDMETA": lambda: _handle_analiza_predmeta(req.poruka, req.predmet_id, uid) if req.predmet_id else _handle_pravno_pitanje(req.poruka, predmet_ctx, user, _hist),
        "PLAN":             lambda: _handle_plan_predmeta(req.poruka, req.predmet_id, uid) if req.predmet_id else _handle_pravno_pitanje(req.poruka, predmet_ctx, user, _hist),
        "DODAJ_ROK":        lambda: _handle_akcija_rok(req.poruka, req.predmet_id, uid) if req.predmet_id else _handle_ostalo(req.poruka, predmet_ctx),
        "KREIRAJ_BELEŠKU":  lambda: _handle_akcija_beleska(req.poruka, req.predmet_id, uid) if req.predmet_id else _handle_ostalo(req.poruka, predmet_ctx),
        "POVEZI_KLIJENTA":  lambda: _handle_akcija_povezi_klijenta(req.poruka, req.predmet_id, uid) if req.predmet_id else _handle_ostalo(req.poruka, predmet_ctx),
        "ROKOVI":           lambda: _handle_pravno_pitanje(req.poruka, predmet_ctx, user, _hist),
        "ZASTARELOST":      lambda: _handle_zastarelost(req.poruka, predmet_ctx, user, _hist),
        "CONFLICT_CHECK":   lambda: _handle_conflict_check(req.poruka, req.predmet_id, uid),
        "BILLING_SAVET":    lambda: _handle_billing_savet(req.poruka),
        "ROCISTE_PRIPREMA": lambda: _handle_rociste_priprema(req.poruka, req.predmet_id),
        "IZVRSENJE":        lambda: _handle_izvrsenje(req.poruka, predmet_ctx, user, _hist),
        "NASLEDSTVO":       lambda: _handle_nasledstvo(req.poruka, predmet_ctx, user, _hist),
        "RADNI_SPOR":       lambda: _handle_radni_spor(req.poruka, predmet_ctx, user, _hist),
        "PRETRAGA":         lambda: _handle_pretraga(req.poruka, uid),
        "PREDLOZI":         lambda: _handle_predlozi(req.predmet_id, uid),
        "NAPLATI_RADNJU":   lambda: _handle_naplati_radnju(req.poruka, req.predmet_id, uid),
        "PRIKAŽI_TARIFU":   lambda: _handle_prikazi_tarifu(req.poruka),
        "OSTALO":           lambda: _handle_ostalo(req.poruka, predmet_ctx),
    }

    handler = handlers.get(intent, handlers["OSTALO"])
    # BLACKSWAN-HIGH-005 fix (Operation Black Swan, Mission 001, Scenario 4): credit is
    # consumed above BEFORE routing, but there was no try/except around the handler call
    # at all -- an uncaught exception propagated as an unhandled 500 with the credit
    # already gone, and ZERO UsageService.refund call sites existed anywhere in this file
    # (grep-confirmed). Reproduced 2 ways: an uncaught handler exception, and a handler
    # that swallows a genuine ask_agent failure into a disclaimer-text HTTP 200 response
    # (same underlying LAMBDA008-REL-001 shape as /api/pitanje, at a call site that fix
    # never covered). The "uspesno" check below is opt-in per handler (only
    # _handle_pravno_pitanje sets it so far) -- a handler that doesn't set it is treated
    # as always successful, the same behavior as before this fix, no regression.
    try:
        result = await handler()
    except Exception:
        await UsageService.refund(uid, email, "copilot")
        raise

    if isinstance(result, dict) and result.get("uspesno") is False:
        await UsageService.refund(uid, email, "copilot")

    return {
        "intent":        intent,
        "intent_label":  INTENT_LABELS.get(intent, "Opšto pitanje"),
        "predmet_id":    req.predmet_id,
        **result,
    }
