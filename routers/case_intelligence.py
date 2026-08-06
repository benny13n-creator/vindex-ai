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

_BRIEFING_SYSTEM = """Ti si pravni AI asistent koji sintetizuje informacije iz vise izvora u jednu jasnu preporuku.

Data ti je analiza predmeta iz sledecih sistema:
- Lekcije iz slicnih predmeta (Lessons Learned)
- Firminski DNA obrasci (Firm DNA)
- Knowledge profili relevantnih oblasti
- Komunikacioni profil klijenta
- Obrasci iz slicnih predmeta (Case Patterns)
- Aktivni alertovi i rizici
- Istorija odluka na predmetu (Decision Log)

Sintetizuj u JEDINSTVEN briefing. Budi hirurski precizan.

Vrati JSON:
{
  "sledeci_korak": "<JEDNA najhitnija konkretna akcija>",
  "razlog": "<zasto je bas ova akcija prioritetna>",
  "kljucni_rizici": ["<rizik1>", "<rizik2>"],
  "relevantne_lekcije": ["<lekcija1 iz slicnih predmeta>"],
  "komunikacioni_savet": "<kako pristupiti klijentu na osnovu profila>",
  "potvrdjeni_obrasci": ["<pattern koji je relevantan>"],
  "hitnost": "<odmah | ovu_nedelju | ovaj_mesec>",
  "pouzdanost_briefinga": "<visoka | srednja | niska>",
  "napomena": "<sta nedostaje ili nije moglo biti analizirano>"
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
        return_exceptions=True,
    )
    _nazivi = ("lessons_learned", "firm_dna", "case_patterns", "proactive_alerts", "decision_log")
    for _naziv, _r in zip(_nazivi, _rezultati):
        if isinstance(_r, Exception):
            logger.warning("[CASE_INTELLIGENCE] Podupit '%s' neuspesan (degradiran, nije fatalan): %s", _naziv, _r)
    lekcije, firm_dna_lista, case_patterns_lista, alertovi, odluke = (_d(r) for r in _rezultati)

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

        # Program Sigma, Master Sprint 004 (2026-08-06) — Forensic Discovery
        # finding, fixed immediately: "sledeci_korak"/"hitnost" above were an
        # INDEPENDENT GPT-generated "most urgent action" + urgency tier,
        # entirely disconnected from case_actions (the platform's own
        # canonical, deterministic action-tracking table, migration 099) —
        # exactly the "Copilot verzija / Strategy verzija / Case Commander
        # verzija" duplication this sprint's own Phase 2 forbids. Overridden
        # here with shared/case_readiness.py::top_open_action's own reading
        # of case_actions — the SAME source Workspace already treats as
        # canonical — whenever one exists; the GPT's own "kljucni_rizici"/
        # "relevantne_lekcije"/"komunikacioni_savet"/"potvrdjeni_obrasci"
        # fields are untouched (legitimately GPT-synthesized narrative/
        # pattern-matching content, not a competing action source).
        try:
            from shared.case_readiness import top_open_action
            _oa_r = await asyncio.to_thread(
                lambda: supa.table("case_actions").select("razlog,prioritet,rok,dedupe_key,status")
                    .eq("predmet_id", predmet_id).eq("status", "open").execute()
            )
            _top = top_open_action(_oa_r.data or [])
            if _top:
                _HITNOST_BY_PRIORITET = {
                    "critical": "odmah", "high": "ovu_nedelju",
                    "medium": "ovaj_mesec", "low": "ovaj_mesec", "informational": "ovaj_mesec",
                }
                briefing["sledeci_korak"] = _top.get("razlog") or briefing.get("sledeci_korak", "")
                briefing["razlog"] = "Najviši prioritet u Case Actions (case_actions.dedupe_key=%s)." % (_top.get("dedupe_key") or "?")
                briefing["hitnost"] = _HITNOST_BY_PRIORITET.get(_top.get("prioritet"), briefing.get("hitnost"))
        except Exception as _cae:
            logger.warning("[CASE_INTELLIGENCE] case_actions top-action override neuspešan (nastavlja sa GPT-ovom sopstvenom): %s", _cae)

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
