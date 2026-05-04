# -*- coding: utf-8 -*-
"""
TEST v3 — _skini_zaglavlja() full validation after numbered-header branch added.

Changes from v2:
  - KZ 19, ZKP 76, ZKP 77, ZOO 124 moved from KNOWN_CLEAN → KNOWN_STRIP
    (v2 revealed these DO have absorbed headers; the KNOWN_CLEAN labels were wrong)
  - ZN 15 added as KNOWN_STRIP (has "3. Treći nasledni red" — numbered header)
  - ZR 186 kept as KNOWN_STRIP (has "6. Posebna zaštita..." — now caught by new branch)
  - 4 fresh KNOWN_CLEAN controls (ZR 189 confirmed + ZN 1, ZOO 1, ZPP 1 as introductory)
  - EDGE and RANDOM unchanged

Verdict logic:
  KNOWN_STRIP + stripped   → CORRECT ✓
  KNOWN_STRIP + unchanged  → WRONG ✗  (regex missed header)
  KNOWN_CLEAN + unchanged  → CORRECT ✓
  KNOWN_CLEAN + stripped   → WRONG ✗  (false positive — stripped legitimate text)
  EDGE / RANDOM            → REVIEW (manual inspection)

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
    # ── KNOWN_STRIP — confirmed absorbed headers (v2 verified or v3 new) ──────
    ("KNOWN_STRIP", "KZ",                            "Član 203",  "strip"),
    ("KNOWN_STRIP", "KZ",                            "Član 204",  "strip"),
    ("KNOWN_STRIP", "porodicni zakon",               "Član 88",   "strip"),
    ("KNOWN_STRIP", "porodicni zakon",               "Član 170",  "strip"),
    ("KNOWN_STRIP", "porodicni zakon",               "Član 171",  "strip"),
    ("KNOWN_STRIP", "zakon o nasledjivanju",         "Član 9",    "strip"),
    ("KNOWN_STRIP", "zakon o radu",                  "Član 186",  "strip"),  # "6. Posebna zaštita..." — numbered header
    ("KNOWN_STRIP", "zakon o obligacionim odnosima", "Član 200",  "strip"),
    ("KNOWN_STRIP", "zakon o obligacionim odnosima", "Član 371",  "strip"),
    # Moved from KNOWN_CLEAN in v2 — all confirmed to have absorbed headers:
    ("KNOWN_STRIP", "KZ",                            "Član 19",   "strip"),  # was wrongly labeled clean
    ("KNOWN_STRIP", "zakon o obligacionim odnosima", "Član 124",  "strip"),  # was wrongly labeled clean
    ("KNOWN_STRIP", "zakonik o krivicnom postupku",  "Član 76",   "strip"),  # was wrongly labeled clean
    ("KNOWN_STRIP", "zakonik o krivicnom postupku",  "Član 77",   "strip"),  # was wrongly labeled clean
    # New — numbered header pattern:
    ("KNOWN_STRIP", "zakon o nasledjivanju",         "Član 15",   "strip"),  # ends with "3. Treći nasledni red"

    # Also KNOWN_STRIP — v3 revealed Article 1 of most laws is at a chapter boundary:
    ("KNOWN_STRIP", "zakon o nasledjivanju",         "Član 1",    "strip"),  # "Osnovi nasleđivanja"
    ("KNOWN_STRIP", "zakon o obligacionim odnosima", "Član 1",    "strip"),  # "Strane u obligacionim odnosima"
    ("KNOWN_STRIP", "zakonik o krivicnom postupku",  "Član 1",    "strip"),  # "Značenje izraza"

    # ── KNOWN_CLEAN — confirmed NOT stripped across all test runs ─────────────
    ("KNOWN_CLEAN", "zakon o radu",                  "Član 189",  "clean"),  # confirmed v2 + v3
    ("KNOWN_CLEAN", "zakon o parnicnom postupku",    "Član 1",    "clean"),  # confirmed v3
    ("KNOWN_CLEAN", "zakon o radu",                  "Član 1",    "clean"),  # confirmed v3
    ("KNOWN_CLEAN", "zakon o parnicnom postupku",    "Član 365",  "clean"),  # confirmed v3

    # ── EDGE CASES ────────────────────────────────────────────────────────────
    ("EDGE",        "KZ",                            "Član 66",   None),
    ("EDGE",        "ustav republike srbije",        "Član 21",   None),
    ("EDGE",        "zakon o parnicnom postupku",    "Član 365",  None),
    ("EDGE",        "zakon o radu",                  "Član 65",   None),
    ("EDGE",        "zakon o obligacionim odnosima", "Član 185",  None),
]

# ── Random sample: 5 diverse laws ─────────────────────────────────────────────
RANDOM_LAWS = [
    "zakon o privrednim drustvima",
    "zakon o zastiti podataka o licnosti",
    "zakon o digitalnoj imovini",
    "zakon o upravnim sporovima",
    "zakon o vanparnicnom postupku",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_parent_text(law: str, article: str) -> tuple[str, int]:
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

emit("TEST v3 — _skini_zaglavlja() full validation (numbered header branch added)")
emit(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
emit()

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

    before_tail = parent_text[-100:].replace('\n', '↵')
    emit()
    emit(f"  BEFORE (last 100 chars): {before_tail!r}")

    if was_stripped:
        emit(f"  STRIPPED:")
        for line in stripped.split('\n'):
            if line.strip():
                emit(f"    {line.strip()!r}")
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

known_strip_total = sum(1 for r in all_articles if r[0] == "KNOWN_STRIP" and r[4] and not r[4].startswith("FETCH"))
known_clean_total = sum(1 for r in all_articles if r[0] == "KNOWN_CLEAN" and r[4] and not r[4].startswith("FETCH"))
emit(f"  KNOWN_STRIP pass rate: {sum(1 for r in all_articles if r[0]=='KNOWN_STRIP' and r[4] and not r[4].startswith('FETCH') and _skini_zaglavlja(r[4])[1])}/{known_strip_total}")
emit(f"  KNOWN_CLEAN pass rate: {sum(1 for r in all_articles if r[0]=='KNOWN_CLEAN' and r[4] and not r[4].startswith('FETCH') and not _skini_zaglavlja(r[4])[1])}/{known_clean_total}")
emit()
if wrong == 0:
    emit("  ALL KNOWN CASES PASS — ready for commit approval")
else:
    emit(f"  {wrong} FAILURE(S) — see WRONG verdicts above before committing")
emit()
emit(f"Timestamp end: {time.strftime('%Y-%m-%d %H:%M:%S')}")

# ── Save output ────────────────────────────────────────────────────────────────
out_path = os.path.join(os.path.dirname(__file__), "test_chunker_fix_v3.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('\n'.join(out_lines) + '\n')
print(f"\n[Output saved to: {out_path}]")
