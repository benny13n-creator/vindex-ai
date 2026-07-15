# -*- coding: utf-8 -*-
"""
Vindex AI — scripts/intake_accuracy_benchmark.py

Smart Intake Engine — Validation Sprint (founder, 2026-07-15; refined same
day with ML-practice feedback). Runs the REAL production classification/
extraction code (shared/intake_classify.py, shared/intake_extract.py — not
a reimplementation) against golden_dataset/, compares to hand-verified
ground truth, and reports accuracy broken down by entity type, by dataset
(A clean digital / B typical Serbian reality / C nightmare), and by
per-document difficulty (easy/medium/hard/nightmare) — a single blended
average hides exactly where the system struggles, which is the point of
having three deliberately different collections instead of one.

Documents with `agreement: false` (two annotators disagreed on the ground
truth itself) are reported SEPARATELY, not folded into the headline
accuracy number — a mismatch there may mean the ground truth is contested,
not that the extraction was wrong. Founder's framing: "Ako se dva advokata
ne slažu oko roka, onda AI možda nije pogrešio. Ground truth je pogrešan."

This is deliberately separate from the unit test suite: unit tests prove
the code executes correctly against fixtures. This proves the AI gets the
right answer against real documents. "1574 testova prolazi" and "case
number accuracy 98.7%" are different claims — this script produces the
second one, honestly, only once golden_dataset/ has real content (see
golden_dataset/README.md — it ships empty on purpose, nothing here is
fabricated to look like real accuracy data).

Usage:
    python scripts/intake_accuracy_benchmark.py
    python scripts/intake_accuracy_benchmark.py --no-save   # don't append to history

Exit code: 0 always (this is a report, not a pass/fail gate — accuracy
targets are a founder/product decision, not something this script enforces
by failing a build).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(dotenv_path=ROOT / ".env")

GOLDEN_DIR = ROOT / "golden_dataset"
DOCUMENTS_DIR = GOLDEN_DIR / "documents"
ANNOTATIONS_PATH = GOLDEN_DIR / "annotations.json"
HISTORY_PATH = ROOT / "docs" / "accuracy_history.json"

_DATASET_FOLDERS = ("a_clean_digital", "b_typical_serbian", "c_nightmare")
_DIFFICULTY_ORDER = ("easy", "medium", "hard", "nightmare")

# Free-text fields (LLM-extracted) get lenient substring comparison — exact
# phrasing/declension varies in Serbian ("Osnovni sud" vs "Osnovnog suda").
# Structured fields (regex-extracted) must match closely after normalization
# — they're deterministic, so near-misses are real bugs, not acceptable variance.
_LENIENT_ENTITY_TYPES = {"judge", "plaintiff", "defendant", "court", "law_cited"}


def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.rstrip(".,;:")
    return s


def _values_match(entity_type: str, expected: str, actual: str) -> bool:
    if not expected:
        return True  # ground truth says "not applicable" — nothing to score
    if not actual:
        return False
    exp_n, act_n = _normalize(expected), _normalize(actual)
    if entity_type in _LENIENT_ENTITY_TYPES:
        return exp_n in act_n or act_n in exp_n
    return exp_n == act_n


def _derive_dataset(filename: str) -> str | None:
    """dataset se NE unosi ručno u annotations.json — izvodi se iz toga u
    kom podfolderu fajl fizički živi (golden_dataset/README.md). Jedan manji
    izvor greške pri prikupljanju pod vremenskim pritiskom."""
    prefix = filename.split("/", 1)[0] if "/" in filename else None
    return prefix if prefix in _DATASET_FOLDERS else None


async def _run_one(doc: dict) -> dict:
    from shared.intake_classify import classify
    from shared.intake_extract import extract_all_entities
    from uploaded_doc.extractor import extract as extract_text

    filename = doc["filename"]
    path = DOCUMENTS_DIR / filename
    meta = {
        "document_id": doc["document_id"],
        "filename": filename,
        "dataset": _derive_dataset(filename),
        "difficulty": doc.get("difficulty"),
        "agreement": doc.get("agreement", True),  # nedostaje polje = pretpostavka da je jedan anotator dovoljan (True), ne da se ne slažu
    }

    if not path.exists():
        return {**meta, "error": f"fajl nije pronađen: {filename}"}

    text, is_scanned, ocr_used = await asyncio.to_thread(extract_text, path)
    if is_scanned:
        return {**meta, "error": "OCR neuspešan — dokument izostavljen iz merenja tačnosti (to je zaseban KPI, ne accuracy)"}

    expected = doc.get("expected", {})
    result = dict(meta)

    klasa = await classify(text)
    result["document_type"] = {
        "expected": expected.get("document_type"),
        "actual": klasa["document_type"],
        "match": expected.get("document_type") == klasa["document_type"] if expected.get("document_type") else None,
        "confidence": klasa["confidence"],
        "method": klasa["method"],
    }

    entities = await extract_all_entities(text)
    entity_by_type = {e["entity_type"]: e for e in entities}
    expected_entities = expected.get("entities", {}) or {}

    result["entities"] = {}
    for entity_type, exp_value in expected_entities.items():
        actual_entity = entity_by_type.get(entity_type, {})
        actual_value = actual_entity.get("value")
        match = _values_match(entity_type, exp_value, actual_value)
        result["entities"][entity_type] = {
            "expected": exp_value, "actual": actual_value, "match": match,
            "confidence": actual_entity.get("confidence"),
        }

    return result


def _score_entities(results: list[dict]) -> dict:
    per_entity: dict[str, dict] = {}
    for r in results:
        for entity_type, e in r.get("entities", {}).items():
            bucket = per_entity.setdefault(entity_type, {"correct": 0, "total": 0})
            bucket["total"] += 1
            if e["match"]:
                bucket["correct"] += 1
    return {
        entity_type: round(b["correct"] / b["total"], 4) if b["total"] else None
        for entity_type, b in per_entity.items()
    }


def _classification_accuracy(results: list[dict]) -> float | None:
    scored = [r for r in results if r.get("document_type", {}).get("match") is not None]
    if not scored:
        return None
    return round(sum(1 for r in scored if r["document_type"]["match"]) / len(scored), 4)


def _aggregate(results: list[dict]) -> dict:
    errors = [r for r in results if "error" in r]
    scoreable = [r for r in results if "error" not in r]

    # Sporne anotacije (dva anotatora se nisu složila) — izveštava se
    # ODVOJENO, ne meša sa AI greškama (vidi modul docstring).
    disagreement = [r for r in scoreable if r.get("agreement") is False]
    agreed = [r for r in scoreable if r.get("agreement") is not False]

    by_dataset = {}
    for ds in _DATASET_FOLDERS:
        subset = [r for r in agreed if r.get("dataset") == ds]
        if subset:
            by_dataset[ds] = {
                "broj_dokumenata": len(subset),
                "klasifikacija_tacnost": _classification_accuracy(subset),
                "ekstrakcija_tacnost_po_polju": _score_entities(subset),
            }

    by_difficulty = {}
    for diff in _DIFFICULTY_ORDER:
        subset = [r for r in agreed if r.get("difficulty") == diff]
        if subset:
            all_matches = [e["match"] for r in subset for e in r.get("entities", {}).values()]
            by_difficulty[diff] = {
                "broj_dokumenata": len(subset),
                "ukupna_tacnost": round(sum(all_matches) / len(all_matches), 4) if all_matches else None,
            }

    return {
        "ukupno_dokumenata": len(results),
        "obrađeno": len(scoreable),
        "greske_ocr": len(errors),
        "sporne_anotacije": len(disagreement),
        "klasifikacija_tacnost": _classification_accuracy(agreed),
        "ekstrakcija_tacnost_po_polju": _score_entities(agreed),
        "po_dataset_setu": by_dataset,
        "po_tezini": by_difficulty,
    }


def _print_report(summary: dict, previous: dict | None) -> None:
    print("=" * 70)
    print("SMART INTAKE — ACCURACY BENCHMARK (golden_dataset/)")
    print("=" * 70)
    print(f"  Dokumenata: {summary['ukupno_dokumenata']}  (obrađeno: {summary['obrađeno']}, OCR greške: {summary['greske_ocr']}, sporne anotacije: {summary['sporne_anotacije']})")
    if summary["klasifikacija_tacnost"] is not None:
        print(f"  Klasifikacija (ukupno): {summary['klasifikacija_tacnost']*100:.1f}%")

    print()
    print("  Ekstrakcija po polju (ukupno):")
    prev_fields = (previous or {}).get("ekstrakcija_tacnost_po_polju", {})
    for entity_type, acc in sorted(summary["ekstrakcija_tacnost_po_polju"].items()):
        if acc is None:
            print(f"    {entity_type:15} nema anotiranih primera")
            continue
        line = f"    {entity_type:15} {acc*100:5.1f}%"
        prev_acc = prev_fields.get(entity_type)
        if prev_acc is not None:
            delta = (acc - prev_acc) * 100
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
            line += f"   ({prev_acc*100:.1f}% → {acc*100:.1f}%, {arrow}{abs(delta):.1f})"
        print(line)

    if summary["po_dataset_setu"]:
        print()
        print("  Po dataset-u (A čist digitalni / B tipična realnost / C nightmare):")
        for ds, stats in summary["po_dataset_setu"].items():
            kt = stats["klasifikacija_tacnost"]
            print(f"    {ds:18} n={stats['broj_dokumenata']:<4} klasifikacija={f'{kt*100:.1f}%' if kt is not None else 'n/a'}")

    if summary["po_tezini"]:
        print()
        print("  Po težini (easy/medium/hard/nightmare):")
        for diff in _DIFFICULTY_ORDER:
            stats = summary["po_tezini"].get(diff)
            if stats:
                acc = stats["ukupna_tacnost"]
                print(f"    {diff:12} n={stats['broj_dokumenata']:<4} tačnost={f'{acc*100:.1f}%' if acc is not None else 'n/a'}")

    if summary["sporne_anotacije"]:
        print()
        print(f"  ⚠ {summary['sporne_anotacije']} dokumenata sa agreement=false — isključeno iz gornjih brojeva.")
        print("    Neslaganje anotatora ne znači nužno da je AI pogrešio — proveriti ground truth.")

    print("=" * 70)


def main() -> int:
    if not ANNOTATIONS_PATH.exists():
        print(f"[ERROR] {ANNOTATIONS_PATH} ne postoji.", file=sys.stderr)
        return 2

    annotations = json.loads(ANNOTATIONS_PATH.read_text(encoding="utf-8"))
    dokumenti = annotations.get("dokumenti", [])

    if not dokumenti:
        print("[INFO] golden_dataset/annotations.json je prazan — nema šta da se meri.")
        print("       Vidi golden_dataset/README.md za format anotacija (3 dataset-a, difficulty, agreement).")
        print("       Ovo je OČEKIVANO stanje dok se ne dodaju stvarni dokumenti — nije greška.")
        return 0

    results = asyncio.run(_run_all(dokumenti))
    summary = _aggregate(results)

    previous = None
    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if history:
            previous = history[-1]["summary"]

    _print_report(summary, previous)

    if "--no-save" not in sys.argv:
        _append_history(summary)

    return 0


async def _run_all(dokumenti: list[dict]) -> list[dict]:
    return [await _run_one(doc) for doc in dokumenti]


def _append_history(summary: dict) -> None:
    HISTORY_PATH.parent.mkdir(exist_ok=True)
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else []
    history.append({"at": datetime.now(timezone.utc).isoformat(), "summary": summary})
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] Rezultat dodat u {HISTORY_PATH.relative_to(ROOT)} — 'git log -p' na taj fajl je istorija tačnosti kroz vreme.")


if __name__ == "__main__":
    sys.exit(main())
