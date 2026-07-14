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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.usage import UsageService

logger = logging.getLogger("vindex.case_intelligence")
router = APIRouter(prefix="/api/intelligence", tags=["case_intelligence"])

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

    predmet_row, lekcije_row, dna_row, patterns_row, alerts_row, decisions_row = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti")
            .select("naziv, tip, status, oblast_prava, opis, klijent_id, case_dna")
            .eq("id", predmet_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        ),
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
            .select("tekst_alerta, tip_alerta, hitnost")
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
    )

    predmet = predmet_row.data or {}
    klijent_id = predmet.get("klijent_id")

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
        "lekcije": lekcije_row.data or [],
        "firm_dna": dna_row.data or [],
        "case_patterns": patterns_row.data or [],
        "alertovi": alerts_row.data or [],
        "odluke": decisions_row.data or [],
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
            lines.append(f"  ! [{a.get('hitnost','?')}] {a.get('tekst_alerta','')[:150]}")

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
async def case_intelligence_briefing(predmet_id: str, user=Depends(PermissionService.require("case_intelligence"))):
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

        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _BRIEFING_SYSTEM},
                {"role": "user", "content": context_text[:10000]}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        briefing = json.loads(resp.choices[0].message.content)

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
        logger.error("case_intelligence_briefing: %s", e)
        raise HTTPException(500, str(e))


@router.get("/predmeti/{predmet_id}/briefing/poslednji")
async def get_poslednji_briefing(predmet_id: str, user=Depends(get_current_user)):
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
