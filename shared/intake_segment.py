# -*- coding: utf-8 -*-
"""
Vindex AI — shared/intake_segment.py

Program Intake Sprint 005 (2026-08-05) — Canonical Document Segmentation.

Deliberately NOT named anything with "segment" collision risk beyond this
module's own boundary: `analiza/segmenter.py` already owns "segment" to mean
a sub-document structural unit (a contract clause, a judgment section) for
LLM-context shaping (Forensic Legal Audit, Evidence Vault grounding) — a
completely different axis of the word. THIS module answers a different
question: how many separate PHYSICAL/LOGICAL documents does one uploaded
file actually contain, before classification ever runs on any of them.
Never import from or extend `analiza/segmenter.py` here, and never let this
module's `Segment` be confused with that one's `Segment` dataclass.

Design: one pure function, zero I/O (no `_get_supa()`, no `asyncio`, no
imports beyond the standard library + `re`) — trivially unit-testable with
literal in-memory input, matching `shared/intake_classify.py`'s own
"heuristic-first, cheap, explicit about what it doesn't know" philosophy.

Governing principle (the mission's own explicit, highest-priority rule):
"Ne optimizuj za to da sistem 'što češće' deli PDF. Optimizuj za to da
nikada ne podeli PDF pogrešno kada nema dovoljno dokaza." A single
wrongly-split legal filing is worse than one correctly-unsplit bundle —
every threshold below is tuned toward that asymmetry, not toward splitting
often.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ── Reused, not reinvented — same keyword vocabulary intake_classify.py's
# own classify_heuristic() already uses for whole-document classification
# (Core Consolidation: one owner for "this word means a new legal document
# is starting," not a segmentation-specific copy that could drift). Kept as
# a local literal copy (not an import) because intake_classify.py's own
# _HEURISTICS is keyed to its 13-value English taxonomy and scoped to a
# document's own first _HEAD_CHARS — this module only needs the trigger
# PHRASES themselves, evaluated per-page, not the full classification
# mapping. See CANONICAL_SEGMENTATION_SIGNAL_SPECIFICATION.md for the full
# per-signal design rationale (pattern, strength, false-positive, mitigation).
_HEADING_KEYWORDS = (
    "ТУЖБА", "TUŽBA",
    "ПРЕСУДА", "PRESUDA",
    "РЕШЕЊЕ", "REŠENJE", "RESENJE",
    "ЖАЛБА", "ŽALBA", "ZALBA",
    "ПУНОМОЋЈЕ", "PUNOMOĆJE", "PUNOMOCJE",
    "ПРИГОВОР", "PRIGOVOR",
    "ОДГОВОР НА ТУЖБУ", "ODGOVOR NA TUŽBU", "ODGOVOR NA TUZBU",
    "ЗАХТЕВ", "ZAHTEV",
    "ПРЕДЛОГ", "PREDLOG",
)

# Serbian court case-number formats: prefix abbreviation + number/year, e.g.
# "П. бр. 1234/24", "Гж 567/23", "Рев 89/2024", "П.1234/22", "Гж.45/24".
# Matches both Cyrillic and Latin prefixes; case-insensitive.
_CASE_NUMBER_RE = re.compile(
    r"\b((?:[ПГЗКРИ]|P|G|Z|K|R|I|Gž|Гж|Rev|Рев|Iv|Ив|Kž|Кж)\s*\.?\s*(?:бр\.?|br\.?)?\s*\d{1,6}\s*/\s*\d{2,4})\b",
    re.IGNORECASE,
)

# "Strana X od Y" / "Page X of Y" footer-style page counters.
_PAGE_COUNTER_RE = re.compile(
    r"(?:Strana|Стр(?:ана)?\.?|Page)\s+(\d+)\s+(?:od|of|/)\s+(\d+)",
    re.IGNORECASE,
)

# How much of a page's own text counts as "near the top" — mirrors
# intake_classify.py's own _HEAD_CHARS=400 discipline (position matters
# more than presence: a keyword in the head of a page is signal, the same
# keyword buried mid-page in quoted prose is not).
_PAGE_HEAD_CHARS = 400

# A page below this length is treated as a near-blank physical separator
# (fax cover sheet, a blank divider between stapled originals).
_BLANK_PAGE_CHAR_THRESHOLD = 20


@dataclass(frozen=True)
class PageText:
    """One physical page's extracted text. 1-indexed `page_number` to match
    how pages are referenced everywhere else in this codebase (PDF viewers,
    "Strana X od Y" footers, a lawyer's own mental model) — never 0-indexed
    internally, to avoid an off-by-one translation layer at every caller."""
    page_number: int
    text: str
    ocr_used: bool = False


@dataclass(frozen=True)
class SegmentSignal:
    """One piece of evidence that justified (or was considered for) a
    boundary at a specific page transition. `strength` is either "strong"
    or "corroborating" — never blended into one undifferentiated score
    before a decision is made (CONFIDENCE_SPECIFICATION.md's own governing
    rule, extended here to segmentation)."""
    kind: str            # e.g. "heading_keyword", "case_number_change", "page_counter_reset", "blank_separator"
    strength: str         # "strong" | "corroborating"
    page_number: int      # the page this signal fired ON (the candidate start of a new segment)
    detail: str           # human-readable evidence, e.g. "found 'TUŽBA' at page-top" — for audit/review display


@dataclass(frozen=True)
class Segment:
    """One logical document within the original upload. Inclusive, 1-based
    page range. `signals` is empty for the common single-segment case (no
    boundary anywhere cleared the threshold) — this is the expected,
    correct output for an ordinary upload, not a degraded fallback."""
    start_page: int
    end_page: int
    signals: tuple[SegmentSignal, ...] = field(default_factory=tuple)

    @property
    def reason(self) -> str:
        """Deterministic, fixed-vocabulary reason — mirrors
        intake_review_queue.reason's own exactly-N-value discipline
        (Sprint 004), never free text. See CANONICAL_SEGMENTATION_SIGNAL_
        SPECIFICATION.md for the full vocabulary."""
        if not self.signals:
            return "single_document"
        kinds = {s.kind for s in self.signals}
        if len(kinds) > 1:
            return "combined_signals"
        return next(iter(kinds))

    @property
    def confidence(self) -> float:
        """Deterministic, not learned — derived directly from which rung of
        the combination table (_confirmed_cut_points) justified this
        segment's start. Only the two combinations that ever actually
        confirm a cut can reach this property with non-empty signals (a
        segment_document() caller never sees a segment starting on
        insufficient evidence — that evidence surfaces via
        uncertain_boundaries() instead), so this is an exhaustive mapping,
        not a fallback default."""
        if not self.signals:
            return 1.0
        strong = sum(1 for s in self.signals if s.strength == "strong")
        if strong >= 2:
            return 0.95
        return 0.85  # 1 strong + 1+ corroborating


def _page_head(page_text: str) -> str:
    return page_text[:_PAGE_HEAD_CHARS]


def _find_heading_keyword(page_head: str) -> Optional[str]:
    """Returns the matched keyword only if it appears isolated near the
    top of the page — a heading, not a keyword recited mid-sentence deep
    in running prose (e.g. a rešenje's own boilerplate "Pouka o pravnom
    leku" footer routinely contains the word "žalba" in a full sentence;
    that is NOT a new document starting). 'Isolated' here means: found on
    one of the first few non-empty lines of the page head, as a
    short/standalone line, not embedded in a long sentence.

    Word-boundary matching (not plain substring containment) is load-
    bearing, not cosmetic: Serbian is heavily inflected, so an ordinary
    continuation sentence like "...u prilog zahtevu." contains "zahtevu"
    (dative case), which a plain `kw in upper` substring check would
    misfire on as if the heading keyword "ZAHTEV" itself appeared — a real
    false-positive found and fixed during this sprint's own testing, not a
    hypothetical."""
    lines = [ln.strip() for ln in page_head.splitlines() if ln.strip()]
    for line in lines[:5]:
        upper = line.upper()
        # A standalone heading line is short and dominated by the keyword
        # itself -- not a full sentence that happens to contain it.
        if len(line) > 80:
            continue
        for kw in _HEADING_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", upper):
                return kw
    return None


def _find_case_number(page_head: str) -> Optional[str]:
    """Same isolation discipline as _find_heading_keyword: only counts a
    case number found as a standalone header-line token, never one cited
    inline within a paragraph of running prose (e.g. "...po žalbi tuženog
    zavedenoj pod Gž.567/23..." cites a case number mid-sentence; that is
    quoted procedural history, not this page's own identity)."""
    lines = [ln.strip() for ln in page_head.splitlines() if ln.strip()]
    for line in lines[:5]:
        if len(line) > 60:
            continue
        m = _CASE_NUMBER_RE.search(line)
        if m:
            return m.group(1)
    return None


def _find_page_counter(page_text: str) -> Optional[tuple[int, int]]:
    """Searches the whole page (footers can be anywhere near the bottom,
    unlike headings which are position-sensitive at the top) for a
    'Strana X od Y' style counter. Returns (x, y) or None."""
    m = _PAGE_COUNTER_RE.search(page_text)
    if not m:
        return None
    try:
        return int(m.group(1)), int(m.group(2))
    except ValueError:
        return None


def _is_blank(page_text: str) -> bool:
    return len(page_text.strip()) < _BLANK_PAGE_CHAR_THRESHOLD


def segment_document(pages: list[PageText]) -> list[Segment]:
    """The one canonical segmentation algorithm. One input (ordered,
    contiguous, 1-based per-page text), one output (an ordered list of
    Segment covering every page exactly once, no gaps, no overlaps).

    A single-page or otherwise unambiguous input always produces exactly
    one Segment with empty `signals` — this is not a special case, it is
    the N=1 instance of the same general algorithm (no separate "did we
    even try to segment" branch exists anywhere in this function or in any
    caller)."""
    if not pages:
        return []
    if len(pages) == 1:
        return [Segment(start_page=1, end_page=1, signals=())]

    # Step 1: detect every candidate boundary signal, per page (2..N),
    # comparing each page against the page immediately before it.
    boundary_signals: dict[int, list[SegmentSignal]] = {}

    prev_heading = _find_heading_keyword(_page_head(pages[0].text))
    prev_case_number = _find_case_number(_page_head(pages[0].text))
    prev_counter = _find_page_counter(pages[0].text)

    for i in range(1, len(pages)):
        page = pages[i]
        head = _page_head(page.text)
        signals: list[SegmentSignal] = []

        heading = _find_heading_keyword(head)
        if heading and heading != prev_heading:
            signals.append(SegmentSignal(
                kind="heading_keyword", strength="strong", page_number=page.page_number,
                detail=f"nova naslovna reč '{heading}' na vrhu strane {page.page_number}",
            ))

        case_number = _find_case_number(head)
        if case_number and prev_case_number and case_number != prev_case_number:
            signals.append(SegmentSignal(
                kind="case_number_change", strength="strong", page_number=page.page_number,
                detail=f"nov broj predmeta '{case_number}' (prethodno '{prev_case_number}')",
            ))

        counter = _find_page_counter(page.text)
        if counter and prev_counter:
            cur_x, _cur_y = counter
            prev_x, prev_y = prev_counter
            if cur_x < prev_x or (cur_x == 1 and prev_x != 1):
                signals.append(SegmentSignal(
                    kind="page_counter_reset", strength="corroborating", page_number=page.page_number,
                    detail=f"brojač strana resetovan (prethodno {prev_x}/{prev_y}, sada {cur_x})",
                ))

        if _is_blank(pages[i - 1].text) and not _is_blank(page.text):
            signals.append(SegmentSignal(
                kind="blank_separator", strength="corroborating", page_number=page.page_number,
                detail=f"prazna strana {pages[i - 1].page_number} razdvaja sadržaj",
            ))

        if signals:
            boundary_signals[page.page_number] = signals

        # Only advance the "previous" trackers when THIS page itself
        # carries a clean, isolated signal of its own -- otherwise a run of
        # ordinary continuation pages (no heading, no case number at all)
        # would silently reset prev_heading/prev_case_number to None and
        # make the NEXT real heading look like a false "change" from
        # nothing, which is not the comparison this algorithm intends.
        if heading:
            prev_heading = heading
        if case_number:
            prev_case_number = case_number
        if counter:
            prev_counter = counter

    # Step 2: decide which candidate boundaries clear the auto-split bar,
    # per the mission's own explicit conservatism mandate. A boundary with
    # real-but-insufficient evidence is not silently resolved either way —
    # see CANONICAL_SEGMENTATION_ARCHITECTURE_REPORT.md for why this
    # engine itself stays a pure function returning ONLY confirmed
    # boundaries; "route to review" is the caller's (shared/intake_worker.py)
    # responsibility, driven by the `uncertain_boundaries()` companion below.
    confirmed_boundaries = _confirmed_cut_points(boundary_signals)

    # Step 3: build the segment list. Each confirmed cut page becomes the
    # START of a new segment; that segment's `signals` are the evidence
    # that justified IT starting there (why THIS page begins a new
    # document) -- not attached to the segment ending the page before.
    sorted_cuts = sorted(confirmed_boundaries.keys())
    boundaries_in_order = [1] + sorted_cuts
    segments: list[Segment] = []
    for idx, seg_start in enumerate(boundaries_in_order):
        seg_end = (boundaries_in_order[idx + 1] - 1) if idx + 1 < len(boundaries_in_order) else len(pages)
        sig = tuple(confirmed_boundaries[seg_start]) if seg_start in confirmed_boundaries else ()
        segments.append(Segment(start_page=seg_start, end_page=seg_end, signals=sig))
    return segments


def _confirmed_cut_points(boundary_signals: dict[int, list[SegmentSignal]]) -> dict[int, list[SegmentSignal]]:
    """The combination rule (CANONICAL_SEGMENTATION_SIGNAL_SPECIFICATION.md
    §2): a boundary auto-splits only when the evidence clears a
    conservative bar. Anything thinner is NOT auto-split here — it is
    surfaced separately via uncertain_boundaries() for the caller to route
    to human review, never silently resolved in either direction by this
    function."""
    confirmed: dict[int, list[SegmentSignal]] = {}
    for page, signals in boundary_signals.items():
        strong = [s for s in signals if s.strength == "strong"]
        corroborating = [s for s in signals if s.strength == "corroborating"]
        if len(strong) >= 2:
            confirmed[page] = signals
        elif len(strong) >= 1 and len(corroborating) >= 1:
            confirmed[page] = signals
        elif len(strong) >= 1:
            pass  # exactly 1 strong, zero corroboration -> uncertain, not auto-split
        # 2+ corroborating alone, or 1 lone corroborating -> uncertain or too thin, never auto-split here
    return confirmed


def uncertain_boundaries(pages: list[PageText]) -> list[SegmentSignal]:
    """Companion to segment_document(): re-runs the same signal detection
    and returns the boundaries that had REAL evidence but did not clear the
    auto-split bar (exactly 1 strong signal alone, or 2+ corroborating
    signals with no strong signal) -- the two "ROUTE TO REVIEW" rows of the
    combination table. A single lone corroborating signal, or no signal at
    all, is not returned here either (too thin to even escalate) -- see
    CANONICAL_SEGMENTATION_SIGNAL_SPECIFICATION.md §2 for the full table.

    Deliberately a separate call, not folded into segment_document()'s own
    return shape: the pure boundary decision (what IS a document) and the
    escalation decision (what MIGHT be, needing a human) are two different
    questions, kept as two small functions rather than one doing both."""
    if not pages or len(pages) == 1:
        return []

    boundary_signals: dict[int, list[SegmentSignal]] = {}
    prev_heading = _find_heading_keyword(_page_head(pages[0].text))
    prev_case_number = _find_case_number(_page_head(pages[0].text))
    prev_counter = _find_page_counter(pages[0].text)

    for i in range(1, len(pages)):
        page = pages[i]
        head = _page_head(page.text)
        signals: list[SegmentSignal] = []

        heading = _find_heading_keyword(head)
        if heading and heading != prev_heading:
            signals.append(SegmentSignal("heading_keyword", "strong", page.page_number, f"nova naslovna reč '{heading}'"))
        case_number = _find_case_number(head)
        if case_number and prev_case_number and case_number != prev_case_number:
            signals.append(SegmentSignal("case_number_change", "strong", page.page_number, f"nov broj predmeta '{case_number}'"))
        counter = _find_page_counter(page.text)
        if counter and prev_counter:
            cur_x, _ = counter
            prev_x, prev_y = prev_counter
            if cur_x < prev_x or (cur_x == 1 and prev_x != 1):
                signals.append(SegmentSignal("page_counter_reset", "corroborating", page.page_number, f"brojač resetovan ({prev_x}->{cur_x})"))
        if _is_blank(pages[i - 1].text) and not _is_blank(page.text):
            signals.append(SegmentSignal("blank_separator", "corroborating", page.page_number, "prazna strana razdvaja sadržaj"))

        if signals:
            boundary_signals[page.page_number] = signals
        if heading:
            prev_heading = heading
        if case_number:
            prev_case_number = case_number
        if counter:
            prev_counter = counter

    uncertain: list[SegmentSignal] = []
    for page, signals in boundary_signals.items():
        strong = [s for s in signals if s.strength == "strong"]
        corroborating = [s for s in signals if s.strength == "corroborating"]
        if len(strong) >= 2 or (len(strong) >= 1 and len(corroborating) >= 1):
            continue  # this one auto-splits, not uncertain
        if len(strong) == 1 and not corroborating:
            uncertain.extend(signals)
        elif len(corroborating) >= 2:
            uncertain.extend(signals)
        # a single lone corroborating signal is too thin even for review
    return uncertain
