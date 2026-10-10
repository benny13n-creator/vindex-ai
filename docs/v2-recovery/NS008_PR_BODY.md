# V2 NS008 — Law Brain / Institutional Intelligence

**DRAFT — DO NOT MERGE.**

- Base: `feature/vindex-v2-ns007-while-you-sleep` (NOT main, NOT NS006)
- Head: `feature/vindex-v2-ns008-law-brain`
- `gh` is not available on this machine, so the PR was not opened automatically. Open it as a **Draft** with this text.

## What this is

A canonical **retrieval + trust + synthesis layer** over existing domain owners. It is not a new chatbot or a new knowledge database:

- `outcome_log` (human outcome)
- `staging_memory` (lawyer-verified work)
- `lessons_learned` (gated lessons)
- `memory_entries` / `memory_graph_edges` (office notes and relations)
- `predmeti` + Genome (case facts / AI analysis)
- the existing Pinecone office namespace

Raw-matter authorization is exclusively `shared/rag_acl.dozvoljeni_predmeti` (owner + active delegation). Being in the same office never grants access to a colleague's matter.

## Status

Work in progress. The task-by-task evidence is in `docs/v2-recovery/NS008_OVERNIGHT_EVIDENCE.md`, and the final summary will be filled in at the end of the sprint.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
