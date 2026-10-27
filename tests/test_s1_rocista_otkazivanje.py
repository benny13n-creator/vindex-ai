# -*- coding: utf-8 -*-
"""S1-C2 — predlozi ročišta iz dokumenata (`shared/rociste_iz_teksta.nadji_rocista`): otkazano / odloženo / skinuto
ročište nije PREDSTOJEĆE ročište i ne sme da se ponudi kao predlog (revizija Sektora 1, reprodukovano)."""
import pytest

from shared.rociste_iz_teksta import nadji_rocista


def _datumi(t):
    return [r["datum"].isoformat() for r in nadji_rocista(t)]


@pytest.mark.parametrize("t", [
    "Odlaže se ročište zakazano za 12.11.2026. godine.",
    "Otkazuje se ročište zakazano za 12.11.2026. godine u 10:00 časova.",
    "Ročište zakazano za 12.11.2026. se ne održava.",
    "Ročište zakazano za 12.11.2026. godine se skida sa dnevnog reda.",
    "Ročište zakazano za 12. 11. 2026. godine stavlja se van snage.",
    "Ročište zakazano za 12.11.2026. godine skida se sa dnevnog reda.",
    # 3. krug revizije: „novo“ kao deo reči i kvalifikator koji opisuje STARO ročište
    "Odlaže se ročište u Novom Sadu zakazano za 12.11.2026. godine.",
    "Otkazuje se sledeće ročište zakazano za 12.11.2026. godine.",
    "Odlaže se nastavak glavne rasprave zakazan za 12.11.2026. godine.",
    "Otkazano je naredno ročište zakazano za 12.11.2026. godine.",
    "Odlaže se ročište po tužbi Novaković zakazano za 12.11.2026.",
])
def test_otkazano_ili_odlozeno_rociste_nije_predlog(t):
    assert _datumi(t) == []


@pytest.mark.parametrize("t,ocekivano", [
    ("Ročište je zakazano za 12.11.2026. godine u 10:00 časova.", ["2026-11-12"]),
    ("Glavna rasprava zakazuje se za 12.11.2026. godine.", ["2026-11-12"]),
    ("Odlaže se ročište zakazano za 10.11.2026. i zakazuje se novo ročište za 12.11.2026. godine.", ["2026-11-12"]),
    ("Ročište zakazano za 10.11.2026. se odlaže, a novo ročište zakazuje se za 12.11.2026.", ["2026-11-12"]),
    # revizija S1 ispravke: nastavak opisan pridevom je NOVO ročište
    ("Odlaže se ročište i novo ročište zakazano za 12.11.2026. u 10 časova.", ["2026-11-12"]),
    ("Ročište se odlaže, nastavak zakazan za 12.11.2026. u 9 časova.", ["2026-11-12"]),
    ("Glavna rasprava se odlaže; sledeće ročište zakazano za 12.11.2026.", ["2026-11-12"]),
])
def test_novo_zakazivanje_i_dalje_daje_predlog(t, ocekivano):
    assert _datumi(t) == ocekivano
