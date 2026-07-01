# -*- coding: utf-8 -*-
"""
Vindex AI — Confidence Auditor

Kalibracija AI pouzdanosti: kada sistem kaze VISOKO, koliko puta je u pravu?
Explainable Learning: odakle dolazi svaka preporuka (interna/RAG/zakon/AI).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("vindex.confidence_auditor")

# Idealni opsezi kalibracije (benchmark)
_IDEAL_CALIBRATION = {
    "visoka": (0.80, 1.00),   # 80-100% tacnost
    "srednja": (0.55, 0.79),  # 55-79% tacnost
    "niska": (0.20, 0.54),    # 20-54% tacnost
}

# Mapiranje ishoda → tacna preporuka
_POZITIVNI_ISHODI = {"pobeda", "nagodba"}


def calculate_source_weights(
    slicni_predmeti: int = 0,
    rag_hits: int = 0,
    zakon_hits: int = 0,
) -> dict:
    """Kalkulise izvore preporuke kao procenat od 100.

    Pozovi ovo kada pravis preporuku i imas podatke o izvorima.
    Rezultat spremi u recommendation_log.izvori_tezina.
    """
    raw = {
        "interna_istorija": slicni_predmeti * 3,  # firma > RAG > zakon
        "sudska_praksa": rag_hits * 2,
        "zakon": zakon_hits * 1,
    }
    total_raw = sum(raw.values())

    if total_raw == 0:
        return {
            "interna_istorija": 0,
            "sudska_praksa": 0,
            "zakon": 0,
            "ai_zakljucivanje": 100,
            "ukupno_izvora": 0,
        }

    skala = 85 / total_raw  # ostavlja 15% za AI reasoning minimum
    tezine = {k: min(round(v * skala), {"interna_istorija": 40, "sudska_praksa": 35, "zakon": 25}[k])
              for k, v in raw.items()}
    tezine["ai_zakljucivanje"] = max(100 - sum(tezine.values()), 5)
    tezine["ukupno_izvora"] = slicni_predmeti + rag_hits + zakon_hits
    return tezine


async def sync_outcomes_to_audit(supa, user_id: str) -> dict:
    """Sinhronizuje outcome_log sa recommendation_log → puni confidence_audit_log.

    Logika:
    - Preuzima sve prihvacene preporuke sa predmet_id
    - Trazi ishod u outcome_log za iste predmete
    - bila_tacna = True ako prihvacena AND ishod IN {pobeda, nagodba}
    - Inserts/updates confidence_audit_log (UNIQUE na recommendation_id)
    """
    try:
        rec_row = await asyncio.to_thread(
            lambda: supa.table("recommendation_log")
            .select("id, predmet_id, prihvacena, confidence_band, oblast_prava")
            .eq("user_id", user_id)
            .eq("prihvacena", True)
            .not_.is_("predmet_id", "null")
            .not_.is_("confidence_band", "null")
            .execute()
        )
        preporuke = rec_row.data or []
        if not preporuke:
            return {"synced": 0, "poruka": "Nema prihvacenih preporuka sa confidence_band i predmet_id"}

        predmet_ids = list({p["predmet_id"] for p in preporuke})

        out_row = await asyncio.to_thread(
            lambda: supa.table("outcome_log")
            .select("predmet_id, ishod")
            .eq("user_id", user_id)
            .in_("predmet_id", predmet_ids)
            .execute()
        )
        ishodi_map = {o["predmet_id"]: o["ishod"] for o in (out_row.data or [])}

        rows_to_upsert = []
        for p in preporuke:
            predmet_id = p["predmet_id"]
            ishod = ishodi_map.get(predmet_id)
            bila_tacna = None
            if ishod:
                bila_tacna = ishod in _POZITIVNI_ISHODI

            rows_to_upsert.append({
                "user_id": user_id,
                "recommendation_id": p["id"],
                "confidence_band": p["confidence_band"],
                "prihvacena": True,
                "ishod": ishod,
                "bila_tacna": bila_tacna,
                "oblast_prava": p.get("oblast_prava"),
                "predmet_id": predmet_id,
            })

        if rows_to_upsert:
            await asyncio.to_thread(
                lambda: supa.table("confidence_audit_log")
                .upsert(rows_to_upsert, on_conflict="recommendation_id")
                .execute()
            )

        return {
            "synced": len(rows_to_upsert),
            "sa_isohodom": sum(1 for r in rows_to_upsert if r["ishod"]),
            "tacnih": sum(1 for r in rows_to_upsert if r["bila_tacna"]),
        }

    except Exception as e:
        logger.error("sync_outcomes_to_audit: %s", e)
        raise


async def calculate_calibration(supa, user_id: str) -> dict:
    """Kalibracija po confidence bandu — srce Confidence Audita.

    Vraca:
    - Per-band: total, tacnih, tacnost_procenat, idealni_opseg, status_kalibracije
    - Ukupno: sve preporuke, prihvacene, sa isohodom
    - Brier score (mera preciznosti predikcije)
    - Preporuka (da li je sistem dobro kalibrisan)
    """
    try:
        # Sve preporuke ikad
        sve_row = await asyncio.to_thread(
            lambda: supa.table("recommendation_log")
            .select("confidence_band", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        ukupno_preporuka = sve_row.count or 0

        prihvacene_row = await asyncio.to_thread(
            lambda: supa.table("recommendation_log")
            .select("confidence_band", count="exact")
            .eq("user_id", user_id)
            .eq("prihvacena", True)
            .execute()
        )
        ukupno_prihvacenih = prihvacene_row.count or 0

        # Audit log za kalibraciju
        audit_row = await asyncio.to_thread(
            lambda: supa.table("confidence_audit_log")
            .select("confidence_band, bila_tacna, oblast_prava")
            .eq("user_id", user_id)
            .execute()
        )
        audit_data = audit_row.data or []

        # Grupisanje po bandu
        bands: dict[str, dict] = {
            "visoka": {"total": 0, "tacnih": 0, "oblasti": {}},
            "srednja": {"total": 0, "tacnih": 0, "oblasti": {}},
            "niska": {"total": 0, "tacnih": 0, "oblasti": {}},
        }

        brier_sum = 0.0
        brier_n = 0

        for row in audit_data:
            band = row.get("confidence_band")
            bila_tacna = row.get("bila_tacna")
            oblast = row.get("oblast_prava", "nepoznato")

            if band not in bands:
                continue
            if bila_tacna is None:
                continue  # jos nema ishoda, iskljuci iz kalibracije

            bands[band]["total"] += 1
            if bila_tacna:
                bands[band]["tacnih"] += 1

            oblast_stats = bands[band]["oblasti"].setdefault(oblast, {"total": 0, "tacnih": 0})
            oblast_stats["total"] += 1
            if bila_tacna:
                oblast_stats["tacnih"] += 1

            # Brier: p_predicted = 0.9 za visoka, 0.65 za srednja, 0.35 za niska
            p_predicted = {"visoka": 0.90, "srednja": 0.65, "niska": 0.35}[band]
            actual = 1 if bila_tacna else 0
            brier_sum += (p_predicted - actual) ** 2
            brier_n += 1

        result_bands = {}
        problemi = []

        for band, stats in bands.items():
            total = stats["total"]
            tacnih = stats["tacnih"]
            tacnost = round(tacnih / total * 100, 1) if total > 0 else None
            idealni_min, idealni_max = _IDEAL_CALIBRATION[band]
            idealni_min_pct = round(idealni_min * 100)
            idealni_max_pct = round(idealni_max * 100)

            if tacnost is None:
                status = "nema_podataka"
            elif tacnost / 100 < idealni_min:
                status = "prekomerno_pouzdan"  # kaze visoko, a grese
                if band in ("visoka", "srednja"):
                    problemi.append(f"Band '{band}': tacnost {tacnost}% je ispod ideala ({idealni_min_pct}%). AI je prekonidencan!")
            elif tacnost / 100 > idealni_max:
                status = "nedovoljno_pouzdan"  # kaze nisko, a pogadja
                if band == "niska":
                    problemi.append(f"Band 'niska': tacnost {tacnost}% je iznad ideala ({idealni_max_pct}%). AI podcenjuje svoju pouzdanost.")
            else:
                status = "kalibrisan"

            result_bands[band] = {
                "total_sa_isohodom": total,
                "tacnih": tacnih,
                "tacnost_procenat": tacnost,
                "idealni_opseg": f"{idealni_min_pct}-{idealni_max_pct}%",
                "status": status,
                "top_oblasti": sorted(
                    [{"oblast": k, **v, "tacnost": round(v["tacnih"]/v["total"]*100, 1) if v["total"] else None}
                     for k, v in stats["oblasti"].items()],
                    key=lambda x: x["total"], reverse=True
                )[:3],
            }

        brier_score = round(brier_sum / brier_n, 4) if brier_n > 0 else None
        # Brier score: 0 = savrsen, 0.25 = random, 1 = najgori
        brier_ocena = None
        if brier_score is not None:
            if brier_score < 0.10:
                brier_ocena = "Odlicna kalibracija"
            elif brier_score < 0.20:
                brier_ocena = "Dobra kalibracija"
            elif brier_score < 0.30:
                brier_ocena = "Prihvatljiva kalibracija"
            else:
                brier_ocena = "Los kalibracija — sistema treba retraining"

        sve_sa_isohodom = sum(b["total_sa_isohodom"] for b in result_bands.values())
        sve_tacnih = sum(b["tacnih"] for b in result_bands.values())

        return {
            "pregled": {
                "ukupno_preporuka_ikad": ukupno_preporuka,
                "ukupno_prihvacenih": ukupno_prihvacenih,
                "prihvacenost_procenat": round(ukupno_prihvacenih / ukupno_preporuka * 100, 1) if ukupno_preporuka else 0,
                "sa_poznatim_isohodom": sve_sa_isohodom,
                "tacnih_ukupno": sve_tacnih,
                "ukupna_tacnost": round(sve_tacnih / sve_sa_isohodom * 100, 1) if sve_sa_isohodom else None,
            },
            "po_bandu": result_bands,
            "brier_score": brier_score,
            "brier_ocena": brier_ocena,
            "problemi": problemi,
            "je_dobro_kalibrisan": len(problemi) == 0 and brier_score is not None and brier_score < 0.25,
            "preporuka_za_akciju": (
                problemi[0] if problemi
                else ("Sistem je dobro kalibrisan." if brier_score is not None
                      else "Nedovoljno podataka za kalibraciju. Potrebno je vise zatvorenih predmeta sa poznatim ishodima.")
            ),
        }

    except Exception as e:
        logger.error("calculate_calibration: %s", e)
        raise


async def get_explainable_recommendation(supa, recommendation_id: str, user_id: str) -> dict:
    """Vraca objasnjenje odakle dolazi preporuka (tezine izvora)."""
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("recommendation_log")
            .select("preporuka, tip_slucaja, confidence_band, oblast_prava, izvori_tezina, prihvacena, created_at")
            .eq("id", recommendation_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not row.data:
            return {"greska": "Preporuka nije pronadjena"}

        rec = row.data
        tezine = rec.get("izvori_tezina") or {}

        if not tezine or not tezine.get("ukupno_izvora"):
            return {
                "recommendation_id": recommendation_id,
                "preporuka": rec.get("preporuka"),
                "confidence_band": rec.get("confidence_band"),
                "izvori_tezina": None,
                "napomena": "Explainability podaci nisu dostupni — preporuka je napravljena pre uvodjenja sistema.",
            }

        # Pripremi citljivi prikaz
        komponente = []
        labele = {
            "interna_istorija": "Interna istorija firme",
            "sudska_praksa": "Sudska praksa (RAG)",
            "zakon": "Zakon / propisi",
            "ai_zakljucivanje": "AI zakljucivanje",
        }
        for kljuc, label in labele.items():
            procenat = tezine.get(kljuc, 0)
            if procenat > 0:
                komponente.append({"izvor": label, "kljuc": kljuc, "procenat": procenat})
        komponente.sort(key=lambda x: x["procenat"], reverse=True)

        return {
            "recommendation_id": recommendation_id,
            "preporuka": rec.get("preporuka"),
            "confidence_band": rec.get("confidence_band"),
            "oblast_prava": rec.get("oblast_prava"),
            "prihvacena": rec.get("prihvacena"),
            "created_at": rec.get("created_at"),
            "komponente": komponente,
            "dominantni_izvor": komponente[0]["izvor"] if komponente else None,
            "ukupno_izvora_analizirano": tezine.get("ukupno_izvora", 0),
        }
    except Exception as e:
        logger.error("get_explainable_recommendation: %s", e)
        raise
