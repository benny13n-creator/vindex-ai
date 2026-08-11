# -*- coding: utf-8 -*-
"""
Brojač za `tests/prod_db_offenders_baseline.txt`.

Bez ovog fajla je allowlist samo ventil: ko god naiđe na
`ProductionDatabaseAccessBlocked` mogao bi da doda svoje ime i nastavi dalje, a
brana bi tiho postala dekoracija. Sa njim, dodavanje imena OBARA suite dok neko
svesno ne podigne broj — uz obrazloženje zašto je novi upis u produkcionu bazu
iz testa prihvatljiv.

Isti obrazac kao `tests/test_network_offenders_baseline.py`, koji je istu ulogu
odigrao za naplative API-je i tamo se broj spustio sa 53 na 0.
"""
import os

# Wave 9 je ovde zamrznuo 115 imena. Wave 10 je problem rešio na nivou
# konfiguracije umesto na nivou DNS-a i IZMERIO da od 455 testova u tih 42 fajla
# pada TAČNO JEDAN — koji je popravljen. Lista je time prazna.
#
# OVAJ BROJ SME SAMO DA SE SMANJUJE. Sada je na dnu: svako novo ime obara suite.
MAKSIMUM = 0

_PUTANJA = os.path.join(os.path.dirname(__file__), "prod_db_offenders_baseline.txt")


def _imena() -> list:
    with open(_PUTANJA, encoding="utf-8") as f:
        return [ln.strip() for ln in f
                if ln.strip() and not ln.lstrip().startswith("#")]


def test_lista_ne_raste():
    imena = _imena()
    assert len(imena) <= MAKSIMUM, (
        f"lista prestupnika je porasla na {len(imena)} (maksimum {MAKSIMUM}). "
        f"Nov test koji dodiruje produkcionu bazu ne sme se dodati ovde — mokuj "
        f"Supabase klijent. Ako je upis u produkciju iz testa stvarno neizbežan, "
        f"podigni MAKSIMUM svesno i napiši razlog."
    )


def test_nema_duplikata():
    imena = _imena()
    assert len(imena) == len(set(imena)), "isti node id je upisan više puta"


def test_svako_ime_izgleda_kao_node_id():
    """Zaštita od toga da neko ubaci `tests/` ili wildcard i time isključi ceo fajl."""
    for ime in _imena():
        assert "::" in ime, (
            f"{ime!r} nije node id pojedinačnog testa — celi fajlovi se ne "
            f"izuzimaju, jer bi tako svaki novi test u njemu tiho dobio prolaz"
        )
        assert not ime.endswith("::"), f"{ime!r} je nepotpun"
        assert "*" not in ime, f"{ime!r} sadrži wildcard"


def test_zaglavlje_objasnjava_cenu():
    """Lista bez razloga postaje lista koju niko ne skraćuje."""
    tekst = open(_PUTANJA, encoding="utf-8").read()
    assert "append-only" in tekst, "zaglavlje ne objašnjava zašto je upis nepovratan"
    assert "LISTA JE PRAZNA" in tekst, (
        "zaglavlje mora reći da je lista prazna i zašto — prazan fajl bez "
        "objašnjenja izgleda kao greška i neko ga obriše zajedno sa branom"
    )
