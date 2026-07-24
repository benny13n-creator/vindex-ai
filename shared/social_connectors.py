# -*- coding: utf-8 -*-
"""
Vindex AI — shared/social_connectors.py

KORAK D: Legal Thought Leadership & Content Agent (2026-07-24)

Bezbedan format-adapter za eksterne platforme (LinkedIn, Blog). NAMERNO ne
sadrži NIJEDAN stvaran HTTP poziv ka spoljnom API-ju -- ovaj modul samo
PRIPREMA payload u formatu koji bi ciljna platforma očekivala, i vraća ga
pozivaocu da ga PRIKAŽE ili izveze (npr. copy-paste, ručno kačenje). Stvarno
slanje (LinkedIn UGC Post API poziv, webhook ka CMS-u, itd.) je namerno
NEIMPLEMENTIRANO -- to bi bio poseban, eksplicitno odobren integracioni
korak (OAuth aplikacija odobrena od strane LinkedIn-a, founder-ova odluka
o webhook cilju), ne nešto što treba tiho da postoji kao nusprodukt Koraka D.

Svaka funkcija ovde je čista (bez I/O) i can be unit-testirana bez mreže.
"""
from typing import Optional

_MAX_LINKEDIN_CHARS = 3000  # LinkedIn UGC post character limit (dokumentovano od strane LinkedIn-a)


def format_for_linkedin(naslov: str, tekst: str, izvor_opis: Optional[str] = None) -> dict:
    """Priprema payload OBLIK koji LinkedIn UGC Post API očekuje
    (https://learn.microsoft.com/linkedin/marketing/community-management/shares/share-api)
    -- BEZ autora/URN-a (ti podaci zahtevaju stvarnu OAuth sesiju koju ovaj
    modul namerno ne poseduje) i BEZ slanja. Pozivalac je odgovoran da ovaj
    payload prosledi stvarnom LinkedIn integracionom sloju KADA (i ako) on
    bude izgrađen uz eksplicitno odobrenje."""
    telo = tekst.strip()
    if izvor_opis:
        telo = f"{telo}\n\n— na osnovu: {izvor_opis}"
    telo = telo[:_MAX_LINKEDIN_CHARS]

    return {
        "platforma": "linkedin",
        "posti_se_automatski": False,
        "payload_oblik": {
            "author": "<POPUNJAVA SE PRI STVARNOJ INTEGRACIJI — URN autorovog LinkedIn naloga>",
            "lifecycleState": "DRAFT",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": telo},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        },
        "napomena": (
            "Ovo je PRIKAZ formata, ne stvaran zahtev. lifecycleState je "
            "namerno 'DRAFT' — stvarno objavljivanje zahteva poseban, "
            "eksplicitno odobren integracioni korak (v. docstring modula)."
        ),
    }


def format_for_blog(naslov: str, tekst: str, izvor_opis: Optional[str] = None) -> dict:
    """Priprema generički blog-post oblik (naslov + telo + meta) — format je
    namerno platform-agnostičan (Markdown telo) jer Vindex trenutno nema
    ugovoren CMS/webhook cilj. Isto ograničenje kao format_for_linkedin:
    NEMA slanja."""
    telo = tekst.strip()
    if izvor_opis:
        telo = f"{telo}\n\n*Na osnovu: {izvor_opis}*"

    return {
        "platforma": "blog",
        "posti_se_automatski": False,
        "payload_oblik": {
            "title": naslov.strip() or "(bez naslova)",
            "body_markdown": telo,
            "status": "draft",
        },
        "napomena": (
            "Ovo je PRIKAZ formata, ne stvaran zahtev. status je namerno "
            "'draft' — objavljivanje na stvarnom CMS-u/blogu zahteva "
            "poseban, eksplicitno odobren integracioni korak."
        ),
    }


def format_draft(platforma: str, naslov: str, tekst: str, izvor_opis: Optional[str] = None) -> dict:
    """Dispečer po platformi. Baca ValueError za nepoznatu platformu --
    namerno glasno (pozivalac treba da zna da format ne postoji, ne da
    tiho dobije prazan/pogrešan payload)."""
    if platforma == "linkedin":
        return format_for_linkedin(naslov, tekst, izvor_opis)
    if platforma == "blog":
        return format_for_blog(naslov, tekst, izvor_opis)
    raise ValueError(f"Nepoznata platforma: {platforma}")
