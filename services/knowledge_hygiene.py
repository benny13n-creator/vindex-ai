# -*- coding: utf-8 -*-
"""
Vindex AI — Knowledge Hygiene

Sprecava digitalni haos kada firma akumulira hiljade lekcija i preporuka.
Automatski detektuje:
  - Duplikate / slicne lekcije (Jaccard similarity)
  - Zastarele lekcije (nisu pristupane u periodu decay za oblast prava)
  - Kontradikcije u case_patterns (isti tip slucaja, suprotne preporuke)
  - Lekcije sa niskom stopom potvrdjivanja (niska_potvrda)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("vindex.knowledge_hygiene")

# Prag za duplikate (Jaccard similarity na prvim 60 reci)
_DUPLIKAT_THRESHOLD = 0.55

# Prag za niska_potvrda: lekcija ima > N predmeta ali nula potvrda
_NISKA_POTVRDA_MIN_PREDMETA = 5

# Decay po oblasti (dani bez pristupa → zastarela)
_DECAY_DAYS = {
    "poresko": 180,
    "radno": 365,
    "procesno": 365,
    "obligaciono": 730,
    "ustavno": 1095,
    "default": 547,
}


def _jaccard(text1: str, text2: str, max_words: int = 60) -> float:
    words1 = set(text1.lower().split()[:max_words])
    words2 = set(text2.lower().split()[:max_words])
    if not words1 or not words2:
        return 0.0
    return len(words1 & words2) / len(words1 | words2)


async def _get_active_lessons(supa, user_id: str) -> list:
    row = await asyncio.to_thread(
        lambda: supa.table("lessons_learned")
        .select("id, sadrzaj, oblast_prava, kategorija, broj_predmeta, pouzdanost, status_lekcije, potvrdio, poslednji_pristup, created_at")
        .eq("user_id", user_id)
        .in_("status_lekcije", ["predlog_ai", "usvojena_praksa"])
        .order("created_at")
        .execute()
    )
    return row.data or []


async def _get_active_patterns(supa, user_id: str) -> list:
    row = await asyncio.to_thread(
        lambda: supa.table("case_patterns")
        .select("id, tip_spora, faktor, pobede, porazi, ukupno")
        .eq("user_id", user_id)
        .execute()
    )
    # Normalizuj: dodaj win_rate za kompatibilnost sa scan_contradictions
    patterns = []
    for p in (row.data or []):
        ukupno = p.get("ukupno") or 0
        pobede = p.get("pobede") or 0
        p["win_rate"] = round(pobede / ukupno * 100, 1) if ukupno > 0 else 0.0
        patterns.append(p)
    return patterns


async def _insert_hygiene_findings(supa, user_id: str, findings: list[dict]) -> int:
    """Upisuje nalaze u knowledge_hygiene_log. Bulk: 1 SELECT + 1 INSERT umesto N*2."""
    if not findings:
        return 0

    existing_row = await asyncio.to_thread(
        lambda: supa.table("knowledge_hygiene_log")
        .select("tip_akcije, entitet_id")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .execute()
    )
    existing_keys = {
        (r["tip_akcije"], r["entitet_id"])
        for r in (existing_row.data or [])
    }

    to_insert = [
        {"user_id": user_id, **f}
        for f in findings
        if (f["tip_akcije"], f["entitet_id"]) not in existing_keys
    ]

    if not to_insert:
        return 0

    await asyncio.to_thread(
        lambda: supa.table("knowledge_hygiene_log").insert(to_insert).execute()
    )
    return len(to_insert)


async def scan_duplicates(supa, user_id: str) -> list[dict]:
    """Detektuje slicne lekcije (Jaccard >= 0.55 na istoj oblasti/kategoriji)."""
    lessons = await _get_active_lessons(supa, user_id)
    findings = []

    for i, l1 in enumerate(lessons):
        for l2 in lessons[i + 1:]:
            if l1.get("oblast_prava") != l2.get("oblast_prava"):
                continue
            if l1.get("kategorija") != l2.get("kategorija"):
                continue
            sim = _jaccard(l1.get("sadrzaj", ""), l2.get("sadrzaj", ""))
            if sim >= _DUPLIKAT_THRESHOLD:
                # Preporucujemo zadrzati onu sa vise potvrda / vise predmeta
                zadrzi = l1 if (l1.get("broj_predmeta") or 0) >= (l2.get("broj_predmeta") or 0) else l2
                obrisi = l2 if zadrzi["id"] == l1["id"] else l1
                findings.append({
                    "tip_akcije": "duplikat",
                    "entitet_tip": "lekcija",
                    "entitet_id": obrisi["id"],
                    "entitet2_id": zadrzi["id"],
                    "skor": round(sim * 100, 1),
                    "opis": (
                        f"Slicnost {round(sim*100)}%: "
                        f"'{obrisi['sadrzaj'][:80]}...' | "
                        f"Preporuka: zadrzati lekciju sa vise podataka."
                    ),
                })

    return findings


async def scan_stale(supa, user_id: str) -> list[dict]:
    """Detektuje lekcije koje nisu pristupane duze od decay perioda za njihovu oblast."""
    lessons = await _get_active_lessons(supa, user_id)
    findings = []
    now = datetime.now(timezone.utc)

    for l in lessons:
        oblast = (l.get("oblast_prava") or "default").lower()
        decay = _DECAY_DAYS.get(oblast, _DECAY_DAYS["default"])

        ref_time_str = l.get("poslednji_pristup") or l.get("created_at")
        if not ref_time_str:
            continue

        try:
            ref_time = datetime.fromisoformat(ref_time_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        dana = (now - ref_time).days
        if dana > decay:
            findings.append({
                "tip_akcije": "zastarela",
                "entitet_tip": "lekcija",
                "entitet_id": l["id"],
                "entitet2_id": None,
                "skor": float(dana),
                "opis": (
                    f"Nije pristupano {dana} dana "
                    f"(threshold za '{oblast}': {decay}d). "
                    f"Lekcija: '{l['sadrzaj'][:100]}'"
                ),
            })

    return findings


async def scan_contradictions(supa, user_id: str) -> list[dict]:
    """Detektuje case_patterns sa istim tip_spora ali razlicitim faktorima i lose win_rate."""
    patterns = await _get_active_patterns(supa, user_id)
    findings = []

    by_type: dict[str, list] = {}
    for p in patterns:
        key = (p.get("tip_spora") or "").strip().lower()
        if key:
            by_type.setdefault(key, []).append(p)

    for tip, group in by_type.items():
        if len(group) < 2:
            continue
        faktori = list({p.get("faktor", "").strip()[:120] for p in group if p.get("faktor")})
        if len(faktori) < 2:
            continue

        group_sorted = sorted(group, key=lambda x: x.get("win_rate") or 0, reverse=True)
        dominant = group_sorted[0]
        konfliktni = group_sorted[1]

        findings.append({
            "tip_akcije": "kontradikcija",
            "entitet_tip": "pattern",
            "entitet_id": konfliktni["id"],
            "entitet2_id": dominant["id"],
            "skor": None,
            "opis": (
                f"Kontradikcija za '{tip}': "
                f"Faktor A (win:{dominant.get('win_rate',0):.0f}%): '{faktori[0][:60]}' "
                f"vs Faktor B (win:{konfliktni.get('win_rate',0):.0f}%): '{faktori[1][:60]}'"
            ),
        })

    return findings


async def scan_low_confirmation(supa, user_id: str) -> list[dict]:
    """Detektuje lekcije sa mnogo predmeta ali bez potvrde partnera (status=predlog_ai)."""
    lessons = await _get_active_lessons(supa, user_id)
    findings = []

    for l in lessons:
        if (
            l.get("status_lekcije") == "predlog_ai"
            and not l.get("potvrdio")
            and (l.get("broj_predmeta") or 0) >= _NISKA_POTVRDA_MIN_PREDMETA
        ):
            findings.append({
                "tip_akcije": "niska_potvrda",
                "entitet_tip": "lekcija",
                "entitet_id": l["id"],
                "entitet2_id": None,
                "skor": float(l.get("broj_predmeta") or 0),
                "opis": (
                    f"Lekcija ima {l.get('broj_predmeta')} predmeta ali nikad nije "
                    f"potvrdjenu od partnera (status: predlog_ai). "
                    f"Sadrzaj: '{l['sadrzaj'][:100]}'"
                ),
            })

    return findings


async def run_full_scan(supa, user_id: str) -> dict:
    """Pokrece sve 4 skeniranja i upisuje nalaze u knowledge_hygiene_log."""
    duplicates, stale, contradictions, low_conf = await asyncio.gather(
        scan_duplicates(supa, user_id),
        scan_stale(supa, user_id),
        scan_contradictions(supa, user_id),
        scan_low_confirmation(supa, user_id),
    )

    all_findings = duplicates + stale + contradictions + low_conf
    inserted = await _insert_hygiene_findings(supa, user_id, all_findings)

    return {
        "duplikati": len(duplicates),
        "zastarele": len(stale),
        "kontradikcije": len(contradictions),
        "niska_potvrda": len(low_conf),
        "ukupno_pronadjeno": len(all_findings),
        "novo_upisano": inserted,
    }


async def merge_lessons(supa, user_id: str, zadrzi_id: str, arhiviraj_id: str) -> dict:
    """Spaja dve slicne lekcije: arhivira jednu, cuva drugu. Azurira hygiene_log."""
    row = await asyncio.to_thread(
        lambda: supa.table("lessons_learned")
        .select("id, sadrzaj, broj_predmeta, status_lekcije")
        .eq("user_id", user_id)
        .in_("id", [zadrzi_id, arhiviraj_id])
        .execute()
    )
    if not row.data or len(row.data) < 2:
        raise ValueError("Jedna ili obe lekcije nisu pronadjene")

    lessons = {l["id"]: l for l in row.data}
    zadrzi = lessons.get(zadrzi_id)
    arhiviraj = lessons.get(arhiviraj_id)
    if not zadrzi or not arhiviraj:
        raise ValueError("Lekcije ne postoje ili ne pripadaju ovom korisniku")

    # Saberi br_predmeta, arhiviraj jednu, ostavi drugu
    novi_br = (zadrzi.get("broj_predmeta") or 0) + (arhiviraj.get("broj_predmeta") or 0)

    await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("lessons_learned")
            .update({"broj_predmeta": novi_br})
            .eq("id", zadrzi_id)
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("lessons_learned")
            .update({"status_lekcije": "zastarela", "grupa_id": zadrzi_id})
            .eq("id", arhiviraj_id)
            .execute()
        ),
    )

    # Markuj hygiene nalaz kao sprovedeno
    await asyncio.to_thread(
        lambda: supa.table("knowledge_hygiene_log")
        .update({"status": "sprovedeno", "updated_at": "now()"})
        .eq("user_id", user_id)
        .eq("tip_akcije", "duplikat")
        .eq("entitet_id", arhiviraj_id)
        .execute()
    )

    return {
        "zadrzana_lekcija": zadrzi_id,
        "arhivirana_lekcija": arhiviraj_id,
        "novi_broj_predmeta": novi_br,
    }


async def archive_stale_lessons(supa, user_id: str) -> dict:
    """Automatski arhivira sve zastarele lekcije sa pending hygiene nalazima."""
    row = await asyncio.to_thread(
        lambda: supa.table("knowledge_hygiene_log")
        .select("entitet_id")
        .eq("user_id", user_id)
        .eq("tip_akcije", "zastarela")
        .eq("status", "pending")
        .execute()
    )
    ids = [r["entitet_id"] for r in (row.data or [])]
    if not ids:
        return {"arhivirano": 0}

    await asyncio.to_thread(
        lambda: supa.table("lessons_learned")
        .update({"status_lekcije": "zastarela"})
        .eq("user_id", user_id)
        .in_("id", ids)
        .execute()
    )

    await asyncio.to_thread(
        lambda: supa.table("knowledge_hygiene_log")
        .update({"status": "sprovedeno", "updated_at": "now()"})
        .eq("user_id", user_id)
        .eq("tip_akcije", "zastarela")
        .eq("status", "pending")
        .execute()
    )

    return {"arhivirano": len(ids), "lekcija_arhivirano": ids}
