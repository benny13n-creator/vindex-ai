# VINDEX V2 — PRODUCT ARCHITECTURE DECISION PAD-001

**Status:** FOUNDER APPROVED — LOCKED
**Approved:** 2026-10-09

Changes to this document require explicit founder authorization.

---

## A. What Vindex is

Vindex = Legal Operating System.

Vindex is NOT a chatbot, a pile of AI features, a generic case-management system,
an AI Judge demo, or a collection of disconnected agents.

Canonical legal workflow:

case → documents → parties → evidence → deadlines → hearings → legal research →
reasoning → strategy → drafting → actions → history

## B. Canonical product model

OBSERVE → UNDERSTAND → REMEMBER → REASON → PLAN → WORK → LEARN

## C. Case Genome

Case Genome is a central Vindex capability.

## D. Law Brain

Law Brain is a central Vindex capability.

## E. Legal Intelligence

Legal Intelligence is a central Vindex capability.

## F. Autonomous Vindex

Autonomous Vindex is a central product objective.

## G. Autonomy levels

Beta autonomy target = A2/A3.

| Level | Name |
|-------|------|
| A0 | Observe |
| A1 | Detect |
| A2 | Prepare |
| A3 | Organize |
| A4 | Internal Execute |
| A5 | External Legal Act |

A5 requires explicit human approval.

## H. Canonical architecture

CHANGE
→ EVENT BUS
→ CASE EVOLUTION
→ CASE GENOME / LAW BRAIN / LEGAL AUTHORITY
→ INTELLIGENCE
→ CASE ACTIONS
→ AGENTS
→ WORK PRODUCTS
→ WORKSPACE
→ LAWYER
→ FINAL ARTIFACT
→ OUTCOME
→ LAW BRAIN

## I. Case Actions

Case Actions is the canonical operational answer to:
"What must be done next?"

## J. Agents

Agents are workers. They are NOT systems of record.

## K. Systems of record

Case Genome / Law Brain / Case Actions / Legal Authority remain systems of record
or canonical domain layers according to their domain responsibility.

## L. Simplicity

New V2 must remain simple even if backend intelligence is complex.

## M. Capability preservation

Existing capabilities cannot be removed merely because their current
implementation is imperfect.

Capabilities that are old, duplicated, unreliable, hidden or architecturally
awkward are: PRESERVE → CONSOLIDATE → HARDEN → RECONNECT — not DELETE.

No existing Vindex capability may be physically removed unless all four exist:

1. caller/dependency proof;
2. replacement coverage proof;
3. preservation proof;
4. explicit founder approval.

## N. Change control

Changes to PAD-001 require explicit founder authorization.

---

### Five strategic pillars (locked)

1. Living Matter / Case Genome
2. Law Brain
3. Legal Intelligence
4. Autonomous Work
5. Trusted Legal Execution

None of these pillars may be retired or de-scoped.
