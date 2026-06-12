# -*- coding: utf-8 -*-
"""
T9 E2E verification — Commit 7a sudska praksa integration.
Run: VINDEX_CACHE_BYPASS=1 python scripts/test_c7a_e2e.py
"""
import sys, os, json, re
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

os.environ["VINDEX_CACHE_BYPASS"] = "1"

import main as _m
ask_agent = _m.ask_agent

PASS = "✅"
FAIL = "❌"

results = []

def chk(label, cond, detail=""):
    sym = PASS if cond else FAIL
    print(f"  {sym} {label}" + (f" — {detail}" if detail else ""))
    results.append((label, cond))
    return cond


print("\n" + "="*65)
print("T9 — E2E Sudska Praksa Verification")
print("="*65)

# ─── A: Q1 zabrana konkurencije — expects praksa ─────────────────────────────
print("\n[A] Q1 — Zabrana konkurencije (expects 1-3 decisions)")
q1 = "Da li poslodavac može zaposlenom da zabrani konkurentski rad nakon prestanka radnog odnosa ako ugovorom nije predviđena posebna naknada?"
r1 = ask_agent(q1)
print(f"  status={r1.get('status')} confidence={r1.get('confidence')} score={r1.get('top_score', 0):.3f}")
a1 = r1.get("data", "")

# Check ZR čl. 162 still in main answer
chk("A1: ZR čl. 162 in odgovor", "162" in a1 or "Član 162" in a1, "")

# Check SUDSKA PRAKSA section
has_sp_section = "--- SUDSKA PRAKSA" in a1
chk("A2: SUDSKA PRAKSA section present", has_sp_section)

# Parse JSON to check sudska_praksa array (if response went through structured path)
# Alternatively check the raw text section
if has_sp_section:
    sp_block = a1.split("--- SUDSKA PRAKSA")[-1].split("---")[0].strip()
    decisions_count = len(re.findall(r"^\d+\.", sp_block, re.MULTILINE))
    chk("A3: 1-3 decisions cited", 1 <= decisions_count <= 3, f"{decisions_count} decisions")
    print(f"  SUDSKA PRAKSA preview: {sp_block[:300]}")
else:
    # Maybe sudska_praksa = [] (gate applied or no relevant praksa)
    chk("A3: gate suppressed (0 decisions OK)", True, "gate applied — no praksa section")

print(f"\n  Answer preview: {a1[:400]}")

# ─── B: Menica — expects sudska_praksa = [] ──────────────────────────────────
print("\n[B] 'Šta je definicija menice po Zakonu o menici?' — expects no praksa")
q2 = "Šta je definicija menice po Zakonu o menici?"
r2 = ask_agent(q2)
print(f"  status={r2.get('status')} confidence={r2.get('confidence')} score={r2.get('top_score', 0):.3f}")
a2 = r2.get("data", "")
chk("B1: No SUDSKA PRAKSA section", "--- SUDSKA PRAKSA" not in a2,
    f"(gate correctly suppressed praksa)")

# ─── C: Regressions ──────────────────────────────────────────────────────────
print("\n[C] Regression — Q31 zabrana konkurencije ZR/162")
q31 = "Može li poslodavac zabraniti radniku da radi kod konkurentske firme nakon otkaza?"
r31 = ask_agent(q31)
print(f"  status={r31.get('status')} confidence={r31.get('confidence')} score={r31.get('top_score', 0):.3f}")
a31 = r31.get("data", "")
chk("C1: ZR/162 still in odgovor", "162" in a31, f"law={r31.get('top_law')} art={r31.get('top_article')}")
chk("C2: confidence != LOW", r31.get("confidence") != "LOW")

print("\n[C] Regression — zalog stečaj (ZOO čl. 966)")
q5 = "Šta se dešava sa zalogom u slučaju stečaja zalogodavca?"
r5 = ask_agent(q5)
print(f"  status={r5.get('status')} confidence={r5.get('confidence')} score={r5.get('top_score', 0):.3f}")
chk("C3: confidence != LOW (zalog stečaj)", r5.get("confidence") != "LOW",
    f"law={r5.get('top_law')}")

print("\n[C] Regression — jemstvo/garancija")
q_jem = "Koja je razlika između jemstva i bankarske garancije?"
r_jem = ask_agent(q_jem)
print(f"  status={r_jem.get('status')} confidence={r_jem.get('confidence')} score={r_jem.get('top_score', 0):.3f}")
chk("C4: confidence != LOW (jemstvo)", r_jem.get("confidence") != "LOW",
    f"law={r_jem.get('top_law')}")

# ─── D: Hallucination negative test ──────────────────────────────────────────
print("\n[D] Hallucination negative test — fabricated praksa should be blocked")
# This question is unlikely to have real praksa in DB → LLM might fabricate
q_fab = "Kakva je sudska praksa Vrhovnog kasacionog suda po pitanju kupovine ostrva u Jadranskom moru?"
r_fab = ask_agent(q_fab)
print(f"  status={r_fab.get('status')} confidence={r_fab.get('confidence')}")
a_fab = r_fab.get("data", "")
# Either: praksa section absent (gate filtered) OR blocked
no_fab = "--- SUDSKA PRAKSA" not in a_fab
chk("D1: No fabricated praksa (gate or LOW)", no_fab,
    "(gate suppressed or LOW confidence — both acceptable)")

# ─── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "="*65)
passed = sum(1 for _, ok in results if ok)
total  = len(results)
print(f"T9 E2E RESULT: {passed}/{total} passed")
if passed == total:
    print(f"  {PASS} ALL PASS — GREEN")
elif passed >= total - 2:
    print(f"  ~ MOSTLY PASS — YELLOW (review above)")
else:
    print(f"  {FAIL} MULTIPLE FAILURES — RED (do not commit)")

sys.exit(0 if passed == total else 1)
