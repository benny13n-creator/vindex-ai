# -*- coding: utf-8 -*-
"""
Vindex AI — shared/constants.py

Deljene konstante koje se koriste u više router modula.
"""

# Očekivani tipovi dokaza po tipu spora
# Koristi se u: routers/matter_intel.py i routers/ccc.py
EXPECTED_DOCS: dict = {
    "parnicno":      ["sudska_odluka", "podnesak", "ugovor", "dopis"],
    "krivicno":      ["sudska_odluka", "podnesak", "medicinska_dokumentacija", "vestacki_nalaz"],
    "radno":         ["ugovor", "dopis", "finansijska_dokumentacija", "sudska_odluka"],
    "upravno":       ["javna_isprava", "podnesak", "dopis", "sudska_odluka"],
    "porodicno":     ["javna_isprava", "medicinska_dokumentacija", "finansijska_dokumentacija", "sudska_odluka"],
    "nasledjivanje": ["javna_isprava", "ugovor", "sudska_odluka", "dopis"],
    "privredno":     ["ugovor", "finansijska_dokumentacija", "dopis", "sudska_odluka"],
    "nepokretnosti": ["javna_isprava", "ugovor", "sudska_odluka", "dopis"],
    "ostalo":        ["podnesak", "dopis"],
}
