# -*- coding: utf-8 -*-
"""
Test for Faza 2.2 cleanup (2026-07-18): routers/strategija.py's APIRouter
now declares prefix="/strategija" instead of each of the 9 routes
hardcoding the full path individually. Behavior-preserving refactor —
this test proves the resolved route table is identical to what it was
before (same 9 full paths, same methods), not just that the router imports.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_strategija_router_resolves_to_same_paths_as_before():
    from routers.strategija import router

    expected_paths = {
        "/strategija/red-team",
        "/strategija/litigation",
        "/strategija/sudija",
        "/strategija/due-diligence",
        "/strategija/revizor",
        "/strategija/witness",
        "/strategija/sudija-v2",
        "/strategija/kompletna-analiza",
        "/strategija/v2/analiza",
    }
    actual_paths = {route.path for route in router.routes}
    assert actual_paths == expected_paths


def test_strategija_router_all_routes_are_post():
    from routers.strategija import router
    for route in router.routes:
        assert "POST" in route.methods
