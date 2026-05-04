# -*- coding: utf-8 -*-
"""
Verification report for sub-query pollution fix.

For the 10 currently-✅ queries (corrected baseline), checks whether the
expected article was present in the original-query top-30 (law-filtered)
Pinecone results.

  IN orig top-30 → full score, no penalty → SAFE from regression
  NOT in orig top-30 → 0.85× penalty applied → RISK of regression

This script is read-only (no pipeline calls) — it directly queries Pinecone
using the original query vector and checks presence of the expected article.
"""
import sys, os, logging, time
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.WARNING)

from app.services.retrieve import (
    _prepoznaj_zakon, _ugradi_query, _pretraga_vec,
)

# 10 currently-✅ queries from the corrected baseline
# (q_num, query, exp_law, exp_art_num)
CURRENTLY_OK = [
    (1,  "Koja je kazna za osnovnu krađu?",
         "KZ", "203"),
    (5,  "Kazna za prevaru iznad milion dinara?",
         "KZ", "208"),
    (8,  "Krivično delo nasilja u porodici - definicija i kazna?",
         "KZ", "194"),
    (9,  "Šta je nužna odbrana po KZ?",
         "KZ", "19"),
    (11, "Kako se utvrđuje nematerijalna šteta?",
         "zakon o obligacionim odnosima", "200"),
    (14, "Pravo na regres kod osiguravajućih društava?",
         "zakon o obligacionim odnosima", "939"),
    (19, "Pravo na naknadu zarade za vreme bolovanja?",
         "zakon o radu", "115"),
    (21, "Uslovi za razvod braka sporazumom?",
         "porodicni zakon", "40"),
    (24, "Postupak usvojenja maloletnog deteta?",
         "porodicni zakon", "311"),
    (29, "Da li je smart contract pravno obavezujući u Srbiji?",
         "zakon o digitalnoj imovini", "2"),
]

SEP = "─" * 90

print("VERIFICATION REPORT — Sub-query pollution fix")
print(f"Checking: is expected article in original-query top-30 (law-filtered)?")
print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print()

results = []
for q_num, query, exp_law, exp_art_num in CURRENTLY_OK:
    vektor = _ugradi_query(query)
    matches = _pretraga_vec(vektor, 30, exp_law)

    exp_art_label = f"Član {exp_art_num}"
    found_rank = None
    found_score = None
    for i, m in enumerate(matches, 1):
        art = (m.metadata or {}).get("article", "")
        if art == exp_art_label:
            found_rank  = i
            found_score = m.score
            break

    status = "SAFE" if found_rank else "RISK"
    results.append({
        "q":     q_num,
        "query": query,
        "art":   exp_art_label,
        "law":   exp_law,
        "rank":  found_rank,
        "score": found_score,
        "status": status,
    })

    rank_str  = f"rank #{found_rank}, score={found_score:.4f}" if found_rank else "NOT IN TOP-30"
    print(f"Q{q_num:02d} {exp_law[:30]:<30} {exp_art_label:<10}  {rank_str:<30}  → {status}")

print()
print(SEP)
safe  = sum(1 for r in results if r["status"] == "SAFE")
risk  = sum(1 for r in results if r["status"] == "RISK")
print(f"SAFE (full score): {safe}/10")
print(f"RISK (0.85× penalty): {risk}/10")
print()

if risk:
    print("RISK queries — inspect before approving benchmark:")
    for r in results:
        if r["status"] == "RISK":
            print(f"  Q{r['q']:02d} — {r['query'][:70]}")
            print(f"       Expected: {r['law']} · {r['art']}")
            print(f"       NOT found in original top-30 → will receive 0.85× base penalty")
else:
    print("All 10 currently-✅ queries have their expected article in top-30.")
    print("No regression risk from the 0.85× penalty.")
