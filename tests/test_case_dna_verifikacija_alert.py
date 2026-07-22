# -*- coding: utf-8 -*-
"""
G-032 (D27, VINDEX_OPERATIONAL_GAP_REGISTER.md) — shared/genome_validator.py's
verify_genome() 'require_review' odluka se ranije racunala i upisivala u audit,
ali nista nije reagovalo na nju (signal bez potrosaca). routers/case_dna.py::
_maybe_alert_require_review() zatvara taj gap reuse-ujuci postojeci
proactive_alerts mehanizam.

Founderovi eksplicitni review kriterijumi (2026-07-22), jedan test po svakom:
1. Alert nastaje samo JEDNOM po problemu (ne na svaki refresh dok isti
   require_review i dalje traje) -- test_no_duplicate_alert_when_still_require_review.
2. Alert sadrzi razlog (hard_flag razlog tekst, ne izmisljen "confidence %") --
   test_alert_on_transition_into_require_review.
3. require_review=False -> nema alert-a -- test_no_alert_when_not_require_review.
4. require_review=True -> alert postoji -- test_alert_on_transition_into_require_review.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_chain(data=None):
    chain = MagicMock()
    for attr in ["select", "eq", "update", "insert", "upsert", "order", "limit",
                 "is_", "in_", "lt", "single", "maybe_single", "ilike"]:
        setattr(chain, attr, MagicMock(return_value=chain))
    chain.execute = MagicMock(return_value=MagicMock(data=data))
    return chain


@pytest.mark.anyio
async def test_no_alert_when_not_require_review():
    """require_review=False -> no alert (criterion 3)."""
    from routers import case_dna as cd

    supa = MagicMock()
    supa.table = MagicMock(return_value=_make_chain(None))

    stari_genome = {"_verifikacija": {"odluka": "approve"}}
    genome = {"verzija": 5, "_verifikacija": {"odluka": "approve_with_warning", "hard_flags": []}}

    await cd._maybe_alert_require_review(supa, "predmet-1", "user-1", stari_genome, genome)

    supa.table.assert_not_called()


@pytest.mark.anyio
async def test_alert_on_transition_into_require_review():
    """require_review=True (transitioning from a non-require_review state) ->
    alert exists, and it contains the real reason (criteria 2 + 4)."""
    from routers import case_dna as cd

    chain = _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(return_value=chain)

    stari_genome = {"_verifikacija": {"odluka": "approve"}}
    genome = {
        "verzija": 5,
        "_verifikacija": {
            "odluka": "require_review",
            "hard_flags": [
                {"polje": "dokazi_rang", "razlog": "dokument 'nepostojeci.pdf' ne postoji medju dokumentima predmeta", "stavka": "nepostojeci.pdf"},
            ],
            "soft_flags": [],
        },
    }

    await cd._maybe_alert_require_review(supa, "predmet-1", "user-1", stari_genome, genome)

    supa.table.assert_called_once_with("proactive_alerts")
    chain.insert.assert_called_once()
    row = chain.insert.call_args[0][0]
    assert row["tip"] == "genome_verification_required"
    assert row["predmet_id"] == "predmet-1"
    assert row["user_id"] == "user-1"
    assert row["urgentnost"] == "visoka"
    assert row["procitana"] is False
    assert "v5" in row["naslov"]
    # The real hard_flag reason must be in the alert text -- not a generic
    # "Genome requires review" with no explanation, and no fabricated
    # confidence percentage that isn't actually computed anywhere.
    assert "nepostojeci.pdf" in row["opis"]
    assert "%" not in row["opis"]  # nema izmisljenog "confidence %"


@pytest.mark.anyio
async def test_no_duplicate_alert_when_still_require_review():
    """Same require_review problem persisting across a second refresh must
    NOT insert a second alert (criterion 1 -- no 'review needed' spam)."""
    from routers import case_dna as cd

    chain = _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(return_value=chain)

    # Old genome was ALREADY require_review (same underlying issue, unresolved).
    stari_genome = {
        "_verifikacija": {
            "odluka": "require_review",
            "hard_flags": [{"polje": "x", "razlog": "isti problem kao pre", "stavka": "x"}],
        }
    }
    genome = {
        "verzija": 6,
        "_verifikacija": {
            "odluka": "require_review",
            "hard_flags": [{"polje": "x", "razlog": "isti problem kao pre", "stavka": "x"}],
        },
    }

    await cd._maybe_alert_require_review(supa, "predmet-1", "user-1", stari_genome, genome)

    supa.table.assert_not_called()


@pytest.mark.anyio
async def test_alert_fires_again_after_problem_resolved_then_recurs():
    """If require_review clears (approve) and then recurs later, that is a
    NEW problem and must alert again -- dedup is per-transition, not permanent."""
    from routers import case_dna as cd

    chain = _make_chain(None)
    supa = MagicMock()
    supa.table = MagicMock(return_value=chain)

    stari_genome = {"_verifikacija": {"odluka": "approve"}}  # problem was resolved
    genome = {
        "verzija": 9,
        "_verifikacija": {
            "odluka": "require_review",
            "hard_flags": [{"polje": "y", "razlog": "novi problem", "stavka": "y"}],
        },
    }

    await cd._maybe_alert_require_review(supa, "predmet-1", "user-1", stari_genome, genome)

    supa.table.assert_called_once_with("proactive_alerts")
    chain.insert.assert_called_once()
