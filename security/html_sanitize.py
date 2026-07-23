# -*- coding: utf-8 -*-
"""
Vindex AI — security/html_sanitize.py  (SEC-008)

Server-side sanitizacija za polja koja potiču iz spoljašnjeg, ne-poverljivog
izvora (npr. scraping portal.sud.rs) a kasnije se prikazuju kroz vidžete koji
rade sa innerHTML na frontendu (routers/portal_monitoring.py — court-portal
status widget, originalni SEC-008 nalaz: 'p.last_error' polje).

Ovo je DEFENSE-IN-DEPTH — client-side escHtml() u static/vindex.js ostaje
primarna odbrana; ovaj sloj obezbeđuje da je sam sadržaj već čist PRE nego
što ikad stigne do baze/frontenda, tako da eventualni propust na frontend
strani (zaboravljen escHtml poziv na nekom novom vidžetu) ne otvara XSS.

Ova polja su po definiciji OBIČAN TEKST (status predmeta, poruka o grešci) —
ne postoji legitiman razlog da sadrže HTML markup, pa se ovde ne dozvoljava
NIJEDAN tag (tags=[]) — potpuno strip, ne "safe subset" sanitizacija.
"""
from __future__ import annotations

import logging

import bleach

logger = logging.getLogger("vindex.security.html_sanitize")

# Polja koja sanitizujemo su čist tekst — nema legitimnog html taga koji bi
# ovde trebalo dozvoliti (kontrast: da postoji rich-text polje, ovde bi bila
# eksplicitna allowlist umesto praznog seta).
_NO_TAGS: list[str] = []
_NO_ATTRS: dict = {}


def sanitize_text(value: str | None, max_len: int = 2000) -> str | None:
    """
    Uklanja SVAKI HTML tag/atribut iz vrednosti — namenjeno poljima koja su
    po prirodi obican tekst (status predmeta, poruka o grešci), ne rich text.

    - None prolazi kroz nepromenjen (čest slučaj: 'last_error' se briše na
      uspešnu proveru — ne pretvarati None u prazan string ovde, pozivalac
      zavisi od te razlike).
    - bleach.clean(strip=True) uklanja tagove umesto da ih HTML-escape-uje —
      za ova polja je to ispravno: '<script>' u statusu predmeta znači
      "nešto je pošlo po zlu u ekstrakciji ili je portal kompromitovan", ne
      "prikaži bukvalno < script >".
    - Skraćuje na max_len — sprečava da jedno polje eksplodira u DB red
      (zaseban, manji problem od XSS-a, ali besplatno rešiv u istom prolazu).
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value

    cleaned = bleach.clean(value, tags=_NO_TAGS, attributes=_NO_ATTRS, strip=True)
    # bleach.clean ne dira html entitete van tagova (npr. '&amp;' ostaje) —
    # to je namerno, ne menjamo semantiku teksta, samo uklanjamo markup.

    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]

    if cleaned != value:
        logger.info(
            "[SANITIZE] Uklonjen HTML markup iz polja (dužina %d → %d)",
            len(value), len(cleaned),
        )

    return cleaned
