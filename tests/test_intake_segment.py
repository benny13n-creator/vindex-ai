# -*- coding: utf-8 -*-
"""
Program Intake Sprint 005 (2026-08-05) — "Canonical Document Segmentation".
Tests for shared/intake_segment.py's pure, zero-I/O segmentation engine.

Mission's own governing rule, checked throughout: "Ne optimizuj za to da
sistem 'sto cesce' deli PDF. Optimizuj za to da nikada ne podeli PDF
pogresno kada nema dovoljno dokaza." Every false-positive test below exists
because a wrongly-split legal filing is worse than one correctly-unsplit
bundle.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.intake_segment import PageText, Segment, segment_document, uncertain_boundaries


def _page(n: int, text: str) -> PageText:
    return PageText(page_number=n, text=text)


# ═══════════════════════════════════════════════════════════════════════════
# Single document (no split warranted)
# ═══════════════════════════════════════════════════════════════════════════

def test_single_page_is_always_one_segment():
    segments = segment_document([_page(1, "TUŽBA\n\nOsnovni sud u Beogradu\n...")])
    assert len(segments) == 1
    assert segments[0].start_page == 1
    assert segments[0].end_page == 1
    assert segments[0].signals == ()
    assert segments[0].reason == "single_document"


def test_ordinary_multi_page_document_stays_one_segment():
    """A normal 5-page presuda with continuation pages (no heading repeat,
    no case-number change, no page-counter reset) must not be split."""
    pages = [
        _page(1, "ПРЕСУДА\n\nОсновни суд у Београду\nП. 245/22\n\nУ ИМЕ НАРОДА..."),
        _page(2, "...образложење пресуде наставља се овде, страна два..."),
        _page(3, "...даље образложење, страна три, без икакве нове одреднице..."),
        _page(4, "...правна поука наставак, страна четири..."),
        _page(5, "Судија\n___________\n\nДостављено странкама."),
    ]
    segments = segment_document(pages)
    assert len(segments) == 1
    assert segments[0].start_page == 1
    assert segments[0].end_page == 5


def test_boilerplate_pouka_o_pravnom_leku_does_not_trigger_false_split():
    """The mission's own named false-positive: a rešenje's closing 'Pouka o
    pravnom leku' footer routinely contains the word 'žalba' inside a full
    sentence at the BOTTOM of the page, not as an isolated heading -- must
    never be read as a new žalba document starting."""
    pages = [
        _page(1, "РЕШЕЊЕ\n\nОсновни суд у Новом Саду\nП. 100/23\n\nОдлучено је следеће..."),
        _page(2, "...образложење наставак.\n\nПоука о правном леку: Против овог решења дозвољена је жалба у року од 8 дана од дана пријема решења."),
    ]
    segments = segment_document(pages)
    assert len(segments) == 1  # the word "жалба" appears, but mid-sentence at page bottom, not a heading


def test_inflected_form_of_heading_keyword_does_not_falsely_trigger_split():
    """Regression (found during this sprint's own worker integration
    testing): Serbian is heavily inflected, so an ordinary continuation
    sentence like "...у прилог захтеву." contains "захтеву" (dative case of
    "захтев"), which a naive substring check would misread as the heading
    keyword "ЗАХТЕВ" itself appearing. _find_heading_keyword must match on
    a word boundary, not plain containment."""
    pages = [
        _page(1, "ТУЖБА\nП. бр. 100/24\nОсновни суд у Београду\n\nТужилац подноси тужбу против туженог ради накнаде штете."),
        _page(2, "Наставак образложења тужбе, страна 2.\nТужилац додатно наводи чињенице у прилог захтеву."),
    ]
    segments = segment_document(pages)
    assert len(segments) == 1  # "захтеву" is an inflected continuation word, not the heading "ЗАХТЕВ"
    assert uncertain_boundaries(pages) == []


def test_quoted_case_number_and_court_in_appellate_reasoning_does_not_split():
    """A second-instance rešenje's own 'obrazloženje' routinely recites the
    first-instance court's identity and case number inline while narrating
    procedural history -- this is quoted material, not a new document."""
    pages = [
        _page(1, "РЕШЕЊЕ\n\nВиши суд у Београду\nГж 45/24\n\nОдлучујући по жалби..."),
        _page(2, "Првостепеном пресудом Основног суда у Новом Саду, П. 245/22, утврђено је да су испуњени услови... по жалби туженог заведеној под Гж.567/23 одлучено је како следи."),
    ]
    segments = segment_document(pages)
    assert len(segments) == 1  # both a court name and 2 case numbers appear, but embedded mid-paragraph


def test_punomocje_attached_annex_does_not_auto_split_alone():
    """A punomoćje's own signature/notarization block appearing mid-upload
    is, alone (no corroborating letterhead/case-number change on the same
    page), only ever CORROBORATING per the signal spec -- must not
    auto-split by itself."""
    pages = [
        _page(1, "ТУЖБА\n\nОсновни суд у Београду\nП. 1/25\n\nТужилац подноси тужбу..."),
        _page(2, "...образложење тужбе наставак..."),
        _page(3, "ПУНОМОЋЈЕ\n\nОверено код јавног бележника, ОПУ бр. 123/25.\n\nАдвокат, Марко Марковић"),
    ]
    segments = segment_document(pages)
    # A bare heading_keyword hit on page 3 (PUNOMOĆJE) IS one strong signal
    # alone -- per the combination table this alone does not auto-split
    # (needs 2 strong, or 1 strong + 1 corroborating). Confirm it's exactly
    # the "route to review" band, not silently kept as one AND not silently split.
    assert len(segments) == 1
    uncertain = uncertain_boundaries(pages)
    assert any(s.page_number == 3 for s in uncertain)


# ═══════════════════════════════════════════════════════════════════════════
# Multi-document (2, 10)
# ═══════════════════════════════════════════════════════════════════════════

def test_two_documents_with_new_letterhead_and_case_number_auto_splits():
    """2 STRONG signals agreeing (heading_keyword + case_number_change) at
    the same boundary -> AUTO-SPLIT, per the combination table."""
    pages = [
        _page(1, "ТУЖБА\n\nОсновни суд у Београду\nП. 1/25\n\nТужилац подноси тужбу против туженог..."),
        _page(2, "...образложење тужбе наставак..."),
        _page(3, "ПРЕСУДА\n\nОсновни суд у Београду\nП. 55/24\n\nУ ИМЕ НАРОДА, суд је донео пресуду..."),
        _page(4, "...образложење пресуде наставак..."),
    ]
    segments = segment_document(pages)
    assert len(segments) == 2
    assert segments[0].start_page == 1 and segments[0].end_page == 2
    assert segments[1].start_page == 3 and segments[1].end_page == 4
    assert segments[1].reason in ("heading_keyword", "case_number_change", "combined_signals")
    kinds = {s.kind for s in segments[1].signals}
    assert "heading_keyword" in kinds
    assert "case_number_change" in kinds


def test_ten_documents_each_correctly_bounded():
    """10 documents of the SAME act-type (realistic: a bundle of 10
    separate tužba filings) -- heading_keyword alone never 'changes'
    (always ТУЖБА), so each new document also carries its own
    page-counter reset (Strana 1 od 2) as the corroborating signal
    alongside the strong case_number_change, correctly clearing the bar."""
    pages = []
    for i in range(10):
        pages.append(_page(i * 2 + 1, f"ТУЖБА\n\nStrana 1 od 2\n\nОсновни суд у Београду\nП. {i+1}/25\n\nТужилац бр {i+1}..."))
        pages.append(_page(i * 2 + 2, f"Strana 2 od 2\n\n...образложење документа {i+1} наставак..."))
    segments = segment_document(pages)
    assert len(segments) == 10
    for i, seg in enumerate(segments):
        assert seg.start_page == i * 2 + 1
        assert seg.end_page == i * 2 + 2
    # No page lost, none duplicated -- every page covered exactly once.
    covered = []
    for seg in segments:
        covered.extend(range(seg.start_page, seg.end_page + 1))
    assert covered == list(range(1, 21))


def test_mixed_document_types_all_correctly_identified_as_separate():
    pages = [
        _page(1, "ТУЖБА\n\nОсновни суд у Београду\nП. 1/25\n\n..."),
        _page(2, "ПРЕСУДА\n\nОсновни суд у Београду\nП. 88/24\n\n..."),
        _page(3, "ПУНОМОЋЈЕ\n\nВиши суд у Београду\nГж 12/25\n\nОверено..."),
    ]
    segments = segment_document(pages)
    assert len(segments) == 3
    assert all(seg.start_page == seg.end_page for seg in segments)  # each is exactly 1 page here


# ═══════════════════════════════════════════════════════════════════════════
# Blank pages, duplicate pages
# ═══════════════════════════════════════════════════════════════════════════

def test_blank_separator_page_assigned_to_preceding_segment_not_orphaned():
    pages = [
        _page(1, "ТУЖБА\n\nОсновни суд у Београду\nП. 1/25\n\n..."),
        _page(2, ""),  # blank divider page
        _page(3, "ПРЕСУДА\n\nОсновни суд у Београду\nП. 99/24\n\n..."),
    ]
    segments = segment_document(pages)
    # blank_separator is corroborating-only; combined with the strong
    # heading_keyword hit on page 3, this DOES clear the bar (1 strong + 1 corroborating).
    assert len(segments) == 2
    # every page covered exactly once -- the blank page belongs to segment 1 (trailing filler)
    covered = []
    for seg in segments:
        covered.extend(range(seg.start_page, seg.end_page + 1))
    assert covered == [1, 2, 3]
    assert segments[0].end_page == 2  # blank page 2 assigned to the preceding segment


def test_duplicate_pages_no_page_lost_or_double_counted():
    """Two identical pages back to back (a scanning duplicate) must not
    confuse the engine into losing or double-counting a page."""
    pages = [
        _page(1, "ТУЖБА\n\nОсновни суд у Београду\nП. 1/25\n\nТекст."),
        _page(2, "ТУЖБА\n\nОсновни суд у Београду\nП. 1/25\n\nТекст."),  # exact duplicate
        _page(3, "...образложење наставак..."),
    ]
    segments = segment_document(pages)
    covered = []
    for seg in segments:
        covered.extend(range(seg.start_page, seg.end_page + 1))
    assert covered == [1, 2, 3]  # no page lost, none duplicated in the output
    # Same heading + same case number on page 2 as page 1 -- not a "change", correctly not split.
    assert len(segments) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Page-counter signal
# ═══════════════════════════════════════════════════════════════════════════

def test_page_counter_reset_corroborates_a_split_with_new_heading():
    pages = [
        _page(1, "ТУЖБА\n\nStrana 1 od 2\n\nТекст првог документа."),
        _page(2, "Strana 2 od 2\n\nНаставак текста."),
        _page(3, "ПРЕСУДА\n\nStrana 1 od 3\n\nТекст другог документа."),
    ]
    segments = segment_document(pages)
    assert len(segments) == 2
    assert segments[1].start_page == 3


def test_page_counter_alone_without_heading_is_only_corroborating_not_sufficient():
    """A page-counter reset with NO heading/case-number change at all is
    exactly 1 corroborating signal -- per the table, too thin even to
    escalate to review, must stay one document."""
    pages = [
        _page(1, "Уговор о раду\n\nStrana 1 od 2\n\nОдредбе уговора..."),
        _page(2, "Strana 1 od 5\n\nНаставак истог уговора са резетованим бројачем поглавља."),
    ]
    segments = segment_document(pages)
    assert len(segments) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Incomplete last document
# ═══════════════════════════════════════════════════════════════════════════

def test_incomplete_last_document_still_gets_its_own_segment():
    """A combined PDF where the last attached document is missing its final
    page(s) -- the engine must not lose the incomplete tail, it becomes its
    own (possibly short) segment covering whatever pages exist."""
    pages = [
        _page(1, "ТУЖБА\n\nОсновни суд у Београду\nП. 1/25\n\n..."),
        _page(2, "ПРЕСУДА\n\nОсновни суд у Београду\nП. 77/24\n\nУ ИМЕ НАРОДА..."),
        # presuda is cut off here -- no closing/signature page, only 1 page exists
    ]
    segments = segment_document(pages)
    assert len(segments) == 2
    assert segments[1].start_page == 2 and segments[1].end_page == 2  # the incomplete tail, not dropped


# ═══════════════════════════════════════════════════════════════════════════
# Very large PDF
# ═══════════════════════════════════════════════════════════════════════════

def test_large_pdf_300_pages_no_page_lost_or_duplicated():
    pages = [_page(i, f"...continuation text page {i}...") for i in range(1, 301)]
    segments = segment_document(pages)
    covered = []
    for seg in segments:
        covered.extend(range(seg.start_page, seg.end_page + 1))
    assert covered == list(range(1, 301))
    assert len(segments) == 1  # no signals anywhere -- stays one document


def test_large_pdf_500_pages_with_20_bundled_documents_all_pages_accounted_for():
    """Same realistic-bundle shape as the 10-document test above: 20
    same-act-type filings, each with its own page-counter reset as the
    corroborating signal alongside the strong case_number_change."""
    pages = []
    for i in range(20):
        base = i * 25
        pages.append(_page(base + 1, f"ТУЖБА\n\nStrana 1 od 25\n\nОсновни суд у Београду\nП. {i+1}/25\n\nПочетак документа {i+1}."))
        for j in range(2, 26):
            pages.append(_page(base + j, f"Strana {j} od 25\n\n...наставак документа {i+1}, страна {j}..."))
    assert len(pages) == 500
    segments = segment_document(pages)
    assert len(segments) == 20
    covered = []
    for seg in segments:
        covered.extend(range(seg.start_page, seg.end_page + 1))
    assert covered == list(range(1, 501))  # every one of 500 pages accounted for exactly once


# ═══════════════════════════════════════════════════════════════════════════
# Rotated / poorly-OCR'd pages — proving BEHAVIOR, not fixing OCR
# (mission's own explicit instruction: "Ne unapređivati OCR. Dokazati
# ponašanje segmentacije.")
# ═══════════════════════════════════════════════════════════════════════════

def test_garbled_ocr_text_degrades_to_no_split_not_a_false_split():
    """Garbled/rotated-page OCR output (no recognizable heading/case-number
    shape at all) must not be misread as a boundary signal -- the engine's
    conservatism means garbage input produces "keep as one," not a
    confident-looking wrong split."""
    pages = [
        _page(1, "ТУЖБА\n\nОсновни суд у Београду\nП. 1/25\n\nТекст."),
        _page(2, "l1l| ¡nc0h3r3nt 0CR g4rb4g3 fr0m r0t4t3d p4g3 !!! ###"),
        _page(3, "...образложење наставак..."),
    ]
    segments = segment_document(pages)
    assert len(segments) == 1  # garbage page produces zero recognizable signals, correctly not a boundary


def test_uncertain_boundaries_never_overlaps_confirmed_segments():
    """A sanity invariant: any page reported by uncertain_boundaries() must
    not ALSO be a start_page of a confirmed segment_document() output --
    the two functions must partition candidate boundaries into disjoint
    "confirmed" and "uncertain" sets, never double-report the same page."""
    pages = [
        _page(1, "ТУЖБА\n\nОсновни суд у Београду\nП. 1/25\n\n..."),
        _page(2, "ПУНОМОЋЈЕ\n\nОверено..."),  # 1 strong signal alone -> uncertain
        _page(3, "ПРЕСУДА\n\nОсновни суд у Београду\nП. 999/24\n\n..."),  # heading + case number -> confirmed
    ]
    segments = segment_document(pages)
    confirmed_starts = {seg.start_page for seg in segments}
    uncertain = uncertain_boundaries(pages)
    uncertain_pages = {s.page_number for s in uncertain}
    assert uncertain_pages.isdisjoint(confirmed_starts)
    assert 3 in confirmed_starts
    assert 2 in uncertain_pages
