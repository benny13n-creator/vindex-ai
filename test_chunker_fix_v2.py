# -*- coding: utf-8 -*-
"""
TEST v2 — _skini_zaglavlja() expanded safety check (25 articles).

Categories:
  KNOWN_STRIP  — articles where we confirmed absorbed headers in v1 test
  KNOWN_CLEAN  — control articles that must NOT be stripped
  EDGE         — edge cases: lists, abbreviations, institution names, long headers
  RANDOM       — first article found per law for 5 diverse laws

Verdict logic:
  KNOWN_STRIP + stripped   → CORRECT ✓
  KNOWN_STRIP + unchanged  → WRONG ✗  (regex missed it)
  KNOWN_CLEAN + unchanged  → CORRECT ✓
  KNOWN_CLEAN + stripped   → WRONG ✗  (false positive — stripped legitimate text)
  EDGE / RANDOM            → REVIEW (manual inspection of output needed)

DOES NOT modify Pinecone. DOES NOT run ingestion. Read-only.
"""

import sys, os, re, time
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from pinecone import Pinecone
from semantic_chunker import _skini_zaglavlja, _SECTION_HEADER_RE, STUB_THRESHOLD

pc    = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index = pc.Index(host=os.environ["PINECONE_HOST"])

DUMMY = [0.0] * 3072
SEP   = "═" * 90
SEP2  = "─" * 90

# ── Article list ──────────────────────────────────────────────────────────────
# (category, law, article, expected)
# expected: "strip" | "clean" | None (manual review)
FIXED_ARTICLES = [
    # ── KNOWN_STRIP — v1 test confirmed absorbed headers ──────────────────────
    ("KNOWN_STRIP", "KZ",                            "Član 203",  "strip"),
    ("KNOWN_STRIP", "KZ",                            "Član 204",  "strip"),
    ("KNOWN_STRIP", "porodicni zakon",               "Član 88",   "strip"),
    ("KNOWN_STRIP", "porodicni zakon",               "Član 170",  "strip"),
    ("KNOWN_STRIP", "porodicni zakon",               "Član 171",  "strip"),
    ("KNOWN_STRIP", "zakon o nasledjivanju",         "Član 9",    "strip"),
    ("KNOWN_STRIP", "zakon o radu",                  "Član 186",  "strip"),
    ("KNOWN_STRIP", "zakon o obligacionim odnosima", "Član 200",  "strip"),
    ("KNOWN_STRIP", "zakon o obligacionim odnosima", "Član 371",  "strip"),

    # ── KNOWN_CLEAN — controls, must NOT be stripped ──────────────────────────
    ("KNOWN_CLEAN", "zakon o radu",                  "Član 189",  "clean"),  # ends with period
    ("KNOWN_CLEAN", "zakon o obligacionim odnosima", "Član 124",  "clean"),  # raskid ugovora
    ("KNOWN_CLEAN", "KZ",                            "Član 19",   "clean"),  # nužna odbrana
    ("KNOWN_CLEAN", "zakonik o krivicnom postupku",  "Član 76",   "clean"),
    ("KNOWN_CLEAN", "zakonik o krivicnom postupku",  "Član 77",   "clean"),

    # ── EDGE CASES ────────────────────────────────────────────────────────────
    # Fragmented article (5 chunks) — tests that multi-chunk parent_text is handled
    ("EDGE",        "KZ",                            "Član 66",   None),

    # Constitutional article with enumerated list of protected characteristics
    # Concern: last list item may be Title Case without terminal punct
    ("EDGE",        "ustav republike srbije",        "Član 21",   None),

    # ZPP procedural article — likely references to other articles/paragraphs
    ("EDGE",        "zakon o parnicnom postupku",    "Član 365",  None),

    # ZR article — may end with "i sl." or "i dr." (abbreviations with periods)
    # Concern: abbreviation ends with period → should be SAFE
    ("EDGE",        "zakon o radu",                  "Član 65",   None),

    # ZN boundary defect area — ZN has 6 boundary defects, Član 15 is a known problem
    ("EDGE",        "zakon o nasledjivanju",         "Član 15",   None),

    # ZOO article with institution references mid-text
    ("EDGE",        "zakon o obligacionim odnosima", "Član 185",  None),
]

# ── Random sample: 5 diverse laws ─────────────────────────────────────────────
# Query each law with dummy vector, take first article returned
RANDOM_LAWS = [
    "zakon o privrednim drustvima",
    "zakon o zastiti podataka o licnosti",
    "zakon o digitalnoj imovini",
    "zakon o upravnim sporovima",
    "zakon o vanparnicnom postupku",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_parent_text(law: str, article: str) -> tuple[str, int]:
    """Returns (longest parent_text found, number of chunks). Empty string if none."""
    try:
        res = index.query(
            vector=DUMMY, top_k=10,
            filter={"law": {"$eq": law}, "article": {"$eq": article}},
            include_metadata=True,
        )
    except Exception as e:
        return f"FETCH_ERROR: {e}", 0

    if not res.matches:
        return "", 0

    best = ""
    for m in res.matches:
        pt = (m.metadata or {}).get("parent_text", "") or ""
        if len(pt) > len(best):
            best = pt
    return best, len(res.matches)


def fetch_random_article(law: str) -> tuple[str, str, str, int]:
    """Returns (article_label, parent_text, law, chunks). Empty if none found."""
    try:
        res = index.query(
            vector=DUMMY, top_k=5,
            filter={"law": {"$eq": law}},
            include_metadata=True,
        )
    except Exception as e:
        return "", f"FETCH_ERROR: {e}", law, 0

    for m in res.matches:
        meta = m.metadata or {}
        article = meta.get("article", "")
        pt = meta.get("parent_text", "") or ""
        if article and pt:
            return article, pt, law, 1
    return "", "", law, 0


def verdict_line(category: str, expected, was_stripped: bool) -> str:
    if category == "KNOWN_STRIP":
        return "CORRECT ✓" if was_stripped else "WRONG ✗  (regex missed header)"
    elif category == "KNOWN_CLEAN":
        return "CORRECT ✓" if not was_stripped else "WRONG ✗  (false positive — stripped legitimate text)"
    else:
        return "REVIEW — see content above"


# ── Run test ──────────────────────────────────────────────────────────────────
out_lines: list[str] = []

def emit(line: str = "") -> None:
    print(line)
    out_lines.append(line)

emit("TEST v2 — _skini_zaglavlja() expanded safety check")
emit(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
emit()

# Collect random articles
random_articles = []
emit("Fetching random articles from 5 diverse laws...")
for law in RANDOM_LAWS:
    art_label, pt, law_, chunks = fetch_random_article(law)
    if art_label:
        random_articles.append(("RANDOM", law_, art_label, None, pt, chunks))
        emit(f"  {law_:<55} → {art_label}")
    else:
        emit(f"  {law_:<55} → (no result)")
emit()

all_articles = []
for row in FIXED_ARTICLES:
    cat, law, article, expected = row
    pt, chunks = fetch_parent_text(law, article)
    all_articles.append((cat, law, article, expected, pt, chunks))

for row in random_articles:
    cat, law, article, expected, pt, chunks = row
    all_articles.append((cat, law, article, expected, pt, chunks))

total = len(all_articles)
emit(f"Total articles to test: {total}")
emit(SEP)

correct = wrong = review = skipped = 0

for idx, (cat, law, article, expected, parent_text, chunks) in enumerate(all_articles, 1):
    emit()
    emit(f"[{idx:02d}/{total}] {cat:<12}  {law} · {article}")
    emit(SEP2)

    if not parent_text or parent_text.startswith("FETCH_ERROR"):
        emit(f"  Chunks: {chunks}  |  parent_text: {'EMPTY' if not parent_text else parent_text}")
        emit(f"  Verdict: SKIPPED (no data)")
        skipped += 1
        continue

    orig_len  = len(parent_text)
    clean, stripped = _skini_zaglavlja(parent_text)
    clean_len = len(clean)
    removed   = orig_len - clean_len
    was_stripped = bool(stripped)
    stub_flag = "  ← STUB" if clean_len < STUB_THRESHOLD else ""

    verdict = verdict_line(cat, expected, was_stripped)
    if "CORRECT" in verdict:
        correct += 1
    elif "WRONG" in verdict:
        wrong += 1
    else:
        review += 1

    emit(f"  Chunks in index : {chunks}")
    emit(f"  Original length : {orig_len} chars")
    emit(f"  After strip     : {clean_len} chars{stub_flag}")
    emit(f"  Chars removed   : {removed}")
    emit(f"  Verdict         : {verdict}")

    # Last 100 chars BEFORE strip
    before_tail = parent_text[-100:].replace('\n', '↵')
    emit()
    emit(f"  BEFORE (last 100 chars): {before_tail!r}")

    if was_stripped:
        # What got stripped
        emit(f"  STRIPPED:")
        for line in stripped.split('\n'):
            if line.strip():
                emit(f"    {line.strip()!r}")
        # Last 100 chars AFTER strip
        after_tail = clean[-100:].replace('\n', '↵') if clean else "(empty)"
        emit(f"  AFTER  (last 100 chars): {after_tail!r}")
    else:
        emit(f"  AFTER  (last 100 chars): (same — nothing stripped)")

    emit()

# ── Summary ────────────────────────────────────────────────────────────────────
emit(SEP)
emit("SUMMARY")
emit(SEP)
emit()
emit(f"  Total tested  : {total}")
emit(f"  CORRECT ✓    : {correct}  (KNOWN_STRIP caught + KNOWN_CLEAN untouched)")
emit(f"  WRONG   ✗    : {wrong}")
emit(f"  REVIEW        : {review}  (edge cases + random — inspect output above)")
emit(f"  SKIPPED       : {skipped}  (no data in index)")
emit()

known_strip_total = sum(1 for r in all_articles if r[0] == "KNOWN_STRIP" and r[4])
known_clean_total = sum(1 for r in all_articles if r[0] == "KNOWN_CLEAN" and r[4])
emit(f"  KNOWN_STRIP pass rate: {sum(1 for r in all_articles if r[0]=='KNOWN_STRIP' and r[4] and _skini_zaglavlja(r[4])[1])}/{known_strip_total}")
emit(f"  KNOWN_CLEAN pass rate: {sum(1 for r in all_articles if r[0]=='KNOWN_CLEAN' and r[4] and not _skini_zaglavlja(r[4])[1])}/{known_clean_total}")
emit()
if wrong == 0:
    emit("  ALL KNOWN CASES PASS — ready for commit approval")
else:
    emit(f"  {wrong} FAILURE(S) — see WRONG verdicts above before committing")
emit()
emit(f"Timestamp end: {time.strftime('%Y-%m-%d %H:%M:%S')}")

# ── Save output ────────────────────────────────────────────────────────────────
out_path = os.path.join(os.path.dirname(__file__), "test_chunker_fix_v2.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('\n'.join(out_lines) + '\n')
print(f"\n[Output saved to: {out_path}]")
