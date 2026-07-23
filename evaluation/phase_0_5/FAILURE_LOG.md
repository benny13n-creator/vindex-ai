# Phase 0.5 — Failure Log

Not a bug tracker. This file records **why LRE lost to Genome** (or vice
versa) on specific cases — founder, 2026-07-23: *"To će postati zlato za
razvoj."* A bug list tells you something broke; this tells you *what kind*
of reasoning LRE is currently bad at, which is what actually informs
Phase 1+ and future engines (Argument Graph, Precedent Engine, etc.).

Add one entry per case where either analysis lost clearly (not for ties,
not for close calls — only for a defensible, specific loss). Keep every
entry in this exact shape — free-form notes belong in the case's own
`score_sheet.notes`, not here.

## Entry format

```
### Case <predmet_id or anonymized index>

**Gubitnik:** LRE | Genome

**Razlog:** <jedna rečenica, konkretna — ne "lošije rezonovanje">

**Uzrok:** <kategorija — npr. "Evidence mapping", "Retrieval promašaj",
"Legal element pogrešno formulisan", "GPT halucinacija van SOURCE-n
ograničenja" (ne bi trebalo da se desi, flag odmah ako se desi),
"Genome-ova narativna formulacija ubedljivija ali netačna">

**Akcija:** <konkretan sledeći korak, ili "nema — jedan slučaj, prati
obrazac pre akcije">
```

## Example (illustrative, not a real entry)

### Case 17

**Gubitnik:** LRE

**Razlog:** LRE nije povezao dokaz 5 sa članom 172 iako je veza očigledna
iz teksta dokumenta.

**Uzrok:** Evidence mapping — dokaz 5 nije bio u top-6 retrieved
predmet_dokazi (Evidence Vault limit u `_fetch_facts`, `limit(30)` — dokaz
je postojao ali možda nije bio dovoljno visoko rangiran za GPT-4o kontekst
prozor, ili GPT ga je video ali nije povezao).

**Akcija:** Proveriti da li se dokaz 5 uopšte pojavio u prompt-u
(`_build_reasoning_prompt` FACT-n listi) pre nego što se pretpostavi
model-side propust.

---

## Entries

*(prazno dok Phase 0.5 skoring ne počne)*
