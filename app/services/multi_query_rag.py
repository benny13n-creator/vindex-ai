# -*- coding: utf-8 -*-
"""
Vindex AI — Multi-Query RAG Pipeline  (v2 — targeted refactor)
===============================================================
Changes from v1:
  FIX-1  classify_query_intent() + intent-aware decompose_query()
  FIX-2  Per-query cap (4) instead of global hard cap; soft cap via reranker
  FIX-3  rerank_documents() uses combined_query (original | sub1 | sub2 …) + priority boost
  FIX-4  build_structured_context() never truncates mid-article
  FIX-5  No "minimum 3 sources" rule; coverage = "sufficient" | "partial"
  FIX-6  LegalDoc.priority_score + source hierarchy weighting in reranker
  FIX-7  analyze_documents() extracts rules/exceptions/conditions/conflicts
  FIX-8  JSON output adds "coverage" and "konflikti" fields
  FIX-9  Stability safeguards: <2 docs, single-law scope, conflict detection
"""

import asyncio
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from app.services.retrieve import (
    _dohvati_parent_text,
    _get_client,
    _get_cohere,
    _get_embeddings,
    _get_index,
    _normalizuj,
    _prepoznaj_zakon,
    # FIX-1: moved to retrieve.py — imported back to avoid duplication
    _INTENT_ANGLES,
    _INTENT_RULES,
    classify_query_intent,
    decompose_query,
)

logger = logging.getLogger("vindex.multi_rag")

# ─── Pipeline constants ───────────────────────────────────────────────────────

# FIX-2: per-query cap (not global); merge happens after all queries complete
TOP_K_PER_QUERY = 4   # per sub-query Pinecone k (filtered); unfiltered uses k//2
# Soft post-rerank cap — never truncated blindly; reranker score determines inclusion
SOFT_CAP_DOCS   = 10
# FIX-4: no per-article char limit; context is managed by dropping low-ranked docs
# FIX-5: MIN_SOURCES removed — use all relevant sources, label coverage instead


# ─── FIX-6: Source hierarchy priority weights ─────────────────────────────────

# Higher weight = boosted in final scoring during reranking fallback.
# Additive boost applied to normalized Pinecone cosine score (0-1 range).
_PRIORITY_WEIGHTS: list[tuple[list[str], float]] = [
    (["ustav republike srbije", "ustav"],                    0.30),  # Constitution
    (["evropska konvencija", "ekljp", "medjunarodni ugovor",
      "medjunarodni pakt"],                                  0.25),  # Intl treaties / ECHR
    # Major codified laws (statutes) — standard weight
    (["zakonik o krivicnom postupku", "krivicni zakonik",
      "zakon o parnicnom postupku", "zakon o radu",
      "zakon o obligacionim odnosima", "zakon o nasledjivanju",
      "zakon o privrednim drustvima", "zakon o digitalnoj imovini",
      "zakon o opstem upravnom postupku", "zakon o upravnim sporovima",
      "zakon o izvrsenju i obezbedjenju",
      "zakon o sprecavanju pranja novca i finansiranja terorizma"],   0.10),
    # By-laws, rulebooks, decisions — lowest weight
    (["pravilnik", "uredba", "odluka", "uputstvo", "naredba"],       0.05),
]


def _get_priority_score(law: str) -> float:
    """Return additive priority weight for a law string (normalized)."""
    law_norm = _normalizuj(law)
    for keywords, weight in _PRIORITY_WEIGHTS:
        if any(kw in law_norm for kw in keywords):
            return weight
    return 0.10  # unknown law treated as statute-level


# ─── Document dataclass ───────────────────────────────────────────────────────

class LegalDoc:
    """Structured legal document with full metadata, including priority_score."""

    # FIX-6: added priority_score slot
    __slots__ = ("doc_id", "law", "article", "text", "score", "priority_score")

    def __init__(
        self,
        doc_id:         str,
        law:            str,
        article:        str,
        text:           str,
        score:          float,
        priority_score: float = 0.10,
    ):
        self.doc_id         = doc_id
        self.law            = law
        self.article        = article
        self.text           = text
        self.score          = score
        self.priority_score = priority_score  # FIX-6: hierarchy weight

    @property
    def dedup_key(self) -> str:
        return f"{_normalizuj(self.law)}::{_normalizuj(self.article)}"

    def __repr__(self) -> str:
        return (
            f"<LegalDoc law={self.law!r} article={self.article!r} "
            f"score={self.score:.3f} priority={self.priority_score}>"
        )


def _match_to_doc(match) -> LegalDoc:
    """Convert a Pinecone match to a LegalDoc, computing priority_score immediately."""
    meta    = match.metadata or {}
    law     = meta.get("law",     "Nepoznat zakon")
    article = meta.get("article", "Nepoznat član")
    text    = _dohvati_parent_text(match) or (meta.get("text") or "").strip()
    return LegalDoc(
        doc_id         = match.id,
        law            = law,
        article        = article,
        text           = text,
        score          = float(match.score),
        priority_score = _get_priority_score(law),  # FIX-6
    )


# ─── FIX-2: Multi-retrieval with per-query cap ────────────────────────────────

def _single_query_retrieve(
    query: str,
    k: int,
    law_filter: Optional[str],
) -> list[LegalDoc]:
    """One Pinecone vector search. Returns LegalDoc list (may overlap across calls)."""
    index      = _get_index()
    embeddings = _get_embeddings()
    try:
        vector  = embeddings.embed_query(query)
        filt    = {"law": {"$eq": law_filter}} if law_filter else None
        matches = index.query(
            vector=vector, top_k=k, include_metadata=True, filter=filt
        ).matches
        return [_match_to_doc(m) for m in matches]
    except Exception as exc:
        logger.warning("[RETRIEVE] Greška za query='%.60s': %s", query, exc)
        return []


def retrieve_multi(
    query_list: list[str],
    top_k: int = TOP_K_PER_QUERY,
    law_filter: Optional[str] = None,
) -> list[LegalDoc]:
    """
    FIX-2: Parallel Pinecone retrieval with per-query cap.

    Each sub-query runs two searches:
      - filtered (top_k=4):   high precision for the detected law
      - unfiltered (top_k=2): cross-law recall

    Merging all pools gives balanced representation across sub-queries.
    No global truncation here — soft cap is applied in deduplicate_and_group().
    """
    if not query_list:
        return []

    all_docs: list[LegalDoc] = []
    max_workers = min(len(query_list) * 2, 16)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for q in query_list:
            # FIX-2: per-query cap (top_k = 4), not a global pool cap
            futures.append(executor.submit(_single_query_retrieve, q, top_k, law_filter))
            futures.append(executor.submit(_single_query_retrieve, q, max(top_k // 2, 2), None))

        for fut in as_completed(futures):
            try:
                all_docs.extend(fut.result())
            except Exception as exc:
                logger.warning("[RETRIEVE_MULTI] Future greška: %s", exc)

    logger.info(
        "[RETRIEVE_MULTI] %d queries × 2 searches (k=%d+%d) → %d raw docs (before dedup)",
        len(query_list), top_k, max(top_k // 2, 2), len(all_docs),
    )
    return all_docs


# ─── Deduplication + grouping ─────────────────────────────────────────────────

def deduplicate_and_group(
    docs: list[LegalDoc],
) -> dict[str, list[LegalDoc]]:
    """
    FIX-2: Deduplicate by (law + article) key; keep highest Pinecone-scored copy.
    No hard cap here — the reranker applies the soft cap (SOFT_CAP_DOCS).

    Returns: {law_name: [LegalDoc, ...]}
    """
    by_key: dict[str, LegalDoc] = {}
    for doc in sorted(docs, key=lambda d: d.score, reverse=True):
        key = doc.dedup_key
        if key not in by_key:
            by_key[key] = doc

    grouped: dict[str, list[LegalDoc]] = {}
    for doc in by_key.values():
        grouped.setdefault(doc.law, []).append(doc)

    total = sum(len(v) for v in grouped.values())
    logger.info(
        "[DEDUP] %d raw → %d unique articles across %d laws",
        len(docs), total, len(grouped),
    )
    return grouped


# ─── FIX-3 + FIX-6: Reranking with combined query and priority boost ──────────

def rerank_documents(
    query: str,
    sub_queries: list[str],
    docs: list[LegalDoc],
    top_n: int = 8,
) -> list[LegalDoc]:
    """
    FIX-3: Use combined_query = original + " | " + sub_queries for Cohere,
           so reranking reflects ALL angles, not just the original phrasing.

    FIX-6: In the score-sort fallback, boost by priority_score so constitutional
           and treaty sources rank above by-laws even at equal semantic similarity.

    Returns top_n most relevant docs.
    """
    if not docs:
        return []

    # FIX-3: build a multi-intent query string for Cohere
    combined_query = query
    if sub_queries:
        combined_query = query + " | " + " | ".join(sub_queries[:4])
    logger.debug("[RERANK] combined_query='%.120s'", combined_query)

    co = _get_cohere()
    if co is None:
        logger.info("[RERANK] Cohere nedostupan — skor-sort + priority boost")
        # FIX-6: fallback sort uses semantic_score + priority_score
        return sorted(
            docs,
            key=lambda d: d.score + d.priority_score,
            reverse=True,
        )[:top_n]

    texts = [d.text[:1200] for d in docs]
    try:
        result = co.rerank(
            model     = "rerank-multilingual-v3.0",
            query     = combined_query,   # FIX-3: multi-angle combined query
            documents = texts,
            top_n     = min(top_n, len(docs)),
        )
        # FIX-6: apply additive priority boost to Cohere relevance scores,
        # then re-sort so high-priority sources don't lose to by-laws
        scored: list[tuple[float, LegalDoc]] = []
        for r in result.results:
            doc          = docs[r.index]
            final_score  = r.relevance_score + doc.priority_score  # FIX-6
            scored.append((final_score, doc))

        reranked = [doc for _, doc in sorted(scored, key=lambda x: x[0], reverse=True)]
        logger.info("[RERANK] Cohere + priority: top-%d od %d", len(reranked), len(docs))
        return reranked
    except Exception as exc:
        logger.warning("[RERANK] Cohere greška: %s — fallback na skor-sort + priority", exc)
        return sorted(
            docs,
            key=lambda d: d.score + d.priority_score,
            reverse=True,
        )[:top_n]


# ─── FIX-4: Context builder — no mid-article truncation ──────────────────────

# Total context budget: if exceeded, drop lowest-ranked docs (never cut article text)
_CONTEXT_TOTAL_BUDGET = 12_000  # chars; stays within GPT-4o 128k but keeps prompt lean


def build_structured_context(grouped: dict[str, list[LegalDoc]]) -> str:
    """
    FIX-4: Never truncate article text mid-provision.

    Strategy:
      - Render articles in full.
      - If cumulative context would exceed _CONTEXT_TOTAL_BUDGET, stop adding
        more articles (lowest-ranked ones are dropped, not partially included).
      - Grouped by law, laws ordered by first-doc priority_score (highest first).
    """
    # Order law groups by max priority_score of their docs (Constitution first etc.)
    ordered_laws = sorted(
        grouped.items(),
        key=lambda kv: max(d.priority_score for d in kv[1]),
        reverse=True,
    )

    sections: list[str] = []
    total_chars = 0

    for law, docs in ordered_laws:
        law_lines = [f"[LAW: {law}]"]
        for doc in docs:
            # FIX-4: use full text — never truncate; budget check drops whole articles
            entry = f"{doc.article}: {doc.text}"
            if total_chars + len(entry) > _CONTEXT_TOTAL_BUDGET:
                # Budget exceeded — skip this article entirely (no partial text)
                logger.debug(
                    "[CONTEXT] Budget przekroczony — pomijam %s/%s (len=%d)",
                    law, doc.article, len(entry),
                )
                continue
            law_lines.append(entry)
            total_chars += len(entry)

        # Only add the law section if at least one article fit
        if len(law_lines) > 1:
            sections.append("\n".join(law_lines))

    context = "\n\n".join(sections)
    logger.info("[CONTEXT] %d chars across %d law sections", total_chars, len(sections))
    return context


# ─── FIX-7: Legal reasoning layer ────────────────────────────────────────────

def analyze_documents(docs: list[LegalDoc]) -> dict:
    """
    FIX-7: Lightweight LLM pass to extract structured legal reasoning notes
    before final answer generation.

    Extracts:
      - rules:      key legal rules stated in the docs
      - exceptions: explicit exceptions or carve-outs
      - conditions: conditions required for a rule to apply
      - conflicts:  any contradictions or tensions between provisions

    Returns a dict with those four keys (empty lists/strings on failure).
    Used to enrich the generation prompt and populate "konflikti" in output.
    """
    if not docs:
        return {"rules": [], "exceptions": [], "conditions": [], "conflicts": ""}

    # Build a compact excerpt (law + article label + first 400 chars of text)
    excerpts = []
    for doc in docs[:8]:  # limit input to avoid blowing mini token budget
        excerpt = f"[{doc.law} — {doc.article}]: {doc.text[:400]}"
        excerpts.append(excerpt)
    context_str = "\n\n".join(excerpts)

    try:
        resp = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=600,
            timeout=10.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Analiziraj sledeće odredbe srpskog zakona. "
                        "Izvuci i vrati SAMO JSON sa ovim ključevima:\n"
                        "  'rules':      lista ključnih pravnih pravila (max 5)\n"
                        "  'exceptions': lista izuzetaka od pravila (max 3)\n"
                        "  'conditions': lista uslova za primenu pravila (max 3)\n"
                        "  'conflicts':  string — kratak opis ako postoje kontradikcije "
                        "između odredbi; prazan string ako nema konflikata\n"
                        "Bez uvoda, samo JSON."
                    ),
                },
                {"role": "user", "content": context_str},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        notes = json.loads(raw)
        if isinstance(notes, dict):
            logger.info(
                "[ANALYZE] rules=%d exceptions=%d conditions=%d conflicts=%s",
                len(notes.get("rules", [])),
                len(notes.get("exceptions", [])),
                len(notes.get("conditions", [])),
                bool(notes.get("conflicts", "")),
            )
            return notes
    except Exception as exc:
        logger.warning("[ANALYZE] Nije uspelo: %s — preskočeno", exc)

    return {"rules": [], "exceptions": [], "conditions": [], "conflicts": ""}


# ─── FIX-8: Updated answer generation ─────────────────────────────────────────

# FIX-5: removed "minimum 3 sources" rule; use all relevant sources
# FIX-8: added coverage and konflikti fields to schema
_ANSWER_SYSTEM_PROMPT = """\
Ti si srpski pravni asistent koji odgovara ISKLJUČIVO na osnovu dostavljenog konteksta.

PRAVILA (obavezna):
1. Koristi SAMO informacije iz konteksta — nikakvo opšte znanje nije dozvoljeno.
2. Citiraj SVE relevantne odredbe iz konteksta (ne postoji minimalni broj).
3. Ako postoji samo 1-2 relevantna izvora — to je validan odgovor; ne izmišljaj dodatne.
4. Ako postoje suprotstavljene odredbe — eksplicitno ih naznači u polju "konflikti".
5. Odgovor vrati kao validan JSON sa TAČNO ovim ključevima:
   {
     "zakljucak": "...",
     "korisceni_clanovi": [
       {"zakon": "...", "clan": "...", "tekst": "..."}
     ],
     "coverage": "sufficient | partial",
     "konflikti": "... ili prazan string",
     "napomena": "..."
   }
6. "coverage": postavi na "sufficient" ako su pronađeni relevantni izvori koji daju
   potpun odgovor; "partial" ako su izvori delimični ili nejednoznačni.
7. "tekst" u korisceni_clanovi: 2-3 rečenice, direktan citat ili parafraza.
8. "napomena": napiši ako odgovor nije potpun ili zahteva konsultaciju advokata; inače "—".
9. Ne dodavaj nikakav tekst van JSON objekta. Nikakve napomene pre/posle JSON-a.
"""


def generate_structured_answer(
    user_query: str,
    context: str,
    docs_used: list[LegalDoc],
    reasoning_notes: dict,       # FIX-7: structured analysis from analyze_documents()
) -> dict:
    """
    FIX-5: No minimum-sources enforcement.
    FIX-7: reasoning_notes injected into prompt to guide conflict/exception handling.
    FIX-8: Returns {zakljucak, korisceni_clanovi, coverage, konflikti, napomena}.
    """
    # FIX-9: stability — log warning for very thin retrieval
    source_count = len(docs_used)
    if source_count < 2:
        logger.warning("[GENERATE] Samo %d dokument(a) — odgovor verovatno nepotpun", source_count)

    # Build reasoning notes section for the prompt (injected as structured hints)
    notes_lines: list[str] = []
    if reasoning_notes.get("rules"):
        notes_lines.append("Ključna pravila: " + "; ".join(reasoning_notes["rules"]))
    if reasoning_notes.get("exceptions"):
        notes_lines.append("Izuzeci: " + "; ".join(reasoning_notes["exceptions"]))
    if reasoning_notes.get("conditions"):
        notes_lines.append("Uslovi primene: " + "; ".join(reasoning_notes["conditions"]))
    if reasoning_notes.get("conflicts"):
        notes_lines.append(f"⚠ Detektovani konflikti između odredbi: {reasoning_notes['conflicts']}")
    notes_block = ("\n\nANALIZA ODREDBI (koristiti pri formulisanju odgovora):\n"
                   + "\n".join(notes_lines)) if notes_lines else ""

    prompt = (
        f"Pitanje korisnika: {user_query}"
        f"{notes_block}"
        f"\n\nKONTEKST IZ PRAVNE BAZE:\n{context}"
    )

    # FIX-8: base error response includes all new fields
    _err_base = {
        "zakljucak":        "",
        "korisceni_clanovi": [],
        "coverage":         "partial",
        "konflikti":        "",
        "napomena":         "",
    }

    try:
        resp = _get_client().chat.completions.create(
            model       = "gpt-4o",
            temperature = 0,
            max_tokens  = 1800,
            timeout     = 30.0,
            messages=[
                {"role": "system", "content": _ANSWER_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$",           "", raw)
        parsed = json.loads(raw)

        clanovi = parsed.get("korisceni_clanovi", [])
        logger.info(
            "[GENERATE] OK — %d članova | coverage=%s | konflikt=%s",
            len(clanovi),
            parsed.get("coverage", "?"),
            bool(parsed.get("konflikti", "")),
        )
        return parsed

    except json.JSONDecodeError as exc:
        logger.error("[GENERATE] JSON parse greška: %s", exc)
        return {**_err_base, "zakljucak": "Greška pri parsiranju odgovora.", "napomena": str(exc)}
    except Exception as exc:
        logger.error("[GENERATE] LLM greška: %s", exc)
        return {**_err_base, "zakljucak": "Servis privremeno nedostupan.", "napomena": str(exc)}


# ─── FIX-5: Coverage helper ───────────────────────────────────────────────────

def _compute_coverage(docs: list[LegalDoc]) -> str:
    """
    FIX-5: Coverage = "sufficient" if ≥2 distinct laws OR ≥3 articles.
    "partial" for 1 law with ≤2 articles.
    This value is passed to the prompt as a hint; LLM makes the final call.
    """
    distinct_laws    = len({d.law for d in docs})
    distinct_articles = len({d.dedup_key for d in docs})
    if distinct_laws >= 2 or distinct_articles >= 3:
        return "sufficient"
    return "partial"


# ─── Main pipeline ────────────────────────────────────────────────────────────

def run_multi_query_rag(user_query: str) -> dict:
    """
    Orchestrates all pipeline stages with all FIX-1 through FIX-9 applied.

    Returns:
        {
          "zakljucak":         str,
          "korisceni_clanovi": [{"zakon", "clan", "tekst"}, ...],
          "coverage":          "sufficient" | "partial",
          "konflikti":         str,
          "napomena":          str
        }
    """
    t0 = time.perf_counter()

    # ── Step 1: Law detection ─────────────────────────────────────────────────
    law_hint = _prepoznaj_zakon(user_query)
    logger.info("[PIPELINE] query='%.80s' | law_hint=%s", user_query, law_hint or "—")

    # ── Step 2: FIX-1 intent-aware decomposition ──────────────────────────────
    sub_queries = decompose_query(user_query)

    all_queries: list[str] = []
    seen_q: set[str] = set()
    for q in [user_query] + sub_queries:
        if q not in seen_q:
            seen_q.add(q)
            all_queries.append(q)

    logger.info("[PIPELINE] %d total queries for retrieval", len(all_queries))

    # ── Step 3: FIX-2 per-query retrieval ────────────────────────────────────
    raw_docs = retrieve_multi(all_queries, top_k=TOP_K_PER_QUERY, law_filter=law_hint)

    # FIX-9: stability — empty retrieval
    if not raw_docs:
        logger.error("[PIPELINE] Prazni rezultati — query='%.80s'", user_query)
        return {
            "zakljucak":         "Nisu pronađeni relevantni pravni izvori za ovo pitanje.",
            "korisceni_clanovi": [],
            "coverage":          "partial",
            "konflikti":         "",
            "napomena":          "Pinecone vratio 0 rezultata. Proverite API ključeve i indeks.",
        }

    # ── Step 4: Dedup + group (FIX-2: no hard cap here) ──────────────────────
    grouped     = deduplicate_and_group(raw_docs)
    flat_unique = [doc for docs in grouped.values() for doc in docs]

    # FIX-9: stability — warn if <2 unique docs after dedup
    if len(flat_unique) < 2:
        logger.warning("[PIPELINE] Samo %d jedinstven(ih) dokument(a) nakon dedup", len(flat_unique))

    # FIX-9: stability — warn if all docs from single law
    distinct_laws = {d.law for d in flat_unique}
    if len(distinct_laws) == 1:
        logger.warning("[PIPELINE] Svi dokumenti iz jednog zakona: %s", next(iter(distinct_laws)))

    # ── Step 5: FIX-3 + FIX-6 reranking ─────────────────────────────────────
    top_docs = rerank_documents(
        query       = user_query,
        sub_queries = sub_queries,       # FIX-3: pass sub_queries for combined_query
        docs        = flat_unique,
        top_n       = min(SOFT_CAP_DOCS, len(flat_unique)),
    )

    # Re-group post-rerank (law order reflects priority + relevance)
    final_grouped: dict[str, list[LegalDoc]] = {}
    for doc in top_docs:
        final_grouped.setdefault(doc.law, []).append(doc)

    logger.info(
        "[PIPELINE] Final: %d docs | %d laws",
        len(top_docs), len(final_grouped),
    )
    for law, docs in final_grouped.items():
        logger.info("[PIPELINE]   %-50s → %s", law, [d.article for d in docs])

    # ── Step 6: FIX-4 context — no truncation ────────────────────────────────
    context = build_structured_context(final_grouped)

    # ── Step 7: FIX-7 legal reasoning analysis ───────────────────────────────
    reasoning_notes = analyze_documents(top_docs)

    # FIX-9: if analyze_documents flagged conflicts, log prominently
    if reasoning_notes.get("conflicts"):
        logger.warning("[PIPELINE] Konflikt između odredbi: %s", reasoning_notes["conflicts"])

    # ── Step 8: FIX-8 structured answer generation ───────────────────────────
    answer = generate_structured_answer(
        user_query      = user_query,
        context         = context,
        docs_used       = top_docs,
        reasoning_notes = reasoning_notes,   # FIX-7
    )

    # FIX-5: inject pipeline-computed coverage as a hint (LLM may override)
    if "coverage" not in answer:
        answer["coverage"] = _compute_coverage(top_docs)

    elapsed = time.perf_counter() - t0
    logger.info("[PIPELINE] Završeno za %.2fs", elapsed)
    return answer


# ─── Async wrapper (unchanged) ────────────────────────────────────────────────

async def run_multi_query_rag_async(user_query: str) -> dict:
    """
    Async entry point — runs the synchronous pipeline in a thread executor
    so it does not block the FastAPI event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_multi_query_rag, user_query)
