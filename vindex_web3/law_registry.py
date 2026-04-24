# -*- coding: utf-8 -*-
"""
Sveobuhvatni registar srpskih zakona koji se primenjuju na blockchain događaje.
Pokriva: ZOO, ZDI, ZSPNFT, ZPDG.
Zero AI — čista lookup tabela. Nepoznat event_type vraća prazan spisak.
"""
from __future__ import annotations

from .interfaces import LawReference, RiskLevel

# ── Registar svih članova ─────────────────────────────────────────────────────

_REGISTRY: dict[str, LawReference] = {

    # ── ZOO (Zakon o obligacionim odnosima) ──────────────────────────────────
    "ZOO_19": LawReference(
        law_code             = "ZOO",
        law_name_sr          = "Zakon o obligacionim odnosima",
        article_number       = "19",
        article_title_sr     = "Nastanak imovinskog prava",
        article_summary_sr   = (
            "Obaveza nastaje iz ugovora, prouzrokovanja štete, sticanja bez osnova "
            "i drugih zakonom određenih činjenica."
        ),
        compliance_risk_level = "LOW",
    ),
    "ZOO_88": LawReference(
        law_code             = "ZOO",
        law_name_sr          = "Zakon o obligacionim odnosima",
        article_number       = "88",
        article_title_sr     = "Punomoćje i ovlašćenje za raspolaganje",
        article_summary_sr   = (
            "Lice može ovlastiti drugo lice da u njegovo ime preduzima pravne radnje. "
            "Punomoćje mora biti dato izričito ili proisticati iz okolnosti."
        ),
        compliance_risk_level = "LOW",
    ),
    "ZOO_124": LawReference(
        law_code             = "ZOO",
        law_name_sr          = "Zakon o obligacionim odnosima",
        article_number       = "124",
        article_title_sr     = "Neispunjenje ugovorne obaveze",
        article_summary_sr   = (
            "Dužnik koji ne ispuni obavezu ili zadocni sa ispunjenjem odgovara "
            "poveriocu za štetu. Poverilac ima pravo na raskid i naknadu štete."
        ),
        compliance_risk_level = "MEDIUM",
    ),
    "ZOO_262": LawReference(
        law_code             = "ZOO",
        law_name_sr          = "Zakon o obligacionim odnosima",
        article_number       = "262",
        article_title_sr     = "Obligacioni odnos i prenos imovine",
        article_summary_sr   = (
            "Poverilac ima pravo zahtevati od dužnika ispunjenje obaveze, a dužnik "
            "je dužan ispuniti je savesno prema sadržini obligacionog odnosa."
        ),
        compliance_risk_level = "MEDIUM",
    ),
    "ZOO_360": LawReference(
        law_code             = "ZOO",
        law_name_sr          = "Zakon o obligacionim odnosima",
        article_number       = "360",
        article_title_sr     = "Prestanak obligacije",
        article_summary_sr   = (
            "Obligacija prestaje ispunjenjem, kompenzacijom, otpustom duga, "
            "konfuzijom, nemogućnošću ispunjenja ili protekom vremena."
        ),
        compliance_risk_level = "LOW",
    ),

    # ── ZDI (Zakon o digitalnoj imovini) ─────────────────────────────────────
    "ZDI_2": LawReference(
        law_code             = "ZDI",
        law_name_sr          = "Zakon o digitalnoj imovini",
        article_number       = "2",
        article_title_sr     = "Definicije digitalne imovine",
        article_summary_sr   = (
            "Digitalna imovina su digitalni zapisi vrednosti koji se mogu digitalno "
            "čuvati, kupovati, prodavati, zamenjivati ili prenositi."
        ),
        compliance_risk_level = "LOW",
    ),
    "ZDI_9": LawReference(
        law_code             = "ZDI",
        law_name_sr          = "Zakon o digitalnoj imovini",
        article_number       = "9",
        article_title_sr     = "Uslovi za izdavanje digitalne imovine",
        article_summary_sr   = (
            "Izdavalac je dužan da pre izdavanja objavi beli papir i dobije "
            "odobrenje Narodne banke Srbije ili Komisije za hartije od vrednosti."
        ),
        compliance_risk_level = "MEDIUM",
    ),
    "ZDI_29": LawReference(
        law_code             = "ZDI",
        law_name_sr          = "Zakon o digitalnoj imovini",
        article_number       = "29",
        article_title_sr     = "Pružanje usluga digitalne imovine",
        article_summary_sr   = (
            "Pružalac usluga digitalne imovine mora posedovati licencu. "
            "Obavezna je registracija i ispunjenje kapitalnih i tehničkih uslova."
        ),
        compliance_risk_level = "MEDIUM",
    ),
    "ZDI_54": LawReference(
        law_code             = "ZDI",
        law_name_sr          = "Zakon o digitalnoj imovini",
        article_number       = "54",
        article_title_sr     = "Zabrane i ograničenja u poslovanju",
        article_summary_sr   = (
            "Zabranjeno je manipulisanje tržištem digitalnih aktiva, korišćenje "
            "privilegovanih informacija i zavaravajuće oglašavanje."
        ),
        compliance_risk_level = "HIGH",
    ),
    "ZDI_79": LawReference(
        law_code             = "ZDI",
        law_name_sr          = "Zakon o digitalnoj imovini",
        article_number       = "79",
        article_title_sr     = "Nadzor nad pružaocima usluga",
        article_summary_sr   = (
            "Nadzor vrše NBS i KHoV prema nadležnosti. Pružaoci su dužni da dostavljaju "
            "redovne izveštaje i čuvaju dokumentaciju."
        ),
        compliance_risk_level = "MEDIUM",
    ),

    # ── ZSPNFT (Zakon o sprečavanju pranja novca i finansiranja terorizma) ───
    "ZSPNFT_7": LawReference(
        law_code             = "ZSPNFT",
        law_name_sr          = "Zakon o sprečavanju pranja novca i finansiranja terorizma",
        article_number       = "7",
        article_title_sr     = "KYC obaveze i identifikacija stranaka",
        article_summary_sr   = (
            "Obveznik je dužan da utvrdi i proveri identitet stranke pre ili u "
            "toku uspostavljanja poslovnog odnosa ili izvršenja transakcije."
        ),
        compliance_risk_level = "HIGH",
    ),
    "ZSPNFT_8": LawReference(
        law_code             = "ZSPNFT",
        law_name_sr          = "Zakon o sprečavanju pranja novca i finansiranja terorizma",
        article_number       = "8",
        article_title_sr     = "Pojačane mere dubinske analize",
        article_summary_sr   = (
            "Pojačane mere se primenjuju prema politički eksponiranim licima, "
            "korespondentskim odnosima i transakcijama visokog rizika."
        ),
        compliance_risk_level = "HIGH",
    ),
    "ZSPNFT_37": LawReference(
        law_code             = "ZSPNFT",
        law_name_sr          = "Zakon o sprečavanju pranja novca i finansiranja terorizma",
        article_number       = "37",
        article_title_sr     = "Praćenje transakcija i poslovnih odnosa",
        article_summary_sr   = (
            "Obveznik je dužan da prati poslovni odnos i transakcije tokom "
            "celog trajanja odnosa radi otkrivanja neobičnih obrazaca."
        ),
        compliance_risk_level = "HIGH",
    ),
    "ZSPNFT_47": LawReference(
        law_code             = "ZSPNFT",
        law_name_sr          = "Zakon o sprečavanju pranja novca i finansiranja terorizma",
        article_number       = "47",
        article_title_sr     = "Obaveza prijave sumnjivih transakcija",
        article_summary_sr   = (
            "Obveznik je dužan da odmah, a najkasnije u roku od 24 časa, prijavi "
            "Upravi za sprečavanje pranja novca svaku sumnjivlu transakciju."
        ),
        compliance_risk_level = "CRITICAL",
    ),

    # ── ZPDG (Zakon o porezu na dohodak građana) ──────────────────────────────
    "ZPDG_72b": LawReference(
        law_code             = "ZPDG",
        law_name_sr          = "Zakon o porezu na dohodak gradjana",
        article_number       = "72b",
        article_title_sr     = "Oporezivanje prihoda od digitalne imovine",
        article_summary_sr   = (
            "Prihodi od prodaje digitalne imovine oporezuju se po stopi od 15%. "
            "Obveznik je dužan da sam obračuna i plati porez."
        ),
        compliance_risk_level = "MEDIUM",
    ),
    "ZPDG_72v": LawReference(
        law_code             = "ZPDG",
        law_name_sr          = "Zakon o porezu na dohodak gradjana",
        article_number       = "72v",
        article_title_sr     = "Kapitalna dobit od digitalne imovine",
        article_summary_sr   = (
            "Kapitalnom dobiti smatra se pozitivna razlika između prodajne i "
            "nabavne vrednosti digitalne imovine. Gubitak se može preneti."
        ),
        compliance_risk_level = "MEDIUM",
    ),
}

# ── Mapiranje event_type → lista ključeva registra ────────────────────────────

_EVENT_LAW_MAP: dict[str, list[str]] = {
    "transfer":       ["ZOO_262", "ZDI_29",  "ZSPNFT_37", "ZPDG_72b"],
    "payment_failed": ["ZOO_262", "ZSPNFT_37", "ZSPNFT_47"],
    "contract_call":  ["ZOO_124", "ZDI_29",  "ZDI_54"],
    "approval":       ["ZOO_88",  "ZDI_29"],
    "mint":           ["ZOO_19",  "ZDI_9",   "ZDI_54",  "ZPDG_72b", "ZPDG_72v"],
    "burn":           ["ZOO_360", "ZDI_2",   "ZPDG_72v"],
}

# Poredak rizika za izračunavanje najvišeg nivoa
_RISK_ORDER: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def get_applicable_laws(event_type: str) -> list[LawReference]:
    """
    Vraća listu svih primenjivih zakonskih članova za dati event_type.
    Nepoznat event_type vraća prazan spisak (ne baca grešku).
    """
    keys = _EVENT_LAW_MAP.get(event_type, [])
    return [_REGISTRY[k] for k in keys if k in _REGISTRY]


def highest_risk_level(laws: list[LawReference]) -> str:
    """Vraća najviši compliance_risk_level iz liste zakona."""
    if not laws:
        return "LOW"
    return max(laws, key=lambda l: _RISK_ORDER.get(l.compliance_risk_level, 0)).compliance_risk_level


def get_law_by_key(key: str) -> LawReference | None:
    """Direktan pristup registru po ključu (npr. 'ZOO_262')."""
    return _REGISTRY.get(key)
