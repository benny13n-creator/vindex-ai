# -*- coding: utf-8 -*-
"""
Vindex AI — shared/case_assimilation.py

Program Intake Sprint 006 (2026-08-05) — Canonical Ownership Resolution.

Sprint 005 proved one upload can contain multiple logical documents. This
module answers the question Sprint 005 deliberately left untouched: once a
document is classified, exactly which case (`predmet`) and which client
(`klijent`) does it belong to?

Governing rule, checked at every decision below (the mission's own, stated
with absolute priority): never guess. A document assigned to the wrong case
is a more serious problem than ten documents waiting for a human to confirm.
Every function here returns an explicit "review_required"/"ambiguous"
outcome rather than picking the "most likely" match — there is no scoring,
no ranking, no tie-break-by-recency. Exactly one confident match resolves;
anything else escalates.

Phase 1 audit finding this module exists to close: `predmeti` has NO
case-number column and no case-matching logic anywhere in the repo — every
non-interactive intake either required the lawyer to manually pick a case
or unconditionally created a new one. `finalize_intake_job`'s own client
lookup (`routers/smart_intake.py`, pre-Sprint-006) compared a full "First
Last" extracted name against `klijenti.ime`, a first-name-only column, with
`.limit(1)` and no disambiguation — a live bug this module's
`resolve_client_ownership()` replaces, not patches around.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from shared.deps import _get_supa

logger = logging.getLogger("vindex.case_assimilation")

# Serbian/regional company-form suffixes, DOT-FREE (looks_like_company
# strips internal dots from each token before comparing, so "d.o.o." and
# "DOO" both normalize to "doo") — a party name containing any of these as a
# whole token is treated as a legal entity (`pravno_lice`), not a person, so
# it's matched against `klijenti.firma` instead of being incorrectly split
# into ime/prezime.
_COMPANY_SUFFIX_TOKENS = (
    "doo", "ad", "dd", "jdoo", "kd", "preduzeće", "preduzece",
    "ortačko", "ortacko",
)

# Program Intake Sprint 007 (Debt 3: Case Number Normalization) — parses a
# Serbian case number into its 3 semantic parts (court-type prefix, main
# number, year) regardless of which punctuation/spacing convention the
# source used. A lawyer's own filing/registry/manual entry can render the
# SAME case number as "P 123/25", "P-123/25", "P123/25", "P-123-25", or
# "P 123 - 25" — none of these differences carry any legal meaning; they
# are formatting variance, not distinct identities. Prefix character set
# covers BOTH cases of Cyrillic (А-Я + Serbian-specific letters Ђ Ж Љ Њ Ћ Џ,
# upper AND lower — a two-letter prefix like "Пж"/"Гж" mixes an uppercase
# first letter with a lowercase second one) plus Latin Extended-A for
# č/ć/đ/š/ž (needed for latinica prefixes like "Pž"). Deliberately a
# broader class than shared/intake_extract.py's own extraction regex (that
# module is classification/extraction-layer, out of this sprint's scope to
# touch) — this function may also normalize a manually-entered case number
# from a source other than AI extraction, so it is not bound by that
# regex's own coverage.
_CASE_NUMBER_PARSE_RE = re.compile(
    r"^\s*([А-Яа-яЂЖЉЊЋЏђжљњћџA-Za-zČĆĐŠŽčćđšž]{1,3})\s*[.\-]?\s*(\d{1,6})\s*[/\-]\s*(\d{2,4})\s*$"
)


def normalize_case_number(raw: Optional[str]) -> Optional[str]:
    """Canonical form: `{PREFIX}{NUMBER}/{YEAR}`, prefix upper-cased, no
    separator between prefix and number, always a forward slash before the
    year — regardless of which of the punctuation/spacing conventions above
    the input used. Returns None for empty/whitespace-only input so callers
    can treat "no case number" uniformly whether the source was None or ''.

    Falls back to a whitespace-collapsed (but otherwise unmodified) form
    when the input doesn't match the expected 3-part shape at all — an
    unparseable string is not silently discarded (that would be indistin-
    guishable from "no case number"), but it also isn't force-fit into a
    canonical shape that might misrepresent it; it simply won't collide
    with any correctly-parsed case number's canonical form, which is the
    only property `resolve_case_ownership()` actually depends on."""
    if not raw:
        return None
    collapsed = " ".join(raw.split())
    if not collapsed:
        return None
    m = _CASE_NUMBER_PARSE_RE.match(collapsed)
    if not m:
        return collapsed
    prefix, number, year = m.groups()
    return f"{prefix.upper()}{number}/{year}"


def looks_like_company(name: str) -> bool:
    """Pure heuristic: does this extracted party name look like a legal
    entity rather than a person? Checked as whole-token matches (not
    substring containment — 'adamović' must not match 'ad'). Internal dots
    are stripped per-token (not replaced with spaces, which would shatter
    'd.o.o.' into meaningless single-letter tokens 'd'/'o'/'o') so 'd.o.o.'
    and 'DOO' both normalize to the same comparison form."""
    if not name:
        return False
    tokens = [tok.lower().strip(".,").replace(".", "") for tok in name.split()]
    return any(tok in _COMPANY_SUFFIX_TOKENS for tok in tokens if tok)


def split_person_name(full_name: str) -> tuple[str, str]:
    """First token = ime, remainder = prezime — matches `klijenti`'s own
    two-column shape. A single-word name (no space) gets an empty prezime
    rather than guessing where the split falls."""
    parts = full_name.strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


async def resolve_case_ownership(user_id: str, extracted_case_number: Optional[str]) -> dict:
    """Decide which predmet a document belongs to, when the caller has NOT
    already been given an explicit predmet_id (that case bypasses this
    function entirely — an explicit human choice is never second-guessed
    here).

    Returns one of:
      {"outcome": "create_new", "case_number": normalized-or-None}
        — no case number extracted, or extracted but matches zero existing
        cases. The mission's own documented product promise ("upload a
        lawsuit and Vindex creates a case") stays intact for the common
        case; this is not a "review required" outcome because there is
        nothing ambiguous about creating a fresh case when nothing existing
        claims to already be it.
      {"outcome": "attach", "predmet_id": ..., "naziv": ...}
        — extracted case number exact-matches EXACTLY ONE existing predmet.
      {"outcome": "review_required", "candidates": [...]}
        — extracted case number matches 2+ existing predmeti. Never picks
        one — the caller must surface the candidates and require an
        explicit predmet_id on retry."""
    case_number = normalize_case_number(extracted_case_number)
    if not case_number:
        return {"outcome": "create_new", "case_number": None}

    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id, naziv")
            .eq("user_id", user_id)
            .eq("broj_predmeta", case_number)
            .execute()
    )
    matches = res.data or []

    if not matches:
        return {"outcome": "create_new", "case_number": case_number}
    if len(matches) == 1:
        return {"outcome": "attach", "predmet_id": matches[0]["id"], "naziv": matches[0].get("naziv") or ""}
    logger.warning(
        "[CASE_ASSIMILATION] broj_predmeta '%s' odgovara %d postojećih predmeta za user=%s — review_required, ne biram nijedan.",
        case_number, len(matches), user_id[:8] if user_id else "?",
    )
    return {"outcome": "review_required", "candidates": matches, "case_number": case_number}


async def resolve_client_ownership(user_id: str, extracted_party_name: Optional[str]) -> dict:
    """Decide which klijent a document's extracted party belongs to.

    Returns one of:
      {"outcome": "create_new", "ime": ..., "prezime": ..., "firma": ..., "tip": ...}
        — no existing client matches; caller may create one with these
        fields (already correctly split/typed, replacing the pre-Sprint-006
        bug where a full "First Last" string was written entirely into the
        first-name-only `ime` column).
      {"outcome": "match", "klijent_id": ...}
        — exactly one existing klijent's full name (ime+" "+prezime, or
        firma for a company) matches, case-insensitively.
      {"outcome": "ambiguous", "candidates": [...]}
        — 2+ existing clients share the same full name (the mission's own
        named edge case: two clients with the same surname). Never guesses
        between them."""
    name = (extracted_party_name or "").strip()
    if not name:
        return {"outcome": "create_new", "ime": "", "prezime": "", "firma": None, "tip": "fizicko_lice"}

    supa = _get_supa()
    is_company = looks_like_company(name)

    if is_company:
        res = await asyncio.to_thread(
            lambda: supa.table("klijenti")
                .select("id")
                .eq("user_id", user_id)
                .ilike("firma", name)
                .neq("status", "soft_deleted")
                .execute()
        )
        matches = res.data or []
        if not matches:
            return {"outcome": "create_new", "ime": "", "prezime": "", "firma": name[:200], "tip": "pravno_lice"}
        if len(matches) == 1:
            return {"outcome": "match", "klijent_id": matches[0]["id"]}
        logger.warning("[CASE_ASSIMILATION] firma '%s' odgovara %d postojećih klijenata za user=%s — ambiguous.", name, len(matches), user_id[:8] if user_id else "?")
        return {"outcome": "ambiguous", "candidates": matches}

    ime, prezime = split_person_name(name)
    # Full-name comparison (ime + " " + prezime), not the pre-Sprint-006
    # ime-only query -- that query structurally could never match a real
    # two-word name against a first-name-only column. Fetched candidate
    # rows by first name (cheap prefilter, uses the existing
    # idx_klijenti_ime index), then the full-name match is confirmed in
    # Python since Postgrest has no clean cross-column-concat ILIKE here.
    res = await asyncio.to_thread(
        lambda: supa.table("klijenti")
            .select("id, ime, prezime")
            .eq("user_id", user_id)
            .ilike("ime", ime)
            .neq("status", "soft_deleted")
            .execute()
    )
    candidates = res.data or []
    full_name_lower = f"{ime} {prezime}".strip().lower()
    matches = [c for c in candidates if f"{(c.get('ime') or '').strip()} {(c.get('prezime') or '').strip()}".strip().lower() == full_name_lower]

    if not matches:
        return {"outcome": "create_new", "ime": ime[:100], "prezime": prezime[:100], "firma": None, "tip": "fizicko_lice"}
    if len(matches) == 1:
        return {"outcome": "match", "klijent_id": matches[0]["id"]}
    logger.warning(
        "[CASE_ASSIMILATION] ime+prezime '%s' odgovara %d postojećih klijenata za user=%s — ambiguous, isti-prezime slučaj koji misija imenuje.",
        full_name_lower, len(matches), user_id[:8] if user_id else "?",
    )
    return {"outcome": "ambiguous", "candidates": matches}


def find_conflicting_case_numbers(per_document_case_numbers: list[Optional[str]]) -> set[str]:
    """Pure function — Phase 2's own named edge case (a genuinely
    multi-case bundle, e.g. two unrelated lawsuits mis-bundled into one
    upload): if 2+ DIFFERENT non-empty case numbers appear across the
    documents produced by one job, that is real evidence this upload should
    NOT be silently assimilated as a single case under whichever document
    happened to be read first. Returns the empty set when there is at most
    one distinct case number (the overwhelmingly common case, and the only
    one this sprint auto-resolves)."""
    distinct = {normalize_case_number(cn) for cn in per_document_case_numbers if normalize_case_number(cn)}
    return distinct if len(distinct) >= 2 else set()
