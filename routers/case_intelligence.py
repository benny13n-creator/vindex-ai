# -*- coding: utf-8 -*-
"""
Vindex AI — Case Intelligence Briefing (Integration Layer)

Jedan endpoint koji ulancava sve module i vraca JEDNU preporuku.
Advokat otvori predmet — AI agregira: lekcije, DNA, knowledge profile,
komunikacioni profil, court predictor, decision log.

Bez otvaranja deset ekrana.

POST /api/intelligence/predmeti/{predmet_id}/briefing
GET  /api/intelligence/predmeti/{predmet_id}/briefing/poslednji
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService
from shared.case_context import build_case_context
from routers.matter_intel import _d

logger = logging.getLogger("vindex.case_intelligence")
router = APIRouter(prefix="/api/intelligence", tags=["case_intelligence"])


@llm_retry
async def _pozovi_briefing_api(client, context_text: str):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _BRIEFING_SYSTEM},
            {"role": "user", "content": context_text[:10000]}
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

# ─── Prompt ───────────────────────────────────────────────────────────────────

# Program Tau, Master Sprint 003 (2026-08-06) -- "Canonical AI Decision Boundary".
# Phase 1's own AI_DECISION_SURFACE_MAP.md found sledeci_korak/razlog/hitnost/
# kljucni_rizici/napomena/pouzdanost_briefinga were either GPT-invented outright
# or only conditionally overridden (falling through to GPT's own guess when
# case_actions had nothing open -- exactly the "GPT may never redefine" gap
# this sprint exists to close). All 6 are now computed deterministically in
# case_intelligence_briefing() below, from case_actions/case_context, never
# from GPT -- so they're removed from what GPT is even asked to produce.
# relevantne_lekcije/komunikacioni_savet/potvrdjeni_obrasci stay: genuine
# narrative synthesis over real fetched rows, no canonical decision they'd
# compete with (see docs/tau/DECISION_OWNERSHIP_MATRIX.md).
_BRIEFING_SYSTEM = """Ti si pravni AI asistent koji sintetizuje informacije iz vise izvora u kratke, korisne uvide za advokata.

Data ti je analiza predmeta iz sledecih sistema:
- Lekcije iz slicnih predmeta (Lessons Learned)
- Firminski DNA obrasci (Firm DNA)
- Knowledge profili relevantnih oblasti
- Komunikacioni profil klijenta
- Obrasci iz slicnih predmeta (Case Patterns)

NE odlucuj sledeci korak, prioritet, hitnost, kljucne rizike niti pouzdanost -- to racuna sistem iz
case_actions/Genome/Gap Engine i dodaje se posle tvog odgovora. Tvoj posao je iskljucivo sinteza NARATIVNOG
uvida iz podataka ispod.

Vrati JSON:
{
  "relevantne_lekcije": ["<lekcija1 iz slicnih predmeta>"],
  "komunikacioni_savet": "<kako pristupiti klijentu na osnovu profila>",
  "potvrdjeni_obrasci": ["<pattern koji je relevantan>"]
}

Samo JSON. Srpski jezik. Budi konkretan, bez filozofisanja."""

# ─── Helper: prikupljanje podataka iz svih modula ─────────────────────────────

async def _gather_case_data(supa, predmet_id: str, user_id: str) -> dict:
    """Paralelno prikuplja podatke iz svih relevantnih tabela."""

    # Program Gamma (2026-08-04) -- ranija verzija je (a) selektovala kolone
    # koje ne postoje na proactive_alerts (tekst_alerta/tip_alerta/hitnost --
    # stvarna sema je tip/naslov/opis/urgentnost, migrations/036_decision_
    # log.sql:40-51 -- ISTA greska koja je nadjena i ispravljena na case_dna.py
    # 2026-07-18, ovde nikad uhvacena) i (b) nije imala return_exceptions=True,
    # pa bi ta jedna greska srusila CEO /briefing poziv (500) umesto da
    # degradira samo alert sekciju.
    #
    # Olympus Faza 10 governance nalaz (2026-08-04, Security Review): vlasnicka
    # provera (predmeti upit, jedina autorizacija u ovoj funkciji) je bila
    # unutar fail-soft gather-a -- prolazna DB/mrezna greska na TOJ specificnoj
    # podupit bi se tiho prijavila kao "Predmet nije pronadjen" (404) umesto
    # kao stvarna greska (500), gubeci vidljivost. Izdvojena kao sopstveni
    # awaited poziv PRE gather-a, isti obrazac kao evidence_graph.py:197-204.
    # (Architecture Review): SimpleNamespace supstitucija je bila TRECI
    # nezavisni idiom za "gather sa delimicnim neuspehom" u ovom repou --
    # matter_intel.py::_d() vec postoji upravo za ovaj slucaj (Faza 2.2,
    # 2026-07-18), sada reuse-ovana ovde umesto cetvrtog idioma.
    predmet_row = await asyncio.to_thread(
        lambda: supa.table("predmeti")
        .select("naziv, tip, status, oblast_prava, opis, klijent_id, case_dna")
        .eq("id", predmet_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    predmet = predmet_row.data or {}
    klijent_id = predmet.get("klijent_id")

    _rezultati = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("lessons_learned")
            .select("sadrzaj, kategorija, pouzdanost, status_lekcije, broj_predmeta")
            .eq("user_id", user_id)
            .in_("status_lekcije", ["predlog_ai", "usvojena_praksa"])
            .order("broj_predmeta", desc=True)
            .limit(5)
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("firm_dna")
            .select("pattern, frekvencija, uzoraka")
            .eq("user_id", user_id)
            .eq("aktuelna", True)
            .order("frekvencija", desc=True)
            .limit(5)
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("case_patterns")
            .select("tip_spora, faktor, pobede, porazi, ukupno")
            .eq("user_id", user_id)
            .order("pobede", desc=True)
            .limit(3)
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("proactive_alerts")
            .select("tip, opis, urgentnost")
            .eq("user_id", user_id)
            .eq("predmet_id", predmet_id)
            .eq("procitana", False)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("decision_log")
            .select("opis, tip_odluke, alternativa, created_at")
            .eq("user_id", user_id)
            .eq("predmet_id", predmet_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        ),
        # Program Tau, Master Sprint 002 (2026-08-06): CONTEXT_BUILDER_REGISTRY.md
        # found this function had ZERO access to predmet_dokumenti/predmet_dokazi/
        # case_actions/rocista -- the briefing synthesized lessons/firm-DNA/
        # patterns/alerts/decisions with no view of the case's own documents,
        # evidence, open actions, or deadlines. build_case_context() (the
        # canonical Case Context Contract) closes that gap by reuse, not a new
        # bespoke fetch -- one redundant `predmeti` row read (cheap, single
        # indexed lookup) is an acceptable cost for not building a 2nd document
        # sampler/evidence reader/action reader here.
        build_case_context(predmet_id, user_id, supa),
        return_exceptions=True,
    )
    _nazivi = ("lessons_learned", "firm_dna", "case_patterns", "proactive_alerts", "decision_log", "case_context")
    for _naziv, _r in zip(_nazivi, _rezultati):
        if isinstance(_r, Exception):
            logger.warning("[CASE_INTELLIGENCE] Podupit '%s' neuspesan (degradiran, nije fatalan): %s", _naziv, _r)
    lekcije, firm_dna_lista, case_patterns_lista, alertovi, odluke = (_d(r) for r in _rezultati[:5])
    _cc_result = _rezultati[5]
    case_context = {} if isinstance(_cc_result, Exception) else (_cc_result or {})

    # Komunikacioni profil klijenta (ako postoji)
    komunikacioni_profil = {}
    if klijent_id:
        try:
            kp_row = await asyncio.to_thread(
                lambda: supa.table("client_twin_profili")
                .select("twin_profil")
                .eq("klijent_id", klijent_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            komunikacioni_profil = (kp_row.data or {}).get("twin_profil") or {}
        except Exception:
            pass

    # Knowledge profili relevantni za oblast
    knowledge_profili = []
    oblast = predmet.get("oblast_prava", "")
    if oblast:
        try:
            kn_row = await asyncio.to_thread(
                lambda: supa.table("knowledge_profiles")
                .select("advokat_ime, oblasti_prava, top_argumenti, taktike")
                .eq("user_id", user_id)
                .eq("aktivan", True)
                .execute()
            )
            for kp in (kn_row.data or []):
                if oblast.lower() in [o.lower() for o in (kp.get("oblasti_prava") or [])]:
                    knowledge_profili.append(kp)
        except Exception:
            pass

    return {
        "predmet": predmet,
        "lekcije": lekcije,
        "firm_dna": firm_dna_lista,
        "case_patterns": case_patterns_lista,
        "alertovi": alertovi,
        "odluke": odluke,
        "komunikacioni_profil": komunikacioni_profil,
        "knowledge_profili": knowledge_profili[:2],
        "case_context": case_context,
    }


def _build_context_text(data: dict) -> str:
    """Formatira prikupljene podatke u tekst za GPT."""
    p = data["predmet"]
    lines = [
        f"PREDMET: {p.get('naziv', 'N/A')} | Tip: {p.get('tip', 'N/A')} | "
        f"Oblast: {p.get('oblast_prava', 'N/A')} | Status: {p.get('status', 'N/A')}\n"
    ]

    # Case Genome — Single Source of Truth
    genome = p.get("case_dna") or {}
    if genome and not genome.get("greska"):
        v = genome.get("verzija", "")
        v_str = f" v{v}" if v else ""
        lines.append(f"CASE GENOME{v_str} — SINGLE SOURCE OF TRUTH:")
        gi = genome.get("pravna_teorija") or {}
        if gi.get("pravni_identitet"):
            lines.append(f"  Identitet: {gi['pravni_identitet']}")
        if gi.get("sustina_spora"):
            lines.append(f"  Suština: {gi['sustina_spora']}")
        if gi.get("osnov_odgovornosti"):
            lines.append(f"  Pravni osnov: {gi['osnov_odgovornosti']}")
        snaga = genome.get("snaga_predmeta_procent")
        if snaga is not None:
            lines.append(f"  Snaga predmeta: {snaga}% ({genome.get('snaga_predmeta','')})")
        # Explainable faktori
        sf = genome.get("snaga_faktori") or []
        if sf:
            lines.append("  Faktori: " + " | ".join(
                f"{f.get('uticaj','')}{f.get('faktor','')}" for f in sf[:4]
            ))
        # Najslabija tacka
        nt = genome.get("najslabija_tacka") or {}
        if nt.get("rizik"):
            lines.append(f"  NAJSLABIJA TACKA [{nt.get('kriticnost','')}%]: {nt['rizik']}")
            if nt.get("preporuka"):
                lines.append(f"    → {nt['preporuka']}")
        # Strategija (War Plan)
        strat = genome.get("strategija") or {}
        if strat.get("primarni_cilj"):
            lines.append(f"  CILJ: {strat['primarni_cilj']}")
        if strat.get("rezervni_plan"):
            lines.append(f"  BACKUP: {strat['rezervni_plan']}")
        for sc in (strat.get("scenariji") or [])[:2]:
            if sc.get("uslov"):
                lines.append(f"    Scenario: {sc['uslov']} → {sc.get('odgovor','')[:80]}")
        # Finansije
        fin = genome.get("finansije") or {}
        if fin.get("tuzeni_iznos"):
            lines.append(f"  Traženi iznos: {fin['tuzeni_iznos']}")
        if fin.get("ukupna_ekspozicija"):
            lines.append(f"  Ukupna ekspozicija: {fin['ukupna_ekspozicija']}")
        # Nedostaje
        ned = genome.get("nedostaje") or []
        if ned:
            lines.append("  NEDOSTAJUCI DOKAZI: " + " | ".join(
                f"[{n.get('hitnost','')}] {n.get('dokument','')}" for n in ned[:3]
            ))
        # Heatmap
        hm = genome.get("heatmap") or {}
        if hm:
            lines.append("  Heatmap: " + " | ".join(
                f"{k}={v}%" for k, v in hm.items() if isinstance(v, int)
            ))
        # Kontradikcije
        kontr = genome.get("kontradikcije") or []
        if kontr:
            lines.append(f"  KONTRADIKCIJE ({len(kontr)}):")
            for k in kontr[:3]:
                lines.append(f"    ⚠ {k.get('opis','')[:120]} [{k.get('tezina','')}]")
        upoz = genome.get("upozorenja") or []
        for u in upoz[:2]:
            lines.append(f"  ! {u[:120]}")
        if genome.get("zakljucak"):
            lines.append(f"  Zaključak: {genome['zakljucak'][:200]}")
        lines.append("")

    # Program Tau, Master Sprint 002 (2026-08-06) -- documents/evidence/open
    # actions/deadlines this briefing never saw before (see comment on the
    # build_case_context() call in _gather_case_data above). Bounded to a
    # modest budget (few documents, short excerpts) so this addition doesn't
    # starve the lessons/firm-DNA/decisions sections below within the
    # existing 10000-char total budget in _pozovi_briefing_api.
    cc = data.get("case_context") or {}
    rel_docs = ((cc.get("relevant_documents") or {}).get("value") or {})
    included = rel_docs.get("included") or []
    if included:
        lines.append(f"DOKUMENTI U DOSIJEU ({rel_docs.get('total_documents', len(included))} ukupno):")
        for d in included[:4]:
            izvod = (d.get("excerpt") or "")[:500]
            lines.append(f"  - {d.get('naziv','')}: {izvod}" if izvod else f"  - {d.get('naziv','')} (bez teksta)")
        not_included = rel_docs.get("not_included_but_retrievable") or []
        if not_included:
            lines.append(f"  (+ još {len(not_included)} dokumenata u dosijeu, nisu prikazani ovde)")
        lines.append("")

    dokazi_graf = ((cc.get("evidence_graph") or {}).get("value") or {})
    if dokazi_graf.get("ukupno_dokaza"):
        lines.append(f"DOKAZI: {dokazi_graf['ukupno_dokaza']} ukupno, po kategoriji: {dokazi_graf.get('po_kategoriji')}")
        lines.append("")

    otvorene_akcije = ((cc.get("active_actions") or {}).get("value") or [])
    if otvorene_akcije:
        lines.append("OTVORENE AKCIJE (case_actions):")
        for a in otvorene_akcije[:3]:
            lines.append(f"  - [{a.get('prioritet','?')}] {a.get('razlog','')[:150]}" + (f" (rok: {a['rok']})" if a.get("rok") else ""))
        lines.append("")

    rokovi_cc = ((cc.get("deadlines") or {}).get("value") or [])
    if rokovi_cc:
        lines.append("ROČIŠTA/ROKOVI:")
        for r in rokovi_cc[:3]:
            lines.append(f"  - {r.get('sud','')} | {str(r.get('datum',''))[:10]} | {r.get('status','')}")
        lines.append("")

    if data["lekcije"]:
        lines.append("LEKCIJE IZ SLICNIH PREDMETA:")
        for l in data["lekcije"]:
            badge = "✔" if l.get("status_lekcije") == "usvojena_praksa" else "⚡"
            lines.append(f"  {badge} [{l.get('pouzdanost','?')}] {l.get('sadrzaj','')[:150]}")

    if data["firm_dna"]:
        lines.append("\nFIRM DNA OBRASCI:")
        for d in data["firm_dna"]:
            lines.append(f"  - {d.get('pattern','')} (frekvencija: {d.get('frekvencija',0)})")

    if data["case_patterns"]:
        lines.append("\nOBRASCI IZ PREDMETA:")
        for cp in data["case_patterns"]:
            win_rate = round(cp.get("pobede", 0) / max(cp.get("ukupno", 1), 1) * 100)
            lines.append(f"  - {cp.get('tip_spora','')}: {cp.get('faktor','')[:100]} (win rate: {win_rate}%)")

    if data["alertovi"]:
        lines.append("\nAKTIVNI ALERTOVI:")
        for a in data["alertovi"]:
            lines.append(f"  ! [{a.get('urgentnost','?')}] {a.get('opis','')[:150]}")

    if data["odluke"]:
        lines.append("\nODLUKE NA PREDMETU:")
        for o in data["odluke"]:
            lines.append(f"  - [{o.get('tip_odluke','?')}] {o.get('opis','')[:150]}")

    kp = data.get("komunikacioni_profil") or {}
    if kp:
        lines.append("\nKOMUNIKACIONI PROFIL KLIJENTA:")
        if kp.get("tip_izvestaja"):
            lines.append(f"  Tip izvestaja: {kp['tip_izvestaja']}")
        if kp.get("preferirani_kanal"):
            lines.append(f"  Preferirani kanal: {kp['preferirani_kanal']}")
        if kp.get("uvek_trazi_procenu_troskova"):
            lines.append("  Uvek trazi procenu troskova!")
        napomene = kp.get("konkretne_napomene") or []
        for n in napomene[:3]:
            lines.append(f"  Napomena: {n}")

    if data["knowledge_profili"]:
        lines.append("\nRELEVANTNI KNOWLEDGE PROFILI:")
        for kpr in data["knowledge_profili"]:
            args = kpr.get("top_argumenti") or []
            if args:
                lines.append(f"  {kpr['advokat_ime']}: {args[0].get('argument','')[:100]}")

    return "\n".join(lines)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/predmeti/{predmet_id}/briefing")
@limiter.limit("10/minute")
async def case_intelligence_briefing(request: Request, predmet_id: str, user=Depends(PermissionService.require("case_intelligence"))):
    """Sintetizuje sve module u jednu preporuku za predmet.

    Ulancava: Lessons Learned → Firm DNA → Knowledge Profile →
    Client Communication Profile → Case Patterns → Alerts → Decision Log
    → GPT-4o → JEDAN sledeci korak.
    """
    supa = _get_supa()
    try:
        data = await _gather_case_data(supa, predmet_id, user["user_id"])

        if not data["predmet"]:
            raise HTTPException(404, "Predmet nije pronadjen")

        context_text = _build_context_text(data)

        import openai
        client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

        resp = await _pozovi_briefing_api(client, context_text)

        briefing = json.loads(resp.choices[0].message.content)

        # Program Tau, Master Sprint 003 (2026-08-06) -- "Canonical AI Decision
        # Boundary". AI_DECISION_SURFACE_MAP.md found Sigma 004's own fix below
        # was CONDITIONAL -- when case_actions had nothing open, GPT's own raw
        # guess (still asked for at the time) survived untouched. This sprint's
        # own rule ("GPT may never redefine") makes that fallback itself the
        # violation, so all 6 fields (sledeci_korak/razlog/hitnost/
        # kljucni_rizici/napomena/pouzdanost_briefinga) are now computed here
        # UNCONDITIONALLY -- GPT is no longer even asked for them (see
        # _BRIEFING_SYSTEM above), so there is no GPT guess left to fall back
        # to. An honest "nothing open" state replaces silent GPT invention.
        case_context = data.get("case_context") or {}
        _raw_actions = ((case_context.get("active_actions") or {}).get("value")) or []
        from shared.case_readiness import top_open_action
        _top = top_open_action(_raw_actions)
        _HITNOST_BY_PRIORITET = {
            "critical": "odmah", "high": "ovu_nedelju",
            "medium": "ovaj_mesec", "low": "ovaj_mesec", "informational": "ovaj_mesec",
        }
        if _top:
            briefing["sledeci_korak"] = _top.get("razlog") or ""
            briefing["razlog"] = "Najviši prioritet u Case Actions (case_actions.dedupe_key=%s)." % (_top.get("dedupe_key") or "?")
            briefing["hitnost"] = _HITNOST_BY_PRIORITET.get(_top.get("prioritet"), "ovaj_mesec")
        else:
            briefing["sledeci_korak"] = "Nema otvorenih akcija u Case Actions za ovaj predmet."
            briefing["razlog"] = "Case Actions ne prati trenutno nijednu otvorenu stavku za ovaj predmet."
            briefing["hitnost"] = "ovaj_mesec"

        # kljucni_rizici -- was pure GPT invention with zero cross-check.
        # Now sourced from case_context's own missing_evidence/contradictions
        # (shared/gap_engine.py, reused not reinvented), capped to 4.
        _missing = ((case_context.get("missing_evidence") or {}).get("value")) or []
        _contra = ((case_context.get("contradictions") or {}).get("value")) or []
        briefing["kljucni_rizici"] = [g.get("razlog") for g in (_contra + _missing)[:4] if g.get("razlog")]

        # napomena -- was GPT's own free guess at "what's missing/couldn't be
        # analyzed," overlapping Gap Engine's own domain. Now a deterministic
        # completeness statement derived from case_context's own audit_metadata.
        _genome_computed = ((case_context.get("audit_metadata") or {}).get("value") or {}).get("genome_computed")
        if _genome_computed is False:
            briefing["napomena"] = "Case Genome još nije izračunat za ovaj predmet -- procena je zasnovana samo na dostupnim beleškama/lekcijama."
        elif not briefing["kljucni_rizici"]:
            briefing["napomena"] = "Nema evidentiranih rizika ili nedostajućih dokaza za ovaj predmet."
        else:
            briefing["napomena"] = ""

        # pouzdanost_briefinga -- was GPT self-declaring its OWN confidence, a
        # structural violation (confidence must be assigned, not self-reported).
        # Deterministic: "visoka" only when both Genome ran AND a real open
        # action was found to anchor sledeci_korak in something canonical.
        if _genome_computed and _top:
            briefing["pouzdanost_briefinga"] = "visoka"
        elif _genome_computed or _top:
            briefing["pouzdanost_briefinga"] = "srednja"
        else:
            briefing["pouzdanost_briefinga"] = "niska"

        # Snimi u decision_log kao poseban tip
        try:
            await asyncio.to_thread(
                lambda: supa.table("decision_log").insert({
                    "user_id": user["user_id"],
                    "predmet_id": predmet_id,
                    "tip_odluke": "intelligence_briefing",
                    "opis": briefing.get("sledeci_korak", ""),
                    "kontekst": {
                        "hitnost": briefing.get("hitnost"),
                        "pouzdanost": briefing.get("pouzdanost_briefinga"),
                        "br_lekcija": len(data["lekcije"]),
                        "br_alertova": len(data["alertovi"]),
                    },
                }).execute()
            )
        except Exception:
            pass

        await UsageService.consume(user["user_id"], user.get("email", ""), "case_intelligence")

        return {
            "predmet_id": predmet_id,
            "predmet_naziv": data["predmet"].get("naziv"),
            "briefing": briefing,
            "izvori": {
                "lekcije_analizirano": len(data["lekcije"]),
                "firm_dna_obrazaca": len(data["firm_dna"]),
                "alertova": len(data["alertovi"]),
                "odluka_na_predmetu": len(data["odluke"]),
                "knowledge_profila": len(data["knowledge_profili"]),
                "komunikacioni_profil_dostupan": bool(data["komunikacioni_profil"]),
                # Frontend (index.html:1613) has always read izvori.pouzdanost_briefinga
                # for the AI Briefing panel's own confidence badge -- the backend
                # only ever wrote it into `briefing`, so that badge never populated.
                # Fixed as a byproduct of this sprint's own switch to a
                # deterministically-computed value: written to both places now,
                # `briefing` for backward compatibility, `izvori` to actually
                # match what the UI reads.
                "pouzdanost_briefinga": briefing["pouzdanost_briefinga"],
            },
            # Program Tau, Master Sprint 003 -- non-breaking addition (existing
            # `briefing`/`izvori` field names/shapes untouched, since both have
            # live frontend consumers -- see docs/tau/AI_DECISION_SURFACE_MAP.md's
            # own live-caller correction). Documents WHO owns each of the fields
            # this sprint moved off raw GPT output, without requiring any
            # frontend change to consume it.
            "_ai_provenance": {
                "sledeci_korak": {"owner": "case_actions" if _top else "human", "source": "shared.case_readiness.top_open_action", "generated_by": "deterministic"},
                "kljucni_rizici": {"owner": "gap_engine", "source": "shared.case_context.build_case_context (missing_evidence + contradictions)", "generated_by": "deterministic"},
                "napomena": {"owner": "genome", "source": "case_context.audit_metadata.genome_computed", "generated_by": "deterministic"},
                "pouzdanost_briefinga": {"owner": "human", "source": "data-completeness heuristic (genome_computed + top_open_action presence)", "generated_by": "deterministic"},
                "relevantne_lekcije": {"owner": "gpt_advisory", "source": "lessons_learned rows", "generated_by": "gpt-4o"},
                "komunikacioni_savet": {"owner": "gpt_advisory", "source": None, "generated_by": "gpt-4o"},
                "potvrdjeni_obrasci": {"owner": "gpt_advisory", "source": "case_patterns rows", "generated_by": "gpt-4o"},
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        _sentry_capture(e)
        logger.error("case_intelligence_briefing: %s", e)
        raise HTTPException(500, str(e))


@router.get("/predmeti/{predmet_id}/briefing/poslednji")
@limiter.limit("30/minute")
async def get_poslednji_briefing(request: Request, predmet_id: str, user=Depends(get_current_user)):
    """Preuzima poslednji sacuvani intelligence briefing za predmet."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("decision_log")
            .select("opis, kontekst, created_at")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user["user_id"])
            .eq("tip_odluke", "intelligence_briefing")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not row.data:
            return {"briefing": None, "poruka": "Nema sacuvanog briefinga. Pokrenite POST /briefing"}
        return {"briefing": row.data[0], "predmet_id": predmet_id}
    except Exception as e:
        raise HTTPException(500, str(e))
