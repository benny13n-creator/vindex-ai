# Legal Evaluation Corpus — Changelog

Founder's framing (2026-07-15): "Golden Dataset" sounds like something
static. It isn't — it's a product with releases, like anything else built
here. Every meaningful batch of new documents, new edge cases, new
annotations, or a revised annotation schema is a new **LEC version**,
recorded here and stamped in `VERSION`.

A version bump is the unit the [Stability KPI](README.md#stability-kpi)
compares against — "did accuracy hold between LEC v2 and LEC v3" is a more
honest question than "did today's run look okay."

## v1 — 2026-07-15

Initial scaffold. Three-tier structure (`a_clean_digital` /
`b_typical_serbian` / `c_nightmare`), `difficulty` axis, `annotator` /
`reviewed_by` / `agreement` fields, optional `error_source` on contested
annotations. **Zero documents.** Ships empty on purpose — nothing here is
fabricated to look like real accuracy data.

Next version bump happens when the founder adds the first real batch of
annotated documents (target: 3-5 office contributions, ~30 documents each,
per the sourcing note in the README — diversity of court/style/scan quality
matters more than raw volume).
